"""
app/services/organization_service.py

Backward-compatible public facade for organization helpers.

PURPOSE
-------
This module preserves the historical import surface:

    from app.services.organization_service import ...

while the implementation is now split into focused modules:
- app.services.organization_queries
- app.services.organization_validation
- app.services.organization_scope

WHY THIS FILE EXISTS
--------------------
The previous implementation had grown into a mixed-responsibility module that
contained:
- dropdown/query loaders
- structural validation helpers
- scope/security guards
- import-support service-unit matching

This facade allows the application to:
- refactor incrementally
- keep existing imports working
- move routes gradually to narrower modules later

PUBLIC API POLICY
-----------------
This file should remain a thin export facade only.

It must NOT:
- reintroduce business/query logic directly
- become a dumping ground
- grow beyond re-exports and documentation
"""

from __future__ import annotations

from .organization.queries import (
    active_personnel_for_service_unit,
    active_personnel_ids_for_service_unit,
    departments_for_dropdown,
    directories_for_dropdown,
    match_service_unit_from_text,
    service_units_for_dropdown,
)
from .organization.scope import (
    effective_scope_service_unit_id_for_manager_or_none,
    ensure_admin_or_manager_only,
    ensure_manager_scope_or_403,
)
from .organization.validation import (
    validate_department_for_directory_and_service_unit,
    validate_directory_for_service_unit,
    validate_service_unit_required,
)

__all__ = [
    "service_units_for_dropdown",
    "directories_for_dropdown",
    "departments_for_dropdown",
    "active_personnel_for_service_unit",
    "active_personnel_ids_for_service_unit",
    "match_service_unit_from_text",
    "validate_service_unit_required",
    "validate_directory_for_service_unit",
    "validate_department_for_directory_and_service_unit",
    "effective_scope_service_unit_id_for_manager_or_none",
    "ensure_admin_or_manager_only",
    "ensure_manager_scope_or_403",
]

