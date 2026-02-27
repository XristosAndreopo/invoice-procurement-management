"""
app/blueprints/settings/routes.py

Settings & Master Data routes.

Enterprise scope:
- Theme selection (all logged-in users)
- Feedback form (all logged-in users)
- Feedback admin (admin-only)
- ServiceUnits CRUD (admin-only)
- Suppliers CRUD (admin-only)
- OptionValue pages (enterprise dropdown master data)
  - Admin-only: status, stage, allocation, quarterly, vat, withholdings
  - Manager+Admin: committees

SECURITY:
- UI is never trusted. All permissions are enforced here server-side.
- A global Viewer read-only guard also blocks unexpected POSTs (see app/security.py),
  but each route still enforces role requirements explicitly.

AUDIT:
- CREATE/UPDATE/DELETE for master data is audited via app/audit.py.
"""

from __future__ import annotations

from typing import Dict, Optional

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import Feedback, OptionCategory, OptionValue, Personnel, ServiceUnit, Supplier
from ...security import admin_required, manager_required

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


# ----------------------------------------------------------------------
# Canonical OptionCategory keys
# ----------------------------------------------------------------------
# IMPORTANT:
# These keys MUST match the keys used by the procurement module.
# procurements/routes.py currently expects:
#   - KATANOMH, TRIMHNIAIA, KATASTASH, STADIO
#
# We also standardize the rest here for enterprise consistency:
#   - FPA, KRATHSEIS, EPITROPES
OPTION_KEY_STATUS = "KATASTASH"
OPTION_KEY_STAGE = "STADIO"
OPTION_KEY_ALLOCATION = "KATANOMH"
OPTION_KEY_QUARTERLY = "TRIMHNIAIA"
OPTION_KEY_VAT = "FPA"
OPTION_KEY_WITHHOLDINGS = "KRATHSEIS"
OPTION_KEY_COMMITTEES = "EPITROPES"


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _parse_optional_int(value: str) -> Optional[int]:
    """Parse optional int from string; returns None for empty/invalid."""
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _active_personnel_for_dropdown():
    """Active personnel list for dropdown selection."""
    return (
        Personnel.query.filter_by(is_active=True)
        .order_by(Personnel.last_name.asc(), Personnel.first_name.asc())
        .all()
    )


def _get_or_create_category(key: str, label: str) -> OptionCategory:
    """
    Ensure an OptionCategory exists.

    This prevents runtime issues if categories have not been seeded yet.

    NOTE:
    - We commit immediately for this small, idempotent operation.
    - In enterprise production, you might prefer to seed via CLI only, but this is safe.
    """
    category = OptionCategory.query.filter_by(key=key).first()
    if category:
        # Keep the label in sync if you ever rename it (optional).
        if category.label != label:
            category.label = label
            db.session.commit()
        return category

    category = OptionCategory(key=key, label=label)
    db.session.add(category)
    db.session.commit()
    return category


def _option_values_for_category(category: OptionCategory):
    """Return OptionValue list ordered consistently."""
    return (
        OptionValue.query.filter_by(category_id=category.id)
        .order_by(OptionValue.sort_order.asc(), OptionValue.value.asc())
        .all()
    )


# ----------------------------------------------------------------------
# THEME (all users)
# ----------------------------------------------------------------------
@settings_bp.route("/theme", methods=["GET", "POST"])
@login_required
def theme():
    """Allow any logged-in user to select their theme."""
    themes = {
        "default": ("Προεπιλογή", "Φωτεινό θέμα με ουδέτερα χρώματα."),
        "dark": ("Σκούρο", "Σκούρο θέμα κατάλληλο για χαμηλό φωτισμό."),
        "ocean": ("Ocean", "Απαλό μπλε θέμα."),
    }

    if request.method == "POST":
        selected = request.form.get("theme")
        if selected not in themes:
            flash("Μη έγκυρο θέμα.", "danger")
            return redirect(url_for("settings.theme"))

        current_user.theme = selected
        db.session.commit()
        flash("Το θέμα ενημερώθηκε.", "success")
        return redirect(url_for("settings.theme"))

    return render_template("settings/theme.html", themes=themes)


# ----------------------------------------------------------------------
# FEEDBACK / COMPLAINT (all users)
# ----------------------------------------------------------------------
@settings_bp.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    """Feedback / complaint form."""
    categories = [
        ("complaint", "Παράπονο"),
        ("suggestion", "Πρόταση"),
        ("bug", "Σφάλμα"),
        ("other", "Άλλο"),
    ]

    if request.method == "POST":
        category = request.form.get("category") or None
        subject = (request.form.get("subject") or "").strip()
        message = (request.form.get("message") or "").strip()
        related_procurement_id_raw = (request.form.get("related_procurement_id") or "").strip()

        if not subject:
            flash("Ο τίτλος είναι υποχρεωτικός.", "danger")
            return redirect(url_for("settings.feedback"))
        if not message:
            flash("Το κείμενο είναι υποχρεωτικό.", "danger")
            return redirect(url_for("settings.feedback"))

        related_procurement_id = _parse_optional_int(related_procurement_id_raw)
        if related_procurement_id_raw and related_procurement_id is None:
            flash("Μη έγκυρο Α/Α προμήθειας.", "danger")
            return redirect(url_for("settings.feedback"))

        fb = Feedback(
            user_id=current_user.id,
            category=category,
            subject=subject,
            message=message,
            related_procurement_id=related_procurement_id,
            status="new",
        )
        db.session.add(fb)
        db.session.commit()

        flash("Το μήνυμά σας καταχωρήθηκε.", "success")
        return redirect(url_for("settings.feedback"))

    recent_feedback = (
        Feedback.query.filter_by(user_id=current_user.id)
        .order_by(Feedback.created_at.desc())
        .limit(5)
        .all()
    )
    return render_template(
        "settings/feedback.html",
        categories=categories,
        recent_feedback=recent_feedback,
    )


# ----------------------------------------------------------------------
# FEEDBACK ADMIN (admin only)
# ----------------------------------------------------------------------
@settings_bp.route("/feedback/admin", methods=["GET", "POST"])
@login_required
@admin_required
def feedback_admin():
    """Admin-only page to review and manage all feedback."""
    status_choices: Dict[str, str] = {
        "new": "Νέο",
        "in_progress": "Σε εξέλιξη",
        "resolved": "Επιλυμένο",
        "closed": "Κλειστό",
    }
    category_labels = {
        "complaint": "Παράπονο",
        "suggestion": "Πρόταση",
        "bug": "Σφάλμα",
        "other": "Άλλο",
        None: "—",
    }

    if request.method == "POST":
        fb_id_raw = request.form.get("feedback_id") or ""
        new_status = request.form.get("status") or ""

        fb_id = _parse_optional_int(fb_id_raw.strip())
        if fb_id is None or new_status not in status_choices:
            flash("Μη έγκυρη ενημέρωση κατάστασης.", "danger")
            return redirect(url_for("settings.feedback_admin"))

        fb = Feedback.query.get(fb_id)
        if not fb:
            flash("Το συγκεκριμένο παράπονο δεν βρέθηκε.", "danger")
            return redirect(url_for("settings.feedback_admin"))

        fb.status = new_status
        db.session.commit()
        flash("Η κατάσταση ενημερώθηκε.", "success")
        return redirect(url_for("settings.feedback_admin"))

    status_filter = (request.args.get("status") or "").strip()
    category_filter = (request.args.get("category") or "").strip()

    query = Feedback.query.order_by(Feedback.created_at.desc())
    if status_filter:
        query = query.filter(Feedback.status == status_filter)
    if category_filter:
        query = query.filter(Feedback.category == category_filter)

    feedback_items = query.all()
    return render_template(
        "settings/feedback_admin.html",
        feedback_items=feedback_items,
        status_choices=status_choices,
        category_labels=category_labels,
        status_filter=status_filter,
        category_filter=category_filter,
    )


# ----------------------------------------------------------------------
# SERVICE UNITS CRUD (admin only)
# ----------------------------------------------------------------------
@settings_bp.route("/service-units")
@login_required
@admin_required
def service_units_list():
    """List ServiceUnits (admin-only)."""
    units = ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()
    return render_template("settings/service_units_list.html", units=units)


@settings_bp.route("/service-units/new", methods=["GET", "POST"])
@login_required
@admin_required
def service_unit_create():
    """Create ServiceUnit (admin-only)."""
    personnel_list = _active_personnel_for_dropdown()

    if request.method == "POST":
        description = (request.form.get("description") or "").strip()
        code = (request.form.get("code") or "").strip()
        short_name = (request.form.get("short_name") or "").strip()
        aahit = (request.form.get("aahit") or "").strip()
        commander = (request.form.get("commander") or "").strip()
        curator = (request.form.get("curator") or "").strip()
        supply_officer = (request.form.get("supply_officer") or "").strip()

        manager_pid = _parse_optional_int((request.form.get("manager_personnel_id") or "").strip())
        deputy_pid = _parse_optional_int((request.form.get("deputy_personnel_id") or "").strip())

        if not description:
            flash("Η περιγραφή είναι υποχρεωτική.", "danger")
            return redirect(url_for("settings.service_unit_create"))

        if manager_pid and deputy_pid and manager_pid == deputy_pid:
            flash("Ο ίδιος/η ίδια δεν μπορεί να είναι και Manager και Deputy.", "danger")
            return redirect(url_for("settings.service_unit_create"))

        active_ids = {p.id for p in personnel_list}
        if manager_pid and manager_pid not in active_ids:
            flash("Μη έγκυρος Manager. Επιτρέπεται μόνο ενεργό προσωπικό.", "danger")
            return redirect(url_for("settings.service_unit_create"))
        if deputy_pid and deputy_pid not in active_ids:
            flash("Μη έγκυρος Deputy. Επιτρέπεται μόνο ενεργό προσωπικό.", "danger")
            return redirect(url_for("settings.service_unit_create"))

        unit = ServiceUnit(
            description=description,
            code=code or None,
            short_name=short_name or None,
            aahit=aahit or None,
            commander=commander or None,
            curator=curator or None,
            supply_officer=supply_officer or None,
            manager_personnel_id=manager_pid,
            deputy_personnel_id=deputy_pid,
        )
        db.session.add(unit)
        db.session.flush()

        log_action(entity=unit, action="CREATE", after=serialize_model(unit))
        db.session.commit()

        flash("Η υπηρεσία δημιουργήθηκε.", "success")
        return redirect(url_for("settings.service_units_list"))

    return render_template("settings/service_unit_form.html", unit=None, personnel_list=personnel_list)


@settings_bp.route("/service-units/<int:unit_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def service_unit_edit(unit_id: int):
    """Edit ServiceUnit (admin-only)."""
    unit = ServiceUnit.query.get_or_404(unit_id)
    personnel_list = _active_personnel_for_dropdown()

    if request.method == "POST":
        before = serialize_model(unit)

        description = (request.form.get("description") or "").strip()
        code = (request.form.get("code") or "").strip()
        short_name = (request.form.get("short_name") or "").strip()
        aahit = (request.form.get("aahit") or "").strip()
        commander = (request.form.get("commander") or "").strip()
        curator = (request.form.get("curator") or "").strip()
        supply_officer = (request.form.get("supply_officer") or "").strip()

        manager_pid = _parse_optional_int((request.form.get("manager_personnel_id") or "").strip())
        deputy_pid = _parse_optional_int((request.form.get("deputy_personnel_id") or "").strip())

        if not description:
            flash("Η περιγραφή είναι υποχρεωτική.", "danger")
            return redirect(url_for("settings.service_unit_edit", unit_id=unit_id))

        if manager_pid and deputy_pid and manager_pid == deputy_pid:
            flash("Ο ίδιος/η ίδια δεν μπορεί να είναι και Manager και Deputy.", "danger")
            return redirect(url_for("settings.service_unit_edit", unit_id=unit_id))

        active_ids = {p.id for p in personnel_list}
        if manager_pid and manager_pid not in active_ids:
            flash("Μη έγκυρος Manager. Επιτρέπεται μόνο ενεργό προσωπικό.", "danger")
            return redirect(url_for("settings.service_unit_edit", unit_id=unit_id))
        if deputy_pid and deputy_pid not in active_ids:
            flash("Μη έγκυρος Deputy. Επιτρέπεται μόνο ενεργό προσωπικό.", "danger")
            return redirect(url_for("settings.service_unit_edit", unit_id=unit_id))

        unit.description = description
        unit.code = code or None
        unit.short_name = short_name or None
        unit.aahit = aahit or None
        unit.commander = commander or None
        unit.curator = curator or None
        unit.supply_officer = supply_officer or None
        unit.manager_personnel_id = manager_pid
        unit.deputy_personnel_id = deputy_pid

        db.session.flush()
        log_action(entity=unit, action="UPDATE", before=before, after=serialize_model(unit))
        db.session.commit()

        flash("Η υπηρεσία ενημερώθηκε.", "success")
        return redirect(url_for("settings.service_units_list"))

    return render_template("settings/service_unit_form.html", unit=unit, personnel_list=personnel_list)


@settings_bp.route("/service-units/<int:unit_id>/delete", methods=["POST"])
@login_required
@admin_required
def service_unit_delete(unit_id: int):
    """Delete ServiceUnit (admin-only)."""
    unit = ServiceUnit.query.get_or_404(unit_id)
    before = serialize_model(unit)

    db.session.delete(unit)
    db.session.flush()

    log_action(entity=unit, action="DELETE", before=before, after=None)
    db.session.commit()

    flash("Η υπηρεσία διαγράφηκε.", "success")
    return redirect(url_for("settings.service_units_list"))


# ----------------------------------------------------------------------
# SUPPLIERS CRUD (admin only)
# ----------------------------------------------------------------------
@settings_bp.route("/suppliers")
@login_required
@admin_required
def suppliers_list():
    """List suppliers (admin-only)."""
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    return render_template("settings/suppliers_list.html", suppliers=suppliers)


@settings_bp.route("/suppliers/new", methods=["GET", "POST"])
@login_required
@admin_required
def supplier_create():
    """Create supplier (admin-only)."""
    if request.method == "POST":
        afm = (request.form.get("afm") or "").strip()
        name = (request.form.get("name") or "").strip()
        address = (request.form.get("address") or "").strip()
        city = (request.form.get("city") or "").strip()
        postal_code = (request.form.get("postal_code") or "").strip()
        country = (request.form.get("country") or "").strip()
        bank_name = (request.form.get("bank_name") or "").strip()
        iban = (request.form.get("iban") or "").strip()

        if not afm or len(afm) != 9 or not afm.isdigit():
            flash("Το ΑΦΜ πρέπει να είναι 9 ψηφία.", "danger")
            return redirect(url_for("settings.supplier_create"))
        if not name:
            flash("Η επωνυμία είναι υποχρεωτική.", "danger")
            return redirect(url_for("settings.supplier_create"))

        supplier = Supplier(
            afm=afm,
            name=name,
            address=address or None,
            city=city or None,
            postal_code=postal_code or None,
            country=country or None,
            bank_name=bank_name or None,
            iban=iban or None,
        )
        db.session.add(supplier)
        db.session.flush()

        log_action(entity=supplier, action="CREATE", after=serialize_model(supplier))
        db.session.commit()

        flash("Ο προμηθευτής δημιουργήθηκε.", "success")
        return redirect(url_for("settings.suppliers_list"))

    return render_template("settings/supplier_form.html", supplier=None)


@settings_bp.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def supplier_edit(supplier_id: int):
    """Edit supplier (admin-only)."""
    supplier = Supplier.query.get_or_404(supplier_id)

    if request.method == "POST":
        before = serialize_model(supplier)

        afm = (request.form.get("afm") or "").strip()
        name = (request.form.get("name") or "").strip()
        address = (request.form.get("address") or "").strip()
        city = (request.form.get("city") or "").strip()
        postal_code = (request.form.get("postal_code") or "").strip()
        country = (request.form.get("country") or "").strip()
        bank_name = (request.form.get("bank_name") or "").strip()
        iban = (request.form.get("iban") or "").strip()

        if not afm or len(afm) != 9 or not afm.isdigit():
            flash("Το ΑΦΜ πρέπει να είναι 9 ψηφία.", "danger")
            return redirect(url_for("settings.supplier_edit", supplier_id=supplier_id))
        if not name:
            flash("Η επωνυμία είναι υποχρεωτική.", "danger")
            return redirect(url_for("settings.supplier_edit", supplier_id=supplier_id))

        supplier.afm = afm
        supplier.name = name
        supplier.address = address or None
        supplier.city = city or None
        supplier.postal_code = postal_code or None
        supplier.country = country or None
        supplier.bank_name = bank_name or None
        supplier.iban = iban or None

        db.session.flush()
        log_action(entity=supplier, action="UPDATE", before=before, after=serialize_model(supplier))
        db.session.commit()

        flash("Ο προμηθευτής ενημερώθηκε.", "success")
        return redirect(url_for("settings.suppliers_list"))

    return render_template("settings/supplier_form.html", supplier=supplier)


@settings_bp.route("/suppliers/<int:supplier_id>/delete", methods=["POST"])
@login_required
@admin_required
def supplier_delete(supplier_id: int):
    """Delete supplier (admin-only)."""
    supplier = Supplier.query.get_or_404(supplier_id)
    before = serialize_model(supplier)

    db.session.delete(supplier)
    db.session.flush()

    log_action(entity=supplier, action="DELETE", before=before)
    db.session.commit()

    flash("Ο προμηθευτής διαγράφηκε.", "success")
    return redirect(url_for("settings.suppliers_list"))


# ----------------------------------------------------------------------
# OPTION VALUES (Enterprise dropdown master-data)
# ----------------------------------------------------------------------
def _options_page(key: str, label: str):
    """
    Generic option values page.

    Pattern:
    - GET: list
    - POST: action in {create, update, delete}
    - Audited for CREATE/UPDATE/DELETE.

    NOTE:
    - Permissions are enforced by the route decorator (admin_required / manager_required).
    """
    category = _get_or_create_category(key=key, label=label)

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()

        # CREATE
        if action == "create":
            value = (request.form.get("value") or "").strip()
            sort_order = _parse_optional_int((request.form.get("sort_order") or "").strip()) or 0
            is_active = bool(request.form.get("is_active") == "on")

            if not value:
                flash("Η τιμή είναι υποχρεωτική.", "danger")
                return redirect(request.path)

            ov = OptionValue(
                category_id=category.id,
                value=value,
                sort_order=sort_order,
                is_active=is_active,
            )
            db.session.add(ov)
            db.session.flush()

            log_action(entity=ov, action="CREATE", after=serialize_model(ov))
            db.session.commit()

            flash("Η τιμή προστέθηκε.", "success")
            return redirect(request.path)

        # UPDATE
        if action == "update":
            ov_id = _parse_optional_int((request.form.get("id") or "").strip())
            if ov_id is None:
                flash("Μη έγκυρη εγγραφή.", "danger")
                return redirect(request.path)

            ov = OptionValue.query.filter_by(id=ov_id, category_id=category.id).first()
            if not ov:
                flash("Η εγγραφή δεν βρέθηκε.", "danger")
                return redirect(request.path)

            before = serialize_model(ov)

            value = (request.form.get("value") or "").strip()
            sort_order = _parse_optional_int((request.form.get("sort_order") or "").strip()) or 0
            is_active = bool(request.form.get("is_active") == "on")

            if not value:
                flash("Η τιμή είναι υποχρεωτική.", "danger")
                return redirect(request.path)

            ov.value = value
            ov.sort_order = sort_order
            ov.is_active = is_active

            db.session.flush()
            log_action(entity=ov, action="UPDATE", before=before, after=serialize_model(ov))
            db.session.commit()

            flash("Η εγγραφή ενημερώθηκε.", "success")
            return redirect(request.path)

        # DELETE
        if action == "delete":
            ov_id = _parse_optional_int((request.form.get("id") or "").strip())
            if ov_id is None:
                flash("Μη έγκυρη εγγραφή.", "danger")
                return redirect(request.path)

            ov = OptionValue.query.filter_by(id=ov_id, category_id=category.id).first()
            if not ov:
                flash("Η εγγραφή δεν βρέθηκε.", "danger")
                return redirect(request.path)

            before = serialize_model(ov)
            db.session.delete(ov)
            db.session.flush()

            log_action(entity=ov, action="DELETE", before=before)
            db.session.commit()

            flash("Η εγγραφή διαγράφηκε.", "success")
            return redirect(request.path)

        flash("Μη έγκυρη ενέργεια.", "danger")
        return redirect(request.path)

    values = _option_values_for_category(category)
    return render_template(
        "settings/options_values.html",
        category=category,
        values=values,
        page_label=label,
    )


# Admin-only option pages (canonical keys to match procurements)
@settings_bp.route("/options/status", methods=["GET", "POST"])
@login_required
@admin_required
def options_status():
    """Option values page: Κατάσταση (admin-only)."""
    return _options_page(key=OPTION_KEY_STATUS, label="Κατάσταση")


@settings_bp.route("/options/stage", methods=["GET", "POST"])
@login_required
@admin_required
def options_stage():
    """Option values page: Στάδιο (admin-only)."""
    return _options_page(key=OPTION_KEY_STAGE, label="Στάδιο")


@settings_bp.route("/options/allocation", methods=["GET", "POST"])
@login_required
@admin_required
def options_allocation():
    """Option values page: Κατανομή (admin-only)."""
    return _options_page(key=OPTION_KEY_ALLOCATION, label="Κατανομή")


@settings_bp.route("/options/quarterly", methods=["GET", "POST"])
@login_required
@admin_required
def options_quarterly():
    """Option values page: Τριμηνιαία (admin-only)."""
    return _options_page(key=OPTION_KEY_QUARTERLY, label="Τριμηνιαία")


@settings_bp.route("/options/vat", methods=["GET", "POST"])
@login_required
@admin_required
def options_vat():
    """Option values page: ΦΠΑ (admin-only)."""
    return _options_page(key=OPTION_KEY_VAT, label="ΦΠΑ")


@settings_bp.route("/options/withholdings", methods=["GET", "POST"])
@login_required
@admin_required
def options_withholdings():
    """Option values page: Κρατήσεις (admin-only)."""
    return _options_page(key=OPTION_KEY_WITHHOLDINGS, label="Κρατήσεις")


# Committees: manager + admin
@settings_bp.route("/options/committees", methods=["GET", "POST"])
@login_required
@manager_required
def options_committees():
    """Option values page: Επιτροπές Προμηθειών (manager+admin)."""
    return _options_page(key=OPTION_KEY_COMMITTEES, label="Επιτροπές Προμηθειών")