"""
app/security/settings_guards.py

Settings-specific reusable scope guards.

PURPOSE
-------
This module centralizes reusable authorization checks that were previously
embedded directly inside `app/blueprints/settings/routes.py`.

WHY THIS FILE EXISTS
--------------------
The current settings blueprint contains two scope checks that are clearly not
HTTP-only concerns:

- committee-management scope enforcement
- legacy service-unit structure redirect scope enforcement

Those checks are reused business/security rules about *who may operate on which
ServiceUnit*. They do not belong inside route handlers.

ARCHITECTURAL BOUNDARY
----------------------
This module MAY:
- inspect the authenticated user
- enforce reusable service-unit scope rules
- abort with 403 when access is not allowed

This module MUST NOT:
- read request.form / request.args directly
- query unrelated presentation data
- render templates
- flash messages
- mutate application state

SECURITY PRINCIPLES
-------------------
- UI is never trusted.
- Admin may operate globally where explicitly allowed.
- Non-admin access is constrained to the user's own ServiceUnit.
- Route decorators remain useful, but they do not replace deeper scope checks.
"""

from __future__ import annotations

from flask import abort
from flask_login import current_user


def ensure_committee_scope_or_403(service_unit_id: int) -> None:
    """
    Enforce committee-management scope.

    RULES
    -----
    - admin: may manage committees for any service unit
    - non-admin:
      * must belong to the same service unit
      * must pass current_user.can_manage()

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit primary key for the committee operation.

    RAISES
    ------
    werkzeug.exceptions.Forbidden
        When the current user is outside the allowed scope.
    """
    if current_user.is_admin:
        return

    if not current_user.service_unit_id or current_user.service_unit_id != service_unit_id:
        abort(403)

    if not current_user.can_manage():
        abort(403)


def ensure_settings_structure_scope_or_403(service_unit_id: int) -> None:
    """
    Enforce service-unit structure access for the legacy compatibility redirect.

    RULES
    -----
    - admin: may access any service unit
    - manager/deputy:
      * only their own service unit
      * current_user.can_manage() must be True

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit primary key for the redirect target.

    RAISES
    ------
    werkzeug.exceptions.Forbidden
        When the current user is outside the allowed scope.
    """
    if current_user.is_admin:
        return

    if not current_user.service_unit_id or current_user.service_unit_id != service_unit_id:
        abort(403)

    if not current_user.can_manage():
        abort(403)


__all__ = [
    "ensure_committee_scope_or_403",
    "ensure_settings_structure_scope_or_403",
]

