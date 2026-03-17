"""
app/security/__init__.py

Public security facade for the Invoice / Procurement Management System.

PURPOSE
-------
This package provides the stable public import surface for security helpers
used across the application.

PACKAGE STRUCTURE
-----------------
- app.security.permissions
    Canonical authorization predicates and scope checks

- app.security.decorators
    Reusable Flask route decorators

- app.security
    Shared response helpers, request-level guard, and public re-exports

SECURITY PRINCIPLES
-------------------
1. The UI is never trusted.
2. Navigation visibility is not authorization.
3. All permission checks are enforced server-side.
4. Non-admin users are limited to their own ServiceUnit scope.
5. Viewers are read-only except for explicitly allowed self-service actions.
"""

from __future__ import annotations

from typing import Optional, Tuple

from flask import abort, render_template, request
from flask_login import current_user

from .permissions import (
    can_edit_procurement,
    can_manage_service_unit,
    can_view_procurement,
    is_admin,
    is_manager_or_deputy,
)

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _forbidden() -> Tuple[str, int]:
    """
    Render the standard 403 page.
    """
    return render_template("errors/403.html"), 403


def _abort_or_render_forbidden() -> None:
    """
    Abort with HTTP 403.
    """
    abort(403)


def viewer_readonly_guard() -> Optional[Tuple[str, int]]:
    """
    Block mutating requests for authenticated read-only viewer users.
    """
    if request.method not in MUTATING_METHODS:
        return None

    if not current_user.is_authenticated:
        return None

    if is_admin() or is_manager_or_deputy():
        return None

    endpoint = (request.endpoint or "").strip()
    allow_mutating_endpoints = {
        "settings.theme",
        "settings.feedback",
        "auth.logout",
    }

    if endpoint in allow_mutating_endpoints:
        return None

    return _forbidden()


from .decorators import (  # noqa: E402
    admin_required,
    ensure_manage_service_unit_or_403,
    manager_required,
    org_manage_required,
    procurement_access_required,
    procurement_edit_required,
)

__all__ = [
    "MUTATING_METHODS",
    "_forbidden",
    "_abort_or_render_forbidden",
    "viewer_readonly_guard",
    "is_admin",
    "is_manager_or_deputy",
    "can_view_procurement",
    "can_edit_procurement",
    "can_manage_service_unit",
    "admin_required",
    "manager_required",
    "procurement_access_required",
    "procurement_edit_required",
    "org_manage_required",
    "ensure_manage_service_unit_or_403",
]

