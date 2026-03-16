"""
app/models/user.py

System user account model.

PURPOSE
-------
This module defines the authenticated application user entity.

A User represents:
- login credentials
- admin flag
- UI preferences
- linkage to organizational Personnel
- optional linkage to a ServiceUnit scope

WHY THIS MODEL EXISTS SEPARATELY
--------------------------------
Although a User is tightly connected to Personnel, it is not the same concept.

- Personnel:
    organizational person / directory record

- User:
    system login account and access identity

This distinction is important because:
- a person may conceptually exist in the organization directory
- but only some people should have application accounts
- account behavior (passwords, theme, admin flag) belongs to User, not Personnel

ARCHITECTURAL BOUNDARY
----------------------
This model may contain:
- schema fields
- relationships
- password helpers
- lightweight user capability helpers

This model must NOT become the place for:
- route-level authorization
- service-unit scope enforcement across requests
- workflow/business orchestration
- query helper collections

Those responsibilities belong in:
- app.security
- app.security.permissions
- app.services.*

SECURITY NOTE
-------------
Capability helpers such as `can_manage()` and `can_view()` are convenience
methods only. They do NOT replace server-side authorization checks in routes
and services.
"""

from __future__ import annotations

from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db


class User(UserMixin, db.Model):
    """
    Authenticated system user.

    CORE RESPONSIBILITIES
    ---------------------
    A User stores:
    - username
    - password hash
    - admin role flag
    - UI theme preference
    - linked Personnel identity
    - linked ServiceUnit scope

    RELATIONSHIP MODEL
    ------------------
    - one User <-> one Personnel
    - many Users may belong conceptually to ServiceUnit over time, but in the
      current model each User stores one optional assigned ServiceUnit
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    is_admin = db.Column(db.Boolean, default=False, nullable=False, index=True)

    # UI preference
    theme = db.Column(db.String(20), nullable=False, default="default")

    personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    service_unit_id = db.Column(
        db.Integer,
        db.ForeignKey("service_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    personnel = db.relationship("Personnel", back_populates="user")

    service_unit = db.relationship(
        "ServiceUnit",
        back_populates="users",
        foreign_keys=[service_unit_id],
    )

    def set_password(self, password: str) -> None:
        """
        Hash and store a new plain-text password.

        SECURITY
        --------
        The plain password is never stored directly.
        Only the password hash is persisted.
        """
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """
        Compare a plain-text password against the stored hash.

        PARAMETERS
        ----------
        password:
            Candidate plain-text password.

        RETURNS
        -------
        bool
            True when the provided password matches the stored hash.
        """
        return check_password_hash(self.password_hash, password)

    def is_manager(self) -> bool:
        """
        Return True if this user is the manager of their assigned ServiceUnit.

        RULE
        ----
        The user is considered manager when:
        - the user has an assigned service unit
        - that service unit's manager_personnel_id matches this user's
          personnel_id
        """
        if not self.service_unit:
            return False
        return self.service_unit.manager_personnel_id == self.personnel_id

    def is_deputy(self) -> bool:
        """
        Return True if this user is the deputy of their assigned ServiceUnit.

        RULE
        ----
        The user is considered deputy when:
        - the user has an assigned service unit
        - that service unit's deputy_personnel_id matches this user's
          personnel_id
        """
        if not self.service_unit:
            return False
        return self.service_unit.deputy_personnel_id == self.personnel_id

    def can_manage(self) -> bool:
        """
        Coarse-grained management capability helper.

        RETURNS TRUE FOR
        ----------------
        - admin
        - service unit manager
        - service unit deputy

        IMPORTANT
        ---------
        This is a convenience helper only. Route-level and service-level
        authorization must still be enforced separately.
        """
        return bool(self.is_admin or self.is_manager() or self.is_deputy())

    def can_view(self) -> bool:
        """
        Coarse-grained visibility helper.

        RETURNS TRUE FOR
        ----------------
        - admin
        - users assigned to a service unit

        IMPORTANT
        ---------
        This helper is useful for simple UI or guard checks, but it is not a
        substitute for scoped procurement / organization authorization rules.
        """
        return bool(self.is_admin or self.service_unit_id is not None)

    @property
    def display_name(self) -> str:
        """
        Preferred display label for the user.

        Falls back gracefully:
        - linked Personnel selected label
        - username
        """
        if self.personnel:
            display_selected = getattr(self.personnel, "display_selected_label", None)
            if callable(display_selected):
                value = display_selected()
                if value:
                    return value

            display_name = getattr(self.personnel, "display_name", None)
            if isinstance(display_name, str) and display_name.strip():
                return display_name.strip()

        return (self.username or "").strip()

    def __repr__(self) -> str:
        return f"<User {self.id}: {self.username}>"