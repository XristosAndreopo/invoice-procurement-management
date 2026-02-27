"""
Security / Authorization helpers.

Centralized authorization logic for:

- Service isolation
- Role-based access
- Procurement-level access control

IMPORTANT:
UI is NEVER trusted.
All security decisions are enforced here.
"""

from functools import wraps
from flask import abort
from flask_login import current_user

from .models import Procurement


# ---------------------------------------------------------------------
# BASIC ROLE CHECKS
# ---------------------------------------------------------------------

def admin_required(func):
    """
    Allow only global administrators.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return func(*args, **kwargs)
    return wrapper


def manager_required(func):
    """
    Allow only manager or deputy of a service unit.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(403)

        if not (current_user.is_admin or current_user.can_manage()):
            abort(403)

        return func(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------
# PROCUREMENT ACCESS CONTROL
# ---------------------------------------------------------------------

def procurement_access_required(func):
    """
    Ensures user can ACCESS a procurement.

    Rules:
    - Admin → access everything
    - Others → only procurements of their own service_unit
    """
    @wraps(func)
    def wrapper(procurement_id, *args, **kwargs):
        procurement = Procurement.query.get_or_404(procurement_id)

        # Admin bypass
        if current_user.is_admin:
            return func(procurement_id, *args, **kwargs)

        # Must belong to same service unit
        if procurement.service_unit_id != current_user.service_unit_id:
            abort(403)

        return func(procurement_id, *args, **kwargs)

    return wrapper


def procurement_edit_required(func):
    """
    Ensures user can EDIT a procurement.

    Rules:
    - Admin → always
    - Manager/Deputy → only their service
    - Viewer → forbidden
    """
    @wraps(func)
    def wrapper(procurement_id, *args, **kwargs):
        procurement = Procurement.query.get_or_404(procurement_id)

        if current_user.is_admin:
            return func(procurement_id, *args, **kwargs)

        # Must belong to same service
        if procurement.service_unit_id != current_user.service_unit_id:
            abort(403)

        # Must be manager or deputy
        if not current_user.can_manage():
            abort(403)

        return func(procurement_id, *args, **kwargs)

    return wrapper