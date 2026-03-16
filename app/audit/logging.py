"""
app/audit_logging.py

AuditLog row creation helpers.

PURPOSE
-------
This module is responsible for assembling and adding `AuditLog` rows to the
current SQLAlchemy session.

WHY THIS FILE EXISTS
--------------------
Previously, `app/audit.py` contained both:
- snapshot serialization helpers
- AuditLog persistence logic

This module isolates the persistence side so that:
- transaction-related audit behavior is easier to find
- actor / request metadata extraction is centralized
- the main public `app.audit` facade stays small

TRANSACTION BEHAVIOR
--------------------
This module adds `AuditLog` rows to the current SQLAlchemy session, but it does
NOT commit. The caller owns transaction boundaries.

WHY THIS MATTERS
----------------
Audit logging should usually participate in the same transaction as the related
business mutation. That keeps the data change and its audit trail aligned.

SUPPORTED CALL STYLES
---------------------
Preferred:
    log_action(entity=entity, action="UPDATE", before=..., after=...)

Backward-compatible positional:
    log_action(entity, "UPDATE", before=..., after=...)
"""

from __future__ import annotations

from typing import Any

from flask import request
from flask_login import current_user

from .serialization import snapshot_to_json
from ..extensions import db
from ..models import AuditLog


def current_audit_user_id() -> int | None:
    """
    Return the authenticated user's id, if available.

    RETURNS
    -------
    int | None
        Authenticated user id or None for anonymous/system contexts.
    """
    if current_user.is_authenticated:
        return current_user.id
    return None


def current_audit_username_snapshot() -> str | None:
    """
    Return a stable username snapshot for audit persistence.

    WHY SNAPSHOT THE USERNAME
    -------------------------
    Even if the username changes later, the audit row should preserve the
    identity label as it existed when the action happened.

    RETURNS
    -------
    str | None
        Current authenticated username or None.
    """
    if current_user.is_authenticated:
        return current_user.username
    return None


def current_request_ip_address() -> str | None:
    """
    Return the client IP address as Flask currently sees it.

    IMPORTANT
    ---------
    In reverse-proxy production deployments, ProxyFix / trusted proxy headers
    should be configured correctly so this reflects the real client IP.

    RETURNS
    -------
    str | None
        Remote IP string or None.
    """
    return request.remote_addr


def build_audit_entry(
    *,
    entity: Any,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    """
    Build an `AuditLog` ORM instance without adding it to the session yet.

    PARAMETERS
    ----------
    entity:
        SQLAlchemy model instance with an `id`.
    action:
        Action name, usually CREATE / UPDATE / DELETE.
    before:
        Optional snapshot before mutation.
    after:
        Optional snapshot after mutation.

    RETURNS
    -------
    AuditLog
        New AuditLog ORM object.

    RAISES
    ------
    ValueError
        If the entity has no id.

    IMPORTANT
    ---------
    The entity must already have an id, so for CREATE operations this should
    normally be called after `flush()`.
    """
    entity_id = getattr(entity, "id", None)
    if entity_id is None:
        raise ValueError("log_action entity must have an 'id' attribute (usually after flush).")

    return AuditLog(
        user_id=current_audit_user_id(),
        username_snapshot=current_audit_username_snapshot(),
        entity_type=entity.__class__.__name__,
        entity_id=int(entity_id),
        action=str(action),
        before_data=snapshot_to_json(before),
        after_data=snapshot_to_json(after),
        ip_address=current_request_ip_address(),
    )


def log_action(
    entity: Any = None,
    action: str | None = None,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    entity_kw: Any = None,
    action_kw: str | None = None,
) -> None:
    """
    Add an AuditLog entry to the current SQLAlchemy session.

    SUPPORTED CALL STYLES
    ---------------------
    Preferred:
        log_action(entity=entity, action="UPDATE", before=..., after=...)

    Backward-compatible positional:
        log_action(entity, "UPDATE", before=..., after=...)

    PARAMETERS
    ----------
    entity:
        SQLAlchemy model instance with an `id`.
    action:
        Action name, usually CREATE / UPDATE / DELETE.
    before:
        Optional dict snapshot before the change.
    after:
        Optional dict snapshot after the change.

    RAISES
    ------
    TypeError
        If entity or action are missing.
    ValueError
        If entity has no id.

    IMPORTANT
    ---------
    This helper only adds the audit row to the current SQLAlchemy session.
    It does not commit.
    """
    # ---------------------------------------------------------------
    # Backward-compatible keyword aliases
    # ---------------------------------------------------------------
    if entity is None and entity_kw is not None:
        entity = entity_kw
    if action is None and action_kw is not None:
        action = action_kw

    if entity is None or action is None:
        raise TypeError("log_action requires 'entity' and 'action'.")

    entry = build_audit_entry(
        entity=entity,
        action=action,
        before=before,
        after=after,
    )
    db.session.add(entry)