"""
app/security.py

Enterprise-grade access control helpers for the Invoice / Procurement Management System.

Key rules:
- UI is never trusted; all permission checks are server-side.
- Admin: full access.
- Service isolation: non-admin sees only their ServiceUnit procurements.
- Per ServiceUnit:
  - Manager + Deputy: full CRUD for procurements of their unit.
  - Viewers: read-only (no mutating requests), except explicit self-service actions.

NEW (V5.0) - Organizational Structure Permissions:
- Directories/Departments/Personnel management require:
  - Admin: always allowed
  - Manager/Deputy: allowed ONLY within their own ServiceUnit (scope enforced server-side)

This module also provides a global safety net:
- viewer_readonly_guard() blocks POST/PUT/PATCH/DELETE for Viewers.
  Wire it via app.before_request in app factory.

IMPORTANT:
- Decorators must preserve wrapped function metadata to avoid Flask endpoint collisions.
  We use functools.wraps everywhere.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Optional, Tuple, TypeVar

from flask import abort, render_template, request
from flask_login import current_user

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

T = TypeVar("T")


def _forbidden() -> Tuple[str, int]:
    """Render a consistent 403 page."""
    return render_template("errors/403.html"), 403


def _abort_or_render_forbidden() -> None:
    """
    Abort with 403.

    NOTE:
    - Some parts of the app use abort(403) and others return a rendered 403 page.
    - Security helpers prefer a consistent template for user experience.
    - Routes that rely on abort(403) can still call abort directly.
    """
    # For now we keep compatibility: returning _forbidden() from decorators.
    # When used as a guard helper in routes, abort is more idiomatic.
    abort(403)


def is_admin() -> bool:
    """Return True if current user is authenticated and admin."""
    return bool(current_user.is_authenticated and getattr(current_user, "is_admin", False))


def is_manager_or_deputy() -> bool:
    """
    Return True if current user can manage their service unit.

    Depends on User.can_manage() which should return True for:
    - admin OR manager OR deputy (based on ServiceUnit manager/deputy links).
    """
    if not current_user.is_authenticated:
        return False
    can_manage = getattr(current_user, "can_manage", None)
    return bool(callable(can_manage) and can_manage())


def can_manage_service_unit(service_unit_id: int | None) -> bool:
    """
    True if current user is allowed to manage entities scoped to a ServiceUnit.

    Rules:
    - Admin: always allowed
    - Manager/Deputy: only if their assigned service_unit_id equals service_unit_id
    - Viewers/others: never allowed
    """
    if not current_user.is_authenticated:
        return False
    if is_admin():
        return True
    if not is_manager_or_deputy():
        return False
    user_su_id = getattr(current_user, "service_unit_id", None)
    return bool(user_su_id and service_unit_id and int(user_su_id) == int(service_unit_id))


def ensure_manage_service_unit_or_403(service_unit_id: int | None) -> None:
    """
    Guard helper: abort(403) if current user cannot manage this ServiceUnit scope.

    Use in routes for:
    - Directories/Departments CRUD
    - Setup page assignments
    - Personnel management (manager scope)
    """
    if not can_manage_service_unit(service_unit_id):
        _abort_or_render_forbidden()


def viewer_readonly_guard() -> Optional[Tuple[str, int]]:
    """
    Global guard: Viewers cannot mutate data.

    Blocks POST/PUT/PATCH/DELETE for users who are:
    - authenticated
    - NOT admin
    - NOT manager/deputy

    Allow-list for safe self-service mutating endpoints:
    - settings.theme
    - settings.feedback
    - auth.logout
    """
    if request.method not in MUTATING_METHODS:
        return None

    if not current_user.is_authenticated:
        return None

    if is_admin() or is_manager_or_deputy():
        return None

    endpoint = (request.endpoint or "").strip()
    allow_mutating_endpoints = {"settings.theme", "settings.feedback", "auth.logout"}
    if endpoint in allow_mutating_endpoints:
        return None

    return _forbidden()


def admin_required(view_func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: admin-only."""
    @wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any):
        if not is_admin():
            return _forbidden()
        return view_func(*args, **kwargs)

    return wrapper


def manager_required(view_func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator: manager/deputy/admin.

    For pages/actions allowed to managers (and also admins), e.g. committees.
    """
    @wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any):
        if not current_user.is_authenticated:
            return _forbidden()
        if not (is_admin() or is_manager_or_deputy()):
            return _forbidden()
        return view_func(*args, **kwargs)

    return wrapper


def procurement_access_required(get_procurement_func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator factory: VIEW permission for a procurement.

    Admin: always allowed.
    Non-admin: allowed only if procurement.service_unit_id == current_user.service_unit_id

    Usage:
        @procurement_access_required(lambda procurement_id: Procurement.query.get_or_404(procurement_id))
        def view(procurement_id): ...
    """
    def decorator(view_func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view_func)
        def wrapper(*args: Any, **kwargs: Any):
            procurement = get_procurement_func(**kwargs)

            if is_admin():
                return view_func(*args, **kwargs)

            user_su_id = getattr(current_user, "service_unit_id", None)
            if not user_su_id or getattr(procurement, "service_unit_id", None) != user_su_id:
                return _forbidden()

            return view_func(*args, **kwargs)

        return wrapper

    return decorator


def procurement_edit_required(get_procurement_func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator factory: EDIT permission for a procurement.

    Admin: always allowed.
    Non-admin: must belong to same ServiceUnit AND be manager/deputy.
    """
    def decorator(view_func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view_func)
        def wrapper(*args: Any, **kwargs: Any):
            procurement = get_procurement_func(**kwargs)

            if is_admin():
                return view_func(*args, **kwargs)

            user_su_id = getattr(current_user, "service_unit_id", None)
            if not user_su_id or getattr(procurement, "service_unit_id", None) != user_su_id:
                return _forbidden()

            if not is_manager_or_deputy():
                return _forbidden()

            return view_func(*args, **kwargs)

        return wrapper

    return decorator


# ---------------------------------------------------------------------
# NEW: Organizational structure decorators
# ---------------------------------------------------------------------
def org_manage_required(view_func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator: admin OR manager/deputy.

    Use for org-management pages (Personnel/Directories/Departments/Setup).
    Route must still enforce ServiceUnit scope server-side (see ensure_manage_service_unit_or_403).
    """
    @wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any):
        if not current_user.is_authenticated:
            return _forbidden()
        if not (is_admin() or is_manager_or_deputy()):
            return _forbidden()
        return view_func(*args, **kwargs)

    return wrapper