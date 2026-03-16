"""
app/audit/__init__.py

Public audit facade for the Invoice / Procurement Management System.

PURPOSE
-------
This package provides the stable public import surface for audit helpers used
across the application.

PACKAGE STRUCTURE
-----------------
- app.audit.serialization
    Audit snapshot preparation / model serialization

- app.audit.logging
    AuditLog row construction and session insertion

- app.audit
    Backwards-compatible public facade

TRANSACTION BEHAVIOR
--------------------
Audit helpers add rows to the current SQLAlchemy session but do NOT commit.
The caller remains responsible for transaction boundaries.
"""

from __future__ import annotations

from .logging import (
    build_audit_entry,
    current_audit_user_id,
    current_audit_username_snapshot,
    current_request_ip_address,
    log_action,
)
from .serialization import safe_audit_value, serialize_model, snapshot_to_json

__all__ = [
    "safe_audit_value",
    "serialize_model",
    "snapshot_to_json",
    "current_audit_user_id",
    "current_audit_username_snapshot",
    "current_request_ip_address",
    "build_audit_entry",
    "log_action",
]