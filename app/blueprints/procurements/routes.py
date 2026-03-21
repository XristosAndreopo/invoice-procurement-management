"""
app/blueprints/procurements/routes.py

Procurement routes – Enterprise Secured Version
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from flask import (
    Blueprint,
    abort,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import Procurement, ProcurementSupplier
from ...reports.award_decision_docx import AwardDecisionConstants, build_award_decision_docx
from ...reports.expense_transmittal_docx import (
    ExpenseTransmittalConstants,
    build_expense_transmittal_docx,
    build_expense_transmittal_filename,
)
from ...reports.proforma_invoice import ProformaConstants, build_proforma_invoice_pdf
from ...security import procurement_access_required, procurement_edit_required
from ...security.procurement_guards import can_mutate_procurement
from ...services.shared.parsing import next_from_request
from ...services.procurement.create import (
    build_create_procurement_page_context,
    execute_create_procurement,
)
from ...services.procurement.edit import (
    build_edit_procurement_page_context,
    execute_edit_procurement,
)
from ...services.procurement.implementation import (
    build_implementation_procurement_page_context,
    execute_implementation_procurement_update,
)
from ...services.procurement.list_pages import (
    build_all_procurements_list_context,
    build_inbox_procurements_list_context,
    build_pending_expenses_list_context,
)
from ...services.procurement.related_entities import (
    execute_add_material_line,
    execute_add_procurement_supplier,
    execute_delete_material_line,
    execute_delete_procurement_supplier,
)
from ...services.procurement_service import (
    is_in_implementation_phase,
    load_procurement,
    money_filename,
    sanitize_filename_component,
)

procurements_bp = Blueprint("procurements", __name__, url_prefix="/procurements")


@procurements_bp.route("/inbox")
@login_required
def inbox_procurements():
    context = build_inbox_procurements_list_context(
        request.args,
        allow_create=(current_user.is_admin or current_user.can_manage()),
    )
    return render_template("procurements/list.html", **context)


@procurements_bp.route("/pending-expenses")
@login_required
def pending_expenses():
    context = build_pending_expenses_list_context(request.args)
    return render_template("procurements/list.html", **context)


@procurements_bp.route("/all")
@login_required
def all_procurements():
    context = build_all_procurements_list_context(request.args)
    return render_template("procurements/list.html", **context)


@procurements_bp.route("/")
@login_required
def list_procurements():
    return redirect(url_for("procurements.inbox_procurements"))


@procurements_bp.route("/<int:procurement_id>/delete", methods=["POST"])
@login_required
@procurement_edit_required(load_procurement)
def delete_procurement(procurement_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)

    if not can_mutate_procurement(current_user, procurement):
        abort(403)

    origin = (request.form.get("delete_origin") or "").strip()
    if origin != "all_procurements":
        flash("Η διαγραφή επιτρέπεται μόνο από τη σελίδα «Όλες οι Προμήθειες».", "warning")
        return redirect(url_for("procurements.all_procurements"))

    next_url = (request.form.get("next") or "").strip()
    before_snapshot = serialize_model(procurement)

    db.session.delete(procurement)
    log_action(procurement, "DELETE", before=before_snapshot, after=None)
    db.session.commit()

    flash("Η προμήθεια διαγράφηκε επιτυχώς.", "success")
    return redirect(next_url or url_for("procurements.all_procurements"))


@procurements_bp.route("/<int:procurement_id>/reports/proforma-invoice", methods=["GET"])
@login_required
@procurement_access_required(load_procurement)
def report_proforma_invoice(procurement_id: int):
    """
    Render the proforma invoice PDF.
    """
    procurement = (
        Procurement.query.options(
            joinedload(Procurement.service_unit),
            joinedload(Procurement.handler_personnel),
            joinedload(Procurement.handler_assignment).joinedload(
                Procurement.handler_assignment.property.mapper.class_.department
            ),
            joinedload(Procurement.handler_assignment).joinedload(
                Procurement.handler_assignment.property.mapper.class_.directory
            ),
            joinedload(Procurement.supplies_links).joinedload(ProcurementSupplier.supplier),
            joinedload(Procurement.materials),
            joinedload(Procurement.withholding_profile),
            joinedload(Procurement.income_tax_rule),
        )
        .get_or_404(procurement_id)
    )

    winner = procurement.winner_supplier_obj()
    analysis = procurement.compute_payment_analysis()

    lines = list(procurement.materials or [])
    has_services = any(bool(getattr(line, "is_service", False)) for line in lines)
    table_title = "Πίνακας Παρεχόμενων Υπηρεσιών" if has_services else "Πίνακας Προμηθευτέων Υλικών"

    pdf_bytes = build_proforma_invoice_pdf(
        procurement=procurement,
        service_unit=procurement.service_unit,
        winner=winner,
        analysis=analysis,
        table_title=table_title,
        constants=ProformaConstants(
            pn_afm="090153025",
            pn_doy="ΚΕΦΟΔΕ ΑΤΤΙΚΗΣ",
            reference_goods="ΒΤ-11-1",
        ),
    )

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'inline; filename="proforma_{procurement.id}.pdf"'
    return response


@procurements_bp.route("/<int:procurement_id>/reports/award-decision", methods=["GET"])
@login_required
@procurement_access_required(load_procurement)
def report_award_decision_docx(procurement_id: int):
    """
    Build and return the Award Decision DOCX.
    """
    procurement = (
        Procurement.query.options(
            joinedload(Procurement.service_unit),
            joinedload(Procurement.handler_personnel),
            joinedload(Procurement.handler_assignment).joinedload(
                Procurement.handler_assignment.property.mapper.class_.directory
            ),
            joinedload(Procurement.handler_assignment).joinedload(
                Procurement.handler_assignment.property.mapper.class_.department
            ),
            joinedload(Procurement.supplies_links).joinedload(ProcurementSupplier.supplier),
            joinedload(Procurement.materials),
            joinedload(Procurement.withholding_profile),
            joinedload(Procurement.income_tax_rule),
        )
        .get_or_404(procurement_id)
    )

    winner = procurement.winner_supplier_obj()

    other_suppliers = []
    for link in (procurement.supplies_links or []):
        if not getattr(link, "supplier", None):
            continue
        if getattr(link, "is_winner", False):
            continue
        other_suppliers.append(link.supplier)

    analysis = procurement.compute_payment_analysis()
    lines = list(procurement.materials or [])
    is_services = any(bool(getattr(line, "is_service", False)) for line in lines)

    docx_bytes = build_award_decision_docx(
        procurement=procurement,
        service_unit=procurement.service_unit,
        winner=winner,
        other_suppliers=other_suppliers,
        analysis=analysis,
        is_services=is_services,
        constants=AwardDecisionConstants(),
    )

    kind_label = "Παροχής Υπηρεσιών" if is_services else "Προμήθειας Υλικών"
    supplier_label = sanitize_filename_component(getattr(winner, "name", None) if winner else "—")

    amount_value = getattr(procurement, "grand_total", None)
    if amount_value is None:
        amount_value = analysis.get("payable_total") or analysis.get("sum_total") or Decimal("0.00")
    amount_label = money_filename(amount_value)

    filename = f"Απόφαση Ανάθεσης {kind_label} {supplier_label} {amount_label}.docx"
    filename = sanitize_filename_component(filename).replace(" .docx", ".docx")
    if not filename.lower().endswith(".docx"):
        filename = f"{filename}.docx"

    buffer = BytesIO(docx_bytes)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        max_age=0,
    )


@procurements_bp.route("/<int:procurement_id>/reports/expense-transmittal", methods=["GET"])
@login_required
@procurement_access_required(load_procurement)
def report_expense_transmittal_docx(procurement_id: int):
    """
    Build and return the Expense Transmittal DOCX.

    REQUIRED RELATIONSHIPS
    ----------------------
    This report needs:
    - service_unit
    - winner supplier
    - materials
    - withholding_profile / income_tax_rule for payment analysis
    - committee

    SOURCE OF TRUTH MAPPINGS
    ------------------------
    The template references committee/invoice/handler-like values.
    These are resolved from the current model contract:
    - procurement.committee.description
    - procurement.invoice_number
    - procurement.invoice_date
    - procurement.materials_receipt_date
    - procurement.invoice_receipt_date
    - service_unit.supply_officer
    """
    procurement = (
        Procurement.query.options(
            joinedload(Procurement.service_unit),
            joinedload(Procurement.handler_personnel),
            joinedload(Procurement.handler_assignment).joinedload(
                Procurement.handler_assignment.property.mapper.class_.directory
            ),
            joinedload(Procurement.handler_assignment).joinedload(
                Procurement.handler_assignment.property.mapper.class_.department
            ),
            joinedload(Procurement.committee),
            joinedload(Procurement.supplies_links).joinedload(ProcurementSupplier.supplier),
            joinedload(Procurement.materials),
            joinedload(Procurement.withholding_profile),
            joinedload(Procurement.income_tax_rule),
        )
        .get_or_404(procurement_id)
    )

    winner = procurement.winner_supplier_obj()
    analysis = procurement.compute_payment_analysis()

    docx_bytes = build_expense_transmittal_docx(
        procurement=procurement,
        service_unit=procurement.service_unit,
        winner=winner,
        analysis=analysis,
        constants=ExpenseTransmittalConstants(),
    )

    filename = build_expense_transmittal_filename(
        procurement=procurement,
        winner=winner,
    )
    filename = sanitize_filename_component(filename).replace(" .docx", ".docx")
    if not filename.lower().endswith(".docx"):
        filename = f"{filename}.docx"

    buffer = BytesIO(docx_bytes)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        max_age=0,
    )


@procurements_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_procurement():
    if not (current_user.is_admin or current_user.can_manage()):
        abort(403)

    if request.method == "POST":
        if not current_user.is_admin and not current_user.service_unit_id:
            abort(403)

        result = execute_create_procurement(
            request.form,
            is_admin=current_user.is_admin,
            current_service_unit_id=current_user.service_unit_id,
        )
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok and result.entity_id is not None:
            return redirect(
                url_for(
                    "procurements.edit_procurement",
                    procurement_id=result.entity_id,
                )
            )

        return redirect(url_for("procurements.create_procurement"))

    context = build_create_procurement_page_context(
        is_admin=current_user.is_admin,
        current_service_unit_id=current_user.service_unit_id,
    )
    return render_template("procurements/new.html", **context)


@procurements_bp.route("/<int:procurement_id>/edit", methods=["GET", "POST"])
@login_required
@procurement_access_required(load_procurement)
def edit_procurement(procurement_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)
    next_url = next_from_request("procurements.inbox_procurements")

    if request.method == "POST":
        if not can_mutate_procurement(current_user, procurement):
            abort(403)

        result = execute_edit_procurement(
            procurement,
            request.form,
            is_admin=current_user.is_admin,
        )
        for item in result.flashes:
            flash(item.message, item.category)

        return redirect(
            url_for(
                "procurements.edit_procurement",
                procurement_id=procurement.id,
                next=next_url,
            )
        )

    context = build_edit_procurement_page_context(procurement, next_url)
    return render_template("procurements/edit.html", **context)


@procurements_bp.route("/<int:procurement_id>/implementation", methods=["GET", "POST"])
@login_required
@procurement_access_required(load_procurement)
def implementation_procurement(procurement_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)

    if not is_in_implementation_phase(procurement):
        return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))

    next_url = next_from_request("procurements.pending_expenses")

    if request.method == "POST":
        if not can_mutate_procurement(current_user, procurement):
            abort(403)

        result = execute_implementation_procurement_update(procurement, request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        return redirect(
            url_for(
                "procurements.implementation_procurement",
                procurement_id=procurement.id,
                next=next_url,
            )
        )

    context = build_implementation_procurement_page_context(
        procurement,
        next_url,
        can_edit=can_mutate_procurement(current_user, procurement),
    )
    return render_template("procurements/implementation.html", **context)


@procurements_bp.route("/<int:procurement_id>/suppliers/add", methods=["POST"])
@login_required
@procurement_edit_required(load_procurement)
def add_procurement_supplier(procurement_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)
    next_url = next_from_request("procurements.inbox_procurements")

    result = execute_add_procurement_supplier(procurement, request.form)
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(
        url_for(
            "procurements.edit_procurement",
            procurement_id=procurement.id,
            next=next_url,
        )
    )


@procurements_bp.route("/<int:procurement_id>/suppliers/<int:link_id>/delete", methods=["POST"])
@login_required
@procurement_edit_required(load_procurement)
def delete_procurement_supplier(procurement_id: int, link_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)
    next_url = next_from_request("procurements.inbox_procurements")

    result = execute_delete_procurement_supplier(procurement, link_id)
    if result.not_found:
        abort(404)

    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(
        url_for(
            "procurements.edit_procurement",
            procurement_id=procurement.id,
            next=next_url,
        )
    )


@procurements_bp.route("/<int:procurement_id>/materials/add", methods=["POST"])
@login_required
@procurement_edit_required(load_procurement)
def add_material_line(procurement_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)
    next_url = next_from_request("procurements.inbox_procurements")

    result = execute_add_material_line(procurement, request.form)
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(
        url_for(
            "procurements.edit_procurement",
            procurement_id=procurement.id,
            next=next_url,
        )
    )


@procurements_bp.route("/<int:procurement_id>/materials/<int:line_id>/delete", methods=["POST"])
@login_required
@procurement_edit_required(load_procurement)
def delete_material_line(procurement_id: int, line_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)
    next_url = next_from_request("procurements.inbox_procurements")

    result = execute_delete_material_line(procurement, line_id)
    if result.not_found:
        abort(404)

    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(
        url_for(
            "procurements.edit_procurement",
            procurement_id=procurement.id,
            next=next_url,
        )
    )