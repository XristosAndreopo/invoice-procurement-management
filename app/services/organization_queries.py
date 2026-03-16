"""
app/services/organization_queries.py

Organization query and lookup helpers.

PURPOSE
-------
This module contains organization-related query helpers only.

It is responsible for:
- dropdown data loaders for ServiceUnit / Directory / Department
- active Personnel lookup for a ServiceUnit
- active Personnel id-set generation for validation support
- controlled free-text ServiceUnit matching for import flows

WHY THIS FILE EXISTS
--------------------
The previous `app/services/organization_service.py` mixed:
- dropdown/query access
- structural validation rules
- scope/security guards

That made one service file responsible for multiple concerns.

This module isolates the query and lookup side so that:
- organization dropdown behavior is easier to locate
- list and import lookups stay reusable
- routes can consume query helpers without pulling in validation/security code

ARCHITECTURAL BOUNDARY
----------------------
This module MAY:
- query ORM rows
- return lists of ORM entities
- return id sets derived from database rows
- perform controlled fuzzy-ish matching for import support

This module must NOT:
- abort with 403
- replace route/service authorization
- mutate organizational structure
- flash / redirect / render templates

SECURITY NOTE
-------------
`match_service_unit_from_text()` is intended for controlled import scenarios.
It is not a security primitive and must never replace explicit server-side
scope validation.
"""

from __future__ import annotations

from flask_login import current_user
from sqlalchemy import func

from ..models import Department, Directory, Personnel, ServiceUnit


def service_units_for_dropdown() -> list[ServiceUnit]:
    """
    Return ServiceUnits visible in current admin/manager dropdown flows.

    RETURNS
    -------
    list[ServiceUnit]
        - admin: all ServiceUnits
        - non-admin: only current_user.service_unit_id, if assigned

    WHY THIS HELPER EXISTS
    ----------------------
    Organization forms and structure screens should expose only the ServiceUnit
    choices that the current user is allowed to operate on.
    """
    if getattr(current_user, "is_admin", False):
        return ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()

    service_unit_id = getattr(current_user, "service_unit_id", None)
    if not service_unit_id:
        return []

    unit = ServiceUnit.query.get(service_unit_id)
    return [unit] if unit else []


def directories_for_dropdown(service_unit_id: int | None = None) -> list[Directory]:
    """
    Return Directory rows for dropdown use.

    PARAMETERS
    ----------
    service_unit_id:
        Optional ServiceUnit filter.

    RETURNS
    -------
    list[Directory]
        Directories ordered by service unit then name, or only by name when a
        specific ServiceUnit is requested.

    WHY THIS HELPER EXISTS
    ----------------------
    Personnel and organization forms need reusable Directory dropdown data with
    optional ServiceUnit scoping.
    """
    query = Directory.query

    if service_unit_id is not None:
        query = query.filter(Directory.service_unit_id == service_unit_id)
        return query.order_by(Directory.name.asc()).all()

    return query.order_by(Directory.service_unit_id.asc(), Directory.name.asc()).all()


def departments_for_dropdown(
    service_unit_id: int | None = None,
    directory_id: int | None = None,
) -> list[Department]:
    """
    Return Department rows for dropdown use.

    PARAMETERS
    ----------
    service_unit_id:
        Optional ServiceUnit filter.
    directory_id:
        Optional Directory filter.

    RETURNS
    -------
    list[Department]
        Departments ordered in a stable, UI-friendly way.

    WHY THIS HELPER EXISTS
    ----------------------
    Personnel and structure forms often need Department options constrained by:
    - service unit
    - directory
    - or both
    """
    query = Department.query

    if service_unit_id is not None:
        query = query.filter(Department.service_unit_id == service_unit_id)

    if directory_id is not None:
        query = query.filter(Department.directory_id == directory_id)

    return query.order_by(
        Department.directory_id.asc(),
        Department.name.asc(),
    ).all()


def active_personnel_for_service_unit(service_unit_id: int) -> list[Personnel]:
    """
    Return active Personnel for a specific ServiceUnit.

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit primary key.

    RETURNS
    -------
    list[Personnel]
        Active personnel ordered by:
        1. last_name
        2. first_name

    WHY THIS HELPER EXISTS
    ----------------------
    Used repeatedly for:
    - handler dropdowns
    - committee assignments
    - directory/department role assignments
    - organization setup pages
    """
    return (
        Personnel.query.filter_by(is_active=True, service_unit_id=service_unit_id)
        .order_by(Personnel.last_name.asc(), Personnel.first_name.asc())
        .all()
    )


def active_personnel_ids_for_service_unit(service_unit_id: int) -> set[int]:
    """
    Return the set of active Personnel ids for a ServiceUnit.

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit primary key.

    RETURNS
    -------
    set[int]
        Active Personnel ids.

    WHY THIS HELPER EXISTS
    ----------------------
    Membership validation often needs quick server-side set membership checks.
    """
    return {person.id for person in active_personnel_for_service_unit(service_unit_id)}


def match_service_unit_from_text(service_value: str) -> ServiceUnit | None:
    """
    Resolve a ServiceUnit from controlled free text.

    PARAMETERS
    ----------
    service_value:
        Raw text value, typically from imported Excel content.

    RETURNS
    -------
    ServiceUnit | None
        Matching ServiceUnit row or None.

    MATCHING STRATEGY
    -----------------
    Case-insensitive search in this priority order:
    1. ServiceUnit.code
    2. ServiceUnit.short_name
    3. ServiceUnit.description

    WHY THIS HELPER EXISTS
    ----------------------
    Import files may refer to a ServiceUnit in different textual forms.
    This helper keeps matching deterministic and centralized.

    IMPORTANT
    ---------
    This helper is intended for controlled import scenarios only.
    It must not be used as a substitute for authorization or strict id-based
    validation.
    """
    value = (service_value or "").strip()
    if not value:
        return None

    by_code = (
        ServiceUnit.query
        .filter(ServiceUnit.code.isnot(None))
        .filter(func.lower(ServiceUnit.code) == value.lower())
        .first()
    )
    if by_code:
        return by_code

    by_short_name = (
        ServiceUnit.query
        .filter(ServiceUnit.short_name.isnot(None))
        .filter(func.lower(ServiceUnit.short_name) == value.lower())
        .first()
    )
    if by_short_name:
        return by_short_name

    by_description = (
        ServiceUnit.query
        .filter(ServiceUnit.description.isnot(None))
        .filter(func.lower(ServiceUnit.description) == value.lower())
        .first()
    )
    if by_description:
        return by_description

    return None


__all__ = [
    "service_units_for_dropdown",
    "directories_for_dropdown",
    "departments_for_dropdown",
    "active_personnel_for_service_unit",
    "active_personnel_ids_for_service_unit",
    "match_service_unit_from_text",
]