"""
app/blueprints/admin/routes.py

Admin Routes – Enterprise Administration Module
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
from ...services.admin.organization_setup import (
    build_organization_setup_page_context,
    execute_organization_setup_action,
)
from ...services.admin.personnel import (
    build_personnel_form_page_context,
    build_personnel_list_page_context,
    execute_create_personnel,
    execute_delete_personnel,
    execute_edit_personnel,
    execute_import_personnel,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/personnel")
@login_required
@admin_or_manager_required
def personnel_list():
    context = build_personnel_list_page_context()
    return render_template("admin/personnel_list.html", **context)


@admin_bp.route("/personnel/import", methods=["POST"])
@login_required
@admin_required
def import_personnel():
    result = execute_import_personnel(request.files.get("file"))
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(url_for("admin.personnel_list"))


@admin_bp.route("/personnel/new", methods=["GET", "POST"])
@login_required
@admin_or_manager_required
def create_personnel():
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
    if request.method == "POST":
        result = execute_organization_setup_action(
            request.form,
            files=request.files,
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


@admin_bp.route("/personnel/<int:personnel_id>/delete", methods=["POST"])
@login_required
@admin_or_manager_required
def delete_personnel(personnel_id: int):
    person = Personnel.query.get_or_404(personnel_id)
    ensure_personnel_manage_scope_or_403(person)

    result = execute_delete_personnel(person)
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(url_for("admin.personnel_list"))