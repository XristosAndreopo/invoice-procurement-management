"""
Audit logging helper utilities.
"""

import json
from flask import request
from flask_login import current_user

from .extensions import db
from .models import AuditLog


def serialize_model(instance):
    """
    Convert SQLAlchemy model to dictionary snapshot.
    """
    data = {}
    for column in instance.__table__.columns:
        value = getattr(instance, column.name)
        try:
            data[column.name] = str(value)
        except Exception:
            data[column.name] = None
    return data


def log_action(entity, action, before=None, after=None):
    """
    Create an audit log entry.

    Parameters:
        entity: SQLAlchemy model instance
        action: CREATE / UPDATE / DELETE
        before: dict (optional)
        after: dict (optional)
    """

    entry = AuditLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        username_snapshot=current_user.username if current_user.is_authenticated else None,
        entity_type=entity.__class__.__name__,
        entity_id=entity.id,
        action=action,
        before_data=json.dumps(before) if before else None,
        after_data=json.dumps(after) if after else None,
        ip_address=request.remote_addr,
    )

    db.session.add(entry)