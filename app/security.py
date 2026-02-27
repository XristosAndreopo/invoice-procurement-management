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

This module also provides a global safety net:
- viewer_readonly_guard() blocks POST/PUT/PATCH/DELETE for Viewers.
  Wire it via app.before_request in app factory.

IMPORTANT:
- Decorators must preserve wrapped function metadata to avoid Flask endpoint collisions.
  We use functools.wraps everywhere.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Optional, Tuple

from flask import render_template, request
from flask_login import current_user

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _forbidden() -> Tuple[str, int]:
    """Render a consistent 403 page."""
    return render_template("errors/403.html"), 403


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