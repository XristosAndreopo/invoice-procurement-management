"""
app/services/procurement_reference_data.py

Procurement reference-data and selection helpers.

PURPOSE
-------
This module contains procurement-related lookup helpers that return
reference/selection data for forms, filters, and validation support.

It is responsible for:
- visible ServiceUnit choices for procurement filters
- handler candidates for a service unit
- handler candidate id sets for validation
- committee lookup by service unit
- active IncomeTaxRule lookup
- active WithholdingProfile lookup

WHY THIS FILE EXISTS
--------------------
The previous procurement service module mixed:
- procurement queries
- lookup/reference-data access
- workflow predicates
- presentation helpers

This file isolates the reference-data side so that:
- dropdown/lookup logic is centralized
- service-unit-scoped selection rules are explicit
- routes and larger orchestration services can stay smaller

ARCHITECTURAL BOUNDARY
----------------------
This module MAY:
- return lists of ORM rows
- return simple sets of valid ids for validation support
- enforce visibility restrictions for dropdown/filter options

This module must NOT:
- flash or redirect
- read request/form objects directly
- perform route orchestration
- decide UI-only behavior
"""

from __future__ import annotations

from flask_login import current_user

from ..extensions import db
from ..models import (
    IncomeTaxRule,
    Personnel,
    ProcurementCommittee,
    ServiceUnit,
    WithholdingProfile,
)


def service_units_for_filter() -> list[ServiceUnit]:
    """
    Return ServiceUnits visible in procurement list filters.

    RETURNS
    -------
    list[ServiceUnit]
        - admin: all service units
        - non-admin: only the user's own service unit, if assigned

    WHY THIS HELPER EXISTS
    ----------------------
    Procurement list filter dropdowns should reflect the user's actual visible
    scope rather than exposing unrelated service units.
    """
    if current_user.is_admin:
        return ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()

    if not current_user.service_unit_id:
        return []

    unit = db.session.get(ServiceUnit, current_user.service_unit_id)
    return [unit] if unit else []


def handler_candidates(service_unit_id: int | None) -> list[Personnel]:
    """
    Return active handler candidates for a specific ServiceUnit.

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit primary key.

    RETURNS
    -------
    list[Personnel]
        Active personnel rows of that service unit, ordered by surname/name.

    WHY THIS HELPER EXISTS
    ----------------------
    Procurement handler assignment is service-unit-scoped. This helper provides
    the canonical source for route/service dropdowns.
    """
    if not service_unit_id:
        return []

    return (
        Personnel.query.filter_by(is_active=True, service_unit_id=service_unit_id)
        .order_by(Personnel.last_name.asc(), Personnel.first_name.asc())
        .all()
    )


def handler_candidate_ids(service_unit_id: int | None) -> set[int]:
    """
    Return the valid handler Personnel id set for a ServiceUnit.

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit primary key.

    RETURNS
    -------
    set[int]
        Candidate Personnel ids.

    WHY THIS HELPER EXISTS
    ----------------------
    Form validation frequently needs fast membership checks against the valid
    handler pool of a specific service unit.
    """
    return {person.id for person in handler_candidates(service_unit_id)}


def committees_for_service_unit(
    service_unit_id: int | None,
) -> list[ProcurementCommittee]:
    """
    Return active procurement committees for a specific ServiceUnit.

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit primary key.

    RETURNS
    -------
    list[ProcurementCommittee]
        Active committees ordered by description.
    """
    if not service_unit_id:
        return []

    return (
        ProcurementCommittee.query.filter_by(
            service_unit_id=service_unit_id,
            is_active=True,
        )
        .order_by(ProcurementCommittee.description.asc())
        .all()
    )


def active_income_tax_rules() -> list[IncomeTaxRule]:
    """
    Return active IncomeTaxRule rows ordered for selection.

    RETURNS
    -------
    list[IncomeTaxRule]
        Active rules ordered by description.
    """
    return (
        IncomeTaxRule.query.filter_by(is_active=True)
        .order_by(IncomeTaxRule.description.asc())
        .all()
    )


def active_withholding_profiles() -> list[WithholdingProfile]:
    """
    Return active WithholdingProfile rows ordered for selection.

    RETURNS
    -------
    list[WithholdingProfile]
        Active profiles ordered by description.
    """
    return (
        WithholdingProfile.query.filter_by(is_active=True)
        .order_by(WithholdingProfile.description.asc())
        .all()
    )


__all__ = [
    "service_units_for_filter",
    "handler_candidates",
    "handler_candidate_ids",
    "committees_for_service_unit",
    "active_income_tax_rules",
    "active_withholding_profiles",
]