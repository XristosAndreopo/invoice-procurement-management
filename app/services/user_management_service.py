"""
app/services/user_management_service.py

User management page builders and mutation use-cases.

PURPOSE
-------
This module contains the non-route orchestration for the admin-only
`users` blueprint.

It is responsible for:
- loading dropdown/form data for create/edit pages
- validating personnel availability and service-unit consistency rules
- executing create/update user mutations
- emitting structured service-layer results for routes

WHY THIS MODULE EXISTS
----------------------
The source-of-truth `app/blueprints/users/routes.py` previously mixed:
- HTTP request handling
- ORM validation rules
- user/personnel/service-unit consistency logic
- persistence and audit logging

That made the route layer thicker than the architecture target for this
refactor stage.

This module moves the reusable orchestration out of the routes so that
`app/blueprints/users/routes.py` can remain focused on:
- decorators
- reading request data
- basic object loading
- calling service functions
- flashing and redirecting/rendering

ARCHITECTURAL BOUNDARY
----------------------
This module MAY:
- query ORM models
- validate business/application rules for user creation and editing
- mutate ORM entities
- write audit logs
- return page-context dictionaries and operation results

This module must NOT:
- register routes
- access Flask request/response globals directly
- render templates
- redirect
- flash directly

RULES ENFORCED HERE
-------------------
Enterprise constraints preserved from the source-of-truth routes module:
- Every User links to exactly one Personnel
- Selected Personnel must be active
- Selected Personnel must not already belong to another User,
  except when editing the same User
- Admin users always have `service_unit_id = None`
- Non-admin users must resolve to the selected Personnel.service_unit_id
- The UI is never trusted; server-side validation decides consistency
"""

from __future__ import annotations

from typing import Any

from ..audit import log_action, serialize_model
from ..extensions import db
from ..models import Personnel, ServiceUnit, User
from .operation_results import FlashMessage, OperationResult


def list_users_for_admin() -> list[User]:
    """
    Return all users ordered for the admin list page.

    This is intentionally tiny and could remain in the route layer, but the
    helper keeps user-related query intent discoverable in one place.
    """
    return User.query.order_by(User.username.asc()).all()


def build_create_user_page_context() -> dict[str, Any]:
    """
    Build template context for the create-user page.
    """
    return {
        "service_units": _load_service_units_for_dropdown(),
        "personnel_list": available_personnel_for_user_dropdown(exclude_user_id=None),
    }


def build_edit_user_page_context(user: User) -> dict[str, Any]:
    """
    Build template context for the edit-user page.
    """
    return {
        "user": user,
        "service_units": _load_service_units_for_dropdown(),
        "personnel_list": available_personnel_for_user_dropdown(exclude_user_id=user.id),
    }


def execute_create_user(
    *,
    username: str,
    password: str,
    service_unit_id: int | None,
    is_admin: bool,
    personnel_id: int | None,
) -> OperationResult:
    """
    Validate and create a new system user.

    ROUTE CONTRACT
    --------------
    The route is expected to:
    - parse and normalize raw HTTP form values before calling
    - emit returned flash messages
    - redirect/render based on `result.ok`
    """
    normalized_username = (username or "").strip()
    normalized_password = (password or "").strip()

    if not normalized_username or not normalized_password:
        return _failure("Username και password είναι υποχρεωτικά.")

    if User.query.filter_by(username=normalized_username).first():
        return _failure("Το username υπάρχει ήδη.")

    if not validate_service_unit_exists(service_unit_id):
        return _failure("Μη έγκυρη υπηρεσία.")

    allowed_personnel = available_personnel_for_user_dropdown(exclude_user_id=None)
    personnel = validate_personnel_selection(
        personnel_id=personnel_id,
        allowed_personnel=allowed_personnel,
    )
    if personnel is None:
        return _failure(
            "Πρέπει να επιλέξετε έγκυρο (ενεργό και μη συσχετισμένο) Προσωπικό."
        )

    normalized_service_unit_id, error = normalize_user_service_assignment(
        is_admin=is_admin,
        service_unit_id=service_unit_id,
        personnel=personnel,
    )
    if error:
        return _failure(error)

    user = User(
        username=normalized_username,
        is_admin=is_admin,
        is_active=True,
        personnel_id=personnel.id,
        service_unit_id=normalized_service_unit_id,
    )
    user.set_password(normalized_password)

    db.session.add(user)
    db.session.flush()

    log_action(
        user,
        "CREATE",
        before=None,
        after=serialize_model(user),
    )
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Ο χρήστης δημιουργήθηκε.", "success"),),
        entity_id=user.id,
    )


def execute_edit_user(
    *,
    user: User,
    is_admin: bool,
    is_active: bool,
    service_unit_id: int | None,
    personnel_id: int | None,
    new_password: str,
) -> OperationResult:
    """
    Validate and update an existing system user.
    """
    if not validate_service_unit_exists(service_unit_id):
        return _failure("Μη έγκυρη υπηρεσία.")

    allowed_personnel = available_personnel_for_user_dropdown(exclude_user_id=user.id)
    personnel = validate_personnel_selection(
        personnel_id=personnel_id,
        allowed_personnel=allowed_personnel,
    )
    if personnel is None:
        return _failure(
            "Μη έγκυρο Προσωπικό. Επιτρέπεται μόνο ενεργό και διαθέσιμο "
            "(ή το ήδη συνδεδεμένο)."
        )

    normalized_service_unit_id, error = normalize_user_service_assignment(
        is_admin=is_admin,
        service_unit_id=service_unit_id,
        personnel=personnel,
    )
    if error:
        return _failure(error)

    before_snapshot = serialize_model(user)

    user.is_admin = is_admin
    user.is_active = is_active
    user.service_unit_id = normalized_service_unit_id
    user.personnel_id = personnel.id

    normalized_new_password = (new_password or "").strip()
    if normalized_new_password:
        user.set_password(normalized_new_password)

    db.session.flush()

    log_action(
        user,
        "UPDATE",
        before=before_snapshot,
        after=serialize_model(user),
    )
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Ο χρήστης ενημερώθηκε.", "success"),),
        entity_id=user.id,
    )


def available_personnel_for_user_dropdown(
    exclude_user_id: int | None = None,
) -> list[Personnel]:
    """
    Return active Personnel that can be linked to a User.

    RULES
    -----
    - Personnel must be active
    - Personnel must not already have a linked User
    - When editing an existing User, keep that User's current Personnel eligible
    """
    candidates = (
        Personnel.query.filter(Personnel.is_active.is_(True))
        .order_by(Personnel.last_name.asc(), Personnel.first_name.asc())
        .all()
    )

    allowed: list[Personnel] = []
    for personnel in candidates:
        if personnel.user is None:
            allowed.append(personnel)
            continue

        if exclude_user_id and personnel.user and personnel.user.id == exclude_user_id:
            allowed.append(personnel)

    return allowed


def validate_service_unit_exists(service_unit_id: int | None) -> bool:
    """
    Validate that a referenced ServiceUnit exists when provided.

    NOTE
    ----
    This mirrors the source-of-truth route behavior exactly:
    - `None` is allowed here
    - non-existent ids are rejected
    """
    if service_unit_id is None:
        return True
    return ServiceUnit.query.get(service_unit_id) is not None


def validate_personnel_selection(
    *,
    personnel_id: int | None,
    allowed_personnel: list[Personnel],
) -> Personnel | None:
    """
    Validate a selected Personnel against availability rules.

    Returns the ORM Personnel row when valid, otherwise `None`.
    """
    if personnel_id is None:
        return None

    allowed_ids = {personnel.id for personnel in allowed_personnel}
    if personnel_id not in allowed_ids:
        return None

    personnel = Personnel.query.get(personnel_id)
    if not personnel or not personnel.is_active:
        return None

    return personnel


def normalize_user_service_assignment(
    *,
    is_admin: bool,
    service_unit_id: int | None,
    personnel: Personnel,
) -> tuple[int | None, str | None]:
    """
    Normalize and validate `User.service_unit_id` for the selected Personnel.

    RULES
    -----
    - Admin user: service_unit_id must always become NULL
    - Non-admin user:
      * selected Personnel must already belong to a ServiceUnit
      * resulting user.service_unit_id must match personnel.service_unit_id
      * when omitted, the value is auto-filled from Personnel
    """
    if is_admin:
        return None, None

    if not personnel.service_unit_id:
        return None, (
            "Το επιλεγμένο Προσωπικό δεν έχει ορισμένη Υπηρεσία. "
            "Δεν μπορεί να δημιουργηθεί ή να αποθηκευτεί non-admin χρήστης χωρίς υπηρεσία."
        )

    normalized_service_unit_id = service_unit_id
    if normalized_service_unit_id is None:
        normalized_service_unit_id = personnel.service_unit_id

    if normalized_service_unit_id != personnel.service_unit_id:
        return None, (
            "Η Υπηρεσία του χρήστη πρέπει να ταυτίζεται με την Υπηρεσία "
            "του επιλεγμένου Προσωπικού."
        )

    return normalized_service_unit_id, None


def _load_service_units_for_dropdown() -> list[ServiceUnit]:
    """
    Return ServiceUnit rows ordered for form dropdown rendering.
    """
    return ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()


def _failure(message: str, *, category: str = "danger") -> OperationResult:
    """
    Build a standard single-message failure result.
    """
    return OperationResult(
        ok=False,
        flashes=(FlashMessage(message, category),),
    )

