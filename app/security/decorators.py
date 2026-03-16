"""
app/security_decorators.py

Reusable authorization decorators for the Invoice / Procurement Management
System.

PURPOSE
-------
This module contains route decorators that enforce access rules by reusing the
canonical authorization predicates from `app.permissions`.

WHY THIS FILE EXISTS
--------------------
Decorators are not the same thing as permission predicates.

- Predicates answer: "is this action allowed?"
- Decorators answer: "how do we enforce that rule on a Flask route?"

Separating them makes both sides cleaner:
- predicates become reusable from services or non-route code
- decorators remain thin wrappers around stable rules
- route modules stay smaller and easier to scan

IMPORTANT
---------
Decorators must preserve wrapped function metadata, so `functools.wraps`
is used everywhere.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from flask_login import current_user

from .permissions import (
    can_edit_procurement,
    can_manage_service_unit,
    can_view_procurement,
    is_admin,
    is_manager_or_deputy,
)
from . import _forbidden

F = TypeVar("F", bound=Callable[..., Any])


def admin_required(view_func: F) -> F:
    """
    Decorator for admin-only routes.

    PARAMETERS
    ----------
    view_func:
        Flask view function.

    RETURNS
    -------
    callable
        Wrapped view function that denies access for non-admin users.
    """
    @wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any):
        if not is_admin():
            return _forbidden()
        return view_func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def manager_required(view_func: F) -> F:
    """
    Decorator for routes accessible to:
    - admin
    - manager
    - deputy

    TYPICAL USE
    -----------
    Pages such as procurement committees or unit-level management actions.
    """
    @wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any):
        if not current_user.is_authenticated:
            return _forbidden()

        if not (is_admin() or is_manager_or_deputy()):
            return _forbidden()

        return view_func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def procurement_access_required(get_procurement_func: Callable[..., Any]) -> Callable[[F], F]:
    """
    Decorator factory for procurement VIEW access.

    PARAMETERS
    ----------
    get_procurement_func:
        Callable that retrieves the procurement from route kwargs.

    EXAMPLE
    -------
        @procurement_access_required(
            lambda procurement_id: Procurement.query.get_or_404(procurement_id)
        )
        def view(procurement_id): ...
    """
    def decorator(view_func: F) -> F:
        @wraps(view_func)
        def wrapper(*args: Any, **kwargs: Any):
            procurement = get_procurement_func(**kwargs)

            if not can_view_procurement(procurement):
                return _forbidden()

            return view_func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def procurement_edit_required(get_procurement_func: Callable[..., Any]) -> Callable[[F], F]:
    """
    Decorator factory for procurement EDIT access.

    PARAMETERS
    ----------
    get_procurement_func:
        Callable that retrieves the procurement from route kwargs.

    RULES
    -----
    - Admin: allowed
    - Same ServiceUnit + manager/deputy: allowed
    - Otherwise: denied
    """
    def decorator(view_func: F) -> F:
        @wraps(view_func)
        def wrapper(*args: Any, **kwargs: Any):
            procurement = get_procurement_func(**kwargs)

            if not can_edit_procurement(procurement):
                return _forbidden()

            return view_func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def org_manage_required(view_func: F) -> F:
    """
    Decorator for organization-management pages.

    ALLOWS
    ------
    - admin
    - manager
    - deputy

    IMPORTANT
    ---------
    This decorator alone is not enough for scoped organization actions.
    Routes must still enforce ServiceUnit scope with:

        ensure_manage_service_unit_or_403(service_unit_id)
    """
    @wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any):
        if not current_user.is_authenticated:
            return _forbidden()

        if not (is_admin() or is_manager_or_deputy()):
            return _forbidden()

        return view_func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def ensure_manage_service_unit_or_403(service_unit_id: int | None) -> None:
    """
    Abort the current request with a standard 403 response when the current user
    may not manage the given ServiceUnit.

    USE CASES
    ---------
    Use this helper inside routes for:
    - Directories CRUD
    - Departments CRUD
    - Personnel management
    - Organizational setup actions

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit id that the route is about to mutate or manage.
    """
    if not can_manage_service_unit(service_unit_id):
        from . import _abort_or_render_forbidden
        _abort_or_render_forbidden()