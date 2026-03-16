"""
app/audit.py

Public audit facade for the Invoice / Procurement Management System.

PURPOSE
-------
This module remains the stable import surface for audit helpers used across the
application.

After refactoring, responsibilities are split as follows:

- `app.audit_serialization`
    Audit snapshot preparation / model serialization

- `app.audit_logging`
    AuditLog row construction and session insertion

- `app.audit`
    Backwards-compatible public facade

WHY THIS STRUCTURE IS BETTER
----------------------------
Previously, one file mixed:
- value normalization
- model snapshot serialization
- request/user metadata extraction
- AuditLog row creation

Those are related but distinct concerns.

Now:
- snapshot rules live in one place
- persistence logic lives in one place
- existing imports continue to work

TRANSACTION BEHAVIOR
--------------------
Audit helpers add rows to the current SQLAlchemy session but do NOT commit.
The caller remains responsible for transaction boundaries.
"""

from __future__ import annotations

from .audit_logging import (
    build_audit_entry,
    current_audit_user_id,
    current_audit_username_snapshot,
    current_request_ip_address,
    log_action,
)
from .audit_serialization import safe_audit_value, serialize_model, snapshot_to_json

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