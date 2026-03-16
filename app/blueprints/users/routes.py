"""
Enterprise User Management (Admin Only).

Enterprise rules enforced:
- Every User MUST link to exactly one Personnel (1-to-1).
- Admin selects Personnel from the organizational directory.
- UI is never trusted: all constraints are validated server-side.
- Personnel organizational assignment is the source of truth for ServiceUnit consistency.

ROUTE LAYER INTENT
------------------
This module is intentionally kept thin.

Routes here should do only:
- decorators and HTTP boundary protection
- reading `request.form`
- basic object loading (`get_or_404`)
- calling service-layer functions
- translating service results into `flash(...)`, `redirect(...)`, and `render_template(...)`

Non-route orchestration lives in:
- `app/services/user_management_service.py`
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ...models import User
from ...security import admin_required
from ...services.parsing import parse_optional_int
from ...services.user_management_service import (
    build_create_user_page_context,
    build_edit_user_page_context,
    execute_create_user,
    execute_edit_user,
    list_users_for_admin,
)

users_bp = Blueprint(
    "users",
    __name__,
    url_prefix="/users",
)


@users_bp.route("/")
@login_required
@admin_required
def list_users():
    """
    Admin view: list all users.

    ARCHITECTURAL DECISION
    ---------------------
    Stabilize, not decompose further.

    This route is already thin:
    - authorization only
    - one list query via service helper
    - direct template render
    """
    users = list_users_for_admin()
    return render_template("users/list.html", users=users)


@users_bp.route("/new", methods=["GET", "POST"])
@login_required
@admin_required
def create_user():
    """
    Create a new system user.
    """
    if request.method == "POST":
        result = execute_create_user(
            username=(request.form.get("username") or "").strip(),
            password=(request.form.get("password") or "").strip(),
            service_unit_id=parse_optional_int(request.form.get("service_unit_id")),
            is_admin=bool(request.form.get("is_admin")),
            personnel_id=parse_optional_int(request.form.get("personnel_id")),
        )

        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("users.list_users"))

        return redirect(url_for("users.create_user"))

    context = build_create_user_page_context()
    return render_template("users/new.html", **context)


@users_bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id: int):
    """
    Edit an existing user.
    """
    user = User.query.get_or_404(user_id)

    if request.method == "POST":
        result = execute_edit_user(
            user=user,
            is_admin=bool(request.form.get("is_admin")),
            is_active=bool(request.form.get("is_active")),
            service_unit_id=parse_optional_int(request.form.get("service_unit_id")),
            personnel_id=parse_optional_int(request.form.get("personnel_id")),
            new_password=(request.form.get("password") or "").strip(),
        )

        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("users.list_users"))

        return redirect(url_for("users.edit_user", user_id=user.id))

    context = build_edit_user_page_context(user)
    return render_template("users/edit.html", **context)
