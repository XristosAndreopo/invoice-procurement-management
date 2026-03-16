"""
app/services/organization_validation.py

Organization structural validation helpers.

PURPOSE
-------
This module contains pure validation helpers for organizational structure.

It is responsible for:
- validating that a ServiceUnit exists when required
- validating Directory -> ServiceUnit ownership
- validating Department -> Directory -> ServiceUnit ownership

WHY THIS FILE EXISTS
--------------------
The previous organization service module mixed:
- query/dropdown loading
- structural validation
- scope/security enforcement

This file isolates the validation side so that:
- structural consistency rules live in one place
- routes can validate posted ids without duplicating rules
- validation helpers remain side-effect-free and easy to test

ARCHITECTURAL BOUNDARY
----------------------
This module MAY:
- query ORM rows to validate ownership/existence
- return True/False validation results

This module must NOT:
- abort(403)
- flash messages
- read request.form / request.args directly
- mutate DB state
"""

from __future__ import annotations

from ..extensions import db
from ..models import Department, Directory, ServiceUnit


def validate_service_unit_required(service_unit_id: int | None) -> bool:
    """
    Validate that a ServiceUnit id is present and exists.

    PARAMETERS
    ----------
    service_unit_id:
        Candidate ServiceUnit primary key.

    RETURNS
    -------
    bool
        True only when service_unit_id is present and the ServiceUnit exists.

    WHY THIS HELPER EXISTS
    ----------------------
    Personnel and organization mutations require a valid ServiceUnit and must
    not trust client-side dropdown restrictions.
    """
    if service_unit_id is None:
        return False

    return db.session.get(ServiceUnit, service_unit_id) is not None


def validate_directory_for_service_unit(
    directory_id: int | None,
    service_unit_id: int | None,
) -> bool:
    """
    Validate that a Directory belongs to the selected ServiceUnit.

    PARAMETERS
    ----------
    directory_id:
        Candidate Directory primary key. None is allowed.
    service_unit_id:
        Target ServiceUnit primary key.

    RETURNS
    -------
    bool
        - True when directory_id is None
        - True when the Directory exists and belongs to the ServiceUnit
        - False otherwise

    WHY THIS HELPER EXISTS
    ----------------------
    UI filtering is convenience only. Directory ownership must be enforced
    server-side for every mutation.
    """
    if directory_id is None:
        return True

    directory = db.session.get(Directory, directory_id)
    if not directory:
        return False

    return bool(directory.service_unit_id == service_unit_id)


def validate_department_for_directory_and_service_unit(
    department_id: int | None,
    directory_id: int | None,
    service_unit_id: int | None,
) -> bool:
    """
    Validate that a Department belongs to both the Directory and ServiceUnit.

    PARAMETERS
    ----------
    department_id:
        Candidate Department primary key. None is allowed.
    directory_id:
        Candidate parent Directory primary key.
    service_unit_id:
        Target ServiceUnit primary key.

    RETURNS
    -------
    bool
        - True when department_id is None
        - False when department_id is provided but directory_id is missing
        - True only when the Department exists and matches both ownership links

    WHY THIS HELPER EXISTS
    ----------------------
    Organizational consistency cannot be trusted to the UI and is not fully
    expressible via a single foreign-key constraint.
    """
    if department_id is None:
        return True

    if directory_id is None:
        return False

    department = db.session.get(Department, department_id)
    if not department:
        return False

    return bool(
        department.directory_id == directory_id
        and department.service_unit_id == service_unit_id
    )


__all__ = [
    "validate_service_unit_required",
    "validate_directory_for_service_unit",
    "validate_department_for_directory_and_service_unit",
]