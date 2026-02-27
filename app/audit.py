"""
app/audit.py

Enterprise audit logging helper utilities.

Goals:
- Capture WHO did WHAT to WHICH entity, with BEFORE/AFTER snapshots.
- Store username snapshot to preserve identity even if username changes later.
- Store IP address for traceability.

IMPORTANT:
- This helper ADDS AuditLog entries to the current SQLAlchemy session.
  The calling route controls transaction boundaries (commit/rollback).
- Never trust UI for audit; audit must run server-side on mutations.

Backward compatibility:
- Supports both:
    log_action(entity, action, before=..., after=...)
  and:
    log_action(entity=..., action=..., before=..., after=...)
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from flask import request
from flask_login import current_user

from .extensions import db
from .models import AuditLog


def _safe_str(value: Any) -> Optional[str]:
    """
    Convert a value to a stable string representation suitable for JSON and DB storage.

    - For Decimal/datetime/etc: str(value) is typically safe.
    - For None: return None.
    - For exotic types: fall back to repr.
    """
    if value is None:
        return None
    try:
        return str(value)
    except Exception:
        try:
            return repr(value)
        except Exception:
            return None


def serialize_model(instance: Any) -> Dict[str, Optional[str]]:
    """
    Convert a SQLAlchemy model instance to a dict snapshot based on table columns.

    NOTES:
    - Captures only scalar column values (not relationships).
    - Values are converted to string for JSON safety and SQLite/PostgreSQL portability.
    """
    data: Dict[str, Optional[str]] = {}
    for column in instance.__table__.columns:
        data[column.name] = _safe_str(getattr(instance, column.name))
    return data


def log_action(
    entity: Any = None,
    action: str | None = None,
    *,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    entity_kw: Any = None,
    action_kw: str | None = None,
) -> None:
    """
    Add an AuditLog entry to the current db session.

    Backward-compatible signature:
    - Preferred:
        log_action(entity=..., action="UPDATE", before=..., after=...)
    - Also supports legacy positional:
        log_action(entity, "UPDATE", before=..., after=...)

    Parameters:
        entity: SQLAlchemy model instance with .id (positional)
        action: CREATE / UPDATE / DELETE (positional)
        before: dict snapshot (optional)
        after: dict snapshot (optional)

    SECURITY NOTE:
    - request.remote_addr is as Flask sees it. In production behind a reverse proxy,
      configure ProxyFix / trusted proxy headers to capture real client IP.
    """
    # Support explicit keyword aliases if used
    if entity is None and entity_kw is not None:
        entity = entity_kw
    if action is None and action_kw is not None:
        action = action_kw

    if entity is None or action is None:
        raise TypeError("log_action requires 'entity' and 'action' (positional or keyword).")

    # Defensive: entity must have an id for meaningful audit
    entity_id = getattr(entity, "id", None)
    if entity_id is None:
        raise ValueError("log_action entity must have an 'id' attribute (after flush).")

    entry = AuditLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        username_snapshot=current_user.username if current_user.is_authenticated else None,
        entity_type=entity.__class__.__name__,
        entity_id=int(entity_id),
        action=str(action),
        before_data=json.dumps(before, ensure_ascii=False) if before else None,
        after_data=json.dumps(after, ensure_ascii=False) if after else None,
        ip_address=request.remote_addr,
    )
    db.session.add(entry)