"""
app/blueprints/auth/routes.py

Authentication routes for the Invoice / Procurement Management System.

PROVIDES
--------
- /auth/login
- /auth/logout
- /auth/seed-admin

ARCHITECTURAL INTENT
--------------------
This file is route-focused.

Routes should remain responsible only for:
- decorators
- request data reads
- Flask-Login session calls
- final HTTP branching
- flash / redirect / render_template

NON-HTTP ORCHESTRATION HAS BEEN EXTRACTED TO
--------------------------------------------
- app/services/auth_service.py

DECISIONS FOR THIS REFACTOR PASS
--------------------------------
1. login
   - extracted to focused auth service for credential validation and safe next
     resolution

2. logout
   - stabilized as-is because it is already thin and purely HTTP/session
     orchestration

3. seed-admin
   - extracted to focused auth service for bootstrap validation and persistence

SECURITY MODEL
--------------
- UI is never trusted.
- Only active users may log in.
- Password validation is always server-side.
- The bootstrap admin route is self-locking after first user creation.
- Every system user must be linked to a Personnel record.

IMPORTANT BOUNDARY
------------------
This module must not re-absorb business/application orchestration back into the
route layer. If future auth flows become more complex, they should expand the
focused auth service module rather than fattening the routes again.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ...services.auth_service import (
    build_login_page_context,
    build_seed_admin_page_context,
    execute_login,
    execute_seed_admin,
    should_block_seed_admin,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Authenticate a user.

    ROUTE RESPONSIBILITIES
    ----------------------
    - redirect already-authenticated users away from login
    - read request form/query values
    - call service-layer validation
    - establish Flask-Login session on success
    - emit flash messages and final response
    """
    if current_user.is_authenticated:
        return redirect(url_for("procurements.inbox_procurements"))

    raw_next = request.args.get("next") or request.form.get("next")

    if request.method == "POST":
        result = execute_login(request.form, raw_next)
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok and result.user is not None and result.redirect_url:
            login_user(result.user)
            return redirect(result.redirect_url)

        context = build_login_page_context(raw_next)
        return render_template("auth/login.html", **context)

    context = build_login_page_context(raw_next)
    return render_template("auth/login.html", **context)


@auth_bp.route("/logout")
@login_required
def logout():
    """
    Log out the current user.

    STABILIZE DECISION
    ------------------
    This route already matches the target architecture:
    - pure HTTP/session boundary concern
    - no business orchestration
    - no need for service extraction
    """
    logout_user()
    flash("Αποσυνδεθήκατε.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/seed-admin", methods=["GET", "POST"])
def seed_admin():
    """
    Bootstrap the first admin of the system.

    ROUTE RESPONSIBILITIES
    ----------------------
    - enforce the self-locking redirect when bootstrap is already closed
    - read submitted form data
    - call service-layer creation orchestration
    - emit flash messages and final response
    """
    if should_block_seed_admin():
        flash("Υπάρχει ήδη χρήστης στο σύστημα.", "warning")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        result = execute_seed_admin(request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("auth.login"))

        context = build_seed_admin_page_context()
        return render_template("auth/seed_admin.html", **context)

    context = build_seed_admin_page_context()
    return render_template("auth/seed_admin.html", **context)
