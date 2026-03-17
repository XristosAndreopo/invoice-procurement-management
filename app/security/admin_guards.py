"""
app/security/admin_guards.py

Reusable authorization helpers specific to admin/organization management flows.

PURPOSE
-------
This module centralizes route-level authorization rules that are specific to
the admin blueprint's organization/personnel workflows.

WHY THIS FILE EXISTS
--------------------
Previously, `app/blueprints/admin/routes.py` contained local decorators and
scope checks such as:
- admin OR manager-only access
- manager-scoped personnel edit checks
- service-unit scope enforcement for organization setup

Those checks are authorization concerns, not route orchestration concerns.

Moving them here keeps route files smaller and makes the rules reusable from
other blueprints if needed later.

DESIGN INTENT
-------------
- function-first
- small explicit guards
- no abstract authorization framework
- no route rendering here

BOUNDARY
--------
This module MAY:
- define decorators
- enforce 403-style scope checks
- inspect current_user

This module MUST NOT:
- flash messages
- redirect users
- query template context
- perform business mutations
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from flask import abort
from flask_login import current_user

from ..models import Personnel

F = TypeVar("F", bound=Callable[..., Any])


def is_admin_or_manager() -> bool:
    """
    Return True for:
    - authenticated admin
    - authenticated ServiceUnit manager

    IMPORTANT
    ---------
    Deputy users are intentionally excluded from this rule, because the admin
    organization/personnel screens were explicitly described as manager-only
    for non-admin users.
    """
    if not current_user.is_authenticated:
        return False

    if getattr(current_user, "is_admin", False):
        return True

    is_mgr = getattr(current_user, "is_manager", None)
    return bool(callable(is_mgr) and is_mgr())


def admin_or_manager_required(view_func: F) -> F:
    """
    Decorator for routes accessible to:
    - admin
    - ServiceUnit manager

    EXCLUDED
    --------
    - deputy
    - viewer
    - anonymous

    RETURNS
    -------
    callable
        Wrapped Flask view function.
    """
    @wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any):
        if not is_admin_or_manager():
            abort(403)
        return view_func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def ensure_personnel_manage_scope_or_403(person: Personnel) -> None:
    """
    Enforce personnel edit/view mutation scope for the admin blueprint.

    RULES
    -----
    - admin: may access any Personnel
    - manager: only Personnel of their own ServiceUnit

    PARAMETERS
    ----------
    person:
        Target Personnel ORM entity.

    RAISES
    ------
    403
        When the current user is outside the allowed scope.
    """
    if getattr(current_user, "is_admin", False):
        return

    scope_service_unit_id = getattr(current_user, "service_unit_id", None)
    if not scope_service_unit_id or person.service_unit_id != scope_service_unit_id:
        abort(403)


def ensure_organization_service_unit_scope_or_403(service_unit_id: int | None) -> None:
    """
    Enforce organization-management scope for a target ServiceUnit.

    RULES
    -----
    - admin: any ServiceUnit allowed
    - manager: only their own ServiceUnit allowed

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit id.

    RAISES
    ------
    403
        When the current user is outside the allowed scope.
    """
    if service_unit_id is None:
        abort(403)

    if getattr(current_user, "is_admin", False):
        return

    scope_service_unit_id = getattr(current_user, "service_unit_id", None)
    if not scope_service_unit_id or service_unit_id != scope_service_unit_id:
        abort(403)


__all__ = [
    "is_admin_or_manager",
    "admin_or_manager_required",
    "ensure_personnel_manage_scope_or_403",
    "ensure_organization_service_unit_scope_or_403",
]

