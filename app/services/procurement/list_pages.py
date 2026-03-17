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
    procurements = order_by_serial_no(with_list_eagerloads(query)).all()

    return {
        "procurements": procurements,
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
    procurements = order_by_serial_no(with_list_eagerloads(query)).all()

    return {
        "procurements": procurements,
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
    procurements = order_by_serial_no(with_list_eagerloads(query)).all()

    return {
        "procurements": procurements,
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

