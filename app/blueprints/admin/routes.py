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

NEW:
- Excel import for Personnel (admin-only).
  Headers (Greek preferred):
    - ΑΓΜ (required)
    - ΟΝΟΜΑ (required)
    - ΕΠΩΝΥΜΟ (required)
    - ΑΕΜ, ΒΑΘΜΟΣ, ΕΙΔΙΚΟΤΗΤΑ (optional)
    - ΥΠΗΡΕΣΙΑ (optional): matches ServiceUnit by code OR short_name OR description

NOTES:
- UI is never trusted. All validations happen server-side.
- Audit must be recorded in the same transaction as the data change.
  Pattern: db.session.flush() -> log_action(...) -> db.session.commit()
"""

from __future__ import annotations

from functools import wraps
from typing import Optional
import unicodedata

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


def _normalize_header(text: str) -> str:
    """
    Normalize Excel headers:
    - lowercase
    - trim spaces
    - remove diacritics (e.g. Περιγραφή == Περιγραφη)
    """
    if text is None:
        return ""
    s = " ".join(str(text).strip().lower().split())
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")
    return s


def _safe_str(v) -> str:
    """Convert excel cell to trimmed string."""
    if v is None:
        return ""
    return str(v).strip()


def _match_service_unit(service_value: str) -> Optional[ServiceUnit]:
    """
    Match service unit from a text value.

    Tries (case-insensitive):
    - code
    - short_name
    - description
    """
    sv = service_value.strip()
    if not sv:
        return None

    # try exact-ish matches in order
    q = ServiceUnit.query
    # code match
    su = q.filter(ServiceUnit.code.isnot(None)).filter(ServiceUnit.code.ilike(sv)).first()
    if su:
        return su

    # short_name match
    su = q.filter(ServiceUnit.short_name.isnot(None)).filter(ServiceUnit.short_name.ilike(sv)).first()
    if su:
        return su

    # description match
    su = q.filter(ServiceUnit.description.ilike(sv)).first()
    if su:
        return su

    return None


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
# IMPORT PERSONNEL (EXCEL) - ADMIN ONLY
# -------------------------------------------------------
@admin_bp.route("/personnel/import", methods=["POST"])
@login_required
@admin_required
def import_personnel():
    """
    Import Personnel from Excel (admin-only).

    Required columns:
    - ΑΓΜ
    - ΟΝΟΜΑ
    - ΕΠΩΝΥΜΟ

    Optional columns:
    - ΑΕΜ
    - ΒΑΘΜΟΣ
    - ΕΙΔΙΚΟΤΗΤΑ
    - ΥΠΗΡΕΣΙΑ (matches ServiceUnit by code OR short_name OR description)

    Rules:
    - Skip rows missing required fields
    - Skip rows with AGM already existing in DB
    - All imported personnel are is_active=True by default
    - Audit CREATE per inserted Personnel
    """
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Δεν επιλέχθηκε αρχείο.", "danger")
        return redirect(url_for("admin.personnel_list"))

    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        flash("Επιτρέπεται μόνο αρχείο .xlsx", "danger")
        return redirect(url_for("admin.personnel_list"))

    try:
        import openpyxl
        wb = openpyxl.load_workbook(file, data_only=True)
        ws = wb.active
    except Exception:
        flash("Αποτυχία ανάγνωσης Excel. Ελέγξτε το αρχείο.", "danger")
        return redirect(url_for("admin.personnel_list"))

    # Header row
    try:
        header_cells = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    except StopIteration:
        flash("Το Excel είναι κενό.", "danger")
        return redirect(url_for("admin.personnel_list"))

    headers = [str(h).strip() if h is not None else "" for h in header_cells]
    idx_map = {_normalize_header(h): i for i, h in enumerate(headers) if _normalize_header(h)}

    # Greek + fallback english
    agm_idx = idx_map.get("αγμ", idx_map.get("agm"))
    first_idx = idx_map.get("ονομα", idx_map.get("first name", idx_map.get("first_name")))
    last_idx = idx_map.get("επωνυμο", idx_map.get("last name", idx_map.get("last_name")))

    aem_idx = idx_map.get("αεμ", idx_map.get("aem"))
    rank_idx = idx_map.get("βαθμος", idx_map.get("rank"))
    spec_idx = idx_map.get("ειδικοτητα", idx_map.get("specialty"))
    service_idx = idx_map.get("υπηρεσια", idx_map.get("service"))

    if agm_idx is None or first_idx is None or last_idx is None:
        flash("Το Excel πρέπει να έχει στήλες: ΑΓΜ, ΟΝΟΜΑ, ΕΠΩΝΥΜΟ (1η γραμμή).", "danger")
        return redirect(url_for("admin.personnel_list"))

    inserted_people: list[Personnel] = []
    skipped_missing = 0
    skipped_duplicate = 0
    skipped_bad_service = 0

    for row in ws.iter_rows(min_row=2, values_only=True):
        # Safe indexing
        def _cell(i: Optional[int]):
            if i is None:
                return None
            if i >= len(row):
                return None
            return row[i]

        agm = _safe_str(_cell(agm_idx))
        first_name = _safe_str(_cell(first_idx))
        last_name = _safe_str(_cell(last_idx))

        if not agm or not first_name or not last_name:
            skipped_missing += 1
            continue

        # Unique AGM
        if Personnel.query.filter_by(agm=agm).first():
            skipped_duplicate += 1
            continue

        aem = _safe_str(_cell(aem_idx)) or None
        rank = _safe_str(_cell(rank_idx)) or None
        specialty = _safe_str(_cell(spec_idx)) or None

        service_unit_id = None
        if service_idx is not None:
            service_val = _safe_str(_cell(service_idx))
            if service_val:
                su = _match_service_unit(service_val)
                if not su:
                    skipped_bad_service += 1
                    continue
                service_unit_id = su.id

        person = Personnel(
            agm=agm,
            aem=aem,
            rank=rank,
            specialty=specialty,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
            service_unit_id=service_unit_id,
        )
        db.session.add(person)
        inserted_people.append(person)

    if not inserted_people:
        flash(
            "Δεν εισήχθησαν εγγραφές. "
            "Ελέγξτε required πεδία/διπλότυπα/Υπηρεσία.",
            "warning",
        )
        return redirect(url_for("admin.personnel_list"))

    db.session.flush()

    for person in inserted_people:
        log_action(person, "CREATE", before=None, after=serialize_model(person))

    db.session.commit()

    flash(
        f"Εισαγωγή ολοκληρώθηκε: {len(inserted_people)} νέες εγγραφές. "
        f"Παραλείφθηκαν: {skipped_missing} (ελλιπή), {skipped_duplicate} (διπλότυπα ΑΓΜ), "
        f"{skipped_bad_service} (μη έγκυρη Υπηρεσία).",
        "success",
    )
    return redirect(url_for("admin.personnel_list"))


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

        existing = Personnel.query.filter(Personnel.agm == agm, Personnel.id != person.id).first()
        if existing:
            flash("Υπάρχει ήδη προσωπικό με αυτό το ΑΓΜ.", "danger")
            return redirect(url_for("admin.edit_personnel", personnel_id=person.id))

        if not _validate_service_unit_id(service_unit_id):
            flash("Μη έγκυρη υπηρεσία.", "danger")
            return redirect(url_for("admin.edit_personnel", personnel_id=person.id))

        person.agm = agm
        person.aem = aem or None
        person.rank = rank or None
        person.specialty = specialty or None
        person.first_name = first_name
        person.last_name = last_name
        person.service_unit_id = service_unit_id
        person.is_active = is_active

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