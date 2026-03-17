"""
app/models/feedback.py

User feedback / complaint / suggestion model.

PURPOSE
-------
This module defines the Feedback entity used for the application's
complaints / suggestions flow.

WHY THIS FILE EXISTS
--------------------
Feedback is a distinct supporting domain:

- it is not procurement workflow data
- it is not organizational hierarchy data
- it is not master-data configuration
- it is not authentication/user-account data

It deserves its own dedicated model module because it has its own lifecycle:
- user submits feedback
- admins review / manage it
- status may change over time

ARCHITECTURAL BOUNDARY
----------------------
This module defines:
- persistence schema
- lightweight display helpers
- basic status/timestamp fields

This module must NOT become the place for:
- admin moderation workflow orchestration
- notification sending
- filtering / reporting query logic
- route-level form handling
- permission enforcement

Those responsibilities belong in:
- app.services.*
- route / blueprint handlers
- security layer

IMPORTANT
---------
This model should remain intentionally simple. It stores the feedback record
itself, not the full management workflow around it.
"""

from __future__ import annotations

from datetime import datetime

from ..extensions import db


class Feedback(db.Model):
    """
    Feedback / complaint / suggestion submitted through the application.

    TYPICAL USE CASES
    -----------------
    - bug report
    - complaint
    - improvement suggestion
    - general comment

    LIFECYCLE
    ---------
    A feedback row is usually:
    1. created by a user
    2. reviewed by admins
    3. optionally marked with a workflow status

    DESIGN NOTE
    -----------
    This model is intentionally generic so the application can support a simple
    feedback channel without introducing unnecessary subtype complexity.
    """

    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(255), nullable=True)
    email = db.Column(db.String(255), nullable=True)

    subject = db.Column(db.String(255), nullable=True)
    message = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(50), nullable=False, default="new", index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    @property
    def display_name(self) -> str:
        """
        Preferred short label for lists/admin screens.

        Priority:
        1. subject
        2. first part of message
        3. fallback id label
        """
        subject = (self.subject or "").strip()
        if subject:
            return subject

        message = (self.message or "").strip()
        if message:
            return message[:60] + ("…" if len(message) > 60 else "")

        return f"Feedback #{self.id}"

    @property
    def sender_display(self) -> str:
        """
        Human-readable sender label for admin views.
        """
        name = (self.name or "").strip()
        email = (self.email or "").strip()

        if name and email:
            return f"{name} <{email}>"
        return name or email or "Ανώνυμος"

    @property
    def is_new(self) -> bool:
        """
        Return True when the feedback is still in the initial state.
        """
        return (self.status or "").strip().lower() == "new"

    def __repr__(self) -> str:
        return f"<Feedback {self.id}: {self.display_name}>"

