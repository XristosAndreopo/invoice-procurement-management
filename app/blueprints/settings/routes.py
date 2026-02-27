"""
Settings routes.

Features
--------
- /settings/theme             -> theme selection (all logged-in users)
- /settings/feedback          -> feedback / complaint form (all logged-in users)
- /settings/feedback/admin    -> admin-only feedback management
- /settings/service-units*    -> Υπηρεσίες (ServiceUnit) CRUD, admin-only
- /settings/suppliers*        -> Προμηθευτές (Supplier) CRUD, admin-only

Option Lists (Enterprise)
-------------------------
Admin-only pages (per sidebar):
- Κατάσταση
- Στάδιο
- Κατανομή
- Τριμηνιαία
- ΦΠΑ
- Κρατήσεις

Manager+Admin:
- Επιτροπές Προμηθειών

IMPORTANT CHANGE (per request):
- The legacy "Στοιχεία/Πληροφορίες" page (/settings/options) is REMOVED.
  There is NO route and NO endpoint "settings.options_index".

Audit (Enterprise)
------------------
- Master-data changes are logged:
  ServiceUnit CREATE/UPDATE/DELETE
  Supplier   CREATE/UPDATE/DELETE
  OptionValue CREATE/UPDATE/DELETE
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from ...extensions import db
from ...models import (
    OptionCategory,
    OptionValue,
    Feedback,
    ServiceUnit,
    Supplier,
    Personnel,
)
from ...audit import log_action, serialize_model


settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _admin_required():
    """Backend gate for admin-only routes."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return render_template("errors/403.html"), 403
    return None


def _manager_or_admin_required():
    """Backend gate for manager+admin routes."""
    if not current_user.is_authenticated:
        return render_template("errors/403.html"), 403
    if not (current_user.is_admin or current_user.can_manage()):
        return render_template("errors/403.html"), 403
    return None


def _active_personnel_for_dropdown():
    """Active personnel list for dropdown selection."""
    return (
        Personnel.query
        .filter_by(is_active=True)
        .order_by(Personnel.last_name.asc(), Personnel.first_name.asc())
        .all()
    )


def _parse_optional_int(value: str):
    """Parse optional int from form. Returns None if empty/invalid."""
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _get_or_create_category(key: str, label: str) -> OptionCategory:
    """
    Ensure an OptionCategory exists.
    This prevents runtime issues if a category hasn't been seeded.
    """
    category = OptionCategory.query.filter_by(key=key).first()
    if category:
        return category

    category = OptionCategory(key=key, label=label)
    db.session.add(category)
    db.session.commit()
    return category


def _option_values_for_category(category: OptionCategory):
    """Return OptionValue list ordered consistently."""
    return (
        OptionValue.query
        .filter_by(category_id=category.id)
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
        Feedback.query
        .filter_by(user_id=current_user.id)
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
def feedback_admin():
    """Admin-only page to review and manage all feedback."""
    guard = _admin_required()
    if guard:
        return guard

    status_choices = {
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
        fb_id_raw = request.form.get("feedback_id")
        new_status = request.form.get("status")

        fb_id = _parse_optional_int(fb_id_raw or "")
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

    status_filter = request.args.get("status") or ""
    category_filter = request.args.get("category") or ""

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
def service_units_list():
    guard = _admin_required()
    if guard:
        return guard

    units = ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()
    return render_template("settings/service_units_list.html", units=units)


@settings_bp.route("/service-units/new", methods=["GET", "POST"])
@login_required
def service_unit_create():
    guard = _admin_required()
    if guard:
        return guard

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
        db.session.commit()

        log_action(unit, "CREATE", before=None, after=serialize_model(unit))
        db.session.commit()

        flash("Η υπηρεσία δημιουργήθηκε.", "success")
        return redirect(url_for("settings.service_units_list"))

    return render_template(
        "settings/service_unit_form.html",
        unit=None,
        form_title="Νέα Υπηρεσία",
        personnel_list=personnel_list,
    )


@settings_bp.route("/service-units/<int:unit_id>/edit", methods=["GET", "POST"])
@login_required
def service_unit_edit(unit_id):
    guard = _admin_required()
    if guard:
        return guard

    unit = ServiceUnit.query.get_or_404(unit_id)
    personnel_list = _active_personnel_for_dropdown()

    if request.method == "POST":
        before_snapshot = serialize_model(unit)

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
            return redirect(url_for("settings.service_unit_edit", unit_id=unit.id))

        if manager_pid and deputy_pid and manager_pid == deputy_pid:
            flash("Ο ίδιος/η ίδια δεν μπορεί να είναι και Manager και Deputy.", "danger")
            return redirect(url_for("settings.service_unit_edit", unit_id=unit.id))

        active_ids = {p.id for p in personnel_list}
        if manager_pid and manager_pid not in active_ids:
            flash("Μη έγκυρος Manager. Επιτρέπεται μόνο ενεργό προσωπικό.", "danger")
            return redirect(url_for("settings.service_unit_edit", unit_id=unit.id))
        if deputy_pid and deputy_pid not in active_ids:
            flash("Μη έγκυρος Deputy. Επιτρέπεται μόνο ενεργό προσωπικό.", "danger")
            return redirect(url_for("settings.service_unit_edit", unit_id=unit.id))

        unit.description = description
        unit.code = code or None
        unit.short_name = short_name or None
        unit.aahit = aahit or None
        unit.commander = commander or None
        unit.curator = curator or None
        unit.supply_officer = supply_officer or None
        unit.manager_personnel_id = manager_pid
        unit.deputy_personnel_id = deputy_pid

        db.session.commit()

        log_action(unit, "UPDATE", before=before_snapshot, after=serialize_model(unit))
        db.session.commit()

        flash("Η υπηρεσία ενημερώθηκε.", "success")
        return redirect(url_for("settings.service_units_list"))

    return render_template(
        "settings/service_unit_form.html",
        unit=unit,
        form_title="Επεξεργασία Υπηρεσίας",
        personnel_list=personnel_list,
    )


@settings_bp.route("/service-units/<int:unit_id>/delete", methods=["POST"])
@login_required
def service_unit_delete(unit_id):
    guard = _admin_required()
    if guard:
        return guard

    unit = ServiceUnit.query.get_or_404(unit_id)
    before_snapshot = serialize_model(unit)

    db.session.delete(unit)
    db.session.commit()

    log_action(unit, "DELETE", before=before_snapshot, after=None)
    db.session.commit()

    flash("Η υπηρεσία διαγράφηκε.", "success")
    return redirect(url_for("settings.service_units_list"))


# ----------------------------------------------------------------------
# SUPPLIERS CRUD (admin only)
# ----------------------------------------------------------------------
@settings_bp.route("/suppliers")
@login_required
def suppliers_list():
    guard = _admin_required()
    if guard:
        return guard

    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    return render_template("settings/suppliers_list.html", suppliers=suppliers)


@settings_bp.route("/suppliers/new", methods=["GET", "POST"])
@login_required
def supplier_create():
    guard = _admin_required()
    if guard:
        return guard

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
            flash("Το ΑΦΜ πρέπει να αποτελείται από 9 ψηφία.", "danger")
            return redirect(url_for("settings.supplier_create"))

        if not name:
            flash("Η επωνυμία είναι υποχρεωτική.", "danger")
            return redirect(url_for("settings.supplier_create"))

        existing = Supplier.query.filter_by(afm=afm).first()
        if existing:
            flash("Υπάρχει ήδη προμηθευτής με αυτό το ΑΦΜ.", "danger")
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
        db.session.commit()

        log_action(supplier, "CREATE", before=None, after=serialize_model(supplier))
        db.session.commit()

        flash("Ο προμηθευτής δημιουργήθηκε.", "success")
        return redirect(url_for("settings.suppliers_list"))

    return render_template("settings/supplier_form.html", supplier=None, form_title="Νέος Προμηθευτής")


@settings_bp.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
@login_required
def supplier_edit(supplier_id):
    guard = _admin_required()
    if guard:
        return guard

    supplier = Supplier.query.get_or_404(supplier_id)

    if request.method == "POST":
        before_snapshot = serialize_model(supplier)

        afm = (request.form.get("afm") or "").strip()
        name = (request.form.get("name") or "").strip()
        address = (request.form.get("address") or "").strip()
        city = (request.form.get("city") or "").strip()
        postal_code = (request.form.get("postal_code") or "").strip()
        country = (request.form.get("country") or "").strip()
        bank_name = (request.form.get("bank_name") or "").strip()
        iban = (request.form.get("iban") or "").strip()

        if not afm or len(afm) != 9 or not afm.isdigit():
            flash("Το ΑΦΜ πρέπει να αποτελείται από 9 ψηφία.", "danger")
            return redirect(url_for("settings.supplier_edit", supplier_id=supplier.id))

        if not name:
            flash("Η επωνυμία είναι υποχρεωτική.", "danger")
            return redirect(url_for("settings.supplier_edit", supplier_id=supplier.id))

        existing = Supplier.query.filter(Supplier.afm == afm, Supplier.id != supplier.id).first()
        if existing:
            flash("Υπάρχει ήδη προμηθευτής με αυτό το ΑΦΜ.", "danger")
            return redirect(url_for("settings.supplier_edit", supplier_id=supplier.id))

        supplier.afm = afm
        supplier.name = name
        supplier.address = address or None
        supplier.city = city or None
        supplier.postal_code = postal_code or None
        supplier.country = country or None
        supplier.bank_name = bank_name or None
        supplier.iban = iban or None

        db.session.commit()

        log_action(supplier, "UPDATE", before=before_snapshot, after=serialize_model(supplier))
        db.session.commit()

        flash("Ο προμηθευτής ενημερώθηκε.", "success")
        return redirect(url_for("settings.suppliers_list"))

    return render_template("settings/supplier_form.html", supplier=supplier, form_title="Επεξεργασία Προμηθευτή")


@settings_bp.route("/suppliers/<int:supplier_id>/delete", methods=["POST"])
@login_required
def supplier_delete(supplier_id):
    guard = _admin_required()
    if guard:
        return guard

    supplier = Supplier.query.get_or_404(supplier_id)
    before_snapshot = serialize_model(supplier)

    db.session.delete(supplier)
    db.session.commit()

    log_action(supplier, "DELETE", before=before_snapshot, after=None)
    db.session.commit()

    flash("Ο προμηθευτής διαγράφηκε.", "success")
    return redirect(url_for("settings.suppliers_list"))


# ----------------------------------------------------------------------
# OPTION LISTS (generic CRUD)
# ----------------------------------------------------------------------
def _options_page(category_key: str, category_label: str, allow_manager: bool = False):
    """
    Render a single option category page.

    Permissions:
    - allow_manager=False -> admin only
    - allow_manager=True  -> manager or admin
    """
    if allow_manager:
        guard = _manager_or_admin_required()
        if guard:
            return guard
    else:
        guard = _admin_required()
        if guard:
            return guard

    category = _get_or_create_category(category_key, category_label)
    values = _option_values_for_category(category)

    return render_template(
        "settings/options_values.html",
        page_title=category_label,
        category=category,
        values=values,
        allow_manager=allow_manager,
    )


def _options_add_value(category_key: str, category_label: str, allow_manager: bool = False):
    """Create OptionValue under given category."""
    if allow_manager:
        guard = _manager_or_admin_required()
        if guard:
            return guard
    else:
        guard = _admin_required()
        if guard:
            return guard

    category = _get_or_create_category(category_key, category_label)

    value = (request.form.get("value") or "").strip()
    sort_order = _parse_optional_int((request.form.get("sort_order") or "").strip()) or 0

    if not value:
        flash("Η τιμή είναι υποχρεωτική.", "danger")
        return redirect(url_for(request.endpoint.replace("_add", "")))

    existing = OptionValue.query.filter_by(category_id=category.id, value=value).first()
    if existing:
        flash("Η τιμή υπάρχει ήδη.", "danger")
        return redirect(url_for(request.endpoint.replace("_add", "")))

    ov = OptionValue(category_id=category.id, value=value, sort_order=sort_order, is_active=True)
    db.session.add(ov)
    db.session.commit()

    log_action(ov, "CREATE", before=None, after=serialize_model(ov))
    db.session.commit()

    flash("Η τιμή προστέθηκε.", "success")
    return redirect(url_for(request.endpoint.replace("_add", "")))


def _options_update_value(category_key: str, category_label: str, allow_manager: bool = False, value_id: int = 0):
    """Update OptionValue fields (value, sort_order, is_active)."""
    if allow_manager:
        guard = _manager_or_admin_required()
        if guard:
            return guard
    else:
        guard = _admin_required()
        if guard:
            return guard

    category = _get_or_create_category(category_key, category_label)
    ov = OptionValue.query.get_or_404(value_id)

    if ov.category_id != category.id:
        abort(403)

    before_snapshot = serialize_model(ov)

    new_value = (request.form.get("value") or "").strip()
    new_sort = _parse_optional_int((request.form.get("sort_order") or "").strip()) or 0
    new_active = bool(request.form.get("is_active"))

    if not new_value:
        flash("Η τιμή είναι υποχρεωτική.", "danger")
        return redirect(url_for(request.endpoint.replace("_update", "")))

    existing = OptionValue.query.filter(
        OptionValue.category_id == category.id,
        OptionValue.value == new_value,
        OptionValue.id != ov.id,
    ).first()
    if existing:
        flash("Υπάρχει ήδη αυτή η τιμή.", "danger")
        return redirect(url_for(request.endpoint.replace("_update", "")))

    ov.value = new_value
    ov.sort_order = new_sort
    ov.is_active = new_active

    db.session.commit()

    log_action(ov, "UPDATE", before=before_snapshot, after=serialize_model(ov))
    db.session.commit()

    flash("Η τιμή ενημερώθηκε.", "success")
    return redirect(url_for(request.endpoint.replace("_update", "")))


# --- Admin-only option pages ---
@settings_bp.route("/options/status")
@login_required
def options_status():
    return _options_page("KATASTASH", "Κατάσταση", allow_manager=False)


@settings_bp.route("/options/status/add", methods=["POST"])
@login_required
def options_status_add():
    return _options_add_value("KATASTASH", "Κατάσταση", allow_manager=False)


@settings_bp.route("/options/status/<int:value_id>/update", methods=["POST"])
@login_required
def options_status_update(value_id):
    return _options_update_value("KATASTASH", "Κατάσταση", allow_manager=False, value_id=value_id)


@settings_bp.route("/options/stage")
@login_required
def options_stage():
    return _options_page("STADIO", "Στάδιο", allow_manager=False)


@settings_bp.route("/options/stage/add", methods=["POST"])
@login_required
def options_stage_add():
    return _options_add_value("STADIO", "Στάδιο", allow_manager=False)


@settings_bp.route("/options/stage/<int:value_id>/update", methods=["POST"])
@login_required
def options_stage_update(value_id):
    return _options_update_value("STADIO", "Στάδιο", allow_manager=False, value_id=value_id)


@settings_bp.route("/options/allocation")
@login_required
def options_allocation():
    return _options_page("KATANOMH", "Κατανομή", allow_manager=False)


@settings_bp.route("/options/allocation/add", methods=["POST"])
@login_required
def options_allocation_add():
    return _options_add_value("KATANOMH", "Κατανομή", allow_manager=False)


@settings_bp.route("/options/allocation/<int:value_id>/update", methods=["POST"])
@login_required
def options_allocation_update(value_id):
    return _options_update_value("KATANOMH", "Κατανομή", allow_manager=False, value_id=value_id)


@settings_bp.route("/options/quarterly")
@login_required
def options_quarterly():
    return _options_page("TRIMHNIAIA", "Τριμηνιαία", allow_manager=False)


@settings_bp.route("/options/quarterly/add", methods=["POST"])
@login_required
def options_quarterly_add():
    return _options_add_value("TRIMHNIAIA", "Τριμηνιαία", allow_manager=False)


@settings_bp.route("/options/quarterly/<int:value_id>/update", methods=["POST"])
@login_required
def options_quarterly_update(value_id):
    return _options_update_value("TRIMHNIAIA", "Τριμηνιαία", allow_manager=False, value_id=value_id)


@settings_bp.route("/options/vat")
@login_required
def options_vat():
    return _options_page("FPA", "ΦΠΑ", allow_manager=False)


@settings_bp.route("/options/vat/add", methods=["POST"])
@login_required
def options_vat_add():
    return _options_add_value("FPA", "ΦΠΑ", allow_manager=False)


@settings_bp.route("/options/vat/<int:value_id>/update", methods=["POST"])
@login_required
def options_vat_update(value_id):
    return _options_update_value("FPA", "ΦΠΑ", allow_manager=False, value_id=value_id)


@settings_bp.route("/options/withholdings")
@login_required
def options_withholdings():
    return _options_page("KRATHSEIS", "Κρατήσεις", allow_manager=False)


@settings_bp.route("/options/withholdings/add", methods=["POST"])
@login_required
def options_withholdings_add():
    return _options_add_value("KRATHSEIS", "Κρατήσεις", allow_manager=False)


@settings_bp.route("/options/withholdings/<int:value_id>/update", methods=["POST"])
@login_required
def options_withholdings_update(value_id):
    return _options_update_value("KRATHSEIS", "Κρατήσεις", allow_manager=False, value_id=value_id)


# --- Manager+Admin page ---
@settings_bp.route("/options/committees")
@login_required
def options_committees():
    return _options_page("EPITROPES", "Επιτροπές Προμηθειών", allow_manager=True)


@settings_bp.route("/options/committees/add", methods=["POST"])
@login_required
def options_committees_add():
    return _options_add_value("EPITROPES", "Επιτροπές Προμηθειών", allow_manager=True)


@settings_bp.route("/options/committees/<int:value_id>/update", methods=["POST"])
@login_required
def options_committees_update(value_id):
    return _options_update_value("EPITROPES", "Επιτροπές Προμηθειών", allow_manager=True, value_id=value_id)