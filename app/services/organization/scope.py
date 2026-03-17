"""
app/services/organization/scope.py

Organization scope and hard-guard helpers.

PURPOSE
-------
This module contains scope helpers and authorization-style hard guards used by
organization-related flows.

It is responsible for:
- resolving the effective ServiceUnit scope for admin/manager list screens
- enforcing admin-or-manager-only access
- enforcing same-ServiceUnit manager scope

WHY THIS FILE EXISTS
--------------------
The previous organization service module mixed:
- query/dropdown loading
- structural validation
- scope/security enforcement

This file isolates the scope/security side so that:
- authorization-adjacent logic is clearly separated
- query and validation modules stay cleaner
- route guards and scoped list flows share one source of truth

IMPORTANT BOUNDARY
------------------
This module supports authorization, but does not replace blueprint decorators,
policy checks, or route-level permission design.

This module MAY:
- inspect current_user
- abort(403) for hard guards
- expose current-user-derived scope

This module must NOT:
- render templates
- flash messages
- read request payloads
- mutate database state
"""

from __future__ import annotations

from flask import abort
from flask_login import current_user


def effective_scope_service_unit_id_for_manager_or_none() -> int | None:
    """
    Return the effective ServiceUnit scope for current admin/manager flows.

    RETURNS
    -------
    int | None
        - None for admin users
        - current_user.service_unit_id for non-admin users

    USE CASE
    --------
    Useful in list views where:
    - admins should see everything
    - managers should be restricted to their own ServiceUnit
    """
    if getattr(current_user, "is_admin", False):
        return None

    return getattr(current_user, "service_unit_id", None)


def ensure_admin_or_manager_only() -> None:
    """
    Hard guard: allow only authenticated admin or manager.

    BEHAVIOR
    --------
    Aborts with HTTP 403 unless current_user is:
    - authenticated
    - admin
    - manager

    IMPORTANT
    ---------
    Deputy is intentionally excluded because some pages are explicitly designed
    for admin or manager only.
    """
    if not current_user.is_authenticated:
        abort(403)

    if getattr(current_user, "is_admin", False):
        return

    is_manager = getattr(current_user, "is_manager", None)
    if callable(is_manager) and is_manager():
        return

    abort(403)


def ensure_manager_scope_or_403(service_unit_id: int | None) -> None:
    """
    Enforce that a non-admin manager acts only within their own ServiceUnit.

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit id of the operation.

    BEHAVIOR
    --------
    - admin: always allowed
    - non-admin:
      * must have a current service_unit_id
      * target service_unit_id must be present
      * both values must match
      * otherwise abort(403)

    WHY THIS HELPER EXISTS
    ----------------------
    This is a core organizational security rule:
    managers must not mutate another ServiceUnit's structure or data.
    """
    if getattr(current_user, "is_admin", False):
        return

    current_service_unit_id = getattr(current_user, "service_unit_id", None)
    if not current_service_unit_id or not service_unit_id:
        abort(403)

    if int(current_service_unit_id) != int(service_unit_id):
        abort(403)


__all__ = [
    "effective_scope_service_unit_id_for_manager_or_none",
    "ensure_admin_or_manager_only",
    "ensure_manager_scope_or_403",
]

