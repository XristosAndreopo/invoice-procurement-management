"""
app/models/__init__.py

Central public export surface for all SQLAlchemy models and selected shared
model helpers.

PURPOSE
-------
This package-level module provides one stable import point for the application's
ORM layer.

After splitting the old monolithic `app/models.py` into the `app/models/`
package, the rest of the application can continue to use imports such as:

    from app.models import User, Personnel, Procurement

instead of importing from individual model modules.

WHY THIS FILE EXISTS
--------------------
A central model facade provides several practical benefits:

- backward compatibility for existing imports
- one predictable import location for routes, services, bootstrap, and audit
- freedom to reorganize model modules internally without touching the whole app
- clearer separation between the public ORM API and internal file layout

PUBLIC API POLICY
-----------------
This file should re-export only:
- model classes that are intended to be used throughout the application
- a very small set of shared model helper functions that existing code may
  already import from `app.models`

This file should NOT become a dumping ground for:
- query helpers
- business workflow logic
- service-layer orchestration
- route-layer helpers

THOSE BELONG ELSEWHERE
----------------------
- query/business logic -> app/services
- route orchestration  -> app/blueprints/.../routes.py (or route services)
- infrastructure       -> app/bootstrap, app/security, app/audit, etc.
"""

from __future__ import annotations

# -------------------------------------------------------------------
# Shared model helpers
# -------------------------------------------------------------------
# These remain re-exported here for backward compatibility, because existing
# code may already import them from `app.models`.
from .helpers import (
    _display_percent,
    _money,
    _normalize_percent,
    _percent_to_fraction,
    _to_decimal,
)

# -------------------------------------------------------------------
# Organization / identity models
# -------------------------------------------------------------------
from .organization import Department, Directory, Personnel, ServiceUnit
from .user import User

# -------------------------------------------------------------------
# Master-data models
# -------------------------------------------------------------------
from .master_data import (
    AleKae,
    Cpv,
    IncomeTaxRule,
    OptionCategory,
    OptionValue,
    WithholdingProfile,
)

# -------------------------------------------------------------------
# Supplier / procurement models
# -------------------------------------------------------------------
from .supplier import Supplier
from .procurement import (
    MaterialLine,
    Procurement,
    ProcurementCommittee,
    ProcurementSupplier,
)

# -------------------------------------------------------------------
# Cross-cutting / supporting models
# -------------------------------------------------------------------
from .feedback import Feedback
from .audit import AuditLog

__all__ = [
    # Shared helpers
    "_to_decimal",
    "_normalize_percent",
    "_percent_to_fraction",
    "_display_percent",
    "_money",

    # Organization / identity
    "Personnel",
    "ServiceUnit",
    "Directory",
    "Department",
    "User",

    # Master data
    "OptionCategory",
    "OptionValue",
    "AleKae",
    "Cpv",
    "IncomeTaxRule",
    "WithholdingProfile",

    # Supplier / procurement
    "Supplier",
    "Procurement",
    "ProcurementSupplier",
    "MaterialLine",
    "ProcurementCommittee",

    # Cross-cutting
    "Feedback",
    "AuditLog",
]

