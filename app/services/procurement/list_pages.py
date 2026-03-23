"""
app/services/procurement/list_pages.py

Page-context builders for procurement list routes.

PURPOSE
-------
This module contains focused read-only page services for procurement list
screens.

WHY THIS FILE EXISTS
--------------------
The procurement blueprint contains list routes that should remain limited to:

- decorators
- reading request args
- calling a service / use-case function
- render_template(...)

List-specific query orchestration and page-context assembly belong here
instead of living inline inside route handlers.

ARCHITECTURAL DIRECTION
-----------------------
This module follows the agreed project direction:

- function-first
- no class unless complexity truly justifies it
- no premature abstraction
- no attempt to replace existing lower-level procurement helpers

CURRENT SCOPE
-------------
At this stage the module supports:

- `/procurements/inbox`
- `/procurements/pending-expenses`
- `/procurements/all`

BOUNDARY
--------
This module MAY:
- compose read-only procurement list queries
- apply route-specific list filters
- call existing procurement query helpers
- assemble template context dictionaries

This module MUST NOT:
- register routes
- call render_template(...)
- mutate database state
- implement unrelated business workflows
- replace existing lower-level procurement query helpers
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ...models import Procurement
from ..master_data_service import get_active_option_values
from ..procurement_service import (
    apply_list_filters,
    base_procurements_query,
    order_by_serial_no,
    service_units_for_filter,
    with_list_eagerloads,
)

# Allowed page sizes for procurement list screens.
#
# These values keep response payloads bounded on PythonAnywhere while still
# giving users a reasonable amount of data per page.
_ALLOWED_PER_PAGE_VALUES = (25, 50, 100)
_DEFAULT_PER_PAGE = 25


def _parse_positive_int(value: object, default: int) -> int:
    """
    Parse a positive integer from request-like input.

    Invalid, empty, negative, or zero values fall back to `default`.
    """
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default

    if parsed <= 0:
        return default

    return parsed


def _parse_per_page(value: object) -> int:
    """
    Parse and normalize the requested page size.

    Only known-safe values are accepted so the list pages remain bounded even
    if a client submits a very large number manually.
    """
    parsed = _parse_positive_int(value, _DEFAULT_PER_PAGE)
    if parsed not in _ALLOWED_PER_PAGE_VALUES:
        return _DEFAULT_PER_PAGE
    return parsed


def _build_pagination_window(current_page: int, total_pages: int, *, radius: int = 2) -> list[int]:
    """
    Build a compact page-number window around the current page.

    Example:
    - current_page=7, total_pages=20, radius=2 -> [5, 6, 7, 8, 9]
    """
    if total_pages <= 0:
        return []

    start_page = max(1, current_page - radius)
    end_page = min(total_pages, current_page + radius)
    return list(range(start_page, end_page + 1))


def _paginate_procurements_query(query, request_args: Mapping[str, Any]) -> tuple[list[Procurement], dict[str, Any]]:
    """
    Apply bounded pagination to a procurement list query.

    Pagination is intentionally applied before template rendering so that:
    - the database returns only the rows needed for the active page
    - PythonAnywhere does not need to materialize large full-result lists
    - the template does not iterate over every matching procurement
    """
    page = _parse_positive_int(request_args.get("page"), 1)
    per_page = _parse_per_page(request_args.get("per_page"))

    total_items = query.order_by(None).count()
    total_pages = max(1, math.ceil(total_items / per_page)) if total_items else 1

    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page

    paged_query = order_by_serial_no(query)
    paged_query = paged_query.offset(offset).limit(per_page)
    paged_query = with_list_eagerloads(paged_query)

    procurements = paged_query.all()

    start_index = offset + 1 if total_items > 0 else 0
    end_index = min(offset + per_page, total_items) if total_items > 0 else 0

    pagination = {
        "page": page,
        "per_page": per_page,
        "per_page_options": list(_ALLOWED_PER_PAGE_VALUES),
        "total_items": total_items,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": page - 1 if page > 1 else None,
        "next_page": page + 1 if page < total_pages else None,
        "page_numbers": _build_pagination_window(page, total_pages),
        "start_index": start_index,
        "end_index": end_index,
    }

    return procurements, pagination


def build_inbox_procurements_list_context(
    request_args: Mapping[str, Any],
    *,
    allow_create: bool,
) -> dict[str, Any]:
    """
    Build template context for the `/procurements/inbox` page.
    """
    query = base_procurements_query()
    query = query.filter(Procurement.status == "ΣΕ ΕΞΕΛΙΞΗ")
    query = query.filter(
        (Procurement.send_to_expenses.is_(False))
        | (Procurement.send_to_expenses.is_(None))
    )

    query = apply_list_filters(query, request_args)
    procurements, pagination = _paginate_procurements_query(query, request_args)

    return {
        "procurements": procurements,
        "pagination": pagination,
        "page_title": "Λίστα Προμηθειών (μη εγκεκριμένες)",
        "page_subtitle": "Προμήθειες σε εξέλιξη που δεν έχουν μεταφερθεί στις Εκκρεμείς Δαπάνες.",
        "allow_create": allow_create,
        "open_mode": "edit",
        "show_open_button": True,
        "enable_row_colors": True,
        "allow_delete": False,
        "service_units": service_units_for_filter(),
        "status_options": get_active_option_values("KATASTASH"),
        "stage_options": get_active_option_values("STADIO"),
    }


def build_pending_expenses_list_context(
    request_args: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Build template context for the `/procurements/pending-expenses` page.
    """
    query = base_procurements_query()
    query = query.filter(Procurement.status == "ΣΕ ΕΞΕΛΙΞΗ")
    query = query.filter(Procurement.send_to_expenses.is_(True))

    query = apply_list_filters(query, request_args)
    procurements, pagination = _paginate_procurements_query(query, request_args)

    return {
        "procurements": procurements,
        "pagination": pagination,
        "page_title": "Εκκρεμείς Δαπάνες",
        "page_subtitle": "Προμήθειες σε εξέλιξη που έχουν μεταφερθεί στις Εκκρεμείς Δαπάνες.",
        "allow_create": False,
        "open_mode": "implementation",
        "show_open_button": True,
        "enable_row_colors": True,
        "allow_delete": False,
        "service_units": service_units_for_filter(),
        "status_options": get_active_option_values("KATASTASH"),
        "stage_options": get_active_option_values("STADIO"),
    }


def build_all_procurements_list_context(
    request_args: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Build template context for the `/procurements/all` page.
    """
    query = base_procurements_query()
    query = apply_list_filters(query, request_args)
    procurements, pagination = _paginate_procurements_query(query, request_args)

    return {
        "procurements": procurements,
        "pagination": pagination,
        "page_title": "Όλες οι Προμήθειες",
        "page_subtitle": "Περιλαμβάνει όλες τις προμήθειες ανεξάρτητα από στάδιο και κατάσταση.",
        "allow_create": False,
        "open_mode": "edit",
        "show_open_button": True,
        "enable_row_colors": True,
        "allow_delete": True,
        "service_units": service_units_for_filter(),
        "status_options": get_active_option_values("KATASTASH"),
        "stage_options": get_active_option_values("STADIO"),
    }