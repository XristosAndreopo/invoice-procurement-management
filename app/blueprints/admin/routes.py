"""
app/blueprints/admin/routes.py

Admin Routes – Enterprise Administration Module

Includes:
- Personnel Management (organizational directory)
- Protected by admin-only access

Enterprise requirements implemented here:
- Admin-only CRUD for Personnel
- Personnel can be assigned to a ServiceUnit (needed for handler filtering)
- Audit logging for CREATE / UPDATE

NOTES:
- UI is never trusted. All validations happen server-side.
- Audit must be recorded in the same transaction as the data change.
  Pattern: db.session.flush() -> log_action(...) -> db.session.commit()
"""

from __future__ import annotations

from functools import wraps
from typing import Optional

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    abort,
)
from flask_login import login_required, current_user

from ...extensions import db
from ...models import Personnel, ServiceUnit
from ...audit import log_action, serialize_model

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# -------------------------------------------------------
# ADMIN PROTECTION DECORATOR
# -------------------------------------------------------
def admin_required(func):
    """
    Ensure only admin users can access route.

    SECURITY:
    - Server-side enforcement (UI never trusted).
    - Returns HTTP 403 if user is not authenticated admin.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, "is_admin", False):
            abort(403)
        return func(*args, **kwargs)

    return wrapper


# -------------------------------------------------------
# HELPERS
# -------------------------------------------------------
def _parse_optional_int(value: str) -> Optional[int]:
    """Parse optional integer from form. Returns None if empty/invalid."""
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _service_units_for_dropdown():
    """ServiceUnits for dropdown selection."""
    return ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()


def _validate_service_unit_id(service_unit_id: Optional[int]) -> bool:
    """
    Return True if service_unit_id is None or exists in DB.

    SECURITY:
    - Prevents forging a service_unit_id that doesn't exist.
    """
    if service_unit_id is None:
        return True
    return ServiceUnit.query.get(service_unit_id) is not None


# -------------------------------------------------------
# PERSONNEL LIST
# -------------------------------------------------------
@admin_bp.route("/personnel")
@login_required
@admin_required
def personnel_list():
    """List organizational personnel (admin only)."""
    personnel = (
        Personnel.query.order_by(
            Personnel.rank.asc(),
            Personnel.last_name.asc(),
            Personnel.first_name.asc(),
        ).all()
    )

    return render_template("admin/personnel_list.html", personnel=personnel)


# -------------------------------------------------------
# CREATE PERSONNEL
# -------------------------------------------------------
@admin_bp.route("/personnel/new", methods=["GET", "POST"])
@login_required
@admin_required
def create_personnel():
    """Create new Personnel record (admin only)."""
    service_units = _service_units_for_dropdown()

    if request.method == "POST":
        agm = request.form.get("agm", "").strip()
        aem = request.form.get("aem", "").strip()
        rank = request.form.get("rank", "").strip()
        specialty = request.form.get("specialty", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()

        service_unit_id = _parse_optional_int((request.form.get("service_unit_id") or "").strip())

        # Validations (server-side)
        if not agm or not first_name or not last_name:
            flash("ΑΓΜ, Όνομα και Επώνυμο είναι υποχρεωτικά.", "danger")
            return redirect(url_for("admin.create_personnel"))

        if Personnel.query.filter_by(agm=agm).first():
            flash("Υπάρχει ήδη προσωπικό με αυτό το ΑΓΜ.", "danger")
            return redirect(url_for("admin.create_personnel"))

        if not _validate_service_unit_id(service_unit_id):
            flash("Μη έγκυρη υπηρεσία.", "danger")
            return redirect(url_for("admin.create_personnel"))

        person = Personnel(
            agm=agm,
            aem=aem or None,
            rank=rank or None,
            specialty=specialty or None,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
            service_unit_id=service_unit_id,
        )

        # Transaction: add -> flush (id exists) -> audit -> commit (once)
        db.session.add(person)
        db.session.flush()

        log_action(person, "CREATE", before=None, after=serialize_model(person))
        db.session.commit()

        flash("Το προσωπικό καταχωρήθηκε.", "success")
        return redirect(url_for("admin.personnel_list"))

    return render_template(
        "admin/personnel_form.html",
        person=None,
        form_title="Νέο Προσωπικό",
        service_units=service_units,
    )


# -------------------------------------------------------
# EDIT PERSONNEL
# -------------------------------------------------------
@admin_bp.route("/personnel/<int:personnel_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_personnel(personnel_id: int):
    """
    Edit Personnel (admin only).

    Admin can:
    - update fields
    - assign/change ServiceUnit
    - activate/deactivate

    ENTERPRISE:
    - Audit UPDATE in the same transaction.
    """
    person = Personnel.query.get_or_404(personnel_id)
    service_units = _service_units_for_dropdown()

    if request.method == "POST":
        before_snapshot = serialize_model(person)

        agm = request.form.get("agm", "").strip()
        aem = request.form.get("aem", "").strip()
        rank = request.form.get("rank", "").strip()
        specialty = request.form.get("specialty", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()

        service_unit_id = _parse_optional_int((request.form.get("service_unit_id") or "").strip())
        is_active = bool(request.form.get("is_active"))

        # Validations (server-side)
        if not agm or not first_name or not last_name:
            flash("ΑΓΜ, Όνομα και Επώνυμο είναι υποχρεωτικά.", "danger")
            return redirect(url_for("admin.edit_personnel", personnel_id=person.id))

        # AGM unique check excluding self
        existing = Personnel.query.filter(Personnel.agm == agm, Personnel.id != person.id).first()
        if existing:
            flash("Υπάρχει ήδη προσωπικό με αυτό το ΑΓΜ.", "danger")
            return redirect(url_for("admin.edit_personnel", personnel_id=person.id))

        if not _validate_service_unit_id(service_unit_id):
            flash("Μη έγκυρη υπηρεσία.", "danger")
            return redirect(url_for("admin.edit_personnel", personnel_id=person.id))

        # Apply updates
        person.agm = agm
        person.aem = aem or None
        person.rank = rank or None
        person.specialty = specialty or None
        person.first_name = first_name
        person.last_name = last_name
        person.service_unit_id = service_unit_id
        person.is_active = is_active

        # Transaction: flush -> audit -> commit (once)
        db.session.flush()
        log_action(person, "UPDATE", before=before_snapshot, after=serialize_model(person))
        db.session.commit()

        flash("Το προσωπικό ενημερώθηκε.", "success")
        return redirect(url_for("admin.personnel_list"))

    return render_template(
        "admin/personnel_form.html",
        person=person,
        form_title="Επεξεργασία Προσωπικού",
        service_units=service_units,
    )