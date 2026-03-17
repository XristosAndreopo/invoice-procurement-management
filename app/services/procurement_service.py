"""
app/services/procurement_service.py

Backward-compatible public facade for procurement helpers.

PURPOSE
-------
This module preserves the historical import surface:

    from app.services.procurement_service import ...

while the implementation is now split into focused modules:
- app.services.procurement_queries
- app.services.procurement_reference_data
- app.services.procurement_workflow
- app.presentation.procurement_ui

WHY THIS FILE EXISTS
--------------------
The previous implementation had grown into a mixed-responsibility module that
contained:
- procurement queries
- list filtering
- reference-data lookup helpers
- workflow predicates
- UI/download helpers

That made the file harder to navigate and increased the chance that unrelated
concerns would keep accumulating inside one service file.

This facade allows the application to:
- refactor incrementally
- keep existing imports working during the transition
- move routes gradually to the more specific modules later

PUBLIC API POLICY
-----------------
This file should remain a thin export facade only.

It must NOT:
- reintroduce business/query logic directly
- become a new dumping ground
- grow beyond import re-exports and module-level documentation

MIGRATION NOTE
--------------
Existing imports may continue to use this module for now.

Future route/service cleanup may replace imports gradually with more specific
modules, for example:
- query helpers       -> app.services.procurement_queries
- lookup helpers      -> app.services.procurement_reference_data
- workflow predicates -> app.services.procurement_workflow
- UI helpers          -> app.presentation.procurement_ui
"""

from __future__ import annotations

from .procurement.queries import (
    apply_list_filters,
    base_procurements_query,
    load_procurement,
    order_by_serial_no,
    with_list_eagerloads,
)
from .procurement.reference_data import (
    active_income_tax_rules,
    active_withholding_profiles,
    committees_for_service_unit,
    handler_candidate_ids,
    handler_candidates,
    service_units_for_filter,
)
from .procurement.workflow import is_in_implementation_phase
from ..presentation.procurement_ui import (
    money_filename,
    opened_from_all_list,
    sanitize_filename_component,
)

__all__ = [
    "load_procurement",
    "base_procurements_query",
    "with_list_eagerloads",
    "order_by_serial_no",
    "apply_list_filters",
    "service_units_for_filter",
    "handler_candidates",
    "handler_candidate_ids",
    "committees_for_service_unit",
    "active_income_tax_rules",
    "active_withholding_profiles",
    "is_in_implementation_phase",
    "opened_from_all_list",
    "sanitize_filename_component",
    "money_filename",
]

