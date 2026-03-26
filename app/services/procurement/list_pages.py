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

PERFORMANCE INSTRUMENTATION
---------------------------
This module includes lightweight request-local instrumentation for:
- full list context build timing
- pagination timing
- filter-options loading timing
- coarse query assembly timing

IMPORTANT
---------
The instrumentation is observability-only:
- no filtering changes
- no pagination changes
- no template-context contract changes
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from typing import Any

from flask import g, has_request_context

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
    These page services must remain safe and reusable even if they are executed
    outside an instrumented request.
    """
    if not has_request_context():
        return None
    return getattr(g, "request_timing", None)


def _timing_name(prefix: str, page_name: str, part: str) -> str:
    """
    Build a stable instrumentation name for list-page timings.

    EXAMPLE
    -------
    _timing_name("list_page", "inbox", "pagination")
    -> "list_page.inbox.pagination"
    """
    return f"{prefix}.{page_name}.{part}"


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


def _paginate_procurements_query(
    query,
    request_args: Mapping[str, Any],
    *,
    page_name: str,
) -> tuple[list[Procurement], dict[str, Any]]:
    """
    Apply bounded pagination to a procurement list query.

    Pagination is intentionally applied before template rendering so that:
    - the database returns only the rows needed for the active page
    - PythonAnywhere does not need to materialize large full-result lists
    - the template does not iterate over every matching procurement

    PERFORMANCE NOTE
    ----------------
    This function measures:
    - count query timing
    - page fetch timing
    - full pagination timing
    """
    request_timing = _current_request_timing()
    pagination_started_at = time.perf_counter()

    page = _parse_positive_int(request_args.get("page"), 1)
    per_page = _parse_per_page(request_args.get("per_page"))

    count_started_at = time.perf_counter()
    total_items = query.order_by(None).count()
    count_elapsed_ms = round((time.perf_counter() - count_started_at) * 1000.0, 2)

    total_pages = max(1, math.ceil(total_items / per_page)) if total_items else 1

    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page

    page_fetch_started_at = time.perf_counter()
    paged_query = order_by_serial_no(query)
    paged_query = paged_query.offset(offset).limit(per_page)
    paged_query = with_list_eagerloads(paged_query)

    procurements = paged_query.all()
    page_fetch_elapsed_ms = round((time.perf_counter() - page_fetch_started_at) * 1000.0, 2)

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

    if request_timing is not None:
        request_timing.add_timing(
            _timing_name("list_page", page_name, "pagination.count"),
            count_elapsed_ms,
        )
        request_timing.add_timing(
            _timing_name("list_page", page_name, "pagination.fetch"),
            page_fetch_elapsed_ms,
        )
        request_timing.add_timing(
            _timing_name("list_page", page_name, "pagination.total"),
            round((time.perf_counter() - pagination_started_at) * 1000.0, 2),
        )
        request_timing.mark(f"{page_name}_page", page)
        request_timing.mark(f"{page_name}_per_page", per_page)
        request_timing.mark(f"{page_name}_total_items", total_items)
        request_timing.mark(f"{page_name}_rows_loaded", len(procurements))

    return procurements, pagination


def build_inbox_procurements_list_context(
    request_args: Mapping[str, Any],
    *,
    allow_create: bool,
) -> dict[str, Any]:
    """
    Build template context for the `/procurements/inbox` page.
    """
    request_timing = _current_request_timing()
    page_name = "inbox"
    started_at = time.perf_counter()

    base_query_started_at = time.perf_counter()
    query = base_procurements_query()
    query = query.filter(Procurement.status == "ΣΕ ΕΞΕΛΙΞΗ")
    query = query.filter(
        (Procurement.send_to_expenses.is_(False))
        | (Procurement.send_to_expenses.is_(None))
    )
    base_query_elapsed_ms = round((time.perf_counter() - base_query_started_at) * 1000.0, 2)

    filters_started_at = time.perf_counter()
    query = apply_list_filters(query, request_args)
    filters_elapsed_ms = round((time.perf_counter() - filters_started_at) * 1000.0, 2)

    procurements, pagination = _paginate_procurements_query(
        query,
        request_args,
        page_name=page_name,
    )

    options_started_at = time.perf_counter()
    service_units = service_units_for_filter()
    status_options = get_active_option_values("KATASTASH")
    stage_options = get_active_option_values("STADIO")
    options_elapsed_ms = round((time.perf_counter() - options_started_at) * 1000.0, 2)

    context = {
        "procurements": procurements,
        "pagination": pagination,
        "page_title": "Λίστα Προμηθειών (μη εγκεκριμένες)",
        "page_subtitle": "Προμήθειες σε εξέλιξη που δεν έχουν μεταφερθεί στις Εκκρεμείς Δαπάνες.",
        "allow_create": allow_create,
        "open_mode": "edit",
        "show_open_button": True,
        "enable_row_colors": True,
        "allow_delete": False,
        "service_units": service_units,
        "status_options": status_options,
        "stage_options": stage_options,
    }

    if request_timing is not None:
        request_timing.add_timing(
            _timing_name("list_page", page_name, "base_query"),
            base_query_elapsed_ms,
        )
        request_timing.add_timing(
            _timing_name("list_page", page_name, "apply_filters"),
            filters_elapsed_ms,
        )
        request_timing.add_timing(
            _timing_name("list_page", page_name, "load_filter_options"),
            options_elapsed_ms,
        )
        request_timing.add_timing(
            _timing_name("list_page", page_name, "build_context"),
            round((time.perf_counter() - started_at) * 1000.0, 2),
        )
        request_timing.mark(f"{page_name}_service_units_count", len(service_units))
        request_timing.mark(f"{page_name}_status_options_count", len(status_options))
        request_timing.mark(f"{page_name}_stage_options_count", len(stage_options))
        request_timing.mark(f"{page_name}_allow_create", bool(allow_create))

    return context


def build_pending_expenses_list_context(
    request_args: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Build template context for the `/procurements/pending-expenses` page.
    """
    request_timing = _current_request_timing()
    page_name = "pending_expenses"
    started_at = time.perf_counter()

    base_query_started_at = time.perf_counter()
    query = base_procurements_query()
    query = query.filter(Procurement.status == "ΣΕ ΕΞΕΛΙΞΗ")
    query = query.filter(Procurement.send_to_expenses.is_(True))
    base_query_elapsed_ms = round((time.perf_counter() - base_query_started_at) * 1000.0, 2)

    filters_started_at = time.perf_counter()
    query = apply_list_filters(query, request_args)
    filters_elapsed_ms = round((time.perf_counter() - filters_started_at) * 1000.0, 2)

    procurements, pagination = _paginate_procurements_query(
        query,
        request_args,
        page_name=page_name,
    )

    options_started_at = time.perf_counter()
    service_units = service_units_for_filter()
    status_options = get_active_option_values("KATASTASH")
    stage_options = get_active_option_values("STADIO")
    options_elapsed_ms = round((time.perf_counter() - options_started_at) * 1000.0, 2)

    context = {
        "procurements": procurements,
        "pagination": pagination,
        "page_title": "Εκκρεμείς Δαπάνες",
        "page_subtitle": "Προμήθειες σε εξέλιξη που έχουν μεταφερθεί στις Εκκρεμείς Δαπάνες.",
        "allow_create": False,
        "open_mode": "implementation",
        "show_open_button": True,
        "enable_row_colors": True,
        "allow_delete": False,
        "service_units": service_units,
        "status_options": status_options,
        "stage_options": stage_options,
    }

    if request_timing is not None:
        request_timing.add_timing(
            _timing_name("list_page", page_name, "base_query"),
            base_query_elapsed_ms,
        )
        request_timing.add_timing(
            _timing_name("list_page", page_name, "apply_filters"),
            filters_elapsed_ms,
        )
        request_timing.add_timing(
            _timing_name("list_page", page_name, "load_filter_options"),
            options_elapsed_ms,
        )
        request_timing.add_timing(
            _timing_name("list_page", page_name, "build_context"),
            round((time.perf_counter() - started_at) * 1000.0, 2),
        )
        request_timing.mark(f"{page_name}_service_units_count", len(service_units))
        request_timing.mark(f"{page_name}_status_options_count", len(status_options))
        request_timing.mark(f"{page_name}_stage_options_count", len(stage_options))

    return context


def build_all_procurements_list_context(
    request_args: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Build template context for the `/procurements/all` page.
    """
    request_timing = _current_request_timing()
    page_name = "all_procurements"
    started_at = time.perf_counter()

    base_query_started_at = time.perf_counter()
    query = base_procurements_query()
    base_query_elapsed_ms = round((time.perf_counter() - base_query_started_at) * 1000.0, 2)

    filters_started_at = time.perf_counter()
    query = apply_list_filters(query, request_args)
    filters_elapsed_ms = round((time.perf_counter() - filters_started_at) * 1000.0, 2)

    procurements, pagination = _paginate_procurements_query(
        query,
        request_args,
        page_name=page_name,
    )

    options_started_at = time.perf_counter()
    service_units = service_units_for_filter()
    status_options = get_active_option_values("KATASTASH")
    stage_options = get_active_option_values("STADIO")
    options_elapsed_ms = round((time.perf_counter() - options_started_at) * 1000.0, 2)

    context = {
        "procurements": procurements,
        "pagination": pagination,
        "page_title": "Όλες οι Προμήθειες",
        "page_subtitle": "Περιλαμβάνει όλες τις προμήθειες ανεξάρτητα από στάδιο και κατάσταση.",
        "allow_create": False,
        "open_mode": "edit",
        "show_open_button": True,
        "enable_row_colors": True,
        "allow_delete": True,
        "service_units": service_units,
        "status_options": status_options,
        "stage_options": stage_options,
    }

    if request_timing is not None:
        request_timing.add_timing(
            _timing_name("list_page", page_name, "base_query"),
            base_query_elapsed_ms,
        )
        request_timing.add_timing(
            _timing_name("list_page", page_name, "apply_filters"),
            filters_elapsed_ms,
        )
        request_timing.add_timing(
            _timing_name("list_page", page_name, "load_filter_options"),
            options_elapsed_ms,
        )
        request_timing.add_timing(
            _timing_name("list_page", page_name, "build_context"),
            round((time.perf_counter() - started_at) * 1000.0, 2),
        )
        request_timing.mark(f"{page_name}_service_units_count", len(service_units))
        request_timing.mark(f"{page_name}_status_options_count", len(status_options))
        request_timing.mark(f"{page_name}_stage_options_count", len(stage_options))

    return context