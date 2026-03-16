"""
app/blueprints/settings/routes.py

Settings & Master Data routes.

OVERVIEW
--------
This blueprint contains the application's settings and master-data management
screens.

ARCHITECTURAL DECISION FOR THIS PASS
------------------------------------
This file now follows a mixed strategy based on the actual current state from
`combined_project.md`:

1. STABILIZE, NOT DECOMPOSE
   - ServiceUnit routes
   - Supplier routes
   These routes are already sufficiently thin because their orchestration has
   already moved into focused service modules.

2. EXTRACT USE-CASE / PAGE SERVICES
   - Theme
   - Feedback
   - Feedback admin
   - ALE-KAE
   - CPV
   - Generic option-value pages
   - IncomeTaxRule
   - WithholdingProfile
   - Committees

3. SECURITY GUARD CONSOLIDATION
   - committee scope guard
   - legacy structure redirect scope guard

ROUTE BOUNDARY
--------------
Routes in this module should now remain responsible only for:
- decorators
- reading request.args / request.form / request.files
- boundary object loads where appropriate
- calling a focused service/use-case function
- flash(...)
- render_template(...)
- redirect(...)

IMPORTANT SOURCE-OF-TRUTH NOTE
------------------------------
`combined_project.md` currently contains at least two visible inconsistencies
outside the code changed in this pass:

1. `app/models/feedback.py` does not visibly define fields used by the current
   settings routes (`user_id`, `category`, `related_procurement_id`).

2. The current ServiceUnit model/service excerpts show inconsistent deputy field
   naming (`deputy_personnel_id` vs `deputy_manager_personnel_id`).

Those issues are not changed here because this pass is focused on the route
refactor boundary, and the instruction was to avoid assumptions beyond the
actual provided source of truth.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ...models import ServiceUnit, Supplier
from ...security import admin_required, manager_required
from ...security.settings_guards import ensure_settings_structure_scope_or_403
from ...services.settings_theme_service import (
    build_theme_page_context,
    execute_theme_update,
)
from ...services.settings_feedback_service import (
    build_feedback_admin_page_context,
    build_feedback_page_context,
    execute_feedback_admin_status_update,
    execute_feedback_submission,
)
from ...services.settings_master_data_admin_service import (
    build_ale_kae_page_context,
    build_cpv_page_context,
    build_income_tax_rules_page_context,
    build_option_values_page_context,
    build_withholding_profiles_page_context,
    execute_ale_kae_action,
    execute_cpv_action,
    execute_import_ale_kae,
    execute_import_cpv,
    execute_income_tax_rule_action,
    execute_option_value_action,
    execute_withholding_profile_action,
)
from ...services.settings_committees_service import (
    build_committees_page_context,
    execute_committee_action,
)
from ...services.settings_service_units_service import (
    build_service_unit_form_page_context,
    build_service_unit_roles_form_page_context,
    build_service_units_list_page_context,
    build_service_units_roles_page_context,
    execute_assign_service_unit_roles,
    execute_create_service_unit,
    execute_delete_service_unit,
    execute_edit_service_unit_info,
    execute_import_service_units,
)
from ...services.settings_suppliers_service import (
    build_supplier_form_page_context,
    build_suppliers_list_page_context,
    execute_create_supplier,
    execute_delete_supplier,
    execute_edit_supplier,
    execute_import_suppliers,
)

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


# ----------------------------------------------------------------------
# THEME (all users)
# ----------------------------------------------------------------------
@settings_bp.route("/theme", methods=["GET", "POST"])
@login_required
def theme():
    """
    Allow any logged-in user to select their UI theme.

    NOTE
    ----
    This remains one of the few mutating actions allowed even for read-only
    users, as handled by the global readonly guard allow-list.
    """
    if request.method == "POST":
        result = execute_theme_update(current_user, request.form)
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(url_for("settings.theme"))

    context = build_theme_page_context()
    return render_template("settings/theme.html", **context)


# ----------------------------------------------------------------------
# FEEDBACK (all users)
# ----------------------------------------------------------------------
@settings_bp.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    """
    Feedback / complaint submission form for logged-in users.
    """
    if request.method == "POST":
        result = execute_feedback_submission(
            user_id=current_user.id,
            form_data=request.form,
        )
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(url_for("settings.feedback"))

    context = build_feedback_page_context(user_id=current_user.id)
    return render_template("settings/feedback.html", **context)


# ----------------------------------------------------------------------
# FEEDBACK ADMIN (admin only)
# ----------------------------------------------------------------------
@settings_bp.route("/feedback/admin", methods=["GET", "POST"])
@login_required
@admin_required
def feedback_admin():
    """
    Admin-only review and management page for all feedback submissions.
    """
    if request.method == "POST":
        result = execute_feedback_admin_status_update(request.form)
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(url_for("settings.feedback_admin"))

    context = build_feedback_admin_page_context(request.args)
    return render_template("settings/feedback_admin.html", **context)


# ----------------------------------------------------------------------
# SERVICE UNITS (admin-only) -- STABILIZE ONLY
# ----------------------------------------------------------------------
@settings_bp.route("/service-units")
@login_required
@admin_required
def service_units_list():
    """List ServiceUnits basic info."""
    context = build_service_units_list_page_context()
    return render_template("settings/service_units_list.html", **context)


@settings_bp.route("/service-units/roles")
@login_required
@admin_required
def service_units_roles_list():
    """List ServiceUnits with Manager/Deputy assignments."""
    context = build_service_units_roles_page_context()
    return render_template("settings/service_units_roles_list.html", **context)


@settings_bp.route("/service-units/new", methods=["GET", "POST"])
@login_required
@admin_required
def service_unit_create():
    """Create a new ServiceUnit."""
    if request.method == "POST":
        result = execute_create_service_unit(request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("settings.service_units_list"))
        return redirect(url_for("settings.service_unit_create"))

    context = build_service_unit_form_page_context(
        unit=None,
        form_title="Νέα Υπηρεσία",
        is_create=True,
    )
    return render_template("settings/service_unit_form.html", **context)


@settings_bp.route("/service-units/import", methods=["POST"])
@login_required
@admin_required
def service_units_import():
    """
    Import ServiceUnits from Excel.
    """
    result = execute_import_service_units(request.files.get("file"))
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(url_for("settings.service_units_list"))


@settings_bp.route("/service-units/<int:unit_id>/edit-info", methods=["GET", "POST"])
@login_required
@admin_required
def service_unit_edit_info(unit_id: int):
    """Edit basic ServiceUnit fields."""
    unit = ServiceUnit.query.get_or_404(unit_id)

    if request.method == "POST":
        result = execute_edit_service_unit_info(unit, request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("settings.service_units_list"))
        return redirect(url_for("settings.service_unit_edit_info", unit_id=unit.id))

    context = build_service_unit_form_page_context(
        unit=unit,
        form_title="Επεξεργασία Υπηρεσίας",
        is_create=False,
    )
    return render_template("settings/service_unit_form.html", **context)


@settings_bp.route("/service-units/<int:unit_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def service_unit_edit(unit_id: int):
    """Assign Manager / Deputy for a ServiceUnit."""
    unit = ServiceUnit.query.get_or_404(unit_id)

    if request.method == "POST":
        result = execute_assign_service_unit_roles(unit, request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("settings.service_units_roles_list"))
        return redirect(url_for("settings.service_unit_edit", unit_id=unit.id))

    context = build_service_unit_roles_form_page_context(
        unit=unit,
        form_title="Ορισμός Deputy/Manager",
    )
    return render_template("settings/service_units_roles_form.html", **context)


@settings_bp.route("/service-units/<int:unit_id>/delete", methods=["POST"])
@login_required
@admin_required
def service_unit_delete(unit_id: int):
    """Delete a ServiceUnit using a defensive SQLite-safe strategy."""
    unit = ServiceUnit.query.get_or_404(unit_id)

    result = execute_delete_service_unit(unit)
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(url_for("settings.service_units_list"))


# ----------------------------------------------------------------------
# LEGACY: SERVICE UNIT STRUCTURE (compatibility redirect)
# ----------------------------------------------------------------------
@settings_bp.route("/service-units/<int:unit_id>/structure", methods=["GET", "POST"])
@login_required
@manager_required
def service_unit_structure(unit_id: int):
    """
    Backward-compatibility redirect to the consolidated organization page.

    This route remains intentionally thin. It is a compatibility boundary,
    not a business workflow.
    """
    unit = ServiceUnit.query.get_or_404(unit_id)
    ensure_settings_structure_scope_or_403(unit.id)
    return redirect(url_for("admin.organization_setup", service_unit_id=unit.id))


# ----------------------------------------------------------------------
# SUPPLIERS CRUD (admin only) -- STABILIZE ONLY
# ----------------------------------------------------------------------
@settings_bp.route("/suppliers")
@login_required
@admin_required
def suppliers_list():
    """List suppliers."""
    context = build_suppliers_list_page_context()
    return render_template("settings/suppliers_list.html", **context)


@settings_bp.route("/suppliers/new", methods=["GET", "POST"])
@login_required
@admin_required
def supplier_create():
    """Create a supplier."""
    if request.method == "POST":
        result = execute_create_supplier(request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("settings.suppliers_list"))
        return redirect(url_for("settings.supplier_create"))

    context = build_supplier_form_page_context(
        supplier=None,
        form_title="Νέος Προμηθευτής",
    )
    return render_template("settings/supplier_form.html", **context)


@settings_bp.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def supplier_edit(supplier_id: int):
    """Edit a supplier."""
    supplier = Supplier.query.get_or_404(supplier_id)

    if request.method == "POST":
        result = execute_edit_supplier(supplier, request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("settings.suppliers_list"))
        return redirect(url_for("settings.supplier_edit", supplier_id=supplier.id))

    context = build_supplier_form_page_context(
        supplier=supplier,
        form_title="Επεξεργασία Προμηθευτή",
    )
    return render_template("settings/supplier_form.html", **context)


@settings_bp.route("/suppliers/<int:supplier_id>/delete", methods=["POST"])
@login_required
@admin_required
def supplier_delete(supplier_id: int):
    """Delete a supplier."""
    supplier = Supplier.query.get_or_404(supplier_id)

    result = execute_delete_supplier(supplier)
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(url_for("settings.suppliers_list"))


@settings_bp.route("/suppliers/import", methods=["POST"])
@login_required
@admin_required
def suppliers_import():
    """
    Import Suppliers from Excel.
    """
    result = execute_import_suppliers(request.files.get("file"))
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(url_for("settings.suppliers_list"))


# ----------------------------------------------------------------------
# ALE-KAE (admin-only) + Excel import
# ----------------------------------------------------------------------
@settings_bp.route("/ale-kae", methods=["GET", "POST"])
@login_required
@admin_required
def ale_kae():
    """Admin-only CRUD page for ALE-KAE."""
    if request.method == "POST":
        result = execute_ale_kae_action(request.form)
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(url_for("settings.ale_kae"))

    context = build_ale_kae_page_context()
    return render_template("settings/ale_kae.html", **context)


@settings_bp.route("/ale-kae/import", methods=["POST"])
@login_required
@admin_required
def ale_kae_import():
    """Admin-only Excel import for ALE-KAE."""
    result = execute_import_ale_kae(request.files.get("file"))
    for item in result.flashes:
        flash(item.message, item.category)
    return redirect(url_for("settings.ale_kae"))


# ----------------------------------------------------------------------
# CPV (admin-only) + Excel import
# ----------------------------------------------------------------------
@settings_bp.route("/cpv", methods=["GET", "POST"])
@login_required
@admin_required
def cpv():
    """Admin-only CRUD page for CPV."""
    if request.method == "POST":
        result = execute_cpv_action(request.form)
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(url_for("settings.cpv"))

    context = build_cpv_page_context()
    return render_template("settings/cpv.html", **context)


@settings_bp.route("/cpv/import", methods=["POST"])
@login_required
@admin_required
def cpv_import():
    """Admin-only Excel import for CPV."""
    result = execute_import_cpv(request.files.get("file"))
    for item in result.flashes:
        flash(item.message, item.category)
    return redirect(url_for("settings.cpv"))


# ----------------------------------------------------------------------
# OPTION VALUES + IncomeTax + Withholding + Committees
# ----------------------------------------------------------------------
def _options_page(key: str, label: str):
    """
    Shared HTTP-only route helper for generic OptionValue category pages.

    WHY THIS HELPER REMAINS HERE
    ----------------------------
    This helper now performs only HTTP orchestration:
    - call service for POST or GET context
    - flash messages
    - render / redirect

    Query composition, validation, persistence, and category bootstrap live in
    the dedicated settings master-data service module.
    """
    if request.method == "POST":
        result = execute_option_value_action(key=key, label=label, form_data=request.form)
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(request.path)

    context = build_option_values_page_context(key=key, label=label)
    return render_template("settings/options_values.html", **context)


@settings_bp.route("/options/status", methods=["GET", "POST"])
@login_required
@admin_required
def options_status():
    """CRUD for status options."""
    return _options_page(key="KATASTASH", label="Κατάσταση")


@settings_bp.route("/options/stage", methods=["GET", "POST"])
@login_required
@admin_required
def options_stage():
    """CRUD for stage options."""
    return _options_page(key="STADIO", label="Στάδιο")


@settings_bp.route("/options/allocation", methods=["GET", "POST"])
@login_required
@admin_required
def options_allocation():
    """CRUD for allocation options."""
    return _options_page(key="KATANOMH", label="Κατανομή")


@settings_bp.route("/options/quarterly", methods=["GET", "POST"])
@login_required
@admin_required
def options_quarterly():
    """CRUD for quarterly options."""
    return _options_page(key="TRIMHNIAIA", label="Τριμηνιαία")


@settings_bp.route("/options/vat", methods=["GET", "POST"])
@login_required
@admin_required
def options_vat():
    """CRUD for VAT options."""
    return _options_page(key="FPA", label="ΦΠΑ")


@settings_bp.route("/income-tax", methods=["GET", "POST"])
@login_required
@admin_required
def income_tax_rules():
    """CRUD for IncomeTaxRule master data."""
    if request.method == "POST":
        result = execute_income_tax_rule_action(request.form)
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(request.path)

    context = build_income_tax_rules_page_context()
    return render_template("settings/income_tax_rules.html", **context)


@settings_bp.route("/withholding-profiles", methods=["GET", "POST"])
@login_required
@admin_required
def withholding_profiles():
    """CRUD for WithholdingProfile master data."""
    if request.method == "POST":
        result = execute_withholding_profile_action(request.form)
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(request.path)

    context = build_withholding_profiles_page_context()
    return render_template("settings/withholding_profiles.html", **context)


@settings_bp.route("/committees", methods=["GET", "POST"])
@login_required
@manager_required
def committees():
    """
    Procurement committees management.

    SCOPE RULES
    -----------
    - admin: may select any service unit
    - manager/deputy: forced to own service unit server-side
    """
    if request.method == "POST":
        result = execute_committee_action(request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        redirect_service_unit_id = result.entity_id
        if redirect_service_unit_id:
            return redirect(url_for("settings.committees", service_unit_id=redirect_service_unit_id))
        return redirect(url_for("settings.committees"))

    context = build_committees_page_context(request.args)
    return render_template("settings/committees.html", **context)
