"""
app/services/settings/committees.py

Procurement committee settings page/use-case helpers.

PURPOSE
-------
This module extracts non-HTTP orchestration from:

- /settings/committees

RESPONSIBILITIES
----------------
This module handles:
- page-context assembly for the committees screen
- ServiceUnit scope resolution for admin vs manager/deputy flows
- committee CRUD validation and persistence
- committee-member validation against active personnel in the same service unit

SECURITY MODEL
--------------
- Admin may operate on any selected ServiceUnit.
- Non-admin manager/deputy is forced server-side to their own ServiceUnit.
- Reusable scope guards remain in `app/security/settings_guards.py`.

DESIGN
------
- function-first
- one focused use-case module for one settings sub-area
- no generic repository abstraction
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flask_login import current_user

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import Personnel, ProcurementCommittee, ServiceUnit
from ..shared.operation_results import FlashMessage, OperationResult
from ..shared.parsing import parse_optional_int
from ...security.settings_guards import ensure_committee_scope_or_403


def _active_personnel_for_dropdown(service_unit_id: int | None = None) -> list[Personnel]:
    """
    Return active personnel for dropdown usage.

    PARAMETERS
    ----------
    service_unit_id:
        Optional ServiceUnit filter.

    RETURNS
    -------
    list[Personnel]
        Active Personnel ordered by last_name / first_name, either globally or
        scoped to one ServiceUnit.
    """
    query = Personnel.query.filter_by(is_active=True)

    if service_unit_id is not None:
        query = query.filter_by(service_unit_id=service_unit_id)

    return query.order_by(Personnel.last_name.asc(), Personnel.first_name.asc()).all()


def build_committees_page_context(args: Mapping[str, object]) -> dict[str, Any]:
    """
    Build template context for the committees page.

    PARAMETERS
    ----------
    args:
        Query-string mapping, typically request.args.

    RETURNS
    -------
    dict[str, Any]
        Template context for the committees page.
    """
    if current_user.is_admin:
        scope_service_unit_id = parse_optional_int((args.get("service_unit_id") or "").strip())
    else:
        scope_service_unit_id = current_user.service_unit_id

    service_units = ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()
    committees_list: list[ProcurementCommittee] = []
    personnel_list: list[Personnel] = []

    if scope_service_unit_id:
        ensure_committee_scope_or_403(scope_service_unit_id)
        committees_list = (
            ProcurementCommittee.query
            .filter_by(service_unit_id=scope_service_unit_id)
            .order_by(ProcurementCommittee.description.asc())
            .all()
        )
        personnel_list = _active_personnel_for_dropdown(scope_service_unit_id)

    return {
        "service_units": service_units,
        "committees": committees_list,
        "personnel_list": personnel_list,
        "scope_service_unit_id": scope_service_unit_id,
        "is_admin": current_user.is_admin,
    }


def execute_committee_action(form_data: Mapping[str, object]) -> OperationResult:
    """
    Execute create/update/delete action for a procurement committee.

    PARAMETERS
    ----------
    form_data:
        Submitted form payload.

    RETURNS
    -------
    OperationResult
        Result object. `entity_id` is used here as the redirect scope
        ServiceUnit id for the route.
    """
    service_unit_id = parse_optional_int((form_data.get("service_unit_id") or "").strip())
    if not service_unit_id:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η υπηρεσία είναι υποχρεωτική.", "danger"),),
        )

    ensure_committee_scope_or_403(service_unit_id)

    allowed_ids = {person.id for person in _active_personnel_for_dropdown(service_unit_id)}

    def _validate_member(candidate_id: int | None) -> int | None:
        if candidate_id is None:
            return None
        return candidate_id if candidate_id in allowed_ids else None

    action = (form_data.get("action") or "").strip()

    if action == "create":
        description = (form_data.get("description") or "").strip()
        identity_text = (form_data.get("identity_text") or "").strip() or None
        president_id = _validate_member(parse_optional_int((form_data.get("president_personnel_id") or "").strip()))
        member1_id = _validate_member(parse_optional_int((form_data.get("member1_personnel_id") or "").strip()))
        member2_id = _validate_member(parse_optional_int((form_data.get("member2_personnel_id") or "").strip()))
        is_active = bool(form_data.get("is_active") == "on")

        if not description:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Η περιγραφή είναι υποχρεωτική.", "danger"),),
                entity_id=service_unit_id,
            )

        exists = ProcurementCommittee.query.filter_by(
            service_unit_id=service_unit_id,
            description=description,
        ).first()
        if exists:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Υπάρχει ήδη επιτροπή με αυτή την περιγραφή στην Υπηρεσία.", "danger"),),
                entity_id=service_unit_id,
            )

        committee = ProcurementCommittee(
            service_unit_id=service_unit_id,
            description=description,
            identity_text=identity_text,
            president_personnel_id=president_id,
            member1_personnel_id=member1_id,
            member2_personnel_id=member2_id,
            is_active=is_active,
        )
        db.session.add(committee)
        db.session.flush()
        log_action(committee, "CREATE", after=serialize_model(committee))
        db.session.commit()

        return OperationResult(
            ok=True,
            flashes=(FlashMessage("Η επιτροπή προστέθηκε.", "success"),),
            entity_id=service_unit_id,
        )

    if action == "update":
        committee_id = parse_optional_int((form_data.get("id") or "").strip())
        if committee_id is None:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρη επιτροπή.", "danger"),),
                entity_id=service_unit_id,
            )

        committee = ProcurementCommittee.query.get_or_404(committee_id)
        if committee.service_unit_id != service_unit_id:
            from flask import abort
            abort(403)

        before = serialize_model(committee)

        description = (form_data.get("description") or "").strip()
        identity_text = (form_data.get("identity_text") or "").strip() or None
        president_id = _validate_member(parse_optional_int((form_data.get("president_personnel_id") or "").strip()))
        member1_id = _validate_member(parse_optional_int((form_data.get("member1_personnel_id") or "").strip()))
        member2_id = _validate_member(parse_optional_int((form_data.get("member2_personnel_id") or "").strip()))
        is_active = bool(form_data.get("is_active") == "on")

        if not description:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Η περιγραφή είναι υποχρεωτική.", "danger"),),
                entity_id=service_unit_id,
            )

        exists = ProcurementCommittee.query.filter(
            ProcurementCommittee.service_unit_id == service_unit_id,
            ProcurementCommittee.description == description,
            ProcurementCommittee.id != committee.id,
        ).first()
        if exists:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Υπάρχει ήδη άλλη επιτροπή με αυτή την περιγραφή στην Υπηρεσία.", "danger"),),
                entity_id=service_unit_id,
            )

        committee.description = description
        committee.identity_text = identity_text
        committee.president_personnel_id = president_id
        committee.member1_personnel_id = member1_id
        committee.member2_personnel_id = member2_id
        committee.is_active = is_active

        db.session.flush()
        log_action(committee, "UPDATE", before=before, after=serialize_model(committee))
        db.session.commit()

        return OperationResult(
            ok=True,
            flashes=(FlashMessage("Η επιτροπή ενημερώθηκε.", "success"),),
            entity_id=service_unit_id,
        )

    if action == "delete":
        committee_id = parse_optional_int((form_data.get("id") or "").strip())
        if committee_id is None:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρη επιτροπή.", "danger"),),
                entity_id=service_unit_id,
            )

        committee = ProcurementCommittee.query.get_or_404(committee_id)
        if committee.service_unit_id != service_unit_id:
            from flask import abort
            abort(403)

        before = serialize_model(committee)
        db.session.delete(committee)
        db.session.flush()
        log_action(committee, "DELETE", before=before, after=None)
        db.session.commit()

        return OperationResult(
            ok=True,
            flashes=(FlashMessage("Η επιτροπή διαγράφηκε.", "success"),),
            entity_id=service_unit_id,
        )

    return OperationResult(
        ok=False,
        flashes=(FlashMessage("Μη έγκυρη ενέργεια.", "danger"),),
        entity_id=service_unit_id,
    )


__all__ = [
    "build_committees_page_context",
    "execute_committee_action",
]

