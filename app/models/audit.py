"""
app/models/audit.py

Audit logging model.

PURPOSE
-------
This module defines the AuditLog entity used to persist enterprise-style audit
records across the application.

WHY THIS FILE EXISTS
--------------------
Audit logs are cross-cutting infrastructure records rather than core business
entities.

They are intentionally kept separate from:
- procurement workflow models
- organization hierarchy models
- user authentication models
- master-data configuration models

This separation makes the architecture easier to reason about and keeps the
domain model boundaries clear.

ARCHITECTURAL BOUNDARY
----------------------
This module defines:
- persistence schema for audit rows
- lightweight display helpers
- the relationship to the originating User record

This module must NOT become the place for:
- audit serialization logic
- request metadata extraction
- audit row creation orchestration
- transaction management
- report/query orchestration

Those responsibilities belong in:
- app.audit.serialization
- app.audit.logging
- app.services.* / route layer where applicable

IMPORTANT DESIGN NOTE
---------------------
Audit rows intentionally store snapshots such as:
- username_snapshot
- before_data
- after_data

This is necessary because the related live entities may change over time.
The audit trail must remain historically meaningful even if:
- a username changes
- the underlying entity is updated again later
- the related user is removed or detached
"""

from __future__ import annotations

from datetime import datetime

from ..extensions import db


class AuditLog(db.Model):
    """
    Enterprise-style audit log row.

    STORED INFORMATION
    ------------------
    - who performed the action
    - what entity type / entity id was affected
    - what action occurred
    - before / after snapshots
    - IP address
    - timestamp

    TYPICAL ACTIONS
    ---------------
    Examples:
    - CREATE
    - UPDATE
    - DELETE

    IMPORTANT
    ---------
    The `before_data` and `after_data` fields are stored as text payloads
    (typically JSON), not parsed ORM structures.
    """

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    username_snapshot = db.Column(db.String(150), nullable=True)

    entity_type = db.Column(db.String(50), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)

    action = db.Column(db.String(20), nullable=False, index=True)

    before_data = db.Column(db.Text, nullable=True)
    after_data = db.Column(db.Text, nullable=True)

    ip_address = db.Column(db.String(45), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship(
        "User",
        backref=db.backref("audit_entries", lazy=True),
    )

    @property
    def display_name(self) -> str:
        """
        Preferred short label for admin/audit list screens.
        """
        entity_type = (self.entity_type or "").strip()
        action = (self.action or "").strip()
        entity_id = self.entity_id

        if entity_type and action and entity_id is not None:
            return f"{action} {entity_type}#{entity_id}"

        return f"AuditLog #{self.id}"

    @property
    def actor_display(self) -> str:
        """
        Best-effort display label for the actor who performed the action.

        Priority:
        1. username_snapshot
        2. related live User.username
        3. system/anonymous fallback
        """
        snapshot = (self.username_snapshot or "").strip()
        if snapshot:
            return snapshot

        if self.user and getattr(self.user, "username", None):
            return str(self.user.username).strip()

        return "system"

    @property
    def has_before_snapshot(self) -> bool:
        """
        Return True when a pre-change snapshot exists.
        """
        return bool((self.before_data or "").strip())

    @property
    def has_after_snapshot(self) -> bool:
        """
        Return True when a post-change snapshot exists.
        """
        return bool((self.after_data or "").strip())

    def __repr__(self) -> str:
        return f"<AuditLog {self.id}: {self.display_name}>"