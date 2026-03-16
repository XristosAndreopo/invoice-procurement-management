"""
app/audit_serialization.py

Serialization helpers for audit logging.

PURPOSE
-------
This module is responsible only for turning model state into compact,
deterministic audit-friendly snapshots.

WHY THIS FILE EXISTS
--------------------
Previously, `app/audit.py` mixed:
- snapshot serialization helpers
- current request / current user metadata extraction
- AuditLog row creation

Those are related but not the same responsibility.

This module isolates the snapshot side of audit logging so that:
- model serialization rules live in one place
- future changes to snapshot formatting stay localized
- audit persistence logic remains smaller and easier to read

AUDIT SNAPSHOT PHILOSOPHY
-------------------------
Audit snapshots should be:
- compact
- deterministic
- safe to JSON-encode
- independent from ORM relationship graphs

Therefore, snapshots include:
- only scalar table-column values
- no relationships
- values converted to stable strings where needed

IMPORTANT
---------
This module does not write to the database.
It only prepares audit-safe data structures.
"""

from __future__ import annotations

import json
from typing import Any, Optional


def safe_audit_value(value: Any) -> Optional[str]:
    """
    Convert a value to a DB- and JSON-safe string representation.

    PARAMETERS
    ----------
    value:
        Any scalar-ish Python value extracted from a model column.

    RETURNS
    -------
    str | None
        Safe string representation, or None when the original value is None.

    WHY THIS EXISTS
    ---------------
    Audit snapshots are stored as JSON text. We want the persisted form to be
    deterministic and easy to inspect, while avoiding unexpected serializer
    behavior for special value types.

    CURRENT STRATEGY
    ----------------
    - None stays None
    - everything else is converted with str(...)
    """
    if value is None:
        return None
    return str(value)


def serialize_model(instance: Any) -> dict[str, Optional[str]]:
    """
    Serialize a SQLAlchemy model instance into an audit snapshot dict.

    WHAT IS INCLUDED
    ----------------
    - Only table columns
    - No relationships
    - Values converted to strings for safe JSON persistence

    WHY RELATIONSHIPS ARE EXCLUDED
    ------------------------------
    Relationship graphs can be large, recursive, lazy-loaded, and unstable for
    auditing purposes. Audit snapshots should be compact and deterministic.

    PARAMETERS
    ----------
    instance:
        A SQLAlchemy model instance with `__table__.columns`.

    RETURNS
    -------
    dict[str, Optional[str]]
        Mapping of column name -> safe string value.
    """
    data: dict[str, Optional[str]] = {}

    for column in instance.__table__.columns:
        data[column.name] = safe_audit_value(getattr(instance, column.name))

    return data


def snapshot_to_json(data: dict[str, Any] | None) -> str | None:
    """
    Convert a snapshot dict to JSON safely for storage.

    PARAMETERS
    ----------
    data:
        Snapshot dictionary or None.

    RETURNS
    -------
    str | None
        JSON string with UTF-8 characters preserved, or None if input is empty.

    NOTES
    -----
    `ensure_ascii=False` is intentional so Greek content remains human-readable
    in stored audit rows.
    """
    if not data:
        return None
    return json.dumps(data, ensure_ascii=False)