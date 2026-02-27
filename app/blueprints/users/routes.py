"""
Enterprise User Management (Admin Only).

Enterprise rules enforced:
- Every User MUST link to exactly one Personnel (1-to-1).
- Admin selects Personnel from the organizational directory.
- UI never trusted: we validate server-side.

Audit:
- CREATE / UPDATE logged
"""

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


def _parse_optional_int(value: str):
    """Parse an optional int from form data. Returns None if empty/invalid."""
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _available_personnel_for_user_dropdown(exclude_user_id: int | None = None):
    """
    Returns active Personnel that can be linked to a User.

    Rule:
    - Personnel must be active
    - Personnel must NOT already have a user (1-to-1)
    - If editing an existing user, allow that user's current personnel
      (so form doesn't break).
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

        # If editing: allow the currently linked personnel for that user
        if exclude_user_id and p.user and p.user.id == exclude_user_id:
            allowed.append(p)

    return allowed


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
    """
    service_units = ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()
    personnel_list = _available_personnel_for_user_dropdown(exclude_user_id=None)

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        service_unit_id = _parse_optional_int((request.form.get("service_unit_id") or "").strip())
        is_admin = bool(request.form.get("is_admin"))

        personnel_id = _parse_optional_int((request.form.get("personnel_id") or "").strip())

        if not username or not password:
            flash("Username και password είναι υποχρεωτικά.", "danger")
            return redirect(url_for("users.create_user"))

        if User.query.filter_by(username=username).first():
            flash("Το username υπάρχει ήδη.", "danger")
            return redirect(url_for("users.create_user"))

        allowed_personnel_ids = {p.id for p in personnel_list}
        if personnel_id is None or personnel_id not in allowed_personnel_ids:
            flash("Πρέπει να επιλέξετε έγκυρο (ενεργό και μη συσχετισμένο) Προσωπικό.", "danger")
            return redirect(url_for("users.create_user"))

        user = User(
            username=username,
            is_admin=is_admin,
            is_active=True,
            personnel_id=personnel_id,
            service_unit_id=service_unit_id,
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

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
def edit_user(user_id):
    """
    Edit an existing user.

    Admin can:
    - change service_unit
    - activate/deactivate
    - toggle admin
    - reset password
    - change personnel link (only to eligible personnel; 1-to-1 enforced)
    """
    user = User.query.get_or_404(user_id)
    service_units = ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()
    personnel_list = _available_personnel_for_user_dropdown(exclude_user_id=user.id)

    if request.method == "POST":
        before_snapshot = serialize_model(user)

        user.is_admin = bool(request.form.get("is_admin"))
        user.is_active = bool(request.form.get("is_active"))

        service_unit_id = _parse_optional_int((request.form.get("service_unit_id") or "").strip())
        user.service_unit_id = service_unit_id

        personnel_id = _parse_optional_int((request.form.get("personnel_id") or "").strip())
        allowed_personnel_ids = {p.id for p in personnel_list}
        if personnel_id is None or personnel_id not in allowed_personnel_ids:
            flash("Μη έγκυρο Προσωπικό. Επιτρέπεται μόνο ενεργό και διαθέσιμο (ή το ήδη συνδεδεμένο).", "danger")
            return redirect(url_for("users.edit_user", user_id=user.id))

        user.personnel_id = personnel_id

        new_password = (request.form.get("password") or "").strip()
        if new_password:
            user.set_password(new_password)

        db.session.commit()

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