"""
app/blueprints/procurements/routes.py

Procurement routes – Enterprise Secured Version (V4)

Guarantees:
- Exposes `procurements_bp` at module import time (prevents ImportError).
- Uses decorator factories correctly (no Flask endpoint collisions).
- Server-side permission checks (UI never trusted).
- Supports:
  - Inbox / Pending Expenses / All lists
  - Create + Edit procurement
  - Supplier participation add/delete
  - Material lines add/delete
  - AA2 selection via IncomeTaxRule
  - Withholding selection via WithholdingProfile
  - Committee selection via ProcurementCommittee (service-unit scoped)
  - Payment analysis display via Procurement.compute_payment_analysis()
"""

from __future__ import annotations

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
    IncomeTaxRule,
    WithholdingProfile,
    ProcurementCommittee,
)
from ...security import procurement_access_required, procurement_edit_required
from ...audit import log_action, serialize_model

# IMPORTANT: this name MUST exist at import time
procurements_bp = Blueprint("procurements", __name__, url_prefix="/procurements")


# ---------------------------------------------------------------------
# Decorator loader (CRITICAL)
# ---------------------------------------------------------------------
def _load_procurement(procurement_id: int, **_: object) -> Procurement:
    """Loader for decorator factories."""
    return Procurement.query.get_or_404(procurement_id)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _parse_decimal(value: str | None) -> Decimal | None:
    """Parse decimal from user input (accepts comma or dot)."""
    if value is None:
        return None
    raw = str(value).strip().replace(",", ".")
    if raw == "":
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _parse_optional_int(value: str | None) -> int | None:
    """Parse optional int from form."""
    if value is None:
        return None
    raw = str(value).strip()
    if raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _get_active_option_values(category_key: str) -> list[str]:
    """Return active OptionValue.value list for an OptionCategory key."""
    category = OptionCategory.query.filter_by(key=category_key).first()
    if not category:
        return []
    values = (
        OptionValue.query.filter_by(category_id=category.id, is_active=True)
        .order_by(OptionValue.sort_order.asc(), OptionValue.value.asc())
        .all()
    )
    return [v.value for v in values]


def _base_procurements_query():
    """Service isolation: non-admin sees only their service unit."""
    if current_user.is_admin:
        return Procurement.query
    return Procurement.query.filter(Procurement.service_unit_id == current_user.service_unit_id)


def _order_by_serial_no(q):
    """Numeric-first ordering for serial_no (SQLite GLOB)."""
    serial = func.coalesce(Procurement.serial_no, "")
    is_numeric = serial.op("GLOB")("[0-9]*")
    numeric_value = func.cast(serial, Integer)

    return q.order_by(
        case((is_numeric, 0), else_=1),
        case((is_numeric, numeric_value), else_=None),
        serial.asc(),
        Procurement.id.asc(),
    )


def _handler_candidates(service_unit_id: int | None):
    if not service_unit_id:
        return []
    return (
        Personnel.query.filter_by(is_active=True, service_unit_id=service_unit_id)
        .order_by(Personnel.last_name.asc(), Personnel.first_name.asc())
        .all()
    )


def _committees_for_service_unit(service_unit_id: int | None):
    if not service_unit_id:
        return []
    return (
        ProcurementCommittee.query.filter_by(service_unit_id=service_unit_id, is_active=True)
        .order_by(ProcurementCommittee.description.asc())
        .all()
    )


def _active_income_tax_rules():
    return IncomeTaxRule.query.filter_by(is_active=True).order_by(IncomeTaxRule.description.asc()).all()


def _active_withholding_profiles():
    return WithholdingProfile.query.filter_by(is_active=True).order_by(WithholdingProfile.description.asc()).all()


# ---------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------
@procurements_bp.route("/inbox")
@login_required
def inbox_procurements():
    q = _base_procurements_query()
    q = q.filter((Procurement.status.is_(None)) | (Procurement.status != "Ακυρωμένη"))
    q = q.filter((Procurement.send_to_expenses.is_(False)) | (Procurement.send_to_expenses.is_(None)))
    procurements = _order_by_serial_no(q).all()
    return render_template(
        "procurements/list.html",
        procurements=procurements,
        page_title="Λίστα Προμηθειών (μη εγκεκριμένες)",
        page_subtitle="Εδώ δημιουργούνται νέες προμήθειες. Ακυρωμένες εμφανίζονται μόνο στις “Όλες”.",
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
    return render_template(
        "procurements/list.html",
        procurements=procurements,
        page_title="Εκκρεμείς Δαπάνες",
        page_subtitle="Εγκεκριμένες προμήθειες που μεταφέρθηκαν στις δαπάνες.",
        allow_create=False,
    )


@procurements_bp.route("/all")
@login_required
def all_procurements():
    q = _base_procurements_query()
    procurements = _order_by_serial_no(q).all()
    return render_template(
        "procurements/list.html",
        procurements=procurements,
        page_title="Όλες οι Προμήθειες",
        page_subtitle="Περιλαμβάνει και τις ακυρωμένες.",
        allow_create=False,
    )


@procurements_bp.route("/")
@login_required
def list_procurements():
    return redirect(url_for("procurements.inbox_procurements"))


# ---------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------
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

    income_tax_rules = _active_income_tax_rules()
    withholding_profiles = _active_withholding_profiles()

    handler_candidates = []
    committees = []
    if not current_user.is_admin and current_user.service_unit_id:
        handler_candidates = _handler_candidates(current_user.service_unit_id)
        committees = _committees_for_service_unit(current_user.service_unit_id)

    if request.method == "POST":
        if current_user.is_admin:
            service_unit_id = _parse_optional_int(request.form.get("service_unit_id"))
        else:
            service_unit_id = current_user.service_unit_id

        description = (request.form.get("description") or "").strip()
        if not description:
            flash("Η σύντομη περιγραφή είναι υποχρεωτική.", "danger")
            return redirect(url_for("procurements.create_procurement"))

        handler_candidates = _handler_candidates(service_unit_id)
        committees = _committees_for_service_unit(service_unit_id)

        handler_pid = _parse_optional_int(request.form.get("handler_personnel_id"))
        if handler_pid:
            allowed = {p.id for p in handler_candidates}
            if handler_pid not in allowed:
                flash("Μη έγκυρος Χειριστής για την επιλεγμένη υπηρεσία.", "danger")
                return redirect(url_for("procurements.create_procurement"))

        income_tax_rule_id = _parse_optional_int(request.form.get("income_tax_rule_id"))
        if income_tax_rule_id:
            rule = IncomeTaxRule.query.get(income_tax_rule_id)
            if not rule or not rule.is_active:
                flash("Μη έγκυρος κανόνας Φόρου Εισοδήματος.", "danger")
                return redirect(url_for("procurements.create_procurement"))
        else:
            rule = None

        withholding_profile_id = _parse_optional_int(request.form.get("withholding_profile_id"))
        if withholding_profile_id:
            wp = WithholdingProfile.query.get(withholding_profile_id)
            if not wp or not wp.is_active:
                flash("Μη έγκυρο προφίλ κρατήσεων.", "danger")
                return redirect(url_for("procurements.create_procurement"))
        else:
            wp = None

        committee_id = _parse_optional_int(request.form.get("committee_id"))
        if committee_id:
            c = ProcurementCommittee.query.get(committee_id)
            if not c or not c.is_active or c.service_unit_id != service_unit_id:
                flash("Μη έγκυρη επιτροπή για την υπηρεσία.", "danger")
                return redirect(url_for("procurements.create_procurement"))
        else:
            c = None

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
            hop_approval_commitment=(request.form.get("hop_approval_commitment") or "").strip() or None,
            hop_preapproval=(request.form.get("hop_preapproval") or "").strip() or None,
            hop_forward1_preapproval=(request.form.get("hop_forward1_preapproval") or "").strip() or None,
            hop_forward2_preapproval=(request.form.get("hop_forward2_preapproval") or "").strip() or None,
            hop_approval=(request.form.get("hop_approval") or "").strip() or None,
            aay=(request.form.get("aay") or "").strip() or None,
            procurement_notes=(request.form.get("procurement_notes") or "").strip() or None,
            handler_personnel_id=handler_pid,
            income_tax_rule_id=rule.id if rule else None,
            withholding_profile_id=wp.id if wp else None,
            committee_id=c.id if c else None,
        )

        send_to_expenses = bool(request.form.get("send_to_expenses"))
        if send_to_expenses and not procurement.hop_approval:
            flash("Για μεταφορά σε Εκκρεμείς Δαπάνες απαιτείται ΗΩΠ Έγκρισης.", "warning")
            procurement.send_to_expenses = False
        else:
            procurement.send_to_expenses = bool(send_to_expenses and procurement.hop_approval)

        db.session.add(procurement)
        procurement.recalc_totals()
        db.session.flush()
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
        income_tax_rules=income_tax_rules,
        withholding_profiles=withholding_profiles,
        committees=committees,
    )


# ---------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------
@procurements_bp.route("/<int:procurement_id>/edit", methods=["GET", "POST"])
@login_required
@procurement_access_required(_load_procurement)
def edit_procurement(procurement_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)

    allocation_options = _get_active_option_values("KATANOMH")
    quarterly_options = _get_active_option_values("TRIMHNIAIA")
    status_options = _get_active_option_values("KATASTASH")
    stage_options = _get_active_option_values("STADIO")

    income_tax_rules = _active_income_tax_rules()
    withholding_profiles = _active_withholding_profiles()

    handler_candidates = _handler_candidates(procurement.service_unit_id)
    committees = _committees_for_service_unit(procurement.service_unit_id)

    if request.method == "POST":
        if not (current_user.is_admin or current_user.can_manage()):
            abort(403)

        before_snapshot = serialize_model(procurement)

        if current_user.is_admin:
            procurement.service_unit_id = _parse_optional_int(request.form.get("service_unit_id"))

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
        procurement.hop_approval_commitment = (request.form.get("hop_approval_commitment") or "").strip() or None
        procurement.hop_preapproval = (request.form.get("hop_preapproval") or "").strip() or None
        procurement.hop_forward1_preapproval = (request.form.get("hop_forward1_preapproval") or "").strip() or None
        procurement.hop_forward2_preapproval = (request.form.get("hop_forward2_preapproval") or "").strip() or None
        procurement.hop_approval = (request.form.get("hop_approval") or "").strip() or None
        procurement.aay = (request.form.get("aay") or "").strip() or None
        procurement.procurement_notes = (request.form.get("procurement_notes") or "").strip() or None

        handler_candidates = _handler_candidates(procurement.service_unit_id)
        committees = _committees_for_service_unit(procurement.service_unit_id)

        handler_pid = _parse_optional_int(request.form.get("handler_personnel_id"))
        if handler_pid:
            allowed = {p.id for p in handler_candidates}
            if handler_pid not in allowed:
                flash("Μη έγκυρος Χειριστής για την υπηρεσία.", "danger")
                return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))
            procurement.handler_personnel_id = handler_pid
        else:
            procurement.handler_personnel_id = None

        income_tax_rule_id = _parse_optional_int(request.form.get("income_tax_rule_id"))
        if income_tax_rule_id:
            rule = IncomeTaxRule.query.get(income_tax_rule_id)
            if not rule or not rule.is_active:
                flash("Μη έγκυρος κανόνας Φόρου Εισοδήματος.", "danger")
                return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))
            procurement.income_tax_rule_id = rule.id
        else:
            procurement.income_tax_rule_id = None

        wp_id = _parse_optional_int(request.form.get("withholding_profile_id"))
        if wp_id:
            wp = WithholdingProfile.query.get(wp_id)
            if not wp or not wp.is_active:
                flash("Μη έγκυρο προφίλ κρατήσεων.", "danger")
                return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))
            procurement.withholding_profile_id = wp.id
        else:
            procurement.withholding_profile_id = None

        committee_id = _parse_optional_int(request.form.get("committee_id"))
        if committee_id:
            c = ProcurementCommittee.query.get(committee_id)
            if not c or not c.is_active or c.service_unit_id != procurement.service_unit_id:
                flash("Μη έγκυρη επιτροπή για την υπηρεσία.", "danger")
                return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))
            procurement.committee_id = c.id
        else:
            procurement.committee_id = None

        send_to_expenses = bool(request.form.get("send_to_expenses"))
        if send_to_expenses and not procurement.hop_approval:
            flash("Για μεταφορά σε Εκκρεμείς Δαπάνες απαιτείται ΗΩΠ Έγκρισης.", "warning")
            procurement.send_to_expenses = False
        else:
            procurement.send_to_expenses = bool(send_to_expenses and procurement.hop_approval)

        procurement.recalc_totals()
        db.session.flush()
        log_action(procurement, "UPDATE", before=before_snapshot, after=serialize_model(procurement))
        db.session.commit()

        flash("Η προμήθεια ενημερώθηκε.", "success")
        return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))

    analysis = procurement.compute_payment_analysis()

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
        income_tax_rules=income_tax_rules,
        withholding_profiles=withholding_profiles,
        committees=committees,
        analysis=analysis,
    )


# ---------------------------------------------------------------------
# Suppliers participation
# ---------------------------------------------------------------------
@procurements_bp.route("/<int:procurement_id>/suppliers/add", methods=["POST"])
@login_required
@procurement_edit_required(_load_procurement)
def add_procurement_supplier(procurement_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)

    supplier_id = _parse_optional_int(request.form.get("supplier_id"))
    if not supplier_id:
        flash("Μη έγκυρος προμηθευτής.", "danger")
        return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))

    exists = ProcurementSupplier.query.filter_by(procurement_id=procurement.id, supplier_id=supplier_id).first()
    if exists:
        flash("Ο συγκεκριμένος προμηθευτής έχει ήδη προστεθεί σε αυτή την προμήθεια.", "warning")
        return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))

    offered_amount = _parse_decimal(request.form.get("offered_amount"))
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
        db.session.flush()
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
@procurement_edit_required(_load_procurement)
def delete_procurement_supplier(procurement_id: int, link_id: int):
    link = ProcurementSupplier.query.get_or_404(link_id)
    before_snapshot = serialize_model(link)

    db.session.delete(link)
    db.session.flush()
    log_action(link, "DELETE", before=before_snapshot, after=None)
    db.session.commit()

    flash("Ο προμηθευτής διαγράφηκε.", "success")
    return redirect(url_for("procurements.edit_procurement", procurement_id=procurement_id))


# ---------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------
@procurements_bp.route("/<int:procurement_id>/materials/add", methods=["POST"])
@login_required
@procurement_edit_required(_load_procurement)
def add_material_line(procurement_id: int):
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
    db.session.flush()
    log_action(line, "CREATE", before=None, after=serialize_model(line))
    db.session.commit()

    flash("Η γραμμή προστέθηκε.", "success")
    return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))


@procurements_bp.route("/<int:procurement_id>/materials/<int:line_id>/delete", methods=["POST"])
@login_required
@procurement_edit_required(_load_procurement)
def delete_material_line(procurement_id: int, line_id: int):
    line = MaterialLine.query.get_or_404(line_id)
    before_snapshot = serialize_model(line)

    db.session.delete(line)
    procurement = Procurement.query.get_or_404(procurement_id)
    procurement.recalc_totals()
    db.session.flush()
    log_action(line, "DELETE", before=before_snapshot, after=None)
    db.session.commit()

    flash("Η γραμμή διαγράφηκε.", "success")
    return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))