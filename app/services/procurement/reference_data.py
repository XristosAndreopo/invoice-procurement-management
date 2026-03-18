"""
app/services/procurement/reference_data.py

Procurement reference-data and selection helpers.
"""

from __future__ import annotations

from flask_login import current_user
from sqlalchemy.orm import joinedload

from ...extensions import db
from ...models import (
    IncomeTaxRule,
    Personnel,
    PersonnelDepartmentAssignment,
    ProcurementCommittee,
    ServiceUnit,
    WithholdingProfile,
)


def service_units_for_filter() -> list[ServiceUnit]:
    if current_user.is_admin:
        return ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()

    if not current_user.service_unit_id:
        return []

    unit = db.session.get(ServiceUnit, current_user.service_unit_id)
    return [unit] if unit else []


def handler_candidates(service_unit_id: int | None) -> list[PersonnelDepartmentAssignment]:
    """
    Return assignment-based handler candidates for a specific ServiceUnit.

    Each row represents:
    - one person
    - one concrete department
    - one concrete directory

    This allows the dropdown to show:
    ΒΑΘΜΟΣ ΕΙΔΙΚΟΤΗΤΑ ΟΝΟΜΑ ΕΠΩΝΥΜΟ / ΤΜΗΜΑ
    and lets the procurement keep the exact selected organizational context.
    """
    if not service_unit_id:
        return []

    return (
        PersonnelDepartmentAssignment.query.options(
            joinedload(PersonnelDepartmentAssignment.personnel),
            joinedload(PersonnelDepartmentAssignment.directory),
            joinedload(PersonnelDepartmentAssignment.department),
        )
        .join(Personnel, Personnel.id == PersonnelDepartmentAssignment.personnel_id)
        .filter(
            PersonnelDepartmentAssignment.service_unit_id == service_unit_id,
            Personnel.is_active.is_(True),
        )
        .order_by(
            Personnel.last_name.asc(),
            Personnel.first_name.asc(),
            PersonnelDepartmentAssignment.is_primary.desc(),
            PersonnelDepartmentAssignment.id.asc(),
        )
        .all()
    )


def handler_candidate_ids(service_unit_id: int | None) -> set[int]:
    return {assignment.id for assignment in handler_candidates(service_unit_id)}


def committees_for_service_unit(
    service_unit_id: int | None,
) -> list[ProcurementCommittee]:
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
    return (
        IncomeTaxRule.query.filter_by(is_active=True)
        .order_by(IncomeTaxRule.description.asc())
        .all()
    )


def active_withholding_profiles() -> list[WithholdingProfile]:
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