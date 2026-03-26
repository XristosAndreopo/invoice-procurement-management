"""
app/services/procurement/queries.py

Procurement query helpers.

PURPOSE
-------
This module contains query-oriented procurement helpers only.

It is responsible for:
- loading a Procurement by id
- building the base procurements query with service isolation
- applying eager loading for list pages
- applying canonical serial-number ordering
- applying list/search filters from request-like args

WHY THIS FILE EXISTS
--------------------
The previous `app/services/procurement_service.py` mixed:
- query construction
- reference-data lookups
- workflow predicates
- presentation/download helpers

This module isolates the query side so that:
- procurement list/query behavior is easier to find
- routes can stay thinner
- query helpers become easier to test independently
- non-query helpers can evolve separately without bloating one file

ARCHITECTURAL BOUNDARY
----------------------
This module MAY:
- return SQLAlchemy query objects
- apply joins, filters, eager loads, and ordering
- load ORM entities for service / route usage

This module must NOT:
- flash messages
- redirect users
- render templates
- decide UI behavior
- generate download filenames
- replace route-level authorization

SECURITY MODEL
--------------
This module supports route/service authorization but does not replace it.

Important assumptions:
- admin users may access all procurements
- non-admin users are service-isolated by Procurement.service_unit_id
- caller still owns action-level permission checks

PERFORMANCE INSTRUMENTATION
---------------------------
This module includes lightweight request-local timing/mark instrumentation for:
- procurement loader timing
- base query construction timing
- eager-load option application timing
- ordering helper timing
- list-filter application timing

IMPORTANT
---------
The instrumentation is observability-only:
- no authorization changes
- no query semantics changes
- no filtering behavior changes
"""

from __future__ import annotations

import time
from collections.abc import Mapping

from flask import abort, g, has_request_context
from flask_login import current_user
from sqlalchemy import Integer, and_, case, func
from sqlalchemy.orm import joinedload

from ...extensions import db
from ...models import Procurement, ProcurementSupplier, Supplier
from ..shared.parsing import normalize_digits, parse_optional_int


def _current_request_timing():
    """
    Return the active request timing collector when available.

    RETURNS
    -------
    RequestInstrumentation | None
        The request-local collector stored on Flask's `g`, or None when
        instrumentation is unavailable.

    WHY THIS HELPER EXISTS
    ----------------------
    Query helpers must remain safe to use even outside a fully instrumented
    request path.
    """
    if not has_request_context():
        return None
    return getattr(g, "request_timing", None)


def load_procurement(procurement_id: int, **_: object) -> Procurement:
    """
    Load a Procurement row by primary key or abort with 404.

    PARAMETERS
    ----------
    procurement_id:
        Target Procurement primary key.

    RETURNS
    -------
    Procurement
        The matching procurement ORM row.

    WHY THIS HELPER EXISTS
    ----------------------
    Decorator factories such as procurement_access_required() often want a
    small loader function with a stable signature. Centralizing it here keeps
    route files smaller and avoids repeated boilerplate.
    """
    request_timing = _current_request_timing()
    started_at = time.perf_counter()

    procurement = db.session.get(Procurement, procurement_id)

    if request_timing is not None:
        request_timing.add_timing(
            "procurement_query.load_procurement",
            round((time.perf_counter() - started_at) * 1000.0, 2),
        )
        request_timing.mark("load_procurement_id", procurement_id)
        request_timing.mark("load_procurement_found", procurement is not None)

    if procurement is None:
        abort(404)

    return procurement


def base_procurements_query():
    """
    Return the canonical base Procurement query with service isolation applied.

    RETURNS
    -------
    SQLAlchemy query
        - admin users: all procurements
        - non-admin users: only procurements of current_user.service_unit_id

    SECURITY RATIONALE
    ------------------
    Non-admin users must not see procurements belonging to another service
    unit. This helper provides the canonical starting point for procurement
    list pages and procurement searches.
    """
    request_timing = _current_request_timing()
    started_at = time.perf_counter()

    if current_user.is_admin:
        query = Procurement.query
        scope = "admin_all"
    else:
        query = Procurement.query.filter(
            Procurement.service_unit_id == current_user.service_unit_id
        )
        scope = "service_scoped"

    if request_timing is not None:
        request_timing.add_timing(
            "procurement_query.base_procurements_query",
            round((time.perf_counter() - started_at) * 1000.0, 2),
        )
        request_timing.mark("procurement_query_scope", scope)
        request_timing.mark(
            "procurement_query_service_unit_id",
            None if current_user.is_admin else current_user.service_unit_id,
        )

    return query


def with_list_eagerloads(query):
    """
    Apply eager loading commonly needed by procurement list pages.

    PARAMETERS
    ----------
    query:
        Base procurement query.

    RETURNS
    -------
    SQLAlchemy query
        Query with joinedload options applied.

    WHY THIS HELPER EXISTS
    ----------------------
    Procurement list pages often display:
    - service unit
    - handler personnel
    - winner supplier

    Without eager loading, list rendering may trigger N+1 query behavior.
    """
    request_timing = _current_request_timing()
    started_at = time.perf_counter()

    query = query.options(
        joinedload(Procurement.service_unit),
        joinedload(Procurement.handler_personnel),
        joinedload(Procurement.supplies_links).joinedload(ProcurementSupplier.supplier),
    )

    if request_timing is not None:
        request_timing.add_timing(
            "procurement_query.with_list_eagerloads",
            round((time.perf_counter() - started_at) * 1000.0, 2),
        )

    return query


def order_by_serial_no(query):
    """
    Apply numeric-first ordering for Procurement.serial_no.

    PARAMETERS
    ----------
    query:
        Procurement query object.

    RETURNS
    -------
    SQLAlchemy query
        Ordered query.

    ORDERING STRATEGY
    -----------------
    1. Purely numeric serial numbers first
    2. Numeric values sorted numerically
    3. Non-numeric values after numeric ones
    4. Final tie-breaker by lexicographic serial value and Procurement.id

    WHY THIS HELPER EXISTS
    ----------------------
    Plain lexicographic sorting would produce undesirable ordering like:
    1, 10, 11, 2, 3

    NOTES
    -----
    This implementation intentionally remains SQLite-friendly.
    """
    request_timing = _current_request_timing()
    started_at = time.perf_counter()

    serial = func.coalesce(Procurement.serial_no, "")
    is_numeric = serial.op("GLOB")("[0-9]+")
    numeric_value = func.cast(serial, Integer)

    query = query.order_by(
        case((is_numeric, 0), else_=1),
        case((is_numeric, numeric_value), else_=None),
        serial.asc(),
        Procurement.id.asc(),
    )

    if request_timing is not None:
        request_timing.add_timing(
            "procurement_query.order_by_serial_no",
            round((time.perf_counter() - started_at) * 1000.0, 2),
        )

    return query


def apply_list_filters(query, request_args: Mapping[str, object]):
    """
    Apply procurement list filters from request-like args.

    PARAMETERS
    ----------
    query:
        Base SQLAlchemy procurement query.
    request_args:
        Typically Flask `request.args`, or any mapping with equivalent
        string-key access.

    RETURNS
    -------
    SQLAlchemy query
        Filtered query.

    SUPPORTED FILTERS
    -----------------
    - service_unit_id (admin only)
    - serial_no
    - description
    - ale
    - hop_preapproval
    - hop_approval
    - aay
    - status
    - stage
    - winner supplier AFM
    - winner supplier name

    IMPORTANT
    ---------
    This helper only applies filtering logic.
    It does not replace authorization logic or submitted-form validation.
    """
    request_timing = _current_request_timing()
    started_at = time.perf_counter()
    applied_filters: list[str] = []

    service_unit_id = parse_optional_int(request_args.get("service_unit_id"))
    if service_unit_id and current_user.is_admin:
        query = query.filter(Procurement.service_unit_id == service_unit_id)
        applied_filters.append("service_unit_id")

    serial_no = (request_args.get("serial_no") or "").strip()
    if serial_no:
        query = query.filter(
            func.coalesce(Procurement.serial_no, "").ilike(f"%{serial_no}%")
        )
        applied_filters.append("serial_no")

    description = (request_args.get("description") or "").strip()
    if description:
        query = query.filter(
            func.coalesce(Procurement.description, "").ilike(f"%{description}%")
        )
        applied_filters.append("description")

    ale = (request_args.get("ale") or "").strip()
    if ale:
        query = query.filter(func.coalesce(Procurement.ale, "").ilike(f"%{ale}%"))
        applied_filters.append("ale")

    hop_preapproval = (request_args.get("hop_preapproval") or "").strip()
    if hop_preapproval:
        query = query.filter(
            func.coalesce(Procurement.hop_preapproval, "").ilike(f"%{hop_preapproval}%")
        )
        applied_filters.append("hop_preapproval")

    hop_approval = (request_args.get("hop_approval") or "").strip()
    if hop_approval:
        query = query.filter(
            func.coalesce(Procurement.hop_approval, "").ilike(f"%{hop_approval}%")
        )
        applied_filters.append("hop_approval")

    aay = (request_args.get("aay") or "").strip()
    if aay:
        query = query.filter(func.coalesce(Procurement.aay, "").ilike(f"%{aay}%"))
        applied_filters.append("aay")

    status = (request_args.get("status") or "").strip()
    if status:
        query = query.filter(Procurement.status == status)
        applied_filters.append("status")

    stage = (request_args.get("stage") or "").strip()
    if stage:
        query = query.filter(Procurement.stage == stage)
        applied_filters.append("stage")

    supplier_afm = normalize_digits(request_args.get("supplier_afm"))
    supplier_name = (request_args.get("supplier_name") or "").strip()

    if supplier_afm or supplier_name:
        query = query.outerjoin(
            ProcurementSupplier,
            and_(
                ProcurementSupplier.procurement_id == Procurement.id,
                ProcurementSupplier.is_winner.is_(True),
            ),
        ).outerjoin(Supplier, Supplier.id == ProcurementSupplier.supplier_id)

        if supplier_afm:
            query = query.filter(
                func.coalesce(Supplier.afm, "").ilike(f"%{supplier_afm}%")
            )
            applied_filters.append("supplier_afm")

        if supplier_name:
            query = query.filter(
                func.coalesce(Supplier.name, "").ilike(f"%{supplier_name}%")
            )
            applied_filters.append("supplier_name")

        query = query.distinct()
        applied_filters.append("winner_supplier_join")

    if request_timing is not None:
        request_timing.add_timing(
            "procurement_query.apply_list_filters",
            round((time.perf_counter() - started_at) * 1000.0, 2),
        )
        request_timing.mark("procurement_filters_count", len(applied_filters))
        request_timing.mark("procurement_filters_applied", applied_filters)

    return query


__all__ = [
    "load_procurement",
    "base_procurements_query",
    "with_list_eagerloads",
    "order_by_serial_no",
    "apply_list_filters",
]