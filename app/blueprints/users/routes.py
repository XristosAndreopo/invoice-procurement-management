"""
Enterprise User Management (Admin Only).

Enterprise rules enforced:
- Every User MUST link to exactly one Personnel (1-to-1).
- Admin selects Personnel from the organizational directory.
- UI is never trusted: all constraints are validated server-side.
- Personnel organizational assignment is the source of truth for ServiceUnit consistency.

ADMIN MODEL DECISION:
- Admin user is still linked to a normal Personnel record.
- That Personnel may be "neutral":
  - service_unit_id = None
  - directory_id = None
  - department_id = None
- Therefore admin users may exist without ServiceUnit assignment.

NON-ADMIN MODEL:
- Non-admin users must be service-bound.
- selected User.service_unit_id must match selected Personnel.service_unit_id
- if Personnel has no ServiceUnit, non-admin user cannot be created/updated

AUDIT:
- CREATE / UPDATE logged
- Flush before audit snapshot persistence

SECURITY:
- UI is never trusted.
- All service/unit/admin consistency checks are enforced server-side.
- SQLite is used in dev, but implementation remains PostgreSQL-ready.
"""

from __future__ import annotations

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)
from flask_login import login_required

from ...extensions import db
from ...models import User, ServiceUnit, Personnel
from ...security import admin_required
from ...audit import log_action, serialize_model


users_bp = Blueprint(
    "users",
    __name__,
    url_prefix="/users",
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _parse_optional_int(value: str | None):
    """Parse an optional int from form data. Returns None if empty/invalid."""
    if not value:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _available_personnel_for_user_dropdown(exclude_user_id: int | None = None):
    """
    Return active Personnel that can be linked to a User.

    Rule:
    - Personnel must be active
    - Personnel must NOT already have a user (1-to-1)
    - If editing an existing user, allow that user's current personnel
      so the form remains stable

    NOTE:
    - This includes "neutral" personnel records as valid options.
      That is required for admin users.
    - Organizational display is handled in template/model helpers.
    """
    query = (
        Personnel.query
        .filter(Personnel.is_active.is_(True))
        .order_by(Personnel.last_name.asc(), Personnel.first_name.asc())
        .all()
    )

    allowed = []
    for p in query:
        if p.user is None:
            allowed.append(p)
            continue

        if exclude_user_id and p.user and p.user.id == exclude_user_id:
            allowed.append(p)

    return allowed


def _validate_service_unit_exists(service_unit_id: int | None) -> bool:
    """
    Validate that a service unit exists when provided.

    SECURITY:
    - UI is never trusted; forged ids must be rejected.
    """
    if service_unit_id is None:
        return True
    return ServiceUnit.query.get(service_unit_id) is not None


def _validate_personnel_selection(personnel_id: int | None, allowed_personnel: list[Personnel]) -> Personnel | None:
    """
    Validate that selected personnel is:
    - present
    - active
    - allowed by 1-to-1 availability rules

    Returns the Personnel instance or None.
    """
    if personnel_id is None:
        return None

    allowed_ids = {p.id for p in allowed_personnel}
    if personnel_id not in allowed_ids:
        return None

    personnel = Personnel.query.get(personnel_id)
    if not personnel or not personnel.is_active:
        return None

    return personnel


def _normalize_user_service_assignment(*, is_admin: bool, service_unit_id: int | None, personnel: Personnel) -> tuple[int | None, str | None]:
    """
    Normalize and validate User.service_unit_id against the selected Personnel.

    Rules:
    - Admin:
      - may have service_unit_id = None
      - may optionally be assigned to a real ServiceUnit
      - if assigned, the ServiceUnit must exist (validated elsewhere)
      - admin may be linked to neutral personnel

    - Non-admin:
      - personnel.service_unit_id is mandatory
      - user.service_unit_id must match personnel.service_unit_id
      - if form leaves service blank, inherit from personnel

    Returns:
    - (normalized_service_unit_id, error_message)
    """
    if is_admin:
        return service_unit_id, None

    if not personnel.service_unit_id:
        return None, (
            "Το επιλεγμένο Προσωπικό δεν έχει ορισμένη Υπηρεσία. "
            "Δεν μπορεί να δημιουργηθεί ή να αποθηκευτεί non-admin χρήστης χωρίς υπηρεσία."
        )

    if service_unit_id is None:
        service_unit_id = personnel.service_unit_id

    if service_unit_id != personnel.service_unit_id:
        return None, (
            "Η Υπηρεσία του χρήστη πρέπει να ταυτίζεται με την Υπηρεσία "
            "του επιλεγμένου Προσωπικού."
        )

    return service_unit_id, None


# ---------------------------------------------------------------------
# LIST USERS
# ---------------------------------------------------------------------
@users_bp.route("/")
@login_required
@admin_required
def list_users():
    """Admin view: list all users."""
    users = User.query.order_by(User.username.asc()).all()

    return render_template(
        "users/list.html",
        users=users,
    )


# ---------------------------------------------------------------------
# CREATE USER
# ---------------------------------------------------------------------
@users_bp.route("/new", methods=["GET", "POST"])
@login_required
@admin_required
def create_user():
    """
    Create a new system user.

    Required:
    - username
    - password
    - personnel_id (must be active + unlinked)

    Organizational consistency:
    - Admin users:
      - may have no service unit
      - may be linked to neutral personnel

    - Non-admin users:
      - must be bound to a service unit
      - must match selected Personnel.service_unit_id
    """
    service_units = ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()
    personnel_list = _available_personnel_for_user_dropdown(exclude_user_id=None)

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        service_unit_id = _parse_optional_int(request.form.get("service_unit_id"))
        is_admin = bool(request.form.get("is_admin"))

        personnel_id = _parse_optional_int(request.form.get("personnel_id"))

        if not username or not password:
            flash("Username και password είναι υποχρεωτικά.", "danger")
            return redirect(url_for("users.create_user"))

        if User.query.filter_by(username=username).first():
            flash("Το username υπάρχει ήδη.", "danger")
            return redirect(url_for("users.create_user"))

        if not _validate_service_unit_exists(service_unit_id):
            flash("Μη έγκυρη υπηρεσία.", "danger")
            return redirect(url_for("users.create_user"))

        personnel = _validate_personnel_selection(personnel_id, personnel_list)
        if personnel is None:
            flash(
                "Πρέπει να επιλέξετε έγκυρο (ενεργό και μη συσχετισμένο) Προσωπικό.",
                "danger",
            )
            return redirect(url_for("users.create_user"))

        normalized_service_unit_id, error = _normalize_user_service_assignment(
            is_admin=is_admin,
            service_unit_id=service_unit_id,
            personnel=personnel,
        )
        if error:
            flash(error, "danger")
            return redirect(url_for("users.create_user"))

        user = User(
            username=username,
            is_admin=is_admin,
            is_active=True,
            personnel_id=personnel.id,
            service_unit_id=normalized_service_unit_id,
        )
        user.set_password(password)

        db.session.add(user)
        db.session.flush()

        log_action(
            user,
            "CREATE",
            before=None,
            after=serialize_model(user),
        )
        db.session.commit()

        flash("Ο χρήστης δημιουργήθηκε.", "success")
        return redirect(url_for("users.list_users"))

    return render_template(
        "users/new.html",
        service_units=service_units,
        personnel_list=personnel_list,
    )


# ---------------------------------------------------------------------
# EDIT USER
# ---------------------------------------------------------------------
@users_bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id: int):
    """
    Edit an existing user.

    Admin can:
    - change service_unit
    - activate/deactivate
    - toggle admin
    - reset password
    - change personnel link (only to eligible personnel; 1-to-1 enforced)

    Organizational consistency:
    - Admin users may remain without service_unit_id
    - Admin users may be linked to neutral personnel
    - Non-admin users must match selected Personnel.service_unit_id
    """
    user = User.query.get_or_404(user_id)
    service_units = ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()
    personnel_list = _available_personnel_for_user_dropdown(exclude_user_id=user.id)

    if request.method == "POST":
        before_snapshot = serialize_model(user)

        is_admin = bool(request.form.get("is_admin"))
        is_active = bool(request.form.get("is_active"))
        service_unit_id = _parse_optional_int(request.form.get("service_unit_id"))
        personnel_id = _parse_optional_int(request.form.get("personnel_id"))

        if not _validate_service_unit_exists(service_unit_id):
            flash("Μη έγκυρη υπηρεσία.", "danger")
            return redirect(url_for("users.edit_user", user_id=user.id))

        personnel = _validate_personnel_selection(personnel_id, personnel_list)
        if personnel is None:
            flash(
                "Μη έγκυρο Προσωπικό. Επιτρέπεται μόνο ενεργό και διαθέσιμο "
                "(ή το ήδη συνδεδεμένο).",
                "danger",
            )
            return redirect(url_for("users.edit_user", user_id=user.id))

        normalized_service_unit_id, error = _normalize_user_service_assignment(
            is_admin=is_admin,
            service_unit_id=service_unit_id,
            personnel=personnel,
        )
        if error:
            flash(error, "danger")
            return redirect(url_for("users.edit_user", user_id=user.id))

        user.is_admin = is_admin
        user.is_active = is_active
        user.service_unit_id = normalized_service_unit_id
        user.personnel_id = personnel.id

        new_password = (request.form.get("password") or "").strip()
        if new_password:
            user.set_password(new_password)

        db.session.flush()

        log_action(
            user,
            "UPDATE",
            before=before_snapshot,
            after=serialize_model(user),
        )
        db.session.commit()

        flash("Ο χρήστης ενημερώθηκε.", "success")
        return redirect(url_for("users.list_users"))

    return render_template(
        "users/edit.html",
        user=user,
        service_units=service_units,
        personnel_list=personnel_list,
    )