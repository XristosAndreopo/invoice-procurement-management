"""
app/blueprints/admin/routes.py

Admin Routes – Enterprise Administration Module

OVERVIEW
--------
This blueprint contains the admin-side organization management flows:

1. Personnel management
   - list
   - Excel import
   - create
   - edit

2. Consolidated organization setup
   - directories
   - departments
   - leadership role assignments

ARCHITECTURAL INTENT
--------------------
This file is now route-focused.

Routes should remain responsible only for:
- decorators
- request/form/file reading
- boundary-level object loads
- calling focused service functions
- flashing service-returned messages
- render/redirect responses

NON-HTTP ORCHESTRATION HAS BEEN EXTRACTED TO
--------------------------------------------
- app/services/admin_personnel_service.py
- app/services/admin_organization_setup_service.py
- app/security/admin_guards.py

SECURITY MODEL
--------------
- Admin: full access
- Manager: own service unit only
- Deputy: excluded from this blueprint's mutation flows
- UI is never trusted
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ...models import Personnel
from ...security import admin_required
from ...security.admin_guards import (
    admin_or_manager_required,
    ensure_personnel_manage_scope_or_403,
)
from ...services.admin_organization_setup_service import (
    build_organization_setup_page_context,
    execute_organization_setup_action,
)
from ...services.admin_personnel_service import (
    build_personnel_form_page_context,
    build_personnel_list_page_context,
    execute_create_personnel,
    execute_edit_personnel,
    execute_import_personnel,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/personnel")
@login_required
@admin_or_manager_required
def personnel_list():
    """
    List organizational personnel.

    Admin:
    - sees all personnel

    Manager:
    - sees only personnel of their own ServiceUnit
    """
    context = build_personnel_list_page_context()
    return render_template("admin/personnel_list.html", **context)


@admin_bp.route("/personnel/import", methods=["POST"])
@login_required
@admin_required
def import_personnel():
    """
    Import Personnel from Excel (admin-only).
    """
    result = execute_import_personnel(request.files.get("file"))
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(url_for("admin.personnel_list"))


@admin_bp.route("/personnel/new", methods=["GET", "POST"])
@login_required
@admin_or_manager_required
def create_personnel():
    """
    Create a new Personnel row.

    Admin:
    - may assign any service unit / directory / department

    Manager:
    - may assign only their own service unit
    """
    if request.method == "POST":
        result = execute_create_personnel(
            request.form,
            is_admin=getattr(current_user, "is_admin", False),
            current_service_unit_id=getattr(current_user, "service_unit_id", None),
        )
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("admin.personnel_list"))

        return redirect(url_for("admin.create_personnel"))

    context = build_personnel_form_page_context(
        person=None,
        form_title="Νέο Προσωπικό",
    )
    return render_template("admin/personnel_form.html", **context)


@admin_bp.route("/personnel/<int:personnel_id>/edit", methods=["GET", "POST"])
@login_required
@admin_or_manager_required
def edit_personnel(personnel_id: int):
    """
    Edit an existing Personnel row.

    Admin:
    - may edit any Personnel

    Manager:
    - may edit only Personnel of their own ServiceUnit
    """
    person = Personnel.query.get_or_404(personnel_id)
    ensure_personnel_manage_scope_or_403(person)

    if request.method == "POST":
        result = execute_edit_personnel(
            person,
            request.form,
            is_admin=getattr(current_user, "is_admin", False),
            current_service_unit_id=getattr(current_user, "service_unit_id", None),
        )
        for item in result.flashes:
            flash(item.message, item.category)

        return redirect(url_for("admin.edit_personnel", personnel_id=person.id))

    context = build_personnel_form_page_context(
        person=person,
        form_title="Επεξεργασία Προσωπικού",
    )
    return render_template("admin/personnel_form.html", **context)


@admin_bp.route("/organization-setup", methods=["GET", "POST"])
@login_required
@admin_or_manager_required
def organization_setup():
    """
    Consolidated ServiceUnit organization management page.
    """
    if request.method == "POST":
        result = execute_organization_setup_action(
            request.form,
            is_admin=getattr(current_user, "is_admin", False),
            current_service_unit_id=getattr(current_user, "service_unit_id", None),
        )
        for item in result.flashes:
            flash(item.message, item.category)

        if result.redirect_service_unit_id is not None:
            return redirect(
                url_for(
                    "admin.organization_setup",
                    service_unit_id=result.redirect_service_unit_id,
                )
            )

        return redirect(url_for("admin.organization_setup"))

    context = build_organization_setup_page_context(
        request.args,
        is_admin=getattr(current_user, "is_admin", False),
        current_service_unit_id=getattr(current_user, "service_unit_id", None),
    )
    return render_template("admin/organization_setup.html", **context)