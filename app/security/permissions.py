"""
app/permissions.py

Central authorization predicates for the Invoice / Procurement Management
System.

PURPOSE
-------
This module contains pure-ish authorization helpers and scope predicates that
answer questions such as:

- Is the current user an admin?
- Is the current user a manager or deputy?
- Can the current user view this procurement?
- Can the current user edit this procurement?
- Can the current user manage this ServiceUnit?

WHY THIS FILE EXISTS
--------------------
Previously, `app/security.py` mixed:
- response helpers
- role predicates
- request guards
- decorators

Those are related, but not the same responsibility.

By moving permission predicates here:
- authorization rules become easier to find
- route decorators stay thin
- future services can reuse the same permission checks
- business rules are less likely to drift across route files

SECURITY PRINCIPLES
-------------------
1. The UI is never trusted.
2. Navigation visibility is not authorization.
3. All permission checks are enforced server-side.
4. Non-admin users are isolated to their own ServiceUnit scope.
5. Viewers are read-only except where explicitly allowed.

IMPORTANT
---------
These helpers support authorization but do not replace route-level validation.

For example:
- a user may be allowed to manage a ServiceUnit in general
- but a submitted foreign key must still be validated server-side
"""

from __future__ import annotations

from typing import Any

from flask_login import current_user


def is_admin() -> bool:
    """
    Return True when the current user is an authenticated admin.

    RETURNS
    -------
    bool
        True only for authenticated admin users.

    NOTES
    -----
    We explicitly require authentication instead of trusting only an
    `is_admin` attribute to avoid accidental truthy behavior on anonymous
    user proxies.
    """
    return bool(current_user.is_authenticated and getattr(current_user, "is_admin", False))


def is_manager_or_deputy() -> bool:
    """
    Return True when the current user can manage within their ServiceUnit scope.

    ROLE RULE
    ---------
    This maps to the existing user method `current_user.can_manage()` which
    already expresses the application's manager/deputy capability model.

    RETURNS
    -------
    bool
        True for authenticated manager/deputy-style users.
    """
    if not current_user.is_authenticated:
        return False

    can_manage = getattr(current_user, "can_manage", None)
    return bool(callable(can_manage) and can_manage())


def can_view_procurement(procurement: Any) -> bool:
    """
    Return whether the current user may view a Procurement.

    RULES
    -----
    - admin: always allowed
    - non-admin: procurement must belong to the user's ServiceUnit

    PARAMETERS
    ----------
    procurement:
        Procurement-like object with `service_unit_id`.

    RETURNS
    -------
    bool
        True when the procurement is inside the user's visible scope.
    """
    if procurement is None or not current_user.is_authenticated:
        return False

    if is_admin():
        return True

    return bool(
        current_user.service_unit_id
        and getattr(procurement, "service_unit_id", None)
        and int(current_user.service_unit_id) == int(procurement.service_unit_id)
    )


def can_edit_procurement(procurement: Any) -> bool:
    """
    Return whether the current user may edit a Procurement.

    RULES
    -----
    - admin: always allowed
    - non-admin: must be manager/deputy AND same ServiceUnit

    PARAMETERS
    ----------
    procurement:
        Procurement-like object with `service_unit_id`.

    RETURNS
    -------
    bool
        True when the user may mutate the procurement.
    """
    if procurement is None or not current_user.is_authenticated:
        return False

    if is_admin():
        return True

    if not is_manager_or_deputy():
        return False

    return bool(
        current_user.service_unit_id
        and getattr(procurement, "service_unit_id", None)
        and int(current_user.service_unit_id) == int(procurement.service_unit_id)
    )


def can_manage_service_unit(service_unit_id: int | None) -> bool:
    """
    Return whether the current user may manage the given ServiceUnit.

    RULES
    -----
    - admin: may manage any ServiceUnit
    - manager/deputy: may manage only their own ServiceUnit
    - viewer/anonymous: denied

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit id.

    RETURNS
    -------
    bool
        True when the target ServiceUnit is inside the current user's
        management scope.
    """
    if service_unit_id is None or not current_user.is_authenticated:
        return False

    if is_admin():
        return True

    if not is_manager_or_deputy():
        return False

    return bool(
        current_user.service_unit_id
        and int(current_user.service_unit_id) == int(service_unit_id)
    )

