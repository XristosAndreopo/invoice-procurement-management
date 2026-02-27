"""
Procurement routes – Enterprise Secured Version

Key UX/Workflow rules:
- New procurement can be created only from Inbox list (UI rule).
- Edit is accessible from all lists (security enforced in backend).
- After create, all fields must remain visible/editable on edit page.

Supplier participation:
- Notes field (large textarea) for offer observations.
- Prevent duplicate supplier participation per procurement (friendly message).

Material lines:
- CPV / NSN / Unit included.

Sorting:
- Lists ordered by A/A (serial_no), numeric-first when possible.
"""

from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import func, case, Integer
from sqlalchemy.exc import IntegrityError

from ...extensions import db
from ...models import (
    Procurement,
    ServiceUnit,
    Supplier,
    ProcurementSupplier,
    MaterialLine,
    OptionCategory,
    OptionValue,
    Personnel,
)
from ...security import procurement_access_required, procurement_edit_required
from ...audit import log_action, serialize_model


procurements_bp = Blueprint("procurements", __name__, url_prefix="/procurements")


def _parse_decimal(value: str | None):
    """Parse decimal from user input (accepts comma or dot). Returns None if empty/invalid."""
    if value is None:
        return None
    raw = str(value).strip().replace(",", ".")
    if raw == "":
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _get_active_option_values(key: str):
    category = OptionCategory.query.filter_by(key=key).first()
    if not category:
        return []
    values = (
        OptionValue.query
        .filter_by(category_id=category.id, is_active=True)
        .order_by(OptionValue.sort_order.asc(), OptionValue.value.asc())
        .all()
    )
    return [v.value for v in values]


def _base_procurements_query():
    if current_user.is_admin:
        return Procurement.query
    return Procurement.query.filter(Procurement.service_unit_id == current_user.service_unit_id)


def _order_by_serial_no(q):
    serial = func.coalesce(Procurement.serial_no, "")
    is_numeric = serial.op("GLOB")("[0-9]*")
    numeric_value = func.cast(serial, Integer)

    return q.order_by(
        case((is_numeric, 0), else_=1),
        case((is_numeric, numeric_value), else_=None),
        serial.asc(),
        Procurement.id.asc(),
    )


def _render_list(procurements, title: str, subtitle: str, allow_create: bool):
    return render_template(
        "procurements/list.html",
        procurements=procurements,
        page_title=title,
        page_subtitle=subtitle,
        allow_create=allow_create,
    )


@procurements_bp.route("/inbox")
@login_required
def inbox_procurements():
    q = _base_procurements_query()
    q = q.filter((Procurement.status.is_(None)) | (Procurement.status != "Ακυρωμένη"))
    q = q.filter((Procurement.send_to_expenses.is_(False)) | (Procurement.send_to_expenses.is_(None)))
    procurements = _order_by_serial_no(q).all()

    return _render_list(
        procurements,
        "Λίστα Προμηθειών (μη εγκεκριμένες)",
        "Εδώ δημιουργούνται νέες προμήθειες. Ακυρωμένες εμφανίζονται μόνο στις “Όλες”.",
        allow_create=(current_user.is_admin or current_user.can_manage()),
    )


@procurements_bp.route("/pending-expenses")
@login_required
def pending_expenses():
    q = _base_procurements_query()
    q = q.filter((Procurement.status.is_(None)) | (Procurement.status != "Ακυρωμένη"))
    q = q.filter(Procurement.hop_approval.isnot(None))
    q = q.filter(Procurement.send_to_expenses.is_(True))
    procurements = _order_by_serial_no(q).all()

    return _render_list(
        procurements,
        "Εκκρεμείς Δαπάνες",
        "Εγκεκριμένες προμήθειες που μεταφέρθηκαν στις δαπάνες.",
        allow_create=False,
    )


@procurements_bp.route("/all")
@login_required
def all_procurements():
    q = _base_procurements_query()
    procurements = _order_by_serial_no(q).all()

    return _render_list(
        procurements,
        "Όλες οι Προμήθειες",
        "Περιλαμβάνει και τις ακυρωμένες.",
        allow_create=False,
    )


@procurements_bp.route("/")
@login_required
def list_procurements():
    return redirect(url_for("procurements.inbox_procurements"))


@procurements_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_procurement():
    if not (current_user.is_admin or current_user.can_manage()):
        abort(403)

    service_units = ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()

    allocation_options = _get_active_option_values("KATANOMH")
    quarterly_options = _get_active_option_values("TRIMHNIAIA")
    status_options = _get_active_option_values("KATASTASH")
    stage_options = _get_active_option_values("STADIO")

    handler_candidates = []
    if not current_user.is_admin and current_user.service_unit_id:
        handler_candidates = (
            Personnel.query
            .filter_by(is_active=True, service_unit_id=current_user.service_unit_id)
            .order_by(Personnel.last_name.asc(), Personnel.first_name.asc())
            .all()
        )

    if request.method == "POST":
        if current_user.is_admin:
            su_raw = (request.form.get("service_unit_id") or "").strip()
            try:
                service_unit_id = int(su_raw) if su_raw else None
            except ValueError:
                service_unit_id = None
        else:
            service_unit_id = current_user.service_unit_id

        description = (request.form.get("description") or "").strip()
        if not description:
            flash("Η σύντομη περιγραφή είναι υποχρεωτική.", "danger")
            return redirect(url_for("procurements.create_procurement"))

        if service_unit_id:
            handler_candidates = (
                Personnel.query
                .filter_by(is_active=True, service_unit_id=service_unit_id)
                .order_by(Personnel.last_name.asc(), Personnel.first_name.asc())
                .all()
            )

        procurement = Procurement(
            service_unit_id=service_unit_id,
            serial_no=(request.form.get("serial_no") or "").strip() or None,
            description=description,
            ale=(request.form.get("ale") or "").strip() or None,
            allocation=(request.form.get("allocation") or "").strip() or None,
            quarterly=(request.form.get("quarterly") or "").strip() or None,
            status=(request.form.get("status") or "").strip() or None,
            stage=(request.form.get("stage") or "").strip() or None,
            vat_rate=_parse_decimal(request.form.get("vat_rate")),
            hop_commitment=(request.form.get("hop_commitment") or "").strip() or None,
            hop_forward1_commitment=(request.form.get("hop_forward1_commitment") or "").strip() or None,
            hop_forward2_commitment=(request.form.get("hop_forward2_commitment") or "").strip() or None,
            hop_preapproval=(request.form.get("hop_preapproval") or "").strip() or None,
            hop_forward1_preapproval=(request.form.get("hop_forward1_preapproval") or "").strip() or None,
            hop_forward2_preapproval=(request.form.get("hop_forward2_preapproval") or "").strip() or None,
            hop_approval=(request.form.get("hop_approval") or "").strip() or None,
            aay=(request.form.get("aay") or "").strip() or None,
            procurement_notes=(request.form.get("procurement_notes") or "").strip() or None,
        )

        handler_pid_raw = (request.form.get("handler_personnel_id") or "").strip()
        try:
            handler_pid = int(handler_pid_raw) if handler_pid_raw else None
        except ValueError:
            handler_pid = None

        if handler_pid and service_unit_id:
            allowed_ids = {p.id for p in handler_candidates}
            if handler_pid not in allowed_ids:
                flash("Μη έγκυρος Χειριστής για την επιλεγμένη υπηρεσία.", "danger")
                return redirect(url_for("procurements.create_procurement"))
            procurement.handler_personnel_id = handler_pid

        send_to_expenses = bool(request.form.get("send_to_expenses"))
        if send_to_expenses and not procurement.hop_approval:
            flash("Για μεταφορά σε Εκκρεμείς Δαπάνες απαιτείται ΗΩΠ Έγκρισης.", "warning")
            procurement.send_to_expenses = False
        else:
            procurement.send_to_expenses = bool(send_to_expenses and procurement.hop_approval)

        db.session.add(procurement)
        procurement.recalc_totals()
        db.session.commit()

        log_action(procurement, "CREATE", before=None, after=serialize_model(procurement))
        db.session.commit()

        flash("Η προμήθεια δημιουργήθηκε.", "success")
        return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))

    return render_template(
        "procurements/new.html",
        service_units=service_units,
        allocation_options=allocation_options,
        quarterly_options=quarterly_options,
        status_options=status_options,
        stage_options=stage_options,
        handler_candidates=handler_candidates,
    )


@procurements_bp.route("/<int:procurement_id>/edit", methods=["GET", "POST"])
@login_required
@procurement_access_required
def edit_procurement(procurement_id):
    procurement = Procurement.query.get_or_404(procurement_id)

    allocation_options = _get_active_option_values("KATANOMH")
    quarterly_options = _get_active_option_values("TRIMHNIAIA")
    status_options = _get_active_option_values("KATASTASH")
    stage_options = _get_active_option_values("STADIO")

    handler_candidates = []
    if procurement.service_unit_id:
        handler_candidates = (
            Personnel.query
            .filter_by(is_active=True, service_unit_id=procurement.service_unit_id)
            .order_by(Personnel.last_name.asc(), Personnel.first_name.asc())
            .all()
        )

    if request.method == "POST":
        if not (current_user.is_admin or current_user.can_manage()):
            abort(403)

        before_snapshot = serialize_model(procurement)

        if current_user.is_admin:
            su_raw = (request.form.get("service_unit_id") or "").strip()
            try:
                procurement.service_unit_id = int(su_raw) if su_raw else None
            except ValueError:
                procurement.service_unit_id = None

        procurement.serial_no = (request.form.get("serial_no") or "").strip() or None
        procurement.description = (request.form.get("description") or "").strip() or None
        procurement.ale = (request.form.get("ale") or "").strip() or None

        procurement.allocation = (request.form.get("allocation") or "").strip() or None
        procurement.quarterly = (request.form.get("quarterly") or "").strip() or None
        procurement.status = (request.form.get("status") or "").strip() or None
        procurement.stage = (request.form.get("stage") or "").strip() or None

        procurement.vat_rate = _parse_decimal(request.form.get("vat_rate"))

        procurement.hop_commitment = (request.form.get("hop_commitment") or "").strip() or None
        procurement.hop_forward1_commitment = (request.form.get("hop_forward1_commitment") or "").strip() or None
        procurement.hop_forward2_commitment = (request.form.get("hop_forward2_commitment") or "").strip() or None

        procurement.hop_preapproval = (request.form.get("hop_preapproval") or "").strip() or None
        procurement.hop_forward1_preapproval = (request.form.get("hop_forward1_preapproval") or "").strip() or None
        procurement.hop_forward2_preapproval = (request.form.get("hop_forward2_preapproval") or "").strip() or None

        procurement.hop_approval = (request.form.get("hop_approval") or "").strip() or None
        procurement.aay = (request.form.get("aay") or "").strip() or None

        procurement.procurement_notes = (request.form.get("procurement_notes") or "").strip() or None

        handler_pid_raw = (request.form.get("handler_personnel_id") or "").strip()
        try:
            handler_pid = int(handler_pid_raw) if handler_pid_raw else None
        except ValueError:
            handler_pid = None

        if handler_pid and procurement.service_unit_id:
            allowed_ids = {p.id for p in handler_candidates}
            if handler_pid not in allowed_ids:
                flash("Μη έγκυρος Χειριστής για την υπηρεσία.", "danger")
                return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))
            procurement.handler_personnel_id = handler_pid
        else:
            procurement.handler_personnel_id = None

        send_to_expenses = bool(request.form.get("send_to_expenses"))
        if send_to_expenses and not procurement.hop_approval:
            flash("Για μεταφορά σε Εκκρεμείς Δαπάνες απαιτείται ΗΩΠ Έγκρισης.", "warning")
            procurement.send_to_expenses = False
        else:
            procurement.send_to_expenses = bool(send_to_expenses and procurement.hop_approval)

        procurement.recalc_totals()
        db.session.commit()

        log_action(procurement, "UPDATE", before=before_snapshot, after=serialize_model(procurement))
        db.session.commit()

        flash("Η προμήθεια ενημερώθηκε.", "success")
        return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))

    return render_template(
        "procurements/edit.html",
        procurement=procurement,
        service_units=ServiceUnit.query.order_by(ServiceUnit.description.asc()).all(),
        suppliers=Supplier.query.order_by(Supplier.name.asc()).all(),
        allocation_options=allocation_options,
        quarterly_options=quarterly_options,
        status_options=status_options,
        stage_options=stage_options,
        handler_candidates=handler_candidates,
    )


@procurements_bp.route("/<int:procurement_id>/suppliers/add", methods=["POST"])
@login_required
@procurement_edit_required
def add_procurement_supplier(procurement_id):
    """
    A supplier can only be added once per procurement.
    Friendly message instead of IntegrityError crash.
    """
    procurement = Procurement.query.get_or_404(procurement_id)

    supplier_id_raw = (request.form.get("supplier_id") or "").strip()
    try:
        supplier_id = int(supplier_id_raw)
    except ValueError:
        flash("Μη έγκυρος προμηθευτής.", "danger")
        return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))

    exists = ProcurementSupplier.query.filter_by(procurement_id=procurement.id, supplier_id=supplier_id).first()
    if exists:
        flash("Ο συγκεκριμένος προμηθευτής έχει ήδη προστεθεί σε αυτή την προμήθεια.", "warning")
        return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))

    offered_amount_raw = request.form.get("offered_amount")
    offered_amount = _parse_decimal(offered_amount_raw)
    is_winner = bool(request.form.get("is_winner"))
    notes = (request.form.get("notes") or "").strip() or None

    if is_winner:
        for link in procurement.supplies_links:
            link.is_winner = False

    link = ProcurementSupplier(
        procurement_id=procurement.id,
        supplier_id=supplier_id,
        offered_amount=offered_amount,
        is_winner=is_winner,
        notes=notes,
    )

    db.session.add(link)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Ο συγκεκριμένος προμηθευτής έχει ήδη προστεθεί σε αυτή την προμήθεια.", "warning")
        return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))

    log_action(link, "CREATE", before=None, after=serialize_model(link))
    db.session.commit()

    flash("Ο προμηθευτής προστέθηκε.", "success")
    return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))


@procurements_bp.route("/<int:procurement_id>/suppliers/<int:link_id>/delete", methods=["POST"])
@login_required
@procurement_edit_required
def delete_procurement_supplier(procurement_id, link_id):
    link = ProcurementSupplier.query.get_or_404(link_id)
    before_snapshot = serialize_model(link)

    db.session.delete(link)
    db.session.commit()

    log_action(link, "DELETE", before=before_snapshot, after=None)
    db.session.commit()

    flash("Ο προμηθευτής διαγράφηκε.", "success")
    return redirect(url_for("procurements.edit_procurement", procurement_id=procurement_id))


@procurements_bp.route("/<int:procurement_id>/materials/add", methods=["POST"])
@login_required
@procurement_edit_required
def add_material_line(procurement_id):
    procurement = Procurement.query.get_or_404(procurement_id)

    description = (request.form.get("description") or "").strip()
    if not description:
        flash("Η περιγραφή γραμμής είναι υποχρεωτική.", "danger")
        return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))

    quantity = _parse_decimal(request.form.get("quantity")) or Decimal("0")
    unit_price = _parse_decimal(request.form.get("unit_price")) or Decimal("0")

    line = MaterialLine(
        procurement_id=procurement.id,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        cpv=(request.form.get("cpv") or "").strip() or None,
        nsn=(request.form.get("nsn") or "").strip() or None,
        unit=(request.form.get("unit") or "").strip() or None,
    )

    db.session.add(line)
    procurement.recalc_totals()
    db.session.commit()

    log_action(line, "CREATE", before=None, after=serialize_model(line))
    db.session.commit()

    flash("Η γραμμή προστέθηκε.", "success")
    return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))


@procurements_bp.route("/<int:procurement_id>/materials/<int:line_id>/delete", methods=["POST"])
@login_required
@procurement_edit_required
def delete_material_line(procurement_id, line_id):
    line = MaterialLine.query.get_or_404(line_id)
    before_snapshot = serialize_model(line)

    db.session.delete(line)
    procurement = Procurement.query.get_or_404(procurement_id)
    procurement.recalc_totals()
    db.session.commit()

    log_action(line, "DELETE", before=before_snapshot, after=None)
    db.session.commit()

    flash("Η γραμμή διαγράφηκε.", "success")
    return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))