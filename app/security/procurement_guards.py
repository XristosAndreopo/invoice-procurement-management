"""
app/security/procurement_guards.py

Focused procurement-specific authorization helpers.

PURPOSE
-------
This module contains reusable procurement authorization predicates that are
small enough not to justify decorator factories, but important enough not to
remain duplicated inside route files.

CURRENT SCOPE
-------------
At this stage the module provides a single focused guard:

- can_mutate_procurement(...)

WHY THIS FILE EXISTS
--------------------
The procurement blueprint previously contained a route-local helper for
mutation authorization. Moving that helper here improves:

- module boundaries
- reuse across procurement routes
- consistency of mutation checks
- route thinness

ARCHITECTURAL INTENT
--------------------
This module is intentionally small and function-first.

It does NOT:
- replace route decorators
- replace procurement_access_required(...)
- replace procurement_edit_required(...)

It only provides a reusable predicate for mutation capability checks.
"""

from __future__ import annotations

from ..models import Procurement, User


def can_mutate_procurement(user: User, procurement: Procurement) -> bool:
    """
    Return True only if the given user may mutate the given procurement.

    RULES
    -----
    - admin: always allowed
    - non-admin: must be manager/deputy AND same service unit

    PARAMETERS
    ----------
    user:
        Current authenticated user.
    procurement:
        Target procurement row.

    RETURNS
    -------
    bool
        True if mutation is allowed, else False.

    NOTES
    -----
    This helper assumes the caller has already resolved both:
    - authenticated user
    - target procurement

    Route decorators still remain the primary access-control boundary.
    """
    if user.is_admin:
        return True

    can_manage = getattr(user, "can_manage", None)
    if not callable(can_manage) or not can_manage():
        return False

    return bool(
        user.service_unit_id
        and procurement.service_unit_id
        and int(user.service_unit_id) == int(procurement.service_unit_id)
    )