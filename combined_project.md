PROJECT: Invoice Management System

FILE: .\app\__init__.py
```python
"""
app/__init__.py

Flask application factory entrypoint for the Invoice / Procurement Management
System.

PURPOSE
-------
This module is intentionally small.

It is responsible only for:
- creating the Flask application instance
- loading configuration
- delegating application wiring to bootstrap helpers

WHY THIS FILE IS NOW SMALL
--------------------------
In the previous structure, this module also contained:
- navigation metadata
- sidebar visibility helpers
- blueprint registration
- request hooks
- context processors
- CLI registration
- root route registration
- Flask-Login wiring

Those responsibilities have been extracted so this file can remain the single,
clear entrypoint of the application factory.

DESIGN PRINCIPLE
----------------
`app/__init__.py` should answer only one question:

    "How is the Flask app instance created?"

Everything else belongs to dedicated modules.

PUBLIC API
----------
- create_app()

BEHAVIOR
--------
No functional behavior is intended to change through this refactor.
The goal is structural clarity and easier maintenance.
"""

from __future__ import annotations

from flask import Flask

from app.presentation import init_presentation

from .bootstrap import configure_app


def create_app() -> Flask:
    """
    Application factory.

    RETURNS
    -------
    Flask
        Fully configured Flask application instance.

    BOOTSTRAP FLOW
    --------------
    1. Create app
    2. Load config
    3. Delegate full wiring to bootstrap helpers
    """
    app = Flask(__name__)
    app.config.from_object("config.Config")
    configure_app(app)
    init_presentation(app)
    return app


```

FILE: .\app\audit\__init__.py
```python
"""
app/audit/__init__.py

Public audit facade for the Invoice / Procurement Management System.

PURPOSE
-------
This package provides the stable public import surface for audit helpers used
across the application.

PACKAGE STRUCTURE
-----------------
- app.audit.serialization
    Audit snapshot preparation / model serialization

- app.audit.logging
    AuditLog row construction and session insertion

- app.audit
    Backwards-compatible public facade

TRANSACTION BEHAVIOR
--------------------
Audit helpers add rows to the current SQLAlchemy session but do NOT commit.
The caller remains responsible for transaction boundaries.
"""

from __future__ import annotations

from .logging import (
    build_audit_entry,
    current_audit_user_id,
    current_audit_username_snapshot,
    current_request_ip_address,
    log_action,
)
from .serialization import safe_audit_value, serialize_model, snapshot_to_json

__all__ = [
    "safe_audit_value",
    "serialize_model",
    "snapshot_to_json",
    "current_audit_user_id",
    "current_audit_username_snapshot",
    "current_request_ip_address",
    "build_audit_entry",
    "log_action",
]


```

FILE: .\app\audit\audit.py
```python
"""
app/audit/audit.py

Legacy audit compatibility facade.

PURPOSE
-------
This file preserves the historical module path `app.audit.audit` while
`app.audit` remains the canonical public facade.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add audit logic here.
- Import from `app.audit` in all new code.
"""

from __future__ import annotations

from . import *  # noqa: F401,F403

```

FILE: .\app\audit\logging.py
```python
"""
app/audit_logging.py

AuditLog row creation helpers.

PURPOSE
-------
This module is responsible for assembling and adding `AuditLog` rows to the
current SQLAlchemy session.

WHY THIS FILE EXISTS
--------------------
Previously, `app/audit.py` contained both:
- snapshot serialization helpers
- AuditLog persistence logic

This module isolates the persistence side so that:
- transaction-related audit behavior is easier to find
- actor / request metadata extraction is centralized
- the main public `app.audit` facade stays small

TRANSACTION BEHAVIOR
--------------------
This module adds `AuditLog` rows to the current SQLAlchemy session, but it does
NOT commit. The caller owns transaction boundaries.

WHY THIS MATTERS
----------------
Audit logging should usually participate in the same transaction as the related
business mutation. That keeps the data change and its audit trail aligned.

SUPPORTED CALL STYLES
---------------------
Preferred:
    log_action(entity=entity, action="UPDATE", before=..., after=...)

Backward-compatible positional:
    log_action(entity, "UPDATE", before=..., after=...)
"""

from __future__ import annotations

from typing import Any

from flask import request
from flask_login import current_user

from .serialization import snapshot_to_json
from ..extensions import db
from ..models import AuditLog


def current_audit_user_id() -> int | None:
    """
    Return the authenticated user's id, if available.

    RETURNS
    -------
    int | None
        Authenticated user id or None for anonymous/system contexts.
    """
    if current_user.is_authenticated:
        return current_user.id
    return None


def current_audit_username_snapshot() -> str | None:
    """
    Return a stable username snapshot for audit persistence.

    WHY SNAPSHOT THE USERNAME
    -------------------------
    Even if the username changes later, the audit row should preserve the
    identity label as it existed when the action happened.

    RETURNS
    -------
    str | None
        Current authenticated username or None.
    """
    if current_user.is_authenticated:
        return current_user.username
    return None


def current_request_ip_address() -> str | None:
    """
    Return the client IP address as Flask currently sees it.

    IMPORTANT
    ---------
    In reverse-proxy production deployments, ProxyFix / trusted proxy headers
    should be configured correctly so this reflects the real client IP.

    RETURNS
    -------
    str | None
        Remote IP string or None.
    """
    return request.remote_addr


def build_audit_entry(
    *,
    entity: Any,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    """
    Build an `AuditLog` ORM instance without adding it to the session yet.

    PARAMETERS
    ----------
    entity:
        SQLAlchemy model instance with an `id`.
    action:
        Action name, usually CREATE / UPDATE / DELETE.
    before:
        Optional snapshot before mutation.
    after:
        Optional snapshot after mutation.

    RETURNS
    -------
    AuditLog
        New AuditLog ORM object.

    RAISES
    ------
    ValueError
        If the entity has no id.

    IMPORTANT
    ---------
    The entity must already have an id, so for CREATE operations this should
    normally be called after `flush()`.
    """
    entity_id = getattr(entity, "id", None)
    if entity_id is None:
        raise ValueError("log_action entity must have an 'id' attribute (usually after flush).")

    return AuditLog(
        user_id=current_audit_user_id(),
        username_snapshot=current_audit_username_snapshot(),
        entity_type=entity.__class__.__name__,
        entity_id=int(entity_id),
        action=str(action),
        before_data=snapshot_to_json(before),
        after_data=snapshot_to_json(after),
        ip_address=current_request_ip_address(),
    )


def log_action(
    entity: Any = None,
    action: str | None = None,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    entity_kw: Any = None,
    action_kw: str | None = None,
) -> None:
    """
    Add an AuditLog entry to the current SQLAlchemy session.

    SUPPORTED CALL STYLES
    ---------------------
    Preferred:
        log_action(entity=entity, action="UPDATE", before=..., after=...)

    Backward-compatible positional:
        log_action(entity, "UPDATE", before=..., after=...)

    PARAMETERS
    ----------
    entity:
        SQLAlchemy model instance with an `id`.
    action:
        Action name, usually CREATE / UPDATE / DELETE.
    before:
        Optional dict snapshot before the change.
    after:
        Optional dict snapshot after the change.

    RAISES
    ------
    TypeError
        If entity or action are missing.
    ValueError
        If entity has no id.

    IMPORTANT
    ---------
    This helper only adds the audit row to the current SQLAlchemy session.
    It does not commit.
    """
    # ---------------------------------------------------------------
    # Backward-compatible keyword aliases
    # ---------------------------------------------------------------
    if entity is None and entity_kw is not None:
        entity = entity_kw
    if action is None and action_kw is not None:
        action = action_kw

    if entity is None or action is None:
        raise TypeError("log_action requires 'entity' and 'action'.")

    entry = build_audit_entry(
        entity=entity,
        action=action,
        before=before,
        after=after,
    )
    db.session.add(entry)


```

FILE: .\app\audit\serialization.py
```python
"""
app/audit_serialization.py

Serialization helpers for audit logging.

PURPOSE
-------
This module is responsible only for turning model state into compact,
deterministic audit-friendly snapshots.

WHY THIS FILE EXISTS
--------------------
Previously, `app/audit.py` mixed:
- snapshot serialization helpers
- current request / current user metadata extraction
- AuditLog row creation

Those are related but not the same responsibility.

This module isolates the snapshot side of audit logging so that:
- model serialization rules live in one place
- future changes to snapshot formatting stay localized
- audit persistence logic remains smaller and easier to read

AUDIT SNAPSHOT PHILOSOPHY
-------------------------
Audit snapshots should be:
- compact
- deterministic
- safe to JSON-encode
- independent from ORM relationship graphs

Therefore, snapshots include:
- only scalar table-column values
- no relationships
- values converted to stable strings where needed

IMPORTANT
---------
This module does not write to the database.
It only prepares audit-safe data structures.
"""

from __future__ import annotations

import json
from typing import Any, Optional


def safe_audit_value(value: Any) -> Optional[str]:
    """
    Convert a value to a DB- and JSON-safe string representation.

    PARAMETERS
    ----------
    value:
        Any scalar-ish Python value extracted from a model column.

    RETURNS
    -------
    str | None
        Safe string representation, or None when the original value is None.

    WHY THIS EXISTS
    ---------------
    Audit snapshots are stored as JSON text. We want the persisted form to be
    deterministic and easy to inspect, while avoiding unexpected serializer
    behavior for special value types.

    CURRENT STRATEGY
    ----------------
    - None stays None
    - everything else is converted with str(...)
    """
    if value is None:
        return None
    return str(value)


def serialize_model(instance: Any) -> dict[str, Optional[str]]:
    """
    Serialize a SQLAlchemy model instance into an audit snapshot dict.

    WHAT IS INCLUDED
    ----------------
    - Only table columns
    - No relationships
    - Values converted to strings for safe JSON persistence

    WHY RELATIONSHIPS ARE EXCLUDED
    ------------------------------
    Relationship graphs can be large, recursive, lazy-loaded, and unstable for
    auditing purposes. Audit snapshots should be compact and deterministic.

    PARAMETERS
    ----------
    instance:
        A SQLAlchemy model instance with `__table__.columns`.

    RETURNS
    -------
    dict[str, Optional[str]]
        Mapping of column name -> safe string value.
    """
    data: dict[str, Optional[str]] = {}

    for column in instance.__table__.columns:
        data[column.name] = safe_audit_value(getattr(instance, column.name))

    return data


def snapshot_to_json(data: dict[str, Any] | None) -> str | None:
    """
    Convert a snapshot dict to JSON safely for storage.

    PARAMETERS
    ----------
    data:
        Snapshot dictionary or None.

    RETURNS
    -------
    str | None
        JSON string with UTF-8 characters preserved, or None if input is empty.

    NOTES
    -----
    `ensure_ascii=False` is intentional so Greek content remains human-readable
    in stored audit rows.
    """
    if not data:
        return None
    return json.dumps(data, ensure_ascii=False)


```

FILE: .\app\blueprints\__init__.py
```python


```

FILE: .\app\blueprints\admin\__init__.py
```python
"""
Admin blueprint package.
"""

from .routes import admin_bp  # noqa: F401


```

FILE: .\app\blueprints\admin\routes.py
```python
"""
app/blueprints/admin/routes.py

Admin Routes – Enterprise Administration Module
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ...models import Personnel
from ...security import admin_required
from ...security.admin_guards import (
    admin_or_manager_required,
    ensure_personnel_manage_scope_or_403,
)
from ...services.admin.organization_setup import (
    build_organization_setup_page_context,
    execute_organization_setup_action,
)
from ...services.admin.personnel import (
    build_personnel_form_page_context,
    build_personnel_list_page_context,
    execute_create_personnel,
    execute_delete_personnel,
    execute_edit_personnel,
    execute_import_personnel,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/personnel")
@login_required
@admin_or_manager_required
def personnel_list():
    context = build_personnel_list_page_context()
    return render_template("admin/personnel_list.html", **context)


@admin_bp.route("/personnel/import", methods=["POST"])
@login_required
@admin_required
def import_personnel():
    result = execute_import_personnel(request.files.get("file"))
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(url_for("admin.personnel_list"))


@admin_bp.route("/personnel/new", methods=["GET", "POST"])
@login_required
@admin_or_manager_required
def create_personnel():
    if request.method == "POST":
        result = execute_create_personnel(
            request.form,
            is_admin=getattr(current_user, "is_admin", False),
            current_service_unit_id=getattr(current_user, "service_unit_id", None),
        )
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("admin.personnel_list"))

        return redirect(url_for("admin.create_personnel"))

    context = build_personnel_form_page_context(
        person=None,
        form_title="Νέο Προσωπικό",
    )
    return render_template("admin/personnel_form.html", **context)


@admin_bp.route("/personnel/<int:personnel_id>/edit", methods=["GET", "POST"])
@login_required
@admin_or_manager_required
def edit_personnel(personnel_id: int):
    person = Personnel.query.get_or_404(personnel_id)
    ensure_personnel_manage_scope_or_403(person)

    if request.method == "POST":
        result = execute_edit_personnel(
            person,
            request.form,
            is_admin=getattr(current_user, "is_admin", False),
            current_service_unit_id=getattr(current_user, "service_unit_id", None),
        )
        for item in result.flashes:
            flash(item.message, item.category)

        return redirect(url_for("admin.edit_personnel", personnel_id=person.id))

    context = build_personnel_form_page_context(
        person=person,
        form_title="Επεξεργασία Προσωπικού",
    )
    return render_template("admin/personnel_form.html", **context)


@admin_bp.route("/organization-setup", methods=["GET", "POST"])
@login_required
@admin_or_manager_required
def organization_setup():
    if request.method == "POST":
        result = execute_organization_setup_action(
            request.form,
            files=request.files,
            is_admin=getattr(current_user, "is_admin", False),
            current_service_unit_id=getattr(current_user, "service_unit_id", None),
        )
        for item in result.flashes:
            flash(item.message, item.category)

        if result.redirect_service_unit_id is not None:
            return redirect(
                url_for(
                    "admin.organization_setup",
                    service_unit_id=result.redirect_service_unit_id,
                )
            )

        return redirect(url_for("admin.organization_setup"))

    context = build_organization_setup_page_context(
        request.args,
        is_admin=getattr(current_user, "is_admin", False),
        current_service_unit_id=getattr(current_user, "service_unit_id", None),
    )
    return render_template("admin/organization_setup.html", **context)


@admin_bp.route("/personnel/<int:personnel_id>/delete", methods=["POST"])
@login_required
@admin_or_manager_required
def delete_personnel(personnel_id: int):
    person = Personnel.query.get_or_404(personnel_id)
    ensure_personnel_manage_scope_or_403(person)

    result = execute_delete_personnel(person)
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(url_for("admin.personnel_list"))

```

FILE: .\app\blueprints\auth\__init__.py
```python
"""
Auth blueprint package.

This file just exposes the Blueprint object to be imported in app.__init__. 
The actual routes and logic are in routes.py. 
"""

from .routes import auth_bp  # noqa: F401


```

FILE: .\app\blueprints\auth\routes.py
```python
"""
app/blueprints/auth/routes.py

Authentication routes for the Invoice / Procurement Management System.

PROVIDES
--------
- /auth/login
- /auth/logout
- /auth/seed-admin

ARCHITECTURAL INTENT
--------------------
This file is route-focused.

Routes should remain responsible only for:
- decorators
- request data reads
- Flask-Login session calls
- final HTTP branching
- flash / redirect / render_template

NON-HTTP ORCHESTRATION HAS BEEN EXTRACTED TO
--------------------------------------------
- app/services/auth_service.py

DECISIONS FOR THIS REFACTOR PASS
--------------------------------
1. login
   - extracted to focused auth service for credential validation and safe next
     resolution

2. logout
   - stabilized as-is because it is already thin and purely HTTP/session
     orchestration

3. seed-admin
   - extracted to focused auth service for bootstrap validation and persistence

SECURITY MODEL
--------------
- UI is never trusted.
- Only active users may log in.
- Password validation is always server-side.
- The bootstrap admin route is self-locking after first user creation.
- Every system user must be linked to a Personnel record.

IMPORTANT BOUNDARY
------------------
This module must not re-absorb business/application orchestration back into the
route layer. If future auth flows become more complex, they should expand the
focused auth service module rather than fattening the routes again.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ...services.auth_service import (
    build_login_page_context,
    build_seed_admin_page_context,
    execute_login,
    execute_seed_admin,
    should_block_seed_admin,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Authenticate a user.

    ROUTE RESPONSIBILITIES
    ----------------------
    - redirect already-authenticated users away from login
    - read request form/query values
    - call service-layer validation
    - establish Flask-Login session on success
    - emit flash messages and final response
    """
    if current_user.is_authenticated:
        return redirect(url_for("procurements.inbox_procurements"))

    raw_next = request.args.get("next") or request.form.get("next")

    if request.method == "POST":
        result = execute_login(request.form, raw_next)
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok and result.user is not None and result.redirect_url:
            login_user(result.user)
            return redirect(result.redirect_url)

        context = build_login_page_context(raw_next)
        return render_template("auth/login.html", **context)

    context = build_login_page_context(raw_next)
    return render_template("auth/login.html", **context)


@auth_bp.route("/logout")
@login_required
def logout():
    """
    Log out the current user.

    STABILIZE DECISION
    ------------------
    This route already matches the target architecture:
    - pure HTTP/session boundary concern
    - no business orchestration
    - no need for service extraction
    """
    logout_user()
    flash("Αποσυνδεθήκατε.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/seed-admin", methods=["GET", "POST"])
def seed_admin():
    """
    Bootstrap the first admin of the system.

    ROUTE RESPONSIBILITIES
    ----------------------
    - enforce the self-locking redirect when bootstrap is already closed
    - read submitted form data
    - call service-layer creation orchestration
    - emit flash messages and final response
    """
    if should_block_seed_admin():
        flash("Υπάρχει ήδη χρήστης στο σύστημα.", "warning")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        result = execute_seed_admin(request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("auth.login"))

        context = build_seed_admin_page_context()
        return render_template("auth/seed_admin.html", **context)

    context = build_seed_admin_page_context()
    return render_template("auth/seed_admin.html", **context)


```

FILE: .\app\blueprints\procurements\__init__.py
```python
"""
app/blueprints/procurements/__init__.py

Blueprint package export.

IMPORTANT:
- Must expose procurements_bp for app factory registration.
- Keep import minimal to avoid side effects.
"""

from __future__ import annotations

from .routes import procurements_bp  # noqa: F401


```

FILE: .\app\blueprints\procurements\routes.py
```python
"""
app/blueprints/procurements/routes.py

Procurement routes – Enterprise Secured Version
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from flask import (
    Blueprint,
    abort,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import Procurement, ProcurementSupplier
from ...reports.award_decision_docx import AwardDecisionConstants, build_award_decision_docx
from ...reports.expense_transmittal_docx import (
    ExpenseTransmittalConstants,
    build_expense_transmittal_docx,
    build_expense_transmittal_filename,
)
from ...reports.proforma_invoice import ProformaConstants, build_proforma_invoice_pdf
from ...security import procurement_access_required, procurement_edit_required
from ...security.procurement_guards import can_mutate_procurement
from ...services.shared.parsing import next_from_request
from ...services.procurement.create import (
    build_create_procurement_page_context,
    execute_create_procurement,
)
from ...services.procurement.edit import (
    build_edit_procurement_page_context,
    execute_edit_procurement,
)
from ...services.procurement.implementation import (
    build_implementation_procurement_page_context,
    execute_implementation_procurement_update,
)
from ...services.procurement.list_pages import (
    build_all_procurements_list_context,
    build_inbox_procurements_list_context,
    build_pending_expenses_list_context,
)
from ...services.procurement.related_entities import (
    execute_add_material_line,
    execute_add_procurement_supplier,
    execute_delete_material_line,
    execute_delete_procurement_supplier,
)
from ...services.procurement_service import (
    is_in_implementation_phase,
    load_procurement,
    money_filename,
    sanitize_filename_component,
)

procurements_bp = Blueprint("procurements", __name__, url_prefix="/procurements")


@procurements_bp.route("/inbox")
@login_required
def inbox_procurements():
    context = build_inbox_procurements_list_context(
        request.args,
        allow_create=(current_user.is_admin or current_user.can_manage()),
    )
    return render_template("procurements/list.html", **context)


@procurements_bp.route("/pending-expenses")
@login_required
def pending_expenses():
    context = build_pending_expenses_list_context(request.args)
    return render_template("procurements/list.html", **context)


@procurements_bp.route("/all")
@login_required
def all_procurements():
    context = build_all_procurements_list_context(request.args)
    return render_template("procurements/list.html", **context)


@procurements_bp.route("/")
@login_required
def list_procurements():
    return redirect(url_for("procurements.inbox_procurements"))


@procurements_bp.route("/<int:procurement_id>/delete", methods=["POST"])
@login_required
@procurement_edit_required(load_procurement)
def delete_procurement(procurement_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)

    if not can_mutate_procurement(current_user, procurement):
        abort(403)

    origin = (request.form.get("delete_origin") or "").strip()
    if origin != "all_procurements":
        flash("Η διαγραφή επιτρέπεται μόνο από τη σελίδα «Όλες οι Προμήθειες».", "warning")
        return redirect(url_for("procurements.all_procurements"))

    next_url = (request.form.get("next") or "").strip()
    before_snapshot = serialize_model(procurement)

    db.session.delete(procurement)
    log_action(procurement, "DELETE", before=before_snapshot, after=None)
    db.session.commit()

    flash("Η προμήθεια διαγράφηκε επιτυχώς.", "success")
    return redirect(next_url or url_for("procurements.all_procurements"))


@procurements_bp.route("/<int:procurement_id>/reports/proforma-invoice", methods=["GET"])
@login_required
@procurement_access_required(load_procurement)
def report_proforma_invoice(procurement_id: int):
    """
    Render the proforma invoice PDF.
    """
    procurement = (
        Procurement.query.options(
            joinedload(Procurement.service_unit),
            joinedload(Procurement.handler_personnel),
            joinedload(Procurement.handler_assignment).joinedload(
                Procurement.handler_assignment.property.mapper.class_.department
            ),
            joinedload(Procurement.handler_assignment).joinedload(
                Procurement.handler_assignment.property.mapper.class_.directory
            ),
            joinedload(Procurement.supplies_links).joinedload(ProcurementSupplier.supplier),
            joinedload(Procurement.materials),
            joinedload(Procurement.withholding_profile),
            joinedload(Procurement.income_tax_rule),
        )
        .get_or_404(procurement_id)
    )

    winner = procurement.winner_supplier_obj()
    analysis = procurement.compute_payment_analysis()

    lines = list(procurement.materials or [])
    has_services = any(bool(getattr(line, "is_service", False)) for line in lines)
    table_title = "Πίνακας Παρεχόμενων Υπηρεσιών" if has_services else "Πίνακας Προμηθευτέων Υλικών"

    pdf_bytes = build_proforma_invoice_pdf(
        procurement=procurement,
        service_unit=procurement.service_unit,
        winner=winner,
        analysis=analysis,
        table_title=table_title,
        constants=ProformaConstants(
            pn_afm="090153025",
            pn_doy="ΚΕΦΟΔΕ ΑΤΤΙΚΗΣ",
            reference_goods="ΒΤ-11-1",
        ),
    )

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'inline; filename="proforma_{procurement.id}.pdf"'
    return response


@procurements_bp.route("/<int:procurement_id>/reports/award-decision", methods=["GET"])
@login_required
@procurement_access_required(load_procurement)
def report_award_decision_docx(procurement_id: int):
    """
    Build and return the Award Decision DOCX.
    """
    procurement = (
        Procurement.query.options(
            joinedload(Procurement.service_unit),
            joinedload(Procurement.handler_personnel),
            joinedload(Procurement.handler_assignment).joinedload(
                Procurement.handler_assignment.property.mapper.class_.directory
            ),
            joinedload(Procurement.handler_assignment).joinedload(
                Procurement.handler_assignment.property.mapper.class_.department
            ),
            joinedload(Procurement.supplies_links).joinedload(ProcurementSupplier.supplier),
            joinedload(Procurement.materials),
            joinedload(Procurement.withholding_profile),
            joinedload(Procurement.income_tax_rule),
        )
        .get_or_404(procurement_id)
    )

    winner = procurement.winner_supplier_obj()

    other_suppliers = []
    for link in (procurement.supplies_links or []):
        if not getattr(link, "supplier", None):
            continue
        if getattr(link, "is_winner", False):
            continue
        other_suppliers.append(link.supplier)

    analysis = procurement.compute_payment_analysis()
    lines = list(procurement.materials or [])
    is_services = any(bool(getattr(line, "is_service", False)) for line in lines)

    docx_bytes = build_award_decision_docx(
        procurement=procurement,
        service_unit=procurement.service_unit,
        winner=winner,
        other_suppliers=other_suppliers,
        analysis=analysis,
        is_services=is_services,
        constants=AwardDecisionConstants(),
    )

    kind_label = "Παροχής Υπηρεσιών" if is_services else "Προμήθειας Υλικών"
    supplier_label = sanitize_filename_component(getattr(winner, "name", None) if winner else "—")

    amount_value = getattr(procurement, "grand_total", None)
    if amount_value is None:
        amount_value = analysis.get("payable_total") or analysis.get("sum_total") or Decimal("0.00")
    amount_label = money_filename(amount_value)

    filename = f"Απόφαση Ανάθεσης {kind_label} {supplier_label} {amount_label}.docx"
    filename = sanitize_filename_component(filename).replace(" .docx", ".docx")
    if not filename.lower().endswith(".docx"):
        filename = f"{filename}.docx"

    buffer = BytesIO(docx_bytes)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        max_age=0,
    )


@procurements_bp.route("/<int:procurement_id>/reports/expense-transmittal", methods=["GET"])
@login_required
@procurement_access_required(load_procurement)
def report_expense_transmittal_docx(procurement_id: int):
    """
    Build and return the Expense Transmittal DOCX.

    REQUIRED RELATIONSHIPS
    ----------------------
    This report needs:
    - service_unit
    - winner supplier
    - materials
    - withholding_profile / income_tax_rule for payment analysis
    - committee

    SOURCE OF TRUTH MAPPINGS
    ------------------------
    The template references committee/invoice/handler-like values.
    These are resolved from the current model contract:
    - procurement.committee.description
    - procurement.invoice_number
    - procurement.invoice_date
    - procurement.materials_receipt_date
    - procurement.invoice_receipt_date
    - service_unit.supply_officer
    """
    procurement = (
        Procurement.query.options(
            joinedload(Procurement.service_unit),
            joinedload(Procurement.handler_personnel),
            joinedload(Procurement.handler_assignment).joinedload(
                Procurement.handler_assignment.property.mapper.class_.directory
            ),
            joinedload(Procurement.handler_assignment).joinedload(
                Procurement.handler_assignment.property.mapper.class_.department
            ),
            joinedload(Procurement.committee),
            joinedload(Procurement.supplies_links).joinedload(ProcurementSupplier.supplier),
            joinedload(Procurement.materials),
            joinedload(Procurement.withholding_profile),
            joinedload(Procurement.income_tax_rule),
        )
        .get_or_404(procurement_id)
    )

    winner = procurement.winner_supplier_obj()
    analysis = procurement.compute_payment_analysis()

    docx_bytes = build_expense_transmittal_docx(
        procurement=procurement,
        service_unit=procurement.service_unit,
        winner=winner,
        analysis=analysis,
        constants=ExpenseTransmittalConstants(),
    )

    filename = build_expense_transmittal_filename(
        procurement=procurement,
        winner=winner,
    )
    filename = sanitize_filename_component(filename).replace(" .docx", ".docx")
    if not filename.lower().endswith(".docx"):
        filename = f"{filename}.docx"

    buffer = BytesIO(docx_bytes)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        max_age=0,
    )


@procurements_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_procurement():
    if not (current_user.is_admin or current_user.can_manage()):
        abort(403)

    if request.method == "POST":
        if not current_user.is_admin and not current_user.service_unit_id:
            abort(403)

        result = execute_create_procurement(
            request.form,
            is_admin=current_user.is_admin,
            current_service_unit_id=current_user.service_unit_id,
        )
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok and result.entity_id is not None:
            return redirect(
                url_for(
                    "procurements.edit_procurement",
                    procurement_id=result.entity_id,
                )
            )

        return redirect(url_for("procurements.create_procurement"))

    context = build_create_procurement_page_context(
        is_admin=current_user.is_admin,
        current_service_unit_id=current_user.service_unit_id,
    )
    return render_template("procurements/new.html", **context)


@procurements_bp.route("/<int:procurement_id>/edit", methods=["GET", "POST"])
@login_required
@procurement_access_required(load_procurement)
def edit_procurement(procurement_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)
    next_url = next_from_request("procurements.inbox_procurements")

    if request.method == "POST":
        if not can_mutate_procurement(current_user, procurement):
            abort(403)

        result = execute_edit_procurement(
            procurement,
            request.form,
            is_admin=current_user.is_admin,
        )
        for item in result.flashes:
            flash(item.message, item.category)

        return redirect(
            url_for(
                "procurements.edit_procurement",
                procurement_id=procurement.id,
                next=next_url,
            )
        )

    context = build_edit_procurement_page_context(procurement, next_url)
    return render_template("procurements/edit.html", **context)


@procurements_bp.route("/<int:procurement_id>/implementation", methods=["GET", "POST"])
@login_required
@procurement_access_required(load_procurement)
def implementation_procurement(procurement_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)

    if not is_in_implementation_phase(procurement):
        return redirect(url_for("procurements.edit_procurement", procurement_id=procurement.id))

    next_url = next_from_request("procurements.pending_expenses")

    if request.method == "POST":
        if not can_mutate_procurement(current_user, procurement):
            abort(403)

        result = execute_implementation_procurement_update(procurement, request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        return redirect(
            url_for(
                "procurements.implementation_procurement",
                procurement_id=procurement.id,
                next=next_url,
            )
        )

    context = build_implementation_procurement_page_context(
        procurement,
        next_url,
        can_edit=can_mutate_procurement(current_user, procurement),
    )
    return render_template("procurements/implementation.html", **context)


@procurements_bp.route("/<int:procurement_id>/suppliers/add", methods=["POST"])
@login_required
@procurement_edit_required(load_procurement)
def add_procurement_supplier(procurement_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)
    next_url = next_from_request("procurements.inbox_procurements")

    result = execute_add_procurement_supplier(procurement, request.form)
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(
        url_for(
            "procurements.edit_procurement",
            procurement_id=procurement.id,
            next=next_url,
        )
    )


@procurements_bp.route("/<int:procurement_id>/suppliers/<int:link_id>/delete", methods=["POST"])
@login_required
@procurement_edit_required(load_procurement)
def delete_procurement_supplier(procurement_id: int, link_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)
    next_url = next_from_request("procurements.inbox_procurements")

    result = execute_delete_procurement_supplier(procurement, link_id)
    if result.not_found:
        abort(404)

    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(
        url_for(
            "procurements.edit_procurement",
            procurement_id=procurement.id,
            next=next_url,
        )
    )


@procurements_bp.route("/<int:procurement_id>/materials/add", methods=["POST"])
@login_required
@procurement_edit_required(load_procurement)
def add_material_line(procurement_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)
    next_url = next_from_request("procurements.inbox_procurements")

    result = execute_add_material_line(procurement, request.form)
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(
        url_for(
            "procurements.edit_procurement",
            procurement_id=procurement.id,
            next=next_url,
        )
    )


@procurements_bp.route("/<int:procurement_id>/materials/<int:line_id>/delete", methods=["POST"])
@login_required
@procurement_edit_required(load_procurement)
def delete_material_line(procurement_id: int, line_id: int):
    procurement = Procurement.query.get_or_404(procurement_id)
    next_url = next_from_request("procurements.inbox_procurements")

    result = execute_delete_material_line(procurement, line_id)
    if result.not_found:
        abort(404)

    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(
        url_for(
            "procurements.edit_procurement",
            procurement_id=procurement.id,
            next=next_url,
        )
    )

```

FILE: .\app\blueprints\settings\__init__.py
```python
"""
Settings blueprint package.
"""

from .routes import settings_bp  # noqa: F401


```

FILE: .\app\blueprints\settings\routes.py
```python
"""
app/blueprints/settings/routes.py

Settings & Master Data routes.

OVERVIEW
--------
This blueprint contains the application's settings and master-data management
screens.

ARCHITECTURAL DECISION FOR THIS PASS
------------------------------------
This file now follows a mixed strategy based on the actual current state from
`combined_project.md`:

1. STABILIZE, NOT DECOMPOSE
   - ServiceUnit routes
   - Supplier routes
   These routes are already sufficiently thin because their orchestration has
   already moved into focused service modules.

2. EXTRACT USE-CASE / PAGE SERVICES
   - Theme
   - Feedback
   - Feedback admin
   - ALE-KAE
   - CPV
   - Generic option-value pages
   - IncomeTaxRule
   - WithholdingProfile
   - Committees

3. SECURITY GUARD CONSOLIDATION
   - committee scope guard
   - legacy structure redirect scope guard

ROUTE BOUNDARY
--------------
Routes in this module should now remain responsible only for:
- decorators
- reading request.args / request.form / request.files
- boundary object loads where appropriate
- calling a focused service/use-case function
- flash(...)
- render_template(...)
- redirect(...)

IMPORTANT SOURCE-OF-TRUTH NOTE
------------------------------
`combined_project.md` currently contains at least two visible inconsistencies
outside the code changed in this pass:

1. `app/models/feedback.py` does not visibly define fields used by the current
   settings routes (`user_id`, `category`, `related_procurement_id`).

2. The current ServiceUnit model/service excerpts show inconsistent deputy field
   naming (`deputy_personnel_id` vs `deputy_manager_personnel_id`).

Those issues are not changed here because this pass is focused on the route
refactor boundary, and the instruction was to avoid assumptions beyond the
actual provided source of truth.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ...models import ServiceUnit, Supplier
from ...security import admin_required, manager_required
from ...security.settings_guards import ensure_settings_structure_scope_or_403
from ...services.settings.theme import (
    build_theme_page_context,
    execute_theme_update,
)
from ...services.settings.feedback import (
    build_feedback_admin_page_context,
    build_feedback_page_context,
    execute_feedback_admin_status_update,
    execute_feedback_submission,
)
from ...services.settings.master_data_admin import (
    build_ale_kae_page_context,
    build_cpv_page_context,
    build_income_tax_rules_page_context,
    build_option_values_page_context,
    build_withholding_profiles_page_context,
    execute_ale_kae_action,
    execute_cpv_action,
    execute_import_ale_kae,
    execute_import_cpv,
    execute_income_tax_rule_action,
    execute_option_value_action,
    execute_withholding_profile_action,
)
from ...services.settings.committees import (
    build_committees_page_context,
    execute_committee_action,
)
from ...services.settings.service_units import (
    build_service_unit_form_page_context,
    build_service_unit_roles_form_page_context,
    build_service_units_list_page_context,
    build_service_units_roles_page_context,
    execute_assign_service_unit_roles,
    execute_create_service_unit,
    execute_delete_service_unit,
    execute_edit_service_unit_info,
    execute_import_service_units,
)
from ...services.settings.suppliers import (
    build_supplier_form_page_context,
    build_suppliers_list_page_context,
    execute_create_supplier,
    execute_delete_supplier,
    execute_edit_supplier,
    execute_import_suppliers,
)

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


# ----------------------------------------------------------------------
# THEME (all users)
# ----------------------------------------------------------------------
@settings_bp.route("/theme", methods=["GET", "POST"])
@login_required
def theme():
    """
    Allow any logged-in user to select their UI theme.

    NOTE
    ----
    This remains one of the few mutating actions allowed even for read-only
    users, as handled by the global readonly guard allow-list.
    """
    if request.method == "POST":
        result = execute_theme_update(current_user, request.form)
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(url_for("settings.theme"))

    context = build_theme_page_context()
    return render_template("settings/theme.html", **context)


# ----------------------------------------------------------------------
# FEEDBACK (all users)
# ----------------------------------------------------------------------
@settings_bp.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    """
    Feedback / complaint submission form for logged-in users.
    """
    if request.method == "POST":
        result = execute_feedback_submission(
            user_id=current_user.id,
            form_data=request.form,
        )
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(url_for("settings.feedback"))

    context = build_feedback_page_context(user_id=current_user.id)
    return render_template("settings/feedback.html", **context)


# ----------------------------------------------------------------------
# FEEDBACK ADMIN (admin only)
# ----------------------------------------------------------------------
@settings_bp.route("/feedback/admin", methods=["GET", "POST"])
@login_required
@admin_required
def feedback_admin():
    """
    Admin-only review and management page for all feedback submissions.
    """
    if request.method == "POST":
        result = execute_feedback_admin_status_update(request.form)
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(url_for("settings.feedback_admin"))

    context = build_feedback_admin_page_context(request.args)
    return render_template("settings/feedback_admin.html", **context)


# ----------------------------------------------------------------------
# SERVICE UNITS (admin-only) -- STABILIZE ONLY
# ----------------------------------------------------------------------
@settings_bp.route("/service-units")
@login_required
@admin_required
def service_units_list():
    """List ServiceUnits basic info."""
    context = build_service_units_list_page_context()
    return render_template("settings/service_units_list.html", **context)


@settings_bp.route("/service-units/roles")
@login_required
@admin_required
def service_units_roles_list():
    """List ServiceUnits with Manager/Deputy assignments."""
    context = build_service_units_roles_page_context()
    return render_template("settings/service_units_roles_list.html", **context)


@settings_bp.route("/service-units/new", methods=["GET", "POST"])
@login_required
@admin_required
def service_unit_create():
    """Create a new ServiceUnit."""
    if request.method == "POST":
        result = execute_create_service_unit(request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("settings.service_units_list"))
        return redirect(url_for("settings.service_unit_create"))

    context = build_service_unit_form_page_context(
        unit=None,
        form_title="Νέα Υπηρεσία",
        is_create=True,
    )
    return render_template("settings/service_unit_form.html", **context)


@settings_bp.route("/service-units/import", methods=["POST"])
@login_required
@admin_required
def service_units_import():
    """
    Import ServiceUnits from Excel.
    """
    result = execute_import_service_units(request.files.get("file"))
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(url_for("settings.service_units_list"))


@settings_bp.route("/service-units/<int:unit_id>/edit-info", methods=["GET", "POST"])
@login_required
@admin_required
def service_unit_edit_info(unit_id: int):
    """Edit basic ServiceUnit fields."""
    unit = ServiceUnit.query.get_or_404(unit_id)

    if request.method == "POST":
        result = execute_edit_service_unit_info(unit, request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("settings.service_units_list"))
        return redirect(url_for("settings.service_unit_edit_info", unit_id=unit.id))

    context = build_service_unit_form_page_context(
        unit=unit,
        form_title="Επεξεργασία Υπηρεσίας",
        is_create=False,
    )
    return render_template("settings/service_unit_form.html", **context)


@settings_bp.route("/service-units/<int:unit_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def service_unit_edit(unit_id: int):
    """Assign Manager / Deputy for a ServiceUnit."""
    unit = ServiceUnit.query.get_or_404(unit_id)

    if request.method == "POST":
        result = execute_assign_service_unit_roles(unit, request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("settings.service_units_roles_list"))
        return redirect(url_for("settings.service_unit_edit", unit_id=unit.id))

    context = build_service_unit_roles_form_page_context(
        unit=unit,
        form_title="Ορισμός Deputy/Manager",
    )
    return render_template("settings/service_unit_roles_form.html", **context)


@settings_bp.route("/service-units/<int:unit_id>/delete", methods=["POST"])
@login_required
@admin_required
def service_unit_delete(unit_id: int):
    """Delete a ServiceUnit using a defensive SQLite-safe strategy."""
    unit = ServiceUnit.query.get_or_404(unit_id)

    result = execute_delete_service_unit(unit)
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(url_for("settings.service_units_list"))


# ----------------------------------------------------------------------
# LEGACY: SERVICE UNIT STRUCTURE (compatibility redirect)
# ----------------------------------------------------------------------
@settings_bp.route("/service-units/<int:unit_id>/structure", methods=["GET", "POST"])
@login_required
@manager_required
def service_unit_structure(unit_id: int):
    """
    Backward-compatibility redirect to the consolidated organization page.

    This route remains intentionally thin. It is a compatibility boundary,
    not a business workflow.
    """
    unit = ServiceUnit.query.get_or_404(unit_id)
    ensure_settings_structure_scope_or_403(unit.id)
    return redirect(url_for("admin.organization_setup", service_unit_id=unit.id))


# ----------------------------------------------------------------------
# SUPPLIERS CRUD (admin only) -- STABILIZE ONLY
# ----------------------------------------------------------------------
@settings_bp.route("/suppliers")
@login_required
@admin_required
def suppliers_list():
    """List suppliers."""
    context = build_suppliers_list_page_context()
    return render_template("settings/suppliers_list.html", **context)


@settings_bp.route("/suppliers/new", methods=["GET", "POST"])
@login_required
@admin_required
def supplier_create():
    """Create a supplier."""
    if request.method == "POST":
        result = execute_create_supplier(request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("settings.suppliers_list"))
        return redirect(url_for("settings.supplier_create"))

    context = build_supplier_form_page_context(
        supplier=None,
        form_title="Νέος Προμηθευτής",
    )
    return render_template("settings/supplier_form.html", **context)


@settings_bp.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def supplier_edit(supplier_id: int):
    """Edit a supplier."""
    supplier = Supplier.query.get_or_404(supplier_id)

    if request.method == "POST":
        result = execute_edit_supplier(supplier, request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("settings.suppliers_list"))
        return redirect(url_for("settings.supplier_edit", supplier_id=supplier.id))

    context = build_supplier_form_page_context(
        supplier=supplier,
        form_title="Επεξεργασία Προμηθευτή",
    )
    return render_template("settings/supplier_form.html", **context)


@settings_bp.route("/suppliers/<int:supplier_id>/delete", methods=["POST"])
@login_required
@admin_required
def supplier_delete(supplier_id: int):
    """Delete a supplier."""
    supplier = Supplier.query.get_or_404(supplier_id)

    result = execute_delete_supplier(supplier)
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(url_for("settings.suppliers_list"))


@settings_bp.route("/suppliers/import", methods=["POST"])
@login_required
@admin_required
def suppliers_import():
    """
    Import Suppliers from Excel.
    """
    result = execute_import_suppliers(request.files.get("file"))
    for item in result.flashes:
        flash(item.message, item.category)

    return redirect(url_for("settings.suppliers_list"))


# ----------------------------------------------------------------------
# ALE-KAE (admin-only) + Excel import
# ----------------------------------------------------------------------
@settings_bp.route("/ale-kae", methods=["GET", "POST"])
@login_required
@admin_required
def ale_kae():
    """Admin-only CRUD page for ALE-KAE."""
    if request.method == "POST":
        result = execute_ale_kae_action(request.form)
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(url_for("settings.ale_kae"))

    context = build_ale_kae_page_context()
    return render_template("settings/ale_kae.html", **context)


@settings_bp.route("/ale-kae/import", methods=["POST"])
@login_required
@admin_required
def ale_kae_import():
    """Admin-only Excel import for ALE-KAE."""
    result = execute_import_ale_kae(request.files.get("file"))
    for item in result.flashes:
        flash(item.message, item.category)
    return redirect(url_for("settings.ale_kae"))


# ----------------------------------------------------------------------
# CPV (admin-only) + Excel import
# ----------------------------------------------------------------------
@settings_bp.route("/cpv", methods=["GET", "POST"])
@login_required
@admin_required
def cpv():
    """Admin-only CRUD page for CPV."""
    if request.method == "POST":
        result = execute_cpv_action(request.form)
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(url_for("settings.cpv"))

    context = build_cpv_page_context()
    return render_template("settings/cpv.html", **context)


@settings_bp.route("/cpv/import", methods=["POST"])
@login_required
@admin_required
def cpv_import():
    """Admin-only Excel import for CPV."""
    result = execute_import_cpv(request.files.get("file"))
    for item in result.flashes:
        flash(item.message, item.category)
    return redirect(url_for("settings.cpv"))


# ----------------------------------------------------------------------
# OPTION VALUES + IncomeTax + Withholding + Committees
# ----------------------------------------------------------------------
def _options_page(key: str, label: str):
    """
    Shared HTTP-only route helper for generic OptionValue category pages.

    WHY THIS HELPER REMAINS HERE
    ----------------------------
    This helper now performs only HTTP orchestration:
    - call service for POST or GET context
    - flash messages
    - render / redirect

    Query composition, validation, persistence, and category bootstrap live in
    the dedicated settings master-data service module.
    """
    if request.method == "POST":
        result = execute_option_value_action(key=key, label=label, form_data=request.form)
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(request.path)

    context = build_option_values_page_context(key=key, label=label)
    return render_template("settings/options_values.html", **context)


@settings_bp.route("/options/status", methods=["GET", "POST"])
@login_required
@admin_required
def options_status():
    """CRUD for status options."""
    return _options_page(key="KATASTASH", label="Κατάσταση")


@settings_bp.route("/options/stage", methods=["GET", "POST"])
@login_required
@admin_required
def options_stage():
    """CRUD for stage options."""
    return _options_page(key="STADIO", label="Στάδιο")


@settings_bp.route("/options/allocation", methods=["GET", "POST"])
@login_required
@admin_required
def options_allocation():
    """CRUD for allocation options."""
    return _options_page(key="KATANOMH", label="Κατανομή")


@settings_bp.route("/options/quarterly", methods=["GET", "POST"])
@login_required
@admin_required
def options_quarterly():
    """CRUD for quarterly options."""
    return _options_page(key="TRIMHNIAIA", label="Τριμηνιαία")


@settings_bp.route("/options/vat", methods=["GET", "POST"])
@login_required
@admin_required
def options_vat():
    """CRUD for VAT options."""
    return _options_page(key="FPA", label="ΦΠΑ")


@settings_bp.route("/income-tax", methods=["GET", "POST"])
@login_required
@admin_required
def income_tax_rules():
    """CRUD for IncomeTaxRule master data."""
    if request.method == "POST":
        result = execute_income_tax_rule_action(request.form)
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(request.path)

    context = build_income_tax_rules_page_context()
    return render_template("settings/income_tax_rules.html", **context)


@settings_bp.route("/withholding-profiles", methods=["GET", "POST"])
@login_required
@admin_required
def withholding_profiles():
    """CRUD for WithholdingProfile master data."""
    if request.method == "POST":
        result = execute_withholding_profile_action(request.form)
        for item in result.flashes:
            flash(item.message, item.category)
        return redirect(request.path)

    context = build_withholding_profiles_page_context()
    return render_template("settings/withholding_profiles.html", **context)


@settings_bp.route("/committees", methods=["GET", "POST"])
@login_required
@manager_required
def committees():
    """
    Procurement committees management.

    SCOPE RULES
    -----------
    - admin: may select any service unit
    - manager/deputy: forced to own service unit server-side
    """
    if request.method == "POST":
        result = execute_committee_action(request.form)
        for item in result.flashes:
            flash(item.message, item.category)

        redirect_service_unit_id = result.entity_id
        if redirect_service_unit_id:
            return redirect(url_for("settings.committees", service_unit_id=redirect_service_unit_id))
        return redirect(url_for("settings.committees"))

    context = build_committees_page_context(request.args)
    return render_template("settings/committees.html", **context)


```

FILE: .\app\blueprints\users\__init__.py
```python
"""
Users management blueprint (Admin only).
"""

from .routes import users_bp


```

FILE: .\app\blueprints\users\routes.py
```python
"""
Enterprise User Management (Admin Only).

Enterprise rules enforced:
- Every User MUST link to exactly one Personnel (1-to-1).
- Admin selects Personnel from the organizational directory.
- UI is never trusted: all constraints are validated server-side.
- Personnel organizational assignment is the source of truth for ServiceUnit consistency.

ROUTE LAYER INTENT
------------------
This module is intentionally kept thin.

Routes here should do only:
- decorators and HTTP boundary protection
- reading `request.form`
- basic object loading (`get_or_404`)
- calling service-layer functions
- translating service results into `flash(...)`, `redirect(...)`, and `render_template(...)`

Non-route orchestration lives in:
- `app/services/user_management_service.py`
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ...models import User
from ...security import admin_required
from ...services.shared.parsing import parse_optional_int
from ...services.user_management_service import (
    build_create_user_page_context,
    build_edit_user_page_context,
    execute_create_user,
    execute_edit_user,
    list_users_for_admin,
)

users_bp = Blueprint(
    "users",
    __name__,
    url_prefix="/users",
)


@users_bp.route("/")
@login_required
@admin_required
def list_users():
    """
    Admin view: list all users.

    ARCHITECTURAL DECISION
    ---------------------
    Stabilize, not decompose further.

    This route is already thin:
    - authorization only
    - one list query via service helper
    - direct template render
    """
    users = list_users_for_admin()
    return render_template("users/list.html", users=users)


@users_bp.route("/new", methods=["GET", "POST"])
@login_required
@admin_required
def create_user():
    """
    Create a new system user.
    """
    if request.method == "POST":
        result = execute_create_user(
            username=(request.form.get("username") or "").strip(),
            password=(request.form.get("password") or "").strip(),
            service_unit_id=parse_optional_int(request.form.get("service_unit_id")),
            is_admin=bool(request.form.get("is_admin")),
            personnel_id=parse_optional_int(request.form.get("personnel_id")),
        )

        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("users.list_users"))

        return redirect(url_for("users.create_user"))

    context = build_create_user_page_context()
    return render_template("users/new.html", **context)


@users_bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id: int):
    """
    Edit an existing user.
    """
    user = User.query.get_or_404(user_id)

    if request.method == "POST":
        result = execute_edit_user(
            user=user,
            is_admin=bool(request.form.get("is_admin")),
            is_active=bool(request.form.get("is_active")),
            service_unit_id=parse_optional_int(request.form.get("service_unit_id")),
            personnel_id=parse_optional_int(request.form.get("personnel_id")),
            new_password=(request.form.get("password") or "").strip(),
        )

        for item in result.flashes:
            flash(item.message, item.category)

        if result.ok:
            return redirect(url_for("users.list_users"))

        return redirect(url_for("users.edit_user", user_id=user.id))

    context = build_edit_user_page_context(user)
    return render_template("users/edit.html", **context)


```

FILE: .\app\bootstrap\__init__.py
```python
"""
app/bootstrap/__init__.py

Application bootstrap helpers for the Invoice / Procurement Management System.

PURPOSE
-------
This package contains the wiring logic that prepares a Flask application after
the Flask app object is created and configuration is loaded.

WHY THIS PACKAGE EXISTS
-----------------------
Previously, application bootstrap code lived directly in `app/__init__.py`.
That made the application factory responsible for too many unrelated concerns.

This package centralizes bootstrap orchestration so that:

- `app/__init__.py` stays small and focused
- app wiring is easy to locate
- navigation injection stays grouped with bootstrap concerns

PUBLIC API
----------
- init_extensions(app)
- configure_login(app)
- register_blueprints(app)
- register_request_hooks(app)
- register_context_processors(app)
- register_cli_commands(app)
- register_root_routes(app)
- configure_app(app)
"""

from __future__ import annotations

import click
from flask import Flask, redirect, url_for
from flask_login import current_user

from ..extensions import csrf, db, login_manager, migrate
from ..security import viewer_readonly_guard
from .navigation import build_visible_nav_sections


def init_extensions(app: Flask) -> None:
    """
    Initialize Flask extensions for the application.
    """
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)


def configure_login(app: Flask) -> None:
    """
    Configure Flask-Login and user loading.
    """
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id: str):
        from ..models import User

        try:
            return User.query.get(int(user_id))
        except Exception:
            return None


def register_blueprints(app: Flask) -> None:
    """
    Register all application blueprints.
    """
    from ..blueprints.admin.routes import admin_bp
    from ..blueprints.auth.routes import auth_bp
    from ..blueprints.procurements.routes import procurements_bp
    from ..blueprints.settings.routes import settings_bp
    from ..blueprints.users import users_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(procurements_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(admin_bp)


def register_cli_commands(app: Flask) -> None:
    """
    Register Flask CLI commands.
    """

    @app.cli.command("seed-options")
    def seed_options_command():
        from ..seed import seed_default_options

        seed_default_options()
        click.echo("Default dropdown options seeded.")


def register_request_hooks(app: Flask) -> None:
    """
    Register global request hooks.
    """

    @app.before_request
    def _viewer_guard_hook():
        result = viewer_readonly_guard()
        if result is not None:
            return result
        return None


def register_context_processors(app: Flask) -> None:
    """
    Register context processors for templates.
    """

    @app.context_processor
    def inject_globals():
        return {
            "config": app.config,
            "nav_sections": build_visible_nav_sections(),
        }


def register_root_routes(app: Flask) -> None:
    """
    Register application-level routes.
    """

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("procurements.inbox_procurements"))
        return redirect(url_for("auth.login"))


def configure_app(app: Flask) -> None:
    """
    Run the full application bootstrap sequence.
    """
    init_extensions(app)
    configure_login(app)
    register_request_hooks(app)
    register_blueprints(app)
    register_context_processors(app)
    register_cli_commands(app)
    register_root_routes(app)


__all__ = [
    "init_extensions",
    "configure_login",
    "register_blueprints",
    "register_request_hooks",
    "register_context_processors",
    "register_cli_commands",
    "register_root_routes",
    "configure_app",
]


```

FILE: .\app\bootstrap\bootstrap.py
```python
"""
app/bootstrap/bootstrap.py

Legacy bootstrap compatibility facade.

PURPOSE
-------
This file preserves the historical module path `app.bootstrap.bootstrap` while
making `app.bootstrap` the single canonical implementation surface.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add wiring logic here.
- Import from `app.bootstrap` in all new code.
"""

from __future__ import annotations

from . import *  # noqa: F401,F403

```

FILE: .\app\bootstrap\navigation.py
```python
"""
app/navigation.py

Sidebar navigation configuration and presentation-only visibility helpers.

PURPOSE
-------
This module centralizes application navigation metadata and the logic that
decides which navigation items are visible to the current user.

WHY THIS FILE EXISTS
--------------------
Previously, navigation metadata and filtering logic lived inside
`app/__init__.py`. That made the application factory file responsible for both:

- application bootstrapping
- UI navigation presentation rules

Those are different responsibilities.

This module keeps navigation concerns isolated so that:
- `app/__init__.py` stays focused on application creation
- sidebar structure becomes easier to maintain
- visibility logic can evolve independently from app bootstrapping

IMPORTANT SECURITY NOTE
-----------------------
Navigation filtering is PRESENTATION ONLY.

Showing or hiding a menu item does NOT grant or deny access by itself.
Real authorization must continue to be enforced in route handlers,
decorators, and security helpers.

CURRENT MODEL
-------------
The application groups sidebar items into sections. Each section may require
authentication, and each item may define extra visibility rules such as:

- admin_only
- endpoint-specific custom visibility rules

PUBLIC API
----------
This module exposes:

- NAV_SECTIONS
- is_nav_item_visible(item)
- build_visible_nav_sections()

The context processor in bootstrap code should call `build_visible_nav_sections()`
and inject its result into templates.
"""

from __future__ import annotations

from flask_login import current_user

# -------------------------------------------------------------------
# NAVIGATION STRUCTURE (presentation only; real auth is server-side)
# -------------------------------------------------------------------
NAV_SECTIONS = [
    {
        "key": "procurements",
        "label": "Προμήθειες",
        "auth_required": True,
        "items": [
            {
                "label": "Λίστα Προμηθειών (μη εγκεκριμένες)",
                "endpoint": "procurements.inbox_procurements",
                "admin_only": False,
            },
            {
                "label": "Εκκρεμείς Δαπάνες",
                "endpoint": "procurements.pending_expenses",
                "admin_only": False,
            },
            {
                "label": "Όλες οι Προμήθειες",
                "endpoint": "procurements.all_procurements",
                "admin_only": False,
            },
        ],
    },
    {
        "key": "settings",
        "label": "Ρυθμίσεις",
        "auth_required": True,
        "items": [
            # ---------------------------------------------------------
            # ΔΕΔΟΜΕΝΑ
            # ---------------------------------------------------------
            {"type": "header", "label": "Δεδομένα"},
            {
                "label": "Προμηθευτές",
                "endpoint": "settings.suppliers_list",
                "admin_only": True,
            },
            {
                "label": "Κατάσταση",
                "endpoint": "settings.options_status",
                "admin_only": True,
            },
            {
                "label": "Στάδιο",
                "endpoint": "settings.options_stage",
                "admin_only": True,
            },
            {
                "label": "Κατανομή",
                "endpoint": "settings.options_allocation",
                "admin_only": True,
            },
            {
                "label": "Τριμηνιαία",
                "endpoint": "settings.options_quarterly",
                "admin_only": True,
            },
            {
                "label": "ΦΠΑ",
                "endpoint": "settings.options_vat",
                "admin_only": True,
            },
            {
                "label": "Φόρος Εισοδήματος",
                "endpoint": "settings.income_tax_rules",
                "admin_only": True,
            },
            {
                "label": "Κρατήσεις",
                "endpoint": "settings.withholding_profiles",
                "admin_only": True,
            },
            {
                "label": "Επιτροπές Προμηθειών",
                "endpoint": "settings.committees",
                "admin_only": False,
            },
            {
                "label": "ΑΛΕ-ΚΑΕ",
                "endpoint": "settings.ale_kae",
                "admin_only": True,
            },
            {
                "label": "CPV",
                "endpoint": "settings.cpv",
                "admin_only": True,
            },

            # ---------------------------------------------------------
            # ΟΡΓΑΝΙΣΜΟΣ
            # ---------------------------------------------------------
            {"type": "header", "label": "Οργανισμός"},
            {
                "label": "Υπηρεσίες",
                "endpoint": "settings.service_units_list",
                "admin_only": True,
            },
            {
                "label": "Προσωπικό",
                "endpoint": "admin.personnel_list",
                "admin_only": False,
            },
            {
                "label": "Ορισμός Deputy/Manager",
                "endpoint": "settings.service_units_roles_list",
                "admin_only": True,
            },
            {
                "label": "Οργάνωση Υπηρεσίας",
                "endpoint": "admin.organization_setup",
                "admin_only": False,
            },
            {
                "label": "Χρήστες",
                "endpoint": "users.list_users",
                "admin_only": True,
            },

            # ---------------------------------------------------------
            # ΠΑΡΑΠΟΝΑ / ΠΡΟΤΑΣΕΙΣ
            # ---------------------------------------------------------
            {"type": "header", "label": "Παράπονα/Προτάσεις"},
            {
                "label": "Παράπονα/Προτάσεις",
                "endpoint": "settings.feedback",
                "admin_only": False,
            },
            {
                "label": "Διαχείριση Παραπόνων/Προτάσεων",
                "endpoint": "settings.feedback_admin",
                "admin_only": True,
            },

            # ---------------------------------------------------------
            # ΛΟΙΠΕΣ ΡΥΘΜΙΣΕΙΣ
            # ---------------------------------------------------------
            {"type": "header", "label": "Λοιπές Ρυθμίσεις"},
            {
                "label": "Θέμα Εμφάνισης",
                "endpoint": "settings.theme",
                "admin_only": False,
            },
        ],
    },
]


def is_nav_item_visible(item: dict) -> bool:
    """
    Determine whether a navigation item should be visible for the current user.

    IMPORTANT
    ---------
    This function controls only what is shown in the sidebar.
    It does NOT grant permission. Real security is still enforced in routes.

    VISIBILITY RULES
    ----------------
    - Section headers are always visible if their group survives filtering.
    - admin_only items are visible only to authenticated admins.
    - Certain endpoints have custom visibility rules.

    PARAMETERS
    ----------
    item:
        A navigation item dict from NAV_SECTIONS.

    RETURNS
    -------
    bool
        True if the item should be shown in the sidebar for the current user.
    """
    if item.get("type") == "header":
        return True

    if item.get("admin_only", False):
        if not (current_user.is_authenticated and current_user.is_admin):
            return False

    endpoint = item.get("endpoint")

    # Committees: visible to admin OR manager/deputy
    if endpoint == "settings.committees":
        return bool(
            current_user.is_authenticated
            and (current_user.is_admin or current_user.can_manage())
        )

    # Consolidated organization page:
    # visible to admin OR manager (not deputy)
    if endpoint == "admin.organization_setup":
        if not current_user.is_authenticated:
            return False
        if current_user.is_admin:
            return True
        is_mgr = getattr(current_user, "is_manager", None)
        return bool(callable(is_mgr) and is_mgr())

    # Personnel list:
    # visible to admin OR manager (not deputy)
    if endpoint == "admin.personnel_list":
        if not current_user.is_authenticated:
            return False
        if current_user.is_admin:
            return True
        is_mgr = getattr(current_user, "is_manager", None)
        return bool(callable(is_mgr) and is_mgr())

    return True


def build_visible_nav_sections() -> list[dict]:
    """
    Build the navigation tree filtered by the current user.

    UX RULE
    -------
    A header is rendered only if at least one visible child item exists under it.

    RETURNS
    -------
    list[dict]
        The final sidebar sections to inject into templates.
    """
    visible_sections: list[dict] = []

    for section in NAV_SECTIONS:
        if section.get("auth_required", False) and not current_user.is_authenticated:
            continue

        section_items = section.get("items", [])
        built_items: list[dict] = []

        current_header: dict | None = None
        current_group: list[dict] = []

        def _flush_group() -> None:
            """
            Flush the current header-group pair into built_items.

            Behavior:
            - If there is no header, append the group directly.
            - If there is a header, append the header only when there is at least
              one visible non-header child item in that group.
            """
            nonlocal current_header, current_group, built_items

            if current_header is None:
                built_items.extend(current_group)
            else:
                if any(i.get("type") != "header" for i in current_group):
                    built_items.append(current_header)
                    built_items.extend(current_group)

            current_header = None
            current_group = []

        for item in section_items:
            if item.get("type") == "header":
                _flush_group()
                current_header = item
                current_group = []
                continue

            if not is_nav_item_visible(item):
                continue

            current_group.append(item)

        _flush_group()

        if built_items:
            visible_sections.append(
                {
                    "key": section["key"],
                    "label": section["label"],
                    "items": built_items,
                }
            )

    return visible_sections


```

FILE: .\app\extensions\__init__.py
```python
"""
app/extensions/__init__.py

Central Flask extension registry for the Invoice / Procurement Management
System.

PURPOSE
-------
This package defines the extension singletons used across the application.

DESIGN RULE
-----------
This module must remain a pure registry.

It may:
- instantiate Flask extension objects
- expose them for import elsewhere

It must NOT:
- initialize extensions with an app
- contain configuration logic
- contain business logic
- contain route logic
"""

from __future__ import annotations

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

__all__ = [
    "db",
    "migrate",
    "login_manager",
    "csrf",
]


```

FILE: .\app\extensions\extensions.py
```python
"""
app/extensions/extensions.py

Legacy extensions compatibility facade.

PURPOSE
-------
This file preserves the historical module path `app.extensions.extensions`
while `app.extensions` remains the canonical public registry surface.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not instantiate new extension objects here.
- Import from `app.extensions` in all new code.
"""

from __future__ import annotations

from . import *  # noqa: F401,F403

```

FILE: .\app\models\__init__.py
```python
"""
app/models/__init__.py

Central public export surface for all SQLAlchemy models and selected shared
model helpers.
"""

from __future__ import annotations

from .helpers import (
    _display_percent,
    _money,
    _normalize_percent,
    _percent_to_fraction,
    _to_decimal,
)

from .organization import (
    Department,
    Directory,
    Personnel,
    PersonnelDepartmentAssignment,
    ServiceUnit,
)
from .user import User

from .master_data import (
    AleKae,
    Cpv,
    IncomeTaxRule,
    OptionCategory,
    OptionValue,
    WithholdingProfile,
)

from .supplier import Supplier
from .procurement import (
    MaterialLine,
    Procurement,
    ProcurementCommittee,
    ProcurementSupplier,
)

from .feedback import Feedback
from .audit import AuditLog

__all__ = [
    "_to_decimal",
    "_normalize_percent",
    "_percent_to_fraction",
    "_display_percent",
    "_money",
    "Personnel",
    "PersonnelDepartmentAssignment",
    "ServiceUnit",
    "Directory",
    "Department",
    "User",
    "OptionCategory",
    "OptionValue",
    "AleKae",
    "Cpv",
    "IncomeTaxRule",
    "WithholdingProfile",
    "Supplier",
    "Procurement",
    "ProcurementSupplier",
    "MaterialLine",
    "ProcurementCommittee",
    "Feedback",
    "AuditLog",
]

```

FILE: .\app\models\audit.py
```python
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


```

FILE: .\app\models\feedback.py
```python
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


```

FILE: .\app\models\helpers.py
```python
"""
app/models/helpers.py

Shared numeric and percentage helpers for model-adjacent financial logic.

PURPOSE
-------
This module contains small, reusable helpers that support model properties and
financial calculations closely related to the ORM layer.

WHY THIS FILE EXISTS
--------------------
The old monolithic `models.py` contained helper functions reused by multiple
entities and business calculations. Those helpers do not logically belong to
one specific SQLAlchemy model, so they live in this dedicated module.

This keeps model files focused on:
- schema definition
- relationships
- lightweight entity behavior

while shared numeric conversion / normalization / rounding logic lives here.

IMPORTANT DESIGN DECISION
-------------------------
These helpers are intentionally model-adjacent, not general-purpose utilities
for the whole application.

In other words:
- if a helper is specifically about procurement percentages, taxes, money, and
  SQLAlchemy numeric fields, it belongs here
- if later you need broader generic helpers (strings, dates, HTTP, etc.),
  those should live elsewhere

BOUNDARY
--------
This module may:
- convert values to Decimal
- normalize percent representations
- convert percent values to fractions
- prepare display percent values
- round monetary values deterministically

This module must NOT:
- query the database
- perform authorization
- depend on Flask request context
- contain route/service orchestration
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def _to_decimal(value: Any) -> Decimal:
    """
    Convert an arbitrary value to Decimal safely.

    PARAMETERS
    ----------
    value:
        Can be None, Decimal, int, float-like, or string-like.

    RETURNS
    -------
    Decimal
        - Decimal("0.00") when value is None
        - Decimal(str(value)) otherwise

    WHY THIS IMPLEMENTATION
    -----------------------
    Converting through `str(value)` avoids common binary float issues and works
    well with values coming from SQLAlchemy, forms, JSON, or mixed sources.

    EXAMPLES
    --------
    _to_decimal(None)      -> Decimal("0.00")
    _to_decimal("12.34")   -> Decimal("12.34")
    _to_decimal(5)         -> Decimal("5")
    """
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value))


def _normalize_percent(rate: Decimal | Any) -> Decimal:
    """
    Normalize a percentage-like input into fractional form.

    SUPPORTED INPUT STYLES
    ----------------------
    - 24    -> 0.24
    - 0.24  -> 0.24
    - 6     -> 0.06
    - 0.06  -> 0.06

    USE CASE
    --------
    This helper is intended for values where the UI or upstream input may send
    either:
    - a display percent (24)
    - or an already fractional value (0.24)

    IMPORTANT
    ---------
    Do NOT use this helper for master-data fields that are always stored as
    true percent values and may legitimately contain sub-1% rates such as
    0.10%.

    Those cases must use `_percent_to_fraction()`.

    PARAMETERS
    ----------
    rate:
        Decimal-like numeric value representing either percent or fraction.

    RETURNS
    -------
    Decimal
        Fractional representation quantized to 7 decimal places.
    """
    rate_dec = _to_decimal(rate)

    if rate_dec > Decimal("1"):
        return (rate_dec / Decimal("100")).quantize(Decimal("0.0000001"))

    return rate_dec.quantize(Decimal("0.0000001"))


def _percent_to_fraction(percent_value: Decimal | Any) -> Decimal:
    """
    Convert a true percentage value into fractional form.

    THIS DIFFERS FROM `_normalize_percent`
    --------------------------------------
    Here we assume the stored value is ALWAYS a percent.

    Examples
    --------
    - 0.10% -> 0.001
    - 6.00% -> 0.06

    PRIMARY USE
    -----------
    Master-data percentages such as withholding components where:
    - 0.10 means 0.10%
    - 6.00 means 6.00%

    PARAMETERS
    ----------
    percent_value:
        Decimal-like numeric value representing a true percent.

    RETURNS
    -------
    Decimal
        Fractional representation quantized to 7 decimal places.
    """
    percent_dec = _to_decimal(percent_value)
    return (percent_dec / Decimal("100")).quantize(Decimal("0.0000001"))


def _display_percent(rate: Decimal | Any) -> Decimal:
    """
    Convert an internally stored rate into display-percent form.

    SUPPORTED BEHAVIOR
    ------------------
    - stored as 24    -> display 24.00
    - stored as 0.24  -> display 24.00
    - stored as 0     -> display 0.00

    PARAMETERS
    ----------
    rate:
        Decimal-like numeric value stored internally either as:
        - percent (24)
        - fraction (0.24)
        - zero

    RETURNS
    -------
    Decimal
        Display percent rounded to 2 decimal places using ROUND_HALF_UP.
    """
    rate_dec = _to_decimal(rate)

    if rate_dec <= Decimal("1") and rate_dec != Decimal("0"):
        return (rate_dec * Decimal("100")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    return rate_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _money(value: Decimal | Any) -> Decimal:
    """
    Round a numeric value to standard money precision.

    WHY THIS HELPER EXISTS
    ----------------------
    Procurement calculations must produce deterministic monetary values for:
    - VAT
    - withholding amounts
    - income tax amounts
    - payable totals
    - report rendering

    PARAMETERS
    ----------
    value:
        Decimal-like numeric value.

    RETURNS
    -------
    Decimal
        Rounded to Decimal("0.01") using ROUND_HALF_UP.
    """
    return _to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


```

FILE: .\app\models\master_data.py
```python
"""
app/models/master_data.py

Reference / master-data models.

CONTAINS
--------
- OptionCategory
- OptionValue
- AleKae
- Cpv
- IncomeTaxRule
- WithholdingProfile

WHY THESE MODELS LIVE TOGETHER
------------------------------
These entities are configuration / lookup tables used by the procurement
workflow.

They are:
- not transactional workflow entities
- not organizational hierarchy entities
- not user/account entities

Grouping them together makes the architecture clearer:
these are reusable master-data records that support the rest of the system.

ARCHITECTURAL BOUNDARY
----------------------
This module defines:
- persistence schema
- relationships
- lightweight display helpers
- small computed properties tightly coupled to the entity itself

This module must NOT become the place for:
- dropdown query orchestration
- import/export logic
- Excel parsing
- route validation flow
- CRUD service orchestration

Those responsibilities belong in:
- app.services.master_data_service
- app.services.excel_imports
- route/service layers

IMPORTANT NUMERIC NOTE
----------------------
Some financial master-data fields are stored as PERCENT VALUES, not fractions.

Example:
- 6.00 means 6.00%
- 0.10 means 0.10%

So any business calculation must be explicit about whether it expects:
- display percent
- stored percent
- normalized fraction

The conversion helpers in `app.models.helpers` exist to make that distinction
safe and predictable.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ..extensions import db
from .helpers import _display_percent, _money, _percent_to_fraction, _to_decimal


class OptionCategory(db.Model):
    """
    Generic option category used to group dropdown values.

    EXAMPLES
    --------
    Typical categories may represent:
    - status
    - stage
    - allocation
    - quarterly
    - VAT

    DESIGN NOTE
    -----------
    This is intentionally generic master data rather than a separate table per
    simple dropdown.
    """

    __tablename__ = "option_categories"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    label = db.Column(db.String(120), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def display_name(self) -> str:
        """
        Preferred human-readable category label.
        """
        return (self.label or self.key or "").strip()

    def __repr__(self) -> str:
        return f"<OptionCategory {self.key}>"


class OptionValue(db.Model):
    """
    Generic option value under an OptionCategory.

    RULES
    -----
    - belongs to one category
    - value must be unique within that category
    - may be active/inactive
    - may have explicit sort order
    """

    __tablename__ = "option_values"

    id = db.Column(db.Integer, primary_key=True)

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("option_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    value = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    sort_order = db.Column(db.Integer, default=0, nullable=False)

    category = db.relationship(
        "OptionCategory",
        backref=db.backref("values", lazy=True, cascade="all, delete-orphan"),
    )

    __table_args__ = (
        db.UniqueConstraint("category_id", "value", name="uq_category_value"),
    )

    @property
    def display_name(self) -> str:
        """
        Preferred human-readable option label.
        """
        return (self.value or "").strip()

    def __repr__(self) -> str:
        return f"<OptionValue {self.category_id}:{self.value}>"


class AleKae(db.Model):
    """
    ALE–KAE master directory (admin-managed).

    COLUMNS
    -------
    - ale
    - old_kae
    - description
    - responsibility

    USE CASE
    --------
    Supports procurement classification and reporting metadata.
    """

    __tablename__ = "ale_kae"

    id = db.Column(db.Integer, primary_key=True)

    ale = db.Column(db.String(80), nullable=False, unique=True, index=True)
    old_kae = db.Column(db.String(80), nullable=True, index=True)
    description = db.Column(db.Text, nullable=True)
    responsibility = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def display_name(self) -> str:
        """
        Human-readable label for dropdowns / admin lists.
        """
        ale = (self.ale or "").strip()
        desc = (self.description or "").strip()
        return f"{ale} - {desc}" if desc else ale

    def __repr__(self) -> str:
        return f"<AleKae {self.ale}>"


class Cpv(db.Model):
    """
    CPV master directory (admin-managed).

    USE CASE
    --------
    Supports line-level procurement classification and validation.
    """

    __tablename__ = "cpv"

    id = db.Column(db.Integer, primary_key=True)

    cpv = db.Column(db.String(50), nullable=False, unique=True, index=True)
    description = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def display_name(self) -> str:
        """
        Human-readable CPV label.
        """
        cpv = (self.cpv or "").strip()
        desc = (self.description or "").strip()
        return f"{cpv} - {desc}" if desc else cpv

    def __repr__(self) -> str:
        return f"<Cpv {self.cpv}>"


class IncomeTaxRule(db.Model):
    """
    Income tax rule (Φόρος Εισοδήματος).

    PURPOSE
    -------
    Used as procurement master data to determine:
    - tax description
    - rate percent
    - threshold amount

    Example logic:
    - if base total <= threshold -> no income tax amount
    - otherwise calculate based on selected rule

    IMPORTANT
    ---------
    `rate_percent` is stored as a percent-style value.
    For example:
    - 4.00 means 4.00%
    - 8.00 means 8.00%
    """

    __tablename__ = "income_tax_rules"

    id = db.Column(db.Integer, primary_key=True)

    description = db.Column(db.String(255), nullable=False, unique=True, index=True)
    rate_percent = db.Column(db.Numeric(6, 2), nullable=False, default=Decimal("0.00"))
    threshold_amount = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def rate_percent_display(self) -> Decimal:
        """
        Display-ready percent for UI/report usage.

        RETURNS
        -------
        Decimal
            Example:
            - stored 4.00 -> 4.00
            - stored 0.04 -> 4.00
        """
        return _display_percent(_to_decimal(self.rate_percent))

    @property
    def rate_fraction(self) -> Decimal:
        """
        Fractional form of the stored percent.

        Example:
        - 4.00 -> 0.04
        - 8.00 -> 0.08

        USE CASE
        --------
        Safe to use in calculations that multiply by a base amount.
        """
        return _percent_to_fraction(_to_decimal(self.rate_percent))

    @property
    def threshold_amount_money(self) -> Decimal:
        """
        Threshold rounded to standard money precision.
        """
        return _money(_to_decimal(self.threshold_amount))

    @property
    def display_name(self) -> str:
        """
        Preferred human-readable label for lists/dropdowns.
        """
        return (self.description or "").strip()

    def __repr__(self) -> str:
        return f"<IncomeTaxRule {self.description}>"


class WithholdingProfile(db.Model):
    """
    Withholding profile / κρατήσεις.

    PURPOSE
    -------
    Groups withholding components used during procurement calculations.

    COMPONENTS
    ----------
    - mt_eloa_percent
    - eadhsy_percent
    - withholding1_percent
    - withholding2_percent

    IMPORTANT STORAGE RULE
    ----------------------
    These fields are stored as true percent values.

    Example:
    - 0.10 means 0.10%
    - 6.00 means 6.00%

    This is why calculations must not use mixed percent normalization logic
    blindly. Conversion to fraction must be explicit.
    """

    __tablename__ = "withholding_profiles"

    id = db.Column(db.Integer, primary_key=True)

    description = db.Column(db.String(255), nullable=False, unique=True, index=True)

    mt_eloa_percent = db.Column(db.Numeric(6, 2), nullable=False, default=Decimal("0.00"))
    eadhsy_percent = db.Column(db.Numeric(6, 2), nullable=False, default=Decimal("0.00"))
    withholding1_percent = db.Column(db.Numeric(6, 2), nullable=False, default=Decimal("0.00"))
    withholding2_percent = db.Column(db.Numeric(6, 2), nullable=False, default=Decimal("0.00"))

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def total_percent(self) -> Decimal:
        """
        Sum all withholding components as display percent.

        RETURNS
        -------
        Decimal
            Rounded total percentage.
        """
        total = (
            _to_decimal(self.mt_eloa_percent)
            + _to_decimal(self.eadhsy_percent)
            + _to_decimal(self.withholding1_percent)
            + _to_decimal(self.withholding2_percent)
        )
        return _money(total)

    @property
    def total_fraction(self) -> Decimal:
        """
        Sum all withholding components as a fractional rate.

        Example:
        - total_percent == 6.10
        - total_fraction == 0.061
        """
        return (
            _percent_to_fraction(_to_decimal(self.mt_eloa_percent))
            + _percent_to_fraction(_to_decimal(self.eadhsy_percent))
            + _percent_to_fraction(_to_decimal(self.withholding1_percent))
            + _percent_to_fraction(_to_decimal(self.withholding2_percent))
        ).quantize(Decimal("0.0000001"))

    @property
    def display_name(self) -> str:
        """
        Preferred human-readable profile label.
        """
        return (self.description or "").strip()

    def __repr__(self) -> str:
        return f"<WithholdingProfile {self.description}>"


```

FILE: .\app\models\organization.py
```python
"""
app/models/organization.py

Organizational structure models.
"""

from __future__ import annotations

from datetime import datetime

from ..extensions import db


class Personnel(db.Model):
    """
    Organizational directory person (admin-managed).
    """

    __tablename__ = "personnel"

    id = db.Column(db.Integer, primary_key=True)

    agm = db.Column(db.String(50), nullable=False, unique=True, index=True)
    aem = db.Column(db.String(50), nullable=True, index=True)

    rank = db.Column(db.String(100), nullable=True)
    specialty = db.Column(db.String(150), nullable=True)

    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

    service_unit_id = db.Column(
        db.Integer,
        db.ForeignKey("service_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship(
        "User",
        back_populates="personnel",
        uselist=False,
        cascade="all, delete",
    )

    service_unit = db.relationship(
        "ServiceUnit",
        foreign_keys=[service_unit_id],
        backref=db.backref("personnel_members", lazy=True),
    )

    def full_name(self) -> str:
        parts = []
        if self.rank:
            parts.append(str(self.rank).strip())
        if self.last_name:
            parts.append(str(self.last_name).strip())
        if self.first_name:
            parts.append(str(self.first_name).strip())
        return " ".join([p for p in parts if p]).strip()

    def _name_core(self) -> str:
        parts = []
        if self.rank:
            parts.append(str(self.rank).strip())
        if self.specialty:
            parts.append(str(self.specialty).strip())
        if self.first_name:
            parts.append(str(self.first_name).strip())
        if self.last_name:
            parts.append(str(self.last_name).strip())
        return " ".join([p for p in parts if p]).strip()

    @property
    def display_name(self) -> str:
        return self.display_selected_label()

    def display_selected_label(self) -> str:
        return self._name_core() or self.full_name()

    def display_option_label(self) -> str:
        base = self._name_core() or self.full_name()

        extra_parts = []
        if self.aem:
            extra_parts.append(f"ΑΕΜ {str(self.aem).strip()}")
        if self.agm:
            extra_parts.append(f"ΑΓΜ {str(self.agm).strip()}")

        extra = " ... ".join(extra_parts).strip()
        return f"{base} ({extra})" if extra else base

    def __repr__(self) -> str:
        return f"<Personnel {self.id}: {self.display_selected_label() or self.agm}>"


class ServiceUnit(db.Model):
    """
    Organizational service / unit.

    NOTES ABOUT THE NEW FIELDS
    --------------------------
    This model now stores additional service-unit metadata required by the
    Settings > Service Unit form and the Excel import flow.

    Added fields:
    - email:
      Contact email of the service unit.

    - region:
      Region / περιοχή of the service unit.

    - prefecture:
      Prefecture / νομός of the service unit.

    - commander_role_type:
      Stores whether the entered person/title is "Διοικητής" or "Κυβερνήτης".

    - application_admin_directory:
      Free-text field storing the ΔΙΕΥΘΥΝΣΗ to which the
      "Διαχειριστής Εφαρμογής" belongs.

    BACKWARD-COMPATIBLE STORAGE DECISION
    ------------------------------------
    The existing `curator` column is preserved and remains the persisted string
    field for the business label "Διαχειριστής Εφαρμογής".

    This is intentional to minimize breakage in existing code paths and database
    installations, while fully changing the UI/business meaning.
    """

    __tablename__ = "service_units"

    id = db.Column(db.Integer, primary_key=True)

    code = db.Column(db.String(50))
    description = db.Column(db.String(255), nullable=False)
    short_name = db.Column(db.String(100))

    aahit = db.Column(db.String(100))

    email = db.Column(db.String(255), nullable=True)

    commander = db.Column(db.String(255))
    commander_role_type = db.Column(db.String(50), nullable=True)

    curator = db.Column(db.String(255))
    application_admin_directory = db.Column(db.String(255), nullable=True)

    supply_officer = db.Column(db.String(255))

    address = db.Column(db.String(255), nullable=True)
    region = db.Column(db.String(255), nullable=True)
    prefecture = db.Column(db.String(255), nullable=True)

    phone = db.Column(db.String(50), nullable=True)

    manager_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    deputy_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    manager = db.relationship(
        "Personnel",
        foreign_keys=[manager_personnel_id],
        backref="managed_units",
    )
    deputy = db.relationship(
        "Personnel",
        foreign_keys=[deputy_personnel_id],
        backref="deputy_units",
    )

    users = db.relationship("User", back_populates="service_unit", lazy=True)

    procurements = db.relationship(
        "Procurement",
        back_populates="service_unit",
        cascade="all, delete-orphan",
    )

    directories = db.relationship(
        "Directory",
        back_populates="service_unit",
        cascade="all, delete-orphan",
        lazy=True,
    )

    departments = db.relationship(
        "Department",
        back_populates="service_unit",
        cascade="all, delete-orphan",
        lazy=True,
    )

    @property
    def display_name(self) -> str:
        return (self.short_name or self.description or "").strip()

    def __repr__(self) -> str:
        return f"<ServiceUnit {self.id}: {self.display_name}>"


class Directory(db.Model):
    """
    Directory / Διεύθυνση under a ServiceUnit.
    """

    __tablename__ = "directories"

    id = db.Column(db.Integer, primary_key=True)

    service_unit_id = db.Column(
        db.Integer,
        db.ForeignKey("service_units.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = db.Column(db.String(255), nullable=False, index=True)

    director_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    service_unit = db.relationship("ServiceUnit", back_populates="directories")
    director = db.relationship("Personnel", foreign_keys=[director_personnel_id])

    departments = db.relationship(
        "Department",
        back_populates="directory",
        cascade="all, delete-orphan",
        lazy=True,
    )

    __table_args__ = (
        db.UniqueConstraint("service_unit_id", "name", name="uq_directory_serviceunit_name"),
    )

    @property
    def display_name(self) -> str:
        return (self.name or "").strip()

    def __repr__(self) -> str:
        return f"<Directory {self.id}: {self.display_name}>"


class Department(db.Model):
    """
    Department / Τμήμα under a Directory.
    """

    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)

    service_unit_id = db.Column(
        db.Integer,
        db.ForeignKey("service_units.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    directory_id = db.Column(
        db.Integer,
        db.ForeignKey("directories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = db.Column(db.String(255), nullable=False, index=True)

    head_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    assistant_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    directory = db.relationship("Directory", back_populates="departments")
    service_unit = db.relationship("ServiceUnit", back_populates="departments")

    head = db.relationship("Personnel", foreign_keys=[head_personnel_id])
    assistant = db.relationship("Personnel", foreign_keys=[assistant_personnel_id])

    assignments = db.relationship(
        "PersonnelDepartmentAssignment",
        back_populates="department",
        cascade="all, delete-orphan",
        lazy=True,
    )

    __table_args__ = (
        db.UniqueConstraint("directory_id", "name", name="uq_department_directory_name"),
    )

    @property
    def display_name(self) -> str:
        return (self.name or "").strip()

    def __repr__(self) -> str:
        return f"<Department {self.id}: {self.display_name}>"


class PersonnelDepartmentAssignment(db.Model):
    """
    Membership/assignment of a person to a department.

    PURPOSE
    -------
    A person may belong to multiple departments and, by extension,
    multiple directories within the same service unit.

    UI / REPORTING ROLE
    -------------------
    This model is also the canonical procurement-handler selection unit.

    That means one assignment row represents:
    - one specific person
    - one specific department
    - one specific directory

    The procurement UI stores the selected assignment id so downstream reports
    can render the exact organizational context used for that procurement.
    """

    __tablename__ = "personnel_department_assignments"

    id = db.Column(db.Integer, primary_key=True)

    personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    service_unit_id = db.Column(
        db.Integer,
        db.ForeignKey("service_units.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    directory_id = db.Column(
        db.Integer,
        db.ForeignKey("directories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    is_primary = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    personnel = db.relationship(
        "Personnel",
        backref=db.backref(
            "department_assignments",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    service_unit = db.relationship("ServiceUnit")
    directory = db.relationship("Directory")
    department = db.relationship("Department", back_populates="assignments")

    __table_args__ = (
        db.UniqueConstraint(
            "personnel_id",
            "department_id",
            name="uq_personnel_department_assignment",
        ),
    )

    def _person_label(self) -> str:
        """
        Return the most useful person-centric label available.

        Falls back safely if the linked Personnel row is missing.
        """
        if not self.personnel:
            return "—"

        display_selected = getattr(self.personnel, "display_selected_label", None)
        if callable(display_selected):
            value = display_selected()
            if value:
                return value

        display_name = getattr(self.personnel, "display_name", None)
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()

        full_name = getattr(self.personnel, "full_name", None)
        if callable(full_name):
            value = full_name()
            if value:
                return value

        return "—"

    def display_selected_label(self) -> str:
        """
        Label used after selection in procurement handler dropdowns.

        FORMAT
        ------
        PERSON / ΤΜΗΜΑ
        """
        person_label = self._person_label()
        department_name = (self.department.name or "").strip() if self.department else ""
        if department_name:
            return f"{person_label} / {department_name}"
        return person_label

    def display_option_label(self) -> str:
        """
        Full searchable label used inside procurement handler dropdown options.

        FORMAT
        ------
        PERSON / ΤΜΗΜΑ / ΔΙΕΥΘΥΝΣΗ
        """
        person_label = self._person_label()
        department_name = (self.department.name or "").strip() if self.department else ""
        directory_name = (self.directory.name or "").strip() if self.directory else ""

        parts = [person_label]
        if department_name:
            parts.append(department_name)
        if directory_name:
            parts.append(directory_name)

        return " / ".join([p for p in parts if p]).strip()

    @property
    def display_name(self) -> str:
        return self.display_option_label()

    def __repr__(self) -> str:
        return f"<PersonnelDepartmentAssignment {self.id}: personnel={self.personnel_id} dept={self.department_id}>"

```

FILE: .\app\models\procurement.py
```python
"""
app/models/procurement.py

Procurement workflow models.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from ..extensions import db
from .helpers import _money, _to_decimal

if TYPE_CHECKING:
    from .supplier import Supplier


class ProcurementCommittee(db.Model):
    __tablename__ = "procurement_committees"

    id = db.Column(db.Integer, primary_key=True)

    service_unit_id = db.Column(
        db.Integer,
        db.ForeignKey("service_units.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    description = db.Column(db.String(255), nullable=False, index=True)
    identity_text = db.Column(db.String(255), nullable=True)

    president_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    member1_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    member2_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    service_unit = db.relationship(
        "ServiceUnit",
        backref=db.backref("committees", lazy=True),
    )

    president = db.relationship("Personnel", foreign_keys=[president_personnel_id])
    member1 = db.relationship("Personnel", foreign_keys=[member1_personnel_id])
    member2 = db.relationship("Personnel", foreign_keys=[member2_personnel_id])

    __table_args__ = (
        db.UniqueConstraint(
            "service_unit_id",
            "description",
            name="uq_committee_serviceunit_desc",
        ),
    )

    @property
    def display_name(self) -> str:
        return (self.description or "").strip()

    def members_display(self) -> str:
        parts = []

        if self.president:
            parts.append(f"Πρόεδρος: {self.president.full_name()}")

        if self.member1:
            parts.append(f"Α' Μέλος: {self.member1.full_name()}")

        if self.member2:
            parts.append(f"Β' Μέλος: {self.member2.full_name()}")

        return " | ".join(parts) if parts else "—"

    def __repr__(self) -> str:
        return f"<ProcurementCommittee {self.id}: {self.display_name}>"


class Procurement(db.Model):
    __tablename__ = "procurements"

    id = db.Column(db.Integer, primary_key=True)

    fiscal_year = db.Column(db.Integer, index=True)

    service_unit_id = db.Column(
        db.Integer,
        db.ForeignKey("service_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    service = db.Column(db.String(255))
    serial_no = db.Column(db.String(50))
    description = db.Column(db.Text)
    ale = db.Column(db.String(50), index=True)

    allocation = db.Column(db.String(80), index=True)
    quarterly = db.Column(db.String(80), index=True)
    status = db.Column(db.String(80), index=True)
    stage = db.Column(db.String(80), index=True)

    handler = db.Column(db.String(255), index=True)

    handler_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    handler_personnel = db.relationship("Personnel", foreign_keys=[handler_personnel_id])

    handler_assignment_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel_department_assignments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    handler_assignment = db.relationship(
        "PersonnelDepartmentAssignment",
        foreign_keys=[handler_assignment_id],
    )

    income_tax_rule_id = db.Column(
        db.Integer,
        db.ForeignKey("income_tax_rules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    income_tax_rule = db.relationship("IncomeTaxRule", foreign_keys=[income_tax_rule_id])

    withholding_profile_id = db.Column(
        db.Integer,
        db.ForeignKey("withholding_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    withholding_profile = db.relationship(
        "WithholdingProfile",
        foreign_keys=[withholding_profile_id],
    )

    committee_id = db.Column(
        db.Integer,
        db.ForeignKey("procurement_committees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    committee = db.relationship("ProcurementCommittee", foreign_keys=[committee_id])

    requested_amount = db.Column(db.Numeric(12, 2))
    approved_amount = db.Column(db.Numeric(12, 2))

    vat_rate = db.Column(db.Numeric(5, 4))
    sum_total = db.Column(db.Numeric(12, 2))
    vat_amount = db.Column(db.Numeric(12, 2))
    grand_total = db.Column(db.Numeric(12, 2))

    hop_commitment = db.Column(db.String(50), nullable=True, index=True)
    hop_forward1_commitment = db.Column(db.String(50), nullable=True, index=True)
    hop_forward2_commitment = db.Column(db.String(50), nullable=True, index=True)
    hop_approval_commitment = db.Column(db.String(50), nullable=True, index=True)
    hop_preapproval = db.Column(db.String(50), nullable=True, index=True)
    hop_forward1_preapproval = db.Column(db.String(50), nullable=True, index=True)
    hop_forward2_preapproval = db.Column(db.String(50), nullable=True, index=True)
    hop_approval = db.Column(db.String(50), nullable=True, index=True)

    aay = db.Column(db.String(50), nullable=True, index=True)

    adam_aay = db.Column(db.String(100), nullable=True, index=True)
    ada_aay = db.Column(db.String(100), nullable=True, index=True)

    identity_prosklisis = db.Column(db.String(255), nullable=True)
    adam_prosklisis = db.Column(db.String(100), nullable=True, index=True)

    identity_apofasis_anathesis = db.Column(db.String(255), nullable=True)
    adam_apofasis_anathesis = db.Column(db.String(100), nullable=True, index=True)

    contract_number = db.Column(db.String(100), nullable=True, index=True)
    adam_contract = db.Column(db.String(100), nullable=True, index=True)

    invoice_number = db.Column(db.String(100), nullable=True, index=True)
    invoice_date = db.Column(db.Date, nullable=True, index=True)
    materials_receipt_date = db.Column(db.Date, nullable=True, index=True)
    invoice_receipt_date = db.Column(db.Date, nullable=True, index=True)

    protocol_number = db.Column(db.String(100), nullable=True, index=True)

    procurement_notes = db.Column(db.Text, nullable=True)

    send_to_expenses = db.Column(db.Boolean, default=False, nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    service_unit = db.relationship("ServiceUnit", back_populates="procurements")

    supplies_links = db.relationship(
        "ProcurementSupplier",
        backref="procurement",
        lazy=True,
        cascade="all, delete-orphan",
    )

    materials = db.relationship(
        "MaterialLine",
        back_populates="procurement",
        cascade="all, delete-orphan",
    )

    @property
    def display_name(self) -> str:
        serial_no = (self.serial_no or "").strip()
        description = (self.description or "").strip()

        if serial_no and description:
            return f"{serial_no} - {description}"
        return serial_no or description or f"Procurement #{self.id}"

    @property
    def winner_link(self) -> ProcurementSupplier | None:
        for link in self.supplies_links or []:
            if link.is_winner:
                return link
        return None

    @property
    def winner_supplier_display(self) -> str | None:
        winner_link = self.winner_link
        if not winner_link or not winner_link.supplier:
            return None

        supplier = winner_link.supplier
        return f"{supplier.afm} - {supplier.name}"

    @property
    def winner_supplier_afm(self) -> str | None:
        winner_link = self.winner_link
        if winner_link and winner_link.supplier:
            return winner_link.supplier.afm
        return None

    @property
    def winner_supplier_name(self) -> str | None:
        winner_link = self.winner_link
        if winner_link and winner_link.supplier:
            return winner_link.supplier.name
        return None

    def winner_supplier_obj(self) -> Supplier | None:
        winner_link = self.winner_link
        if winner_link and winner_link.supplier:
            return winner_link.supplier
        return None

    @property
    def handler_display(self) -> str | None:
        if self.handler_personnel:
            return self.handler_personnel.full_name()
        return self.handler or None

    @property
    def handler_directory_name(self) -> str | None:
        if self.handler_assignment and self.handler_assignment.directory:
            return self.handler_assignment.directory.name
        return None

    @property
    def handler_department_name(self) -> str | None:
        if self.handler_assignment and self.handler_assignment.department:
            return self.handler_assignment.department.name
        return None

    @property
    def aa2_description(self) -> str | None:
        if self.income_tax_rule and self.income_tax_rule.description:
            return self.income_tax_rule.description
        return None

    @property
    def requested_amount_money(self) -> Decimal:
        return _money(_to_decimal(self.requested_amount))

    @property
    def approved_amount_money(self) -> Decimal:
        return _money(_to_decimal(self.approved_amount))

    @property
    def sum_total_money(self) -> Decimal:
        return _money(_to_decimal(self.sum_total))

    @property
    def vat_amount_money(self) -> Decimal:
        return _money(_to_decimal(self.vat_amount))

    @property
    def grand_total_money(self) -> Decimal:
        return _money(_to_decimal(self.grand_total))

    @property
    def materials_total_pre_vat(self) -> Decimal:
        total = Decimal("0.00")
        for line in self.materials or []:
            total += _to_decimal(line.total_pre_vat)
        return _money(total)

    def recalc_totals(self) -> None:
        from ..services.procurement_calculations import ProcurementCalculationService
        ProcurementCalculationService.recalc_totals(self)

    def compute_public_withholdings(self) -> dict:
        from ..services.procurement_calculations import ProcurementCalculationService
        return ProcurementCalculationService.compute_public_withholdings(self)

    def compute_income_tax(self) -> dict:
        from ..services.procurement_calculations import ProcurementCalculationService
        return ProcurementCalculationService.compute_income_tax(self)

    def compute_payment_analysis(self) -> dict:
        from ..services.procurement_calculations import ProcurementCalculationService
        return ProcurementCalculationService.compute_payment_analysis(self)

    def __repr__(self) -> str:
        return f"<Procurement {self.id}: {self.display_name}>"


class ProcurementSupplier(db.Model):
    __tablename__ = "procurement_suppliers"

    id = db.Column(db.Integer, primary_key=True)

    procurement_id = db.Column(
        db.Integer,
        db.ForeignKey("procurements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    result = db.Column(db.String(80))
    is_winner = db.Column(db.Boolean, default=False)
    offered_amount = db.Column(db.Numeric(12, 2))

    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    supplier = db.relationship(
        "Supplier",
        backref=db.backref("procurement_links", lazy=True),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "procurement_id",
            "supplier_id",
            name="uq_procurement_supplier",
        ),
    )

    @property
    def offered_amount_money(self) -> Decimal:
        return _money(_to_decimal(self.offered_amount))

    @property
    def display_name(self) -> str:
        if self.supplier:
            return getattr(self.supplier, "display_label", None) or self.supplier.name
        return f"SupplierLink #{self.id}"

    def __repr__(self) -> str:
        supplier_part = self.supplier.afm if self.supplier else self.supplier_id
        return f"<ProcurementSupplier procurement={self.procurement_id} supplier={supplier_part}>"


class MaterialLine(db.Model):
    __tablename__ = "material_lines"

    id = db.Column(db.Integer, primary_key=True)

    procurement_id = db.Column(
        db.Integer,
        db.ForeignKey("procurements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    line_no = db.Column(db.Integer)
    is_service = db.Column(db.Boolean, default=False)
    description = db.Column(db.Text, nullable=False)
    cpv = db.Column(db.String(50))
    nsn = db.Column(db.String(50))
    unit = db.Column(db.String(50))

    quantity = db.Column(db.Numeric(12, 2), nullable=False, default=1)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    procurement = db.relationship("Procurement", back_populates="materials")

    @property
    def total_pre_vat(self) -> Decimal:
        quantity = _to_decimal(self.quantity)
        unit_price = _to_decimal(self.unit_price)

        if quantity == Decimal("0.00") or unit_price == Decimal("0.00"):
            return Decimal("0.00")

        return (quantity * unit_price).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    @property
    def display_name(self) -> str:
        return (self.description or "").strip()

    def __repr__(self) -> str:
        return f"<MaterialLine {self.id}: line_no={self.line_no}>"

```

FILE: .\app\models\supplier.py
```python
"""
app/models/supplier.py

Supplier master-data model.

PURPOSE
-------
This module defines the Supplier master-data entity used throughout the
procurement workflow.

WHY THIS FILE EXISTS
--------------------
Suppliers are reference/master records used by procurements, but they deserve
their own dedicated module because:

- they are a distinct business entity
- they typically have their own admin CRUD screens
- they are reused across many procurement records
- they contain business-facing contact and payment metadata

ARCHITECTURAL BOUNDARY
----------------------
This module defines:
- persistence schema
- lightweight display helpers
- supplier identity / contact / payment fields

This module must NOT become the place for:
- AFM validation workflows
- duplicate-detection orchestration
- procurement participation logic
- supplier import/export orchestration
- route-level form handling

Those responsibilities belong in:
- app.services.*
- app.routes / blueprints
- import services

IMPORTANT
---------
This is generally admin-managed master data. Server-side validation must still
be enforced by the calling service/route layer, especially for:
- AFM uniqueness
- IBAN normalization/validation
- email normalization
- required-field policies
"""

from __future__ import annotations

from datetime import datetime

from ..extensions import db


class Supplier(db.Model):
    """
    Supplier master data.

    KEY FIELDS
    ----------
    - afm:
        Tax identifier / ΑΦΜ. Intended to be unique per supplier.

    - name:
        Supplier legal or display name.

    - doy:
        Tax office / Δ.Ο.Υ.

    - phone, email:
        Contact details.

    - address, city, postal_code, country:
        Address metadata.

    - bank_name, iban:
        Payment / banking details.

    - emba:
        Reporting or compliance metadata field retained from the existing app.

    DESIGN NOTE
    -----------
    This model intentionally stays simple and schema-focused. It is a reusable
    supplier directory record, not a transactional procurement object.
    """

    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)

    afm = db.Column(db.String(9), nullable=False, unique=True, index=True)
    name = db.Column(db.String(255), nullable=False, index=True)

    # Supplier tax office (Δ.Ο.Υ.)
    doy = db.Column(db.String(255), nullable=True)

    # Contact information
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(255), nullable=True)

    # Reporting / compliance field
    emba = db.Column(db.String(255), nullable=True)

    # Address / location
    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(100), nullable=True)

    # Payment details
    bank_name = db.Column(db.String(120), nullable=True)
    iban = db.Column(db.String(34), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def display_name(self) -> str:
        """
        Preferred human-readable supplier label.
        """
        return (self.name or "").strip()

    @property
    def display_label(self) -> str:
        """
        Useful compact label for dropdowns or summary views.

        FORMAT
        ------
        "Επωνυμία (ΑΦΜ)"
        """
        name = (self.name or "").strip()
        afm = (self.afm or "").strip()

        if name and afm:
            return f"{name} ({afm})"
        return name or afm

    @property
    def location_label(self) -> str:
        """
        Compact city/country display label for UI/report usage.
        """
        city = (self.city or "").strip()
        country = (self.country or "").strip()

        if city and country:
            return f"{city}, {country}"
        return city or country

    @property
    def has_payment_details(self) -> bool:
        """
        Return True when at least one payment-related field is present.
        """
        return bool(
            (self.bank_name and str(self.bank_name).strip())
            or (self.iban and str(self.iban).strip())
        )

    @property
    def has_contact_details(self) -> bool:
        """
        Return True when at least one contact-related field is present.
        """
        return bool(
            (self.phone and str(self.phone).strip())
            or (self.email and str(self.email).strip())
            or (self.address and str(self.address).strip())
        )

    def __repr__(self) -> str:
        return f"<Supplier {self.afm} - {self.name}>"


```

FILE: .\app\models\user.py
```python
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
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
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


```

FILE: .\app\presentation\__init__.py
```python
"""
app/presentation/__init__.py

Presentation-only helpers for the Invoice / Procurement Management System.

PURPOSE
-------
This package contains helpers used purely for UI rendering and visual
presentation decisions.

IMPORTANT BOUNDARY
------------------
Helpers in this package may:
- inspect values already loaded into memory
- compute labels / CSS classes / display decisions

Helpers in this package must NOT:
- query the database
- perform authorization
- mutate application state
- enforce business rules
"""

from __future__ import annotations


def _as_clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def procurement_row_class(proc):
    status = _as_clean_text(getattr(proc, "status", None))
    stage = _as_clean_text(getattr(proc, "stage", None))

    if status == "ΑΚΥΡΩΘΗΚΕ":
        return "row-cancelled"

    if status == "ΟΛΟΚΛΗΡΩΘΗΚΕ":
        return "row-complete"

    if status == "ΣΕ ΕΞΕΛΙΞΗ" and stage == "Αποστολή Δαπάνης":
        return "row-expense-purple"

    if status == "ΣΕ ΕΞΕΛΙΞΗ" and stage == "Τιμολόγιο":
        return "row-invoice"

    if status == "ΣΕ ΕΞΕΛΙΞΗ" and stage == "Έγκριση":
        return "row-approval"

    return ""


def init_presentation(app):
    app.jinja_env.globals["procurement_row_class"] = procurement_row_class

    @app.context_processor
    def inject_template_helpers():
        return {
            "procurement_row_class": procurement_row_class,
        }


__all__ = ["init_presentation", "procurement_row_class"]

```

FILE: .\app\presentation\presentation.py
```python
"""
app/presentation/presentation.py

Legacy presentation compatibility facade.

PURPOSE
-------
This file preserves the historical module path `app.presentation.presentation`
while `app.presentation` remains the canonical public surface.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add presentation rules here.
- Import from `app.presentation` in all new code.
"""

from __future__ import annotations

from . import *  # noqa: F401,F403

```

FILE: .\app\presentation\procurement_ui.py
```python
"""
app/presentation/procurement_ui.py

Procurement UI / presentation helpers.

PURPOSE
-------
This module contains procurement-specific helpers that are presentation-facing
rather than domain/query-facing.

It is responsible for:
- UI-only next-url interpretation helpers
- Windows-safe filename sanitization for downloadable procurement outputs
- money formatting intended specifically for filenames

WHY THIS FILE EXISTS
--------------------
These helpers existed previously inside the procurement service module, but they
do not represent procurement query logic or procurement workflow rules.

Moving them here gives cleaner boundaries:
- services keep domain/query/workflow logic
- presentation keeps UI-only and downloadable-output naming helpers

IMPORTANT BOUNDARY
------------------
These helpers must NEVER:
- influence authorization
- replace route-level validation
- perform DB queries
- mutate application state

They are intentionally side-effect-free.
"""

from __future__ import annotations

import re
from decimal import Decimal

# Characters that are illegal or problematic in Windows filenames.
_ILLEGAL_WIN_FILENAME = r'<>:"/\\|?*\n\r\t'


def opened_from_all_list(next_url: str) -> bool:
    """
    Detect whether a page was opened from '/procurements/all'.

    PARAMETERS
    ----------
    next_url:
        Safe local next URL already validated upstream.

    RETURNS
    -------
    bool
        True if next_url appears to point to the all-procurements list.

    IMPORTANT
    ---------
    This helper is presentation-only.
    It must NEVER influence authorization or domain-state decisions.
    """
    return bool(next_url and next_url.startswith("/procurements/all"))


def sanitize_filename_component(value: str) -> str:
    """
    Make a Windows-safe filename component.

    PARAMETERS
    ----------
    value:
        Raw text intended to become part of a downloadable filename.

    RETURNS
    -------
    str
        Sanitized filename fragment.

    SANITIZATION RULES
    ------------------
    - remove illegal filename characters
    - collapse repeated whitespace
    - strip trailing spaces and dots
    - fallback to '—' when empty after cleanup

    WHY THIS HELPER EXISTS
    ----------------------
    Download filenames may include:
    - supplier names
    - report labels
    - amounts
    - procurement descriptions

    These values must be cleaned to avoid invalid filenames on Windows systems.
    """
    value = (value or "").strip()
    if not value:
        return "—"

    value = re.sub(f"[{re.escape(_ILLEGAL_WIN_FILENAME)}]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = value.strip(" .")
    return value or "—"


def money_filename(value: object) -> str:
    """
    Format a numeric value for safe filename usage.

    PARAMETERS
    ----------
    value:
        Numeric-like value, usually Decimal/str/int/float-compatible.

    RETURNS
    -------
    str
        String formatted with:
        - 2 decimal places
        - comma decimal separator
        - no currency symbol

    EXAMPLES
    --------
    Decimal("1700")   -> "1700,00"
    Decimal("1700.5") -> "1700,50"

    WHY THIS HELPER EXISTS
    ----------------------
    Report filenames often include monetary amounts and should remain readable
    for Greek business users.
    """
    try:
        amount = Decimal(str(value or "0"))
    except Exception:
        amount = Decimal("0")

    amount = amount.quantize(Decimal("0.01"))
    return f"{amount:.2f}".replace(".", ",")


__all__ = [
    "opened_from_all_list",
    "sanitize_filename_component",
    "money_filename",
]


```

FILE: .\app\reports\__init__.py
```python


```

FILE: .\app\reports\award_decision_docx.py
```python
"""
app/reports/award_decision_docx.py

Generate "ΑΠΟΦΑΣΗ ΑΝΑΘΕΣΗΣ" as DOCX bytes using a Word template
and placeholder replacement.

IMPORTANT DOMAIN CHANGE
-----------------------
Handler organizational data must now come from the selected procurement
handler assignment, not by assuming one fixed department/directory on Personnel.

Placeholders supported for the selected handler assignment:
  {{HANDLER_DIRECTORY}}
  {{HANDLER_DEPARTMENT}}

IMPORTANT MASTER-DATA RULE
--------------------------
The placeholder `{{armodiothtas}}` must be resolved from the ALE–KAE master
directory using the Procurement.ale code.

The Procurement entity stores only:
- procurement.ale

It does not store:
- procurement.armodiothtas
- procurement.ale_kae relationship

Therefore this report must look up the ALE master row explicitly through the
shared master-data service.

TEMPLATE ALIGNMENT
------------------
This implementation is aligned to the current final award decision DOCX template.

Confirmed placeholders present in the template include:
- {{SHORT_DATE}}
- {{SERVICE_UNIT_NAME}}
- {{SERVICE_UNIT_PHONE}}
- {{SERVICE_UNIT_REGION}}
- {{COMMANDER_ROLE_TYPE}}
- {{service.commander}}
- {{WINNER_SUPPLIER_LINE}}
- {{HANDLER_DIRECTORY}}
- {{HANDLER_DEPARTMENT}}
- {{ML_TOTAL_WORDS}}
- cost-analysis placeholders
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Optional

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from ..services.master_data_service import get_ale_row_by_code


def _safe(v: Any, default: str = "—") -> str:
    s = ("" if v is None else str(v)).strip()
    return s if s else default


def _to_decimal(v: Any) -> Decimal:
    try:
        return Decimal(str(v or "0"))
    except Exception:
        return Decimal("0.00")


def _money_plain(v: Any) -> str:
    d = _to_decimal(v).quantize(Decimal("0.01"))
    s = f"{d:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def _money(v: Any) -> str:
    return f"{_money_plain(v)} €"


def _percent(v: Any) -> str:
    d = _to_decimal(v).quantize(Decimal("0.01"))
    s = f"{d:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def _upper_no_accents(value: Any, default: str = "—") -> str:
    """
    Return uppercase Greek/Latin text without accents/diacritics.

    Example:
    Υπηρεσία Ναυτικών Τεχνικών Εγκαταστάσεων Λέρου
    -> ΥΠΗΡΕΣΙΑ ΝΑΥΤΙΚΩΝ ΤΕΧΝΙΚΩΝ ΕΓΚΑΤΑΣΤΑΣΕΩΝ ΛΕΡΟΥ
    """
    text = _safe(value, default=default)

    normalized = unicodedata.normalize("NFD", text)
    no_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", no_marks).upper()


def _upper_service_name(name: str) -> str:
    """
    Return service-unit display name in uppercase without accents.

    This intentionally matches the report requirement for all-caps Greek text
    without tonos/diacritics.
    """
    return _upper_no_accents(name)


def _short_date_el(value: Any | None = None) -> str:
    """
    Return date in Greek short format: DD Mon YY.

    Examples:
    - 07 Μαρ 26
    - 22 Μαρ 26

    Accepted inputs:
    - datetime
    - date-like object with day/month/year attrs
    - None -> datetime.now()
    """
    months = {
        1: "Ιαν",
        2: "Φεβ",
        3: "Μαρ",
        4: "Απρ",
        5: "Μαϊ",
        6: "Ιουν",
        7: "Ιουλ",
        8: "Αυγ",
        9: "Σεπ",
        10: "Οκτ",
        11: "Νοε",
        12: "Δεκ",
    }

    dt = value or datetime.now()

    try:
        day = int(dt.day)
        month = int(dt.month)
        year_2d = int(dt.year) % 100
    except Exception:
        dt = datetime.now()
        day = dt.day
        month = dt.month
        year_2d = dt.year % 100

    month_label = months.get(month, "")
    return f"{day:02d} {month_label} {year_2d:02d}".strip()


def _int_to_greek_words_genitive(n: int) -> str:
    """
    Convert a non-negative integer to Greek words in genitive case,
    suitable for phrases like:

    - συνολικής αξίας ...
    - ποσού ...

    Examples:
    1755 -> χιλίων επτακοσίων πενήντα πέντε
    20   -> είκοσι
    200  -> διακοσίων

    Supported range:
    0 <= n <= 999_999_999
    """
    if n < 0:
        raise ValueError("Negative values are not supported.")
    if n == 0:
        return "μηδενός"

    units = {
        0: "",
        1: "ενός",
        2: "δύο",
        3: "τριών",
        4: "τεσσάρων",
        5: "πέντε",
        6: "έξι",
        7: "επτά",
        8: "οκτώ",
        9: "εννέα",
    }

    teens = {
        10: "δέκα",
        11: "έντεκα",
        12: "δώδεκα",
        13: "δεκατριών",
        14: "δεκατεσσάρων",
        15: "δεκαπέντε",
        16: "δεκαέξι",
        17: "δεκαεπτά",
        18: "δεκαοκτώ",
        19: "δεκαεννέα",
    }

    tens = {
        2: "είκοσι",
        3: "τριάντα",
        4: "σαράντα",
        5: "πενήντα",
        6: "εξήντα",
        7: "εβδομήντα",
        8: "ογδόντα",
        9: "ενενήντα",
    }

    hundreds = {
        1: "εκατόν",
        2: "διακοσίων",
        3: "τριακοσίων",
        4: "τετρακοσίων",
        5: "πεντακοσίων",
        6: "εξακοσίων",
        7: "επτακοσίων",
        8: "οκτακοσίων",
        9: "εννιακοσίων",
    }

    def two_digits(num: int) -> str:
        if num < 10:
            return units[num]
        if 10 <= num <= 19:
            return teens[num]

        t = num // 10
        u = num % 10
        if u == 0:
            return tens[t]
        return f"{tens[t]} {units[u]}".strip()

    def three_digits(num: int) -> str:
        if num < 100:
            return two_digits(num)

        h = num // 100
        rem = num % 100

        if rem == 0:
            # For exact hundreds in amount phrasing:
            # 100 -> εκατό
            # 200 -> διακοσίων
            if h == 1:
                return "εκατό"
            return hundreds[h]

        return f"{hundreds[h]} {two_digits(rem)}".strip()

    parts: list[str] = []

    millions = n // 1_000_000
    remainder = n % 1_000_000

    thousands = remainder // 1_000
    below_thousand = remainder % 1_000

    if millions:
        if millions == 1:
            parts.append("ενός εκατομμυρίου")
        else:
            parts.append(f"{three_digits(millions)} εκατομμυρίων")

    if thousands:
        if thousands == 1:
            parts.append("χιλίων")
        else:
            parts.append(f"{three_digits(thousands)} χιλιάδων")

    if below_thousand:
        parts.append(three_digits(below_thousand))

    return " ".join(p for p in parts if p).strip()


def _money_words_el(v: Any) -> str:
    """
    Convert a numeric amount to Greek words in genitive case, suitable for:
    'συνολικής αξίας ...' or 'ποσού ...'

    Examples:
    1755.00 -> χιλίων επτακοσίων πενήντα πέντε ευρώ
    1755.20 -> χιλίων επτακοσίων πενήντα πέντε ευρώ και είκοσι λεπτών
    2000.00 -> δύο χιλιάδων ευρώ
    """
    amount = _to_decimal(v).quantize(Decimal("0.01"))

    euros = int(amount)
    cents = int((amount - Decimal(euros)) * 100)

    euro_words = _int_to_greek_words_genitive(euros)

    if cents == 0:
        return f"{euro_words} ευρώ"

    cents_words = _int_to_greek_words_genitive(cents)
    return f"{euro_words} ευρώ και {cents_words} λεπτών"


def _template_path() -> Path:
    app_dir = Path(__file__).resolve().parents[1]
    return app_dir / "templates" / "docx" / "award_decision_template.docx"


def _set_global_font_arial_12(doc: Document) -> None:
    try:
        style = doc.styles["Normal"]
        style.font.name = "Arial"
        style.font.size = Pt(12)
    except Exception:
        pass

    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            run.font.name = "Arial"
            run.font.size = Pt(12)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.name = "Arial"
                        run.font.size = Pt(12)


def _set_cell_alignment(
    cell,
    *,
    horizontal: WD_ALIGN_PARAGRAPH = WD_ALIGN_PARAGRAPH.CENTER,
    vertical: WD_ALIGN_VERTICAL = WD_ALIGN_VERTICAL.CENTER,
) -> None:
    cell.vertical_alignment = vertical
    for paragraph in cell.paragraphs:
        paragraph.alignment = horizontal


def _replace_in_paragraph(paragraph, mapping: dict[str, str]) -> None:
    original = paragraph.text
    updated = original

    for key, value in mapping.items():
        if key in updated:
            updated = updated.replace(key, value)

    if updated != original:
        paragraph.text = updated


def _replace_everywhere(doc: Document, mapping: dict[str, str]) -> None:
    for paragraph in doc.paragraphs:
        _replace_in_paragraph(paragraph, mapping)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _replace_in_paragraph(paragraph, mapping)


def _find_items_table(doc: Document):
    """
    Find the materials/items table in the template.

    Current template contract:
    - 5 columns
    - header includes CPV and ΠΕΡΙΓΡΑΦΗ
    """
    for table in doc.tables:
        if len(table.columns) != 5 or not table.rows:
            continue

        header_text = " ".join(cell.text for cell in table.rows[0].cells).upper()
        if "CPV" in header_text and "ΠΕΡΙΓΡΑΦΗ" in header_text:
            return table

    return None


def _find_cost_table(doc: Document):
    """
    Find the pricing/cost table in the template.

    Current template contract:
    - 6 columns
    - header includes ΤΙΜΗ, ΜΟΝ, ΣΥΝΟΛΟ
    """
    for table in doc.tables:
        if len(table.columns) != 6 or not table.rows:
            continue

        header_text = " ".join(cell.text for cell in table.rows[0].cells).upper()
        if "ΤΙΜΗ" in header_text and "ΜΟΝ" in header_text and "ΣΥΝΟΛΟ" in header_text:
            return table

    return None


def _clear_table_body_keep_header(table, header_rows: int = 1) -> None:
    while len(table.rows) > header_rows:
        tbl = table._tbl
        tr = table.rows[header_rows]._tr
        tbl.remove(tr)


def _fill_items_table(table, materials: list[Any]) -> None:
    _clear_table_body_keep_header(table, header_rows=1)

    if not materials:
        row = table.add_row().cells
        row[0].text = "—"
        row[1].text = "Δεν υπάρχουν γραμμές υλικών/υπηρεσιών."
        row[2].text = "—"
        row[3].text = "—"
        row[4].text = "—"
        for cell in row:
            _set_cell_alignment(cell, horizontal=WD_ALIGN_PARAGRAPH.CENTER, vertical=WD_ALIGN_VERTICAL.CENTER)
        return

    for i, line in enumerate(materials, start=1):
        row = table.add_row().cells
        row[0].text = str(i)
        row[1].text = _safe(getattr(line, "description", None), default="")
        row[2].text = _safe(getattr(line, "unit", None))
        row[3].text = _safe(getattr(line, "quantity", None))
        row[4].text = _safe(getattr(line, "cpv", None))

        for cell in row:
            _set_cell_alignment(cell, horizontal=WD_ALIGN_PARAGRAPH.CENTER, vertical=WD_ALIGN_VERTICAL.CENTER)


def _add_cost_summary_row(table, label: str, amount: Any) -> None:
    row = table.add_row()
    merged_cell = row.cells[0].merge(row.cells[4])
    merged_cell.text = label
    row.cells[5].text = _money_plain(amount)

    _set_cell_alignment(
        merged_cell,
        horizontal=WD_ALIGN_PARAGRAPH.RIGHT,
        vertical=WD_ALIGN_VERTICAL.CENTER,
    )
    _set_cell_alignment(
        row.cells[5],
        horizontal=WD_ALIGN_PARAGRAPH.CENTER,
        vertical=WD_ALIGN_VERTICAL.CENTER,
    )


def _fill_cost_table(table, materials: list[Any], analysis: dict[str, Any]) -> None:
    _clear_table_body_keep_header(table, header_rows=1)

    if not materials:
        row = table.add_row().cells
        for i in range(6):
            row[i].text = "—"
        for cell in row:
            _set_cell_alignment(cell, horizontal=WD_ALIGN_PARAGRAPH.CENTER, vertical=WD_ALIGN_VERTICAL.CENTER)
    else:
        for i, line in enumerate(materials, start=1):
            qty = getattr(line, "quantity", None)
            unit_price = getattr(line, "unit_price", None)
            total_pre_vat = getattr(line, "total_pre_vat", None)

            row = table.add_row().cells
            row[0].text = str(i)
            row[1].text = _safe(getattr(line, "description", None), default="")
            row[2].text = _safe(getattr(line, "unit", None))
            row[3].text = _safe(qty)
            row[4].text = _money_plain(unit_price)
            row[5].text = _money_plain(total_pre_vat)

            for cell in row:
                _set_cell_alignment(
                    cell,
                    horizontal=WD_ALIGN_PARAGRAPH.CENTER,
                    vertical=WD_ALIGN_VERTICAL.CENTER,
                )

    public_withholdings = analysis.get("public_withholdings") or {}
    income_tax = analysis.get("income_tax") or {}

    public_pct = _percent(public_withholdings.get("total_percent", 0))
    income_tax_pct = _percent(income_tax.get("rate_percent", 0))
    vat_pct = _percent(analysis.get("vat_percent", 0))

    _add_cost_summary_row(table, "Μερικό Σύνολο", analysis.get("sum_total", 0))
    _add_cost_summary_row(
        table,
        f"Κρατήσεις Υπερ Δημοσίου ({public_pct}%)",
        public_withholdings.get("total_amount", 0),
    )
    _add_cost_summary_row(
        table,
        f"ΦΕ ({income_tax_pct}%)",
        income_tax.get("amount", 0),
    )
    _add_cost_summary_row(
        table,
        f"ΦΠΑ ({vat_pct}%)",
        analysis.get("vat_amount", 0),
    )
    _add_cost_summary_row(table, "Τελικό Σύνολο", analysis.get("payable_total", 0))


def _winner_supplier_line(winner: Any) -> str:
    name = _safe(getattr(winner, "name", None), default="—")
    afm = _safe(getattr(winner, "afm", None), default="—")
    addr = _safe(getattr(winner, "address", None), default="—")
    city = _safe(getattr(winner, "city", None), default="—")
    phone = _safe(getattr(winner, "phone", None), default="—")
    doy = _safe(getattr(winner, "doy", None), default="—")
    email = _safe(getattr(winner, "email", None), default="—")

    return (
        f"{name} με ΑΦΜ: {afm}, διεύθυνση: {addr}, {city}, "
        f"τηλέφωνο: {phone}, Δ.Ο.Υ.: {doy}, email: {email}"
    )


def _format_recipients(other_suppliers: Iterable[Any]) -> str:
    rows: list[str] = []
    for supplier in list(other_suppliers or []):
        rows.append(f"«{_winner_supplier_line(supplier)}»")

    return "\n".join(rows) if rows else "—"


def _resolve_armodiothtas(procurement: Any) -> str:
    """
    Resolve the responsibility text for the award decision.

    SOURCE OF TRUTH
    ---------------
    The Procurement row stores only:
    - procurement.ale

    The actual responsibility text lives in the ALE–KAE master directory.

    RESOLUTION ORDER
    ----------------
    1. Lookup AleKae row by procurement.ale
    2. Return AleKae.responsibility when present
    3. Fallback to "—"

    IMPORTANT
    ---------
    We intentionally do NOT rely on:
    - procurement.armodiothtas
    - procurement.ale_kae

    because those fields/relationships are not part of the provided current
    Procurement contract.
    """
    ale_code = (getattr(procurement, "ale", None) or "").strip()
    if not ale_code:
        return "—"

    ale_row = get_ale_row_by_code(ale_code)
    if ale_row is None:
        return "—"

    responsibility = getattr(ale_row, "responsibility", None)
    return _safe(responsibility)


def _resolve_document_total(procurement: Any, analysis: dict[str, Any]) -> str:
    grand_total = getattr(procurement, "grand_total", None)
    if grand_total is not None:
        return _money_plain(grand_total)

    payable_total = analysis.get("payable_total")
    if payable_total is not None:
        return _money_plain(payable_total)

    return _money_plain(analysis.get("sum_total", 0))


def _resolve_document_total_value(procurement: Any, analysis: dict[str, Any]) -> Any:
    """
    Resolve the numeric total value that should be displayed in the document
    both numerically and in words.
    """
    grand_total = getattr(procurement, "grand_total", None)
    if grand_total is not None:
        return grand_total

    payable_total = analysis.get("payable_total")
    if payable_total is not None:
        return payable_total

    return analysis.get("sum_total", 0)


def _apply_award_paragraph_vat_text(doc: Document, proc_type: str, vat_percent: Any) -> None:
    vat_is_zero = _to_decimal(vat_percent).quantize(Decimal("0.01")) == Decimal("0.00")
    replacement_tail = ", άνευ ΦΠΑ." if vat_is_zero else " και ΦΠΑ."

    targets = [
        f", {proc_type}.",
        f", {proc_type} .",
        f"/ {proc_type}.",
        f"/{proc_type}.",
    ]

    for paragraph in doc.paragraphs:
        text = paragraph.text or ""
        if "συμπεριλαμβανομένων κρατήσεων" not in text:
            continue

        new_text = text
        for target in targets:
            if target in new_text:
                new_text = new_text.replace(target, replacement_tail)

        new_text = new_text.replace(", άνευ ΦΠΑ/ και ΦΠΑ.", ", άνευ ΦΠΑ.")
        new_text = new_text.replace(", άνευ ΦΠΑ / και ΦΠΑ.", ", άνευ ΦΠΑ.")
        new_text = new_text.replace(", άνευ ΦΠΑ/και ΦΠΑ.", ", άνευ ΦΠΑ.")
        new_text = new_text.replace(", άνευ ΦΠΑ /και ΦΠΑ.", ", άνευ ΦΠΑ.")

        if new_text != text:
            paragraph.text = new_text
            break


def _resolve_handler_directory(procurement: Any) -> str:
    """
    Resolve handler directory from the selected handler assignment first.

    Priority:
    1. procurement.handler_assignment.directory.name
    2. procurement.handler_personnel.directory.name (legacy fallback)
    """
    assignment = getattr(procurement, "handler_assignment", None)
    if assignment is not None:
        directory = getattr(assignment, "directory", None)
        if directory is not None:
            return _safe(getattr(directory, "name", None))

    handler = getattr(procurement, "handler_personnel", None)
    return _safe(getattr(getattr(handler, "directory", None), "name", None))


def _resolve_handler_department(procurement: Any) -> str:
    """
    Resolve handler department from the selected handler assignment first.

    Priority:
    1. procurement.handler_assignment.department.name
    2. procurement.handler_personnel.department.name (legacy fallback)
    """
    assignment = getattr(procurement, "handler_assignment", None)
    if assignment is not None:
        department = getattr(assignment, "department", None)
        if department is not None:
            return _safe(getattr(department, "name", None))

    handler = getattr(procurement, "handler_personnel", None)
    return _safe(getattr(getattr(handler, "department", None), "name", None))


@dataclass(frozen=True)
class AwardDecisionConstants:
    pass


def build_award_decision_docx(
    *,
    procurement: Any,
    service_unit: Any,
    winner: Optional[Any],
    other_suppliers: Iterable[Any],
    analysis: dict,
    is_services: bool,
    constants: Optional[AwardDecisionConstants] = None,
) -> bytes:
    _ = constants

    tpl_path = _template_path()
    if not tpl_path.exists():
        raise FileNotFoundError(f"Template not found: {tpl_path}")

    doc = Document(str(tpl_path))

    proc_type = "παροχή υπηρεσιών" if is_services else "προμήθεια υλικών"

    aay = _safe(getattr(procurement, "aay", None))
    adam_aay = _safe(getattr(procurement, "adam_aay", None))
    identity_prosklisis = _safe(getattr(procurement, "identity_prosklisis", None))
    adam_prosklisis = _safe(getattr(procurement, "adam_prosklisis", None))
    ale = _safe(getattr(procurement, "ale", None))
    current_year = str(getattr(procurement, "fiscal_year", None) or datetime.now().year)

    public_withholdings = analysis.get("public_withholdings") or {}
    income_tax = analysis.get("income_tax") or {}

    public_pct = _percent(public_withholdings.get("total_percent", 0))
    income_tax_pct = _percent(income_tax.get("rate_percent", 0))
    vat_pct = _percent(analysis.get("vat_percent", 0))

    winner_name = _safe(getattr(winner, "name", None), default="—")
    winner_afm = _safe(getattr(winner, "afm", None), default="—")
    winner_line = _winner_supplier_line(winner) if winner is not None else "—"

    commander = _safe(getattr(service_unit, "commander", None), default="—")
    commander_role_type = _safe(getattr(service_unit, "commander_role_type", None))
    service_unit_region = _safe(getattr(service_unit, "region", None))

    document_total_plain = _resolve_document_total(procurement, analysis)
    document_total_value = _resolve_document_total_value(procurement, analysis)

    mapping: dict[str, str] = {
        "{{SHORT_DATE}}": _short_date_el(),
        "{{PROC_TYPE}}": proc_type,
        "{{SERVICE_UNIT_NAME}}": _upper_service_name(
            _safe(getattr(service_unit, "description", None), default="—")
        ),
        "{{SERVICE_UNIT_PHONE}}": _safe(getattr(service_unit, "phone", None)),
        "{{SERVICE_UNIT_REGION}}": service_unit_region,
        "{{procurement.aay}}": aay,
        "{{procurement.adam_aay}}": adam_aay,
        "{{procurement.identity_prosklisis}}": identity_prosklisis,
        "{{procurement.adam_prosklisis}}": adam_prosklisis,
        "{{ procurement.adam_prosklisis}}": adam_prosklisis,
        "{{procurement.ale}}": ale,
        "{{current_year}}": current_year,
        "{{current year}}": current_year,
        "{{armodiothtas}}": _resolve_armodiothtas(procurement),
        "{{WINNER_SUPPLIER_LINE}}": winner_line,
        "{{supplier.name}}": winner_name,
        "{{supplier.afm}}": winner_afm,
        "{{RECIPIENTS_INFO}}": _format_recipients(other_suppliers),
        "{{service.commander}}": commander,
        "{{COMMANDER_ROLE_TYPE}}": commander_role_type,
        "{{AN_PUBLIC_WITHHOLD_PERCENT}}": f" ({public_pct}%)",
        "{{AN_PUBLIC_WITHHOLD_TOTAL}}": _money_plain(public_withholdings.get("total_amount", 0)),
        "{{AN_INCOME_TAX_RATE}}": f" ({income_tax_pct}%)",
        "{{AN_INCOME_TAX_TOTAL}}": _money_plain(income_tax.get("amount", 0)),
        "{{AN_VAT_PERCENT}}": vat_pct,
        "{{AN_VAT_AMOUNT}}": _money_plain(analysis.get("vat_amount", 0)),
        "{{AN_SUM_TOTAL}}": _money_plain(analysis.get("sum_total", 0)),
        "{{AN_PAYABLE_TOTAL}}": _money_plain(analysis.get("payable_total", 0)),
        "{{ML_TOTAL}}": document_total_plain,
        "{{ML_TOTAL_WORDS}}": _money_words_el(document_total_value),
        "{{HANDLER_DIRECTORY}}": _upper_no_accents(_resolve_handler_directory(procurement)),
        "{{HANDLER_DEPARTMENT}}": _resolve_handler_department(procurement),
    }

    _replace_everywhere(doc, mapping)
    _apply_award_paragraph_vat_text(doc, proc_type, analysis.get("vat_percent", 0))

    materials = list(getattr(procurement, "materials", []) or [])

    items_table = _find_items_table(doc)
    if items_table is not None:
        _fill_items_table(items_table, materials)

    cost_table = _find_cost_table(doc)
    if cost_table is not None:
        _fill_cost_table(cost_table, materials, analysis)

    _set_global_font_arial_12(doc)

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def build_award_decision_filename(
    *,
    procurement: Any,
    winner: Optional[Any],
    is_services: bool,
) -> str:
    kind = "Παροχής Υπηρεσιών" if is_services else "Προμήθειας Υλικών"
    supplier_name = _safe(getattr(winner, "name", None), default="—")

    grand_total = getattr(procurement, "grand_total", None)

    if grand_total is None and hasattr(procurement, "compute_payment_analysis"):
        try:
            analysis = procurement.compute_payment_analysis()
            grand_total = analysis.get("payable_total")
        except Exception:
            grand_total = None

    total_str = _money_plain(grand_total)
    return f"Απόφαση Ανάθεσης {kind} {supplier_name} {total_str}.docx"

```

FILE: .\app\reports\expense_transmittal_docx.py
```python
"""
app/reports/expense_transmittal_docx.py

Generate "ΔΙΑΒΙΒΑΣΤΙΚΟ ΔΑΠΑΝΗΣ" as DOCX bytes using a Word template
and placeholder replacement.

SOURCE OF TRUTH
---------------
This implementation is aligned strictly to the provided current template and
the current ServiceUnit / Procurement contract.

IMPORTANT FIELD MAPPING RULES
-----------------------------
The uploaded DOCX contains placeholders that must be resolved from the current
domain objects only.

Current source-of-truth fields used:
- procurement.hop_approval
- procurement.hop_preapproval
- procurement.aay
- procurement.protocol_number
- procurement.committee.identity_text
- procurement.invoice_number
- procurement.invoice_date
- procurement.invoice_receipt_date
- procurement.identity_prosklisis
- service_unit.description
- service_unit.phone
- service_unit.region
- service_unit.curator                     -> APPLICATION_ADMIN
- service_unit.application_admin_directory -> APPLICATION_ADMIN_DIRECTORY

IMPORTANT RENDERING RULES
-------------------------
1. {{SUPPORTING_DOCUMENTS_BLOCK}} must be placed alone in its own paragraph.
2. The supporting-documents block is rendered as separate paragraphs.
3. There must be NO blank paragraphs between η., θ., ι., ...
4. Each generated line must begin with exactly two tab characters.
5. Paragraph tab stops / paragraph properties are cloned from paragraph 'ζ.'.
6. Placeholder replacement must work even when placeholders are split across runs.
7. Run-level formatting in the template must be preserved as much as possible.
"""

from __future__ import annotations

import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from docx import Document
from docx.oxml import OxmlElement
from docx.shared import Pt


# ---------------------------------------------------------------------------
# Generic formatting helpers
# ---------------------------------------------------------------------------

def _safe(value: Any, default: str = "—") -> str:
    """
    Convert any value to a stripped display string.
    """
    text = ("" if value is None else str(value)).strip()
    return text if text else default


def _to_decimal(value: Any) -> Decimal:
    """
    Safely convert numeric-like input to Decimal.
    """
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0.00")


def _money_plain(value: Any) -> str:
    """
    Format decimal-like value using Greek-style separators without currency.

    Example
    -------
    1700.5 -> "1.700,50"
    """
    amount = _to_decimal(value).quantize(Decimal("0.01"))
    text = f"{amount:,.2f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _upper_no_accents(value: Any, default: str = "—") -> str:
    """
    Return uppercase Greek/Latin text without accents/diacritics.
    """
    text = _safe(value, default=default)
    normalized = unicodedata.normalize("NFD", text)
    no_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", no_marks).upper()


def _upper_service_name(name: str) -> str:
    """
    Uppercase service name without accents for official document styling.
    """
    return _upper_no_accents(name)


def _format_date(value: Any, default: str = "—") -> str:
    """
    Format a date value as DD/MM/YYYY.
    """
    if value is None:
        return default

    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    try:
        return value.strftime("%d/%m/%Y")
    except Exception:
        text = str(value).strip()
        return text if text else default


def _short_date_el(value: Any | None = None) -> str:
    """
    Return date in Greek short format: DD Mon YY.

    Examples:
    - 07 Μαρ 26
    - 22 Μαρ 26
    """
    months = {
        1: "Ιαν",
        2: "Φεβ",
        3: "Μαρ",
        4: "Απρ",
        5: "Μαϊ",
        6: "Ιουν",
        7: "Ιουλ",
        8: "Αυγ",
        9: "Σεπ",
        10: "Οκτ",
        11: "Νοε",
        12: "Δεκ",
    }

    dt = value or datetime.now()

    try:
        day = int(dt.day)
        month = int(dt.month)
        year_2d = int(dt.year) % 100
    except Exception:
        dt = datetime.now()
        day = dt.day
        month = dt.month
        year_2d = dt.year % 100

    month_label = months.get(month, "")
    return f"{day:02d} {month_label} {year_2d:02d}".strip()


def _int_to_greek_words_genitive(n: int) -> str:
    """
    Convert a non-negative integer to Greek words in genitive case,
    suitable for phrases like:

    - συνολικής αξίας ...
    - ποσού ...

    Examples:
    1755 -> χιλίων επτακοσίων πενήντα πέντε
    20   -> είκοσι
    200  -> διακοσίων
    """
    if n < 0:
        raise ValueError("Negative values are not supported.")
    if n == 0:
        return "μηδενός"

    units = {
        0: "",
        1: "ενός",
        2: "δύο",
        3: "τριών",
        4: "τεσσάρων",
        5: "πέντε",
        6: "έξι",
        7: "επτά",
        8: "οκτώ",
        9: "εννέα",
    }

    teens = {
        10: "δέκα",
        11: "έντεκα",
        12: "δώδεκα",
        13: "δεκατριών",
        14: "δεκατεσσάρων",
        15: "δεκαπέντε",
        16: "δεκαέξι",
        17: "δεκαεπτά",
        18: "δεκαοκτώ",
        19: "δεκαεννέα",
    }

    tens = {
        2: "είκοσι",
        3: "τριάντα",
        4: "σαράντα",
        5: "πενήντα",
        6: "εξήντα",
        7: "εβδομήντα",
        8: "ογδόντα",
        9: "ενενήντα",
    }

    hundreds = {
        1: "εκατόν",
        2: "διακοσίων",
        3: "τριακοσίων",
        4: "τετρακοσίων",
        5: "πεντακοσίων",
        6: "εξακοσίων",
        7: "επτακοσίων",
        8: "οκτακοσίων",
        9: "εννιακοσίων",
    }

    def two_digits(num: int) -> str:
        if num < 10:
            return units[num]
        if 10 <= num <= 19:
            return teens[num]

        t = num // 10
        u = num % 10
        if u == 0:
            return tens[t]
        return f"{tens[t]} {units[u]}".strip()

    def three_digits(num: int) -> str:
        if num < 100:
            return two_digits(num)

        h = num // 100
        rem = num % 100

        if rem == 0:
            if h == 1:
                return "εκατό"
            return hundreds[h]

        return f"{hundreds[h]} {two_digits(rem)}".strip()

    parts: list[str] = []

    millions = n // 1_000_000
    remainder = n % 1_000_000

    thousands = remainder // 1_000
    below_thousand = remainder % 1_000

    if millions:
        if millions == 1:
            parts.append("ενός εκατομμυρίου")
        else:
            parts.append(f"{three_digits(millions)} εκατομμυρίων")

    if thousands:
        if thousands == 1:
            parts.append("χιλίων")
        else:
            parts.append(f"{three_digits(thousands)} χιλιάδων")

    if below_thousand:
        parts.append(three_digits(below_thousand))

    return " ".join(p for p in parts if p).strip()


def _money_words_el(value: Any) -> str:
    """
    Convert a numeric amount to Greek words in genitive case, suitable for:
    'συνολικής αξίας ...' or 'ποσού ...'

    Examples:
    1755.00 -> χιλίων επτακοσίων πενήντα πέντε ευρώ
    1755.20 -> χιλίων επτακοσίων πενήντα πέντε ευρώ και είκοσι λεπτών
    12.40   -> δώδεκα ευρώ και σαράντα λεπτών
    """
    amount = _to_decimal(value).quantize(Decimal("0.01"))

    euros = int(amount)
    cents = int((amount - Decimal(euros)) * 100)

    euro_words = _int_to_greek_words_genitive(euros)

    if cents == 0:
        return f"{euro_words} ευρώ"

    cents_words = _int_to_greek_words_genitive(cents)
    return f"{euro_words} ευρώ και {cents_words} λεπτών"


def _template_path() -> Path:
    """
    Resolve the DOCX template path.
    """
    app_dir = Path(__file__).resolve().parents[1]
    return app_dir / "templates" / "docx" / "expense_transmittal_template.docx"


# ---------------------------------------------------------------------------
# DOCX low-level helpers
# ---------------------------------------------------------------------------

def _clone_paragraph_properties(src_paragraph, dst_paragraph) -> None:
    """
    Clone paragraph properties XML (including tabs, indents, spacing, alignment).
    """
    dst_p = dst_paragraph._p
    src_p = src_paragraph._p

    if dst_p.pPr is not None:
        dst_p.remove(dst_p.pPr)

    if src_p.pPr is not None:
        dst_p.insert(0, deepcopy(src_p.pPr))


def _copy_run_style(src_run, dst_run) -> None:
    """
    Copy run-level style.
    """
    if src_run is None:
        return

    dst_run.bold = src_run.bold
    dst_run.italic = src_run.italic
    dst_run.underline = src_run.underline
    dst_run.font.name = src_run.font.name
    dst_run.font.size = src_run.font.size

    try:
        if src_run.font.color is not None and src_run.font.color.rgb is not None:
            dst_run.font.color.rgb = src_run.font.color.rgb
    except Exception:
        pass

    try:
        dst_run.font.highlight_color = src_run.font.highlight_color
    except Exception:
        pass


def _insert_paragraph_after(paragraph):
    """
    Insert and return a new paragraph immediately after the given paragraph.
    """
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    return paragraph._parent.add_paragraph().__class__(new_p, paragraph._parent)


def _clear_paragraph_runs(paragraph) -> None:
    """
    Remove all runs from a paragraph while preserving paragraph properties.
    """
    p = paragraph._p
    for child in list(p):
        if child.tag.endswith("}r") or child.tag.endswith("}hyperlink"):
            p.remove(child)


def _set_global_font_arial_12(doc: Document) -> None:
    """
    Normalize generated report font to Arial 12 where possible.
    """
    try:
        style = doc.styles["Normal"]
        style.font.name = "Arial"
        style.font.size = Pt(12)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Placeholder replacement across runs
# ---------------------------------------------------------------------------

def _paragraph_runs_text(paragraph) -> tuple[str, list[tuple[int, int, int]]]:
    """
    Return paragraph full text and positional map.

    The map contains tuples:
    (run_index, start_offset_in_full_text, end_offset_in_full_text)
    """
    pieces: list[str] = []
    positions: list[tuple[int, int, int]] = []

    cursor = 0
    for idx, run in enumerate(paragraph.runs):
        text = run.text or ""
        pieces.append(text)
        start = cursor
        end = start + len(text)
        positions.append((idx, start, end))
        cursor = end

    return "".join(pieces), positions


def _find_run_index_at_offset(positions: list[tuple[int, int, int]], offset: int) -> int:
    """
    Find the run index containing the given character offset.
    """
    for run_index, start, end in positions:
        if start <= offset < end:
            return run_index

    if positions and offset == positions[-1][2]:
        return positions[-1][0]

    return -1


def _replace_placeholder_once_in_paragraph(paragraph, placeholder: str, replacement: str) -> bool:
    """
    Replace one occurrence of a placeholder in a paragraph, even if the
    placeholder is split across multiple runs.

    The replacement inherits the style of the first run participating in the
    placeholder.
    """
    full_text, positions = _paragraph_runs_text(paragraph)
    if not full_text or placeholder not in full_text:
        return False

    start = full_text.find(placeholder)
    end = start + len(placeholder)

    start_run_idx = _find_run_index_at_offset(positions, start)
    end_run_idx = _find_run_index_at_offset(positions, end - 1)

    if start_run_idx < 0 or end_run_idx < 0:
        return False

    start_run = paragraph.runs[start_run_idx]
    end_run = paragraph.runs[end_run_idx]

    start_run_global_start = positions[start_run_idx][1]
    end_run_global_start = positions[end_run_idx][1]

    prefix = start_run.text[: start - start_run_global_start]
    suffix = end_run.text[(end - end_run_global_start):]

    start_run.text = f"{prefix}{replacement}{suffix}"

    for idx in range(start_run_idx + 1, end_run_idx + 1):
        paragraph.runs[idx].text = ""

    return True


def _replace_placeholder_all_in_paragraph(paragraph, placeholder: str, replacement: str) -> None:
    """
    Replace all occurrences of a placeholder in a paragraph, robustly across runs.
    """
    while _replace_placeholder_once_in_paragraph(paragraph, placeholder, replacement):
        pass


def _replace_placeholders_everywhere(doc: Document, mapping: dict[str, str]) -> None:
    """
    Replace placeholders across all paragraphs and table paragraphs.
    """
    for paragraph in doc.paragraphs:
        for placeholder, replacement in mapping.items():
            _replace_placeholder_all_in_paragraph(paragraph, placeholder, replacement)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for placeholder, replacement in mapping.items():
                        _replace_placeholder_all_in_paragraph(paragraph, placeholder, replacement)


# ---------------------------------------------------------------------------
# Domain formatting helpers
# ---------------------------------------------------------------------------

def _resolve_document_total(procurement: Any, analysis: dict[str, Any]) -> str:
    """
    Resolve the monetary total shown in the transmittal document.

    Resolution order:
    1. procurement.grand_total
    2. analysis["payable_total"]
    3. analysis["sum_total"]
    4. 0.00
    """
    grand_total = getattr(procurement, "grand_total", None)
    if grand_total is not None:
        return _money_plain(grand_total)

    payable_total = analysis.get("payable_total")
    if payable_total is not None:
        return _money_plain(payable_total)

    return _money_plain(analysis.get("sum_total", 0))


def _resolve_document_total_value(procurement: Any, analysis: dict[str, Any]) -> Any:
    """
    Resolve the numeric total value shown in the transmittal document
    for both numeric and text rendering.
    """
    grand_total = getattr(procurement, "grand_total", None)
    if grand_total is not None:
        return grand_total

    payable_total = analysis.get("payable_total")
    if payable_total is not None:
        return payable_total

    return analysis.get("sum_total", 0)


def _resolve_analysis_total(procurement: Any, analysis: dict[str, Any]) -> Decimal:
    """
    Resolve the amount threshold used for supporting-documents visibility.

    The user explicitly requested the amount from the analysis total.
    Resolution order:
    1. analysis["sum_total"]
    2. analysis["payable_total"]
    3. procurement.grand_total
    4. Decimal("0.00")
    """
    if analysis is None:
        analysis = {}

    candidate = analysis.get("sum_total", None)
    if candidate is not None:
        return _to_decimal(candidate)

    candidate = analysis.get("payable_total", None)
    if candidate is not None:
        return _to_decimal(candidate)

    candidate = getattr(procurement, "grand_total", None)
    if candidate is not None:
        return _to_decimal(candidate)

    return Decimal("0.00")


def _winner_supplier_line(winner: Any) -> str:
    """
    Build a supplier identity line suitable for the report body.
    """
    if winner is None:
        return "—"

    name = _safe(getattr(winner, "name", None), default="—")
    afm = _safe(getattr(winner, "afm", None), default="—")
    address = _safe(getattr(winner, "address", None), default="—")
    city = _safe(getattr(winner, "city", None), default="—")
    phone = _safe(getattr(winner, "phone", None), default="—")
    doy = _safe(getattr(winner, "doy", None), default="—")
    email = _safe(getattr(winner, "email", None), default="—")

    return (
        f"{name} με ΑΦΜ: {afm}, διεύθυνση: {address}, {city}, "
        f"τηλέφωνο: {phone}, Δ.Ο.Υ.: {doy}, email: {email}"
    )


def _resolve_proc_type(procurement: Any) -> str:
    """
    Resolve whether the procurement concerns services or goods.
    """
    materials = list(getattr(procurement, "materials", []) or [])
    is_services = any(bool(getattr(line, "is_service", False)) for line in materials)
    return "παροχής υπηρεσιών" if is_services else "προμήθειας υλικών"


def _resolve_committee_description(procurement: Any) -> str:
    """
    Resolve the linked committee identity text.

    SOURCE OF TRUTH
    ---------------
    ProcurementCommittee exposes both:
    - description
    - identity_text

    The user requested that the document must show the committee identity,
    therefore this field must resolve `identity_text`.
    """
    committee = getattr(procurement, "committee", None)
    if committee is None:
        return "—"
    return _safe(getattr(committee, "identity_text", None))


def _resolve_application_admin(service_unit: Any) -> str:
    """
    Resolve application administrator text.

    SOURCE OF TRUTH
    ---------------
    In the current ServiceUnit model:
    - curator = Διαχειριστής Εφαρμογής
    """
    return _safe(getattr(service_unit, "curator", None))


def _resolve_application_admin_directory(service_unit: Any) -> str:
    """
    Resolve the free-text application-admin directory field.

    SOURCE OF TRUTH
    ---------------
    In the current ServiceUnit model:
    - application_admin_directory = free-text ΔΙΕΥΘΥΝΣΗ
    """
    return _safe(getattr(service_unit, "application_admin_directory", None))


def _greek_enumeration_labels() -> list[str]:
    """
    Ordered Greek labels for the supporting-documents block.
    """
    return [
        "η.",
        "θ.",
        "ι.",
        "ια.",
        "ιβ.",
        "ιγ.",
        "ιδ.",
        "ιε.",
        "ιστ.",
        "ιζ.",
        "ιη.",
        "ιθ.",
        "κ.",
    ]


def _build_supporting_document_items(procurement: Any, analysis: dict[str, Any]) -> list[str]:
    """
    Build the supporting-document item texts according to the requested amount thresholds.
    """
    total_amount = _resolve_analysis_total(procurement, analysis)

    full_items = [
        f"Πρόσκληση Υποβολής Προσφοράς με {_safe(getattr(procurement, 'identity_prosklisis', None))}.",
        "Βεβαίωση ΙΒΑΝ.",
        "Υπεύθυνη δήλωση στοιχείων επικοινωνίας και τραπεζικών στοιχείων.",
        "Πιστοποιητικό Εκπροσώπησης.",
        "Υπεύθυνη Δήλωση μη υποχρέωσης ένταξης στο Εθνικό Μητρώο Παραγωγών.",
        "Υπεύθυνη Δήλωση μη δωροδοκίας.",
        "Αντίγραφο Ποινικού Μητρώου.",
        "Αποδεικτικό Φορολογικής Ενημερότητας.",
        "Αποδεικτικό Ασφαλιστικής Ενημερότητας.",
    ]

    if total_amount < Decimal("1500"):
        return [
            "Βεβαίωση ΙΒΑΝ.",
            "Υπεύθυνη δήλωση στοιχείων επικοινωνίας και τραπεζικών στοιχείων.",
        ]

    if total_amount < Decimal("2500"):
        return [
            "Βεβαίωση ΙΒΑΝ.",
            "Υπεύθυνη δήλωση στοιχείων επικοινωνίας και τραπεζικών στοιχείων.",
            "Αποδεικτικό Φορολογικής Ενημερότητας.",
        ]

    return full_items


# ---------------------------------------------------------------------------
# Supporting documents block rendering
# ---------------------------------------------------------------------------

def _find_reference_paragraph_for_supporting_block(doc: Document):
    """
    Find the paragraph that starts with 'ζ.' and use it as the formatting
    source for the generated supporting-documents block.
    """
    def _matches(paragraph) -> bool:
        text = (paragraph.text or "").strip()
        return text.startswith("ζ.")

    for paragraph in doc.paragraphs:
        if _matches(paragraph):
            return paragraph

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    if _matches(paragraph):
                        return paragraph

    return None


def _render_supporting_documents_block_in_paragraph(
    paragraph,
    items: list[str],
    formatting_source_paragraph=None,
) -> None:
    """
    Render supporting documents as consecutive paragraphs.

    The generated η./θ./ι./... paragraphs inherit paragraph formatting from
    paragraph 'ζ.' (tabs, alignment, spacing, line spacing, indentation).
    """
    labels = _greek_enumeration_labels()

    source_paragraph = formatting_source_paragraph or paragraph
    template_run = source_paragraph.runs[0] if source_paragraph.runs else (
        paragraph.runs[0] if paragraph.runs else None
    )

    _clear_paragraph_runs(paragraph)
    _clone_paragraph_properties(source_paragraph, paragraph)

    anchor = paragraph

    for idx, item in enumerate(items):
        if idx >= len(labels):
            raise ValueError("Not enough Greek enumeration labels for supporting documents block.")

        target = anchor if idx == 0 else _insert_paragraph_after(anchor)
        _clone_paragraph_properties(source_paragraph, target)

        run = target.add_run(f"\t\t{labels[idx]}\t{item}")
        _copy_run_style(template_run, run)

        anchor = target


def _render_supporting_documents_block(doc: Document, placeholder: str, items: list[str]) -> None:
    """
    Find the placeholder paragraph and replace it with the rendered block.

    The generated paragraphs inherit formatting from the paragraph that starts
    with 'ζ.'.
    """
    formatting_source_paragraph = _find_reference_paragraph_for_supporting_block(doc)

    for paragraph in doc.paragraphs:
        if placeholder in paragraph.text:
            _render_supporting_documents_block_in_paragraph(
                paragraph=paragraph,
                items=items,
                formatting_source_paragraph=formatting_source_paragraph,
            )
            return

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    if placeholder in paragraph.text:
                        _render_supporting_documents_block_in_paragraph(
                            paragraph=paragraph,
                            items=items,
                            formatting_source_paragraph=formatting_source_paragraph,
                        )
                        return


# ---------------------------------------------------------------------------
# Public report API
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExpenseTransmittalConstants:
    """
    Future-proof constants container.
    """
    pass


def build_expense_transmittal_docx(
    *,
    procurement: Any,
    service_unit: Any,
    winner: Optional[Any],
    analysis: dict[str, Any],
    constants: Optional[ExpenseTransmittalConstants] = None,
) -> bytes:
    """
    Build the expense transmittal DOCX as bytes.
    """
    _ = constants

    template_path = _template_path()
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    doc = Document(str(template_path))

    proc_type = _resolve_proc_type(procurement)
    winner_line = _winner_supplier_line(winner)
    ml_total = _resolve_document_total(procurement, analysis)
    ml_total_words = _money_words_el(_resolve_document_total_value(procurement, analysis))
    committee_description = _resolve_committee_description(procurement)
    application_admin = _resolve_application_admin(service_unit)
    application_admin_directory = _resolve_application_admin_directory(service_unit)
    supporting_items = _build_supporting_document_items(procurement, analysis)

    invoice_number = _safe(getattr(procurement, "invoice_number", None))
    invoice_date = _format_date(getattr(procurement, "invoice_date", None))
    invoice_receipt_date = _format_date(getattr(procurement, "invoice_receipt_date", None))
    identity_prosklisis = _safe(getattr(procurement, "identity_prosklisis", None))

    mapping: dict[str, str] = {
        "{{SERVICE_UNIT_NAME}}": _upper_service_name(
            _safe(getattr(service_unit, "description", None), default="—")
        ),
        "{{APPLICATION_ADMIN_DIRECTORY}}": application_admin_directory,
        "{{APPLICATION_ADMIN}}": application_admin,
        "{{SERVICE_UNIT_PHONE}}": _safe(getattr(service_unit, "phone", None)),
        "{{SERVICE_UNIT_REGION}}": _safe(getattr(service_unit, "region", None)),
        "{{SHORT_DATE}}": _short_date_el(),
        "{{PROC_TYPE}}": proc_type,
        "{{procurement.hop_approval}}": _safe(getattr(procurement, "hop_approval", None)),
        "{{procurement.hop_preapproval}}": _safe(getattr(procurement, "hop_preapproval", None)),
        "{{procurement. hop_preapproval}}": _safe(getattr(procurement, "hop_preapproval", None)),
        "{{procurement.aay}}": _safe(getattr(procurement, "aay", None)),
        "{{procurement.protocol_number}}": _safe(getattr(procurement, "protocol_number", None)),
        "{{procurement. protocol_number}}": _safe(getattr(procurement, "protocol_number", None)),
        "{{procurement.committee_description}}": committee_description,
        "{{WINNER_SUPPLIER_LINE}}": winner_line,
        "{{procurement.invoice_number}}": invoice_number,
        "{{procurement.invoice_date}}": invoice_date,
        "{{ML_TOTAL}}": ml_total,
        "{{ML_TOTAL_WORDS}}": ml_total_words,
        "{{procurement.invoice_receipt_date}}": invoice_receipt_date,
        "{{procurement.identity_prosklisis}}": identity_prosklisis,

        # Legacy placeholders retained defensively
        "{{ProcurementCommittee.description}}": committee_description,
        "{{procurement.invoice}}": invoice_number,
        "{{procurement.date}}": invoice_date,
        "{{MANAGER_SERVICE}}": application_admin,
    }

    _replace_placeholders_everywhere(doc, mapping)

    _render_supporting_documents_block(
        doc=doc,
        placeholder="{{SUPPORTING_DOCUMENTS_BLOCK}}",
        items=supporting_items,
    )

    _set_global_font_arial_12(doc)

    output = BytesIO()
    doc.save(output)
    return output.getvalue()


def build_expense_transmittal_filename(
    *,
    procurement: Any,
    winner: Optional[Any],
) -> str:
    """
    Build a readable output filename for the generated DOCX.
    """
    supplier_name = _safe(getattr(winner, "name", None), default="—")

    grand_total = getattr(procurement, "grand_total", None)
    if grand_total is None and hasattr(procurement, "compute_payment_analysis"):
        try:
            computed_analysis = procurement.compute_payment_analysis()
            grand_total = computed_analysis.get("payable_total")
        except Exception:
            grand_total = None

    total_str = _money_plain(grand_total)
    return f"Διαβιβαστικό Δαπάνης {supplier_name} {total_str}.docx"

```

FILE: .\app\reports\proforma_invoice.py
```python
# app/reports/proforma_invoice.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from typing import Any, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import os

@dataclass(frozen=True)
class ProformaConstants:
    pn_afm: str
    pn_doy: str
    reference_goods: str


def _money(v: Any) -> str:
    try:
        d = Decimal(str(v or "0"))
    except Exception:
        d = Decimal("0")
    d = d.quantize(Decimal("0.01"))
    # ελληνικό friendly: 1.234,56
    s = f"{d:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


def _safe(v: Any) -> str:
    s = ("" if v is None else str(v)).strip()
    return s if s else "—"


def _register_greek_font() -> str:
    """
    Ensure a TTF font that supports Greek is registered.

    Strategy:
    1) Try DejaVu Sans if available (best cross-platform if you ship it).
    2) Try Windows Arial.
    3) Fall back to Helvetica (may break Greek glyphs on some machines).
    """
    here = os.path.dirname(__file__)
    dejavu_path = os.path.join(here, "..", "static", "fonts", "DejaVuSans.ttf")
    dejavu_path = os.path.normpath(dejavu_path)

    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", dejavu_path))
        return "DejaVuSans"
    except Exception:
        pass
    
    candidates = [
        # ("DejaVuSans", "app/static/fonts/DejaVuSans.ttf"),
        ("Arial", r"C:\Windows\Fonts\arial.ttf"),
        ("ArialUnicode", r"C:\Windows\Fonts\arialuni.ttf"),
    ]
    for name, path in candidates:
        try:
            pdfmetrics.registerFont(TTFont(name, path))
            return name
        except Exception:
            continue
    return "Helvetica"


def build_proforma_invoice_pdf(
    procurement: Any,
    service_unit: Any,
    winner: Optional[Any],
    analysis: dict,
    table_title: str,
    constants: ProformaConstants,
) -> bytes:
    font_name = _register_greek_font()

    styles = getSampleStyleSheet()
    base = ParagraphStyle(
        "base",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10,
        leading=12,
        spaceAfter=0,
    )
    small = ParagraphStyle(
        "small",
        parent=base,
        fontSize=9,
        leading=11,
    )
    title = ParagraphStyle(
        "title",
        parent=base,
        fontSize=14,
        leading=16,
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    h = ParagraphStyle(
        "h",
        parent=base,
        fontSize=11,
        leading=13,
        spaceBefore=6,
        spaceAfter=4,
    )
    right = ParagraphStyle("right", parent=base, alignment=TA_RIGHT)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Προτιμολόγιο",
        author="Invoice Management System",
        subject="Προτιμολόγιο",
    )

    elems = []
    elems.append(Paragraph("ΠΡΟΤΙΜΟΛΟΓΙΟ", title))
    elems.append(Spacer(1, 6))

    # -------------------------
    # HEADER (2 columns)
    # -------------------------
    left_lines = [
        "<b>ΣΤΟΙΧΕΙΑ ΠΟΛΕΜΙΚΟΥ ΝΑΥΤΙΚΟΥ</b>",
        f"<b>ΕΠΩΝΥΜΙΑ:</b> ΠΟΛΕΜΙΚΟ ΝΑΥΤΙΚΟ - {_safe(getattr(service_unit, 'description', None))}",
        f"<b>ΔΙΕΥΘΥΝΣΗ:</b> {_safe(getattr(service_unit, 'address', None))}",
    ]
    phone = _safe(getattr(service_unit, "phone", None))
    if phone != "—":
        left_lines.append(f"<b>ΤΗΛΕΦΩΝΟ:</b> {phone}")

    left_lines += [
        f"<b>ΑΦΜ:</b> {constants.pn_afm}",
        f"<b>ΔΟΥ:</b> {constants.pn_doy}",
        f"<b>ΑΡΙΘΜΟΣ ΑΑΗΤ:</b> {_safe(getattr(service_unit, 'aahit', None))}",
        f"<b>ΣΤΟΙΧΕΙΟ ΑΝΑΦΟΡΑΣ ΑΓΑΘΟΥ:</b> {constants.reference_goods}",
    ]

    right_lines = [
        "<b>ΣΤΟΙΧΕΙΑ ΑΝΑΔΟΧΟΥ ΦΟΡΕΑ</b>",
        f"<b>ΕΠΩΝΥΜΙΑ:</b> {_safe(getattr(winner, 'name', None) if winner else None)}",
        f"<b>ΑΦΜ:</b> {_safe(getattr(winner, 'afm', None) if winner else None)}",
        f"<b>EMAIL:</b> {_safe(getattr(winner, 'email', None) if winner else None)}",
        f"<b>ΕΜΠΑ:</b> {_safe(getattr(winner, 'emba', None) if winner else None)}",
        f"<b>ΔΙΕΥΘΥΝΣΗ:</b> {_safe(getattr(winner, 'address', None) if winner else None)}",
        f"<b>ΠΟΛΗ:</b> {_safe(getattr(winner, 'city', None) if winner else None)}",
        f"<b>Τ.Κ.:</b> {_safe(getattr(winner, 'postal_code', None) if winner else None)}",
        f"<b>ΧΩΡΑ:</b> {_safe(getattr(winner, 'country', None) if winner else None)}",
    ]

    header_table = Table(
        [
            [
                Paragraph("<br/>".join(left_lines), small),
                Paragraph("<br/>".join(right_lines), small),
            ]
        ],
        colWidths=[(A4[0] - 28 * mm) / 2, (A4[0] - 28 * mm) / 2],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (0, 0), 0.8, colors.black),
                ("BOX", (1, 0), (1, 0), 0.8, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elems.append(header_table)
    elems.append(Spacer(1, 10))

    # -------------------------
    # META
    # -------------------------
    elems.append(Paragraph(f"<b>Σύντομη Περιγραφή:</b> {_safe(getattr(procurement, 'description', None))}", base))
    elems.append(Paragraph(f"<b>ΑΛΕ:</b> {_safe(getattr(procurement, 'ale', None))}", base))
    elems.append(Spacer(1, 10))

    # -------------------------
    # LINES TABLE
    # -------------------------
    elems.append(Paragraph(table_title, ParagraphStyle("tt", parent=h, alignment=TA_CENTER)))
    elems.append(Spacer(1, 4))

    data = [
        [
            Paragraph("<b>Α/Α</b>", small),
            Paragraph("<b>ΠΕΡΙΓΡΑΦΗ</b>", small),
            Paragraph("<b>CPV</b>", small),
            Paragraph("<b>Μ/Μ</b>", small),
            Paragraph("<b>ΠΟΣΟΤΗΤΑ</b>", small),
            Paragraph("<b>ΤΙΜ. ΜΟΝ.</b>", small),
            Paragraph("<b>ΣΥΝΟΛΟ</b>", small),
        ]
    ]

    lines = list(getattr(procurement, "materials", []) or [])
    if lines:
        for i, ln in enumerate(lines, start=1):
            qty = getattr(ln, "quantity", None)
            unit_price = getattr(ln, "unit_price", None)
            total_pre_vat = getattr(ln, "total_pre_vat", None)

            data.append(
                [
                    Paragraph(str(i), small),
                    Paragraph(_safe(getattr(ln, "description", None)), small),
                    Paragraph(_safe(getattr(ln, "cpv", None)), small),
                    Paragraph(_safe(getattr(ln, "unit", None)), small),
                    Paragraph(_safe(qty), ParagraphStyle("rq", parent=small, alignment=TA_RIGHT)),
                    Paragraph(_safe(unit_price), ParagraphStyle("rup", parent=small, alignment=TA_RIGHT)),
                    Paragraph(_money(total_pre_vat), ParagraphStyle("rt", parent=small, alignment=TA_RIGHT)),
                ]
            )
    else:
        data.append([Paragraph("—", small)] + [Paragraph("Δεν υπάρχουν γραμμές υλικών/υπηρεσιών.", small)] + [Paragraph("", small)] * 5)

    col_widths = [14 * mm, 78 * mm, 20 * mm, 18 * mm, 18 * mm, 22 * mm, 24 * mm]
    lines_table = Table(data, colWidths=col_widths, repeatRows=1)
    lines_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.7, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    elems.append(lines_table)
    elems.append(Spacer(1, 10))

    # -------------------------
    # ANALYSIS
    # -------------------------
    elems.append(Paragraph("ΑΝΑΛΥΣΗ ΔΑΠΑΝΗΣ", h))

    pw = analysis.get("public_withholdings") or {}
    it = analysis.get("income_tax") or {}

    analysis_rows = [
        ["ΠΙΣΤΩΣΗ ΧΩΡΙΣ ΦΠΑ", _money(analysis.get("sum_total"))],
        [f"ΚΡΑΤΗΣΕΙΣ ΥΠΕΡ ΔΗΜΟΣΙΟΥ ({_safe(pw.get('total_percent'))}%)", _money(pw.get("total_amount"))],
    ]
    items = pw.get("items") or []
    if items:
        for item in items:
            analysis_rows.append(
                [f"— {_safe(item.get('label'))} ({_safe(item.get('percent'))}%)", _money(item.get("amount"))]
            )


    analysis_rows += [
        [f"ΦΟΡΟΣ ΕΙΣΟΔΗΜΑΤΟΣ ({_safe(it.get('rate_percent'))}%)", _money(it.get("amount"))],
        [f"ΦΠΑ ({_safe(analysis.get('vat_percent'))}%)", _money(analysis.get("vat_amount"))],
        ["ΤΕΛΙΚΟ ΠΛΗΡΩΤΕΟ ΠΟΣΟ", _money(analysis.get("payable_total"))],
    ]

    analysis_tbl = Table(
        [[Paragraph(_safe(a), base), Paragraph(_safe(b), ParagraphStyle("ar", parent=base, alignment=TA_RIGHT))] for a, b in analysis_rows],
        colWidths=[(A4[0] - 28 * mm) * 0.72, (A4[0] - 28 * mm) * 0.28],
    )
    analysis_tbl.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.7, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elems.append(analysis_tbl)
    elems.append(Spacer(1, 10))

    # -------------------------
    # JUSTIFICATIONS (conditional)
    # -------------------------
    elems.append(Paragraph("ΔΙΚΑΙΟΛΟΓΗΤΙΚΑ ΠΛΗΡΩΜΗΣ ΤΙΜΟΛΟΓΙΟΥ", h))

    base_amount = analysis.get("sum_total") or Decimal("0")
    try:
        base_amount_dec = Decimal(str(base_amount))
    except Exception:
        base_amount_dec = Decimal("0")

    items = []
    items.append(" Υπεύθυνη Δήλωση.")
    items.append(" Βεβαίωση ΙΒΑΝ (εάν αναγράφεται στο τιμολόγιο δεν χρειάζεται).")

    if base_amount >= Decimal("1500"):
        items.append(" Πιστοποιητικό Φορολογικής Ενημερότητας.")

    if base_amount >= Decimal("2500"):
        items.append(" Πιστοποιητικό Ασφαλιστικής Ενημερότητας.")
        items.append(" Πιστοποιητικό Νόμιμης Εκπροσώπησης (πρέπει να αναγράφονται αναλυτικά οι εκπρόσωποι).")
        items.append(" Αντίγραφο Ποινικού Μητρώου.")

    elems.append(Paragraph("• " + "<br/>• ".join(items), base))
    elems.append(Spacer(1, 4))
    

    doc.build(elems)
    return buf.getvalue()


```

FILE: .\app\security\__init__.py
```python
"""
app/security/__init__.py

Public security facade for the Invoice / Procurement Management System.

PURPOSE
-------
This package provides the stable public import surface for security helpers
used across the application.

PACKAGE STRUCTURE
-----------------
- app.security.permissions
    Canonical authorization predicates and scope checks

- app.security.decorators
    Reusable Flask route decorators

- app.security
    Shared response helpers, request-level guard, and public re-exports

SECURITY PRINCIPLES
-------------------
1. The UI is never trusted.
2. Navigation visibility is not authorization.
3. All permission checks are enforced server-side.
4. Non-admin users are limited to their own ServiceUnit scope.
5. Viewers are read-only except for explicitly allowed self-service actions.
"""

from __future__ import annotations

from typing import Optional, Tuple

from flask import abort, render_template, request
from flask_login import current_user

from .permissions import (
    can_edit_procurement,
    can_manage_service_unit,
    can_view_procurement,
    is_admin,
    is_manager_or_deputy,
)

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _forbidden() -> Tuple[str, int]:
    """
    Render the standard 403 page.
    """
    return render_template("errors/403.html"), 403


def _abort_or_render_forbidden() -> None:
    """
    Abort with HTTP 403.
    """
    abort(403)


def viewer_readonly_guard() -> Optional[Tuple[str, int]]:
    """
    Block mutating requests for authenticated read-only viewer users.
    """
    if request.method not in MUTATING_METHODS:
        return None

    if not current_user.is_authenticated:
        return None

    if is_admin() or is_manager_or_deputy():
        return None

    endpoint = (request.endpoint or "").strip()
    allow_mutating_endpoints = {
        "settings.theme",
        "settings.feedback",
        "auth.logout",
    }

    if endpoint in allow_mutating_endpoints:
        return None

    return _forbidden()


from .decorators import (  # noqa: E402
    admin_required,
    ensure_manage_service_unit_or_403,
    manager_required,
    org_manage_required,
    procurement_access_required,
    procurement_edit_required,
)

__all__ = [
    "MUTATING_METHODS",
    "_forbidden",
    "_abort_or_render_forbidden",
    "viewer_readonly_guard",
    "is_admin",
    "is_manager_or_deputy",
    "can_view_procurement",
    "can_edit_procurement",
    "can_manage_service_unit",
    "admin_required",
    "manager_required",
    "procurement_access_required",
    "procurement_edit_required",
    "org_manage_required",
    "ensure_manage_service_unit_or_403",
]


```

FILE: .\app\security\admin_guards.py
```python
"""
app/security/admin_guards.py

Reusable authorization helpers specific to admin/organization management flows.

PURPOSE
-------
This module centralizes route-level authorization rules that are specific to
the admin blueprint's organization/personnel workflows.

WHY THIS FILE EXISTS
--------------------
Previously, `app/blueprints/admin/routes.py` contained local decorators and
scope checks such as:
- admin OR manager-only access
- manager-scoped personnel edit checks
- service-unit scope enforcement for organization setup

Those checks are authorization concerns, not route orchestration concerns.

Moving them here keeps route files smaller and makes the rules reusable from
other blueprints if needed later.

DESIGN INTENT
-------------
- function-first
- small explicit guards
- no abstract authorization framework
- no route rendering here

BOUNDARY
--------
This module MAY:
- define decorators
- enforce 403-style scope checks
- inspect current_user

This module MUST NOT:
- flash messages
- redirect users
- query template context
- perform business mutations
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from flask import abort
from flask_login import current_user

from ..models import Personnel

F = TypeVar("F", bound=Callable[..., Any])


def is_admin_or_manager() -> bool:
    """
    Return True for:
    - authenticated admin
    - authenticated ServiceUnit manager

    IMPORTANT
    ---------
    Deputy users are intentionally excluded from this rule, because the admin
    organization/personnel screens were explicitly described as manager-only
    for non-admin users.
    """
    if not current_user.is_authenticated:
        return False

    if getattr(current_user, "is_admin", False):
        return True

    is_mgr = getattr(current_user, "is_manager", None)
    return bool(callable(is_mgr) and is_mgr())


def admin_or_manager_required(view_func: F) -> F:
    """
    Decorator for routes accessible to:
    - admin
    - ServiceUnit manager

    EXCLUDED
    --------
    - deputy
    - viewer
    - anonymous

    RETURNS
    -------
    callable
        Wrapped Flask view function.
    """
    @wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any):
        if not is_admin_or_manager():
            abort(403)
        return view_func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def ensure_personnel_manage_scope_or_403(person: Personnel) -> None:
    """
    Enforce personnel edit/view mutation scope for the admin blueprint.

    RULES
    -----
    - admin: may access any Personnel
    - manager: only Personnel of their own ServiceUnit

    PARAMETERS
    ----------
    person:
        Target Personnel ORM entity.

    RAISES
    ------
    403
        When the current user is outside the allowed scope.
    """
    if getattr(current_user, "is_admin", False):
        return

    scope_service_unit_id = getattr(current_user, "service_unit_id", None)
    if not scope_service_unit_id or person.service_unit_id != scope_service_unit_id:
        abort(403)


def ensure_organization_service_unit_scope_or_403(service_unit_id: int | None) -> None:
    """
    Enforce organization-management scope for a target ServiceUnit.

    RULES
    -----
    - admin: any ServiceUnit allowed
    - manager: only their own ServiceUnit allowed

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit id.

    RAISES
    ------
    403
        When the current user is outside the allowed scope.
    """
    if service_unit_id is None:
        abort(403)

    if getattr(current_user, "is_admin", False):
        return

    scope_service_unit_id = getattr(current_user, "service_unit_id", None)
    if not scope_service_unit_id or service_unit_id != scope_service_unit_id:
        abort(403)


__all__ = [
    "is_admin_or_manager",
    "admin_or_manager_required",
    "ensure_personnel_manage_scope_or_403",
    "ensure_organization_service_unit_scope_or_403",
]


```

FILE: .\app\security\decorators.py
```python
"""
app/security_decorators.py

Reusable authorization decorators for the Invoice / Procurement Management
System.

PURPOSE
-------
This module contains route decorators that enforce access rules by reusing the
canonical authorization predicates from `app.permissions`.

WHY THIS FILE EXISTS
--------------------
Decorators are not the same thing as permission predicates.

- Predicates answer: "is this action allowed?"
- Decorators answer: "how do we enforce that rule on a Flask route?"

Separating them makes both sides cleaner:
- predicates become reusable from services or non-route code
- decorators remain thin wrappers around stable rules
- route modules stay smaller and easier to scan

IMPORTANT
---------
Decorators must preserve wrapped function metadata, so `functools.wraps`
is used everywhere.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from flask_login import current_user

from .permissions import (
    can_edit_procurement,
    can_manage_service_unit,
    can_view_procurement,
    is_admin,
    is_manager_or_deputy,
)
from . import _forbidden

F = TypeVar("F", bound=Callable[..., Any])


def admin_required(view_func: F) -> F:
    """
    Decorator for admin-only routes.

    PARAMETERS
    ----------
    view_func:
        Flask view function.

    RETURNS
    -------
    callable
        Wrapped view function that denies access for non-admin users.
    """
    @wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any):
        if not is_admin():
            return _forbidden()
        return view_func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def manager_required(view_func: F) -> F:
    """
    Decorator for routes accessible to:
    - admin
    - manager
    - deputy

    TYPICAL USE
    -----------
    Pages such as procurement committees or unit-level management actions.
    """
    @wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any):
        if not current_user.is_authenticated:
            return _forbidden()

        if not (is_admin() or is_manager_or_deputy()):
            return _forbidden()

        return view_func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def procurement_access_required(get_procurement_func: Callable[..., Any]) -> Callable[[F], F]:
    """
    Decorator factory for procurement VIEW access.

    PARAMETERS
    ----------
    get_procurement_func:
        Callable that retrieves the procurement from route kwargs.

    EXAMPLE
    -------
        @procurement_access_required(
            lambda procurement_id: Procurement.query.get_or_404(procurement_id)
        )
        def view(procurement_id): ...
    """
    def decorator(view_func: F) -> F:
        @wraps(view_func)
        def wrapper(*args: Any, **kwargs: Any):
            procurement = get_procurement_func(**kwargs)

            if not can_view_procurement(procurement):
                return _forbidden()

            return view_func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def procurement_edit_required(get_procurement_func: Callable[..., Any]) -> Callable[[F], F]:
    """
    Decorator factory for procurement EDIT access.

    PARAMETERS
    ----------
    get_procurement_func:
        Callable that retrieves the procurement from route kwargs.

    RULES
    -----
    - Admin: allowed
    - Same ServiceUnit + manager/deputy: allowed
    - Otherwise: denied
    """
    def decorator(view_func: F) -> F:
        @wraps(view_func)
        def wrapper(*args: Any, **kwargs: Any):
            procurement = get_procurement_func(**kwargs)

            if not can_edit_procurement(procurement):
                return _forbidden()

            return view_func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def org_manage_required(view_func: F) -> F:
    """
    Decorator for organization-management pages.

    ALLOWS
    ------
    - admin
    - manager
    - deputy

    IMPORTANT
    ---------
    This decorator alone is not enough for scoped organization actions.
    Routes must still enforce ServiceUnit scope with:

        ensure_manage_service_unit_or_403(service_unit_id)
    """
    @wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any):
        if not current_user.is_authenticated:
            return _forbidden()

        if not (is_admin() or is_manager_or_deputy()):
            return _forbidden()

        return view_func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def ensure_manage_service_unit_or_403(service_unit_id: int | None) -> None:
    """
    Abort the current request with a standard 403 response when the current user
    may not manage the given ServiceUnit.

    USE CASES
    ---------
    Use this helper inside routes for:
    - Directories CRUD
    - Departments CRUD
    - Personnel management
    - Organizational setup actions

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit id that the route is about to mutate or manage.
    """
    if not can_manage_service_unit(service_unit_id):
        from . import _abort_or_render_forbidden
        _abort_or_render_forbidden()


```

FILE: .\app\security\permissions.py
```python
"""
app/permissions.py

Central authorization predicates for the Invoice / Procurement Management
System.

PURPOSE
-------
This module contains pure-ish authorization helpers and scope predicates that
answer questions such as:

- Is the current user an admin?
- Is the current user a manager or deputy?
- Can the current user view this procurement?
- Can the current user edit this procurement?
- Can the current user manage this ServiceUnit?

WHY THIS FILE EXISTS
--------------------
Previously, `app/security.py` mixed:
- response helpers
- role predicates
- request guards
- decorators

Those are related, but not the same responsibility.

By moving permission predicates here:
- authorization rules become easier to find
- route decorators stay thin
- future services can reuse the same permission checks
- business rules are less likely to drift across route files

SECURITY PRINCIPLES
-------------------
1. The UI is never trusted.
2. Navigation visibility is not authorization.
3. All permission checks are enforced server-side.
4. Non-admin users are isolated to their own ServiceUnit scope.
5. Viewers are read-only except where explicitly allowed.

IMPORTANT
---------
These helpers support authorization but do not replace route-level validation.

For example:
- a user may be allowed to manage a ServiceUnit in general
- but a submitted foreign key must still be validated server-side
"""

from __future__ import annotations

from typing import Any

from flask_login import current_user


def is_admin() -> bool:
    """
    Return True when the current user is an authenticated admin.

    RETURNS
    -------
    bool
        True only for authenticated admin users.

    NOTES
    -----
    We explicitly require authentication instead of trusting only an
    `is_admin` attribute to avoid accidental truthy behavior on anonymous
    user proxies.
    """
    return bool(current_user.is_authenticated and getattr(current_user, "is_admin", False))


def is_manager_or_deputy() -> bool:
    """
    Return True when the current user can manage within their ServiceUnit scope.

    ROLE RULE
    ---------
    This maps to the existing user method `current_user.can_manage()` which
    already expresses the application's manager/deputy capability model.

    RETURNS
    -------
    bool
        True for authenticated manager/deputy-style users.
    """
    if not current_user.is_authenticated:
        return False

    can_manage = getattr(current_user, "can_manage", None)
    return bool(callable(can_manage) and can_manage())


def can_view_procurement(procurement: Any) -> bool:
    """
    Return whether the current user may view a Procurement.

    RULES
    -----
    - admin: always allowed
    - non-admin: procurement must belong to the user's ServiceUnit

    PARAMETERS
    ----------
    procurement:
        Procurement-like object with `service_unit_id`.

    RETURNS
    -------
    bool
        True when the procurement is inside the user's visible scope.
    """
    if procurement is None or not current_user.is_authenticated:
        return False

    if is_admin():
        return True

    return bool(
        current_user.service_unit_id
        and getattr(procurement, "service_unit_id", None)
        and int(current_user.service_unit_id) == int(procurement.service_unit_id)
    )


def can_edit_procurement(procurement: Any) -> bool:
    """
    Return whether the current user may edit a Procurement.

    RULES
    -----
    - admin: always allowed
    - non-admin: must be manager/deputy AND same ServiceUnit

    PARAMETERS
    ----------
    procurement:
        Procurement-like object with `service_unit_id`.

    RETURNS
    -------
    bool
        True when the user may mutate the procurement.
    """
    if procurement is None or not current_user.is_authenticated:
        return False

    if is_admin():
        return True

    if not is_manager_or_deputy():
        return False

    return bool(
        current_user.service_unit_id
        and getattr(procurement, "service_unit_id", None)
        and int(current_user.service_unit_id) == int(procurement.service_unit_id)
    )


def can_manage_service_unit(service_unit_id: int | None) -> bool:
    """
    Return whether the current user may manage the given ServiceUnit.

    RULES
    -----
    - admin: may manage any ServiceUnit
    - manager/deputy: may manage only their own ServiceUnit
    - viewer/anonymous: denied

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit id.

    RETURNS
    -------
    bool
        True when the target ServiceUnit is inside the current user's
        management scope.
    """
    if service_unit_id is None or not current_user.is_authenticated:
        return False

    if is_admin():
        return True

    if not is_manager_or_deputy():
        return False

    return bool(
        current_user.service_unit_id
        and int(current_user.service_unit_id) == int(service_unit_id)
    )


```

FILE: .\app\security\procurement_guards.py
```python
"""
app/security/procurement_guards.py

Focused procurement-specific authorization helpers.

PURPOSE
-------
This module contains reusable procurement authorization predicates that are
small enough not to justify decorator factories, but important enough not to
remain duplicated inside route files.

CURRENT SCOPE
-------------
At this stage the module provides a single focused guard:

- can_mutate_procurement(...)

WHY THIS FILE EXISTS
--------------------
The procurement blueprint previously contained a route-local helper for
mutation authorization. Moving that helper here improves:

- module boundaries
- reuse across procurement routes
- consistency of mutation checks
- route thinness

ARCHITECTURAL INTENT
--------------------
This module is intentionally small and function-first.

It does NOT:
- replace route decorators
- replace procurement_access_required(...)
- replace procurement_edit_required(...)

It only provides a reusable predicate for mutation capability checks.
"""

from __future__ import annotations

from ..models import Procurement, User


def can_mutate_procurement(user: User, procurement: Procurement) -> bool:
    """
    Return True only if the given user may mutate the given procurement.

    RULES
    -----
    - admin: always allowed
    - non-admin: must be manager/deputy AND same service unit

    PARAMETERS
    ----------
    user:
        Current authenticated user.
    procurement:
        Target procurement row.

    RETURNS
    -------
    bool
        True if mutation is allowed, else False.

    NOTES
    -----
    This helper assumes the caller has already resolved both:
    - authenticated user
    - target procurement

    Route decorators still remain the primary access-control boundary.
    """
    if user.is_admin:
        return True

    can_manage = getattr(user, "can_manage", None)
    if not callable(can_manage) or not can_manage():
        return False

    return bool(
        user.service_unit_id
        and procurement.service_unit_id
        and int(user.service_unit_id) == int(procurement.service_unit_id)
    )


```

FILE: .\app\security\security.py
```python
"""
app/security/security.py

Legacy security compatibility facade.

PURPOSE
-------
This file preserves the historical module path `app.security.security` while
`app.security` remains the canonical public security facade.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add authorization logic here.
- Import from `app.security` in all new code.
"""

from __future__ import annotations

from . import *  # noqa: F401,F403

```

FILE: .\app\security\settings_guards.py
```python
"""
app/security/settings_guards.py

Settings-specific reusable scope guards.

PURPOSE
-------
This module centralizes reusable authorization checks that were previously
embedded directly inside `app/blueprints/settings/routes.py`.

WHY THIS FILE EXISTS
--------------------
The current settings blueprint contains two scope checks that are clearly not
HTTP-only concerns:

- committee-management scope enforcement
- legacy service-unit structure redirect scope enforcement

Those checks are reused business/security rules about *who may operate on which
ServiceUnit*. They do not belong inside route handlers.

ARCHITECTURAL BOUNDARY
----------------------
This module MAY:
- inspect the authenticated user
- enforce reusable service-unit scope rules
- abort with 403 when access is not allowed

This module MUST NOT:
- read request.form / request.args directly
- query unrelated presentation data
- render templates
- flash messages
- mutate application state

SECURITY PRINCIPLES
-------------------
- UI is never trusted.
- Admin may operate globally where explicitly allowed.
- Non-admin access is constrained to the user's own ServiceUnit.
- Route decorators remain useful, but they do not replace deeper scope checks.
"""

from __future__ import annotations

from flask import abort
from flask_login import current_user


def ensure_committee_scope_or_403(service_unit_id: int) -> None:
    """
    Enforce committee-management scope.

    RULES
    -----
    - admin: may manage committees for any service unit
    - non-admin:
      * must belong to the same service unit
      * must pass current_user.can_manage()

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit primary key for the committee operation.

    RAISES
    ------
    werkzeug.exceptions.Forbidden
        When the current user is outside the allowed scope.
    """
    if current_user.is_admin:
        return

    if not current_user.service_unit_id or current_user.service_unit_id != service_unit_id:
        abort(403)

    if not current_user.can_manage():
        abort(403)


def ensure_settings_structure_scope_or_403(service_unit_id: int) -> None:
    """
    Enforce service-unit structure access for the legacy compatibility redirect.

    RULES
    -----
    - admin: may access any service unit
    - manager/deputy:
      * only their own service unit
      * current_user.can_manage() must be True

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit primary key for the redirect target.

    RAISES
    ------
    werkzeug.exceptions.Forbidden
        When the current user is outside the allowed scope.
    """
    if current_user.is_admin:
        return

    if not current_user.service_unit_id or current_user.service_unit_id != service_unit_id:
        abort(403)

    if not current_user.can_manage():
        abort(403)


__all__ = [
    "ensure_committee_scope_or_403",
    "ensure_settings_structure_scope_or_403",
]


```

FILE: .\app\seed\__init__.py
```python
"""
app/seed/__init__.py

Public seed facade for the Invoice / Procurement Management System.

PURPOSE
-------
This package provides the stable public import surface for application
reference-data seeding.

PACKAGE STRUCTURE
-----------------
- app.seed.defaults
    Canonical static default values

- app.seed.reference_data
    Idempotent database seeding logic

- app.seed
    Backwards-compatible public facade and CLI helper

SCOPE
-----
This package seeds only reference data such as:
- dropdown categories / values
- income tax rules
- withholding profiles
"""

from __future__ import annotations

import click

from .defaults import (
    DEFAULT_INCOME_TAX_RULES,
    DEFAULT_OPTION_CATEGORIES,
    DEFAULT_WITHHOLDING_PROFILES,
)
from .reference_data import (
    get_or_create_option_category,
    seed_income_tax_rules,
    seed_option_categories_and_values,
    seed_reference_data,
    seed_withholding_profiles,
)


def seed_default_options() -> None:
    """
    Backwards-compatible public entrypoint for reference-data seeding.
    """
    seed_reference_data()


@click.command("seed-options")
def seed_options_command() -> None:
    """
    CLI command for seeding default option categories and reference-data.
    """
    seed_default_options()
    click.echo("Seeding completed.")


__all__ = [
    "DEFAULT_OPTION_CATEGORIES",
    "DEFAULT_INCOME_TAX_RULES",
    "DEFAULT_WITHHOLDING_PROFILES",
    "get_or_create_option_category",
    "seed_option_categories_and_values",
    "seed_income_tax_rules",
    "seed_withholding_profiles",
    "seed_reference_data",
    "seed_default_options",
    "seed_options_command",
]


```

FILE: .\app\seed\defaults.py
```python
"""
app/seed_defaults.py

Canonical default reference-data values for initial application seeding.

PURPOSE
-------
This module contains only the static default values used by the seed process.

WHY THIS FILE EXISTS
--------------------
Previously, `app/seed.py` mixed:
- constant default data
- database seeding logic
- execution entrypoints

Those are related, but they are not the same responsibility.

This module isolates the canonical defaults so that:
- seed data is easy to inspect and review
- business defaults can be updated without scanning DB logic
- seeding behavior can evolve independently from the data itself

IMPORTANT
---------
This file contains no database access and no Flask-specific behavior.
It is intentionally pure data.

SEED DATA INCLUDED
------------------
- Generic dropdown categories / values
- Income tax rule defaults
- Withholding profile defaults

SEED DATA EXCLUDED
------------------
This file intentionally does NOT define defaults for:
- Personnel
- Suppliers
- Users

Those are first-class business entities, not generic reference-data rows.
"""

from __future__ import annotations

from decimal import Decimal

# -------------------------------------------------------------------
# Generic option categories / values
# -------------------------------------------------------------------
# Tuple format:
#   (category_key, category_label, [option_value_1, option_value_2, ...])
DEFAULT_OPTION_CATEGORIES = [
    (
        "KATASTASH",
        "Κατάσταση",
        [
            "-",
            "ΣΕ ΕΞΕΛΙΞΗ",
            "ΟΛΟΚΛΗΡΩΘΗΚΕ",
            "ΑΚΥΡΩΘΗΚΕ",
        ],
    ),
    (
        "STADIO",
        "Στάδιο",
        [
            "-",
            "Δέσμευση",
            "Πρόσκληση",
            "Προέγκριση",
            "Έγκριση",
            "Απόφαση Ανάθεσης",
            "Σύμβαση",
            "Τιμολόγιο",
            "Αποστολή Δαπάνης",
        ],
    ),
    (
        "KATANOMH",
        "Κατανομή",
        [
            "-",
            "Παγία",
            "Κατ' εξαίρεση",
            "Γραφική Ύλη",
            "Μικρογραφικά",
            "Ειδικές Διαχειρίσεις",
            "Καθαριότητα",
            "Λοιπές Προεγκρίσεις",
        ],
    ),
    (
        "TRIMHNIAIA",
        "Τριμηνιαία",
        [
            "-",
            "Α' ΤΡΙΜΗΝΙΑΙΑ",
            "Β' ΤΡΙΜΗΝΙΑΙΑ",
            "Γ' ΤΡΙΜΗΝΙΑΙΑ",
            "Δ' ΤΡΙΜΗΝΙΑΙΑ",
        ],
    ),
    (
        "FPA",
        "ΦΠΑ",
        ["0", "6", "13", "24"],
    ),

    # ---------------------------------------------------------------
    # Legacy compatibility categories
    # ---------------------------------------------------------------
    # These are intentionally kept because older screens / flows may still
    # expect these categories to exist even if richer models now back the
    # real domain behavior.
    (
        "KRATHSEIS",
        "Κρατήσεις (Λίστα)",
        ["-"],
    ),
    (
        "EPITROPES",
        "Επιτροπές (Λίστα)",
        ["-"],
    ),
]


# -------------------------------------------------------------------
# Income tax rules
# -------------------------------------------------------------------
# Tuple format:
#   (description, rate_percent, threshold_amount)
DEFAULT_INCOME_TAX_RULES = [
    ("ΥΠΗΡΕΣΙΕΣ ΧΩΡΙΣ ΦΕ", Decimal("0.00"), Decimal("150.00")),
    ("ΥΠΗΡΕΣΙΕΣ ΜΕ ΦΕ", Decimal("8.00"), Decimal("150.00")),
    ("ΠΡΟΜΗΘΕΙΑ ΥΛΙΚΩΝ ΧΩΡΙΣ ΦΕ", Decimal("0.00"), Decimal("150.00")),
    ("ΠΡΟΜΗΘΕΙΑ ΥΛΙΚΩΝ ΜΕ ΦΕ", Decimal("4.00"), Decimal("150.00")),
]


# -------------------------------------------------------------------
# Withholding profiles
# -------------------------------------------------------------------
# Tuple format:
#   (description, mt_eloa_percent, eadhsy_percent, withholding1_percent, withholding2_percent)
DEFAULT_WITHHOLDING_PROFILES = [
    ("ΔΑΠΑΝΕΣ <= 1000 (ΙΔΙΩΤΗΣ)", Decimal("6.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
    ("ΔΑΠΑΝΕΣ > 1000 (ΙΔΙΩΤΗΣ)", Decimal("6.00"), Decimal("0.10"), Decimal("0.00"), Decimal("0.00")),
    ("ΔΑΠΑΝΕΣ <= 1000 (ΣΤ. ΠΡΑΤΗΡΙΟ)", Decimal("6.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
    ("ΔΑΠΑΝΕΣ > 1000 (ΣΤ. ΠΡΑΤΗΡΙΟ)", Decimal("6.00"), Decimal("0.10"), Decimal("0.00"), Decimal("0.00")),
    ("ΔΑΠΑΝΕΣ <= 1000 (ΔΗΜΟΣΙΟΣ ΦΟΡΕΑΣ)", Decimal("4.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
    ("ΔΑΠΑΝΕΣ > 1000 (ΔΗΜΟΣΙΟΣ ΦΟΡΕΑΣ)", Decimal("4.00"), Decimal("0.10"), Decimal("0.00"), Decimal("0.00")),
]


```

FILE: .\app\seed\reference_data.py
```python
"""
app/seed_reference_data.py

Idempotent reference-data seeding for the Invoice / Procurement Management
System.

PURPOSE
-------
This module contains the database logic that ensures core reference-data rows
exist and remain aligned with the canonical defaults.

WHY THIS FILE EXISTS
--------------------
Previously, `app/seed.py` mixed:
- constant default values
- database upsert-like seeding logic
- execution entrypoints

This module isolates the database-facing seeding behavior so that:
- idempotent seed logic is easier to test and review
- constant defaults stay separate from persistence logic
- the public seed facade stays small and stable

SEEDING PRINCIPLES
------------------
1. Safe to run multiple times
2. Existing canonical rows are updated when needed
3. Missing canonical rows are created
4. Data is flushed as needed, then committed once at the orchestration layer

IMPORTANT
---------
This module does NOT commit inside low-level helper functions.
The orchestration function decides the transaction boundary.

SEEDED DOMAINS
--------------
- Generic option categories / values
- Income tax rules
- Withholding profiles

EXCLUDED DOMAINS
----------------
This module intentionally does NOT seed:
- Personnel
- Suppliers
- Users

Those are first-class business entities rather than simple reference data.
"""

from __future__ import annotations

from ..extensions import db
from ..models import (
    IncomeTaxRule,
    OptionCategory,
    OptionValue,
    WithholdingProfile,
)
from .defaults import (
    DEFAULT_INCOME_TAX_RULES,
    DEFAULT_OPTION_CATEGORIES,
    DEFAULT_WITHHOLDING_PROFILES,
)


def get_or_create_option_category(key: str, label: str) -> OptionCategory:
    """
    Ensure an OptionCategory exists and return it.

    BEHAVIOR
    --------
    - Finds by canonical key
    - Updates the label if the row already exists
    - Creates the row if missing

    PARAMETERS
    ----------
    key:
        Canonical category key.
    label:
        Human-readable category label.

    RETURNS
    -------
    OptionCategory
        Existing or newly created category row.
    """
    category = OptionCategory.query.filter_by(key=key).first()

    if category:
        category.label = label
        return category

    category = OptionCategory(key=key, label=label)
    db.session.add(category)
    db.session.flush()
    return category


def seed_option_categories_and_values() -> None:
    """
    Seed canonical OptionCategory and OptionValue rows.

    IDEMPOTENT BEHAVIOR
    -------------------
    - Matches categories by key
    - Updates category labels if they changed
    - Creates missing categories
    - Creates missing values
    - Updates sort_order of canonical values
    - Reactivates canonical values if they already exist but were inactive

    IMPORTANT
    ---------
    This function does not remove non-canonical extra values.
    That is intentional, because administrators may have introduced local
    business-specific values that should not be deleted automatically.
    """
    for category_key, category_label, values in DEFAULT_OPTION_CATEGORIES:
        category = get_or_create_option_category(category_key, category_label)

        for sort_order, value_text in enumerate(values, start=1):
            existing = OptionValue.query.filter_by(
                category_id=category.id,
                value=value_text,
            ).first()

            if existing:
                existing.sort_order = sort_order
                if existing.is_active is None or existing.is_active is False:
                    existing.is_active = True
                continue

            db.session.add(
                OptionValue(
                    category_id=category.id,
                    value=value_text,
                    sort_order=sort_order,
                    is_active=True,
                )
            )

    db.session.flush()


def seed_income_tax_rules() -> None:
    """
    Seed canonical IncomeTaxRule defaults.

    IDEMPOTENT BEHAVIOR
    -------------------
    - Matches existing rows by description
    - Updates rate/threshold if the row already exists
    - Creates missing rows
    """
    for description, rate_percent, threshold_amount in DEFAULT_INCOME_TAX_RULES:
        existing = IncomeTaxRule.query.filter_by(description=description).first()

        if existing:
            existing.rate_percent = rate_percent
            existing.threshold_amount = threshold_amount

            if existing.is_active is None:
                existing.is_active = True

            continue

        db.session.add(
            IncomeTaxRule(
                description=description,
                rate_percent=rate_percent,
                threshold_amount=threshold_amount,
                is_active=True,
            )
        )

    db.session.flush()


def seed_withholding_profiles() -> None:
    """
    Seed canonical WithholdingProfile defaults.

    IDEMPOTENT BEHAVIOR
    -------------------
    - Matches existing rows by description
    - Updates component values if the row already exists
    - Creates missing rows
    """
    for description, mt_eloa, eadhsy, withholding1, withholding2 in DEFAULT_WITHHOLDING_PROFILES:
        existing = WithholdingProfile.query.filter_by(description=description).first()

        if existing:
            existing.mt_eloa_percent = mt_eloa
            existing.eadhsy_percent = eadhsy
            existing.withholding1_percent = withholding1
            existing.withholding2_percent = withholding2

            if existing.is_active is None:
                existing.is_active = True

            continue

        db.session.add(
            WithholdingProfile(
                description=description,
                mt_eloa_percent=mt_eloa,
                eadhsy_percent=eadhsy,
                withholding1_percent=withholding1,
                withholding2_percent=withholding2,
                is_active=True,
            )
        )

    db.session.flush()


def seed_reference_data() -> None:
    """
    Seed all default reference data.

    EXECUTION ORDER
    ---------------
    1. Option categories / values
    2. Income tax rules
    3. Withholding profiles

    TRANSACTION
    -----------
    A single commit at the end keeps the seed operation reasonably atomic for
    normal application use.

    IMPORTANT
    ---------
    This function owns the commit boundary for the overall reference-data seed.
    """
    seed_option_categories_and_values()
    seed_income_tax_rules()
    seed_withholding_profiles()
    db.session.commit()


```

FILE: .\app\seed\seed.py
```python
"""
app/seed.py

Public seed facade for the Invoice / Procurement Management System.

PURPOSE
-------
This module remains the stable import surface for application reference-data
seeding.

After refactoring, responsibilities are split as follows:

- `app.seed_defaults`
    Canonical static default values

- `app.seed_reference_data`
    Idempotent database seeding logic

- `app.seed`
    Backwards-compatible public facade and CLI command

WHY THIS STRUCTURE IS BETTER
----------------------------
Previously, one file mixed:
- static seed defaults
- database seeding helpers
- orchestration / commit logic
- CLI entrypoints

Those concerns are related, but keeping them together makes the file harder to
scan and maintain.

Now:
- seed data is defined in one place
- seeding behavior lives in one place
- old imports continue to work

SCOPE
-----
This module seeds only reference data such as:
- dropdown categories / values
- income tax rules
- withholding profiles

It intentionally does NOT seed first-class business entities like:
- Personnel
- Suppliers
- Users
"""

from __future__ import annotations

import click

from .defaults import (
    DEFAULT_INCOME_TAX_RULES,
    DEFAULT_OPTION_CATEGORIES,
    DEFAULT_WITHHOLDING_PROFILES,
)
from .reference_data import (
    get_or_create_option_category,
    seed_income_tax_rules,
    seed_option_categories_and_values,
    seed_reference_data,
    seed_withholding_profiles,
)

# -------------------------------------------------------------------
# Backwards-compatible public name
# -------------------------------------------------------------------
# The rest of the application currently imports and calls:
#
#     from app.seed import seed_default_options
#
# so we preserve that stable name.
def seed_default_options() -> None:
    """
    Backwards-compatible public entrypoint for reference-data seeding.

    Delegates to `seed_reference_data()`.

    IMPORTANT
    ---------
    This function preserves the old import and call style used by the
    application bootstrap / CLI wiring.
    """
    seed_reference_data()


@click.command("seed-options")
def seed_options_command() -> None:
    """
    CLI command for seeding default option categories and reference-data.
    """
    seed_default_options()
    click.echo("Seeding completed.")


__all__ = [
    # Seed defaults
    "DEFAULT_OPTION_CATEGORIES",
    "DEFAULT_INCOME_TAX_RULES",
    "DEFAULT_WITHHOLDING_PROFILES",

    # Low-level helpers
    "get_or_create_option_category",
    "seed_option_categories_and_values",
    "seed_income_tax_rules",
    "seed_withholding_profiles",

    # Public orchestration
    "seed_reference_data",
    "seed_default_options",
    "seed_options_command",
]


```

FILE: .\app\services\__init__.py
```python
"""
app/services/__init__.py

Canonical services package.

PURPOSE
-------
This package groups application services by domain while preserving the
existing project policy of function-first orchestration.

PACKAGE GROUPS
--------------
- app.services.admin
- app.services.organization
- app.services.procurement
- app.services.settings
- app.services.shared

IMPORTANT
---------
This file intentionally exports no large wildcard public API.
Callers should import from the concrete canonical module they need.
"""

from __future__ import annotations

```

FILE: .\app\services\admin\__init__.py
```python
"""
app/services/admin/__init__.py

Canonical admin service package.

This package contains non-HTTP orchestration used by the admin blueprint.
"""

from __future__ import annotations

from .organization_setup import *  # noqa: F401,F403
from .personnel import *  # noqa: F401,F403

```

FILE: .\app\services\admin\organization_setup.py
```python
"""
app/services/admin/organization_setup.py

Focused page/use-case services for the consolidated organization setup flow.

PURPOSE
-------
This module extracts non-HTTP orchestration from:

    /admin/organization-setup

It moves out:
- page-context assembly
- action dispatch
- structural validation
- ORM mutation orchestration
- audit logging / commit

IMPORTANT CHANGE
----------------
Organization membership is assignment-based.

A person may belong to multiple departments/directories inside the same
ServiceUnit through `PersonnelDepartmentAssignment`.

That means:
- Personnel edit page no longer owns department/directory assignment.
- All organizational placement is centrally managed from Organization Setup.
- Procurement handler dropdown uses these assignment rows directly.

BUSINESS RULE FOR PROCUREMENT HANDLERS
--------------------------------------
Procurement handler selection is assignment-based and must preserve the exact:
- person
- directory
- department

used for a specific procurement.

Therefore, when a department role holder is assigned manually from the
organization setup screen:
- head_personnel_id
- assistant_personnel_id

the corresponding PersonnelDepartmentAssignment should also exist.

Otherwise the person is visible as a department role holder in organization
setup, but does not appear in the procurement handler dropdown, because
procurement handlers are loaded from assignment rows.

This module therefore auto-creates missing assignment rows for:
- department head
- department assistant

when department roles are updated manually.

ARCHITECTURAL INTENT
--------------------
This module is intentionally explicit and function-first.

BOUNDARY
--------
This module MAY:
- query organization entities
- validate submitted values
- mutate organization entities
- audit and commit
- return structured results for routes

This module MUST NOT:
- define routes
- call render_template(...)
- call redirect(...)
- call flash(...)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from openpyxl import load_workbook

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import (
    Department,
    Directory,
    Personnel,
    PersonnelDepartmentAssignment,
    ServiceUnit,
)
from ..organization import (
    active_personnel_for_service_unit,
    active_personnel_ids_for_service_unit,
    service_units_for_dropdown,
)
from ..shared.operation_results import FlashMessage
from ..shared.parsing import parse_optional_int


@dataclass(frozen=True)
class OrganizationSetupOperationResult:
    """
    Result object for organization-setup POST actions.
    """

    ok: bool
    flashes: tuple[FlashMessage, ...]
    redirect_service_unit_id: int | None = None


def build_organization_setup_page_context(
    request_args: Mapping[str, Any],
    *,
    is_admin: bool,
    current_service_unit_id: int | None,
) -> dict[str, Any]:
    """
    Build template context for the consolidated organization setup page.

    RETURNS
    -------
    dict[str, Any]
        Includes:
        - service unit scope
        - directories
        - departments
        - active personnel list
        - department membership rows grouped per department
    """
    if is_admin:
        service_unit_id = parse_optional_int(request_args.get("service_unit_id"))
    else:
        service_unit_id = current_service_unit_id

    service_units = service_units_for_dropdown()

    unit = ServiceUnit.query.get(service_unit_id) if service_unit_id else None
    directories: list[Directory] = []
    departments: list[Department] = []
    personnel_list: list[Personnel] = []
    department_memberships: dict[int, list[PersonnelDepartmentAssignment]] = {}

    if unit:
        _ensure_target_service_unit_scope(
            unit.id,
            is_admin=is_admin,
            current_service_unit_id=current_service_unit_id,
        )

        directories = (
            Directory.query.filter_by(service_unit_id=unit.id)
            .order_by(Directory.name.asc())
            .all()
        )
        departments = (
            Department.query.filter_by(service_unit_id=unit.id)
            .order_by(Department.directory_id.asc(), Department.name.asc())
            .all()
        )
        personnel_list = active_personnel_for_service_unit(unit.id)

        assignments = (
            PersonnelDepartmentAssignment.query.filter_by(service_unit_id=unit.id)
            .order_by(
                PersonnelDepartmentAssignment.department_id.asc(),
                PersonnelDepartmentAssignment.is_primary.desc(),
                PersonnelDepartmentAssignment.id.asc(),
            )
            .all()
        )

        for assignment in assignments:
            department_memberships.setdefault(assignment.department_id, []).append(assignment)

    return {
        "service_units": service_units,
        "scope_service_unit_id": (unit.id if unit else None),
        "unit": unit,
        "directories": directories,
        "departments": departments,
        "personnel_list": personnel_list,
        "department_memberships": department_memberships,
        "is_admin": is_admin,
    }


def execute_organization_setup_action(
    form_data: Mapping[str, Any],
    *,
    files: Mapping[str, Any] | None = None,
    is_admin: bool,
    current_service_unit_id: int | None,
) -> OrganizationSetupOperationResult:
    """
    Dispatch and execute one organization-setup action.

    SUPPORTED ACTIONS
    -----------------
    - import
    - create/update/delete directory
    - create/update/delete department
    - update directory director
    - update department roles
    - add_department_member
    - remove_department_member
    """
    action = (form_data.get("action") or "").strip()

    target_service_unit_id = _resolve_target_service_unit_id(
        form_data,
        is_admin=is_admin,
        current_service_unit_id=current_service_unit_id,
    )
    if target_service_unit_id is None:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Η υπηρεσία είναι υποχρεωτική.", "danger"),),
            redirect_service_unit_id=None,
        )

    _ensure_target_service_unit_scope(
        target_service_unit_id,
        is_admin=is_admin,
        current_service_unit_id=current_service_unit_id,
    )

    unit = ServiceUnit.query.get_or_404(target_service_unit_id)
    allowed_personnel_ids = active_personnel_ids_for_service_unit(unit.id)

    if action == "import":
        return _execute_import_organization_structure(
            unit,
            (files or {}).get("file"),
            allowed_personnel_ids=allowed_personnel_ids,
        )

    if action == "create_directory":
        return _execute_create_directory(unit, form_data)

    if action == "update_directory":
        return _execute_update_directory(unit, form_data)

    if action == "delete_directory":
        return _execute_delete_directory(unit, form_data)

    if action == "create_department":
        return _execute_create_department(unit, form_data)

    if action == "update_department":
        return _execute_update_department(unit, form_data)

    if action == "delete_department":
        return _execute_delete_department(unit, form_data)

    if action == "update_directory_director":
        return _execute_update_directory_director(
            unit,
            form_data,
            allowed_personnel_ids=allowed_personnel_ids,
        )

    if action == "update_department_roles":
        return _execute_update_department_roles(
            unit,
            form_data,
            allowed_personnel_ids=allowed_personnel_ids,
        )

    if action == "add_department_member":
        return _execute_add_department_member(
            unit,
            form_data,
            allowed_personnel_ids=allowed_personnel_ids,
        )

    if action == "remove_department_member":
        return _execute_remove_department_member(unit, form_data)

    return OrganizationSetupOperationResult(
        ok=False,
        flashes=(FlashMessage("Μη έγκυρη ενέργεια.", "danger"),),
        redirect_service_unit_id=unit.id,
    )


def _resolve_target_service_unit_id(
    form_data: Mapping[str, Any],
    *,
    is_admin: bool,
    current_service_unit_id: int | None,
) -> int | None:
    if is_admin:
        return parse_optional_int(form_data.get("service_unit_id"))
    return current_service_unit_id


def _ensure_target_service_unit_scope(
    service_unit_id: int,
    *,
    is_admin: bool,
    current_service_unit_id: int | None,
) -> None:
    if is_admin:
        return

    if not current_service_unit_id or service_unit_id != current_service_unit_id:
        from flask import abort
        abort(403)


def _validate_service_unit_personnel_or_none(
    raw_personnel_id: Any,
    *,
    allowed_personnel_ids: set[int],
) -> tuple[int | None, FlashMessage | None]:
    personnel_id = parse_optional_int(raw_personnel_id)
    if personnel_id is None:
        return None, None

    if personnel_id not in allowed_personnel_ids:
        return None, FlashMessage("Μη έγκυρη επιλογή προσωπικού για την υπηρεσία.", "danger")

    return personnel_id, None


def _ensure_department_assignment(
    *,
    unit: ServiceUnit,
    department: Department,
    personnel_id: int | None,
    is_primary: bool,
) -> bool:
    """
    Ensure that a PersonnelDepartmentAssignment exists for the given person and
    department.

    PARAMETERS
    ----------
    unit:
        The scoped ServiceUnit.
    department:
        The target Department.
    personnel_id:
        Personnel id to ensure membership for.
    is_primary:
        Whether the created/updated membership should be primary.

    RETURNS
    -------
    bool
        True when a new assignment row was created.
        False when no new row was needed.

    WHY THIS HELPER EXISTS
    ----------------------
    Procurement handler selection is assignment-based. If a user is assigned as
    Department Head or Assistant but no membership row exists, they will not
    appear as a selectable handler for procurements.

    This helper keeps manual role assignment consistent with the assignment-
    based organizational model.
    """
    if personnel_id is None:
        return False

    existing_assignment = PersonnelDepartmentAssignment.query.filter_by(
        personnel_id=personnel_id,
        department_id=department.id,
    ).first()

    if existing_assignment is not None:
        existing_assignment.service_unit_id = unit.id
        existing_assignment.directory_id = department.directory_id

        if is_primary and not existing_assignment.is_primary:
            existing_assignment.is_primary = True

        return False

    assignment = PersonnelDepartmentAssignment(
        personnel_id=personnel_id,
        service_unit_id=unit.id,
        directory_id=department.directory_id,
        department_id=department.id,
        is_primary=is_primary,
    )
    db.session.add(assignment)
    db.session.flush()
    log_action(entity=assignment, action="CREATE", before=None, after=serialize_model(assignment))
    return True


def _execute_create_directory(
    unit: ServiceUnit,
    form_data: Mapping[str, Any],
) -> OrganizationSetupOperationResult:
    name = (form_data.get("directory_name") or "").strip()

    if not name:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Η ονομασία Διεύθυνσης είναι υποχρεωτική.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    exists = Directory.query.filter_by(service_unit_id=unit.id, name=name).first()
    if exists:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Υπάρχει ήδη Διεύθυνση με αυτή την ονομασία στην Υπηρεσία.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    directory = Directory(
        service_unit_id=unit.id,
        name=name,
        is_active=True,
        director_personnel_id=None,
    )
    db.session.add(directory)
    db.session.flush()
    log_action(entity=directory, action="CREATE", before=None, after=serialize_model(directory))
    db.session.commit()

    return OrganizationSetupOperationResult(
        ok=True,
        flashes=(FlashMessage("Η Διεύθυνση δημιουργήθηκε.", "success"),),
        redirect_service_unit_id=unit.id,
    )


def _execute_update_directory(
    unit: ServiceUnit,
    form_data: Mapping[str, Any],
) -> OrganizationSetupOperationResult:
    directory_id = parse_optional_int(form_data.get("directory_id"))
    if directory_id is None:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Διεύθυνση.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    directory = Directory.query.get_or_404(directory_id)
    if directory.service_unit_id != unit.id:
        from flask import abort
        abort(403)

    name = (form_data.get("directory_name") or "").strip()
    is_active = bool(form_data.get("is_active"))

    if not name:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Η ονομασία Διεύθυνσης είναι υποχρεωτική.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    exists = Directory.query.filter(
        Directory.service_unit_id == unit.id,
        Directory.name == name,
        Directory.id != directory.id,
    ).first()
    if exists:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Υπάρχει ήδη άλλη Διεύθυνση με αυτή την ονομασία.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    before = serialize_model(directory)
    directory.name = name
    directory.is_active = is_active

    db.session.flush()
    log_action(entity=directory, action="UPDATE", before=before, after=serialize_model(directory))
    db.session.commit()

    return OrganizationSetupOperationResult(
        ok=True,
        flashes=(FlashMessage("Η Διεύθυνση ενημερώθηκε.", "success"),),
        redirect_service_unit_id=unit.id,
    )


def _execute_delete_directory(
    unit: ServiceUnit,
    form_data: Mapping[str, Any],
) -> OrganizationSetupOperationResult:
    directory_id = parse_optional_int(form_data.get("directory_id"))
    if directory_id is None:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Διεύθυνση.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    directory = Directory.query.get_or_404(directory_id)
    if directory.service_unit_id != unit.id:
        from flask import abort
        abort(403)

    before = serialize_model(directory)

    Department.query.filter_by(directory_id=directory.id).update(
        {"head_personnel_id": None, "assistant_personnel_id": None},
        synchronize_session=False,
    )

    PersonnelDepartmentAssignment.query.filter_by(directory_id=directory.id).delete(
        synchronize_session=False
    )

    departments_to_delete = Department.query.filter_by(directory_id=directory.id).all()
    for department in departments_to_delete:
        department_before = serialize_model(department)
        db.session.delete(department)
        db.session.flush()
        log_action(entity=department, action="DELETE", before=department_before, after=None)

    db.session.delete(directory)
    db.session.flush()
    log_action(entity=directory, action="DELETE", before=before, after=None)
    db.session.commit()

    return OrganizationSetupOperationResult(
        ok=True,
        flashes=(FlashMessage("Η Διεύθυνση διαγράφηκε.", "success"),),
        redirect_service_unit_id=unit.id,
    )


def _execute_create_department(
    unit: ServiceUnit,
    form_data: Mapping[str, Any],
) -> OrganizationSetupOperationResult:
    directory_id = parse_optional_int(form_data.get("directory_id"))
    name = (form_data.get("department_name") or "").strip()

    if not directory_id:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Η Διεύθυνση είναι υποχρεωτική για δημιουργία Τμήματος.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    if not name:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Η ονομασία Τμήματος είναι υποχρεωτική.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    directory = Directory.query.get(directory_id)
    if not directory or directory.service_unit_id != unit.id:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Διεύθυνση για την Υπηρεσία.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    exists = Department.query.filter_by(directory_id=directory.id, name=name).first()
    if exists:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Υπάρχει ήδη Τμήμα με αυτή την ονομασία στη συγκεκριμένη Διεύθυνση.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    department = Department(
        service_unit_id=unit.id,
        directory_id=directory.id,
        name=name,
        is_active=True,
        head_personnel_id=None,
        assistant_personnel_id=None,
    )
    db.session.add(department)
    db.session.flush()
    log_action(entity=department, action="CREATE", before=None, after=serialize_model(department))
    db.session.commit()

    return OrganizationSetupOperationResult(
        ok=True,
        flashes=(FlashMessage("Το Τμήμα δημιουργήθηκε.", "success"),),
        redirect_service_unit_id=unit.id,
    )


def _execute_update_department(
    unit: ServiceUnit,
    form_data: Mapping[str, Any],
) -> OrganizationSetupOperationResult:
    department_id = parse_optional_int(form_data.get("department_id"))
    new_directory_id = parse_optional_int(form_data.get("directory_id"))
    name = (form_data.get("department_name") or "").strip()

    if department_id is None:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο Τμήμα.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    if new_directory_id is None:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Η Διεύθυνση είναι υποχρεωτική.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    if not name:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Η ονομασία Τμήματος είναι υποχρεωτική.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    department = Department.query.get_or_404(department_id)
    if department.service_unit_id != unit.id:
        from flask import abort
        abort(403)

    new_directory = Directory.query.get_or_404(new_directory_id)
    if new_directory.service_unit_id != unit.id:
        from flask import abort
        abort(403)

    exists = Department.query.filter(
        Department.directory_id == new_directory.id,
        Department.name == name,
        Department.id != department.id,
    ).first()
    if exists:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Υπάρχει ήδη άλλο Τμήμα με αυτή την ονομασία στη συγκεκριμένη Διεύθυνση.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    before = serialize_model(department)
    department.directory_id = new_directory.id
    department.name = name
    department.is_active = bool(form_data.get("is_active"))

    PersonnelDepartmentAssignment.query.filter_by(department_id=department.id).update(
        {"directory_id": new_directory.id},
        synchronize_session=False,
    )

    db.session.flush()
    log_action(entity=department, action="UPDATE", before=before, after=serialize_model(department))
    db.session.commit()

    return OrganizationSetupOperationResult(
        ok=True,
        flashes=(FlashMessage("Το Τμήμα ενημερώθηκε.", "success"),),
        redirect_service_unit_id=unit.id,
    )


def _execute_delete_department(
    unit: ServiceUnit,
    form_data: Mapping[str, Any],
) -> OrganizationSetupOperationResult:
    department_id = parse_optional_int(form_data.get("department_id"))
    if department_id is None:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο Τμήμα.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    department = Department.query.get_or_404(department_id)
    if department.service_unit_id != unit.id:
        from flask import abort
        abort(403)

    before = serialize_model(department)

    PersonnelDepartmentAssignment.query.filter_by(department_id=department.id).delete(
        synchronize_session=False
    )

    department.head_personnel_id = None
    department.assistant_personnel_id = None

    db.session.flush()
    db.session.delete(department)
    db.session.flush()
    log_action(entity=department, action="DELETE", before=before, after=None)
    db.session.commit()

    return OrganizationSetupOperationResult(
        ok=True,
        flashes=(FlashMessage("Το Τμήμα διαγράφηκε.", "success"),),
        redirect_service_unit_id=unit.id,
    )


def _execute_update_directory_director(
    unit: ServiceUnit,
    form_data: Mapping[str, Any],
    *,
    allowed_personnel_ids: set[int],
) -> OrganizationSetupOperationResult:
    directory_id = parse_optional_int(form_data.get("directory_id"))
    if directory_id is None:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Διεύθυνση.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    directory = Directory.query.get_or_404(directory_id)
    if directory.service_unit_id != unit.id:
        from flask import abort
        abort(403)

    director_personnel_id, validation_flash = _validate_service_unit_personnel_or_none(
        form_data.get("director_personnel_id"),
        allowed_personnel_ids=allowed_personnel_ids,
    )

    before = serialize_model(directory)
    directory.director_personnel_id = director_personnel_id

    db.session.flush()
    log_action(entity=directory, action="UPDATE", before=before, after=serialize_model(directory))
    db.session.commit()

    flashes: list[FlashMessage] = []
    if validation_flash is not None:
        flashes.append(validation_flash)
    flashes.append(FlashMessage("Ο Διευθυντής Διεύθυνσης ενημερώθηκε.", "success"))

    return OrganizationSetupOperationResult(
        ok=True,
        flashes=tuple(flashes),
        redirect_service_unit_id=unit.id,
    )


def _execute_update_department_roles(
    unit: ServiceUnit,
    form_data: Mapping[str, Any],
    *,
    allowed_personnel_ids: set[int],
) -> OrganizationSetupOperationResult:
    """
    Update department role holders and ensure assignment-based membership exists.

    IMPORTANT
    ---------
    Procurement handler selection is built from PersonnelDepartmentAssignment.
    Therefore, assigning a Department Head / Assistant manually must also ensure
    the corresponding membership row exists, otherwise the role holder will not
    appear as a selectable procurement handler.
    """
    department_id = parse_optional_int(form_data.get("department_id"))
    if department_id is None:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο Τμήμα.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    head_personnel_id, head_flash = _validate_service_unit_personnel_or_none(
        form_data.get("head_personnel_id"),
        allowed_personnel_ids=allowed_personnel_ids,
    )
    assistant_personnel_id, assistant_flash = _validate_service_unit_personnel_or_none(
        form_data.get("assistant_personnel_id"),
        allowed_personnel_ids=allowed_personnel_ids,
    )

    if (
        head_personnel_id is not None
        and assistant_personnel_id is not None
        and head_personnel_id == assistant_personnel_id
    ):
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Ο ίδιος/η ίδια δεν μπορεί να είναι και Προϊστάμενος και Βοηθός.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    department = Department.query.get_or_404(department_id)
    if department.service_unit_id != unit.id:
        from flask import abort
        abort(403)

    before = serialize_model(department)
    department.head_personnel_id = head_personnel_id
    department.assistant_personnel_id = assistant_personnel_id

    created_memberships = 0

    if _ensure_department_assignment(
        unit=unit,
        department=department,
        personnel_id=head_personnel_id,
        is_primary=True,
    ):
        created_memberships += 1

    if _ensure_department_assignment(
        unit=unit,
        department=department,
        personnel_id=assistant_personnel_id,
        is_primary=False,
    ):
        created_memberships += 1

    db.session.flush()
    log_action(entity=department, action="UPDATE", before=before, after=serialize_model(department))
    db.session.commit()

    flashes: list[FlashMessage] = []
    if head_flash is not None:
        flashes.append(head_flash)
    if assistant_flash is not None:
        flashes.append(assistant_flash)

    if created_memberships:
        flashes.append(
            FlashMessage(
                f"Δημιουργήθηκαν αυτόματα {created_memberships} αναθέσεις μέλους για συμβατότητα με τον Χειριστή Προμήθειας.",
                "info",
            )
        )

    flashes.append(FlashMessage("Οι ρόλοι Τμήματος ενημερώθηκαν.", "success"))

    return OrganizationSetupOperationResult(
        ok=True,
        flashes=tuple(flashes),
        redirect_service_unit_id=unit.id,
    )


def _execute_add_department_member(
    unit: ServiceUnit,
    form_data: Mapping[str, Any],
    *,
    allowed_personnel_ids: set[int],
) -> OrganizationSetupOperationResult:
    """
    Add one personnel membership assignment to a department.

    VALIDATION
    ----------
    - Person must belong to same service unit scope.
    - Department must belong to same service unit.
    - Duplicate membership is prevented by validation before insert.
    """
    department_id = parse_optional_int(form_data.get("department_id"))
    personnel_id = parse_optional_int(form_data.get("personnel_id"))

    if department_id is None:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο Τμήμα.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    if personnel_id is None:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Το προσωπικό είναι υποχρεωτικό.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    if personnel_id not in allowed_personnel_ids:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη επιλογή προσωπικού για την υπηρεσία.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    department = Department.query.get_or_404(department_id)
    if department.service_unit_id != unit.id:
        from flask import abort
        abort(403)

    exists = PersonnelDepartmentAssignment.query.filter_by(
        personnel_id=personnel_id,
        department_id=department.id,
    ).first()
    if exists:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Το προσωπικό είναι ήδη καταχωρημένο στο συγκεκριμένο Τμήμα.", "warning"),),
            redirect_service_unit_id=unit.id,
        )

    assignment = PersonnelDepartmentAssignment(
        personnel_id=personnel_id,
        service_unit_id=unit.id,
        directory_id=department.directory_id,
        department_id=department.id,
        is_primary=False,
    )

    db.session.add(assignment)
    db.session.flush()
    log_action(entity=assignment, action="CREATE", before=None, after=serialize_model(assignment))
    db.session.commit()

    return OrganizationSetupOperationResult(
        ok=True,
        flashes=(FlashMessage("Το μέλος προστέθηκε στο Τμήμα.", "success"),),
        redirect_service_unit_id=unit.id,
    )


def _execute_remove_department_member(
    unit: ServiceUnit,
    form_data: Mapping[str, Any],
) -> OrganizationSetupOperationResult:
    """
    Remove one personnel membership assignment from a department.
    """
    assignment_id = parse_optional_int(form_data.get("assignment_id"))
    if assignment_id is None:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη ανάθεση μέλους.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    assignment = PersonnelDepartmentAssignment.query.get_or_404(assignment_id)
    if assignment.service_unit_id != unit.id:
        from flask import abort
        abort(403)

    before = serialize_model(assignment)
    db.session.delete(assignment)
    db.session.flush()
    log_action(entity=assignment, action="DELETE", before=before, after=None)
    db.session.commit()

    return OrganizationSetupOperationResult(
        ok=True,
        flashes=(FlashMessage("Το μέλος αφαιρέθηκε από το Τμήμα.", "success"),),
        redirect_service_unit_id=unit.id,
    )


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_agm(value: Any) -> str:
    raw = _clean_cell(value)
    if not raw:
        return ""
    if raw.endswith(".0"):
        raw = raw[:-2]
    return raw.strip()


def _personnel_id_by_agm_for_service_unit(service_unit_id: int, agm: str) -> int | None:
    agm_value = _normalize_agm(agm)
    if not agm_value:
        return None

    person = (
        Personnel.query.filter(
            Personnel.service_unit_id == service_unit_id,
            Personnel.agm == agm_value,
            Personnel.is_active.is_(True),
        )
        .first()
    )
    return person.id if person else None


def _execute_import_organization_structure(
    unit,
    file_storage,
    *,
    allowed_personnel_ids: set[int] | None = None,
) -> OrganizationSetupOperationResult:
    """
    Import organization structure from Excel.

    IMPORTANT IMPORT BEHAVIOR
    -------------------------
    - Creates missing Directories
    - Creates missing Departments
    - Assigns directory/department role holders when AGM matches
    - Creates membership assignments for matched personnel into the department
    """
    if file_storage is None or not getattr(file_storage, "filename", ""):
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Δεν επιλέχθηκε αρχείο Excel.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    filename = (file_storage.filename or "").lower()
    if not filename.endswith(".xlsx"):
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Υποστηρίζονται μόνο αρχεία .xlsx.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    try:
        file_bytes = file_storage.read()
        workbook = load_workbook(BytesIO(file_bytes), data_only=True)
        sheet = workbook.active
    except Exception:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Αποτυχία ανάγνωσης του αρχείου Excel.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage("Το Excel είναι κενό.", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    header_row = rows[0]
    headers = {_clean_cell(cell).upper(): idx for idx, cell in enumerate(header_row)}

    required_headers = {
        "ΔΙΕΥΘΥΝΣΗ",
        "ΔΙΕΥΘΥΝΤΗΣ_ΑΓΜ",
        "ΤΜΗΜΑ",
        "ΠΡΟΙΣΤΑΜΕΝΟΣ_ΑΓΜ",
        "ΒΟΗΘΟΣ_ΑΓΜ",
    }

    missing = [h for h in required_headers if h not in headers]
    if missing:
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(
                FlashMessage(
                    "Λείπουν υποχρεωτικές στήλες: " + ", ".join(missing),
                    "danger",
                ),
            ),
            redirect_service_unit_id=unit.id,
        )

    created_directories = 0
    created_departments = 0
    created_memberships = 0
    assigned_directors = 0
    assigned_managers = 0
    assigned_deputies = 0
    skipped_role_assignments = 0

    try:
        for excel_row in rows[1:]:
            if excel_row is None:
                continue

            directory_name = _clean_cell(excel_row[headers["ΔΙΕΥΘΥΝΣΗ"]])
            director_agm = _normalize_agm(excel_row[headers["ΔΙΕΥΘΥΝΤΗΣ_ΑΓΜ"]])
            department_name = _clean_cell(excel_row[headers["ΤΜΗΜΑ"]])
            manager_agm = _normalize_agm(excel_row[headers["ΠΡΟΙΣΤΑΜΕΝΟΣ_ΑΓΜ"]])
            deputy_agm = _normalize_agm(excel_row[headers["ΒΟΗΘΟΣ_ΑΓΜ"]])

            if not any([directory_name, director_agm, department_name, manager_agm, deputy_agm]):
                continue

            if not directory_name:
                continue

            directory = (
                Directory.query.filter(
                    Directory.service_unit_id == unit.id,
                    Directory.name == directory_name,
                )
                .first()
            )
            if directory is None:
                directory = Directory(
                    service_unit_id=unit.id,
                    name=directory_name,
                )
                db.session.add(directory)
                db.session.flush()
                created_directories += 1

            if director_agm:
                director_personnel_id = _personnel_id_by_agm_for_service_unit(unit.id, director_agm)
                if (
                    director_personnel_id is not None
                    and (
                        allowed_personnel_ids is None
                        or director_personnel_id in allowed_personnel_ids
                    )
                ):
                    if getattr(directory, "director_personnel_id", None) != director_personnel_id:
                        directory.director_personnel_id = director_personnel_id
                        assigned_directors += 1
                else:
                    skipped_role_assignments += 1

            if not department_name:
                continue

            department = (
                Department.query.filter(
                    Department.service_unit_id == unit.id,
                    Department.directory_id == directory.id,
                    Department.name == department_name,
                )
                .first()
            )
            if department is None:
                department = Department(
                    service_unit_id=unit.id,
                    directory_id=directory.id,
                    name=department_name,
                )
                db.session.add(department)
                db.session.flush()
                created_departments += 1

            if manager_agm:
                manager_personnel_id = _personnel_id_by_agm_for_service_unit(unit.id, manager_agm)
                if (
                    manager_personnel_id is not None
                    and (
                        allowed_personnel_ids is None
                        or manager_personnel_id in allowed_personnel_ids
                    )
                ):
                    if getattr(department, "head_personnel_id", None) != manager_personnel_id:
                        department.head_personnel_id = manager_personnel_id
                        assigned_managers += 1

                    membership_exists = PersonnelDepartmentAssignment.query.filter_by(
                        personnel_id=manager_personnel_id,
                        department_id=department.id,
                    ).first()
                    if membership_exists is None:
                        db.session.add(
                            PersonnelDepartmentAssignment(
                                personnel_id=manager_personnel_id,
                                service_unit_id=unit.id,
                                directory_id=directory.id,
                                department_id=department.id,
                                is_primary=True,
                            )
                        )
                        created_memberships += 1
                else:
                    skipped_role_assignments += 1

            if deputy_agm:
                deputy_personnel_id = _personnel_id_by_agm_for_service_unit(unit.id, deputy_agm)
                if (
                    deputy_personnel_id is not None
                    and (
                        allowed_personnel_ids is None
                        or deputy_personnel_id in allowed_personnel_ids
                    )
                ):
                    if getattr(department, "assistant_personnel_id", None) != deputy_personnel_id:
                        department.assistant_personnel_id = deputy_personnel_id
                        assigned_deputies += 1

                    membership_exists = PersonnelDepartmentAssignment.query.filter_by(
                        personnel_id=deputy_personnel_id,
                        department_id=department.id,
                    ).first()
                    if membership_exists is None:
                        db.session.add(
                            PersonnelDepartmentAssignment(
                                personnel_id=deputy_personnel_id,
                                service_unit_id=unit.id,
                                directory_id=directory.id,
                                department_id=department.id,
                                is_primary=False,
                            )
                        )
                        created_memberships += 1
                else:
                    skipped_role_assignments += 1

        db.session.commit()

    except Exception as exc:
        db.session.rollback()
        return OrganizationSetupOperationResult(
            ok=False,
            flashes=(FlashMessage(f"Αποτυχία import: {exc}", "danger"),),
            redirect_service_unit_id=unit.id,
        )

    summary = (
        f"Το import ολοκληρώθηκε. "
        f"Νέες Διευθύνσεις: {created_directories}, "
        f"Νέα Τμήματα: {created_departments}, "
        f"Νέες συμμετοχές προσωπικού: {created_memberships}, "
        f"Διευθυντές: {assigned_directors}, "
        f"Προϊστάμενοι: {assigned_managers}, "
        f"Βοηθοί: {assigned_deputies}."
    )

    flashes = [FlashMessage(summary, "success")]
    if skipped_role_assignments:
        flashes.append(
            FlashMessage(
                f"{skipped_role_assignments} αναθέσεις ρόλων παραλείφθηκαν "
                f"επειδή δεν βρέθηκε ενεργό προσωπικό της ίδιας Υπηρεσίας.",
                "warning",
            )
        )

    return OrganizationSetupOperationResult(
        ok=True,
        flashes=tuple(flashes),
        redirect_service_unit_id=unit.id,
    )

```

FILE: .\app\services\admin\personnel.py
```python
"""
app/services/admin/personnel.py

Focused personnel page/use-case services for the admin blueprint.

PURPOSE
-------
This module contains person-centric administration services for:
- listing Personnel
- importing Personnel from Excel
- creating Personnel
- editing Personnel
- deleting Personnel

IMPORTANT DOMAIN RULE
---------------------
Directory/Department assignment must NOT be edited from the Personnel form page.

Organizational placement is managed centrally only from:
    /admin/organization-setup

Therefore:
- create/edit/import personnel must not accept or persist directory_id
- create/edit/import personnel must not accept or persist department_id
- the Personnel page remains person-centric
- directory/department placement belongs to the separate
  `PersonnelDepartmentAssignment` model

MODEL-COMPATIBILITY NOTE
------------------------
The actual `Personnel` ORM model supports:
- agm
- aem
- rank
- specialty
- first_name
- last_name
- is_active
- service_unit_id

It does NOT support:
- directory_id
- department_id

This module must stay aligned with that schema. Passing unsupported keyword
arguments to `Personnel(...)` or assigning missing attributes on an existing
`Personnel` instance will raise runtime errors.

ARCHITECTURAL BOUNDARY
----------------------
This module MAY:
- query ORM rows
- validate submitted form/import data
- create/update/delete Personnel rows
- flush/commit DB state
- emit structured service results

This module MUST NOT:
- render templates
- redirect
- flash directly
- implement organization placement orchestration that belongs elsewhere
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.exc import IntegrityError

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import Personnel
from ..organization import (
    effective_scope_service_unit_id_for_manager_or_none,
    match_service_unit_from_text,
    service_units_for_dropdown,
    validate_service_unit_required,
)
from ..shared.excel_imports import build_header_index, cell_at, safe_cell_str
from ..shared.operation_results import FlashMessage, OperationResult
from ..shared.parsing import parse_optional_int


def build_personnel_list_page_context() -> dict[str, Any]:
    """
    Build template context for the personnel list page.

    RETURNS
    -------
    dict[str, Any]
        Template payload containing the visible Personnel rows.

    SCOPE RULE
    ----------
    - admins may see all Personnel
    - managers are restricted to their effective service-unit scope
    """
    query = Personnel.query.options(
        db.joinedload(Personnel.service_unit),
    )

    scope_service_unit_id = effective_scope_service_unit_id_for_manager_or_none()
    if scope_service_unit_id:
        query = query.filter(Personnel.service_unit_id == scope_service_unit_id)

    personnel = (
        query.order_by(
            Personnel.rank.asc(),
            Personnel.last_name.asc(),
            Personnel.first_name.asc(),
        ).all()
    )

    return {
        "personnel": personnel,
    }


def build_personnel_form_page_context(
    *,
    person: Personnel | None,
    form_title: str,
) -> dict[str, Any]:
    """
    Build template context for both create/edit personnel forms.

    PARAMETERS
    ----------
    person:
        Existing Personnel row for edit mode, or None for create mode.
    form_title:
        Page/form title to render.

    RETURNS
    -------
    dict[str, Any]
        Template context for the personnel form page.

    IMPORTANT
    ---------
    Directory / Department are no longer edited here.
    They are managed only from Organization Setup.
    """
    return {
        "person": person,
        "form_title": form_title,
        "service_units": service_units_for_dropdown(),
    }


def execute_import_personnel(file_storage: Any) -> OperationResult:
    """
    Import Personnel rows from an uploaded Excel file.

    PARAMETERS
    ----------
    file_storage:
        Uploaded Flask file object.

    RETURNS
    -------
    OperationResult
        Import outcome, including summary flash text.

    REQUIRED EXCEL COLUMNS
    ----------------------
    The first row must contain headers that map to:
    - ΑΓΜ
    - ΟΝΟΜΑ
    - ΕΠΩΝΥΜΟ

    OPTIONAL COLUMNS
    ----------------
    - ΑΕΜ
    - ΒΑΘΜΟΣ
    - ΕΙΔΙΚΟΤΗΤΑ
    - ΥΠΗΡΕΣΙΑ

    IMPORTANT DOMAIN RULE
    ---------------------
    This import is person-centric only.
    It may assign `service_unit_id` if a valid ServiceUnit match is found,
    but it must NOT attempt to assign directory/department fields on Personnel.
    """
    if not file_storage or not getattr(file_storage, "filename", None):
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Δεν επιλέχθηκε αρχείο.", "danger"),),
        )

    filename = str(file_storage.filename or "").lower()
    if not filename.endswith(".xlsx"):
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Επιτρέπεται μόνο αρχείο .xlsx", "danger"),),
        )

    try:
        import openpyxl

        workbook = openpyxl.load_workbook(file_storage, data_only=True)
        worksheet = workbook.active
    except Exception:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Αποτυχία ανάγνωσης Excel. Ελέγξτε το αρχείο.", "danger"),),
        )

    try:
        header_cells = [cell.value for cell in next(worksheet.iter_rows(min_row=1, max_row=1))]
    except StopIteration:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Το Excel είναι κενό.", "danger"),),
        )

    idx_map = build_header_index(header_cells)

    agm_idx = idx_map.get("αγμ", idx_map.get("agm"))
    first_idx = idx_map.get("ονομα", idx_map.get("first name", idx_map.get("first_name")))
    last_idx = idx_map.get("επωνυμο", idx_map.get("last name", idx_map.get("last_name")))
    aem_idx = idx_map.get("αεμ", idx_map.get("aem"))
    rank_idx = idx_map.get("βαθμος", idx_map.get("rank"))
    spec_idx = idx_map.get("ειδικοτητα", idx_map.get("specialty"))
    service_idx = idx_map.get("υπηρεσια", idx_map.get("service"))

    if agm_idx is None or first_idx is None or last_idx is None:
        return OperationResult(
            ok=False,
            flashes=(
                FlashMessage(
                    "Το Excel πρέπει να έχει στήλες: ΑΓΜ, ΟΝΟΜΑ, ΕΠΩΝΥΜΟ (1η γραμμή).",
                    "danger",
                ),
            ),
        )

    inserted_people: list[Personnel] = []
    skipped_missing = 0
    skipped_duplicate = 0
    skipped_bad_service = 0

    for row in worksheet.iter_rows(min_row=2, values_only=True):
        agm = safe_cell_str(cell_at(row, agm_idx))
        first_name = safe_cell_str(cell_at(row, first_idx))
        last_name = safe_cell_str(cell_at(row, last_idx))

        if not agm or not first_name or not last_name:
            skipped_missing += 1
            continue

        if Personnel.query.filter_by(agm=agm).first():
            skipped_duplicate += 1
            continue

        service_unit_id = None
        if service_idx is not None:
            service_val = safe_cell_str(cell_at(row, service_idx))
            if service_val:
                service_unit = match_service_unit_from_text(service_val)
                if not service_unit:
                    skipped_bad_service += 1
                    continue
                service_unit_id = service_unit.id

        # IMPORTANT:
        # Create Personnel only with fields that actually exist on the model.
        # Directory/Department placement is intentionally excluded from this
        # page/use-case and belongs to PersonnelDepartmentAssignment.
        person = Personnel(
            agm=agm,
            aem=safe_cell_str(cell_at(row, aem_idx)) or None,
            rank=safe_cell_str(cell_at(row, rank_idx)) or None,
            specialty=safe_cell_str(cell_at(row, spec_idx)) or None,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
            service_unit_id=service_unit_id,
        )
        db.session.add(person)
        inserted_people.append(person)

    if not inserted_people:
        return OperationResult(
            ok=False,
            flashes=(
                FlashMessage(
                    "Δεν εισήχθησαν εγγραφές. Ελέγξτε required πεδία/διπλότυπα/Υπηρεσία.",
                    "warning",
                ),
            ),
        )

    db.session.flush()

    for person in inserted_people:
        log_action(person, "CREATE", before=None, after=serialize_model(person))

    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(
            FlashMessage(
                (
                    f"Εισαγωγή ολοκληρώθηκε: {len(inserted_people)} νέες εγγραφές. "
                    f"Παραλείφθηκαν: {skipped_missing} (ελλιπή), "
                    f"{skipped_duplicate} (διπλότυπα ΑΓΜ), "
                    f"{skipped_bad_service} (μη έγκυρη Υπηρεσία)."
                ),
                "success",
            ),
        ),
    )


def execute_create_personnel(
    form_data: Mapping[str, Any],
    *,
    is_admin: bool,
    current_service_unit_id: int | None,
) -> OperationResult:
    """
    Validate and create a Personnel row.

    PARAMETERS
    ----------
    form_data:
        Submitted form mapping.
    is_admin:
        True when the acting user is admin.
    current_service_unit_id:
        Current acting user's service-unit scope for manager-restricted create.

    RETURNS
    -------
    OperationResult
        Creation outcome.

    IMPORTANT
    ---------
    Directory / Department are no longer set from this form.
    """
    agm = (form_data.get("agm") or "").strip()
    aem = (form_data.get("aem") or "").strip()
    rank = (form_data.get("rank") or "").strip()
    specialty = (form_data.get("specialty") or "").strip()
    first_name = (form_data.get("first_name") or "").strip()
    last_name = (form_data.get("last_name") or "").strip()

    if is_admin:
        service_unit_id = parse_optional_int(form_data.get("service_unit_id"))
    else:
        service_unit_id = current_service_unit_id

    if not agm or not first_name or not last_name:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("ΑΓΜ, Όνομα και Επώνυμο είναι υποχρεωτικά.", "danger"),),
        )

    if Personnel.query.filter_by(agm=agm).first():
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Υπάρχει ήδη προσωπικό με αυτό το ΑΓΜ.", "danger"),),
        )

    if not validate_service_unit_required(service_unit_id):
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η Υπηρεσία είναι υποχρεωτική και πρέπει να είναι έγκυρη.", "danger"),),
        )

    # IMPORTANT:
    # Personnel is person-centric. Only persist actual model fields here.
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

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Το προσωπικό καταχωρήθηκε.", "success"),),
        entity_id=person.id,
    )


def execute_edit_personnel(
    person: Personnel,
    form_data: Mapping[str, Any],
    *,
    is_admin: bool,
    current_service_unit_id: int | None,
) -> OperationResult:
    """
    Validate and update an existing Personnel row.

    PARAMETERS
    ----------
    person:
        Existing Personnel row to update.
    form_data:
        Submitted form mapping.
    is_admin:
        True when the acting user is admin.
    current_service_unit_id:
        Current acting user's service-unit scope for manager-restricted edit.

    RETURNS
    -------
    OperationResult
        Update outcome.

    IMPORTANT
    ---------
    Directory / Department are no longer edited here.

    MODEL RULE
    ----------
    Since `Personnel` does not define `directory_id` / `department_id`, this
    service must not assign those attributes at all.
    """
    before_snapshot = serialize_model(person)

    agm = (form_data.get("agm") or "").strip()
    aem = (form_data.get("aem") or "").strip()
    rank = (form_data.get("rank") or "").strip()
    specialty = (form_data.get("specialty") or "").strip()
    first_name = (form_data.get("first_name") or "").strip()
    last_name = (form_data.get("last_name") or "").strip()

    if is_admin:
        service_unit_id = parse_optional_int(form_data.get("service_unit_id"))
    else:
        service_unit_id = current_service_unit_id

    is_active = bool(form_data.get("is_active"))

    if not agm or not first_name or not last_name:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("ΑΓΜ, Όνομα και Επώνυμο είναι υποχρεωτικά.", "danger"),),
        )

    existing = Personnel.query.filter(
        Personnel.agm == agm,
        Personnel.id != person.id,
    ).first()
    if existing:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Υπάρχει ήδη προσωπικό με αυτό το ΑΓΜ.", "danger"),),
        )

    if not validate_service_unit_required(service_unit_id):
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η Υπηρεσία είναι υποχρεωτική και πρέπει να είναι έγκυρη.", "danger"),),
        )

    person.agm = agm
    person.aem = aem or None
    person.rank = rank or None
    person.specialty = specialty or None
    person.first_name = first_name
    person.last_name = last_name
    person.service_unit_id = service_unit_id
    person.is_active = is_active

    # IMPORTANT:
    # Do not touch directory/department placement here.
    # Placement is managed centrally through organization setup and
    # PersonnelDepartmentAssignment, not via inline Personnel fields.

    db.session.flush()
    log_action(person, "UPDATE", before=before_snapshot, after=serialize_model(person))
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Το προσωπικό ενημερώθηκε.", "success"),),
        entity_id=person.id,
    )


def execute_delete_personnel(person: Personnel) -> OperationResult:
    """
    Delete a Personnel row if no blocking references exist.

    PARAMETERS
    ----------
    person:
        Target Personnel row.

    RETURNS
    -------
    OperationResult
        Deletion outcome.

    FAILURE MODE
    ------------
    If the row is already referenced elsewhere, the delete is rolled back and a
    user-facing error message is returned.
    """
    before = serialize_model(person)

    try:
        db.session.delete(person)
        db.session.flush()
        log_action(entity=person, action="DELETE", before=before)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return OperationResult(
            ok=False,
            flashes=(
                FlashMessage(
                    "Το προσωπικό δεν μπορεί να διαγραφεί γιατί χρησιμοποιείται ήδη αλλού στο σύστημα.",
                    "danger",
                ),
            ),
            entity_id=person.id,
        )

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Το προσωπικό διαγράφηκε.", "success"),),
        entity_id=person.id,
    )

```

FILE: .\app\services\admin_organization_setup_service.py
```python
"""
app/services/admin_organization_setup_service.py

Admin organization setup service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.admin.organization_setup`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.admin.organization_setup import *  # noqa: F401,F403

```

FILE: .\app\services\admin_personnel_service.py
```python
"""
app/services/admin_personnel_service.py

Admin personnel service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.admin.personnel`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.admin.personnel import *  # noqa: F401,F403

```

FILE: .\app\services\auth_service.py
```python
"""
app/services/auth_service.py

Focused authentication and bootstrap services for the auth blueprint.

PURPOSE
-------
This module extracts non-HTTP orchestration from:

- /auth/login
- /auth/seed-admin

It keeps `app/blueprints/auth/routes.py` focused on:
- request boundary handling
- render / redirect branching
- flash emission
- Flask-Login session calls

ARCHITECTURAL INTENT
--------------------
This module follows the agreed direction for the project:
- function-first
- explicit helpers
- no unnecessary class hierarchy
- no framework-heavy abstractions

WHY THIS FILE EXISTS
--------------------
In the current source-of-truth state, the auth routes still contained:
- credential validation branching
- active-user checks
- bootstrap admin validation
- bootstrap Personnel/User creation orchestration
- transaction handling

Those are not HTTP concerns and are better kept outside the route layer.

BOUNDARY
--------
This module MAY:
- query ORM rows
- validate submitted auth/bootstrap data
- create and persist ORM rows
- flush / commit database state
- prepare structured service results for routes

This module MUST NOT:
- register routes
- call `render_template(...)`
- call `redirect(...)`
- call `flash(...)`
- call Flask-Login session functions such as `login_user(...)`

SECURITY NOTES
--------------
- UI is never trusted.
- Password validation is always server-side.
- Login result only returns a validated authenticated `User`; the route remains
  responsible for actually calling `login_user(...)`.
- The bootstrap admin flow is self-locking once any `User` exists.

IMPORTANT MODEL-COMPATIBILITY NOTE
----------------------------------
The bootstrap Personnel row must match the actual `Personnel` ORM schema.

According to the provided source-of-truth and actual model implementation:
- `Personnel` includes `service_unit_id`
- `Personnel` does NOT include `directory_id`
- `Personnel` does NOT include `department_id`

Directory/Department placement belongs to the separate
`PersonnelDepartmentAssignment` model and must not be passed into the
`Personnel(...)` constructor.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..extensions import db
from ..models import Personnel, User
from ..services.shared.operation_results import FlashMessage, OperationResult
from ..services.shared.parsing import safe_next_url


@dataclass(frozen=True)
class AuthLoginResult:
    """
    Structured result for login execution.

    FIELDS
    ------
    ok:
        True when credentials are valid and the user may log in.
    flashes:
        Flash-style messages for the route to emit.
    user:
        Authenticated `User` object when login succeeds.
    redirect_url:
        Sanitized post-login redirect target.

    WHY A SEPARATE RESULT TYPE EXISTS
    ---------------------------------
    Login differs from generic CRUD service operations because the route needs:
    - the authenticated `User` object for `login_user(...)`
    - a resolved redirect target

    Reusing the generic `OperationResult` would be awkward and less explicit.
    """

    ok: bool
    flashes: tuple[FlashMessage, ...]
    user: User | None = None
    redirect_url: str | None = None


@dataclass(frozen=True)
class SeedAdminPageContext:
    """
    Small page-context payload for the bootstrap admin page.

    FIELDS
    ------
    bootstrap_blocked:
        True when the application already contains at least one user and the
        seed-admin flow should not be shown as an active setup path.
    """

    bootstrap_blocked: bool

    def as_template_context(self) -> dict[str, Any]:
        """
        Return a template-friendly dict.
        """
        return {
            "bootstrap_blocked": self.bootstrap_blocked,
        }


# ---------------------------------------------------------------------------
# Login services
# ---------------------------------------------------------------------------
def build_login_page_context(raw_next: str | None) -> dict[str, Any]:
    """
    Build template context for the login page.

    PARAMETERS
    ----------
    raw_next:
        Raw `next` value from request args or form data.

    RETURNS
    -------
    dict[str, Any]
        Template context containing a sanitized next URL.

    WHY THIS HELPER EXISTS
    ----------------------
    The login page usually needs to preserve a safe redirect target across GET
    -> POST. Keeping the sanitization here avoids repeating that detail inside
    the route.
    """
    return {
        "next": safe_next_url(
            raw_next,
            fallback_endpoint="procurements.inbox_procurements",
        )
    }


def execute_login(form_data: Mapping[str, Any], raw_next: str | None) -> AuthLoginResult:
    """
    Validate login credentials and resolve the post-login redirect target.

    PARAMETERS
    ----------
    form_data:
        Submitted login form mapping.
    raw_next:
        Raw `next` value from query string or form data.

    RETURNS
    -------
    AuthLoginResult
        Structured login outcome.

    RULES ENFORCED
    --------------
    - username is normalized via strip()
    - password is checked against the stored password hash
    - inactive users are blocked
    - redirect target is sanitized server-side

    IMPORTANT
    ---------
    This function does not call `login_user(...)`.
    The route remains responsible for the Flask session/auth boundary.
    """
    username = (form_data.get("username") or "").strip()
    password = form_data.get("password") or ""

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return AuthLoginResult(
            ok=False,
            flashes=(FlashMessage("Λάθος όνομα χρήστη ή κωδικός.", "danger"),),
            user=None,
            redirect_url=None,
        )

    if not getattr(user, "is_active", False):
        return AuthLoginResult(
            ok=False,
            flashes=(FlashMessage("Ο λογαριασμός είναι ανενεργός.", "danger"),),
            user=None,
            redirect_url=None,
        )

    return AuthLoginResult(
        ok=True,
        flashes=(FlashMessage("Καλώς ήρθατε!", "success"),),
        user=user,
        redirect_url=safe_next_url(
            raw_next,
            fallback_endpoint="procurements.inbox_procurements",
        ),
    )


# ---------------------------------------------------------------------------
# Seed admin services
# ---------------------------------------------------------------------------
def should_block_seed_admin() -> bool:
    """
    Return True when bootstrap admin creation must be blocked.

    RETURNS
    -------
    bool
        True if at least one User already exists.

    WHY THIS HELPER EXISTS
    ----------------------
    The seed-admin flow is intentionally self-locking after the first user is
    created. This rule is used by both GET and POST route branches.
    """
    return User.query.count() > 0


def build_seed_admin_page_context() -> dict[str, Any]:
    """
    Build template context for the bootstrap admin page.

    RETURNS
    -------
    dict[str, Any]
        Minimal template context describing whether bootstrap is already closed.
    """
    return SeedAdminPageContext(
        bootstrap_blocked=should_block_seed_admin(),
    ).as_template_context()


def execute_seed_admin(form_data: Mapping[str, Any]) -> OperationResult:
    """
    Validate and create the first system admin.

    PARAMETERS
    ----------
    form_data:
        Submitted seed-admin form mapping.

    RETURNS
    -------
    OperationResult
        Service-layer outcome with flash messages.

    RULES ENFORCED
    --------------
    - bootstrap is blocked if any user already exists
    - username and password are required
    - username must be unique
    - system-generated bootstrap Personnel AGM must not already exist
    - admin is created together with a linked neutral Personnel row

    TRANSACTION BEHAVIOR
    --------------------
    This function owns the transaction boundary for the bootstrap creation and
    commits on success.

    MODEL COMPATIBILITY
    -------------------
    The bootstrap Personnel row must be created using only fields that actually
    exist on the `Personnel` model.

    The current schema supports:
    - agm
    - aem
    - rank
    - specialty
    - first_name
    - last_name
    - is_active
    - service_unit_id

    It does NOT support:
    - directory_id
    - department_id

    If future bootstrap requirements need directory/department placement, that
    must be implemented through `PersonnelDepartmentAssignment` in a separate
    step after the `Personnel` row exists.
    """
    if should_block_seed_admin():
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Υπάρχει ήδη χρήστης στο σύστημα.", "warning"),),
        )

    username = (form_data.get("username") or "").strip()
    password = form_data.get("password") or ""

    if not username or not password:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Συμπληρώστε όνομα χρήστη και κωδικό.", "danger"),),
        )

    if User.query.filter_by(username=username).first():
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Το username υπάρχει ήδη.", "danger"),),
        )

    existing_admin_personnel = Personnel.query.filter_by(agm="SYS-ADMIN-001").first()
    if existing_admin_personnel:
        return OperationResult(
            ok=False,
            flashes=(
                FlashMessage(
                    "Υπάρχει ήδη system-generated εγγραφή Προσωπικού για bootstrap admin. "
                    "Ελέγξτε τη βάση πριν συνεχίσετε.",
                    "danger",
                ),
            ),
        )

    # ------------------------------------------------------------------
    # IMPORTANT:
    # Create only with fields that actually exist in the Personnel model.
    #
    # DO NOT pass directory_id / department_id here.
    # Those fields are not defined on Personnel and would raise:
    # TypeError: '<field>' is an invalid keyword argument for Personnel
    #
    # Organizational membership to Directory/Department belongs to the
    # PersonnelDepartmentAssignment model and is not part of the bootstrap
    # seed-admin responsibility in the current provided source-of-truth.
    # ------------------------------------------------------------------
    personnel = Personnel(
        agm="SYS-ADMIN-001",
        aem=None,
        rank="SYSTEM",
        specialty="SYSTEM",
        first_name="System",
        last_name="Administrator",
        is_active=True,
        service_unit_id=None,
    )
    db.session.add(personnel)
    db.session.flush()

    user = User(
        username=username,
        is_admin=True,
        is_active=True,
        personnel_id=personnel.id,
        service_unit_id=None,
    )
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Ο admin δημιουργήθηκε. Συνδεθείτε.", "success"),),
        entity_id=user.id,
    )


__all__ = [
    "AuthLoginResult",
    "SeedAdminPageContext",
    "build_login_page_context",
    "execute_login",
    "should_block_seed_admin",
    "build_seed_admin_page_context",
    "execute_seed_admin",
]

```

FILE: .\app\services\excel_imports.py
```python
"""
app/services/excel_imports.py

Shared Excel-import helper compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.shared.excel_imports`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.shared.excel_imports import *  # noqa: F401,F403

```

FILE: .\app\services\master_data_service.py
```python
"""
app/services/master_data_service.py

Shared master-data lookup and validation helpers.

OVERVIEW
--------
This module centralizes repeated read-only and validation-oriented logic for
application master data.

At the moment, this includes:

1. Generic dropdown master data
   - OptionCategory
   - OptionValue

2. ALE–KAE master directory
   - AleKae

3. CPV master directory
   - Cpv

WHY THIS MODULE EXISTS
----------------------
The application uses master-data tables in many places:
- procurement create/edit forms
- filtering screens
- settings pages
- validation of user-submitted form values
- future reporting/export logic

Without a shared service, these patterns tend to get duplicated across route
modules. That leads to:
- inconsistent ordering
- inconsistent validation behavior
- repeated queries
- larger and harder-to-maintain blueprint files

This module solves that by acting as a single place for common master-data
lookup rules.

DESIGN PRINCIPLES
-----------------
- Keep helpers small, explicit, and predictable.
- Validation helpers must be safe for server-side enforcement.
- UI dropdown choices are never trusted by themselves.
- Return empty lists / None on invalid input instead of raising exceptions
  for normal validation scenarios.

SECURITY NOTES
--------------
Master-data validation must happen server-side.

Example:
A browser may submit a forged ALE or CPV value even if the UI dropdown did not
offer it. For that reason:
- validate_ale_or_none()
- validate_cpv_or_none()

must be used before persisting such values.

CURRENT SCOPE
-------------
This module currently provides:
- active option lookups by OptionCategory key
- category fetch helper
- ALE list lookup + validation
- CPV list lookup + validation

ARCHITECTURAL DECISION
----------------------
This module is intentionally kept as a single file for now.

Why it stays unified:
- it is still small
- it has one coherent responsibility: master-data read/validation helpers
- splitting into separate option/ALE/CPV modules now would add complexity
  without meaningful architectural benefit

So for this module the correct decision is:

    stabilize, not decompose

FUTURE EXTENSIONS
-----------------
This module is a good place to later add shared helpers for:
- IncomeTaxRule master data
- WithholdingProfile master data
- canonical labels/keys for option categories
- small cached lookup helpers if needed
"""

from __future__ import annotations

from sqlalchemy.orm import Query

from ..models import AleKae, Cpv, OptionCategory, OptionValue


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------
def _clean_key(value: str | None) -> str:
    """
    Normalize a category-like key for lookup.

    PARAMETERS
    ----------
    value:
        Raw string value.

    RETURNS
    -------
    str
        Trimmed string, or empty string when missing.

    WHY THIS HELPER EXISTS
    ----------------------
    Several public helpers accept an OptionCategory key. Centralizing the
    normalization avoids repeating the same `(value or "").strip()` logic.
    """
    return (value or "").strip()


def _category_id_for_key(category_key: str) -> int | None:
    """
    Resolve the OptionCategory id for a canonical category key.

    PARAMETERS
    ----------
    category_key:
        Canonical OptionCategory.key value.

    RETURNS
    -------
    int | None
        Matching OptionCategory id, or None if the category does not exist.

    WHY THIS HELPER EXISTS
    ----------------------
    Multiple option-row helpers need the category id only. Using a shared
    private helper avoids duplicating the category lookup logic.
    """
    category = get_option_category_by_key(category_key)
    return category.id if category else None


def _option_rows_query(category_id: int, *, active_only: bool) -> Query:
    """
    Build the canonical OptionValue query for a category.

    PARAMETERS
    ----------
    category_id:
        Target OptionCategory primary key.
    active_only:
        When True, include only active rows.

    RETURNS
    -------
    Query
        SQLAlchemy query ordered by:
        1. sort_order ascending
        2. value ascending

    WHY THIS HELPER EXISTS
    ----------------------
    The public option lookup helpers share identical ordering and differ only by:
    - active-only filtering
    - whether they return rows or only `.value` strings
    """
    query = OptionValue.query.filter_by(category_id=category_id)
    if active_only:
        query = query.filter_by(is_active=True)

    return query.order_by(
        OptionValue.sort_order.asc(),
        OptionValue.value.asc(),
    )


# ----------------------------------------------------------------------
# OptionCategory / OptionValue helpers
# ----------------------------------------------------------------------
def get_option_category_by_key(category_key: str) -> OptionCategory | None:
    """
    Return the OptionCategory row for a given key.

    PARAMETERS
    ----------
    category_key:
        Canonical OptionCategory.key value, such as:
        - "KATASTASH"
        - "STADIO"
        - "KATANOMH"
        - "TRIMHNIAIA"
        - "FPA"

    RETURNS
    -------
    OptionCategory | None
        The matching category row, or None if it does not exist.

    WHY THIS HELPER EXISTS
    ----------------------
    Some callers need the full category object, not just its values.
    Centralizing the lookup here keeps route/service code consistent.
    """
    value = _clean_key(category_key)
    if not value:
        return None

    return OptionCategory.query.filter_by(key=value).first()


def get_active_option_values(category_key: str) -> list[str]:
    """
    Return active OptionValue.value strings for a specific OptionCategory key.

    PARAMETERS
    ----------
    category_key:
        The canonical key of the option category.

    RETURNS
    -------
    list[str]
        Active option values ordered by:
        1. sort_order ascending
        2. value ascending

        Returns an empty list when:
        - the category does not exist
        - the category exists but has no active values

    WHY THIS HELPER EXISTS
    ----------------------
    This is one of the most commonly repeated patterns in forms and filters.
    By centralizing it here we guarantee:
    - consistent ordering
    - identical filtering rules
    - smaller blueprint files

    EXAMPLE
    -------
    get_active_option_values("KATASTASH")
    -> ["-", "Εν Εξελίξει", "Ακυρωμένη", "Πέρας"]
    """
    category_id = _category_id_for_key(category_key)
    if category_id is None:
        return []

    rows = _option_rows_query(category_id, active_only=True).all()
    return [row.value for row in rows]


def get_active_option_rows(category_key: str) -> list[OptionValue]:
    """
    Return active OptionValue rows for a category key.

    PARAMETERS
    ----------
    category_key:
        Canonical OptionCategory key.

    RETURNS
    -------
    list[OptionValue]
        Active rows ordered consistently.

    WHY THIS HELPER EXISTS
    ----------------------
    Some screens may need the full row objects rather than only the value text,
    for example to show:
    - id
    - sort_order
    - is_active
    - future metadata
    """
    category_id = _category_id_for_key(category_key)
    if category_id is None:
        return []

    return _option_rows_query(category_id, active_only=True).all()


def get_all_option_rows(category_key: str) -> list[OptionValue]:
    """
    Return all OptionValue rows for a category key, including inactive ones.

    PARAMETERS
    ----------
    category_key:
        Canonical OptionCategory key.

    RETURNS
    -------
    list[OptionValue]
        All rows ordered consistently.

    USE CASE
    --------
    This helper is useful for admin/configuration screens where inactive values
    still need to be displayed and managed.
    """
    category_id = _category_id_for_key(category_key)
    if category_id is None:
        return []

    return _option_rows_query(category_id, active_only=False).all()


# ----------------------------------------------------------------------
# ALE–KAE helpers
# ----------------------------------------------------------------------
def active_ale_rows() -> list[AleKae]:
    """
    Return all ALE–KAE rows ordered for dropdown/list use.

    RETURNS
    -------
    list[AleKae]
        Ordered by AleKae.ale ascending.

    WHY THIS HELPER EXISTS
    ----------------------
    ALE rows are used in multiple places:
    - procurement forms
    - admin settings pages
    - validation logic
    - future exports/reports

    Keeping the canonical ordering here avoids repeated `.order_by(...)`.
    """
    return AleKae.query.order_by(AleKae.ale.asc()).all()


def get_ale_row_by_code(ale_code: str | None) -> AleKae | None:
    """
    Return the ALE row for a given ALE code.

    PARAMETERS
    ----------
    ale_code:
        Raw ALE code.

    RETURNS
    -------
    AleKae | None
        Matching row or None when missing/not found.
    """
    value = (ale_code or "").strip()
    if not value:
        return None

    return AleKae.query.filter_by(ale=value).first()


def validate_ale_or_none(raw: str | None) -> str | None:
    """
    Validate an ALE code against the ALE master directory.

    PARAMETERS
    ----------
    raw:
        Raw ALE code from user input.

    RETURNS
    -------
    str | None
        - cleaned ALE code if it exists in the ALE master list
        - None if the value is blank or invalid

    SECURITY RATIONALE
    ------------------
    UI selections are never trusted. A user may submit a forged value even if
    the UI offered only valid rows.

    Therefore, callers should use this helper before storing ALE values in
    business entities such as Procurement.

    EXAMPLE
    -------
    raw = request.form.get("ale")
    validated = validate_ale_or_none(raw)

    if raw and validated is None:
        flash("Μη έγκυρο ΑΛΕ.", "danger")
    """
    value = (raw or "").strip()
    if not value:
        return None

    exists = AleKae.query.filter_by(ale=value).first()
    return value if exists else None


# ----------------------------------------------------------------------
# CPV helpers
# ----------------------------------------------------------------------
def active_cpv_rows() -> list[Cpv]:
    """
    Return all CPV rows ordered for dropdown/list use.

    RETURNS
    -------
    list[Cpv]
        Ordered by Cpv.cpv ascending.

    WHY THIS HELPER EXISTS
    ----------------------
    CPV rows are reused across forms, validation, filtering, and future export
    logic. Keeping the canonical ordering here avoids repeated query fragments.
    """
    return Cpv.query.order_by(Cpv.cpv.asc()).all()


def get_cpv_row_by_code(cpv_code: str | None) -> Cpv | None:
    """
    Return the CPV row for a given CPV code.

    PARAMETERS
    ----------
    cpv_code:
        Raw CPV code.

    RETURNS
    -------
    Cpv | None
        Matching row or None when missing/not found.
    """
    value = (cpv_code or "").strip()
    if not value:
        return None

    return Cpv.query.filter_by(cpv=value).first()


def validate_cpv_or_none(raw: str | None) -> str | None:
    """
    Validate a CPV code against the CPV master directory.

    PARAMETERS
    ----------
    raw:
        Raw CPV code from user input.

    RETURNS
    -------
    str | None
        - cleaned CPV code if it exists in the CPV master list
        - None if the value is blank or invalid

    SECURITY RATIONALE
    ------------------
    As with ALE validation, CPV values must be enforced server-side because
    client-side dropdown restrictions are not sufficient for trust.

    TYPICAL USE
    -----------
    cpv_raw = request.form.get("cpv")
    cpv_value = validate_cpv_or_none(cpv_raw)
    """
    value = (raw or "").strip()
    if not value:
        return None

    exists = Cpv.query.filter_by(cpv=value).first()
    return value if exists else None


__all__ = [
    "get_option_category_by_key",
    "get_active_option_values",
    "get_active_option_rows",
    "get_all_option_rows",
    "active_ale_rows",
    "get_ale_row_by_code",
    "validate_ale_or_none",
    "active_cpv_rows",
    "get_cpv_row_by_code",
    "validate_cpv_or_none",
]


```

FILE: .\app\services\operation_results.py
```python
"""
app/services/operation_results.py

Shared operation-result compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.shared.operation_results`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.shared.operation_results import *  # noqa: F401,F403

```

FILE: .\app\services\organization\__init__.py
```python
"""
app/services/organization/__init__.py

Canonical organization helper package.

This package exposes query, scope, and validation helpers related to
ServiceUnit/Directory/Department/Personnel structure.
"""

from __future__ import annotations

from .queries import *  # noqa: F401,F403
from .scope import *  # noqa: F401,F403
from .validation import *  # noqa: F401,F403

```

FILE: .\app\services\organization\queries.py
```python
"""
app/services/organization/queries.py

Organization query and lookup helpers.

PURPOSE
-------
This module contains organization-related query helpers only.

It is responsible for:
- dropdown data loaders for ServiceUnit / Directory / Department
- active Personnel lookup for a ServiceUnit
- active Personnel id-set generation for validation support
- controlled free-text ServiceUnit matching for import flows

WHY THIS FILE EXISTS
--------------------
The previous `app/services/organization_service.py` mixed:
- dropdown/query access
- structural validation rules
- scope/security guards

That made one service file responsible for multiple concerns.

This module isolates the query and lookup side so that:
- organization dropdown behavior is easier to locate
- list and import lookups stay reusable
- routes can consume query helpers without pulling in validation/security code

ARCHITECTURAL BOUNDARY
----------------------
This module MAY:
- query ORM rows
- return lists of ORM entities
- return id sets derived from database rows
- perform controlled fuzzy-ish matching for import support

This module must NOT:
- abort with 403
- replace route/service authorization
- mutate organizational structure
- flash / redirect / render templates

SECURITY NOTE
-------------
`match_service_unit_from_text()` is intended for controlled import scenarios.
It is not a security primitive and must never replace explicit server-side
scope validation.
"""

from __future__ import annotations

from flask_login import current_user
from sqlalchemy import func

from ...models import Department, Directory, Personnel, ServiceUnit


def service_units_for_dropdown() -> list[ServiceUnit]:
    """
    Return ServiceUnits visible in current admin/manager dropdown flows.

    RETURNS
    -------
    list[ServiceUnit]
        - admin: all ServiceUnits
        - non-admin: only current_user.service_unit_id, if assigned

    WHY THIS HELPER EXISTS
    ----------------------
    Organization forms and structure screens should expose only the ServiceUnit
    choices that the current user is allowed to operate on.
    """
    if getattr(current_user, "is_admin", False):
        return ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()

    service_unit_id = getattr(current_user, "service_unit_id", None)
    if not service_unit_id:
        return []

    unit = ServiceUnit.query.get(service_unit_id)
    return [unit] if unit else []


def directories_for_dropdown(service_unit_id: int | None = None) -> list[Directory]:
    """
    Return Directory rows for dropdown use.

    PARAMETERS
    ----------
    service_unit_id:
        Optional ServiceUnit filter.

    RETURNS
    -------
    list[Directory]
        Directories ordered by service unit then name, or only by name when a
        specific ServiceUnit is requested.

    WHY THIS HELPER EXISTS
    ----------------------
    Personnel and organization forms need reusable Directory dropdown data with
    optional ServiceUnit scoping.
    """
    query = Directory.query

    if service_unit_id is not None:
        query = query.filter(Directory.service_unit_id == service_unit_id)
        return query.order_by(Directory.name.asc()).all()

    return query.order_by(Directory.service_unit_id.asc(), Directory.name.asc()).all()


def departments_for_dropdown(
    service_unit_id: int | None = None,
    directory_id: int | None = None,
) -> list[Department]:
    """
    Return Department rows for dropdown use.

    PARAMETERS
    ----------
    service_unit_id:
        Optional ServiceUnit filter.
    directory_id:
        Optional Directory filter.

    RETURNS
    -------
    list[Department]
        Departments ordered in a stable, UI-friendly way.

    WHY THIS HELPER EXISTS
    ----------------------
    Personnel and structure forms often need Department options constrained by:
    - service unit
    - directory
    - or both
    """
    query = Department.query

    if service_unit_id is not None:
        query = query.filter(Department.service_unit_id == service_unit_id)

    if directory_id is not None:
        query = query.filter(Department.directory_id == directory_id)

    return query.order_by(
        Department.directory_id.asc(),
        Department.name.asc(),
    ).all()


def active_personnel_for_service_unit(service_unit_id: int) -> list[Personnel]:
    """
    Return active Personnel for a specific ServiceUnit.

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit primary key.

    RETURNS
    -------
    list[Personnel]
        Active personnel ordered by:
        1. last_name
        2. first_name

    WHY THIS HELPER EXISTS
    ----------------------
    Used repeatedly for:
    - handler dropdowns
    - committee assignments
    - directory/department role assignments
    - organization setup pages
    """
    return (
        Personnel.query.filter_by(is_active=True, service_unit_id=service_unit_id)
        .order_by(Personnel.last_name.asc(), Personnel.first_name.asc())
        .all()
    )


def active_personnel_ids_for_service_unit(service_unit_id: int) -> set[int]:
    """
    Return the set of active Personnel ids for a ServiceUnit.

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit primary key.

    RETURNS
    -------
    set[int]
        Active Personnel ids.

    WHY THIS HELPER EXISTS
    ----------------------
    Membership validation often needs quick server-side set membership checks.
    """
    return {person.id for person in active_personnel_for_service_unit(service_unit_id)}


def match_service_unit_from_text(service_value: str) -> ServiceUnit | None:
    """
    Resolve a ServiceUnit from controlled free text.

    PARAMETERS
    ----------
    service_value:
        Raw text value, typically from imported Excel content.

    RETURNS
    -------
    ServiceUnit | None
        Matching ServiceUnit row or None.

    MATCHING STRATEGY
    -----------------
    Case-insensitive search in this priority order:
    1. ServiceUnit.code
    2. ServiceUnit.short_name
    3. ServiceUnit.description

    WHY THIS HELPER EXISTS
    ----------------------
    Import files may refer to a ServiceUnit in different textual forms.
    This helper keeps matching deterministic and centralized.

    IMPORTANT
    ---------
    This helper is intended for controlled import scenarios only.
    It must not be used as a substitute for authorization or strict id-based
    validation.
    """
    value = (service_value or "").strip()
    if not value:
        return None

    by_code = (
        ServiceUnit.query
        .filter(ServiceUnit.code.isnot(None))
        .filter(func.lower(ServiceUnit.code) == value.lower())
        .first()
    )
    if by_code:
        return by_code

    by_short_name = (
        ServiceUnit.query
        .filter(ServiceUnit.short_name.isnot(None))
        .filter(func.lower(ServiceUnit.short_name) == value.lower())
        .first()
    )
    if by_short_name:
        return by_short_name

    by_description = (
        ServiceUnit.query
        .filter(ServiceUnit.description.isnot(None))
        .filter(func.lower(ServiceUnit.description) == value.lower())
        .first()
    )
    if by_description:
        return by_description

    return None


__all__ = [
    "service_units_for_dropdown",
    "directories_for_dropdown",
    "departments_for_dropdown",
    "active_personnel_for_service_unit",
    "active_personnel_ids_for_service_unit",
    "match_service_unit_from_text",
]


```

FILE: .\app\services\organization\scope.py
```python
"""
app/services/organization/scope.py

Organization scope and hard-guard helpers.

PURPOSE
-------
This module contains scope helpers and authorization-style hard guards used by
organization-related flows.

It is responsible for:
- resolving the effective ServiceUnit scope for admin/manager list screens
- enforcing admin-or-manager-only access
- enforcing same-ServiceUnit manager scope

WHY THIS FILE EXISTS
--------------------
The previous organization service module mixed:
- query/dropdown loading
- structural validation
- scope/security enforcement

This file isolates the scope/security side so that:
- authorization-adjacent logic is clearly separated
- query and validation modules stay cleaner
- route guards and scoped list flows share one source of truth

IMPORTANT BOUNDARY
------------------
This module supports authorization, but does not replace blueprint decorators,
policy checks, or route-level permission design.

This module MAY:
- inspect current_user
- abort(403) for hard guards
- expose current-user-derived scope

This module must NOT:
- render templates
- flash messages
- read request payloads
- mutate database state
"""

from __future__ import annotations

from flask import abort
from flask_login import current_user


def effective_scope_service_unit_id_for_manager_or_none() -> int | None:
    """
    Return the effective ServiceUnit scope for current admin/manager flows.

    RETURNS
    -------
    int | None
        - None for admin users
        - current_user.service_unit_id for non-admin users

    USE CASE
    --------
    Useful in list views where:
    - admins should see everything
    - managers should be restricted to their own ServiceUnit
    """
    if getattr(current_user, "is_admin", False):
        return None

    return getattr(current_user, "service_unit_id", None)


def ensure_admin_or_manager_only() -> None:
    """
    Hard guard: allow only authenticated admin or manager.

    BEHAVIOR
    --------
    Aborts with HTTP 403 unless current_user is:
    - authenticated
    - admin
    - manager

    IMPORTANT
    ---------
    Deputy is intentionally excluded because some pages are explicitly designed
    for admin or manager only.
    """
    if not current_user.is_authenticated:
        abort(403)

    if getattr(current_user, "is_admin", False):
        return

    is_manager = getattr(current_user, "is_manager", None)
    if callable(is_manager) and is_manager():
        return

    abort(403)


def ensure_manager_scope_or_403(service_unit_id: int | None) -> None:
    """
    Enforce that a non-admin manager acts only within their own ServiceUnit.

    PARAMETERS
    ----------
    service_unit_id:
        Target ServiceUnit id of the operation.

    BEHAVIOR
    --------
    - admin: always allowed
    - non-admin:
      * must have a current service_unit_id
      * target service_unit_id must be present
      * both values must match
      * otherwise abort(403)

    WHY THIS HELPER EXISTS
    ----------------------
    This is a core organizational security rule:
    managers must not mutate another ServiceUnit's structure or data.
    """
    if getattr(current_user, "is_admin", False):
        return

    current_service_unit_id = getattr(current_user, "service_unit_id", None)
    if not current_service_unit_id or not service_unit_id:
        abort(403)

    if int(current_service_unit_id) != int(service_unit_id):
        abort(403)


__all__ = [
    "effective_scope_service_unit_id_for_manager_or_none",
    "ensure_admin_or_manager_only",
    "ensure_manager_scope_or_403",
]


```

FILE: .\app\services\organization\validation.py
```python
"""
app/services/organization/validation.py

Organization structural validation helpers.

PURPOSE
-------
This module contains pure validation helpers for organizational structure.

It is responsible for:
- validating that a ServiceUnit exists when required
- validating Directory -> ServiceUnit ownership
- validating Department -> Directory -> ServiceUnit ownership

WHY THIS FILE EXISTS
--------------------
The previous organization service module mixed:
- query/dropdown loading
- structural validation
- scope/security enforcement

This file isolates the validation side so that:
- structural consistency rules live in one place
- routes can validate posted ids without duplicating rules
- validation helpers remain side-effect-free and easy to test

ARCHITECTURAL BOUNDARY
----------------------
This module MAY:
- query ORM rows to validate ownership/existence
- return True/False validation results

This module must NOT:
- abort(403)
- flash messages
- read request.form / request.args directly
- mutate DB state
"""

from __future__ import annotations

from ...extensions import db
from ...models import Department, Directory, ServiceUnit


def validate_service_unit_required(service_unit_id: int | None) -> bool:
    """
    Validate that a ServiceUnit id is present and exists.

    PARAMETERS
    ----------
    service_unit_id:
        Candidate ServiceUnit primary key.

    RETURNS
    -------
    bool
        True only when service_unit_id is present and the ServiceUnit exists.

    WHY THIS HELPER EXISTS
    ----------------------
    Personnel and organization mutations require a valid ServiceUnit and must
    not trust client-side dropdown restrictions.
    """
    if service_unit_id is None:
        return False

    return db.session.get(ServiceUnit, service_unit_id) is not None


def validate_directory_for_service_unit(
    directory_id: int | None,
    service_unit_id: int | None,
) -> bool:
    """
    Validate that a Directory belongs to the selected ServiceUnit.

    PARAMETERS
    ----------
    directory_id:
        Candidate Directory primary key. None is allowed.
    service_unit_id:
        Target ServiceUnit primary key.

    RETURNS
    -------
    bool
        - True when directory_id is None
        - True when the Directory exists and belongs to the ServiceUnit
        - False otherwise

    WHY THIS HELPER EXISTS
    ----------------------
    UI filtering is convenience only. Directory ownership must be enforced
    server-side for every mutation.
    """
    if directory_id is None:
        return True

    directory = db.session.get(Directory, directory_id)
    if not directory:
        return False

    return bool(directory.service_unit_id == service_unit_id)


def validate_department_for_directory_and_service_unit(
    department_id: int | None,
    directory_id: int | None,
    service_unit_id: int | None,
) -> bool:
    """
    Validate that a Department belongs to both the Directory and ServiceUnit.

    PARAMETERS
    ----------
    department_id:
        Candidate Department primary key. None is allowed.
    directory_id:
        Candidate parent Directory primary key.
    service_unit_id:
        Target ServiceUnit primary key.

    RETURNS
    -------
    bool
        - True when department_id is None
        - False when department_id is provided but directory_id is missing
        - True only when the Department exists and matches both ownership links

    WHY THIS HELPER EXISTS
    ----------------------
    Organizational consistency cannot be trusted to the UI and is not fully
    expressible via a single foreign-key constraint.
    """
    if department_id is None:
        return True

    if directory_id is None:
        return False

    department = db.session.get(Department, department_id)
    if not department:
        return False

    return bool(
        department.directory_id == directory_id
        and department.service_unit_id == service_unit_id
    )


__all__ = [
    "validate_service_unit_required",
    "validate_directory_for_service_unit",
    "validate_department_for_directory_and_service_unit",
]


```

FILE: .\app\services\organization_queries.py
```python
"""
app/services/organization_queries.py

Organization query helper compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.organization.queries`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.organization.queries import *  # noqa: F401,F403

```

FILE: .\app\services\organization_scope.py
```python
"""
app/services/organization_scope.py

Organization scope helper compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.organization.scope`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.organization.scope import *  # noqa: F401,F403

```

FILE: .\app\services\organization_service.py
```python
"""
app/services/organization_service.py

Backward-compatible public facade for organization helpers.

PURPOSE
-------
This module preserves the historical import surface:

    from app.services.organization_service import ...

while the implementation is now split into focused modules:
- app.services.organization_queries
- app.services.organization_validation
- app.services.organization_scope

WHY THIS FILE EXISTS
--------------------
The previous implementation had grown into a mixed-responsibility module that
contained:
- dropdown/query loaders
- structural validation helpers
- scope/security guards
- import-support service-unit matching

This facade allows the application to:
- refactor incrementally
- keep existing imports working
- move routes gradually to narrower modules later

PUBLIC API POLICY
-----------------
This file should remain a thin export facade only.

It must NOT:
- reintroduce business/query logic directly
- become a dumping ground
- grow beyond re-exports and documentation
"""

from __future__ import annotations

from .organization.queries import (
    active_personnel_for_service_unit,
    active_personnel_ids_for_service_unit,
    departments_for_dropdown,
    directories_for_dropdown,
    match_service_unit_from_text,
    service_units_for_dropdown,
)
from .organization.scope import (
    effective_scope_service_unit_id_for_manager_or_none,
    ensure_admin_or_manager_only,
    ensure_manager_scope_or_403,
)
from .organization.validation import (
    validate_department_for_directory_and_service_unit,
    validate_directory_for_service_unit,
    validate_service_unit_required,
)

__all__ = [
    "service_units_for_dropdown",
    "directories_for_dropdown",
    "departments_for_dropdown",
    "active_personnel_for_service_unit",
    "active_personnel_ids_for_service_unit",
    "match_service_unit_from_text",
    "validate_service_unit_required",
    "validate_directory_for_service_unit",
    "validate_department_for_directory_and_service_unit",
    "effective_scope_service_unit_id_for_manager_or_none",
    "ensure_admin_or_manager_only",
    "ensure_manager_scope_or_403",
]


```

FILE: .\app\services\organization_validation.py
```python
"""
app/services/organization_validation.py

Organization validation helper compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.organization.validation`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.organization.validation import *  # noqa: F401,F403

```

FILE: .\app\services\parsing.py
```python
"""
app/services/parsing.py

Shared parsing helper compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.shared.parsing`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.shared.parsing import *  # noqa: F401,F403

```

FILE: .\app\services\procurement\__init__.py
```python
"""
app/services/procurement/__init__.py

Canonical procurement service package.

This package groups procurement-specific use-case, query, and workflow
services while keeping the project function-first.
"""

from __future__ import annotations

```

FILE: .\app\services\procurement\create.py
```python
"""
app/services/procurement/create.py

Focused page/update services for the procurement create route.

PURPOSE
-------
This module extracts non-HTTP orchestration from:

    /procurements/new

It keeps the route thin by moving out:
- GET page-context assembly
- POST validation / creation orchestration

ARCHITECTURAL INTENT
--------------------
This module follows the agreed project direction:

- function-first
- explicit helpers
- no unnecessary service classes
- shared lightweight result types where multiple services need the same shape

IMPORTANT CHANGE
----------------
Handler selection is assignment-based, not just person-based.

That means the procurement form stores:
- handler_personnel_id: who the handler is
- handler_assignment_id: the exact organizational assignment selected
  (Directory + Department)

WHY THIS CHANGE EXISTS
----------------------
A single person may belong to multiple Departments / Directories.
The procurement must therefore store the exact organizational context selected
at the time of assignment, so reports (e.g. Award Decision) can render the
correct:
- Department
- Directory

CANONICAL TEMPLATE / SERVICE CONTRACT
-------------------------------------
The UI field name for handler selection is:

- handler_assignment_id

The page context collection exposed to templates is:

- handler_assignments

This module must stay aligned with the templates. Historically, a mismatch
between:
- handler_candidates vs handler_assignments
- handler_personnel_id vs handler_assignment_id

caused the handler dropdown to render empty and the submitted value not to be
read correctly on POST.

BOUNDARY
--------
This module MAY:
- assemble create-page template context
- validate submitted create form values
- create Procurement rows
- perform audit logging and commit

This module MUST NOT:
- register routes
- call render_template(...)
- call redirect(...)
- call flash(...)
"""

from __future__ import annotations

from collections.abc import Mapping

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import (
    IncomeTaxRule,
    Procurement,
    ServiceUnit,
    WithholdingProfile,
)
from ..master_data_service import (
    active_ale_rows,
    get_active_option_values,
    validate_ale_or_none,
)
from ..shared.operation_results import FlashMessage, OperationResult
from ..shared.parsing import parse_decimal, parse_optional_int
from .reference_data import (
    active_income_tax_rules,
    active_withholding_profiles,
    handler_candidate_ids,
    handler_candidates,
)


def build_create_procurement_page_context(
    *,
    is_admin: bool,
    current_service_unit_id: int | None,
) -> dict[str, object]:
    """
    Build template context for the procurement creation page.

    BEHAVIOR
    --------
    - Admin may choose service unit first, so handler list starts empty.
    - Non-admin is scoped to one service unit, so assignment-based handler
      candidates are loaded immediately.

    RETURNS
    -------
    dict[str, object]
        Context for `procurements/new.html`.

    IMPORTANT TEMPLATE CONTRACT
    ---------------------------
    The template expects:
    - handler_assignments

    and not:
    - handler_candidates

    The list contents are still produced by `handler_candidates(...)`, but the
    exposed template key must remain stable and aligned with the form template.
    """
    handler_list = []
    if not is_admin and current_service_unit_id:
        handler_list = handler_candidates(current_service_unit_id)

    return {
        "service_units": ServiceUnit.query.order_by(ServiceUnit.description.asc()).all(),
        "allocation_options": get_active_option_values("KATANOMH"),
        "quarterly_options": get_active_option_values("TRIMHNIAIA"),
        "status_options": get_active_option_values("KATASTASH"),
        "stage_options": get_active_option_values("STADIO"),
        "handler_assignments": handler_list,
        "income_tax_rules": active_income_tax_rules(),
        "withholding_profiles": active_withholding_profiles(),
        "committees": [],
        "ale_rows": active_ale_rows(),
    }


def execute_create_procurement(
    form_data: Mapping[str, object],
    *,
    is_admin: bool,
    current_service_unit_id: int | None,
) -> OperationResult:
    """
    Execute the POST workflow for procurement creation.

    SECURITY / VALIDATION
    ---------------------
    - ServiceUnit is validated server-side.
    - Handler selection is validated against the assignment ids that belong
      to the selected ServiceUnit.
    - UI-submitted values are never trusted.

    IMPORTANT HANDLER RULE
    ----------------------
    The submitted form field is:

        handler_assignment_id

    This value contains the selected `PersonnelDepartmentAssignment.id`.

    From that assignment we derive:
    - procurement.handler_assignment_id
    - procurement.handler_personnel_id

    WHY THIS MATTERS
    ----------------
    The procurement must preserve the exact organizational context selected by
    the user, so later reporting can display the correct Department/Directory.
    """
    if is_admin:
        service_unit_id = parse_optional_int(form_data.get("service_unit_id"))
        if service_unit_id is None:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Η Υπηρεσία είναι υποχρεωτική.", "danger"),),
            )

        service_unit = ServiceUnit.query.get(service_unit_id)
        if not service_unit:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρη Υπηρεσία.", "danger"),),
            )
    else:
        if not current_service_unit_id:
            raise PermissionError("Non-admin procurement creation requires assigned service unit.")
        service_unit_id = current_service_unit_id

    description = (form_data.get("description") or "").strip()
    if not description:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η σύντομη περιγραφή είναι υποχρεωτική.", "danger"),),
        )

    handler_assignment_id = parse_optional_int(form_data.get("handler_assignment_id"))
    selected_assignment = None
    if handler_assignment_id:
        allowed_ids = handler_candidate_ids(service_unit_id)
        if handler_assignment_id not in allowed_ids:
            return OperationResult(
                ok=False,
                flashes=(
                    FlashMessage(
                        "Μη έγκυρος Χειριστής για την επιλεγμένη υπηρεσία.",
                        "danger",
                    ),
                ),
            )

        selected_assignment = next(
            (row for row in handler_candidates(service_unit_id) if row.id == handler_assignment_id),
            None,
        )
        if selected_assignment is None:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Αδυναμία φόρτωσης του επιλεγμένου χειριστή.", "danger"),),
            )

    income_tax_rule_id = parse_optional_int(form_data.get("income_tax_rule_id"))
    if income_tax_rule_id:
        rule = IncomeTaxRule.query.get(income_tax_rule_id)
        if not rule or not rule.is_active:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρος κανόνας Φόρου Εισοδήματος.", "danger"),),
            )
    else:
        rule = None

    withholding_profile_id = parse_optional_int(form_data.get("withholding_profile_id"))
    if withholding_profile_id:
        profile = WithholdingProfile.query.get(withholding_profile_id)
        if not profile or not profile.is_active:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρο προφίλ κρατήσεων.", "danger"),),
            )
    else:
        profile = None

    ale_value = validate_ale_or_none(form_data.get("ale"))
    if (form_data.get("ale") or "").strip() and not ale_value:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο ΑΛΕ (δεν υπάρχει στη λίστα ΑΛΕ-ΚΑΕ).", "danger"),),
        )

    procurement = Procurement(
        service_unit_id=service_unit_id,
        serial_no=(form_data.get("serial_no") or "").strip() or None,
        description=description,
        ale=ale_value,
        allocation=(form_data.get("allocation") or "").strip() or None,
        quarterly=(form_data.get("quarterly") or "").strip() or None,
        status=(form_data.get("status") or "").strip() or None,
        stage=(form_data.get("stage") or "").strip() or None,
        vat_rate=parse_decimal(form_data.get("vat_rate")),
        hop_commitment=(form_data.get("hop_commitment") or "").strip() or None,
        hop_forward1_commitment=(form_data.get("hop_forward1_commitment") or "").strip() or None,
        hop_forward2_commitment=(form_data.get("hop_forward2_commitment") or "").strip() or None,
        hop_approval_commitment=(form_data.get("hop_approval_commitment") or "").strip() or None,
        hop_preapproval=(form_data.get("hop_preapproval") or "").strip() or None,
        hop_forward1_preapproval=(form_data.get("hop_forward1_preapproval") or "").strip() or None,
        hop_forward2_preapproval=(form_data.get("hop_forward2_preapproval") or "").strip() or None,
        hop_approval=(form_data.get("hop_approval") or "").strip() or None,
        aay=(form_data.get("aay") or "").strip() or None,
        procurement_notes=(form_data.get("procurement_notes") or "").strip() or None,
        handler_personnel_id=(
            selected_assignment.personnel_id if selected_assignment is not None else None
        ),
        handler_assignment_id=(
            selected_assignment.id if selected_assignment is not None else None
        ),
        income_tax_rule_id=rule.id if rule else None,
        withholding_profile_id=profile.id if profile else None,
        committee_id=None,
        invoice_number=None,
        invoice_date=None,
        materials_receipt_date=None,
        invoice_receipt_date=None,
    )

    flashes: list[FlashMessage] = []

    send_to_expenses = bool(form_data.get("send_to_expenses"))
    if send_to_expenses and not procurement.hop_approval:
        procurement.send_to_expenses = False
        flashes.append(
            FlashMessage(
                "Για μεταφορά σε Εκκρεμείς Δαπάνες απαιτείται ΗΩΠ Έγκρισης.",
                "warning",
            )
        )
    else:
        procurement.send_to_expenses = bool(send_to_expenses and procurement.hop_approval)

    db.session.add(procurement)
    procurement.recalc_totals()
    db.session.flush()
    log_action(procurement, "CREATE", before=None, after=serialize_model(procurement))
    db.session.commit()

    flashes.append(FlashMessage("Η προμήθεια δημιουργήθηκε.", "success"))

    return OperationResult(
        ok=True,
        flashes=tuple(flashes),
        entity_id=procurement.id,
    )

```

FILE: .\app\services\procurement\edit.py
```python
"""
app/services/procurement/edit.py

Focused edit-page services for the main procurement edit route.

PURPOSE
-------
This module extracts non-HTTP orchestration from:

    /procurements/<id>/edit

It keeps the route thin by moving out:
- GET page-context assembly
- POST validation / mutation orchestration

IMPORTANT CHANGE
----------------
Handler selection is assignment-based.

The selected dropdown value is the id of a PersonnelDepartmentAssignment row,
not just a Personnel row.

This allows the procurement to retain:
- the specific person
- the specific department
- the specific directory

for enterprise-grade reporting consistency.

CANONICAL TEMPLATE / SERVICE CONTRACT
-------------------------------------
The edit template expects:
- handler_assignments

The submitted handler form field is:
- handler_assignment_id

Historically, mismatches between:
- handler_candidates vs handler_assignments
- handler_personnel_id vs handler_assignment_id

caused the handler dropdown to render empty and POST updates to ignore the
selected value.

BOUNDARY
--------
This module MAY:
- assemble edit-page template context
- validate submitted edit form values
- mutate Procurement state
- perform audit logging and commit

This module MUST NOT:
- register routes
- call render_template(...)
- call redirect(...)
- call flash(...)
"""

from __future__ import annotations

from collections.abc import Mapping

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import IncomeTaxRule, Procurement, ServiceUnit, Supplier, WithholdingProfile
from ..master_data_service import (
    active_ale_rows,
    active_cpv_rows,
    get_active_option_values,
    validate_ale_or_none,
)
from ..procurement_service import opened_from_all_list
from ..shared.operation_results import FlashMessage, OperationResult
from ..shared.parsing import parse_decimal, parse_optional_date, parse_optional_int
from .reference_data import (
    active_income_tax_rules,
    active_withholding_profiles,
    handler_candidate_ids,
    handler_candidates,
)


def build_edit_procurement_page_context(
    procurement: Procurement,
    next_url: str,
) -> dict[str, object]:
    """
    Build template context for the main procurement edit page.

    RETURNS
    -------
    dict[str, object]
        Context used by `procurements/edit.html`.

    IMPORTANT TEMPLATE CONTRACT
    ---------------------------
    The template expects:
    - handler_assignments

    The underlying data still comes from `handler_candidates(...)`, but the
    exposed context key must stay aligned with the template contract.
    """
    return {
        "procurement": procurement,
        "service_units": ServiceUnit.query.order_by(ServiceUnit.description.asc()).all(),
        "suppliers": Supplier.query.order_by(Supplier.name.asc()).all(),
        "allocation_options": get_active_option_values("KATANOMH"),
        "quarterly_options": get_active_option_values("TRIMHNIAIA"),
        "status_options": get_active_option_values("KATASTASH"),
        "stage_options": get_active_option_values("STADIO"),
        "handler_assignments": handler_candidates(procurement.service_unit_id),
        "income_tax_rules": active_income_tax_rules(),
        "withholding_profiles": active_withholding_profiles(),
        "committees": [],
        "analysis": procurement.compute_payment_analysis(),
        "next_url": next_url,
        "show_all_report_buttons": opened_from_all_list(next_url),
        "ale_rows": active_ale_rows(),
        "cpv_rows": active_cpv_rows(),
    }


def execute_edit_procurement(
    procurement: Procurement,
    form_data: Mapping[str, object],
    *,
    is_admin: bool,
) -> OperationResult:
    """
    Execute the POST edit workflow for a procurement.

    IMPORTANT HANDLER RULE
    ----------------------
    The submitted form field is:

        handler_assignment_id

    This value carries the selected `PersonnelDepartmentAssignment.id`.

    Server-side we resolve:
    - procurement.handler_assignment_id
    - procurement.handler_personnel_id
    """
    before_snapshot = serialize_model(procurement)

    status_options = get_active_option_values("KATASTASH")
    stage_options = get_active_option_values("STADIO")

    if is_admin:
        new_service_unit_id = parse_optional_int(form_data.get("service_unit_id"))
        if new_service_unit_id is None:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Η Υπηρεσία είναι υποχρεωτική.", "danger"),),
            )

        service_unit = ServiceUnit.query.get(new_service_unit_id)
        if not service_unit:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρη Υπηρεσία.", "danger"),),
            )

        procurement.service_unit_id = service_unit.id

    procurement.serial_no = (form_data.get("serial_no") or "").strip() or None
    procurement.description = (form_data.get("description") or "").strip() or None
    if not procurement.description:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η σύντομη περιγραφή είναι υποχρεωτική.", "danger"),),
        )

    ale_raw = (form_data.get("ale") or "").strip()
    procurement.ale = validate_ale_or_none(ale_raw)
    if ale_raw and procurement.ale is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο ΑΛΕ (δεν υπάρχει στη λίστα ΑΛΕ-ΚΑΕ).", "danger"),),
        )

    procurement.allocation = (form_data.get("allocation") or "").strip() or None
    procurement.quarterly = (form_data.get("quarterly") or "").strip() or None

    new_status = (form_data.get("status") or "").strip() or None
    if new_status and new_status not in status_options:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Κατάσταση.", "danger"),),
        )
    procurement.status = new_status

    new_stage = (form_data.get("stage") or "").strip() or None
    if new_stage and new_stage not in stage_options:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο Στάδιο.", "danger"),),
        )
    procurement.stage = new_stage

    procurement.vat_rate = parse_decimal(form_data.get("vat_rate"))

    procurement.hop_commitment = (form_data.get("hop_commitment") or "").strip() or None
    procurement.hop_forward1_commitment = (form_data.get("hop_forward1_commitment") or "").strip() or None
    procurement.hop_forward2_commitment = (form_data.get("hop_forward2_commitment") or "").strip() or None
    procurement.hop_approval_commitment = (form_data.get("hop_approval_commitment") or "").strip() or None
    procurement.hop_preapproval = (form_data.get("hop_preapproval") or "").strip() or None
    procurement.hop_forward1_preapproval = (form_data.get("hop_forward1_preapproval") or "").strip() or None
    procurement.hop_forward2_preapproval = (form_data.get("hop_forward2_preapproval") or "").strip() or None
    procurement.hop_approval = (form_data.get("hop_approval") or "").strip() or None
    procurement.aay = (form_data.get("aay") or "").strip() or None
    procurement.procurement_notes = (form_data.get("procurement_notes") or "").strip() or None

    procurement.identity_prosklisis = (form_data.get("identity_prosklisis") or "").strip() or None
    procurement.adam_aay = (form_data.get("adam_aay") or "").strip() or None
    procurement.ada_aay = (form_data.get("ada_aay") or "").strip() or None
    procurement.adam_prosklisis = (form_data.get("adam_prosklisis") or "").strip() or None

    procurement.identity_apofasis_anathesis = (form_data.get("identity_apofasis_anathesis") or "").strip() or None
    procurement.adam_apofasis_anathesis = (form_data.get("adam_apofasis_anathesis") or "").strip() or None
    procurement.contract_number = (form_data.get("contract_number") or "").strip() or None
    procurement.adam_contract = (form_data.get("adam_contract") or "").strip() or None

    invoice_number_raw = form_data.get("invoice_number")
    invoice_date_raw = form_data.get("invoice_date")
    materials_receipt_date_raw = form_data.get("materials_receipt_date")
    invoice_receipt_date_raw = form_data.get("invoice_receipt_date")

    procurement.invoice_number = (invoice_number_raw or "").strip() or None

    parsed_invoice_date = parse_optional_date(invoice_date_raw)
    if (invoice_date_raw or "").strip() and parsed_invoice_date is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Ημερομηνία Τιμολογίου.", "danger"),),
        )
    procurement.invoice_date = parsed_invoice_date

    parsed_materials_receipt_date = parse_optional_date(materials_receipt_date_raw)
    if (materials_receipt_date_raw or "").strip() and parsed_materials_receipt_date is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Ημερομηνία Παραλαβής Υλικών.", "danger"),),
        )
    procurement.materials_receipt_date = parsed_materials_receipt_date

    parsed_invoice_receipt_date = parse_optional_date(invoice_receipt_date_raw)
    if (invoice_receipt_date_raw or "").strip() and parsed_invoice_receipt_date is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Ημερομηνία Παραλαβής Τιμολογίου.", "danger"),),
        )
    procurement.invoice_receipt_date = parsed_invoice_receipt_date

    procurement.protocol_number = (form_data.get("protocol_number") or "").strip() or None

    handler_assignment_id = parse_optional_int(form_data.get("handler_assignment_id"))
    if handler_assignment_id:
        allowed_ids = handler_candidate_ids(procurement.service_unit_id)
        if handler_assignment_id not in allowed_ids:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρος Χειριστής για την υπηρεσία.", "danger"),),
            )

        selected_assignment = next(
            (row for row in handler_candidates(procurement.service_unit_id) if row.id == handler_assignment_id),
            None,
        )
        if selected_assignment is None:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Αδυναμία φόρτωσης του επιλεγμένου χειριστή.", "danger"),),
            )

        procurement.handler_assignment_id = selected_assignment.id
        procurement.handler_personnel_id = selected_assignment.personnel_id
    else:
        procurement.handler_assignment_id = None
        procurement.handler_personnel_id = None

    income_tax_rule_id = parse_optional_int(form_data.get("income_tax_rule_id"))
    if income_tax_rule_id:
        rule = IncomeTaxRule.query.get(income_tax_rule_id)
        if not rule or not rule.is_active:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρος κανόνας Φόρου Εισοδήματος.", "danger"),),
            )
        procurement.income_tax_rule_id = rule.id
    else:
        procurement.income_tax_rule_id = None

    withholding_profile_id = parse_optional_int(form_data.get("withholding_profile_id"))
    if withholding_profile_id:
        profile = WithholdingProfile.query.get(withholding_profile_id)
        if not profile or not profile.is_active:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρο προφίλ κρατήσεων.", "danger"),),
            )
        procurement.withholding_profile_id = profile.id
    else:
        procurement.withholding_profile_id = None

    flashes: list[FlashMessage] = []

    send_to_expenses = bool(form_data.get("send_to_expenses"))
    if send_to_expenses and not procurement.hop_approval:
        procurement.send_to_expenses = False
        flashes.append(
            FlashMessage(
                "Για μεταφορά σε Εκκρεμείς Δαπάνες απαιτείται ΗΩΠ Έγκρισης.",
                "warning",
            )
        )
    else:
        procurement.send_to_expenses = bool(send_to_expenses and procurement.hop_approval)

    procurement.recalc_totals()
    db.session.flush()
    log_action(procurement, "UPDATE", before=before_snapshot, after=serialize_model(procurement))
    db.session.commit()

    flashes.append(FlashMessage("Η προμήθεια ενημερώθηκε.", "success"))

    return OperationResult(
        ok=True,
        flashes=tuple(flashes),
    )

```

FILE: .\app\services\procurement\implementation.py
```python
"""
app/services/procurement/implementation.py

Focused page/update services for the procurement implementation phase route.

PURPOSE
-------
This module extracts non-HTTP orchestration from:

    /procurements/<id>/implementation

It keeps the route thin by moving out:
- GET page-context assembly
- POST validation / mutation orchestration

ARCHITECTURAL INTENT
--------------------
This module follows the agreed project direction:

- function-first
- explicit helpers
- no unnecessary service classes
- shared lightweight result types where multiple services need the same shape

BOUNDARY
--------
This module MAY:
- assemble implementation-page template context
- validate submitted implementation form values
- mutate Procurement state
- perform audit logging and commit

This module MUST NOT:
- register routes
- call render_template(...)
- call redirect(...)
- call flash(...)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import IncomeTaxRule, Procurement, ProcurementCommittee, WithholdingProfile
from ..master_data_service import get_active_option_values
from ..shared.operation_results import FlashMessage, OperationResult
from ..shared.parsing import parse_decimal, parse_optional_date, parse_optional_int
from .reference_data import (
    active_income_tax_rules,
    active_withholding_profiles,
    committees_for_service_unit,
)


def build_implementation_procurement_page_context(
    procurement: Procurement,
    next_url: str,
    *,
    can_edit: bool,
) -> dict[str, Any]:
    """
    Build template context for the implementation-phase procurement page.
    """
    return {
        "procurement": procurement,
        "income_tax_rules": active_income_tax_rules(),
        "withholding_profiles": active_withholding_profiles(),
        "committees": committees_for_service_unit(procurement.service_unit_id),
        "analysis": procurement.compute_payment_analysis(),
        "can_edit": can_edit,
        "status_options": get_active_option_values("KATASTASH"),
        "stage_options": get_active_option_values("STADIO"),
        "next_url": next_url,
    }


def execute_implementation_procurement_update(
    procurement: Procurement,
    form_data: Mapping[str, Any],
) -> OperationResult:
    """
    Execute the POST workflow for the implementation-phase procurement page.

    NOTE
    ----
    Handler selection is intentionally not edited here.
    The implementation page keeps the handler context read-only and only updates
    implementation-phase fields.
    """
    before_snapshot = serialize_model(procurement)

    status_options = get_active_option_values("KATASTASH")
    stage_options = get_active_option_values("STADIO")

    new_status = (form_data.get("status") or "").strip() or None
    if new_status and new_status not in status_options:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Κατάσταση.", "danger"),),
        )
    procurement.status = new_status

    new_stage = (form_data.get("stage") or "").strip() or None
    if new_stage and new_stage not in stage_options:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο Στάδιο.", "danger"),),
        )
    procurement.stage = new_stage

    procurement.hop_preapproval = (form_data.get("hop_preapproval") or "").strip() or None
    procurement.hop_approval = (form_data.get("hop_approval") or "").strip() or None
    procurement.aay = (form_data.get("aay") or "").strip() or None
    procurement.procurement_notes = (form_data.get("procurement_notes") or "").strip() or None

    procurement.identity_prosklisis = (form_data.get("identity_prosklisis") or "").strip() or None

    committee_id = parse_optional_int(form_data.get("committee_id"))
    if committee_id:
        committee = ProcurementCommittee.query.get(committee_id)
        if not committee or not committee.is_active or committee.service_unit_id != procurement.service_unit_id:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρη επιτροπή για την υπηρεσία.", "danger"),),
            )
        procurement.committee_id = committee.id
    else:
        procurement.committee_id = None

    income_tax_rule_id = parse_optional_int(form_data.get("income_tax_rule_id"))
    if income_tax_rule_id:
        rule = IncomeTaxRule.query.get(income_tax_rule_id)
        if not rule or not rule.is_active:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρος κανόνας Φόρου Εισοδήματος.", "danger"),),
            )
        procurement.income_tax_rule_id = rule.id
    else:
        procurement.income_tax_rule_id = None

    procurement.adam_aay = (form_data.get("adam_aay") or "").strip() or None
    procurement.ada_aay = (form_data.get("ada_aay") or "").strip() or None
    procurement.adam_prosklisis = (form_data.get("adam_prosklisis") or "").strip() or None

    procurement.identity_apofasis_anathesis = (form_data.get("identity_apofasis_anathesis") or "").strip() or None
    procurement.adam_apofasis_anathesis = (form_data.get("adam_apofasis_anathesis") or "").strip() or None
    procurement.contract_number = (form_data.get("contract_number") or "").strip() or None
    procurement.adam_contract = (form_data.get("adam_contract") or "").strip() or None

    invoice_number_raw = form_data.get("invoice_number")
    invoice_date_raw = form_data.get("invoice_date")
    materials_receipt_date_raw = form_data.get("materials_receipt_date")
    invoice_receipt_date_raw = form_data.get("invoice_receipt_date")

    procurement.invoice_number = (invoice_number_raw or "").strip() or None

    parsed_invoice_date = parse_optional_date(invoice_date_raw)
    if (invoice_date_raw or "").strip() and parsed_invoice_date is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Ημερομηνία Τιμολογίου.", "danger"),),
        )
    procurement.invoice_date = parsed_invoice_date

    parsed_materials_receipt_date = parse_optional_date(materials_receipt_date_raw)
    if (materials_receipt_date_raw or "").strip() and parsed_materials_receipt_date is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Ημερομηνία Παραλαβής Υλικών.", "danger"),),
        )
    procurement.materials_receipt_date = parsed_materials_receipt_date

    parsed_invoice_receipt_date = parse_optional_date(invoice_receipt_date_raw)
    if (invoice_receipt_date_raw or "").strip() and parsed_invoice_receipt_date is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Ημερομηνία Παραλαβής Τιμολογίου.", "danger"),),
        )
    procurement.invoice_receipt_date = parsed_invoice_receipt_date

    procurement.protocol_number = (form_data.get("protocol_number") or "").strip() or None

    withholding_profile_id = parse_optional_int(form_data.get("withholding_profile_id"))
    if withholding_profile_id:
        profile = WithholdingProfile.query.get(withholding_profile_id)
        if not profile or not profile.is_active:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρο προφίλ κρατήσεων.", "danger"),),
            )
        procurement.withholding_profile_id = profile.id
    else:
        procurement.withholding_profile_id = None

    procurement.vat_rate = parse_decimal(form_data.get("vat_rate"))

    flashes: list[FlashMessage] = []

    send_to_expenses = bool(form_data.get("send_to_expenses"))
    if send_to_expenses and not procurement.hop_approval:
        procurement.send_to_expenses = False
        flashes.append(
            FlashMessage(
                "Για μεταφορά σε Εκκρεμείς Δαπάνες απαιτείται ΗΩΠ Έγκρισης.",
                "warning",
            )
        )
    else:
        procurement.send_to_expenses = bool(send_to_expenses and procurement.hop_approval)

    procurement.recalc_totals()

    db.session.flush()
    log_action(procurement, "UPDATE", before=before_snapshot, after=serialize_model(procurement))
    db.session.commit()

    flashes.append(FlashMessage("Η προμήθεια (φάση υλοποίησης) ενημερώθηκε.", "success"))

    return OperationResult(
        ok=True,
        flashes=tuple(flashes),
    )

```

FILE: .\app\services\procurement\list_pages.py
```python
"""
app/services/procurement/list_pages.py

Page-context builders for procurement list routes.

PURPOSE
-------
This module contains focused read-only page services for procurement list
screens.

WHY THIS FILE EXISTS
--------------------
The procurement blueprint contains list routes that should remain limited to:

- decorators
- reading request args
- calling a service / use-case function
- render_template(...)

List-specific query orchestration and page-context assembly belong here
instead of living inline inside route handlers.

ARCHITECTURAL DIRECTION
-----------------------
This module follows the agreed project direction:

- function-first
- no class unless complexity truly justifies it
- no premature abstraction
- no attempt to replace existing lower-level procurement helpers

CURRENT SCOPE
-------------
At this stage the module supports:

- `/procurements/inbox`
- `/procurements/pending-expenses`
- `/procurements/all`

BOUNDARY
--------
This module MAY:
- compose read-only procurement list queries
- apply route-specific list filters
- call existing procurement query helpers
- assemble template context dictionaries

This module MUST NOT:
- register routes
- call render_template(...)
- mutate database state
- implement unrelated business workflows
- replace existing lower-level procurement query helpers
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...models import Procurement
from ..master_data_service import get_active_option_values
from ..procurement_service import (
    apply_list_filters,
    base_procurements_query,
    order_by_serial_no,
    service_units_for_filter,
    with_list_eagerloads,
)


def build_inbox_procurements_list_context(
    request_args: Mapping[str, Any],
    *,
    allow_create: bool,
) -> dict[str, Any]:
    """
    Build template context for the `/procurements/inbox` page.
    """
    query = base_procurements_query()
    query = query.filter(Procurement.status == "ΣΕ ΕΞΕΛΙΞΗ")
    query = query.filter(
        (Procurement.send_to_expenses.is_(False))
        | (Procurement.send_to_expenses.is_(None))
    )

    query = apply_list_filters(query, request_args)
    procurements = order_by_serial_no(with_list_eagerloads(query)).all()

    return {
        "procurements": procurements,
        "page_title": "Λίστα Προμηθειών (μη εγκεκριμένες)",
        "page_subtitle": "Προμήθειες σε εξέλιξη που δεν έχουν μεταφερθεί στις Εκκρεμείς Δαπάνες.",
        "allow_create": allow_create,
        "open_mode": "edit",
        "show_open_button": True,
        "enable_row_colors": True,
        "allow_delete": False,
        "service_units": service_units_for_filter(),
        "status_options": get_active_option_values("KATASTASH"),
        "stage_options": get_active_option_values("STADIO"),
    }


def build_pending_expenses_list_context(
    request_args: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Build template context for the `/procurements/pending-expenses` page.
    """
    query = base_procurements_query()
    query = query.filter(Procurement.status == "ΣΕ ΕΞΕΛΙΞΗ")
    query = query.filter(Procurement.send_to_expenses.is_(True))

    query = apply_list_filters(query, request_args)
    procurements = order_by_serial_no(with_list_eagerloads(query)).all()

    return {
        "procurements": procurements,
        "page_title": "Εκκρεμείς Δαπάνες",
        "page_subtitle": "Προμήθειες σε εξέλιξη που έχουν μεταφερθεί στις Εκκρεμείς Δαπάνες.",
        "allow_create": False,
        "open_mode": "implementation",
        "show_open_button": True,
        "enable_row_colors": True,
        "allow_delete": False,
        "service_units": service_units_for_filter(),
        "status_options": get_active_option_values("KATASTASH"),
        "stage_options": get_active_option_values("STADIO"),
    }


def build_all_procurements_list_context(
    request_args: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Build template context for the `/procurements/all` page.
    """
    query = base_procurements_query()
    query = apply_list_filters(query, request_args)
    procurements = order_by_serial_no(with_list_eagerloads(query)).all()

    return {
        "procurements": procurements,
        "page_title": "Όλες οι Προμήθειες",
        "page_subtitle": "Περιλαμβάνει όλες τις προμήθειες ανεξάρτητα από στάδιο και κατάσταση.",
        "allow_create": False,
        "open_mode": "edit",
        "show_open_button": True,
        "enable_row_colors": True,
        "allow_delete": True,
        "service_units": service_units_for_filter(),
        "status_options": get_active_option_values("KATASTASH"),
        "stage_options": get_active_option_values("STADIO"),
    }


```

FILE: .\app\services\procurement\queries.py
```python
"""
app/services/procurement/queries.py

Procurement query helpers.

PURPOSE
-------
This module contains query-oriented procurement helpers only.

It is responsible for:
- loading a Procurement by id
- building the base procurements query with service isolation
- applying eager loading for list pages
- applying canonical serial-number ordering
- applying list/search filters from request-like args

WHY THIS FILE EXISTS
--------------------
The previous `app/services/procurement_service.py` mixed:
- query construction
- reference-data lookups
- workflow predicates
- presentation/download helpers

This module isolates the query side so that:
- procurement list/query behavior is easier to find
- routes can stay thinner
- query helpers become easier to test independently
- non-query helpers can evolve separately without bloating one file

ARCHITECTURAL BOUNDARY
----------------------
This module MAY:
- return SQLAlchemy query objects
- apply joins, filters, eager loads, and ordering
- load ORM entities for service / route usage

This module must NOT:
- flash messages
- redirect users
- render templates
- decide UI behavior
- generate download filenames
- replace route-level authorization

SECURITY MODEL
--------------
This module supports route/service authorization but does not replace it.

Important assumptions:
- admin users may access all procurements
- non-admin users are service-isolated by Procurement.service_unit_id
- caller still owns action-level permission checks
"""

from __future__ import annotations

from collections.abc import Mapping

from flask import abort
from flask_login import current_user
from sqlalchemy import Integer, and_, case, func
from sqlalchemy.orm import joinedload

from ...extensions import db
from ...models import Procurement, ProcurementSupplier, Supplier
from ..shared.parsing import normalize_digits, parse_optional_int


def load_procurement(procurement_id: int, **_: object) -> Procurement:
    """
    Load a Procurement row by primary key or abort with 404.

    PARAMETERS
    ----------
    procurement_id:
        Target Procurement primary key.

    RETURNS
    -------
    Procurement
        The matching procurement ORM row.

    WHY THIS HELPER EXISTS
    ----------------------
    Decorator factories such as procurement_access_required() often want a
    small loader function with a stable signature. Centralizing it here keeps
    route files smaller and avoids repeated boilerplate.
    """
    procurement = db.session.get(Procurement, procurement_id)
    if procurement is None:
        abort(404)
    return procurement


def base_procurements_query():
    """
    Return the canonical base Procurement query with service isolation applied.

    RETURNS
    -------
    SQLAlchemy query
        - admin users: all procurements
        - non-admin users: only procurements of current_user.service_unit_id

    SECURITY RATIONALE
    ------------------
    Non-admin users must not see procurements belonging to another service
    unit. This helper provides the canonical starting point for procurement
    list pages and procurement searches.
    """
    if current_user.is_admin:
        return Procurement.query

    return Procurement.query.filter(
        Procurement.service_unit_id == current_user.service_unit_id
    )


def with_list_eagerloads(query):
    """
    Apply eager loading commonly needed by procurement list pages.

    PARAMETERS
    ----------
    query:
        Base procurement query.

    RETURNS
    -------
    SQLAlchemy query
        Query with joinedload options applied.

    WHY THIS HELPER EXISTS
    ----------------------
    Procurement list pages often display:
    - service unit
    - handler personnel
    - winner supplier

    Without eager loading, list rendering may trigger N+1 query behavior.
    """
    return query.options(
        joinedload(Procurement.service_unit),
        joinedload(Procurement.handler_personnel),
        joinedload(Procurement.supplies_links).joinedload(ProcurementSupplier.supplier),
    )


def order_by_serial_no(query):
    """
    Apply numeric-first ordering for Procurement.serial_no.

    PARAMETERS
    ----------
    query:
        Procurement query object.

    RETURNS
    -------
    SQLAlchemy query
        Ordered query.

    ORDERING STRATEGY
    -----------------
    1. Purely numeric serial numbers first
    2. Numeric values sorted numerically
    3. Non-numeric values after numeric ones
    4. Final tie-breaker by lexicographic serial value and Procurement.id

    WHY THIS HELPER EXISTS
    ----------------------
    Plain lexicographic sorting would produce undesirable ordering like:
    1, 10, 11, 2, 3

    NOTES
    -----
    This implementation intentionally remains SQLite-friendly.
    """
    serial = func.coalesce(Procurement.serial_no, "")
    is_numeric = serial.op("GLOB")("[0-9]+")
    numeric_value = func.cast(serial, Integer)

    return query.order_by(
        case((is_numeric, 0), else_=1),
        case((is_numeric, numeric_value), else_=None),
        serial.asc(),
        Procurement.id.asc(),
    )


def apply_list_filters(query, request_args: Mapping[str, object]):
    """
    Apply procurement list filters from request-like args.

    PARAMETERS
    ----------
    query:
        Base SQLAlchemy procurement query.
    request_args:
        Typically Flask `request.args`, or any mapping with equivalent
        string-key access.

    RETURNS
    -------
    SQLAlchemy query
        Filtered query.

    SUPPORTED FILTERS
    -----------------
    - service_unit_id (admin only)
    - serial_no
    - description
    - ale
    - hop_preapproval
    - hop_approval
    - aay
    - status
    - stage
    - winner supplier AFM
    - winner supplier name

    IMPORTANT
    ---------
    This helper only applies filtering logic.
    It does not replace authorization logic or submitted-form validation.
    """
    service_unit_id = parse_optional_int(request_args.get("service_unit_id"))
    if service_unit_id and current_user.is_admin:
        query = query.filter(Procurement.service_unit_id == service_unit_id)

    serial_no = (request_args.get("serial_no") or "").strip()
    if serial_no:
        query = query.filter(
            func.coalesce(Procurement.serial_no, "").ilike(f"%{serial_no}%")
        )

    description = (request_args.get("description") or "").strip()
    if description:
        query = query.filter(
            func.coalesce(Procurement.description, "").ilike(f"%{description}%")
        )

    ale = (request_args.get("ale") or "").strip()
    if ale:
        query = query.filter(func.coalesce(Procurement.ale, "").ilike(f"%{ale}%"))

    hop_preapproval = (request_args.get("hop_preapproval") or "").strip()
    if hop_preapproval:
        query = query.filter(
            func.coalesce(Procurement.hop_preapproval, "").ilike(f"%{hop_preapproval}%")
        )

    hop_approval = (request_args.get("hop_approval") or "").strip()
    if hop_approval:
        query = query.filter(
            func.coalesce(Procurement.hop_approval, "").ilike(f"%{hop_approval}%")
        )

    aay = (request_args.get("aay") or "").strip()
    if aay:
        query = query.filter(func.coalesce(Procurement.aay, "").ilike(f"%{aay}%"))

    status = (request_args.get("status") or "").strip()
    if status:
        query = query.filter(Procurement.status == status)

    stage = (request_args.get("stage") or "").strip()
    if stage:
        query = query.filter(Procurement.stage == stage)

    supplier_afm = normalize_digits(request_args.get("supplier_afm"))
    supplier_name = (request_args.get("supplier_name") or "").strip()

    if supplier_afm or supplier_name:
        query = query.outerjoin(
            ProcurementSupplier,
            and_(
                ProcurementSupplier.procurement_id == Procurement.id,
                ProcurementSupplier.is_winner.is_(True),
            ),
        ).outerjoin(Supplier, Supplier.id == ProcurementSupplier.supplier_id)

        if supplier_afm:
            query = query.filter(
                func.coalesce(Supplier.afm, "").ilike(f"%{supplier_afm}%")
            )

        if supplier_name:
            query = query.filter(
                func.coalesce(Supplier.name, "").ilike(f"%{supplier_name}%")
            )

        query = query.distinct()

    return query


__all__ = [
    "load_procurement",
    "base_procurements_query",
    "with_list_eagerloads",
    "order_by_serial_no",
    "apply_list_filters",
]


```

FILE: .\app\services\procurement\reference_data.py
```python
"""
app/services/procurement/reference_data.py

Procurement reference-data and selection helpers.
"""

from __future__ import annotations

from flask_login import current_user
from sqlalchemy.orm import joinedload

from ...extensions import db
from ...models import (
    IncomeTaxRule,
    Personnel,
    PersonnelDepartmentAssignment,
    ProcurementCommittee,
    ServiceUnit,
    WithholdingProfile,
)


def service_units_for_filter() -> list[ServiceUnit]:
    if current_user.is_admin:
        return ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()

    if not current_user.service_unit_id:
        return []

    unit = db.session.get(ServiceUnit, current_user.service_unit_id)
    return [unit] if unit else []


def handler_candidates(service_unit_id: int | None) -> list[PersonnelDepartmentAssignment]:
    """
    Return assignment-based handler candidates for a specific ServiceUnit.

    Each row represents:
    - one person
    - one concrete department
    - one concrete directory

    This allows the dropdown to show:
    ΒΑΘΜΟΣ ΕΙΔΙΚΟΤΗΤΑ ΟΝΟΜΑ ΕΠΩΝΥΜΟ / ΤΜΗΜΑ
    and lets the procurement keep the exact selected organizational context.
    """
    if not service_unit_id:
        return []

    return (
        PersonnelDepartmentAssignment.query.options(
            joinedload(PersonnelDepartmentAssignment.personnel),
            joinedload(PersonnelDepartmentAssignment.directory),
            joinedload(PersonnelDepartmentAssignment.department),
        )
        .join(Personnel, Personnel.id == PersonnelDepartmentAssignment.personnel_id)
        .filter(
            PersonnelDepartmentAssignment.service_unit_id == service_unit_id,
            Personnel.is_active.is_(True),
        )
        .order_by(
            Personnel.last_name.asc(),
            Personnel.first_name.asc(),
            PersonnelDepartmentAssignment.is_primary.desc(),
            PersonnelDepartmentAssignment.id.asc(),
        )
        .all()
    )


def handler_candidate_ids(service_unit_id: int | None) -> set[int]:
    return {assignment.id for assignment in handler_candidates(service_unit_id)}


def committees_for_service_unit(
    service_unit_id: int | None,
) -> list[ProcurementCommittee]:
    if not service_unit_id:
        return []

    return (
        ProcurementCommittee.query.filter_by(
            service_unit_id=service_unit_id,
            is_active=True,
        )
        .order_by(ProcurementCommittee.description.asc())
        .all()
    )


def active_income_tax_rules() -> list[IncomeTaxRule]:
    return (
        IncomeTaxRule.query.filter_by(is_active=True)
        .order_by(IncomeTaxRule.description.asc())
        .all()
    )


def active_withholding_profiles() -> list[WithholdingProfile]:
    return (
        WithholdingProfile.query.filter_by(is_active=True)
        .order_by(WithholdingProfile.description.asc())
        .all()
    )


__all__ = [
    "service_units_for_filter",
    "handler_candidates",
    "handler_candidate_ids",
    "committees_for_service_unit",
    "active_income_tax_rules",
    "active_withholding_profiles",
]

```

FILE: .\app\services\procurement\related_entities.py
```python
"""
app/services/procurement/related_entities.py

Focused mutation services for procurement-related child entities.

PURPOSE
-------
This module extracts non-HTTP orchestration from child-entity POST routes under
a procurement, specifically:

- supplier participation rows
- material/service lines

ARCHITECTURAL INTENT
--------------------
This module follows the agreed direction:

- function-first
- explicit action-oriented helpers
- no generic repository / command framework
- shared lightweight result types where multiple services need the same shape

BOUNDARY
--------
This module MAY:
- validate submitted child-entity form data
- load and validate child entities against a parent procurement
- perform ORM mutations
- perform audit logging and commit

This module MUST NOT:
- register routes
- call render_template(...)
- call redirect(...)
- call flash(...)
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import MaterialLine, Procurement, ProcurementSupplier, Supplier
from ..master_data_service import validate_cpv_or_none
from ..shared.operation_results import FlashMessage, OperationResult
from ..shared.parsing import parse_decimal, parse_optional_int


def execute_add_procurement_supplier(
    procurement: Procurement,
    form_data: Mapping[str, object],
) -> OperationResult:
    """
    Add a supplier participation row to a procurement.
    """
    supplier_id = parse_optional_int(form_data.get("supplier_id"))
    if not supplier_id:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρος προμηθευτής.", "danger"),),
        )

    supplier = Supplier.query.get(supplier_id)
    if not supplier:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Ο προμηθευτής δεν βρέθηκε.", "danger"),),
        )

    exists = ProcurementSupplier.query.filter_by(
        procurement_id=procurement.id,
        supplier_id=supplier_id,
    ).first()
    if exists:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Ο συγκεκριμένος προμηθευτής έχει ήδη προστεθεί σε αυτή την προμήθεια.", "warning"),),
        )

    offered_amount = parse_decimal(form_data.get("offered_amount"))
    is_winner = bool(form_data.get("is_winner"))
    notes = (form_data.get("notes") or "").strip() or None

    if is_winner:
        for link in procurement.supplies_links:
            link.is_winner = False

    link = ProcurementSupplier(
        procurement_id=procurement.id,
        supplier_id=supplier_id,
        offered_amount=offered_amount,
        is_winner=is_winner,
        notes=notes,
    )

    db.session.add(link)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Ο συγκεκριμένος προμηθευτής έχει ήδη προστεθεί σε αυτή την προμήθεια.", "warning"),),
        )

    procurement.recalc_totals()
    db.session.flush()
    log_action(link, "CREATE", before=None, after=serialize_model(link))
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Ο προμηθευτής προστέθηκε.", "success"),),
    )


def execute_delete_procurement_supplier(
    procurement: Procurement,
    link_id: int,
) -> OperationResult:
    """
    Delete a supplier participation row from a procurement.
    """
    link = ProcurementSupplier.query.get(link_id)
    if link is None or link.procurement_id != procurement.id:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η συμμετοχή προμηθευτή δεν βρέθηκε.", "danger"),),
            not_found=True,
        )

    before_snapshot = serialize_model(link)

    db.session.delete(link)
    procurement.recalc_totals()
    db.session.flush()
    log_action(link, "DELETE", before=before_snapshot, after=None)
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Ο προμηθευτής διαγράφηκε.", "success"),),
    )


def execute_add_material_line(
    procurement: Procurement,
    form_data: Mapping[str, object],
) -> OperationResult:
    """
    Add a material/service line to a procurement.
    """
    description = (form_data.get("description") or "").strip()
    if not description:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η περιγραφή γραμμής είναι υποχρεωτική.", "danger"),),
        )

    quantity = parse_decimal(form_data.get("quantity")) or Decimal("0")
    unit_price = parse_decimal(form_data.get("unit_price")) or Decimal("0")

    cpv_raw = (form_data.get("cpv") or "").strip()
    cpv_value = validate_cpv_or_none(cpv_raw)
    if cpv_raw and cpv_value is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο CPV (δεν υπάρχει στη λίστα CPV).", "danger"),),
        )

    line = MaterialLine(
        procurement_id=procurement.id,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        cpv=cpv_value,
        nsn=(form_data.get("nsn") or "").strip() or None,
        unit=(form_data.get("unit") or "").strip() or None,
    )

    db.session.add(line)
    db.session.flush()
    procurement.recalc_totals()
    db.session.flush()
    log_action(line, "CREATE", before=None, after=serialize_model(line))
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Η γραμμή προστέθηκε.", "success"),),
    )


def execute_delete_material_line(
    procurement: Procurement,
    line_id: int,
) -> OperationResult:
    """
    Delete a material/service line from a procurement.
    """
    line = MaterialLine.query.get(line_id)
    if line is None or line.procurement_id != procurement.id:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η γραμμή δεν βρέθηκε.", "danger"),),
            not_found=True,
        )

    before_snapshot = serialize_model(line)

    db.session.delete(line)
    procurement.recalc_totals()
    db.session.flush()
    log_action(line, "DELETE", before=before_snapshot, after=None)
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Η γραμμή διαγράφηκε.", "success"),),
    )


```

FILE: .\app\services\procurement\workflow.py
```python
"""
app/services/procurement/workflow.py

Procurement workflow predicates and domain-state helpers.

PURPOSE
-------
This module contains small procurement workflow helpers that express
domain/application state rules without becoming route handlers.

CURRENT SCOPE
-------------
At this stage, this module intentionally remains small and focused:
- implementation-phase predicate

WHY THIS FILE EXISTS
--------------------
The previous procurement service module mixed:
- query helpers
- reference-data lookups
- workflow rules
- presentation/download helpers

Even though the current workflow surface is small, extracting it now creates a
clear boundary for future procurement-state rules without bloating query or
presentation modules.

ARCHITECTURAL BOUNDARY
----------------------
This module MAY:
- inspect Procurement state
- expose route-independent boolean predicates
- centralize repeated workflow interpretation rules

This module must NOT:
- render templates
- flash/redirect
- access request objects
- contain SQLAlchemy list/query orchestration
- contain UI-only helpers
"""

from __future__ import annotations

from ...models import Procurement


def is_in_implementation_phase(procurement: Procurement) -> bool:
    """
    Determine whether a procurement is in implementation / expenses phase.

    PARAMETERS
    ----------
    procurement:
        Procurement entity.

    RETURNS
    -------
    bool
        True when the procurement is considered to be in implementation phase.

    CURRENT RULE
    ------------
    A procurement is in implementation phase when:
    - send_to_expenses is True
    - hop_approval has a value

    WHY THIS HELPER EXISTS
    ----------------------
    This predicate appears repeatedly in navigation and implementation flows.
    Keeping it centralized ensures one business interpretation.
    """
    return bool(procurement.send_to_expenses and procurement.hop_approval)


__all__ = [
    "is_in_implementation_phase",
]


```

FILE: .\app\services\procurement_calculations.py
```python
"""
app/services/procurement_calculations.py

Conservative procurement calculation service.

PURPOSE
-------
`app/models/procurement.py` delegates financial calculations to
`ProcurementCalculationService`, but that implementation file was not present in
the uploaded `combined_project.md` snapshot.

This module provides the missing canonical implementation so the documented
model contract resolves to a concrete service.

IMPORTANT SCOPE NOTE
--------------------
The formulas implemented here are intentionally conservative and are derived
only from data structures visible in the uploaded source:

- line totals are summed from `procurement.materials[*].total_pre_vat`
- VAT uses `procurement.vat_rate` as a fractional rate when <= 1, otherwise as
  a percentage value
- withholding profile percentages are treated as true percent values, matching
  `WithholdingProfile.total_fraction`
- income tax is applied only when the pre-VAT subtotal exceeds the configured
  threshold, matching the visible `IncomeTaxRule` model docstring

If the original project has additional domain rules that were not included in
`combined_project.md`, reconcile them explicitly before production use.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .shared.parsing import parse_decimal
from ..models.helpers import _money, _normalize_percent, _percent_to_fraction, _to_decimal


class ProcurementCalculationService:
    """
    Stateless financial calculation service for Procurement aggregates.

    DESIGN
    ------
    Class-based only because `app.models.procurement.Procurement` already
    imports this symbol by name. Methods remain stateless and explicit.
    """

    @staticmethod
    def _subtotal(procurement: Any) -> Decimal:
        total = Decimal("0.00")
        for line in getattr(procurement, "materials", []) or []:
            total += _to_decimal(getattr(line, "total_pre_vat", None))
        return _money(total)

    @staticmethod
    def _vat_fraction(procurement: Any) -> Decimal:
        return _normalize_percent(_to_decimal(getattr(procurement, "vat_rate", None)))

    @staticmethod
    def compute_public_withholdings(procurement: Any) -> dict[str, Decimal]:
        subtotal = ProcurementCalculationService._subtotal(procurement)
        profile = getattr(procurement, "withholding_profile", None)
        if not profile:
            return {
                "mt_eloa_amount": Decimal("0.00"),
                "eadhsy_amount": Decimal("0.00"),
                "withholding1_amount": Decimal("0.00"),
                "withholding2_amount": Decimal("0.00"),
                "total_amount": Decimal("0.00"),
                "total_percent": Decimal("0.00"),
            }

        mt = _money(subtotal * _percent_to_fraction(getattr(profile, "mt_eloa_percent", 0)))
        eadhsy = _money(subtotal * _percent_to_fraction(getattr(profile, "eadhsy_percent", 0)))
        w1 = _money(subtotal * _percent_to_fraction(getattr(profile, "withholding1_percent", 0)))
        w2 = _money(subtotal * _percent_to_fraction(getattr(profile, "withholding2_percent", 0)))
        total = _money(mt + eadhsy + w1 + w2)
        return {
            "mt_eloa_amount": mt,
            "eadhsy_amount": eadhsy,
            "withholding1_amount": w1,
            "withholding2_amount": w2,
            "total_amount": total,
            "total_percent": _money(getattr(profile, "total_percent", Decimal("0.00"))),
        }

    @staticmethod
    def compute_income_tax(procurement: Any) -> dict[str, Decimal | bool]:
        subtotal = ProcurementCalculationService._subtotal(procurement)
        rule = getattr(procurement, "income_tax_rule", None)
        if not rule:
            return {
                "applies": False,
                "rate_percent": Decimal("0.00"),
                "threshold_amount": Decimal("0.00"),
                "amount": Decimal("0.00"),
            }

        threshold = _money(getattr(rule, "threshold_amount", Decimal("0.00")))
        if subtotal <= threshold:
            return {
                "applies": False,
                "rate_percent": _money(getattr(rule, "rate_percent", Decimal("0.00"))),
                "threshold_amount": threshold,
                "amount": Decimal("0.00"),
            }

        amount = _money(subtotal * _percent_to_fraction(getattr(rule, "rate_percent", 0)))
        return {
            "applies": True,
            "rate_percent": _money(getattr(rule, "rate_percent", Decimal("0.00"))),
            "threshold_amount": threshold,
            "amount": amount,
        }

    @staticmethod
    def compute_payment_analysis(procurement: Any) -> dict[str, Any]:
        subtotal = ProcurementCalculationService._subtotal(procurement)
        vat_fraction = ProcurementCalculationService._vat_fraction(procurement)
        vat_amount = _money(subtotal * vat_fraction)
        grand_total = _money(subtotal + vat_amount)
        public_withholdings = ProcurementCalculationService.compute_public_withholdings(procurement)
        income_tax = ProcurementCalculationService.compute_income_tax(procurement)
        payable_total = _money(
            grand_total
            - _to_decimal(public_withholdings.get("total_amount"))
            - _to_decimal(income_tax.get("amount"))
        )
        return {
            "sum_total": subtotal,
            "vat_percent": _money(vat_fraction * Decimal("100")),
            "vat_amount": vat_amount,
            "grand_total": grand_total,
            "public_withholdings": public_withholdings,
            "income_tax": income_tax,
            "payable_total": payable_total,
        }

    @staticmethod
    def recalc_totals(procurement: Any) -> None:
        analysis = ProcurementCalculationService.compute_payment_analysis(procurement)
        procurement.sum_total = analysis["sum_total"]
        procurement.vat_amount = analysis["vat_amount"]
        procurement.grand_total = analysis["grand_total"]

```

FILE: .\app\services\procurement_create_service.py
```python
"""
app/services/procurement_create_service.py

Procurement create service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.procurement.create`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.procurement.create import *  # noqa: F401,F403

```

FILE: .\app\services\procurement_edit_service.py
```python
"""
app/services/procurement_edit_service.py

Procurement edit service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.procurement.edit`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.procurement.edit import *  # noqa: F401,F403

```

FILE: .\app\services\procurement_implementation_service.py
```python
"""
app/services/procurement_implementation_service.py

Procurement implementation service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.procurement.implementation`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.procurement.implementation import *  # noqa: F401,F403

```

FILE: .\app\services\procurement_list_page_service.py
```python
"""
app/services/procurement_list_page_service.py

Procurement list page service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.procurement.list_pages`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.procurement.list_pages import *  # noqa: F401,F403

```

FILE: .\app\services\procurement_queries.py
```python
"""
app/services/procurement_queries.py

Procurement query helper compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.procurement.queries`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.procurement.queries import *  # noqa: F401,F403

```

FILE: .\app\services\procurement_reference_data.py
```python
"""
app/services/procurement_reference_data.py

Procurement reference-data helper compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.procurement.reference_data`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.procurement.reference_data import *  # noqa: F401,F403

```

FILE: .\app\services\procurement_related_entities_service.py
```python
"""
app/services/procurement_related_entities_service.py

Procurement related-entities service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.procurement.related_entities`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.procurement.related_entities import *  # noqa: F401,F403

```

FILE: .\app\services\procurement_service.py
```python
"""
app/services/procurement_service.py

Backward-compatible public facade for procurement helpers.

PURPOSE
-------
This module preserves the historical import surface:

    from app.services.procurement_service import ...

while the implementation is now split into focused modules:
- app.services.procurement_queries
- app.services.procurement_reference_data
- app.services.procurement_workflow
- app.presentation.procurement_ui

WHY THIS FILE EXISTS
--------------------
The previous implementation had grown into a mixed-responsibility module that
contained:
- procurement queries
- list filtering
- reference-data lookup helpers
- workflow predicates
- UI/download helpers

That made the file harder to navigate and increased the chance that unrelated
concerns would keep accumulating inside one service file.

This facade allows the application to:
- refactor incrementally
- keep existing imports working during the transition
- move routes gradually to the more specific modules later

PUBLIC API POLICY
-----------------
This file should remain a thin export facade only.

It must NOT:
- reintroduce business/query logic directly
- become a new dumping ground
- grow beyond import re-exports and module-level documentation

MIGRATION NOTE
--------------
Existing imports may continue to use this module for now.

Future route/service cleanup may replace imports gradually with more specific
modules, for example:
- query helpers       -> app.services.procurement_queries
- lookup helpers      -> app.services.procurement_reference_data
- workflow predicates -> app.services.procurement_workflow
- UI helpers          -> app.presentation.procurement_ui
"""

from __future__ import annotations

from .procurement.queries import (
    apply_list_filters,
    base_procurements_query,
    load_procurement,
    order_by_serial_no,
    with_list_eagerloads,
)
from .procurement.reference_data import (
    active_income_tax_rules,
    active_withholding_profiles,
    committees_for_service_unit,
    handler_candidate_ids,
    handler_candidates,
    service_units_for_filter,
)
from .procurement.workflow import is_in_implementation_phase
from ..presentation.procurement_ui import (
    money_filename,
    opened_from_all_list,
    sanitize_filename_component,
)

__all__ = [
    "load_procurement",
    "base_procurements_query",
    "with_list_eagerloads",
    "order_by_serial_no",
    "apply_list_filters",
    "service_units_for_filter",
    "handler_candidates",
    "handler_candidate_ids",
    "committees_for_service_unit",
    "active_income_tax_rules",
    "active_withholding_profiles",
    "is_in_implementation_phase",
    "opened_from_all_list",
    "sanitize_filename_component",
    "money_filename",
]


```

FILE: .\app\services\procurement_workflow.py
```python
"""
app/services/procurement_workflow.py

Procurement workflow helper compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.procurement.workflow`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.procurement.workflow import *  # noqa: F401,F403

```

FILE: .\app\services\settings\__init__.py
```python
"""
app/services/settings/__init__.py

Canonical settings service package.

This package contains non-HTTP orchestration used by the settings blueprint.
"""

from __future__ import annotations

```

FILE: .\app\services\settings\committees.py
```python
"""
app/services/settings/committees.py

Procurement committee settings page/use-case helpers.

PURPOSE
-------
This module extracts non-HTTP orchestration from:

- /settings/committees

RESPONSIBILITIES
----------------
This module handles:
- page-context assembly for the committees screen
- ServiceUnit scope resolution for admin vs manager/deputy flows
- committee CRUD validation and persistence
- committee-member validation against active personnel in the same service unit

SECURITY MODEL
--------------
- Admin may operate on any selected ServiceUnit.
- Non-admin manager/deputy is forced server-side to their own ServiceUnit.
- Reusable scope guards remain in `app/security/settings_guards.py`.

DESIGN
------
- function-first
- one focused use-case module for one settings sub-area
- no generic repository abstraction
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flask_login import current_user

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import Personnel, ProcurementCommittee, ServiceUnit
from ..shared.operation_results import FlashMessage, OperationResult
from ..shared.parsing import parse_optional_int
from ...security.settings_guards import ensure_committee_scope_or_403


def _active_personnel_for_dropdown(service_unit_id: int | None = None) -> list[Personnel]:
    """
    Return active personnel for dropdown usage.

    PARAMETERS
    ----------
    service_unit_id:
        Optional ServiceUnit filter.

    RETURNS
    -------
    list[Personnel]
        Active Personnel ordered by last_name / first_name, either globally or
        scoped to one ServiceUnit.
    """
    query = Personnel.query.filter_by(is_active=True)

    if service_unit_id is not None:
        query = query.filter_by(service_unit_id=service_unit_id)

    return query.order_by(Personnel.last_name.asc(), Personnel.first_name.asc()).all()


def build_committees_page_context(args: Mapping[str, object]) -> dict[str, Any]:
    """
    Build template context for the committees page.

    PARAMETERS
    ----------
    args:
        Query-string mapping, typically request.args.

    RETURNS
    -------
    dict[str, Any]
        Template context for the committees page.
    """
    if current_user.is_admin:
        scope_service_unit_id = parse_optional_int((args.get("service_unit_id") or "").strip())
    else:
        scope_service_unit_id = current_user.service_unit_id

    service_units = ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()
    committees_list: list[ProcurementCommittee] = []
    personnel_list: list[Personnel] = []

    if scope_service_unit_id:
        ensure_committee_scope_or_403(scope_service_unit_id)
        committees_list = (
            ProcurementCommittee.query
            .filter_by(service_unit_id=scope_service_unit_id)
            .order_by(ProcurementCommittee.description.asc())
            .all()
        )
        personnel_list = _active_personnel_for_dropdown(scope_service_unit_id)

    return {
        "service_units": service_units,
        "committees": committees_list,
        "personnel_list": personnel_list,
        "scope_service_unit_id": scope_service_unit_id,
        "is_admin": current_user.is_admin,
    }


def execute_committee_action(form_data: Mapping[str, object]) -> OperationResult:
    """
    Execute create/update/delete action for a procurement committee.

    PARAMETERS
    ----------
    form_data:
        Submitted form payload.

    RETURNS
    -------
    OperationResult
        Result object. `entity_id` is used here as the redirect scope
        ServiceUnit id for the route.
    """
    service_unit_id = parse_optional_int((form_data.get("service_unit_id") or "").strip())
    if not service_unit_id:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η υπηρεσία είναι υποχρεωτική.", "danger"),),
        )

    ensure_committee_scope_or_403(service_unit_id)

    allowed_ids = {person.id for person in _active_personnel_for_dropdown(service_unit_id)}

    def _validate_member(candidate_id: int | None) -> int | None:
        if candidate_id is None:
            return None
        return candidate_id if candidate_id in allowed_ids else None

    action = (form_data.get("action") or "").strip()

    if action == "create":
        description = (form_data.get("description") or "").strip()
        identity_text = (form_data.get("identity_text") or "").strip() or None
        president_id = _validate_member(parse_optional_int((form_data.get("president_personnel_id") or "").strip()))
        member1_id = _validate_member(parse_optional_int((form_data.get("member1_personnel_id") or "").strip()))
        member2_id = _validate_member(parse_optional_int((form_data.get("member2_personnel_id") or "").strip()))
        is_active = bool(form_data.get("is_active") == "on")

        if not description:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Η περιγραφή είναι υποχρεωτική.", "danger"),),
                entity_id=service_unit_id,
            )

        exists = ProcurementCommittee.query.filter_by(
            service_unit_id=service_unit_id,
            description=description,
        ).first()
        if exists:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Υπάρχει ήδη επιτροπή με αυτή την περιγραφή στην Υπηρεσία.", "danger"),),
                entity_id=service_unit_id,
            )

        committee = ProcurementCommittee(
            service_unit_id=service_unit_id,
            description=description,
            identity_text=identity_text,
            president_personnel_id=president_id,
            member1_personnel_id=member1_id,
            member2_personnel_id=member2_id,
            is_active=is_active,
        )
        db.session.add(committee)
        db.session.flush()
        log_action(committee, "CREATE", after=serialize_model(committee))
        db.session.commit()

        return OperationResult(
            ok=True,
            flashes=(FlashMessage("Η επιτροπή προστέθηκε.", "success"),),
            entity_id=service_unit_id,
        )

    if action == "update":
        committee_id = parse_optional_int((form_data.get("id") or "").strip())
        if committee_id is None:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρη επιτροπή.", "danger"),),
                entity_id=service_unit_id,
            )

        committee = ProcurementCommittee.query.get_or_404(committee_id)
        if committee.service_unit_id != service_unit_id:
            from flask import abort
            abort(403)

        before = serialize_model(committee)

        description = (form_data.get("description") or "").strip()
        identity_text = (form_data.get("identity_text") or "").strip() or None
        president_id = _validate_member(parse_optional_int((form_data.get("president_personnel_id") or "").strip()))
        member1_id = _validate_member(parse_optional_int((form_data.get("member1_personnel_id") or "").strip()))
        member2_id = _validate_member(parse_optional_int((form_data.get("member2_personnel_id") or "").strip()))
        is_active = bool(form_data.get("is_active") == "on")

        if not description:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Η περιγραφή είναι υποχρεωτική.", "danger"),),
                entity_id=service_unit_id,
            )

        exists = ProcurementCommittee.query.filter(
            ProcurementCommittee.service_unit_id == service_unit_id,
            ProcurementCommittee.description == description,
            ProcurementCommittee.id != committee.id,
        ).first()
        if exists:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Υπάρχει ήδη άλλη επιτροπή με αυτή την περιγραφή στην Υπηρεσία.", "danger"),),
                entity_id=service_unit_id,
            )

        committee.description = description
        committee.identity_text = identity_text
        committee.president_personnel_id = president_id
        committee.member1_personnel_id = member1_id
        committee.member2_personnel_id = member2_id
        committee.is_active = is_active

        db.session.flush()
        log_action(committee, "UPDATE", before=before, after=serialize_model(committee))
        db.session.commit()

        return OperationResult(
            ok=True,
            flashes=(FlashMessage("Η επιτροπή ενημερώθηκε.", "success"),),
            entity_id=service_unit_id,
        )

    if action == "delete":
        committee_id = parse_optional_int((form_data.get("id") or "").strip())
        if committee_id is None:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρη επιτροπή.", "danger"),),
                entity_id=service_unit_id,
            )

        committee = ProcurementCommittee.query.get_or_404(committee_id)
        if committee.service_unit_id != service_unit_id:
            from flask import abort
            abort(403)

        before = serialize_model(committee)
        db.session.delete(committee)
        db.session.flush()
        log_action(committee, "DELETE", before=before, after=None)
        db.session.commit()

        return OperationResult(
            ok=True,
            flashes=(FlashMessage("Η επιτροπή διαγράφηκε.", "success"),),
            entity_id=service_unit_id,
        )

    return OperationResult(
        ok=False,
        flashes=(FlashMessage("Μη έγκυρη ενέργεια.", "danger"),),
        entity_id=service_unit_id,
    )


__all__ = [
    "build_committees_page_context",
    "execute_committee_action",
]


```

FILE: .\app\services\settings\feedback.py
```python
"""
app/services/settings/feedback.py

Feedback page/use-case helpers for settings routes.

PURPOSE
-------
This module extracts non-HTTP orchestration from:

- /settings/feedback
- /settings/feedback/admin

RESPONSIBILITIES
----------------
This module handles:
- page-context assembly for user and admin feedback screens
- feedback submission validation
- admin feedback status updates
- filtering logic for the admin list page

ROUTE BOUNDARY
--------------
Routes remain responsible only for:
- decorators
- reading request.args / request.form
- flashing returned messages
- render / redirect responses

IMPORTANT SOURCE-OF-TRUTH NOTE
------------------------------
The current `combined_project.md` contains an inconsistency:
`app/blueprints/settings/routes.py` uses Feedback fields such as `user_id`,
`category`, and `related_procurement_id`, while the visible
`app/models/feedback.py` excerpt in the same source does not show those fields.

This module preserves the route contract exactly as the route file currently
uses it. The model/schema mismatch must be reconciled separately in the project.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...extensions import db
from ...models import Feedback
from ..shared.operation_results import FlashMessage, OperationResult
from ..shared.parsing import parse_optional_int

FEEDBACK_CATEGORIES: list[tuple[str, str]] = [
    ("complaint", "Παράπονο"),
    ("suggestion", "Πρόταση"),
    ("bug", "Σφάλμα"),
    ("other", "Άλλο"),
]

FEEDBACK_STATUS_CHOICES: dict[str, str] = {
    "new": "Νέο",
    "in_progress": "Σε εξέλιξη",
    "resolved": "Επιλυμένο",
    "closed": "Κλειστό",
}

FEEDBACK_CATEGORY_LABELS: dict[str | None, str] = {
    "complaint": "Παράπονο",
    "suggestion": "Πρόταση",
    "bug": "Σφάλμα",
    "other": "Άλλο",
    None: "—",
}

VALID_FEEDBACK_CATEGORY_KEYS = {"complaint", "suggestion", "bug", "other"}


def build_feedback_page_context(*, user_id: int) -> dict[str, Any]:
    """
    Build template context for the user feedback page.

    PARAMETERS
    ----------
    user_id:
        Authenticated user id.

    RETURNS
    -------
    dict[str, Any]
        Template context for feedback submission/history display.
    """
    recent_feedback = (
        Feedback.query.filter_by(user_id=user_id)
        .order_by(Feedback.created_at.desc())
        .limit(5)
        .all()
    )

    return {
        "categories": FEEDBACK_CATEGORIES,
        "recent_feedback": recent_feedback,
    }


def execute_feedback_submission(*, user_id: int, form_data: Mapping[str, object]) -> OperationResult:
    """
    Validate and create a feedback entry submitted by a logged-in user.

    PARAMETERS
    ----------
    user_id:
        Authenticated user id.
    form_data:
        Submitted form payload.

    RETURNS
    -------
    OperationResult
        Result object for route flashing/redirecting.
    """
    category = form_data.get("category") or None
    subject = (form_data.get("subject") or "").strip()
    message = (form_data.get("message") or "").strip()
    related_procurement_id_raw = (form_data.get("related_procurement_id") or "").strip()

    if not subject:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Ο τίτλος είναι υποχρεωτικός.", "danger"),),
        )

    if not message:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Το κείμενο είναι υποχρεωτικό.", "danger"),),
        )

    related_procurement_id = parse_optional_int(related_procurement_id_raw)
    if related_procurement_id_raw and related_procurement_id is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο Α/Α προμήθειας.", "danger"),),
        )

    feedback_row = Feedback(
        user_id=user_id,
        category=category,
        subject=subject,
        message=message,
        related_procurement_id=related_procurement_id,
        status="new",
    )
    db.session.add(feedback_row)
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Το μήνυμά σας καταχωρήθηκε.", "success"),),
        entity_id=getattr(feedback_row, "id", None),
    )


def build_feedback_admin_page_context(args: Mapping[str, object]) -> dict[str, Any]:
    """
    Build template context for the admin feedback management page.

    PARAMETERS
    ----------
    args:
        Query-string mapping, typically request.args.

    RETURNS
    -------
    dict[str, Any]
        Template context with filters, labels, and the filtered feedback list.
    """
    status_filter = (args.get("status") or "").strip() or None
    category_filter = (args.get("category") or "").strip() or None

    query = Feedback.query

    if status_filter and status_filter in FEEDBACK_STATUS_CHOICES:
        query = query.filter(Feedback.status == status_filter)

    if category_filter and category_filter in VALID_FEEDBACK_CATEGORY_KEYS:
        query = query.filter(Feedback.category == category_filter)

    feedback_items = query.order_by(Feedback.created_at.desc()).all()

    return {
        "feedback_items": feedback_items,
        "status_choices": FEEDBACK_STATUS_CHOICES,
        "category_labels": FEEDBACK_CATEGORY_LABELS,
        "status_filter": status_filter,
        "category_filter": category_filter,
    }


def execute_feedback_admin_status_update(form_data: Mapping[str, object]) -> OperationResult:
    """
    Validate and apply an admin feedback status update.

    PARAMETERS
    ----------
    form_data:
        Submitted form payload.

    RETURNS
    -------
    OperationResult
        Result object for route flashing/redirecting.
    """
    feedback_id_raw = (form_data.get("feedback_id") or "").strip()
    new_status = (form_data.get("status") or "").strip()

    feedback_id = parse_optional_int(feedback_id_raw)
    if feedback_id is None or new_status not in FEEDBACK_STATUS_CHOICES:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη ενημέρωση κατάστασης.", "danger"),),
        )

    feedback_row = Feedback.query.get(feedback_id)
    if not feedback_row:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Το συγκεκριμένο παράπονο δεν βρέθηκε.", "danger"),),
            not_found=True,
        )

    feedback_row.status = new_status
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Η κατάσταση ενημερώθηκε.", "success"),),
        entity_id=feedback_id,
    )


__all__ = [
    "FEEDBACK_CATEGORIES",
    "FEEDBACK_STATUS_CHOICES",
    "FEEDBACK_CATEGORY_LABELS",
    "build_feedback_page_context",
    "execute_feedback_submission",
    "build_feedback_admin_page_context",
    "execute_feedback_admin_status_update",
]


```

FILE: .\app\services\settings\master_data_admin.py
```python
"""
app/services/settings/master_data_admin.py

Focused master-data admin services for settings routes.

PURPOSE
-------
This module extracts non-HTTP orchestration from the fat admin/master-data
routes inside `app/blueprints/settings/routes.py`, specifically:

- /settings/ale-kae
- /settings/ale-kae/import
- /settings/cpv
- /settings/cpv/import
- /settings/options/*
- /settings/income-tax
- /settings/withholding-profiles

WHY THIS FILE EXISTS
--------------------
The current settings blueprint mixes already-thin route groups
(ServiceUnits/Suppliers) with several still-fat CRUD/import flows.
Those flows perform:
- validation
- object loading
- persistence
- audit logging
- page-context assembly

That orchestration belongs in the service/use-case layer rather than in route
handlers.

DESIGN
------
- function-first
- one focused module for settings master-data administration
- no generic CRUD framework
- small explicit helper functions per sub-area
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
from typing import Any

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import AleKae, Cpv, IncomeTaxRule, OptionCategory, OptionValue, WithholdingProfile
from ..shared.excel_imports import build_header_index, cell_at, safe_cell_str
from ..master_data_service import get_all_option_rows, get_option_category_by_key
from ..shared.operation_results import FlashMessage, OperationResult
from ..shared.parsing import parse_decimal, parse_optional_int


def _get_or_create_category(key: str, label: str) -> OptionCategory:
    """
    Ensure an OptionCategory row exists and return it.

    NOTE
    ----
    This preserves the current self-healing behavior of the settings option
    pages when seed data has not been run yet.
    """
    category = get_option_category_by_key(key)
    if category:
        if category.label != label:
            category.label = label
            db.session.commit()
        return category

    category = OptionCategory(key=key, label=label)
    db.session.add(category)
    db.session.commit()
    return category


# ----------------------------------------------------------------------
# ALE-KAE
# ----------------------------------------------------------------------
def build_ale_kae_page_context() -> dict[str, Any]:
    """
    Build template context for the ALE-KAE page.
    """
    rows = AleKae.query.order_by(AleKae.ale.asc()).all()
    return {"rows": rows}


def execute_ale_kae_action(form_data: Mapping[str, object]) -> OperationResult:
    """
    Execute create/update/delete action for ALE-KAE rows.
    """
    action = (form_data.get("action") or "").strip()

    if action == "create":
        ale = (form_data.get("ale") or "").strip()
        old_kae = (form_data.get("old_kae") or "").strip() or None
        description = (form_data.get("description") or "").strip() or None
        responsibility = (form_data.get("responsibility") or "").strip() or None

        if not ale:
            return OperationResult(False, (FlashMessage("Το ΑΛΕ είναι υποχρεωτικό.", "danger"),))

        if AleKae.query.filter_by(ale=ale).first():
            return OperationResult(False, (FlashMessage("Υπάρχει ήδη εγγραφή με αυτό το ΑΛΕ.", "danger"),))

        row = AleKae(
            ale=ale,
            old_kae=old_kae,
            description=description,
            responsibility=responsibility,
        )
        db.session.add(row)
        db.session.flush()
        log_action(entity=row, action="CREATE", before=None, after=serialize_model(row))
        db.session.commit()

        return OperationResult(True, (FlashMessage("Η εγγραφή ΑΛΕ-ΚΑΕ προστέθηκε.", "success"),), entity_id=row.id)

    if action == "update":
        row_id = parse_optional_int((form_data.get("id") or "").strip())
        if row_id is None:
            return OperationResult(False, (FlashMessage("Μη έγκυρη εγγραφή.", "danger"),))

        row = AleKae.query.get_or_404(row_id)
        before = serialize_model(row)

        ale = (form_data.get("ale") or "").strip()
        old_kae = (form_data.get("old_kae") or "").strip() or None
        description = (form_data.get("description") or "").strip() or None
        responsibility = (form_data.get("responsibility") or "").strip() or None

        if not ale:
            return OperationResult(False, (FlashMessage("Το ΑΛΕ είναι υποχρεωτικό.", "danger"),))

        exists = AleKae.query.filter(AleKae.ale == ale, AleKae.id != row.id).first()
        if exists:
            return OperationResult(False, (FlashMessage("Υπάρχει ήδη άλλη εγγραφή με αυτό το ΑΛΕ.", "danger"),))

        row.ale = ale
        row.old_kae = old_kae
        row.description = description
        row.responsibility = responsibility

        db.session.flush()
        log_action(entity=row, action="UPDATE", before=before, after=serialize_model(row))
        db.session.commit()

        return OperationResult(True, (FlashMessage("Η εγγραφή ενημερώθηκε.", "success"),), entity_id=row.id)

    if action == "delete":
        row_id = parse_optional_int((form_data.get("id") or "").strip())
        if row_id is None:
            return OperationResult(False, (FlashMessage("Μη έγκυρη εγγραφή.", "danger"),))

        row = AleKae.query.get_or_404(row_id)
        before = serialize_model(row)

        db.session.delete(row)
        db.session.flush()
        log_action(entity=row, action="DELETE", before=before, after=None)
        db.session.commit()

        return OperationResult(True, (FlashMessage("Η εγγραφή διαγράφηκε.", "success"),), entity_id=row.id)

    return OperationResult(False, (FlashMessage("Μη έγκυρη ενέργεια.", "danger"),))


def execute_import_ale_kae(file_storage: Any) -> OperationResult:
    """
    Import ALE-KAE rows from an XLSX file.
    """
    file = file_storage
    if not file or not getattr(file, "filename", None):
        return OperationResult(False, (FlashMessage("Δεν επιλέχθηκε αρχείο.", "danger"),))

    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        return OperationResult(False, (FlashMessage("Επιτρέπεται μόνο αρχείο .xlsx", "danger"),))

    try:
        import openpyxl
        workbook = openpyxl.load_workbook(file, data_only=True)
        worksheet = workbook.active
    except Exception:
        return OperationResult(False, (FlashMessage("Αποτυχία ανάγνωσης Excel. Ελέγξτε το αρχείο.", "danger"),))

    try:
        header_cells = [cell.value for cell in next(worksheet.iter_rows(min_row=1, max_row=1))]
    except StopIteration:
        return OperationResult(False, (FlashMessage("Το Excel είναι κενό.", "danger"),))

    idx_map = build_header_index(header_cells)

    ale_idx = idx_map.get("αλε", idx_map.get("ale"))
    old_kae_idx = idx_map.get("παλιος καε", idx_map.get("old kae", idx_map.get("old_kae")))
    desc_idx = idx_map.get("περιγραφη", idx_map.get("description"))
    resp_idx = idx_map.get("αρμοδιοτητας", idx_map.get("responsibility"))

    if ale_idx is None:
        return OperationResult(False, (FlashMessage("Το Excel πρέπει να έχει στήλη 'ΑΛΕ'.", "danger"),))

    inserted: list[AleKae] = []
    skipped_missing = 0
    skipped_duplicate = 0

    for row in worksheet.iter_rows(min_row=2, values_only=True):
        ale = safe_cell_str(cell_at(row, ale_idx))
        if not ale:
            skipped_missing += 1
            continue

        if AleKae.query.filter_by(ale=ale).first():
            skipped_duplicate += 1
            continue

        obj = AleKae(
            ale=ale,
            old_kae=safe_cell_str(cell_at(row, old_kae_idx)) or None,
            description=safe_cell_str(cell_at(row, desc_idx)) or None,
            responsibility=safe_cell_str(cell_at(row, resp_idx)) or None,
        )
        db.session.add(obj)
        inserted.append(obj)

    if not inserted:
        return OperationResult(False, (FlashMessage("Δεν εισήχθησαν εγγραφές. Ελέγξτε required πεδία/διπλότυπα.", "warning"),))

    db.session.flush()
    for obj in inserted:
        log_action(entity=obj, action="CREATE", before=None, after=serialize_model(obj))
    db.session.commit()

    return OperationResult(
        True,
        (
            FlashMessage(
                f"Εισαγωγή ολοκληρώθηκε: {len(inserted)} νέες εγγραφές. "
                f"Παραλείφθηκαν: {skipped_missing} (ελλιπή), {skipped_duplicate} (διπλότυπα).",
                "success",
            ),
        ),
    )


# ----------------------------------------------------------------------
# CPV
# ----------------------------------------------------------------------
def build_cpv_page_context() -> dict[str, Any]:
    """
    Build template context for the CPV page.
    """
    rows = Cpv.query.order_by(Cpv.cpv.asc()).all()
    return {"rows": rows}


def execute_cpv_action(form_data: Mapping[str, object]) -> OperationResult:
    """
    Execute create/update/delete action for CPV rows.
    """
    action = (form_data.get("action") or "").strip()

    if action == "create":
        cpv_code = (form_data.get("cpv") or "").strip()
        description = (form_data.get("description") or "").strip() or None

        if not cpv_code:
            return OperationResult(False, (FlashMessage("Το CPV είναι υποχρεωτικό.", "danger"),))

        if Cpv.query.filter_by(cpv=cpv_code).first():
            return OperationResult(False, (FlashMessage("Υπάρχει ήδη εγγραφή με αυτό το CPV.", "danger"),))

        obj = Cpv(cpv=cpv_code, description=description)
        db.session.add(obj)
        db.session.flush()
        log_action(entity=obj, action="CREATE", before=None, after=serialize_model(obj))
        db.session.commit()

        return OperationResult(True, (FlashMessage("Η εγγραφή CPV προστέθηκε.", "success"),), entity_id=obj.id)

    if action == "update":
        obj_id = parse_optional_int((form_data.get("id") or "").strip())
        if obj_id is None:
            return OperationResult(False, (FlashMessage("Μη έγκυρη εγγραφή.", "danger"),))

        obj = Cpv.query.get_or_404(obj_id)
        before = serialize_model(obj)

        cpv_code = (form_data.get("cpv") or "").strip()
        description = (form_data.get("description") or "").strip() or None

        if not cpv_code:
            return OperationResult(False, (FlashMessage("Το CPV είναι υποχρεωτικό.", "danger"),))

        exists = Cpv.query.filter(Cpv.cpv == cpv_code, Cpv.id != obj.id).first()
        if exists:
            return OperationResult(False, (FlashMessage("Υπάρχει ήδη άλλη εγγραφή με αυτό το CPV.", "danger"),))

        obj.cpv = cpv_code
        obj.description = description

        db.session.flush()
        log_action(entity=obj, action="UPDATE", before=before, after=serialize_model(obj))
        db.session.commit()

        return OperationResult(True, (FlashMessage("Η εγγραφή ενημερώθηκε.", "success"),), entity_id=obj.id)

    if action == "delete":
        obj_id = parse_optional_int((form_data.get("id") or "").strip())
        if obj_id is None:
            return OperationResult(False, (FlashMessage("Μη έγκυρη εγγραφή.", "danger"),))

        obj = Cpv.query.get_or_404(obj_id)
        before = serialize_model(obj)

        db.session.delete(obj)
        db.session.flush()
        log_action(entity=obj, action="DELETE", before=before, after=None)
        db.session.commit()

        return OperationResult(True, (FlashMessage("Η εγγραφή διαγράφηκε.", "success"),), entity_id=obj.id)

    return OperationResult(False, (FlashMessage("Μη έγκυρη ενέργεια.", "danger"),))


def execute_import_cpv(file_storage: Any) -> OperationResult:
    """
    Import CPV rows from an XLSX file.
    """
    file = file_storage
    if not file or not getattr(file, "filename", None):
        return OperationResult(False, (FlashMessage("Δεν επιλέχθηκε αρχείο.", "danger"),))

    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        return OperationResult(False, (FlashMessage("Επιτρέπεται μόνο αρχείο .xlsx", "danger"),))

    try:
        import openpyxl
        workbook = openpyxl.load_workbook(file, data_only=True)
        worksheet = workbook.active
    except Exception:
        return OperationResult(False, (FlashMessage("Αποτυχία ανάγνωσης Excel. Ελέγξτε το αρχείο.", "danger"),))

    try:
        header_cells = [cell.value for cell in next(worksheet.iter_rows(min_row=1, max_row=1))]
    except StopIteration:
        return OperationResult(False, (FlashMessage("Το Excel είναι κενό.", "danger"),))

    idx_map = build_header_index(header_cells)

    cpv_idx = idx_map.get("cpv")
    desc_idx = idx_map.get("περιγραφη", idx_map.get("description"))

    if cpv_idx is None:
        return OperationResult(False, (FlashMessage("Το Excel πρέπει να έχει στήλη 'CPV'.", "danger"),))

    inserted: list[Cpv] = []
    skipped_missing = 0
    skipped_duplicate = 0

    for row in worksheet.iter_rows(min_row=2, values_only=True):
        cpv_code = safe_cell_str(cell_at(row, cpv_idx))
        if not cpv_code:
            skipped_missing += 1
            continue

        if Cpv.query.filter_by(cpv=cpv_code).first():
            skipped_duplicate += 1
            continue

        obj = Cpv(
            cpv=cpv_code,
            description=safe_cell_str(cell_at(row, desc_idx)) or None,
        )
        db.session.add(obj)
        inserted.append(obj)

    if not inserted:
        return OperationResult(False, (FlashMessage("Δεν εισήχθησαν εγγραφές. Ελέγξτε required πεδία/διπλότυπα.", "warning"),))

    db.session.flush()
    for obj in inserted:
        log_action(entity=obj, action="CREATE", before=None, after=serialize_model(obj))
    db.session.commit()

    return OperationResult(
        True,
        (
            FlashMessage(
                f"Εισαγωγή ολοκληρώθηκε: {len(inserted)} νέες εγγραφές. "
                f"Παραλείφθηκαν: {skipped_missing} (ελλιπή), {skipped_duplicate} (διπλότυπα).",
                "success",
            ),
        ),
    )


# ----------------------------------------------------------------------
# OPTION VALUES
# ----------------------------------------------------------------------
def build_option_values_page_context(*, key: str, label: str) -> dict[str, Any]:
    """
    Build template context for one generic OptionValue category page.
    """
    category = _get_or_create_category(key=key, label=label)
    values = get_all_option_rows(category.key)
    return {
        "category": category,
        "values": values,
        "page_label": label,
    }


def execute_option_value_action(*, key: str, label: str, form_data: Mapping[str, object]) -> OperationResult:
    """
    Execute create/update/delete action for one OptionValue category page.
    """
    category = _get_or_create_category(key=key, label=label)
    action = (form_data.get("action") or "").strip()

    if action == "create":
        value = (form_data.get("value") or "").strip()
        sort_order = parse_optional_int((form_data.get("sort_order") or "").strip()) or 0
        is_active = bool(form_data.get("is_active") == "on")

        if not value:
            return OperationResult(False, (FlashMessage("Η τιμή είναι υποχρεωτική.", "danger"),))

        existing = OptionValue.query.filter_by(
            category_id=category.id,
            value=value
        ).first()

        if existing:
            return OperationResult(
                False,
                (FlashMessage("Η τιμή υπάρχει ήδη σε αυτή την κατηγορία.", "warning"),),
             entity_id=existing.id,
        )

        row = OptionValue(
            category_id=category.id,
         value=value,
            is_active=is_active,
            sort_order=sort_order,
        )

        try:
            db.session.add(row)
            db.session.flush()
            log_action(entity=row, action="CREATE", after=serialize_model(row))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return OperationResult(
                False,
                (FlashMessage("Η τιμή υπάρχει ήδη σε αυτή την κατηγορία.", "warning"),),
            )

        return OperationResult(
            True,
            (FlashMessage("Η τιμή προστέθηκε.", "success"),),
            entity_id=row.id,
        )

    if action == "update":
        option_value_id = parse_optional_int((form_data.get("id") or "").strip())
        if option_value_id is None:
            return OperationResult(False, (FlashMessage("Μη έγκυρη εγγραφή.", "danger"),))

        row = OptionValue.query.filter_by(id=option_value_id, category_id=category.id).first()
        if not row:
            return OperationResult(False, (FlashMessage("Η εγγραφή δεν βρέθηκε.", "danger"),), not_found=True)

        before = serialize_model(row)
        value = (form_data.get("value") or "").strip()
        sort_order = parse_optional_int((form_data.get("sort_order") or "").strip()) or 0
        is_active = bool(form_data.get("is_active") == "on")

        if not value:
            return OperationResult(False, (FlashMessage("Η τιμή είναι υποχρεωτική.", "danger"),))

        duplicate = (
            OptionValue.query.filter(
                OptionValue.category_id == category.id,
                OptionValue.value == value,
                OptionValue.id != row.id,
            ).first()
        )
        if duplicate:
            return OperationResult(
                False,
                (FlashMessage("Υπάρχει ήδη άλλη εγγραφή με αυτή την τιμή.", "warning"),),
                entity_id=row.id,
            )

        row.value = value
        row.sort_order = sort_order
        row.is_active = is_active

        try:
            db.session.flush()
            log_action(entity=row, action="UPDATE", before=before, after=serialize_model(row))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return OperationResult(
                False,
                (FlashMessage("Υπάρχει ήδη άλλη εγγραφή με αυτή την τιμή.", "warning"),),
                entity_id=row.id,
            )

        return OperationResult(
            True,
            (FlashMessage("Η τιμή ενημερώθηκε.", "success"),),
            entity_id=row.id,
        )

    if action == "delete":
        option_value_id = parse_optional_int((form_data.get("id") or "").strip())
        if option_value_id is None:
            return OperationResult(False, (FlashMessage("Μη έγκυρη εγγραφή.", "danger"),))

        row = OptionValue.query.filter_by(id=option_value_id, category_id=category.id).first()
        if not row:
            return OperationResult(False, (FlashMessage("Η εγγραφή δεν βρέθηκε.", "danger"),), not_found=True)

        before = serialize_model(row)

        try:
            db.session.delete(row)
            db.session.flush()
            log_action(entity=row, action="DELETE", before=before)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return OperationResult(
                False,
                (FlashMessage("Η τιμή δεν μπορεί να διαγραφεί γιατί χρησιμοποιείται ήδη.", "danger"),),
                entity_id=row.id,
            )

        return OperationResult(
            True,
            (FlashMessage("Η τιμή διαγράφηκε.", "success"),),
            entity_id=row.id,
        )

    return OperationResult(False, (FlashMessage("Μη έγκυρη ενέργεια.", "danger"),))


# ----------------------------------------------------------------------
# INCOME TAX RULES
# ----------------------------------------------------------------------
def build_income_tax_rules_page_context() -> dict[str, Any]:
    """
    Build template context for the IncomeTaxRule page.
    """
    rules = IncomeTaxRule.query.order_by(IncomeTaxRule.description.asc()).all()
    return {"rules": rules}


def execute_income_tax_rule_action(form_data: Mapping[str, object]) -> OperationResult:
    action = (form_data.get("action") or "").strip()

    if action == "create":
        description = (form_data.get("description") or "").strip()
        rate_percent = parse_decimal((form_data.get("rate_percent") or "").strip())
        threshold_amount = parse_decimal((form_data.get("threshold_amount") or "").strip())
        is_active = bool(form_data.get("is_active") == "on")

        if not description:
            return OperationResult(False, (FlashMessage("Η περιγραφή είναι υποχρεωτική.", "danger"),))

        existing = IncomeTaxRule.query.filter_by(description=description).first()
        if existing:
            return OperationResult(
                False,
                (FlashMessage("Υπάρχει ήδη κανόνας με αυτή την περιγραφή.", "warning"),),
                entity_id=existing.id,
            )

        row = IncomeTaxRule(
            description=description,
            rate_percent=rate_percent,
            threshold_amount=threshold_amount,
            is_active=is_active,
        )

        try:
            db.session.add(row)
            db.session.flush()
            log_action(entity=row, action="CREATE", after=serialize_model(row))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return OperationResult(
                False,
                (FlashMessage("Υπάρχει ήδη κανόνας με αυτή την περιγραφή.", "warning"),),
            )

        return OperationResult(
            True,
            (FlashMessage("Ο κανόνας φόρου εισοδήματος προστέθηκε.", "success"),),
            entity_id=row.id,
        )

    if action == "update":
        rule_id = parse_optional_int((form_data.get("id") or "").strip())
        if rule_id is None:
            return OperationResult(False, (FlashMessage("Μη έγκυρη εγγραφή.", "danger"),))

        row = IncomeTaxRule.query.get(rule_id)
        if not row:
            return OperationResult(False, (FlashMessage("Η εγγραφή δεν βρέθηκε.", "danger"),), not_found=True)

        description = (form_data.get("description") or "").strip()
        rate_percent = parse_decimal((form_data.get("rate_percent") or "").strip())
        threshold_amount = parse_decimal((form_data.get("threshold_amount") or "").strip())
        is_active = bool(form_data.get("is_active") == "on")

        if not description:
            return OperationResult(False, (FlashMessage("Η περιγραφή είναι υποχρεωτική.", "danger"),))

        duplicate = IncomeTaxRule.query.filter(
            IncomeTaxRule.description == description,
            IncomeTaxRule.id != row.id,
        ).first()
        if duplicate:
            return OperationResult(
                False,
                (FlashMessage("Υπάρχει ήδη άλλος κανόνας με αυτή την περιγραφή.", "warning"),),
                entity_id=row.id,
            )

        before = serialize_model(row)
        row.description = description
        row.rate_percent = rate_percent
        row.threshold_amount = threshold_amount
        row.is_active = is_active

        try:
            db.session.flush()
            log_action(entity=row, action="UPDATE", before=before, after=serialize_model(row))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return OperationResult(
                False,
                (FlashMessage("Υπάρχει ήδη άλλος κανόνας με αυτή την περιγραφή.", "warning"),),
                entity_id=row.id,
            )

        return OperationResult(
            True,
            (FlashMessage("Ο κανόνας φόρου εισοδήματος ενημερώθηκε.", "success"),),
            entity_id=row.id,
        )

    if action == "delete":
        rule_id = parse_optional_int((form_data.get("id") or "").strip())
        if rule_id is None:
            return OperationResult(False, (FlashMessage("Μη έγκυρη εγγραφή.", "danger"),))

        row = IncomeTaxRule.query.get(rule_id)
        if not row:
            return OperationResult(False, (FlashMessage("Η εγγραφή δεν βρέθηκε.", "danger"),), not_found=True)

        before = serialize_model(row)

        try:
            db.session.delete(row)
            db.session.flush()
            log_action(entity=row, action="DELETE", before=before)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return OperationResult(
                False,
                (FlashMessage("Ο κανόνας δεν μπορεί να διαγραφεί γιατί χρησιμοποιείται ήδη.", "danger"),),
                entity_id=row.id,
            )

        return OperationResult(
            True,
            (FlashMessage("Ο κανόνας φόρου εισοδήματος διαγράφηκε.", "success"),),
            entity_id=row.id,
        )

    return OperationResult(False, (FlashMessage("Μη έγκυρη ενέργεια.", "danger"),))

# ----------------------------------------------------------------------
# WITHHOLDING PROFILES
# ----------------------------------------------------------------------
def build_withholding_profiles_page_context() -> dict[str, Any]:
    """
    Build template context for the WithholdingProfile page.
    """
    profiles = WithholdingProfile.query.order_by(WithholdingProfile.description.asc()).all()
    return {"profiles": profiles}


def execute_withholding_profile_action(form_data: Mapping[str, object]) -> OperationResult:
    action = (form_data.get("action") or "").strip()

    if action == "create":
        description = (form_data.get("description") or "").strip()
        mt_eloa_percent = parse_decimal((form_data.get("mt_eloa_percent") or "").strip())
        eadhsy_percent = parse_decimal((form_data.get("eadhsy_percent") or "").strip())
        withholding1_percent = parse_decimal((form_data.get("withholding1_percent") or "").strip())
        withholding2_percent = parse_decimal((form_data.get("withholding2_percent") or "").strip())
        is_active = bool(form_data.get("is_active") == "on")

        if not description:
            return OperationResult(False, (FlashMessage("Η περιγραφή είναι υποχρεωτική.", "danger"),))

        existing = WithholdingProfile.query.filter_by(description=description).first()
        if existing:
            return OperationResult(
                False,
                (FlashMessage("Υπάρχει ήδη προφίλ με αυτή την περιγραφή.", "warning"),),
                entity_id=existing.id,
            )

        row = WithholdingProfile(
            description=description,
            mt_eloa_percent=mt_eloa_percent,
            eadhsy_percent=eadhsy_percent,
            withholding1_percent=withholding1_percent,
            withholding2_percent=withholding2_percent,
            is_active=is_active,
        )

        try:
            db.session.add(row)
            db.session.flush()
            log_action(entity=row, action="CREATE", after=serialize_model(row))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return OperationResult(
                False,
                (FlashMessage("Υπάρχει ήδη προφίλ με αυτή την περιγραφή.", "warning"),),
            )

        return OperationResult(
            True,
            (FlashMessage("Το προφίλ κρατήσεων προστέθηκε.", "success"),),
            entity_id=row.id,
        )

    if action == "update":
        profile_id = parse_optional_int((form_data.get("id") or "").strip())
        if profile_id is None:
            return OperationResult(False, (FlashMessage("Μη έγκυρη εγγραφή.", "danger"),))

        row = WithholdingProfile.query.get(profile_id)
        if not row:
            return OperationResult(False, (FlashMessage("Η εγγραφή δεν βρέθηκε.", "danger"),), not_found=True)

        description = (form_data.get("description") or "").strip()
        mt_eloa_percent = parse_decimal((form_data.get("mt_eloa_percent") or "").strip())
        eadhsy_percent = parse_decimal((form_data.get("eadhsy_percent") or "").strip())
        withholding1_percent = parse_decimal((form_data.get("withholding1_percent") or "").strip())
        withholding2_percent = parse_decimal((form_data.get("withholding2_percent") or "").strip())
        is_active = bool(form_data.get("is_active") == "on")

        if not description:
            return OperationResult(False, (FlashMessage("Η περιγραφή είναι υποχρεωτική.", "danger"),))

        duplicate = WithholdingProfile.query.filter(
            WithholdingProfile.description == description,
            WithholdingProfile.id != row.id,
        ).first()
        if duplicate:
            return OperationResult(
                False,
                (FlashMessage("Υπάρχει ήδη άλλο προφίλ με αυτή την περιγραφή.", "warning"),),
                entity_id=row.id,
            )

        before = serialize_model(row)
        row.description = description
        row.mt_eloa_percent = mt_eloa_percent
        row.eadhsy_percent = eadhsy_percent
        row.withholding1_percent = withholding1_percent
        row.withholding2_percent = withholding2_percent
        row.is_active = is_active

        try:
            db.session.flush()
            log_action(entity=row, action="UPDATE", before=before, after=serialize_model(row))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return OperationResult(
                False,
                (FlashMessage("Υπάρχει ήδη άλλο προφίλ με αυτή την περιγραφή.", "warning"),),
                entity_id=row.id,
            )

        return OperationResult(
            True,
            (FlashMessage("Το προφίλ κρατήσεων ενημερώθηκε.", "success"),),
            entity_id=row.id,
        )

    if action == "delete":
        profile_id = parse_optional_int((form_data.get("id") or "").strip())
        if profile_id is None:
            return OperationResult(False, (FlashMessage("Μη έγκυρη εγγραφή.", "danger"),))

        row = WithholdingProfile.query.get(profile_id)
        if not row:
            return OperationResult(False, (FlashMessage("Η εγγραφή δεν βρέθηκε.", "danger"),), not_found=True)

        before = serialize_model(row)

        try:
            db.session.delete(row)
            db.session.flush()
            log_action(entity=row, action="DELETE", before=before)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return OperationResult(
                False,
                (FlashMessage("Το προφίλ δεν μπορεί να διαγραφεί γιατί χρησιμοποιείται ήδη.", "danger"),),
                entity_id=row.id,
            )

        return OperationResult(
            True,
            (FlashMessage("Το προφίλ κρατήσεων διαγράφηκε.", "success"),),
            entity_id=row.id,
        )

    return OperationResult(False, (FlashMessage("Μη έγκυρη ενέργεια.", "danger"),))


__all__ = [
    "build_ale_kae_page_context",
    "execute_ale_kae_action",
    "execute_import_ale_kae",
    "build_cpv_page_context",
    "execute_cpv_action",
    "execute_import_cpv",
    "build_option_values_page_context",
    "execute_option_value_action",
    "build_income_tax_rules_page_context",
    "execute_income_tax_rule_action",
    "build_withholding_profiles_page_context",
    "execute_withholding_profile_action",
]


```

FILE: .\app\services\settings\service_units.py
```python
"""
app/services/settings/service_units.py

Focused page/use-case services for ServiceUnit settings routes.

PURPOSE
-------
Extract non-HTTP orchestration from:

- /settings/service-units
- /settings/service-units/roles
- /settings/service-units/new
- /settings/service-units/import
- /settings/service-units/<id>/edit-info
- /settings/service-units/<id>/edit
- /settings/service-units/<id>/delete

ARCHITECTURAL INTENT
--------------------
Routes remain responsible only for:
- decorators
- reading request.form / request.files
- boundary object loads
- flashing returned messages
- render / redirect responses

This module handles:
- page-context assembly
- validation orchestration
- persistence
- audit logging
- SQLite-safe ServiceUnit deletion

DESIGN
------
- function-first
- no unnecessary classes
- explicit validation branches
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import Personnel, Procurement, ProcurementCommittee, ServiceUnit, User
from ..shared.excel_imports import build_header_index, cell_at, safe_cell_str
from ..shared.operation_results import FlashMessage, OperationResult


VALID_COMMANDER_ROLE_TYPES = {"Διοικητής", "Κυβερνήτης"}


def _active_personnel_for_dropdown() -> list[Personnel]:
    """
    Return all active Personnel ordered for dropdown usage.

    This preserves the current route behavior for ServiceUnit role assignment:
    Manager / Deputy may be selected from all active personnel.
    """
    return (
        Personnel.query.filter_by(is_active=True)
        .order_by(Personnel.last_name.asc(), Personnel.first_name.asc())
        .all()
    )


def _normalize_nullable_text(value: Any) -> str | None:
    """
    Normalize any input to trimmed nullable text.

    Empty strings become None.
    Non-string values are converted to string and stripped.
    """
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _normalize_commander_role_type(value: Any) -> str | None:
    """
    Normalize the commander/governor role type.

    Allowed persisted values:
    - Διοικητής
    - Κυβερνήτης

    Empty input becomes None.

    Raises:
        ValueError: if a non-empty value is provided but is not valid.
    """
    normalized = _normalize_nullable_text(value)
    if normalized is None:
        return None

    if normalized not in VALID_COMMANDER_ROLE_TYPES:
        raise ValueError("Μη έγκυρος τύπος Διοικητή/Κυβερνήτη.")

    return normalized


def build_service_units_list_page_context() -> dict[str, Any]:
    """
    Build template context for the ServiceUnits list page.
    """
    units = ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()
    return {"units": units}


def build_service_units_roles_page_context() -> dict[str, Any]:
    """
    Build template context for the ServiceUnits role-assignment list page.
    """
    units = ServiceUnit.query.order_by(ServiceUnit.description.asc()).all()
    return {"units": units}


def build_service_unit_form_page_context(
    *,
    unit: ServiceUnit | None,
    form_title: str,
    is_create: bool,
) -> dict[str, Any]:
    """
    Build template context for create/edit ServiceUnit form pages.
    """
    return {
        "unit": unit,
        "form_title": form_title,
        "is_create": is_create,
        "commander_role_type_options": ("Διοικητής", "Κυβερνήτης"),
    }


def build_service_unit_roles_form_page_context(
    *,
    unit: ServiceUnit,
    form_title: str,
) -> dict[str, Any]:
    """
    Build template context for ServiceUnit Manager/Deputy assignment page.
    """
    return {
        "unit": unit,
        "personnel_list": _active_personnel_for_dropdown(),
        "form_title": form_title,
    }


def execute_create_service_unit(form_data: Mapping[str, Any]) -> OperationResult:
    """
    Validate and create a new ServiceUnit.
    """
    description = (form_data.get("description") or "").strip()
    code = (form_data.get("code") or "").strip()
    short_name = (form_data.get("short_name") or "").strip()
    aahit = (form_data.get("aahit") or "").strip()

    email = (form_data.get("email") or "").strip()
    address = (form_data.get("address") or "").strip()
    region = (form_data.get("region") or "").strip()
    prefecture = (form_data.get("prefecture") or "").strip()

    phone = (form_data.get("phone") or "").strip()

    commander = (form_data.get("commander") or "").strip()
    commander_role_type_raw = form_data.get("commander_role_type")

    application_administrator = (form_data.get("curator") or "").strip()
    application_admin_directory = (form_data.get("application_admin_directory") or "").strip()

    supply_officer = (form_data.get("supply_officer") or "").strip()

    if not description:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η περιγραφή Υπηρεσίας είναι υποχρεωτική.", "danger"),),
        )

    try:
        commander_role_type = _normalize_commander_role_type(commander_role_type_raw)
    except ValueError as exc:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage(str(exc), "danger"),),
        )

    if ServiceUnit.query.filter_by(description=description).first():
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Υπάρχει ήδη Υπηρεσία με αυτή την περιγραφή.", "danger"),),
        )

    if code and ServiceUnit.query.filter_by(code=code).first():
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Υπάρχει ήδη Υπηρεσία με αυτόν τον κωδικό.", "danger"),),
        )

    if short_name and ServiceUnit.query.filter_by(short_name=short_name).first():
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Υπάρχει ήδη Υπηρεσία με αυτή τη συντομογραφία.", "danger"),),
        )

    unit = ServiceUnit(
        description=description,
        code=code or None,
        short_name=short_name or None,
        aahit=aahit or None,
        email=email or None,
        address=address or None,
        region=region or None,
        prefecture=prefecture or None,
        phone=phone or None,
        commander=commander or None,
        commander_role_type=commander_role_type,
        curator=application_administrator or None,
        application_admin_directory=application_admin_directory or None,
        supply_officer=supply_officer or None,
        manager_personnel_id=None,
        deputy_personnel_id=None,
    )

    db.session.add(unit)
    db.session.flush()
    log_action(entity=unit, action="CREATE", before=None, after=serialize_model(unit))
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Η Υπηρεσία δημιουργήθηκε.", "success"),),
        entity_id=unit.id,
    )


def execute_edit_service_unit_info(
    unit: ServiceUnit,
    form_data: Mapping[str, Any],
) -> OperationResult:
    """
    Validate and update basic ServiceUnit information.
    """
    before = serialize_model(unit)

    description = (form_data.get("description") or "").strip()
    code = (form_data.get("code") or "").strip()
    short_name = (form_data.get("short_name") or "").strip()
    aahit = (form_data.get("aahit") or "").strip()

    email = (form_data.get("email") or "").strip()
    address = (form_data.get("address") or "").strip()
    region = (form_data.get("region") or "").strip()
    prefecture = (form_data.get("prefecture") or "").strip()

    phone = (form_data.get("phone") or "").strip()

    commander = (form_data.get("commander") or "").strip()
    commander_role_type_raw = form_data.get("commander_role_type")

    application_administrator = (form_data.get("curator") or "").strip()
    application_admin_directory = (form_data.get("application_admin_directory") or "").strip()

    supply_officer = (form_data.get("supply_officer") or "").strip()

    if not description:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η περιγραφή Υπηρεσίας είναι υποχρεωτική.", "danger"),),
        )

    try:
        commander_role_type = _normalize_commander_role_type(commander_role_type_raw)
    except ValueError as exc:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage(str(exc), "danger"),),
        )

    duplicate_desc = ServiceUnit.query.filter(
        ServiceUnit.description == description,
        ServiceUnit.id != unit.id,
    ).first()
    if duplicate_desc:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Υπάρχει ήδη άλλη Υπηρεσία με αυτή την περιγραφή.", "danger"),),
        )

    if code:
        duplicate_code = ServiceUnit.query.filter(
            ServiceUnit.code == code,
            ServiceUnit.id != unit.id,
        ).first()
        if duplicate_code:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Υπάρχει ήδη άλλη Υπηρεσία με αυτόν τον κωδικό.", "danger"),),
            )

    if short_name:
        duplicate_short_name = ServiceUnit.query.filter(
            ServiceUnit.short_name == short_name,
            ServiceUnit.id != unit.id,
        ).first()
        if duplicate_short_name:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Υπάρχει ήδη άλλη Υπηρεσία με αυτή τη συντομογραφία.", "danger"),),
            )

    unit.description = description
    unit.code = code or None
    unit.short_name = short_name or None
    unit.aahit = aahit or None

    unit.email = email or None
    unit.address = address or None
    unit.region = region or None
    unit.prefecture = prefecture or None

    unit.phone = phone or None

    unit.commander = commander or None
    unit.commander_role_type = commander_role_type

    # Business label: "Διαχειριστής Εφαρμογής"
    # Persisted storage: existing `curator` column retained intentionally.
    unit.curator = application_administrator or None
    unit.application_admin_directory = application_admin_directory or None

    unit.supply_officer = supply_officer or None

    db.session.flush()
    log_action(entity=unit, action="UPDATE", before=before, after=serialize_model(unit))
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Η Υπηρεσία ενημερώθηκε.", "success"),),
        entity_id=unit.id,
    )


def execute_assign_service_unit_roles(
    unit: ServiceUnit,
    form_data: Mapping[str, Any],
) -> OperationResult:
    before = serialize_model(unit)

    manager_personnel_id_raw = form_data.get("manager_personnel_id")
    deputy_personnel_id_raw = form_data.get("deputy_personnel_id")

    manager_personnel_id = None
    deputy_personnel_id = None

    if manager_personnel_id_raw:
        try:
            manager_personnel_id = int(manager_personnel_id_raw)
        except (TypeError, ValueError):
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρος Manager.", "danger"),),
            )

    if deputy_personnel_id_raw:
        try:
            deputy_personnel_id = int(deputy_personnel_id_raw)
        except (TypeError, ValueError):
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρος Deputy.", "danger"),),
            )

    if (
        manager_personnel_id is not None
        and deputy_personnel_id is not None
        and manager_personnel_id == deputy_personnel_id
    ):
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Δεν γίνεται ο Manager και ο Deputy να είναι το ίδιο πρόσωπο.", "danger"),),
        )

    if manager_personnel_id is not None:
        manager_person = Personnel.query.filter_by(
            id=manager_personnel_id,
            is_active=True,
        ).first()
        if not manager_person:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Ο επιλεγμένος Manager δεν είναι έγκυρο ενεργό προσωπικό.", "danger"),),
            )

        manager_used_elsewhere = ServiceUnit.query.filter(
            ServiceUnit.manager_personnel_id == manager_personnel_id,
            ServiceUnit.id != unit.id,
        ).first()
        if manager_used_elsewhere:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Το συγκεκριμένο προσωπικό είναι ήδη Manager σε άλλη Υπηρεσία.", "danger"),),
            )

    if deputy_personnel_id is not None:
        deputy_person = Personnel.query.filter_by(
            id=deputy_personnel_id,
            is_active=True,
        ).first()
        if not deputy_person:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Ο επιλεγμένος Deputy δεν είναι έγκυρο ενεργό προσωπικό.", "danger"),),
            )

        deputy_used_elsewhere = ServiceUnit.query.filter(
            ServiceUnit.deputy_personnel_id == deputy_personnel_id,
            ServiceUnit.id != unit.id,
        ).first()
        if deputy_used_elsewhere:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Το συγκεκριμένο προσωπικό είναι ήδη Deputy σε άλλη Υπηρεσία.", "danger"),),
            )

    unit.manager_personnel_id = manager_personnel_id
    unit.deputy_personnel_id = deputy_personnel_id

    db.session.flush()
    log_action(entity=unit, action="UPDATE", before=before, after=serialize_model(unit))
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Οι ρόλοι Υπηρεσίας ενημερώθηκαν.", "success"),),
        entity_id=unit.id,
    )


def execute_delete_service_unit(unit: ServiceUnit) -> OperationResult:
    """
    Delete a ServiceUnit using a defensive, SQLite-safe strategy.

    WHY THIS EXISTS
    ---------------
    In development with SQLite, cascades involving non-nullable relationships
    may behave less predictably than on PostgreSQL. To keep the project stable,
    we explicitly detach or delete related rows before deleting the ServiceUnit.

    DELETE STRATEGY
    ---------------
    1. Audit snapshot of the ServiceUnit
    2. Delete related ProcurementCommittee rows
    3. Clear nullable references from Personnel
    4. Clear manager/deputy references on User rows
    5. Clear manager/deputy references on the ServiceUnit itself
    6. Abort if Procurements still point to the ServiceUnit
    7. Delete the ServiceUnit

    IMPORTANT
    ---------
    The provided Personnel model contains only `service_unit_id` among the
    service-unit-scoped nullable references. Therefore we clear only that field
    here, avoiding references to non-existent columns.
    """
    before = serialize_model(unit)

    # Delete committees first, preserving audit logs.
    committees = ProcurementCommittee.query.filter_by(service_unit_id=unit.id).all()
    for committee in committees:
        committee_before = serialize_model(committee)
        db.session.delete(committee)
        db.session.flush()
        log_action(entity=committee, action="DELETE", before=committee_before, after=None)

    # Clear Personnel references that are nullable and scoped to this ServiceUnit.
    Personnel.query.filter_by(service_unit_id=unit.id).update(
        {"service_unit_id": None},
        synchronize_session=False,
    )

    # Clear user role pointers that may target this ServiceUnit.
    users = User.query.filter_by(service_unit_id=unit.id).all()
    for user in users:
        user.service_unit_id = None

    # Clear manager/deputy references on the unit itself before delete.
    unit.manager_personnel_id = None
    unit.deputy_personnel_id = None
    db.session.flush()

    # Defensive block: do not delete if Procurements still point to this ServiceUnit.
    procurements_exist = Procurement.query.filter_by(service_unit_id=unit.id).first() is not None
    if procurements_exist:
        db.session.rollback()
        return OperationResult(
            ok=False,
            flashes=(
                FlashMessage(
                    "Η Υπηρεσία δεν μπορεί να διαγραφεί γιατί υπάρχουν συνδεδεμένες προμήθειες.",
                    "danger",
                ),
            ),
        )

    db.session.delete(unit)
    db.session.flush()
    log_action(entity=unit, action="DELETE", before=before, after=None)
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Η Υπηρεσία διαγράφηκε.", "success"),),
    )


def execute_import_service_units(file_storage: Any) -> OperationResult:
    """
    Import ServiceUnits from an uploaded Excel file.

    ACCEPTED HEADERS
    ----------------
    Required:
    - Περιγραφή / description

    Optional:
    - Κωδικός / code
    - Συντομογραφία / short_name
    - ΑΑΗΤ / aahit

    - Email / email / e-mail / υπηρεσιακό email
    - Διεύθυνση / address
    - Περιοχή / region
    - Νομός / prefecture
    - Τηλέφωνο / phone

    - Διοικητής/Κυβερνήτης / commander
    - Διοικητής / commander
    - Κυβερνήτης / commander

    - Τύπος Διοικητή/Κυβερνήτη / commander_role_type
    - Τύπος Διοικητή - Κυβερνήτη / commander_role_type
    - commander role type

    - Διαχειριστής Εφαρμογής / curator
    - Επιμελητής / curator
      (retained for backward-compatible import support)

    - ΔΙΕΥΘΥΝΣΗ Διαχειριστή Εφαρμογής / application_admin_directory
    - Διεύθυνση Διαχειριστή Εφαρμογής / application_admin_directory
    - application_admin_directory

    - Υπόλογος Εφοδιασμού / supply_officer

    IMPORT POLICY
    -------------
    - Only .xlsx is accepted.
    - Description remains required.
    - Duplicate checks remain:
      description, code, short_name.
    - commander_role_type is validated if provided.
    """
    if not file_storage or not getattr(file_storage, "filename", None):
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Δεν επιλέχθηκε αρχείο.", "danger"),),
        )

    filename = str(file_storage.filename or "").lower()
    if not filename.endswith(".xlsx"):
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Επιτρέπεται μόνο αρχείο .xlsx", "danger"),),
        )

    try:
        import openpyxl

        workbook = openpyxl.load_workbook(file_storage, data_only=True)
        worksheet = workbook.active
    except Exception:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Αποτυχία ανάγνωσης Excel. Ελέγξτε το αρχείο.", "danger"),),
        )

    try:
        header_cells = [cell.value for cell in next(worksheet.iter_rows(min_row=1, max_row=1))]
    except StopIteration:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Το Excel είναι κενό.", "danger"),),
        )

    idx_map = build_header_index(header_cells)

    desc_idx = idx_map.get("περιγραφη", idx_map.get("description"))
    code_idx = idx_map.get("κωδικος", idx_map.get("code"))
    short_idx = idx_map.get("συντομογραφια", idx_map.get("short name", idx_map.get("short_name")))
    aahit_idx = idx_map.get("ααητ", idx_map.get("aahit"))

    email_idx = idx_map.get(
        "email",
        idx_map.get("e-mail", idx_map.get("υπηρεσιακο email", idx_map.get("υπηρεσιακο e-mail"))),
    )

    address_idx = idx_map.get("διευθυνση", idx_map.get("address"))
    region_idx = idx_map.get("περιοχη", idx_map.get("region"))
    prefecture_idx = idx_map.get("νομος", idx_map.get("prefecture"))

    phone_idx = idx_map.get("τηλεφωνο", idx_map.get("phone"))

    commander_idx = idx_map.get(
        "διοικητης/κυβερνητης",
        idx_map.get(
            "διοικητης",
            idx_map.get("κυβερνητης", idx_map.get("commander")),
        ),
    )

    commander_role_type_idx = idx_map.get(
        "τυπος διοικητη/κυβερνητη",
        idx_map.get(
            "τυπος διοικητη - κυβερνητη",
            idx_map.get(
                "τυπος διοικητη κυ-βερνητη",
                idx_map.get("commander_role_type", idx_map.get("commander role type")),
            ),
        ),
    )

    curator_idx = idx_map.get(
        "διαχειριστης εφαρμογης",
        idx_map.get("curator", idx_map.get("επιμελητης")),
    )

    application_admin_directory_idx = idx_map.get(
        "διευθυνση διαχειριστη εφαρμογης",
        idx_map.get(
            "διευθυνση διαχειριστη εφαρμογης",
            idx_map.get(
                "application_admin_directory",
                idx_map.get("διευθυνση διαχειριστη εφαρμογης"),
            ),
        ),
    )

    # Support also uppercase business-style heading "ΔΙΕΥΘΥΝΣΗ Διαχειριστή Εφαρμογής"
    if application_admin_directory_idx is None:
        application_admin_directory_idx = idx_map.get("διευθυνση διαχειριστη εφαρμογης")

    supply_officer_idx = idx_map.get("υπολογος εφοδιασμου", idx_map.get("supply_officer"))

    if desc_idx is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Το Excel πρέπει να έχει στήλη 'Περιγραφή' (ή 'description').", "danger"),),
        )

    inserted_units: list[ServiceUnit] = []
    skipped_missing = 0
    skipped_duplicate = 0
    skipped_invalid_role_type = 0

    for row in worksheet.iter_rows(min_row=2, values_only=True):
        description = safe_cell_str(cell_at(row, desc_idx))
        if not description:
            skipped_missing += 1
            continue

        code = safe_cell_str(cell_at(row, code_idx)) or None
        short_name = safe_cell_str(cell_at(row, short_idx)) or None

        duplicate_exists = ServiceUnit.query.filter_by(description=description).first() is not None

        if not duplicate_exists and code:
            duplicate_exists = ServiceUnit.query.filter_by(code=code).first() is not None

        if not duplicate_exists and short_name:
            duplicate_exists = ServiceUnit.query.filter_by(short_name=short_name).first() is not None

        if duplicate_exists:
            skipped_duplicate += 1
            continue

        commander_role_type_raw = safe_cell_str(cell_at(row, commander_role_type_idx)) or None
        try:
            commander_role_type = _normalize_commander_role_type(commander_role_type_raw)
        except ValueError:
            skipped_invalid_role_type += 1
            continue

        unit = ServiceUnit(
            description=description,
            code=code,
            short_name=short_name,
            aahit=safe_cell_str(cell_at(row, aahit_idx)) or None,
            email=safe_cell_str(cell_at(row, email_idx)) or None,
            address=safe_cell_str(cell_at(row, address_idx)) or None,
            region=safe_cell_str(cell_at(row, region_idx)) or None,
            prefecture=safe_cell_str(cell_at(row, prefecture_idx)) or None,
            phone=safe_cell_str(cell_at(row, phone_idx)) or None,
            commander=safe_cell_str(cell_at(row, commander_idx)) or None,
            commander_role_type=commander_role_type,
            curator=safe_cell_str(cell_at(row, curator_idx)) or None,
            application_admin_directory=safe_cell_str(cell_at(row, application_admin_directory_idx)) or None,
            supply_officer=safe_cell_str(cell_at(row, supply_officer_idx)) or None,
            manager_personnel_id=None,
            deputy_personnel_id=None,
        )
        db.session.add(unit)
        inserted_units.append(unit)

    if not inserted_units:
        details = []
        if skipped_missing:
            details.append(f"{skipped_missing} ελλιπείς")
        if skipped_duplicate:
            details.append(f"{skipped_duplicate} διπλότυπες")
        if skipped_invalid_role_type:
            details.append(f"{skipped_invalid_role_type} με μη έγκυρο τύπο Διοικητή/Κυβερνήτη")

        details_text = ", ".join(details) if details else "χωρίς έγκυρες εγγραφές"
        return OperationResult(
            ok=False,
            flashes=(FlashMessage(f"Δεν εισήχθησαν εγγραφές. Έλεγχος αρχείου: {details_text}.", "warning"),),
        )

    db.session.flush()
    for unit in inserted_units:
        log_action(entity=unit, action="CREATE", before=None, after=serialize_model(unit))
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(
            FlashMessage(
                f"Εισαγωγή ολοκληρώθηκε: {len(inserted_units)} νέες Υπηρεσίες. "
                f"Παραλείφθηκαν: {skipped_missing} (ελλιπή), "
                f"{skipped_duplicate} (διπλότυπα), "
                f"{skipped_invalid_role_type} (μη έγκυρος τύπος Διοικητή/Κυβερνήτη).",
                "success",
            ),
        ),
    )

```

FILE: .\app\services\settings\suppliers.py
```python
"""
app/services/settings/suppliers.py

Focused page/use-case services for Supplier settings routes.

PURPOSE
-------
Extract non-HTTP orchestration from:

- /settings/suppliers
- /settings/suppliers/new
- /settings/suppliers/<id>/edit
- /settings/suppliers/<id>/delete
- /settings/suppliers/import

DESIGN
------
- function-first
- explicit validation paths
- routes stay thin
"""

from __future__ import annotations

from collections.abc import Mapping
from sqlite3 import IntegrityError
from typing import Any

from app.models.procurement import ProcurementSupplier

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import Supplier
from ..shared.excel_imports import build_header_index, cell_at, normalize_header, safe_cell_str
from ..shared.operation_results import FlashMessage, OperationResult


def build_suppliers_list_page_context() -> dict[str, Any]:
    """
    Build template context for the suppliers list page.
    """
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    return {"suppliers": suppliers}


def build_supplier_form_page_context(
    *,
    supplier: Supplier | None,
    form_title: str,
) -> dict[str, Any]:
    """
    Build template context for supplier create/edit form pages.
    """
    return {
        "supplier": supplier,
        "form_title": form_title,
    }


def execute_create_supplier(form_data: Mapping[str, Any]) -> OperationResult:
    """
    Validate and create a Supplier.
    """
    afm = (form_data.get("afm") or "").strip()
    name = (form_data.get("name") or "").strip()
    doy = (form_data.get("doy") or "").strip()
    phone = (form_data.get("phone") or "").strip()
    email = (form_data.get("email") or "").strip()
    emba = (form_data.get("emba") or "").strip()
    address = (form_data.get("address") or "").strip()
    city = (form_data.get("city") or "").strip()
    postal_code = (form_data.get("postal_code") or "").strip()
    country = (form_data.get("country") or "").strip()
    bank_name = (form_data.get("bank_name") or "").strip()
    iban = (form_data.get("iban") or "").strip()

    if not afm or len(afm) != 9 or not afm.isdigit():
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Το ΑΦΜ πρέπει να είναι 9 ψηφία.", "danger"),),
        )

    if not name:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η επωνυμία είναι υποχρεωτική.", "danger"),),
        )

    if Supplier.query.filter_by(afm=afm).first():
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Υπάρχει ήδη προμηθευτής με αυτό το ΑΦΜ.", "danger"),),
        )

    supplier = Supplier(
        afm=afm,
        name=name,
        doy=doy or None,
        phone=phone or None,
        email=email or None,
        emba=emba or None,
        address=address or None,
        city=city or None,
        postal_code=postal_code or None,
        country=country or None,
        bank_name=bank_name or None,
        iban=iban or None,
    )

    db.session.add(supplier)
    db.session.flush()
    log_action(entity=supplier, action="CREATE", before=None, after=serialize_model(supplier))
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Ο προμηθευτής δημιουργήθηκε.", "success"),),
        entity_id=supplier.id,
    )


def execute_edit_supplier(
    supplier: Supplier,
    form_data: Mapping[str, Any],
) -> OperationResult:
    """
    Validate and update a Supplier.
    """
    before = serialize_model(supplier)

    afm = (form_data.get("afm") or "").strip()
    name = (form_data.get("name") or "").strip()
    doy = (form_data.get("doy") or "").strip()
    phone = (form_data.get("phone") or "").strip()
    email = (form_data.get("email") or "").strip()
    emba = (form_data.get("emba") or "").strip()
    address = (form_data.get("address") or "").strip()
    city = (form_data.get("city") or "").strip()
    postal_code = (form_data.get("postal_code") or "").strip()
    country = (form_data.get("country") or "").strip()
    bank_name = (form_data.get("bank_name") or "").strip()
    iban = (form_data.get("iban") or "").strip()

    if not afm or len(afm) != 9 or not afm.isdigit():
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Το ΑΦΜ πρέπει να είναι 9 ψηφία.", "danger"),),
        )

    if not name:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η επωνυμία είναι υποχρεωτική.", "danger"),),
        )

    existing_afm = Supplier.query.filter(
        Supplier.afm == afm,
        Supplier.id != supplier.id,
    ).first()
    if existing_afm:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Υπάρχει ήδη άλλος προμηθευτής με αυτό το ΑΦΜ.", "danger"),),
        )

    supplier.afm = afm
    supplier.name = name
    supplier.doy = doy or None
    supplier.phone = phone or None
    supplier.email = email or None
    supplier.emba = emba or None
    supplier.address = address or None
    supplier.city = city or None
    supplier.postal_code = postal_code or None
    supplier.country = country or None
    supplier.bank_name = bank_name or None
    supplier.iban = iban or None

    db.session.flush()
    log_action(entity=supplier, action="UPDATE", before=before, after=serialize_model(supplier))
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Ο προμηθευτής ενημερώθηκε.", "success"),),
        entity_id=supplier.id,
    )


def execute_delete_supplier(supplier: Supplier) -> OperationResult:
    before = serialize_model(supplier)

    linked_row = ProcurementSupplier.query.filter_by(supplier_id=supplier.id).first()
    if linked_row:
        return OperationResult(
            ok=False,
            flashes=(
                FlashMessage(
                    "Ο προμηθευτής δεν μπορεί να διαγραφεί γιατί χρησιμοποιείται ήδη σε προμήθειες.",
                    "danger",
                ),
            ),
        )

    try:
        db.session.delete(supplier)
        db.session.flush()
        log_action(entity=supplier, action="DELETE", before=before, after=None)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return OperationResult(
            ok=False,
            flashes=(
                FlashMessage(
                    "Ο προμηθευτής δεν μπορεί να διαγραφεί γιατί χρησιμοποιείται ήδη σε προμήθειες.",
                    "danger",
                ),
            ),
        )

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Ο προμηθευτής διαγράφηκε.", "success"),),
    )


def execute_import_suppliers(file_storage: Any) -> OperationResult:
    """
    Import Suppliers from an uploaded Excel file.
    """
    if not file_storage or not getattr(file_storage, "filename", None):
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Δεν επιλέχθηκε αρχείο.", "danger"),),
        )

    filename = str(file_storage.filename or "").lower()
    if not filename.endswith(".xlsx"):
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Επιτρέπεται μόνο αρχείο .xlsx", "danger"),),
        )

    try:
        import openpyxl

        workbook = openpyxl.load_workbook(file_storage, data_only=True)
        worksheet = workbook.active
    except Exception:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Αποτυχία ανάγνωσης Excel. Ελέγξτε το αρχείο.", "danger"),),
        )

    try:
        header_cells = [c.value for c in next(worksheet.iter_rows(min_row=1, max_row=1))]
    except StopIteration:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Το Excel είναι κενό.", "danger"),),
        )

    def _norm(header_value: str | None) -> str:
        return normalize_header(header_value).replace(".", "")

    headers = [str(h).strip() if h is not None else "" for h in header_cells]
    idx_map = {_norm(h): i for i, h in enumerate(headers) if _norm(h)}

    afm_idx = idx_map.get("αφμ", idx_map.get("afm"))
    name_idx = idx_map.get("επωνυμια", idx_map.get("name", idx_map.get("ονομασια")))
    doy_idx = idx_map.get("δου", idx_map.get("doy", idx_map.get("δοy", idx_map.get("δοϋ"))))
    phone_idx = idx_map.get("τηλεφωνο", idx_map.get("phone", idx_map.get("tel")))
    email_idx = idx_map.get("email")
    emba_idx = idx_map.get("εμπα", idx_map.get("emba"))
    addr_idx = idx_map.get("διευθυνση", idx_map.get("address"))
    city_idx = idx_map.get("τοπος", idx_map.get("city"))
    pc_idx = idx_map.get("τκ", idx_map.get("tk", idx_map.get("postal_code")))
    country_idx = idx_map.get("χωρα", idx_map.get("country"))
    bank_idx = idx_map.get("τραπεζα", idx_map.get("bank_name"))
    iban_idx = idx_map.get("iban")

    if afm_idx is None or name_idx is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Το Excel πρέπει να έχει στήλες 'ΑΦΜ' και 'ΕΠΩΝΥΜΙΑ' (ή 'name').", "danger"),),
        )

    inserted: list[Supplier] = []
    skipped_missing = 0
    skipped_invalid_afm = 0
    skipped_duplicate = 0

    for row in worksheet.iter_rows(min_row=2, values_only=True):
        afm_raw = safe_cell_str(cell_at(row, afm_idx))
        name_raw = safe_cell_str(cell_at(row, name_idx))

        if not afm_raw or not name_raw:
            skipped_missing += 1
            continue

        afm = "".join(ch for ch in afm_raw if ch.isdigit())
        if len(afm) != 9:
            skipped_invalid_afm += 1
            continue

        if Supplier.query.filter_by(afm=afm).first():
            skipped_duplicate += 1
            continue

        supplier = Supplier(
            afm=afm,
            name=name_raw,
            doy=safe_cell_str(cell_at(row, doy_idx)) or None,
            phone=safe_cell_str(cell_at(row, phone_idx)) or None,
            email=safe_cell_str(cell_at(row, email_idx)) or None,
            emba=safe_cell_str(cell_at(row, emba_idx)) or None,
            address=safe_cell_str(cell_at(row, addr_idx)) or None,
            city=safe_cell_str(cell_at(row, city_idx)) or None,
            postal_code=safe_cell_str(cell_at(row, pc_idx)) or None,
            country=safe_cell_str(cell_at(row, country_idx)) or None,
            bank_name=safe_cell_str(cell_at(row, bank_idx)) or None,
            iban=safe_cell_str(cell_at(row, iban_idx)) or None,
        )
        db.session.add(supplier)
        inserted.append(supplier)

    if not inserted:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Δεν εισήχθησαν εγγραφές. Ελέγξτε required πεδία/διπλότυπα/ΑΦΜ.", "warning"),),
        )

    db.session.flush()
    for supplier in inserted:
        log_action(entity=supplier, action="CREATE", before=None, after=serialize_model(supplier))
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(
            FlashMessage(
                f"Εισαγωγή ολοκληρώθηκε: {len(inserted)} νέοι προμηθευτές. "
                f"Παραλείφθηκαν: {skipped_missing} (ελλιπή), "
                f"{skipped_invalid_afm} (μη έγκυρο ΑΦΜ), "
                f"{skipped_duplicate} (διπλότυπα).",
                "success",
            ),
        ),
    )


```

FILE: .\app\services\settings\theme.py
```python
"""
app/services/settings/theme.py

Theme settings page/use-case helpers.

PURPOSE
-------
This module extracts the non-HTTP theme selection logic from
`app/blueprints/settings/routes.py`.

CURRENT ROUTES SUPPORTED
------------------------
- /settings/theme

ARCHITECTURAL INTENT
--------------------
The route should remain responsible only for:
- decorators
- reading request.form
- flashing returned messages
- redirect / render decisions

This module is responsible for:
- publishing supported theme metadata for the page
- validating submitted theme selection
- applying the selected theme to the current user
- committing the change

DESIGN CHOICE
-------------
A small function-first module is sufficient here.
No class abstraction is justified for a single, simple settings use-case.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...extensions import db
from ..shared.operation_results import FlashMessage, OperationResult

THEME_CHOICES: dict[str, tuple[str, str]] = {
    "default": ("Προεπιλογή", "Φωτεινό θέμα με ουδέτερα χρώματα."),
    "dark": ("Σκούρο", "Σκούρο θέμα κατάλληλο για χαμηλό φωτισμό."),
    "ocean": ("Ocean", "Απαλό μπλε θέμα."),
}


def build_theme_page_context() -> dict[str, Any]:
    """
    Build template context for the theme settings page.

    RETURNS
    -------
    dict[str, Any]
        Template context with the supported theme choices.
    """
    return {
        "themes": THEME_CHOICES,
    }


def execute_theme_update(user: Any, form_data: Mapping[str, object]) -> OperationResult:
    """
    Validate and persist a user's theme selection.

    PARAMETERS
    ----------
    user:
        The authenticated User ORM entity.
    form_data:
        Submitted form payload.

    RETURNS
    -------
    OperationResult
        Generic service-layer result for route flashing/redirecting.
    """
    selected = form_data.get("theme")
    if selected not in THEME_CHOICES:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο θέμα.", "danger"),),
        )

    user.theme = str(selected)
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Το θέμα ενημερώθηκε.", "success"),),
    )


__all__ = [
    "THEME_CHOICES",
    "build_theme_page_context",
    "execute_theme_update",
]


```

FILE: .\app\services\settings_committees_service.py
```python
"""
app/services/settings_committees_service.py

Settings committees service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.settings.committees`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.settings.committees import *  # noqa: F401,F403

```

FILE: .\app\services\settings_feedback_service.py
```python
"""
app/services/settings_feedback_service.py

Settings feedback service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.settings.feedback`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.settings.feedback import *  # noqa: F401,F403

```

FILE: .\app\services\settings_master_data_admin_service.py
```python
"""
app/services/settings_master_data_admin_service.py

Settings master-data admin service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.settings.master_data_admin`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.settings.master_data_admin import *  # noqa: F401,F403

```

FILE: .\app\services\settings_service_units_service.py
```python
"""
app/services/settings_service_units_service.py

Settings service-units service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.settings.service_units`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.settings.service_units import *  # noqa: F401,F403

```

FILE: .\app\services\settings_suppliers_service.py
```python
"""
app/services/settings_suppliers_service.py

Settings suppliers service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.settings.suppliers`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.settings.suppliers import *  # noqa: F401,F403

```

FILE: .\app\services\settings_theme_service.py
```python
"""
app/services/settings_theme_service.py

Settings theme service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.settings.theme`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.settings.theme import *  # noqa: F401,F403

```

FILE: .\app\services\shared\__init__.py
```python
"""
app/services/shared/__init__.py

Shared service helper package.

This package contains low-level helpers and result types shared by multiple
service domains.
"""

from __future__ import annotations

```

FILE: .\app\services\shared\excel_imports.py
```python
"""
app/services/shared/excel_imports.py

Low-level reusable helpers for Excel import routes.

PURPOSE
-------
This module centralizes small, repeated helper logic used by many Excel-import
routes across the application.

Typical repeated patterns in the project included:
- normalizing Excel headers
- building a normalized header -> column index map
- converting cell values safely to trimmed strings
- safely retrieving a cell by index from a values_only row tuple

These patterns appear in multiple places, including:
- personnel import
- service unit import
- supplier import
- ALE–KAE import
- CPV import
- organizational structure import

WHY THIS MODULE EXISTS
----------------------
Excel import code is usually already long because it must handle:
- uploaded file validation
- workbook parsing
- header matching
- row validation
- duplicate handling
- audit logging
- summary messages

If every route also redefines the same low-level helpers, those routes become
much harder to read and maintain.

This module extracts the repeated low-level pieces so that route code stays
focused on:
- business validation
- import decisions
- persistence and feedback

ARCHITECTURAL DECISION
----------------------
For this file the correct decision is:

    stabilize, not decompose

Why:
- it already has one clean responsibility
- it has no database dependency
- it contains no business/domain orchestration
- it is already the right abstraction level for shared Excel import support

DESIGN GOALS
------------
- very defensive
- easy to reuse
- works with openpyxl `values_only=True` rows
- consistent normalization logic across imports
- no database dependency
- stable API for route consumers

FUNCTIONS PROVIDED
------------------
- normalize_header(text)
- safe_cell_str(value)
- build_header_index(header_cells)
- cell_at(row_values, index)

COMMON IMPORT PATTERN
---------------------
Typical route usage looks like this:

    header_cells = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx_map = build_header_index(header_cells)

    afm_idx = idx_map.get("αφμ", idx_map.get("afm"))

    for row in ws.iter_rows(min_row=2, values_only=True):
        afm = safe_cell_str(cell_at(row, afm_idx))

DEPENDENCIES
------------
- standard library only
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from typing import Any


def normalize_header(text: str | None) -> str:
    """
    Normalize an Excel header label for resilient matching.

    PARAMETERS
    ----------
    text:
        Raw header cell value.

    RETURNS
    -------
    str
        A normalized string suitable for matching header aliases.

    NORMALIZATION RULES
    -------------------
    1. Convert to string
    2. Trim leading/trailing whitespace
    3. Lowercase
    4. Collapse repeated internal spaces
    5. Remove accents / diacritics

    EXAMPLES
    --------
    normalize_header(" Περιγραφή ")        -> "περιγραφη"
    normalize_header("Διευθυντής_ΑΓΜ")     -> "διευθυντης_αγμ"
    normalize_header("First Name")         -> "first name"
    normalize_header(None)                 -> ""

    WHY DIACRITIC REMOVAL MATTERS
    -----------------------------
    In manually prepared Greek Excel files, headers may appear with or without
    accent marks. For example:
    - Περιγραφή
    - Περιγραφη

    Normalizing both to the same representation makes imports more tolerant.

    IMPORTANT
    ---------
    This helper intentionally does NOT:
    - replace underscores with spaces
    - remove punctuation broadly
    - perform fuzzy matching

    Alias handling remains the responsibility of the calling route/service,
    which should explicitly check accepted header variants.
    """
    if text is None:
        return ""

    normalized = " ".join(str(text).strip().lower().split())
    normalized = "".join(
        ch
        for ch in unicodedata.normalize("NFD", normalized)
        if unicodedata.category(ch) != "Mn"
    )
    return normalized


def safe_cell_str(value: Any) -> str:
    """
    Convert an Excel cell value to a safe trimmed string.

    PARAMETERS
    ----------
    value:
        Any cell value returned from openpyxl, commonly:
        - None
        - str
        - int
        - float
        - datetime
        - Decimal-like values

    RETURNS
    -------
    str
        - empty string for None
        - trimmed string representation otherwise

    EXAMPLES
    --------
    safe_cell_str(None)        -> ""
    safe_cell_str(" test ")    -> "test"
    safe_cell_str(123)         -> "123"

    WHY THIS HELPER EXISTS
    ----------------------
    Excel import rows often contain mixed types. Route code typically wants
    a simple "safe user-like text representation" before applying business
    validation.

    IMPORTANT
    ---------
    This helper does not try to preserve Excel formatting semantics.
    For example:
    - dates remain whatever string Python/openpyxl yields
    - floats are stringified as Python values
    - locale-aware formatting is intentionally out of scope

    Domain-specific parsing belongs to higher-level services/routes.
    """
    if value is None:
        return ""
    return str(value).strip()


def build_header_index(header_cells: list[Any]) -> dict[str, int]:
    """
    Build a normalized header -> column index map.

    PARAMETERS
    ----------
    header_cells:
        A list of raw header cell values from the first worksheet row.

    RETURNS
    -------
    dict[str, int]
        Mapping from normalized header names to zero-based column indexes.

    EXAMPLE
    -------
    Given headers:
        ["ΑΦΜ", "ΕΠΩΝΥΜΙΑ", "Δ.Ο.Υ."]

    the result becomes approximately:
        {
            "αφμ": 0,
            "επωνυμια": 1,
            "δ.ο.υ.": 2,
        }

    DUPLICATE HEADER POLICY
    -----------------------
    If the same normalized header appears more than once, the FIRST occurrence
    wins and later duplicates are ignored.

    WHY THIS POLICY
    ---------------
    Import routes typically expect one canonical column per semantic field.
    Silently preferring the first occurrence keeps behavior deterministic and
    avoids accidental remapping by later duplicate columns.

    IMPORTANT
    ---------
    This function does not validate that required headers exist.
    Required-header validation belongs to the caller.
    """
    index_map: dict[str, int] = {}

    for idx, raw in enumerate(header_cells):
        normalized = normalize_header(raw)
        if normalized and normalized not in index_map:
            index_map[normalized] = idx

    return index_map


def cell_at(row_values: Sequence[Any] | None, index: int | None) -> Any | None:
    """
    Safely retrieve a cell value from a values_only row sequence.

    PARAMETERS
    ----------
    row_values:
        Usually the tuple returned by:
            worksheet.iter_rows(..., values_only=True)
        but any indexable sequence is accepted.
    index:
        Zero-based column index, or None.

    RETURNS
    -------
    Any | None
        - the cell value when index is valid
        - None when the row is missing, index is None, negative, or out of range

    EXAMPLES
    --------
    row = ("123", "ACME", None)

    cell_at(row, 0)    -> "123"
    cell_at(row, 2)    -> None
    cell_at(row, 5)    -> None
    cell_at(row, None) -> None

    WHY THIS HELPER EXISTS
    ----------------------
    Import routes frequently access optional columns whose indexes may be:
    - missing because the header was absent
    - outside the row bounds
    - intentionally unset

    This helper avoids repeated defensive index checks across routes.
    """
    if row_values is None or index is None:
        return None

    if index < 0:
        return None

    if index >= len(row_values):
        return None

    return row_values[index]


__all__ = [
    "normalize_header",
    "safe_cell_str",
    "build_header_index",
    "cell_at",
]


```

FILE: .\app\services\shared\operation_results.py
```python
"""
app/services/shared/operation_results.py

Shared lightweight result objects for service-layer orchestration.

PURPOSE
-------
This module centralizes a few small structured return types used by multiple
service modules.

WHY THIS FILE EXISTS
--------------------
The current procurement refactor introduces several service-layer functions that
need to return:
- success/failure state
- flash-style user messages
- optional identifiers
- optional "not found" semantics

Keeping these tiny dataclasses in one place avoids repetition without
introducing heavy abstraction.

ARCHITECTURAL INTENT
--------------------
This module is intentionally conservative:
- plain dataclasses
- no inheritance trees
- no result monads
- no framework-specific behavior

These are simple transport objects between service layer and routes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FlashMessage:
    """
    Structured flash-style message returned from service-layer execution.
    """

    message: str
    category: str


@dataclass(frozen=True)
class OperationResult:
    """
    Generic service-layer result with one or more flash-style messages.

    FIELDS
    ------
    ok:
        Whether the operation succeeded.
    flashes:
        Flash-style messages for the route to emit.
    entity_id:
        Optional created/target entity id, when useful to the caller.
    not_found:
        Optional flag for routes that should translate the outcome to 404.
    """

    ok: bool
    flashes: tuple[FlashMessage, ...]
    entity_id: int | None = None
    not_found: bool = False


```

FILE: .\app\services\shared\parsing.py
```python
"""
app/services/shared/parsing.py

Shared parsing and safe-navigation helpers for the application.

PURPOSE
-------
This module centralizes small, repeated parsing utilities that previously
appeared across many route files.

Typical duplicated examples in the project were:
- parse optional integer ids from forms / query strings
- parse Decimal values that may use comma or dot
- parse optional HTML date input values
- normalize digit-only values (AFM / VAT-like filters)
- safely resolve the "next" redirect target

WHY THIS MODULE EXISTS
----------------------
Without a shared parsing module, route files tend to accumulate many small
helpers such as:

    _parse_optional_int(...)
    _parse_decimal(...)
    _parse_optional_date(...)
    _safe_next_url(...)
    _get_next_from_request(...)

Those helpers are easy to duplicate, but duplication causes problems:
- inconsistent behavior between blueprints
- slightly different validation rules
- harder maintenance
- more noise inside route files

This module provides a single canonical implementation for those concerns.

SECURITY NOTES
--------------
The application follows the rule:

    UI is never trusted.

That means parsing is not just about convenience; it is part of defensive
server-side validation.

Especially for redirect targets:
- never trust arbitrary "next" URLs from user input
- only allow local, relative application paths
- reject external redirects

FUNCTIONS PROVIDED
------------------
- parse_optional_int(value)
- parse_decimal(value)
- parse_optional_date(value)
- normalize_digits(value)
- safe_next_url(raw_next, fallback_endpoint)
- next_from_request(fallback_endpoint)

DEPENDENCIES
------------
- Standard library only, except:
  - flask.request / flask.url_for for redirect helpers
"""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from flask import request, url_for


def parse_optional_int(value: str | None) -> int | None:
    """
    Parse an optional integer value.

    PARAMETERS
    ----------
    value:
        A string-like value from form/query input, or None.

    RETURNS
    -------
    int | None
        - Returns int(value) when the input is a valid integer string.
        - Returns None when:
            * the input is None
            * the input is empty/whitespace
            * the input is invalid

    EXAMPLES
    --------
    parse_optional_int("15")      -> 15
    parse_optional_int(" 15 ")    -> 15
    parse_optional_int("")        -> None
    parse_optional_int(None)      -> None
    parse_optional_int("abc")     -> None

    WHY THIS HELPER EXISTS
    ----------------------
    Many route handlers receive optional foreign-key ids from forms and query
    strings. Repeating this logic everywhere creates noise and inconsistency.

    DESIGN DECISION
    ---------------
    Invalid input returns None instead of raising ValueError because route
    handlers usually want to respond with a user-facing flash message instead
    of crashing the request.
    """
    if value is None:
        return None

    raw = str(value).strip()
    if raw == "":
        return None

    try:
        return int(raw)
    except ValueError:
        return None


def parse_decimal(value: str | None) -> Decimal | None:
    """
    Parse a Decimal from user input.

    PARAMETERS
    ----------
    value:
        String-like numeric input from form/query values.

    RETURNS
    -------
    Decimal | None
        - Returns Decimal for valid numeric input
        - Returns None for empty or invalid input

    SUPPORTED INPUT STYLES
    ----------------------
    Both dot and comma decimals are supported:

    - "12.50" -> Decimal("12.50")
    - "12,50" -> Decimal("12.50")

    EXAMPLES
    --------
    parse_decimal("10")      -> Decimal("10")
    parse_decimal("10.25")   -> Decimal("10.25")
    parse_decimal("10,25")   -> Decimal("10.25")
    parse_decimal("")        -> None
    parse_decimal("abc")     -> None

    WHY THIS HELPER EXISTS
    ----------------------
    Greek / European users often type decimal numbers with commas. Supporting
    both comma and dot avoids unnecessary input friction while keeping the
    stored type consistent.

    DESIGN DECISION
    ---------------
    Invalid numeric input returns None so the caller can decide:
    - whether None is acceptable
    - whether to flash an error message
    - whether to fall back to a default value
    """
    if value is None:
        return None

    raw = str(value).strip().replace(",", ".")
    if raw == "":
        return None

    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def parse_optional_date(value: str | None) -> date | None:
    """
    Parse an optional HTML date input string (YYYY-MM-DD).

    PARAMETERS
    ----------
    value:
        String-like date value, usually from an <input type="date"> field.

    RETURNS
    -------
    date | None
        A Python date instance for valid input, otherwise None.

    EXPECTED FORMAT
    ---------------
    HTML date inputs usually submit values as:

        YYYY-MM-DD

    EXAMPLES
    --------
    parse_optional_date("2025-01-10") -> date(2025, 1, 10)
    parse_optional_date("")           -> None
    parse_optional_date(None)         -> None
    parse_optional_date("10/01/2025") -> None

    WHY THIS HELPER EXISTS
    ----------------------
    Many procurement forms contain optional date fields:
    - invoice_date
    - materials_receipt_date
    - invoice_receipt_date

    The route layer typically needs "safe optional parsing" rather than
    exception-driven parsing.
    """
    if value is None:
        return None

    raw = str(value).strip()
    if raw == "":
        return None

    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def normalize_digits(value: str | None) -> str:
    """
    Keep only numeric digits from a value.

    PARAMETERS
    ----------
    value:
        Any string-like value that may contain formatting characters.

    RETURNS
    -------
    str
        A string containing only digit characters.

    EXAMPLES
    --------
    normalize_digits("094-123-456") -> "094123456"
    normalize_digits(" 12 34 ")     -> "1234"
    normalize_digits(None)          -> ""

    COMMON USE CASES
    ----------------
    - AFM filtering
    - phone / number cleanup
    - VAT-like filter normalization

    WHY THIS HELPER EXISTS
    ----------------------
    Filters often need a loose, user-friendly search. Users may type separators,
    spaces, or punctuation. Normalizing to digits makes comparisons easier.
    """
    if not value:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def safe_next_url(raw_next: str | None, fallback_endpoint: str) -> str:
    """
    Safely resolve a user-provided "next" URL.

    PARAMETERS
    ----------
    raw_next:
        The raw "next" value from query string or form data.
    fallback_endpoint:
        Flask endpoint name used when raw_next is missing or unsafe.

    RETURNS
    -------
    str
        A safe local URL:
        - returns raw_next only if it is a relative local path
        - otherwise returns url_for(fallback_endpoint)

    SECURITY RULES
    --------------
    This helper intentionally rejects:
    - absolute URLs with scheme, e.g. https://example.com/...
    - URLs with netloc/domain
    - non-path values not starting with "/"

    WHY THIS HELPER EXISTS
    ----------------------
    Redirecting to unvalidated "next" parameters can create open redirect
    vulnerabilities.

    SAFE EXAMPLES
    -------------
    raw_next = "/procurements/all?page=2"
    -> allowed

    UNSAFE EXAMPLES
    ---------------
    raw_next = "https://evil.example"
    -> rejected, fallback used

    raw_next = "procurements/all"
    -> rejected, fallback used
    """
    if not raw_next:
        return url_for(fallback_endpoint)

    try:
        parsed = urlparse(raw_next)
    except Exception:
        return url_for(fallback_endpoint)

    if parsed.scheme or parsed.netloc:
        return url_for(fallback_endpoint)

    if not raw_next.startswith("/"):
        return url_for(fallback_endpoint)

    return raw_next


def next_from_request(fallback_endpoint: str) -> str:
    """
    Read "next" from the current request and return a safe local URL.

    PARAMETERS
    ----------
    fallback_endpoint:
        Flask endpoint name used as a safe fallback when no valid "next"
        parameter is available.

    RETURNS
    -------
    str
        Safe redirect target.

    RESOLUTION ORDER
    ----------------
    This helper checks:
    1. request.args["next"]
    2. request.form["next"]

    It then passes the result to safe_next_url(...).

    WHY THIS HELPER EXISTS
    ----------------------
    Many views support the pattern:
    - user opens edit page from a filtered list
    - after save/delete, user should return to the same logical list
    - the "next" value may come from either GET or POST

    Centralizing this logic avoids repeating the same secure redirect code in
    every route file.
    """
    raw_next = request.args.get("next") or request.form.get("next")
    return safe_next_url(raw_next, fallback_endpoint=fallback_endpoint)


```

FILE: .\app\services\user_management_service.py
```python
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


```

FILE: .\app\static\app.css
```css
/*
Minimal, professional styling on top of Bootstrap.

We keep colors soft and use "glass" cards and row highlights,
with support for simple themes: default, dark, ocean.

V4.7:
- Select2 styling tweaks (including dark theme compatibility).
*/

:root{
  --bg-soft: #f6f7fb;
}

.bg-app{
  background: var(--bg-soft);
}

body.theme-default{
  --bg-soft: #f6f7fb;
  color: #212529;
}

body.theme-dark{
  --bg-soft: #111827;
  color: #e5e7eb;
}

body.theme-dark .navbar{
  background-color: #020617 !important;
}

body.theme-dark .card,
body.theme-dark .sidebar-card,
body.theme-dark .glass-card{
  background: #111827;
  color: #e5e7eb;
}

body.theme-dark .list-group-item{
  background-color: transparent;
  color: inherit;
}

body.theme-dark .table{
  color: #e5e7eb;
}

body.theme-ocean{
  --bg-soft: #e6f4ff;
  color: #0f172a;
}

body.theme-ocean .navbar{
  background-color: #0c4a6e !important;
}

/* Shared components */

.glass-card{
  background: rgba(255,255,255,0.96);
  backdrop-filter: blur(6px);
  border-radius: 14px;
}

.sidebar-card{
  background: rgba(255,255,255,0.94);
  backdrop-filter: blur(4px);
  border-radius: 16px;
  position: sticky;
  top: 1rem;

  display: flex;
  flex-direction: column;
}

.sidebar-nav{
  flex: 1 1 auto;
}

.sidebar-section-header{
  font-weight: 600;
  font-size: 0.95rem;
  background-color: transparent;
  border: 0;
  color: #212529;
}

.sidebar-section-header:hover{
  background-color: #f1f3f5;
}

.sidebar-section-header.section-open{
  color: #111827;
}

.sidebar-caret{
  font-size: 0.7rem;
  opacity: 0.8;
}

.sidebar-link{
  font-size: 0.9rem;
  border-left: 3px solid transparent;
  color: #212529;
}

.sidebar-link:hover{
  background-color: #f1f3f5;
}

.sidebar-link.active{
  background-color: #0d6efd;
  color: #fff;
  border-left-color: #0b5ed7;
  font-weight: 600;
}

.sidebar-link.active:hover{
  background-color: #0b5ed7;
}

.sidebar-footer{
  padding: 0.6rem 0.9rem;
}

.sidebar-logout-link{
  font-size: 0.9rem;
  text-decoration: none;
  color: #dc3545;
}

.sidebar-logout-link:hover{
  color: #b02a37;
}

.theme-option-card{
  cursor: pointer;
}

.theme-option-card:hover{
  background-color: #f8fafc;
}

/* ------------------------------------------------------------------
   Procurement lists (wrap + centered)
   ------------------------------------------------------------------ */

.procurements-table th,
.procurements-table td{
  vertical-align: middle;
  text-align: center;
  white-space: normal;
  word-break: break-word;
}

.procurements-table thead .form-control,
.procurements-table thead .form-select{
  text-align: center;
}

/* ------------------------------------------------------------------
   Row color rules (Bootstrap-safe)
   IMPORTANT:
   - Bootstrap tables apply background on cells (td/th).
   - Therefore color the cells via `> *`.
   ------------------------------------------------------------------ */

   
.row-complete > *{
  background-color: #cfe8a9 !important;   /* πράσινο */
}

.row-cancelled > *{
  background-color: #e40f0f !important;   /* κόκκινο */
}

.row-expense-purple > *{
  background-color: #efe3ff !important;   /* ανοικτό μωβ */
}

.row-invoice > *{
  background-color: #ffb366 !important;   /* βαθύ πορτοκαλί */
}

.row-approval > *{
  background-color: #fff4b3 !important;   /* ανοικτό κίτρινο */
}

/* Do NOT color the Open button cell */
.row-approval > td.open-cell,
.row-complete > td.open-cell,
.row-cancelled > td.open-cell,
.row-expense-purple > td.open-cell,
.row-invoice > td.open-cell{
  background-color: transparent !important;
}

.table thead th{
  font-size: 0.85rem;
  letter-spacing: 0.2px;
}

.card{
  border-radius: 14px;
}

.footer-link{
  color: inherit;
  text-decoration: none;
}

.footer-link:hover{
  text-decoration: underline;
}

.footer-icon{
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

/* === Forms === */
.col-form-label-sm {
  font-size: 0.85rem;
  color: #6c757d;
  padding-top: 0.25rem;
  padding-bottom: 0.25rem;
  margin-bottom: 0;
}

.form-control-sm,
.form-select-sm {
  font-size: 0.85rem;
  padding-top: 0.2rem;
  padding-bottom: 0.2rem;
}

.row.align-items-center + .row.align-items-center {
  margin-top: 0.15rem;
}

.form-text {
  font-size: 0.75rem;
  color: #6c757d;
}

.table-sm thead th {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.table-sm tbody td {
  font-size: 0.8rem;
}

.card.bg-light {
  border-radius: 0.75rem;
}

.btn.btn-sm {
  font-size: 0.8rem;
  padding: 0.15rem 0.4rem;
}

.btn-primary,
.btn-outline-primary,
.btn-outline-danger,
.btn-outline-secondary {
  border-radius: 999px;
}

html,
body {
  height: 100%;
}

.body-wrapper {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.main-content {
  flex: 1 0 auto;
}

.app-footer {
  flex-shrink: 0;
  font-size: 0.8rem;
  color: #6c757d;
}

/* ------------------------------------------------------------------
   Select2 (Bootstrap 5 theme) - extra polish
   ------------------------------------------------------------------ */

/* Keep select2 aligned with other inputs */
.select2-container {
  width: 100% !important;
}

/* Default dropdown look */
.select2-container--bootstrap-5 .select2-dropdown {
  border-radius: 0.6rem;
}

/* Dark theme fixes */
body.theme-dark .select2-container--bootstrap-5 .select2-selection {
  background-color: #0b1220;
  border-color: #243044;
  color: #e5e7eb;
}

body.theme-dark .select2-container--bootstrap-5 .select2-selection__rendered {
  color: #e5e7eb;
}

body.theme-dark .select2-container--bootstrap-5 .select2-dropdown {
  background-color: #0b1220;
  border-color: #243044;
  color: #e5e7eb;
}

body.theme-dark .select2-container--bootstrap-5 .select2-results__option {
  color: #e5e7eb;
}

body.theme-dark .select2-container--bootstrap-5 .select2-search__field {
  background-color: #111827;
  color: #e5e7eb;
  border-color: #243044;
}

body.theme-dark .select2-container--bootstrap-5 .select2-results__option--highlighted {
  background-color: #1f2937;
  color: #e5e7eb;
}


```

FILE: .\app\templates\admin\organization_setup.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">Οργάνωση Υπηρεσίας</h1>
    <div class="text-muted small">
      Κεντρική διαχείριση οργανωτικής δομής και ρόλων ανά Υπηρεσία:
      Διευθύνσεις, Τμήματα, Διευθυντές, Προϊστάμενοι, Βοηθοί και μέλη Τμημάτων.
    </div>
  </div>

  <div class="d-flex gap-2">
    {% if is_admin %}
      <a href="{{ url_for('settings.service_units_list') }}" class="btn btn-outline-secondary btn-sm">
        &larr; Πίσω στις Υπηρεσίες
      </a>
    {% endif %}
  </div>
</div>

<div class="card glass-card shadow-sm border-0 mb-3">
  <div class="card-body">
    {% if is_admin %}
      <form method="get" class="row g-2 align-items-end">
        <div class="col-12 col-md-8">
          <label class="form-label small text-muted mb-1">Υπηρεσία</label>
          <select name="service_unit_id" class="form-select form-select-sm">
            <option value="">(επιλέξτε υπηρεσία)</option>
            {% for su in service_units %}
              <option value="{{ su.id }}" {% if scope_service_unit_id == su.id %}selected{% endif %}>
                {{ su.short_name or su.description }}
              </option>
            {% endfor %}
          </select>
        </div>
        <div class="col-12 col-md-4">
          <button class="btn btn-sm btn-outline-primary w-100">Φόρτωση</button>
        </div>
      </form>
    {% else %}
      <div class="small text-muted">Υπηρεσία</div>
      <div class="fw-semibold">
        {{ unit.short_name or unit.description if unit else "" }}
      </div>
      <div class="form-text mt-1">
        Έχεις πρόσβαση μόνο στη δική σου Υπηρεσία.
      </div>
    {% endif %}
  </div>
</div>

{% if unit %}
  <div class="row g-3 mb-3">
    <div class="col-12 col-lg-7">
      <div class="card glass-card shadow-sm border-0 h-100">
        <div class="card-body">
          <h2 class="h6 fw-bold mb-3">Βασικά στοιχεία Υπηρεσίας</h2>

          <div class="row g-2 small">
            <div class="col-12 col-md-6">
              <div class="text-muted">Κωδικός</div>
              <div class="fw-semibold">{{ unit.code or '—' }}</div>
            </div>

            <div class="col-12 col-md-6">
              <div class="text-muted">Συντομογραφία</div>
              <div class="fw-semibold">{{ unit.short_name or '—' }}</div>
            </div>

            <div class="col-12 col-md-6">
              <div class="text-muted">Περιγραφή</div>
              <div class="fw-semibold">{{ unit.description }}</div>
            </div>

            <div class="col-12 col-md-6">
              <div class="text-muted">ΑΑΗΤ</div>
              <div class="fw-semibold">{{ unit.aahit or '—' }}</div>
            </div>

            <div class="col-12 col-md-6">
              <div class="text-muted">Διεύθυνση</div>
              <div class="fw-semibold">{{ unit.address or '—' }}</div>
            </div>

            <div class="col-12 col-md-6">
              <div class="text-muted">Τηλέφωνο</div>
              <div class="fw-semibold">{{ unit.phone or '—' }}</div>
            </div>

            <div class="col-12 col-md-4">
              <div class="text-muted">Διοικητής</div>
              <div class="fw-semibold">{{ unit.commander or '—' }}</div>
            </div>

            <div class="col-12 col-md-4">
              <div class="text-muted">Επιμελητής</div>
              <div class="fw-semibold">{{ unit.curator or '—' }}</div>
            </div>

            <div class="col-12 col-md-4">
              <div class="text-muted">Υπόλογος εφοδιασμού</div>
              <div class="fw-semibold">{{ unit.supply_officer or '—' }}</div>
            </div>
          </div>

          {% if is_admin %}
            <div class="mt-3">
              <a href="{{ url_for('settings.service_unit_edit_info', unit_id=unit.id) }}" class="btn btn-sm btn-outline-secondary">
                Επεξεργασία Βασικών Στοιχείων
              </a>
              <a href="{{ url_for('settings.service_unit_edit', unit_id=unit.id) }}" class="btn btn-sm btn-outline-primary">
                Ρόλοι Manager / Deputy
              </a>
            </div>
          {% endif %}
        </div>
      </div>
    </div>

    <div class="col-12 col-lg-5">
      <div class="card glass-card shadow-sm border-0 h-100">
        <div class="card-body">
          <h2 class="h6 fw-bold mb-3">Excel Import Δομής + Ρόλων</h2>

          <div class="small text-muted mb-2">
            Υποστηρίζονται ενδεικτικά headers:
            <span class="fw-semibold">ΔΙΕΥΘΥΝΣΗ</span>,
            <span class="fw-semibold">ΔΙΕΥΘΥΝΤΗΣ_ΑΓΜ</span>,
            <span class="fw-semibold">ΤΜΗΜΑ</span>,
            <span class="fw-semibold">ΠΡΟΙΣΤΑΜΕΝΟΣ_ΑΓΜ</span>,
            <span class="fw-semibold">ΒΟΗΘΟΣ_ΑΓΜ</span>.
          </div>

          <div class="form-text mb-3">
            Αν κάποια Διεύθυνση ή Τμήμα δεν υπάρχει, δημιουργείται αυτόματα.
            Αν βρεθεί ΑΓΜ ενεργού προσωπικού της ίδιας Υπηρεσίας, δημιουργείται και
            η αντίστοιχη συμμετοχή του στο Τμήμα.
          </div>

          <form method="post" enctype="multipart/form-data" class="d-flex gap-2">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <input type="hidden" name="action" value="import">
            <input type="hidden" name="service_unit_id" value="{{ unit.id }}">
            <input type="file" name="file" accept=".xlsx" class="form-control form-control-sm" required>
            <button class="btn btn-sm btn-outline-primary">Εισαγωγή Excel</button>
          </form>
        </div>
      </div>
    </div>
  </div>

<div class="row g-3">
  <div class="col-12">
    <div class="card glass-card shadow-sm border-0">
      <div class="card-body">
        <h2 class="h6 fw-bold mb-3">Οργανωτική Δομή</h2>

        <div class="card bg-light border-0 mb-3">
          <div class="card-body">
            <div class="fw-semibold mb-2">Νέα Διεύθυνση</div>
            <form method="post" class="row g-2">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
              <input type="hidden" name="action" value="create_directory">
              <input type="hidden" name="service_unit_id" value="{{ unit.id }}">

              <div class="col-12 col-md-8">
                <input name="directory_name" class="form-control form-control-sm" placeholder="Ονομασία Διεύθυνσης" required>
              </div>
              <div class="col-12 col-md-4">
                <button class="btn btn-sm btn-primary w-100">Προσθήκη</button>
              </div>
            </form>
          </div>
        </div>

        <div class="card bg-light border-0 mb-3">
          <div class="card-body">
            <div class="fw-semibold mb-2">Νέο Τμήμα</div>
            <form method="post" class="row g-2">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
              <input type="hidden" name="action" value="create_department">
              <input type="hidden" name="service_unit_id" value="{{ unit.id }}">

              <div class="col-12 col-md-5">
                <select name="directory_id" class="form-select form-select-sm js-select2" data-placeholder="Διεύθυνση" required>
                  <option value=""></option>
                  {% for d in directories %}
                    <option value="{{ d.id }}">{{ d.name }}</option>
                  {% endfor %}
                </select>
              </div>

              <div class="col-12 col-md-5">
                <input name="department_name" class="form-control form-control-sm" placeholder="Ονομασία Τμήματος" required>
              </div>

              <div class="col-12 col-md-2">
                <button class="btn btn-sm btn-primary w-100">Προσθήκη</button>
              </div>
            </form>
          </div>
        </div>

        <div class="mb-4">
          <div class="fw-semibold mb-2">Διευθύνσεις</div>
          {% if directories %}
            <div class="table-responsive">
              <table class="table table-sm align-middle mb-0">
                <thead>
                  <tr>
                    <th>Ονομασία</th>
                    <th>Ενεργό</th>
                    <th class="text-end">Ενέργειες</th>
                  </tr>
                </thead>
                <tbody>
                  {% for d in directories %}
                    <tr>
                      <td style="min-width: 220px;">
                        <form method="post" class="d-flex gap-2">
                          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                          <input type="hidden" name="action" value="update_directory">
                          <input type="hidden" name="service_unit_id" value="{{ unit.id }}">
                          <input type="hidden" name="directory_id" value="{{ d.id }}">
                          <input name="directory_name" class="form-control form-control-sm" value="{{ d.name }}" required>
                      </td>
                      <td>
                        <input type="checkbox" name="is_active" {% if d.is_active %}checked{% endif %}>
                      </td>
                      <td class="text-end">
                          <button class="btn btn-sm btn-outline-primary">Αποθήκευση</button>
                        </form>

                        <form method="post" class="d-inline" onsubmit="return confirm('Σίγουρα θέλετε να διαγράψετε τη Διεύθυνση;');">
                          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                          <input type="hidden" name="action" value="delete_directory">
                          <input type="hidden" name="service_unit_id" value="{{ unit.id }}">
                          <input type="hidden" name="directory_id" value="{{ d.id }}">
                          <button class="btn btn-sm btn-outline-danger">Διαγραφή</button>
                        </form>
                      </td>
                    </tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
          {% else %}
            <div class="small text-muted">Δεν υπάρχουν Διευθύνσεις.</div>
          {% endif %}
        </div>

        <div>
          <div class="fw-semibold mb-2">Τμήματα</div>
          {% if departments %}
            <div class="table-responsive">
              <table class="table table-sm align-middle mb-0">
                <thead>
                  <tr>
                    <th>Διεύθυνση</th>
                    <th>Τμήμα</th>
                    <th>Ενεργό</th>
                    <th class="text-end">Ενέργειες</th>
                  </tr>
                </thead>
                <tbody>
                  {% for dep in departments %}
                    <tr>
                      <td class="small" style="min-width: 180px;">
                        {{ dep.directory.name if dep.directory else '—' }}
                      </td>
                      <td style="min-width: 240px;">
                        <form method="post" class="row g-2">
                          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                          <input type="hidden" name="action" value="update_department">
                          <input type="hidden" name="service_unit_id" value="{{ unit.id }}">
                          <input type="hidden" name="department_id" value="{{ dep.id }}">

                          <div class="col-12 col-md-5">
                            <select name="directory_id" class="form-select form-select-sm js-select2" data-placeholder="Διεύθυνση" required>
                              <option value=""></option>
                              {% for d in directories %}
                                <option value="{{ d.id }}" {% if dep.directory_id == d.id %}selected{% endif %}>
                                  {{ d.name }}
                                </option>
                              {% endfor %}
                            </select>
                          </div>

                          <div class="col-12 col-md-5">
                            <input name="department_name" class="form-control form-control-sm" value="{{ dep.name }}" required>
                          </div>

                          <div class="col-12 col-md-2">
                            <button class="btn btn-sm btn-outline-primary w-100">Αποθήκευση</button>
                          </div>
                      </td>
                      <td>
                        <input type="checkbox" name="is_active" {% if dep.is_active %}checked{% endif %}>
                      </td>
                      <td class="text-end">
                        </form>

                        <form method="post" class="d-inline" onsubmit="return confirm('Σίγουρα θέλετε να διαγράψετε το Τμήμα;');">
                          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                          <input type="hidden" name="action" value="delete_department">
                          <input type="hidden" name="service_unit_id" value="{{ unit.id }}">
                          <input type="hidden" name="department_id" value="{{ dep.id }}">
                          <button class="btn btn-sm btn-outline-danger">Διαγραφή</button>
                        </form>
                      </td>
                    </tr>

                    <tr>
                      <td></td>
                      <td colspan="3">
                        <div class="border rounded p-2 bg-light-subtle">
                          <div class="fw-semibold small mb-2">Μέλη Τμήματος</div>

                          <form method="post" class="row g-2 mb-2">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            <input type="hidden" name="action" value="add_department_member">
                            <input type="hidden" name="service_unit_id" value="{{ unit.id }}">
                            <input type="hidden" name="department_id" value="{{ dep.id }}">

                            <div class="col-12 col-md-9">
                              <select name="personnel_id" class="form-select form-select-sm js-personnel-select" required>
                                <option value=""></option>
                                {% for p in personnel_list %}
                                  <option value="{{ p.id }}">{{ p.display_option_label() }}</option>
                                {% endfor %}
                              </select>
                            </div>

                            <div class="col-12 col-md-3">
                              <button class="btn btn-sm btn-outline-primary w-100">Προσθήκη Μέλους</button>
                            </div>
                          </form>

                          {% set dep_members = department_memberships.get(dep.id, []) %}
                          {% if dep_members %}
                            <div class="table-responsive">
                              <table class="table table-sm mb-0">
                                <thead>
                                  <tr>
                                    <th>Προσωπικό</th>
                                    <th class="text-end">Ενέργεια</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {% for assignment in dep_members %}
                                    <tr>
                                      <td class="small">{{ assignment.personnel.display_option_label() }}</td>
                                      <td class="text-end">
                                        <form method="post" class="d-inline" onsubmit="return confirm('Να αφαιρεθεί το μέλος από το Τμήμα;');">
                                          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                                          <input type="hidden" name="action" value="remove_department_member">
                                          <input type="hidden" name="service_unit_id" value="{{ unit.id }}">
                                          <input type="hidden" name="assignment_id" value="{{ assignment.id }}">
                                          <button class="btn btn-sm btn-outline-danger">Αφαίρεση</button>
                                        </form>
                                      </td>
                                    </tr>
                                  {% endfor %}
                                </tbody>
                              </table>
                            </div>
                          {% else %}
                            <div class="small text-muted">Δεν υπάρχουν μέλη στο συγκεκριμένο Τμήμα.</div>
                          {% endif %}
                        </div>
                      </td>
                    </tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
          {% else %}
            <div class="small text-muted">Δεν υπάρχουν Τμήματα.</div>
          {% endif %}
        </div>
      </div>
    </div>
  </div>

  <div class="col-12">
    <div class="card glass-card shadow-sm border-0">
      <div class="card-body">
        <h2 class="h6 fw-bold mb-3">Ρόλοι Δομής</h2>

        <div class="mb-4">
          <div class="fw-semibold mb-2">Διευθύνσεις → Διευθυντής</div>

          {% if directories %}
            <div class="table-responsive">
              <table class="table table-sm align-middle mb-0">
                <thead>
                  <tr>
                    <th>Διεύθυνση</th>
                    <th>Διευθυντής (Τμηματάρχης/Διευθυντής)</th>
                    <th class="text-end"></th>
                  </tr>
                </thead>
                <tbody>
                  {% for d in directories %}
                    <tr>
                      <td class="small" style="min-width: 180px;">{{ d.name }}</td>
                      <td style="min-width: 280px;">
                        <form method="post" class="d-flex gap-2">
                          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                          <input type="hidden" name="action" value="update_directory_director">
                          <input type="hidden" name="service_unit_id" value="{{ unit.id }}">
                          <input type="hidden" name="directory_id" value="{{ d.id }}">

                          <select name="director_personnel_id" class="form-select form-select-sm js-personnel-select">
                            <option value="">(κανένας)</option>
                            {% for p in personnel_list %}
                              <option value="{{ p.id }}" {% if d.director_personnel_id == p.id %}selected{% endif %}>
                                {{ p.display_option_label() }}
                              </option>
                            {% endfor %}
                          </select>
                      </td>
                      <td class="text-end">
                          <button class="btn btn-sm btn-outline-primary">Αποθήκευση</button>
                        </form>
                      </td>
                    </tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
          {% else %}
            <div class="small text-muted">Δεν υπάρχουν Διευθύνσεις για ανάθεση ρόλων.</div>
          {% endif %}
        </div>

        <div>
          <div class="fw-semibold mb-2">Τμήματα → Προϊστάμενος / Βοηθός</div>

          {% if departments %}
            <div class="table-responsive">
              <table class="table table-sm align-middle mb-0">
                <thead>
                  <tr>
                    <th>Διεύθυνση</th>
                    <th>Τμήμα</th>
                    <th>Προϊστάμενος</th>
                    <th>Βοηθός</th>
                    <th class="text-end"></th>
                  </tr>
                </thead>
                <tbody>
                  {% for dep in departments %}
                    <tr>
                      <td class="small" style="min-width: 160px;">
                        {{ dep.directory.name if dep.directory else '—' }}
                      </td>
                      <td class="small" style="min-width: 160px;">{{ dep.name }}</td>
                      <td style="min-width: 240px;">
                        <form method="post" class="d-flex gap-2">
                          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                          <input type="hidden" name="action" value="update_department_roles">
                          <input type="hidden" name="service_unit_id" value="{{ unit.id }}">
                          <input type="hidden" name="department_id" value="{{ dep.id }}">

                          <select name="head_personnel_id" class="form-select form-select-sm js-personnel-select">
                            <option value="">(κανένας)</option>
                            {% for p in personnel_list %}
                              <option value="{{ p.id }}" {% if dep.head_personnel_id == p.id %}selected{% endif %}>
                                {{ p.display_option_label() }}
                              </option>
                            {% endfor %}
                          </select>
                      </td>
                      <td style="min-width: 240px;">
                          <select name="assistant_personnel_id" class="form-select form-select-sm js-personnel-select">
                            <option value="">(κανένας)</option>
                            {% for p in personnel_list %}
                              <option value="{{ p.id }}" {% if dep.assistant_personnel_id == p.id %}selected{% endif %}>
                                {{ p.display_option_label() }}
                              </option>
                            {% endfor %}
                          </select>
                      </td>
                      <td class="text-end">
                          <button class="btn btn-sm btn-outline-primary">Αποθήκευση</button>
                        </form>
                      </td>
                    </tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
          {% else %}
            <div class="small text-muted">Δεν υπάρχουν Τμήματα για ανάθεση ρόλων.</div>
          {% endif %}
        </div>
      </div>
    </div>
  </div>
</div>

<script>
(function() {
  if (!window.jQuery || !jQuery.fn || !jQuery.fn.select2) return;

  function stripParen(text) {
    if (!text) return text;
    return String(text).replace(/\s*\([^)]*\)\s*$/, "").trim();
  }

  jQuery(".js-personnel-select").each(function() {
    const $el = jQuery(this);
    if ($el.data("select2")) return;

    $el.select2({
      theme: "bootstrap-5",
      width: "100%",
      allowClear: true,
      placeholder: "(αναζήτηση...)",
      templateResult: function(state) {
        if (!state || !state.text) return state.text;
        return state.text;
      },
      templateSelection: function(state) {
        if (!state || !state.text) return state.text;
        return stripParen(state.text);
      }
    });
  });

  jQuery(".js-select2").each(function() {
    const $el = jQuery(this);
    if ($el.data("select2")) return;

    $el.select2({
      theme: "bootstrap-5",
      width: "100%",
      allowClear: true,
      placeholder: $el.data("placeholder") || "(αναζήτηση...)"
    });
  });
})();
</script>

{% else %}
  <div class="alert alert-info">
    {% if is_admin %}
      Επίλεξε υπηρεσία για να διαχειριστείς τη δομή και τους ρόλους της.
    {% else %}
      Δεν βρέθηκε διαθέσιμη Υπηρεσία για οργάνωση.
    {% endif %}
  </div>
{% endif %}

{% endblock %}

```

FILE: .\app\templates\admin\personnel_form.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">{{ form_title }}</h1>
    <div class="text-muted small">
      Καταχώρηση/ενημέρωση βασικών στοιχείων προσωπικού.
      Η οργανωτική ένταξη σε Διεύθυνση/Τμήμα γίνεται μόνο από την «Οργάνωση Υπηρεσίας».
    </div>
  </div>
  <a href="{{ url_for('admin.personnel_list') }}" class="btn btn-outline-secondary btn-sm">
    &larr; Πίσω στη λίστα
  </a>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    <div class="row g-3">
      <div class="col-12 col-lg-8">

        <form method="post">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Υπηρεσία *</label>
            <div class="col-8">
              {% if current_user.is_admin %}
                <select id="service_unit_id" name="service_unit_id" class="form-select form-select-sm">
                  <option value="">(επιλέξτε)</option>
                  {% for su in service_units %}
                    <option value="{{ su.id }}"
                      {% if person and person.service_unit_id == su.id %}selected{% endif %}>
                      {{ su.short_name or su.description }}
                    </option>
                  {% endfor %}
                </select>
              {% else %}
                <input
                  class="form-control form-control-sm"
                  value="{{ current_user.service_unit.short_name if current_user.service_unit else '' }}"
                  disabled
                >
                <input type="hidden" id="service_unit_id" name="service_unit_id" value="">
              {% endif %}
              <div class="form-text">
                Απαιτείται. Η οργανωτική ένταξη σε Διεύθυνση/Τμήμα δεν ορίζεται από εδώ.
              </div>
            </div>
          </div>

          <hr class="my-3">

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΓΜ *</label>
            <div class="col-8">
              <input name="agm" class="form-control form-control-sm"
                     value="{{ person.agm if person else '' }}" required>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΕΜ</label>
            <div class="col-8">
              <input name="aem" class="form-control form-control-sm"
                     value="{{ person.aem if person and person.aem else '' }}">
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Βαθμός</label>
            <div class="col-8">
              <input name="rank" class="form-control form-control-sm"
                     value="{{ person.rank if person and person.rank else '' }}">
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Όνομα *</label>
            <div class="col-8">
              <input name="first_name" class="form-control form-control-sm"
                     value="{{ person.first_name if person else '' }}" required>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Επώνυμο *</label>
            <div class="col-8">
              <input name="last_name" class="form-control form-control-sm"
                     value="{{ person.last_name if person else '' }}" required>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Ειδικότητα</label>
            <div class="col-8">
              <input name="specialty" class="form-control form-control-sm"
                     value="{{ person.specialty if person and person.specialty else '' }}">
            </div>
          </div>

          {% if person %}
          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Κατάσταση</label>
            <div class="col-8">
              <div class="form-check">
                <input class="form-check-input" type="checkbox" name="is_active" id="is_active"
                       {% if person.is_active %}checked{% endif %}>
                <label class="form-check-label" for="is_active">
                  Ενεργό Προσωπικό
                </label>
              </div>
            </div>
          </div>
          {% endif %}

          <div class="mt-3">
            <button class="btn btn-primary btn-sm">
              Αποθήκευση
            </button>
          </div>

        </form>

      </div>

      <div class="col-12 col-lg-4">
        <div class="card bg-light border-0 h-100">
          <div class="card-body py-3 small">
            <div class="fw-bold mb-2">Σημείωση</div>
            <ul class="mb-0">
              <li>Η Υπηρεσία είναι υποχρεωτική (server-side).</li>
              <li>Η ένταξη σε Διευθύνσεις/Τμήματα ορίζεται μόνο από την «Οργάνωση Υπηρεσίας».</li>
              <li>Έτσι υποστηρίζεται σωστά συμμετοχή του ίδιου προσώπου σε πολλά Τμήματα.</li>
            </ul>
          </div>
        </div>
      </div>

    </div>
  </div>
</div>
{% endblock %}

```

FILE: .\app\templates\admin\personnel_list.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex justify-content-between align-items-start align-items-md-center mb-3 flex-column flex-md-row gap-2">
  <div>
    <h1 class="h4 fw-bold mb-1">Προσωπικό Οργανισμού</h1>
    <div class="text-muted small">Διαχείριση προσωπικού και ανάθεση υπηρεσίας / διεύθυνσης / τμήματος.</div>
  </div>

  <div class="d-flex gap-2 align-items-center flex-wrap">
    <a href="{{ url_for('admin.create_personnel') }}" class="btn btn-primary btn-sm">
      Νέο Προσωπικό
    </a>
  </div>
</div>

<div class="card glass-card shadow-sm border-0 mb-3">
  <div class="card-body">
    <div class="d-flex flex-column flex-md-row align-items-start align-items-md-end justify-content-between gap-2">
      <div class="small text-muted">
        Excel import: στήλες <span class="fw-semibold">ΑΓΜ</span>, <span class="fw-semibold">ΟΝΟΜΑ</span>, <span class="fw-semibold">ΕΠΩΝΥΜΟ</span>
        (προαιρετικά: ΑΕΜ, ΒΑΘΜΟΣ, ΕΙΔΙΚΟΤΗΤΑ, ΥΠΗΡΕΣΙΑ).
      </div>

      <form method="post" action="{{ url_for('admin.import_personnel') }}" enctype="multipart/form-data" class="d-flex gap-2">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="file" name="file" accept=".xlsx" class="form-control form-control-sm" required>
        <button class="btn btn-outline-primary btn-sm">
          Εισαγωγή Excel
        </button>
      </form>
    </div>
  </div>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    {% if personnel %}
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr>
              <th>ΑΓΜ</th>
              <th>ΑΕΜ</th>
              <th>Βαθμός</th>
              <th>Ειδικότητα</th>
              <th>Ονοματεπώνυμο</th>
              <th>Υπηρεσία</th>
              <th>Διεύθυνση</th>
              <th>Τμήμα</th>
              <th>Κατάσταση</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {% for p in personnel %}
              <tr>
                <td class="small fw-semibold">{{ p.agm }}</td>
                <td class="small">{{ p.aem or '—' }}</td>
                <td class="small">{{ p.rank or '—' }}</td>
                <td class="small">{{ p.specialty or '—' }}</td>
                <td class="small">
                  {{ p.display_selected_label() if p else '—' }}
                </td>
                <td class="small">
                  {% if p.service_unit %}
                    {{ p.service_unit.short_name or p.service_unit.description }}
                  {% else %}
                    —
                  {% endif %}
                </td>
                <td class="small">
                  {% if p.directory %}
                    {{ p.directory.name }}
                  {% else %}
                    —
                  {% endif %}
                </td>
                <td class="small">
                  {% if p.department %}
                    {{ p.department.name }}
                  {% else %}
                    —
                  {% endif %}
                </td>
                <td class="small">
                  {% if p.is_active %}
                    <span class="badge bg-success">Ενεργό</span>
                  {% else %}
                    <span class="badge bg-secondary">Ανενεργό</span>
                  {% endif %}
                </td>
                <td class="text-end">
                  <div class="d-inline-flex gap-1">
                    <a href="{{ url_for('admin.edit_personnel', personnel_id=p.id) }}"
                      class="btn btn-sm btn-outline-secondary">
                      Επεξεργασία
                    </a>

                    <form method="post"
                          action="{{ url_for('admin.delete_personnel', personnel_id=p.id) }}"
                          style="display:inline"
                          onsubmit="return confirm('Να διαγραφεί το προσωπικό;');">
                      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                      <button type="submit" class="btn btn-sm btn-outline-danger">
                        Διαγραφή
                      </button>
                    </form>
                  </div>
                </td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <div class="text-muted small">Δεν υπάρχει καταχωρημένο προσωπικό.</div>
    {% endif %}
  </div>
</div>
{% endblock %}


```

FILE: .\app\templates\auth\login.html
```html
{% extends "base.html" %}

{% block content %}
<div class="row justify-content-center">
  <div class="col-12 col-md-6 col-lg-4">
    <div class="card glass-card shadow-sm border-0">
      <div class="card-body p-4">
        <h1 class="h4 fw-bold mb-3">Σύνδεση</h1>

        <form method="post">
          <!-- CSRF hidden field -->
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

          <div class="mb-3">
            <label class="form-label">Όνομα χρήστη</label>
            <input name="username" class="form-control" required>
          </div>

          <div class="mb-3">
            <label class="form-label">Κωδικός</label>
            <input name="password" type="password" class="form-control" required>
          </div>

          <button class="btn btn-primary w-100">
            Είσοδος
          </button>
        </form>

        <div class="mt-3 small text-muted">
          Αν είναι η πρώτη εγκατάσταση, δημιουργήστε admin από:
          <code>/auth/seed-admin</code>
        </div>
      </div>
    </div>
  </div>
</div>
{% endblock %}


```

FILE: .\app\templates\auth\seed_admin.html
```html
{% extends "base.html" %}

{% block content %}
<div class="row justify-content-center">
  <div class="col-12 col-md-7 col-lg-5">
    <div class="card glass-card shadow-sm border-0">
      <div class="card-body p-4">
        <h1 class="h4 fw-bold mb-2">Δημιουργία Πρώτου Admin</h1>
        <p class="text-muted small">
          Αυτή η φόρμα είναι μόνο για την αρχική εγκατάσταση.
        </p>

        <form method="post">
          <!-- CSRF hidden field -->
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

          <div class="mb-3">
            <label class="form-label">Όνομα χρήστη</label>
            <input name="username" class="form-control" required>
          </div>

          <div class="mb-3">
            <label class="form-label">Κωδικός</label>
            <input name="password" type="password" class="form-control" required>
          </div>

          <button class="btn btn-success w-100">
            Δημιουργία Admin
          </button>
        </form>
      </div>
    </div>
  </div>
</div>
{% endblock %}


```

FILE: .\app\templates\base.html
```html
{# 
Base layout for all pages.

Top:
  - Black navbar with "Procurement Management" on the left
  - Logged-in username on the right

Below:
  - If logged in: left sidebar (sections + pages) + main content on the right
  - If not logged in: main content full width

Logout ("Έξοδος") is at the BOTTOM of the sidebar.
Footer is sticky at bottom of the viewport thanks to flex layout.

IMPORTANT: block "content" is defined only once at the bottom.

V4.7:
- Added Select2 (searchable dropdowns) for large master lists (ALE/CPV).
- NOTE: Select2 requires jQuery.
#}
<!doctype html>
<html lang="el">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ config.APP_NAME }}</title>

  <!-- Bootstrap 5 CSS from CDN -->
  <link
    href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
    rel="stylesheet"
  >

  <!-- Select2 CSS -->
  <link
    href="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css"
    rel="stylesheet"
  >
  <!-- Select2 Bootstrap-5 Theme (nice integration) -->
  <link
    href="https://cdn.jsdelivr.net/npm/select2-bootstrap-5-theme@1.3.0/dist/select2-bootstrap-5-theme.min.css"
    rel="stylesheet"
  >

  <!-- Custom app styles -->
  <link rel="stylesheet" href="{{ url_for('static', filename='app.css') }}">

  <style>
    /* ------------------------------------------------------------
       Select2 minor tweaks to match Bootstrap-sm controls
       ------------------------------------------------------------ */
    .select2-container--bootstrap-5 .select2-selection--single {
      min-height: calc(1.5em + .4rem + 2px);
      padding: .15rem .4rem;
      font-size: .85rem;
    }
    .select2-container--bootstrap-5 .select2-selection--single .select2-selection__rendered {
      line-height: 1.5;
    }
    .select2-container--bootstrap-5 .select2-selection--single .select2-selection__arrow {
      height: calc(1.5em + .4rem + 2px);
    }
  </style>
</head>
<body class="bg-app {% if current_user.is_authenticated %}theme-{{ current_user.theme or 'default' }}{% else %}theme-default{% endif %} d-flex flex-column min-vh-100">

<nav class="navbar navbar-expand-lg navbar-dark bg-dark shadow-sm">
  <div class="container-fluid">
    {# Brand: Procurement Management on the top left #}
    <a class="navbar-brand fw-semibold" href="{{ url_for('procurements.list_procurements') }}">
      {{ config.APP_NAME }}
    </a>

    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navMain">
      <span class="navbar-toggler-icon"></span>
    </button>

    <div class="collapse navbar-collapse" id="navMain">
      <div class="me-auto"></div>

      {# RIGHT SIDE: username OR login link (logout is now in sidebar) #}
      <ul class="navbar-nav ms-auto">
        {% if current_user.is_authenticated %}
          <li class="nav-item me-2">
            <span class="nav-link text-light opacity-75">
              {{ current_user.username }}
            </span>
          </li>
        {% else %}
          <li class="nav-item">
            <a class="nav-link" href="{{ url_for('auth.login') }}">Σύνδεση</a>
          </li>
        {% endif %}
      </ul>
    </div>
  </div>
</nav>

{# flex-grow-1 makes main stretch and pushes footer to bottom #}
<main class="container-fluid py-4 flex-grow-1">
  <div class="row">
    {% if current_user.is_authenticated %}
      {# LEFT SIDEBAR: visible only when logged in #}
      <aside class="col-12 col-md-3 col-lg-2 mb-3 mb-md-0">
        <div class="card sidebar-card shadow-sm border-0">
          <div class="list-group list-group-flush sidebar-nav">
            {% for section in nav_sections %}
              {% set section_id = 'nav-section-' ~ loop.index %}

              {# Determine if this section is active based on current endpoint. #}
              {% set ns = namespace(active=false) %}
              {% for item in section["items"] %}
                {% if item.get("endpoint") and request.endpoint == item["endpoint"] %}
                  {% set ns.active = true %}
                {% endif %}
              {% endfor %}

              <div class="sidebar-section">
                <button
                  class="list-group-item list-group-item-action d-flex justify-content-between align-items-center sidebar-section-header {% if ns.active %}section-open{% endif %}"
                  data-bs-toggle="collapse"
                  data-bs-target="#{{ section_id }}"
                  aria-expanded="{{ 'true' if ns.active else 'false' }}"
                  type="button"
                >
                  <span>{{ section["label"] }}</span>
                  <span class="sidebar-caret">&#9662;</span>
                </button>

                <div
                  id="{{ section_id }}"
                  class="collapse {% if ns.active %}show{% endif %}"
                >
                  {% for item in section["items"] %}
                    {# Sub-header grouping inside the section #}
                    {% if item.get("type") == "header" %}
                      <div class="list-group-item sidebar-section-header py-2 ps-4"
                           style="cursor: default; background: transparent; font-size: 0.82rem; opacity: 0.8; text-decoration: underline;">
                        {{ item["label"] }}
                      </div>
                    {% else %}
                      {% set has_endpoint = item.get("endpoint") %}
                      {% set is_active_link = has_endpoint and (request.endpoint == item["endpoint"]) %}
                      {% set is_disabled = (not has_endpoint) or item.get("disabled", False) %}

                      {% if is_disabled %}
                        <div class="list-group-item ps-4 sidebar-link"
                             style="opacity:0.55; cursor:not-allowed;">
                          {{ item["label"] }}
                        </div>
                      {% else %}
                        <a
                          class="list-group-item list-group-item-action ps-4 sidebar-link {% if is_active_link %}active{% endif %}"
                          href="{{ url_for(item['endpoint']) }}"
                        >
                          {{ item["label"] }}
                        </a>
                      {% endif %}
                    {% endif %}
                  {% endfor %}
                </div>
              </div>
            {% endfor %}
          </div>

          {# LOGOUT at the very bottom of the sidebar #}
          <div class="sidebar-footer border-top">
            <a href="{{ url_for('auth.logout') }}" class="sidebar-logout-link d-flex align-items-center">
              <span class="me-2">⏻</span>
              <span>Έξοδος</span>
            </a>
          </div>
        </div>
      </aside>

      {# MAIN CONTENT COLUMN (for logged-in users) #}
      {% set content_col_classes = "col-12 col-md-9 col-lg-10" %}
    {% else %}
      {# If not logged in, main content takes full width #}
      {% set content_col_classes = "col-12" %}
    {% endif %}

    <section class="{{ content_col_classes }}">
      {# Flash messages (always shown above content) #}
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
          <div class="mb-3">
            {% for category, msg in messages %}
              <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                {{ msg }}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
              </div>
            {% endfor %}
          </div>
        {% endif %}
      {% endwith %}

      {# SINGLE content block used by child templates #}
      {% block content %}{% endblock %}
    </section>
  </div>
</main>

<footer class="container pb-4">
  <div class="d-flex flex-column flex-md-row justify-content-between align-items-center small text-muted gap-2">
    <div>
      Εσωτερικό εργαλείο • Flask
    </div>
    <div class="d-flex align-items-center gap-3">
      <a href="mailto:you@example.com" class="footer-link d-inline-flex align-items-center">
        <span class="footer-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 16 16">
            <path d="M0 4a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v.217l-8 4.8-8-4.8V4z"/>
            <path d="M0 5.383v6.617A2 2 0 0 0 2 14h12a2 2 0 0 0 2-2V5.383l-7.555 4.533a1 1 0 0 1-1.022 0L0 5.383z"/>
          </svg>
        </span>
        <span class="ms-1">you@example.com</span>
      </a>

      <a href="https://github.com/yourusername" target="_blank" class="footer-link d-inline-flex align-items-center">
        <span class="footer-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 16 16">
            <path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38
                     0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13
                     -.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52
                     .28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95
                     0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12
                     0 0 .67-.21 2.2.82A7.65 7.65 0 0 1 8 3.5
                     c.68.003 1.37.092 2.01.27 1.53-1.04 2.2-.82 2.2-.82
                     .44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15
                     0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48
                     0 1.07-.01 1.93-.01 2.19 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8
                     c0-4.42-3.58-8-8-8z"/>
          </svg>
        </span>
        <span class="ms-1">GitHub</span>
      </a>

      <a href="https://www.linkedin.com/in/yourprofile" target="_blank" class="footer-link d-inline-flex align-items-center">
        <span class="footer-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 16 16">
            <path d="M1.146 1.146C1.54.752 2.074.5 2.667.5c.593 0 1.127.252 1.52.646.394.394.647.928.647 1.52
                     0 .593-.253 1.127-.647 1.52A2.144 2.144 0 0 1 2.667 4.833
                     c-.593 0-1.127-.253-1.52-.647A2.144 2.144 0 0 1 .5 2.667c0-.593.252-1.127.646-1.52zM.667 6h4v9.333h-4V6zm5.333 0h3.833v1.227h.053
                     c.534-.96 1.837-1.973 3.78-1.973C15.94 5.254 16 7.427 16 9.88V15.333h-4V10.44
                     c0-1.166-.02-2.667-1.627-2.667-1.627 0-1.877 1.27-1.877 2.58v4.98h-4V6z"/>
          </svg>
        </span>
        <span class="ms-1">LinkedIn</span>
      </a>
    </div>
  </div>
</footer>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>

<!-- jQuery (required by Select2) -->
<script src="https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.min.js"></script>
<!-- Select2 JS -->
<script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>

<script>
/**
 * Global Select2 initializer.
 *
 * Usage:
 * - Add class "js-select2" to any <select>.
 * - Optional: data-placeholder="..." on the select.
 *
 * IMPORTANT:
 * - UI is not trusted. All validations remain server-side.
 */
(function() {
  function initSelect2() {
    if (!window.jQuery || !jQuery.fn || !jQuery.fn.select2) return;

    jQuery(".js-select2").each(function() {
      const $el = jQuery(this);

      // Prevent double-init if template rerenders
      if ($el.data("select2")) return;

      const placeholder = $el.data("placeholder") || "(αναζήτηση...)";

      $el.select2({
        theme: "bootstrap-5",
        width: "100%",
        placeholder: placeholder,
        allowClear: true
      });
    });
  }

  // DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSelect2);
  } else {
    initSelect2();
  }
})();
</script>

</body>
</html>


```

FILE: .\app\templates\errors\403.html
```html
{% extends "base.html" %}

{% block content %}
<div class="text-center py-5">
  <h1 class="h4 fw-bold mb-2">403 - Μη εξουσιοδοτημένη πρόσβαση</h1>
  <p class="text-muted">Δεν έχετε δικαίωμα να δείτε αυτή τη σελίδα.</p>
</div>
{% endblock %}


```

FILE: .\app\templates\procurements\edit.html
```html
{# app/templates/procurements/edit.html #}
{% extends "base.html" %}
{% block content %}

{% set can_edit = current_user.is_admin or current_user.can_manage() %}
{% set is_admin = current_user.is_admin %}
{% set back_url = next_url if next_url is defined and next_url else url_for('procurements.inbox_procurements') %}
{% set show_all_reports = show_all_report_buttons if show_all_report_buttons is defined else false %}

<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">Προμήθεια #{{ procurement.id }}</h1>
    <div class="text-muted small">
      Όλα τα στοιχεία παραμένουν διαθέσιμα για επεξεργασία μετά την αποθήκευση.
    </div>
  </div>

  <div class="d-flex gap-2 flex-wrap justify-content-end">

    <button type="button" class="btn btn-sm btn-outline-primary" disabled title="Σύντομα">
      Δέσμευση
    </button>
    <button type="button" class="btn btn-sm btn-outline-primary" disabled title="Σύντομα">
      Πρόσκληση
    </button>
    <button type="button" class="btn btn-sm btn-outline-primary" disabled title="Σύντομα">
      Προέγκριση
    </button>

    {% if show_all_reports %}
      <a
        class="btn btn-sm btn-outline-primary"
        href="{{ url_for('procurements.report_proforma_invoice', procurement_id=procurement.id) }}"
        target="_blank"
        rel="noopener"
        title="Άνοιγμα Προτιμολογίου (PDF)"
      >
        Προτιμολόγιο
      </a>

      <a
        class="btn btn-sm btn-outline-primary"
        href="{{ url_for('procurements.report_award_decision_docx', procurement_id=procurement.id) }}"
        title="Λήψη Απόφασης Ανάθεσης (DOCX)"
      >
        Απόφαση Ανάθεσης
      </a>

      <button type="button" class="btn btn-sm btn-outline-primary" disabled title="Σύντομα">
        Σύμβαση
      </button>
      <button type="button" class="btn btn-sm btn-outline-primary" disabled title="Σύντομα">
        Πρωτόκολλο
      </button>
      <button type="button" class="btn btn-sm btn-outline-primary" disabled title="Σύντομα">
        ΚΠΔ
      </button>

      <a
        class="btn btn-sm btn-outline-primary"
        href="{{ url_for('procurements.report_expense_transmittal_docx', procurement_id=procurement.id) }}"
        title="Λήψη Διαβιβαστικού Δαπάνης (DOCX)"
      >
        Διαβιβαστικό Δαπάνης
      </a>
      
    {% endif %}

    <a href="{{ back_url }}" class="btn btn-outline-secondary btn-sm">
      &larr; Επιστροφή
    </a>
  </div>
</div>

<div class="card glass-card shadow-sm border-0 mb-3">
  <div class="card-body">
    <h2 class="h6 fw-bold mb-3">Βασικά στοιχεία</h2>

    <form method="post">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <input type="hidden" name="next" value="{{ back_url }}">

      <div class="row g-3">
        <div class="col-12 col-lg-8">

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Υπηρεσία</label>
            <div class="col-8">
              {% if is_admin %}
                <select name="service_unit_id" class="form-select form-select-sm" {% if not can_edit %}disabled{% endif %}>
                  <option value="">(επιλέξτε)</option>
                  {% for su in service_units %}
                    <option value="{{ su.id }}" {% if procurement.service_unit_id == su.id %}selected{% endif %}>
                      {{ su.short_name or su.description }}
                    </option>
                  {% endfor %}
                </select>
              {% else %}
                <input class="form-control form-control-sm" disabled
                       value="{{ procurement.service_unit.short_name if procurement.service_unit else '' }}">
              {% endif %}
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Α/Α</label>
            <div class="col-8">
              <input name="serial_no" class="form-control form-control-sm"
                     value="{{ procurement.serial_no or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Τύπος Προμήθειας</label>
            <div class="col-8">
              <select name="income_tax_rule_id" class="form-select form-select-sm" {% if not can_edit %}disabled{% endif %}>
                <option value="">(—)</option>
                {% for r in income_tax_rules %}
                  <option value="{{ r.id }}" {% if procurement.income_tax_rule_id == r.id %}selected{% endif %}>
                    {{ r.description }} ({{ r.rate_percent }}% > {{ r.threshold_amount }}€)
                  </option>
                {% endfor %}
              </select>
              <div class="form-text">
                Η επιλογή χρησιμοποιείται στον υπολογισμό ΦΕ.
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Σύντομη Περιγραφή *</label>
            <div class="col-8">
              <input name="description" class="form-control form-control-sm" required
                     value="{{ procurement.description or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΛΕ</label>
            <div class="col-8">
              <select
                name="ale"
                class="form-select form-select-sm js-ale-select"
                data-placeholder="Αναζήτηση ΑΛΕ..."
                {% if not can_edit %}disabled{% endif %}
              >
                <option value=""></option>
                {% for r in (ale_rows or []) %}
                  {% set ale_display = r.ale ~ ('/' ~ r.responsibility if r.responsibility else '') %}
                  <option value="{{ r.ale }}"
                          data-ale-display="{{ ale_display }}"
                          {% if procurement.ale == r.ale %}selected{% endif %}>
                    {{ ale_display }}{% if r.description %} — {{ r.description }}{% endif %}
                  </option>
                {% endfor %}
              </select>
              <div class="form-text">Πηγή: Ρυθμίσεις → ΑΛΕ-ΚΑΕ.</div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Κατανομή</label>
            <div class="col-8">
              <select name="allocation" class="form-select form-select-sm" {% if not can_edit %}disabled{% endif %}>
                <option value="">(—)</option>
                {% for v in allocation_options %}
                  <option value="{{ v }}" {% if procurement.allocation == v %}selected{% endif %}>{{ v }}</option>
                {% endfor %}
              </select>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Τριμηνιαία</label>
            <div class="col-8">
              <select name="quarterly" class="form-select form-select-sm" {% if not can_edit %}disabled{% endif %}>
                <option value="">(—)</option>
                {% for v in quarterly_options %}
                  <option value="{{ v }}" {% if procurement.quarterly == v %}selected{% endif %}>{{ v }}</option>
                {% endfor %}
              </select>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Κατάσταση</label>
            <div class="col-8">
              <select name="status" class="form-select form-select-sm" {% if not can_edit %}disabled{% endif %}>
                <option value="">(—)</option>
                {% for v in status_options %}
                  <option value="{{ v }}" {% if procurement.status == v %}selected{% endif %}>{{ v }}</option>
                {% endfor %}
              </select>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Στάδιο</label>
            <div class="col-8">
              <select name="stage" class="form-select form-select-sm" {% if not can_edit %}disabled{% endif %}>
                <option value="">(—)</option>
                {% for v in stage_options %}
                  <option value="{{ v }}" {% if procurement.stage == v %}selected{% endif %}>{{ v }}</option>
                {% endfor %}
              </select>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Χειριστής</label>
            <div class="col-8">
              <select
                name="handler_assignment_id"
                class="form-select form-select-sm js-handler-assignment-select"
                data-placeholder="Αναζήτηση Χειριστή..."
                {% if not can_edit %}disabled{% endif %}
              >
                <option value=""></option>
                {% for a in handler_assignments %}
                  <option
                    value="{{ a.id }}"
                    data-selected-label="{{ a.display_selected_label() }}"
                    {% if procurement.handler_assignment_id == a.id %}selected{% endif %}
                  >
                    {{ a.display_option_label() }}
                  </option>
                {% endfor %}
              </select>
              <div class="form-text">
                Αναζήτηση με μορφή: ΒΑΘΜΟΣ ΕΙΔΙΚΟΤΗΤΑ ΟΝΟΜΑ ΕΠΩΝΥΜΟ / ΤΜΗΜΑ / ΔΙΕΥΘΥΝΣΗ.
                Μετά την επιλογή εμφανίζεται: ΒΑΘΜΟΣ ΕΙΔΙΚΟΤΗΤΑ ΟΝΟΜΑ ΕΠΩΝΥΜΟ / ΤΜΗΜΑ.
              </div>
            </div>
          </div>

        </div>

        <div class="col-12 col-lg-4">
          <div class="card bg-light border-0 h-100">
            <div class="card-body py-3 small">

              <div class="text-center mb-2">
                <div class="fw-bold">Μειοδότης</div>
                <div class="mt-1">{{ procurement.winner_supplier_display or '—' }}</div>
              </div>

              <hr class="my-2">

              <div class="text-center mb-2">
                <div class="fw-bold">Ποσά Προέγκρισης</div>
              </div>

              <div class="d-flex justify-content-between">
                <span>Σύνολο</span>
                <span class="fw-semibold">
                  {% if procurement.sum_total %}{{ "{:,.2f}".format(procurement.sum_total) }} €{% else %}—{% endif %}
                </span>
              </div>
              <div class="d-flex justify-content-between">
                <span>ΦΠΑ ({{ analysis.get("vat_percent", 0) }}%)</span>
                <span class="fw-semibold">
                  {% if procurement.vat_amount %}{{ "{:,.2f}".format(procurement.vat_amount) }} €{% else %}—{% endif %}
                </span>
              </div>
              <div class="d-flex justify-content-between">
                <span class="fw-bold">Γενικό Σύνολο</span>
                <span class="fw-bold">
                  {% if procurement.grand_total %}{{ "{:,.2f}".format(procurement.grand_total) }} €{% else %}—{% endif %}
                </span>
              </div>

              <hr class="my-2">

              <div class="fw-bold mb-2">ΑΝΑΛΥΣΗ ΔΑΠΑΝΗΣ</div>

              <div class="d-flex justify-content-between mb-1">
                <span>Σύνολο</span>
                <span class="fw-semibold">{{ "{:,.2f}".format(analysis.get("sum_total", 0)) }} €</span>
              </div>

              {% set pw = analysis.get("public_withholdings") or {} %}
              {% if pw.get("total_amount") and pw.get("total_amount") != 0 %}
                <div class="mt-2">
                  <div class="d-flex justify-content-between fw-semibold">
                    <span>Κρατήσεις υπέρ δημοσίου ({{ pw.get("total_percent", 0) }}%)</span>
                    <span>{{ "{:,.2f}".format(pw.get("total_amount", 0)) }} €</span>
                  </div>

                  <div class="mt-2">
                    {% for item in pw.get("items", []) %}
                      <div class="d-flex justify-content-between">
                        <span>{{ item.get("label", "—") }} ({{ item.get("percent", 0) }}%)</span>
                        <span>{{ "{:,.2f}".format(item.get("amount", 0)) }} €</span>
                      </div>
                    {% endfor %}
                  </div>
                </div>
              {% endif %}

              {% set it = analysis.get("income_tax") or {} %}
              {% if it.get("amount") and it.get("amount") != 0 %}
                <div class="mt-2">
                  <div class="d-flex justify-content-between fw-semibold">
                    <span>Φόρος Εισοδήματος ({{ it.get("rate_percent", 0) }}%)</span>
                    <span>{{ "{:,.2f}".format(it.get("amount", 0)) }} €</span>
                  </div>
                  <div class="text-muted" style="font-size: 12px;">
                    Υπολογισμός: [Σύνολο - Κρατήσεις] × {{ it.get("rate_percent", 0) }}%
                  </div>
                </div>
              {% endif %}

              {% if analysis.get("vat_amount") and analysis.get("vat_amount") != 0 %}
                <div class="mt-2">
                  <div class="d-flex justify-content-between fw-semibold">
                    <span>ΦΠΑ ({{ analysis.get("vat_percent", 0) }}%)</span>
                    <span>{{ "{:,.2f}".format(analysis.get("vat_amount", 0)) }} €</span>
                  </div>
                </div>
              {% endif %}

              <div class="mt-2 pt-2 border-top d-flex justify-content-between fw-bold">
                <span>Τελικό Πληρωτέο Ποσό</span>
                <span>{{ "{:,.2f}".format(analysis.get("payable_total", 0)) }} €</span>
              </div>

            </div>
          </div>
        </div>
      </div>

      <hr class="my-3">

      <div class="row g-3">
        <div class="col-12 col-lg-8">
          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Δέσμευσης</label>
            <div class="col-8">
              <input name="hop_commitment" class="form-control form-control-sm"
                     value="{{ procurement.hop_commitment or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Προωθητικού Δέσμευσης 1</label>
            <div class="col-8">
              <input name="hop_forward1_commitment" class="form-control form-control-sm"
                     value="{{ procurement.hop_forward1_commitment or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Προωθητικού Δέσμευσης 2</label>
            <div class="col-8">
              <input name="hop_forward2_commitment" class="form-control form-control-sm"
                     value="{{ procurement.hop_forward2_commitment or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Έγκρισης Δέσμευσης</label>
            <div class="col-8">
              <input name="hop_approval_commitment" class="form-control form-control-sm"
                     value="{{ procurement.hop_approval_commitment or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Προέγκρισης</label>
            <div class="col-8">
              <input name="hop_preapproval" class="form-control form-control-sm"
                     value="{{ procurement.hop_preapproval or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Προωθητικού 1 (Προέγκρισης)</label>
            <div class="col-8">
              <input name="hop_forward1_preapproval" class="form-control form-control-sm"
                     value="{{ procurement.hop_forward1_preapproval or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Προωθητικού 2 (Προέγκρισης)</label>
            <div class="col-8">
              <input name="hop_forward2_preapproval" class="form-control form-control-sm"
                     value="{{ procurement.hop_forward2_preapproval or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Έγκρισης</label>
            <div class="col-8">
              <input name="hop_approval" class="form-control form-control-sm"
                     value="{{ procurement.hop_approval or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΑΥ</label>
            <div class="col-8">
              <input name="aay" class="form-control form-control-sm"
                     value="{{ procurement.aay or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΔΑΜ ΑΑΥ</label>
            <div class="col-8">
              <input name="adam_aay" class="form-control form-control-sm"
                     value="{{ procurement.adam_aay or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΔΑ ΑΑΥ</label>
            <div class="col-8">
              <input name="ada_aay" class="form-control form-control-sm"
                     value="{{ procurement.ada_aay or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Ταυτότητα Εγγράφου Πρόσκλησης</label>
            <div class="col-8">
              <input name="identity_prosklisis" class="form-control form-control-sm"
                     value="{{ procurement.identity_prosklisis or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΔΑΜ ΠΡΟΣΚΛΗΣΗΣ</label>
            <div class="col-8">
              <input name="adam_prosklisis" class="form-control form-control-sm"
                     value="{{ procurement.adam_prosklisis or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          {% if show_all_reports %}
            <hr class="my-3">
            <h3 class="h6 fw-bold mb-3">Στοιχεία Υλοποίησης (από “Όλες”)</h3>

            <div class="mb-2 row align-items-center">
              <label class="col-4 col-form-label col-form-label-sm">Ταυτότητα Εγγράφου Απόφασης Ανάθεσης</label>
              <div class="col-8">
                <input name="identity_apofasis_anathesis" class="form-control form-control-sm"
                       value="{{ procurement.identity_apofasis_anathesis or '' }}" {% if not can_edit %}disabled{% endif %}>
              </div>
            </div>

            <div class="mb-2 row align-items-center">
              <label class="col-4 col-form-label col-form-label-sm">ΑΔΑΜ ΑΠΟΦΑΣΗΣ ΑΝΑΘΕΣΗΣ</label>
              <div class="col-8">
                <input name="adam_apofasis_anathesis" class="form-control form-control-sm"
                       value="{{ procurement.adam_apofasis_anathesis or '' }}" {% if not can_edit %}disabled{% endif %}>
              </div>
            </div>

            <div class="mb-2 row align-items-center">
              <label class="col-4 col-form-label col-form-label-sm">ΑΡΙΘΜΟΣ ΣΥΜΒΑΣΗΣ</label>
              <div class="col-8">
                <input name="contract_number" class="form-control form-control-sm"
                       value="{{ procurement.contract_number or '' }}" {% if not can_edit %}disabled{% endif %}>
              </div>
            </div>

            <div class="mb-2 row align-items-center">
              <label class="col-4 col-form-label col-form-label-sm">ΑΔΑΜ ΣΥΜΒΑΣΗΣ</label>
              <div class="col-8">
                <input name="adam_contract" class="form-control form-control-sm"
                       value="{{ procurement.adam_contract or '' }}" {% if not can_edit %}disabled{% endif %}>
              </div>
            </div>

            <div class="mb-2 row align-items-center">
              <label class="col-4 col-form-label col-form-label-sm">ΑΡΙΘΜΟΣ ΤΙΜΟΛΟΓΙΟΥ</label>
              <div class="col-8">
                <input name="invoice_number" class="form-control form-control-sm"
                       value="{{ procurement.invoice_number or '' }}" {% if not can_edit %}disabled{% endif %}>
              </div>
            </div>

            <div class="mb-2 row align-items-center">
              <label class="col-4 col-form-label col-form-label-sm">ΗΜΕΡΟΜΗΝΙΑ ΤΙΜΟΛΟΓΙΟΥ</label>
              <div class="col-8">
                <input type="date" name="invoice_date" class="form-control form-control-sm"
                       value="{{ procurement.invoice_date.isoformat() if procurement.invoice_date else '' }}"
                       {% if not can_edit %}disabled{% endif %}>
              </div>
            </div>

            <div class="mb-2 row align-items-center">
              <label class="col-4 col-form-label col-form-label-sm">ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΛΑΒΗΣ ΥΛΙΚΩΝ</label>
              <div class="col-8">
                <input type="date" name="materials_receipt_date" class="form-control form-control-sm"
                       value="{{ procurement.materials_receipt_date.isoformat() if procurement.materials_receipt_date else '' }}"
                       {% if not can_edit %}disabled{% endif %}>
              </div>
            </div>

            <div class="mb-2 row align-items-center">
              <label class="col-4 col-form-label col-form-label-sm">ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΛΑΒΗΣ ΤΙΜΟΛΟΓΙΟΥ</label>
              <div class="col-8">
                <input type="date" name="invoice_receipt_date" class="form-control form-control-sm"
                       value="{{ procurement.invoice_receipt_date.isoformat() if procurement.invoice_receipt_date else '' }}"
                       {% if not can_edit %}disabled{% endif %}>
              </div>
            </div>

            <div class="mb-2 row align-items-center">
              <label class="col-4 col-form-label col-form-label-sm">ΑΡΙΘΜΟΣ ΠΡΩΤΟΚΟΛΛΟΥ</label>
              <div class="col-8">
                <input name="protocol_number" class="form-control form-control-sm"
                       value="{{ procurement.protocol_number or '' }}" {% if not can_edit %}disabled{% endif %}>
              </div>
            </div>
          {% endif %}

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Μεταφορά σε Εκκρεμείς Δαπάνες</label>
            <div class="col-8">
              <div class="form-check">
                <input class="form-check-input" type="checkbox" name="send_to_expenses" id="send_to_expenses"
                       {% if procurement.send_to_expenses %}checked{% endif %}
                       {% if not can_edit %}disabled{% endif %}>
                <label class="form-check-label" for="send_to_expenses">
                  Ναι (λειτουργεί μόνο αν υπάρχει ΗΩΠ Έγκρισης)
                </label>
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Κρατήσεις (Περιγραφή)</label>
            <div class="col-8">
              <select name="withholding_profile_id" class="form-select form-select-sm" {% if not can_edit %}disabled{% endif %}>
                <option value="">(—)</option>
                {% for p in withholding_profiles %}
                  <option value="{{ p.id }}" {% if procurement.withholding_profile_id == p.id %}selected{% endif %}>
                    {{ p.description }}
                  </option>
                {% endfor %}
              </select>
              <div class="form-text">Η επιλογή επηρεάζει την Ανάλυση Δαπάνης.</div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΦΠΑ</label>
            <div class="col-8">
              <input name="vat_rate" class="form-control form-control-sm" placeholder="24 ή 0.24"
                     value="{{ procurement.vat_rate if procurement.vat_rate is not none else '' }}"
                     {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

        </div>

        <div class="col-12 col-lg-4">
          <div class="card bg-light border-0 h-100">
            <div class="card-body py-3 small">
              <div class="fw-bold mb-2">Παρατηρήσεις Προμήθειας</div>
              <textarea
                name="procurement_notes"
                class="form-control"
                rows="14"
                {% if not can_edit %}disabled{% endif %}
                placeholder="Παρατηρήσεις χειριστή για την προμήθεια (εσωτερικές σημειώσεις)."
              >{{ procurement.procurement_notes or '' }}</textarea>
              <div class="form-text mt-2">
                Εσωτερικό πεδίο. Δεν επηρεάζει τα ποσά/υπολογισμούς.
              </div>
            </div>
          </div>
        </div>
      </div>

      {% if can_edit %}
        <div class="mt-3">
          <button class="btn btn-primary">Αποθήκευση</button>
        </div>
      {% endif %}
    </form>
  </div>
</div>

<div class="card glass-card shadow-sm border-0 mb-3">
  <div class="card-body">
    <h2 class="h6 fw-bold mb-3">Προμηθευτές</h2>

    {% if can_edit %}
      <form class="row g-2 mb-3" method="post"
            action="{{ url_for('procurements.add_procurement_supplier', procurement_id=procurement.id, next=back_url) }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="next" value="{{ back_url }}">

        <div class="col-12 col-md-4">
          <select name="supplier_id" class="form-select" required>
            <option value="">(επιλέξτε)</option>
            {% for s in suppliers %}
              <option value="{{ s.id }}">{{ s.afm }} - {{ s.name }}</option>
            {% endfor %}
          </select>
        </div>

        <div class="col-12 col-md-2">
          <input type="number" step="0.01" name="offered_amount" class="form-control" placeholder="Ποσό προσφοράς">
        </div>

        <div class="col-12 col-md-2">
          <div class="form-check mt-2">
            <input class="form-check-input" type="checkbox" name="is_winner" id="new_is_winner">
            <label class="form-check-label" for="new_is_winner">Μειοδότης</label>
          </div>
        </div>

        <div class="col-12 col-md-4">
          <textarea name="notes" class="form-control" rows="2"
                    placeholder="Παρατηρήσεις (όροι, διευκρινίσεις, σχόλια)"></textarea>
        </div>

        <div class="col-12">
          <button class="btn btn-outline-primary w-100">Προσθήκη</button>
        </div>
      </form>
    {% endif %}

    {% if procurement.supplies_links %}
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr>
              <th>Προμηθευτής</th>
              <th>Προσφορά</th>
              <th>Μειοδότης</th>
              <th>Παρατηρήσεις</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {% for link in procurement.supplies_links %}
              <tr>
                <td class="small">{{ link.supplier.afm }} - {{ link.supplier.name }}</td>
                <td class="small">
                  {% if link.offered_amount is not none %}
                    {{ "{:,.2f}".format(link.offered_amount) }} €
                  {% else %}
                    —
                  {% endif %}
                </td>
                <td class="small">
                  {% if link.is_winner %}
                    <span class="badge bg-success">ΝΑΙ</span>
                  {% else %}
                    —
                  {% endif %}
                </td>
                <td class="small text-break" style="max-width: 320px;">{{ link.notes or '—' }}</td>
                <td class="text-end">
                  {% if can_edit %}
                    <form method="post"
                          action="{{ url_for('procurements.delete_procurement_supplier',
                            procurement_id=procurement.id, link_id=link.id, next=back_url) }}">
                      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                      <input type="hidden" name="next" value="{{ back_url }}">
                      <button class="btn btn-sm btn-outline-danger">Διαγραφή</button>
                    </form>
                  {% endif %}
                </td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <div class="small text-muted">Δεν υπάρχουν καταχωρημένοι προμηθευτές.</div>
    {% endif %}
  </div>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    <h2 class="h6 fw-bold mb-3">Υλικά / Υπηρεσίες</h2>

    {% if can_edit %}
      <form class="row g-2 mb-3" method="post"
            action="{{ url_for('procurements.add_material_line', procurement_id=procurement.id, next=back_url) }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="next" value="{{ back_url }}">

        <div class="col-12 col-md-4">
          <input name="description" class="form-control" placeholder="Περιγραφή γραμμής" required>
        </div>

        <div class="col-6 col-md-2">
          <select
            name="cpv"
            class="form-select js-select2"
            data-placeholder="Αναζήτηση CPV..."
            title="CPV"
          >
            <option value=""></option>
            {% for r in (cpv_rows or []) %}
              <option value="{{ r.cpv }}">{{ r.cpv }}{% if r.description %} — {{ r.description }}{% endif %}</option>
            {% endfor %}
          </select>
        </div>

        <div class="col-6 col-md-2">
          <input name="nsn" class="form-control" placeholder="NSN">
        </div>
        <div class="col-6 col-md-2">
          <input name="unit" class="form-control" placeholder="Μονάδα">
        </div>
        <div class="col-6 col-md-1">
          <input type="number" step="0.01" name="quantity" class="form-control" placeholder="Ποσότητα">
        </div>
        <div class="col-6 col-md-1">
          <input type="number" step="0.01" name="unit_price" class="form-control" placeholder="Τιμή">
        </div>

        <div class="col-12">
          <button class="btn btn-outline-primary w-100">Προσθήκη</button>
        </div>
      </form>
    {% endif %}

    {% if procurement.materials %}
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr>
              <th>Περιγραφή</th>
              <th>CPV</th>
              <th>NSN</th>
              <th>Μονάδα</th>
              <th class="text-end">Ποσότητα</th>
              <th class="text-end">Τιμή</th>
              <th class="text-end">Σύνολο</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {% for line in procurement.materials %}
              <tr>
                <td class="small">{{ line.description }}</td>
                <td class="small">{{ line.cpv or '—' }}</td>
                <td class="small">{{ line.nsn or '—' }}</td>
                <td class="small">{{ line.unit or '—' }}</td>
                <td class="small text-end">{{ line.quantity }}</td>
                <td class="small text-end">{{ line.unit_price }}</td>
                <td class="small text-end">{{ "{:,.2f}".format(line.total_pre_vat) }} €</td>
                <td class="text-end">
                  {% if can_edit %}
                    <form method="post"
                          action="{{ url_for('procurements.delete_material_line',
                            procurement_id=procurement.id, line_id=line.id, next=back_url) }}">
                      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                      <input type="hidden" name="next" value="{{ back_url }}">
                      <button class="btn btn-sm btn-outline-danger">Διαγραφή</button>
                    </form>
                  {% endif %}
                </td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <div class="small text-muted">Δεν υπάρχουν γραμμές υλικών/υπηρεσιών.</div>
    {% endif %}
  </div>
</div>

<script>
(function() {
  if (!window.jQuery || !jQuery.fn || !jQuery.fn.select2) return;

  jQuery(".js-select2").each(function() {
    const $el = jQuery(this);
    if ($el.data("select2")) return;

    $el.select2({
      theme: "bootstrap-5",
      width: "100%",
      allowClear: true,
      placeholder: $el.data("placeholder") || "(αναζήτηση...)"
    });
  });

  jQuery(".js-ale-select").each(function() {
    const $el = jQuery(this);
    if ($el.data("select2")) return;

    $el.select2({
      theme: "bootstrap-5",
      width: "100%",
      allowClear: true,
      placeholder: $el.data("placeholder") || "(αναζήτηση...)",
      templateResult: function(state) {
        if (!state || !state.element) return state.text;
        return state.text;
      },
      templateSelection: function(state) {
        if (!state || !state.element) return state.text;
        return state.element.getAttribute("data-ale-display") || state.text;
      }
    });
  });

  jQuery(".js-handler-assignment-select").each(function() {
    const $el = jQuery(this);
    if ($el.data("select2")) return;

    $el.select2({
      theme: "bootstrap-5",
      width: "100%",
      allowClear: true,
      placeholder: $el.data("placeholder") || "(αναζήτηση...)",
      templateResult: function(state) {
        if (!state || !state.text) return state.text;
        return state.text;
      },
      templateSelection: function(state) {
        if (!state || !state.element) return state.text;
        return state.element.getAttribute("data-selected-label") || state.text;
      }
    });
  });
})();
</script>

{% endblock %}

```

FILE: .\app\templates\procurements\implementation.html
```html
{% extends "base.html" %}
{% block content %}

{% set vat_pct = analysis.get("vat_percent", "") if analysis else "" %}
{% set back_url = next_url if next_url is defined and next_url else url_for('procurements.pending_expenses') %}

<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">Προμήθεια #{{ procurement.id }} — Τελική Φάση Υλοποίησης</h1>
    <div class="text-muted small">
      Εμφανίζονται μόνο τα απαραίτητα πεδία για υλοποίηση και δαπάνες. Τα υπόλοιπα παραμένουν ως έχουν.
    </div>
  </div>

  <div class="d-flex gap-2 flex-wrap justify-content-end">

    <a
      class="btn btn-sm btn-outline-primary"
      href="{{ url_for('procurements.report_proforma_invoice', procurement_id=procurement.id) }}"
      target="_blank"
      rel="noopener"
      title="Άνοιγμα Προτιμολογίου (PDF)"
    >
      Προτιμολόγιο
    </a>

    <a
      class="btn btn-sm btn-outline-primary"
      href="{{ url_for('procurements.report_award_decision_docx', procurement_id=procurement.id) }}"
      title="Λήψη Απόφασης Ανάθεσης (Word)"
    >
      Απόφαση Ανάθεσης (Word)
    </a>
    <button type="button" class="btn btn-sm btn-outline-primary" disabled title="Σύντομα">
      Σύμβαση
    </button>
    <button type="button" class="btn btn-sm btn-outline-primary" disabled title="Σύντομα">
      Πρωτόκολλο
    </button>
    <button type="button" class="btn btn-sm btn-outline-primary" disabled title="Σύντομα">
      ΚΠΔ
    </button>
    
    <a
      class="btn btn-sm btn-outline-primary"
      href="{{ url_for('procurements.report_expense_transmittal_docx', procurement_id=procurement.id) }}"
      title="Λήψη Διαβιβαστικού Δαπάνης (DOCX)"
    >
      Διαβιβαστικό
    </a>

    <a href="{{ back_url }}" class="btn btn-outline-secondary btn-sm">
      &larr; Επιστροφή
    </a>
  </div>
</div>

<div class="card glass-card shadow-sm border-0 mb-3">
  <div class="card-body">

    <div class="row g-3">
      <div class="col-12 col-lg-8">
        <h2 class="h6 fw-bold mb-3">Βασικά στοιχεία (ως έχουν)</h2>

        <div class="mb-2 row align-items-center">
          <label class="col-4 col-form-label col-form-label-sm">Υπηρεσία</label>
          <div class="col-8">
            <input class="form-control form-control-sm" disabled
                   value="{{ procurement.service_unit.short_name if procurement.service_unit else '' }}">
          </div>
        </div>

        <div class="mb-2 row align-items-center">
          <label class="col-4 col-form-label col-form-label-sm">Α/Α</label>
          <div class="col-8">
            <input class="form-control form-control-sm" disabled value="{{ procurement.serial_no or '' }}">
          </div>
        </div>

        <div class="mb-2 row align-items-center">
          <label class="col-4 col-form-label col-form-label-sm">Σύντομη Περιγραφή</label>
          <div class="col-8">
            <input class="form-control form-control-sm" disabled value="{{ procurement.description or '' }}">
          </div>
        </div>

        <div class="mb-2 row align-items-center">
          <label class="col-4 col-form-label col-form-label-sm">ΑΛΕ</label>
          <div class="col-8">
            <input class="form-control form-control-sm" disabled value="{{ procurement.ale or '' }}">
          </div>
        </div>

        <div class="mb-2 row align-items-center">
          <label class="col-4 col-form-label col-form-label-sm">Κατανομή</label>
          <div class="col-8">
            <input class="form-control form-control-sm" disabled value="{{ procurement.allocation or '' }}">
          </div>
        </div>

        <div class="mb-2 row align-items-center">
          <label class="col-4 col-form-label col-form-label-sm">Τριμηνιαία</label>
          <div class="col-8">
            <input class="form-control form-control-sm" disabled value="{{ procurement.quarterly or '' }}">
          </div>
        </div>

        <div class="mb-2 row align-items-center">
          <label class="col-4 col-form-label col-form-label-sm">Κατάσταση</label>
          <div class="col-8">
            <select name="status_display" class="form-select form-select-sm" disabled>
              <option value="">{{ procurement.status or '' }}</option>
            </select>
            <div class="form-text">Η επεξεργασία γίνεται στα "Πεδία Υλοποίησης" παρακάτω.</div>
          </div>
        </div>

        <div class="mb-2 row align-items-center">
          <label class="col-4 col-form-label col-form-label-sm">Στάδιο</label>
          <div class="col-8">
            <select name="stage_display" class="form-select form-select-sm" disabled>
              <option value="">{{ procurement.stage or '' }}</option>
            </select>
            <div class="form-text">Η επεξεργασία γίνεται στα "Πεδία Υλοποίησης" παρακάτω.</div>
          </div>
        </div>

        <div class="mb-2 row align-items-center">
          <label class="col-4 col-form-label col-form-label-sm">Χειριστής</label>
          <div class="col-8">
            <input class="form-control form-control-sm" disabled value="{{ procurement.handler_display or '' }}">
          </div>
        </div>

      </div>

      <div class="col-12 col-lg-4">
        <div class="card bg-light border-0 h-100">
          <div class="card-body py-3 small">

            <div class="text-center mb-2">
              <div class="fw-bold">Μειοδότης</div>
              <div class="mt-1">{{ procurement.winner_supplier_display or '—' }}</div>
            </div>

            <hr class="my-2">

            <div class="text-center mb-2">
              <div class="fw-bold">Ποσά</div>
            </div>

            <div class="d-flex justify-content-between">
              <span>Σύνολο</span>
              <span class="fw-semibold">
                {% if procurement.sum_total %}{{ "{:,.2f}".format(procurement.sum_total) }} €{% else %}—{% endif %}
              </span>
            </div>
            <div class="d-flex justify-content-between">
              <span>ΦΠΑ ({{ vat_pct }}%)</span>
              <span class="fw-semibold">
                {% if procurement.vat_amount %}{{ "{:,.2f}".format(procurement.vat_amount) }} €{% else %}—{% endif %}
              </span>
            </div>
            <div class="d-flex justify-content-between">
              <span class="fw-bold">Γενικό Σύνολο</span>
              <span class="fw-bold">
                {% if procurement.grand_total %}{{ "{:,.2f}".format(procurement.grand_total) }} €{% else %}—{% endif %}
              </span>
            </div>

            <hr class="my-2">

            <div class="fw-bold mb-2">ΑΝΑΛΥΣΗ ΔΑΠΑΝΗΣ</div>

            <div class="d-flex justify-content-between mb-1">
              <span>Σύνολο</span>
              <span class="fw-semibold">{{ "{:,.2f}".format(analysis.get("sum_total", 0)) }} €</span>
            </div>

            {% set pw = analysis.get("public_withholdings") or {} %}
            {% if pw.get("total_amount") and pw.get("total_amount") != 0 %}
              <div class="mt-2">
                <div class="d-flex justify-content-between fw-semibold">
                  <span>Κρατήσεις υπέρ δημοσίου ({{ pw.get("total_percent", 0) }}%)</span>
                  <span>{{ "{:,.2f}".format(pw.get("total_amount", 0)) }} €</span>
                </div>

                <div class="mt-2">
                  {% for item in pw.get("items", []) %}
                    <div class="d-flex justify-content-between">
                      <span>{{ item.get("label", "—") }} ({{ item.get("percent", 0) }}%)</span>
                      <span>{{ "{:,.2f}".format(item.get("amount", 0)) }} €</span>
                    </div>
                  {% endfor %}
                </div>
              </div>
            {% endif %}

            {% set it = analysis.get("income_tax") or {} %}
            {% if it.get("amount") and it.get("amount") != 0 %}
              <div class="mt-2">
                <div class="d-flex justify-content-between fw-semibold">
                  <span>Φόρος Εισοδήματος ({{ it.get("rate_percent", 0) }}%)</span>
                  <span>{{ "{:,.2f}".format(it.get("amount", 0)) }} €</span>
                </div>
              </div>
            {% endif %}

            {% if analysis.get("vat_amount") and analysis.get("vat_amount") != 0 %}
              <div class="mt-2">
                <div class="d-flex justify-content-between fw-semibold">
                  <span>ΦΠΑ ({{ vat_pct }}%)</span>
                  <span>{{ "{:,.2f}".format(analysis.get("vat_amount", 0)) }} €</span>
                </div>
              </div>
            {% endif %}

            <div class="mt-2 pt-2 border-top d-flex justify-content-between fw-bold">
              <span>Τελικό Πληρωτέο Ποσό</span>
              <span>{{ "{:,.2f}".format(analysis.get("payable_total", 0)) }} €</span>
            </div>

          </div>
        </div>
      </div>
    </div>

    <hr class="my-3">

    <h2 class="h6 fw-bold mb-3">Πεδία υλοποίησης (μόνο αυτά αλλάζουν)</h2>

    <form method="post">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <input type="hidden" name="next" value="{{ back_url }}">

      <div class="row g-3">
        <div class="col-12 col-lg-8">

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Κατάσταση</label>
            <div class="col-8">
              <select name="status" class="form-select form-select-sm" {% if not can_edit %}disabled{% endif %}>
                <option value="">(—)</option>
                {% for s in (status_options or []) %}
                  <option value="{{ s }}" {% if procurement.status == s %}selected{% endif %}>{{ s }}</option>
                {% endfor %}
              </select>
              <div class="form-text">Επιτρεπτές τιμές από τις επιλογές (seed-options).</div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Στάδιο</label>
            <div class="col-8">
              <select name="stage" class="form-select form-select-sm" {% if not can_edit %}disabled{% endif %}>
                <option value="">(—)</option>
                {% for st in (stage_options or []) %}
                  <option value="{{ st }}" {% if procurement.stage == st %}selected{% endif %}>{{ st }}</option>
                {% endfor %}
              </select>
              <div class="form-text">Επιτρεπτές τιμές από τις επιλογές (seed-options).</div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Επιτροπή Προμηθειών</label>
            <div class="col-8">
              <select
                name="committee_id"
                class="form-select form-select-sm js-select2"
                data-placeholder="Αναζήτηση Επιτροπής..."
                {% if not can_edit %}disabled{% endif %}
              >
                <option value=""></option>
                {% for c in committees %}
                  <option value="{{ c.id }}" {% if procurement.committee_id == c.id %}selected{% endif %}>
                    {{ c.description }}
                  </option>
                {% endfor %}
              </select>
              <div class="form-text">Εμφανίζονται μόνο οι ενεργές επιτροπές της υπηρεσίας.</div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Τύπος Προμήθειας</label>
            <div class="col-8">
              <select
                name="income_tax_rule_id"
                class="form-select form-select-sm js-select2"
                data-placeholder="Αναζήτηση Τύπου..."
                {% if not can_edit %}disabled{% endif %}
              >
                <option value=""></option>
                {% for r in income_tax_rules %}
                  <option value="{{ r.id }}" {% if procurement.income_tax_rule_id == r.id %}selected{% endif %}>
                    {{ r.description }} ({{ r.rate_percent }}% > {{ r.threshold_amount }}€)
                  </option>
                {% endfor %}
              </select>
              <div class="form-text">Η επιλογή χρησιμοποιείται στον υπολογισμό ΦΕ.</div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Προέγκρισης</label>
            <div class="col-8">
              <input name="hop_preapproval" class="form-control form-control-sm"
                     value="{{ procurement.hop_preapproval or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Έγκρισης</label>
            <div class="col-8">
              <input name="hop_approval" class="form-control form-control-sm"
                     value="{{ procurement.hop_approval or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΑΥ</label>
            <div class="col-8">
              <input name="aay" class="form-control form-control-sm"
                     value="{{ procurement.aay or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΔΑΜ ΑΑΥ</label>
            <div class="col-8">
              <input name="adam_aay" class="form-control form-control-sm"
                     value="{{ procurement.adam_aay or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΔΑ ΑΑΥ</label>
            <div class="col-8">
              <input name="ada_aay" class="form-control form-control-sm"
                     value="{{ procurement.ada_aay or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Ταυτότητα Εγγράφου Πρόσκλησης</label>
            <div class="col-8">
              <input name="identity_prosklisis" class="form-control form-control-sm"
                     value="{{ procurement.identity_prosklisis or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΔΑΜ ΠΡΟΣΚΛΗΣΗΣ</label>
            <div class="col-8">
              <input name="adam_prosklisis" class="form-control form-control-sm"
                     value="{{ procurement.adam_prosklisis or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Μεταφορά σε Εκκρεμείς Δαπάνες</label>
            <div class="col-8">
              <div class="form-check">
                <input class="form-check-input" type="checkbox" name="send_to_expenses" id="send_to_expenses"
                       {% if procurement.send_to_expenses %}checked{% endif %}
                       {% if not can_edit %}disabled{% endif %}>
                <label class="form-check-label" for="send_to_expenses">
                  Ναι (λειτουργεί μόνο αν υπάρχει ΗΩΠ Έγκρισης)
                </label>
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Κρατήσεις (Περιγραφή)</label>
            <div class="col-8">
              <select name="withholding_profile_id" class="form-select form-select-sm" {% if not can_edit %}disabled{% endif %}>
                <option value="">(—)</option>
                {% for p in withholding_profiles %}
                  <option value="{{ p.id }}" {% if procurement.withholding_profile_id == p.id %}selected{% endif %}>
                    {{ p.description }}
                  </option>
                {% endfor %}
              </select>
              <div class="form-text">Η επιλογή επηρεάζει την Ανάλυση Δαπάνης.</div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΦΠΑ</label>
            <div class="col-8">
              <input name="vat_rate" class="form-control form-control-sm" placeholder="24 ή 0.24"
                     value="{{ procurement.vat_rate if procurement.vat_rate is not none else '' }}"
                     {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <hr class="my-3">
          <h3 class="h6 fw-bold mb-3">Στοιχεία Υλοποίησης (νέα)</h3>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Ταυτότητα Εγγράφου Απόφασης Ανάθεσης</label>
            <div class="col-8">
              <input name="identity_apofasis_anathesis" class="form-control form-control-sm"
                     value="{{ procurement.identity_apofasis_anathesis or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΔΑΜ ΑΠΟΦΑΣΗΣ ΑΝΑΘΕΣΗΣ</label>
            <div class="col-8">
              <input name="adam_apofasis_anathesis" class="form-control form-control-sm"
                     value="{{ procurement.adam_apofasis_anathesis or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΡΙΘΜΟΣ ΣΥΜΒΑΣΗΣ</label>
            <div class="col-8">
              <input name="contract_number" class="form-control form-control-sm"
                     value="{{ procurement.contract_number or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΔΑΜ ΣΥΜΒΑΣΗΣ</label>
            <div class="col-8">
              <input name="adam_contract" class="form-control form-control-sm"
                     value="{{ procurement.adam_contract or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΡΙΘΜΟΣ ΤΙΜΟΛΟΓΙΟΥ</label>
            <div class="col-8">
              <input name="invoice_number" class="form-control form-control-sm"
                     value="{{ procurement.invoice_number or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΜΕΡΟΜΗΝΙΑ ΤΙΜΟΛΟΓΙΟΥ</label>
            <div class="col-8">
              <input type="date" name="invoice_date" class="form-control form-control-sm"
                     value="{{ procurement.invoice_date.isoformat() if procurement.invoice_date else '' }}"
                     {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΛΑΒΗΣ ΥΛΙΚΩΝ</label>
            <div class="col-8">
              <input type="date" name="materials_receipt_date" class="form-control form-control-sm"
                     value="{{ procurement.materials_receipt_date.isoformat() if procurement.materials_receipt_date else '' }}"
                     {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΛΑΒΗΣ ΤΙΜΟΛΟΓΙΟΥ</label>
            <div class="col-8">
              <input type="date" name="invoice_receipt_date" class="form-control form-control-sm"
                     value="{{ procurement.invoice_receipt_date.isoformat() if procurement.invoice_receipt_date else '' }}"
                     {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΡΙΘΜΟΣ ΠΡΩΤΟΚΟΛΛΟΥ</label>
            <div class="col-8">
              <input name="protocol_number" class="form-control form-control-sm"
                     value="{{ procurement.protocol_number or '' }}" {% if not can_edit %}disabled{% endif %}>
            </div>
          </div>

          {% if can_edit %}
            <div class="mt-3">
              <button class="btn btn-primary">Αποθήκευση</button>
            </div>
          {% endif %}

        </div>

        <div class="col-12 col-lg-4">
          <div class="card bg-light border-0 h-100">
            <div class="card-body py-3 small">
              <div class="fw-bold mb-2">Παρατηρήσεις Προμήθειας</div>
              <textarea
                name="procurement_notes"
                class="form-control"
                rows="14"
                {% if not can_edit %}disabled{% endif %}
                placeholder="Παρατηρήσεις χειριστή για την προμήθεια (εσωτερικές σημειώσεις)."
              >{{ procurement.procurement_notes or '' }}</textarea>
              <div class="form-text mt-2">
                Εσωτερικό πεδίο. Δεν επηρεάζει τα ποσά/υπολογισμούς.
              </div>
            </div>
          </div>
        </div>

      </div>
    </form>

  </div>
</div>

<div class="card glass-card shadow-sm border-0 mb-3">
  <div class="card-body">
    <h2 class="h6 fw-bold mb-3">Προμηθευτές (ως έχουν)</h2>

    {% if procurement.supplies_links %}
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr>
              <th>Προμηθευτής</th>
              <th>Προσφορά</th>
              <th>Μειοδότης</th>
              <th>Παρατηρήσεις</th>
            </tr>
          </thead>
          <tbody>
            {% for link in procurement.supplies_links %}
              <tr>
                <td class="small">{{ link.supplier.afm }} - {{ link.supplier.name }}</td>
                <td class="small">
                  {% if link.offered_amount is not none %}
                    {{ "{:,.2f}".format(link.offered_amount) }} €
                  {% else %}
                    —
                  {% endif %}
                </td>
                <td class="small">
                  {% if link.is_winner %}
                    <span class="badge bg-success">ΝΑΙ</span>
                  {% else %}
                    —
                  {% endif %}
                </td>
                <td class="small text-break" style="max-width: 420px;">{{ link.notes or '—' }}</td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <div class="small text-muted">Δεν υπάρχουν καταχωρημένοι προμηθευτές.</div>
    {% endif %}
  </div>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    <h2 class="h6 fw-bold mb-3">Υλικά / Υπηρεσίες (ως έχουν)</h2>

    {% if procurement.materials %}
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr>
              <th>Περιγραφή</th>
              <th>CPV</th>
              <th>NSN</th>
              <th>Μονάδα</th>
              <th class="text-end">Ποσότητα</th>
              <th class="text-end">Τιμή</th>
              <th class="text-end">Σύνολο</th>
            </tr>
          </thead>
          <tbody>
            {% for line in procurement.materials %}
              <tr>
                <td class="small">{{ line.description }}</td>
                <td class="small">{{ line.cpv or '—' }}</td>
                <td class="small">{{ line.nsn or '—' }}</td>
                <td class="small">{{ line.unit or '—' }}</td>
                <td class="small text-end">{{ line.quantity }}</td>
                <td class="small text-end">{{ line.unit_price }}</td>
                <td class="small text-end">{{ "{:,.2f}".format(line.total_pre_vat) }} €</td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <div class="small text-muted">Δεν υπάρχουν γραμμές υλικών/υπηρεσιών.</div>
    {% endif %}
  </div>
</div>

<script>
(function() {
  if (!window.jQuery || !jQuery.fn || !jQuery.fn.select2) return;

  jQuery(".js-select2").each(function() {
    const $el = jQuery(this);
    if ($el.data("select2")) return;

    $el.select2({
      theme: "bootstrap-5",
      width: "100%",
      allowClear: true,
      placeholder: $el.data("placeholder") || "(αναζήτηση...)"
    });
  });
})();
</script>

{% endblock %}

```

FILE: .\app\templates\procurements\list.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">{{ page_title or "Λίστα Προμηθειών" }}</h1>
    {% if page_subtitle %}
      <div class="text-muted small">{{ page_subtitle }}</div>
    {% endif %}
  </div>

  {% if allow_create %}
    <a href="{{ url_for('procurements.create_procurement') }}" class="btn btn-primary btn-sm">
      Νέα Προμήθεια
    </a>
  {% endif %}
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    <div class="table-responsive">
      <form id="filters-form" method="get" action="{{ request.path }}" class="mb-0">
        <table class="table table-sm align-middle mb-0 procurements-table">
          <thead>
            <tr class="text-center">
              <th>Υπηρεσία</th>
              <th>Α/Α</th>
              <th>Σύντομη Περιγραφή</th>
              <th>ΑΛΕ</th>
              <th>ΑΦΜ</th>
              <th>Μειοδότης</th>
              <th>ΗΩΠ Προέγκρισης</th>
              <th>ΗΩΠ Έγκρισης</th>
              <th>ΑΑΥ</th>
              <th>ΠΟΣΟ</th>
              <th>Κατάσταση</th>
              <th>Στάδιο</th>
              {% if show_open_button %}
                <th></th>
              {% endif %}
            </tr>

            <tr class="table-light text-center">
              <th style="min-width:190px;">
                <select name="service_unit_id" class="form-select form-select-sm js-filter text-center">
                  <option value="">Όλες</option>
                  {% for su in (service_units or []) %}
                    {% set su_id = su.id|string %}
                    <option value="{{ su_id }}" {% if request.args.get('service_unit_id') == su_id %}selected{% endif %}>
                      {{ su.short_name or su.description }}
                    </option>
                  {% endfor %}
                </select>
              </th>

              <th style="min-width:90px;">
                <input name="serial_no"
                       value="{{ request.args.get('serial_no','') }}"
                       class="form-control form-control-sm js-filter js-filter-text text-center"
                       placeholder="..."
                       autocomplete="off">
              </th>

              <th style="min-width:240px;">
                <input name="description"
                       value="{{ request.args.get('description','') }}"
                       class="form-control form-control-sm js-filter js-filter-text text-center"
                       placeholder="..."
                       autocomplete="off">
              </th>

              <th style="min-width:90px;">
                <input name="ale"
                       value="{{ request.args.get('ale','') }}"
                       class="form-control form-control-sm js-filter js-filter-text text-center"
                       placeholder="..."
                       autocomplete="off">
              </th>

              <th style="min-width:110px;">
                <input name="supplier_afm"
                       value="{{ request.args.get('supplier_afm','') }}"
                       class="form-control form-control-sm js-filter js-filter-text text-center"
                       placeholder="..."
                       autocomplete="off">
              </th>

              <th style="min-width:200px;">
                <input name="supplier_name"
                       value="{{ request.args.get('supplier_name','') }}"
                       class="form-control form-control-sm js-filter js-filter-text text-center"
                       placeholder="..."
                       autocomplete="off">
              </th>

              <th style="min-width:150px;">
                <input name="hop_preapproval"
                       value="{{ request.args.get('hop_preapproval','') }}"
                       class="form-control form-control-sm js-filter js-filter-text text-center"
                       placeholder="..."
                       autocomplete="off">
              </th>

              <th style="min-width:150px;">
                <input name="hop_approval"
                       value="{{ request.args.get('hop_approval','') }}"
                       class="form-control form-control-sm js-filter js-filter-text text-center"
                       placeholder="..."
                       autocomplete="off">
              </th>

              <th style="min-width:110px;">
                <input name="aay"
                       value="{{ request.args.get('aay','') }}"
                       class="form-control form-control-sm js-filter js-filter-text text-center"
                       placeholder="..."
                       autocomplete="off">
              </th>

              <th style="min-width:120px;">
                <div class="text-muted small">—</div>
              </th>

              <th style="min-width:160px;">
                <select name="status" class="form-select form-select-sm js-filter text-center">
                  <option value="">Όλες</option>
                  {% for s in (status_options or []) %}
                    <option value="{{ s }}" {% if request.args.get('status') == s %}selected{% endif %}>
                      {{ s }}
                    </option>
                  {% endfor %}
                </select>
              </th>

              <th style="min-width:180px;">
                <select name="stage" class="form-select form-select-sm js-filter text-center">
                  <option value="">Όλα</option>
                  {% for st in (stage_options or []) %}
                    <option value="{{ st }}" {% if request.args.get('stage') == st %}selected{% endif %}>
                      {{ st }}
                    </option>
                  {% endfor %}
                </select>
              </th>

              {% if show_open_button %}
                <th class="text-end" style="min-width:240px;">
                  <a href="{{ request.path }}" class="btn btn-sm btn-outline-secondary">
                    Καθαρισμός
                  </a>
                </th>
              {% endif %}
            </tr>
          </thead>

          <tbody>
            {% if procurements %}
              {% for p in procurements %}
                {% set row_class = procurement_row_class(p) if enable_row_colors else "" %}

                <tr class="{{ row_class }} text-center">
                  <td>
                    {{ p.service_unit.short_name or p.service_unit.description if p.service_unit else '—' }}
                  </td>
                  <td>{{ p.serial_no or '—' }}</td>
                  <td>{{ p.description or '—' }}</td>
                  <td>{{ p.ale or '—' }}</td>

                  <td>{{ p.winner_supplier_afm or '—' }}</td>
                  <td>{{ p.winner_supplier_name or '—' }}</td>

                  <td>{{ p.hop_preapproval or '—' }}</td>
                  <td>{{ p.hop_approval or '—' }}</td>
                  <td>{{ p.aay or '—' }}</td>

                  <td>
                    {% if p.grand_total is not none %}
                      {{ "{:,.2f}".format(p.grand_total) }} €
                    {% else %}
                      —
                    {% endif %}
                  </td>

                  <td>{{ p.status or '—' }}</td>
                  <td>{{ p.stage or '—' }}</td>

                  {% if show_open_button %}
                    <td class="text-end open-cell">
                      <div class="d-inline-flex gap-2">
                        {% if open_mode == "implementation" %}
                          <a href="{{ url_for('procurements.implementation_procurement', procurement_id=p.id, next=request.full_path) }}"
                             class="btn btn-sm btn-outline-secondary">
                            Άνοιγμα
                          </a>
                        {% else %}
                          <a href="{{ url_for('procurements.edit_procurement', procurement_id=p.id, next=request.full_path) }}"
                             class="btn btn-sm btn-outline-secondary">
                            Άνοιγμα
                          </a>
                        {% endif %}

                        {% if allow_delete %}
                          <form method="post"
                                action="{{ url_for('procurements.delete_procurement', procurement_id=p.id) }}"
                                class="d-inline js-delete-procurement-form">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            <input type="hidden" name="next" value="{{ request.full_path }}">
                            <input type="hidden" name="delete_origin" value="all_procurements">
                            <button type="submit"
                                    class="btn btn-sm btn-outline-danger"
                                    data-procurement-label="{{ p.serial_no or p.id }}">
                              Διαγραφή
                            </button>
                          </form>
                        {% endif %}
                      </div>
                    </td>
                  {% endif %}
                </tr>
              {% endfor %}
            {% else %}
              <tr>
                <td colspan="{{ 13 if show_open_button else 12 }}" class="text-center text-muted py-3">
                  Δεν υπάρχουν εγγραφές.
                </td>
              </tr>
            {% endif %}
          </tbody>
        </table>
      </form>
    </div>
  </div>
</div>

<script>
(function() {
  const form = document.getElementById("filters-form");
  if (!form) return;

  let t = null;
  const debounceMs = 450;

  function submitNow() {
    try { form.requestSubmit(); }
    catch (e) { form.submit(); }
  }

  function debounceSubmit() {
    if (t) window.clearTimeout(t);
    t = window.setTimeout(submitNow, debounceMs);
  }

  form.querySelectorAll(".js-filter:not(.js-filter-text)").forEach(el => {
    el.addEventListener("change", () => submitNow());
  });

  form.querySelectorAll(".js-filter-text").forEach(el => {
    el.addEventListener("input", () => debounceSubmit());
    el.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        submitNow();
      }
    });
  });
})();

(function() {
  document.querySelectorAll(".js-delete-procurement-form").forEach(form => {
    form.addEventListener("submit", function(ev) {
      const btn = form.querySelector("button[type='submit']");
      const label = btn?.getAttribute("data-procurement-label") || "τη συγκεκριμένη προμήθεια";
      const ok = window.confirm(
        `Είσαι βέβαιος ότι θέλεις να διαγράψεις την προμήθεια ${label}; Η ενέργεια δεν αναιρείται.`
      );
      if (!ok) {
        ev.preventDefault();
      }
    });
  });
})();
</script>
{% endblock %}


```

FILE: .\app\templates\procurements\new.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">Νέα Προμήθεια</h1>
    <div class="text-muted small">Δημιουργία νέας προμήθειας (με workflow πεδία).</div>
  </div>
  <a href="{{ url_for('procurements.inbox_procurements') }}" class="btn btn-outline-secondary btn-sm">
    &larr; Επιστροφή
  </a>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    <form method="post">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

      <div class="row g-3">
        <div class="col-12 col-lg-8">

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Υπηρεσία</label>
            <div class="col-8">
              {% if current_user.is_admin %}
                <select name="service_unit_id" class="form-select form-select-sm">
                  <option value="">(επιλέξτε)</option>
                  {% for su in service_units %}
                    <option value="{{ su.id }}">{{ su.short_name or su.description }}</option>
                  {% endfor %}
                </select>
              {% else %}
                <input type="text" class="form-control form-control-sm"
                       value="{{ current_user.service_unit.short_name if current_user.service_unit else '' }}" disabled>
              {% endif %}
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Α/Α</label>
            <div class="col-8">
              <input type="text" name="serial_no" class="form-control form-control-sm">
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Τύπος Προμήθειας</label>
            <div class="col-8">
              <select name="income_tax_rule_id" class="form-select form-select-sm">
                <option value="">(—)</option>
                {% for r in income_tax_rules %}
                  <option value="{{ r.id }}">{{ r.description }} ({{ r.rate_percent }}% > {{ r.threshold_amount }}€)</option>
                {% endfor %}
              </select>
              <div class="form-text">Η επιλογή αυτή χρησιμοποιείται στον υπολογισμό ΦΕ.</div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Σύντομη Περιγραφή *</label>
            <div class="col-8">
              <input type="text" name="description" class="form-control form-control-sm" required>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΛΕ</label>
            <div class="col-8">
              <select
                name="ale"
                class="form-select form-select-sm js-ale-select"
                data-placeholder="Αναζήτηση ΑΛΕ..."
              >
                <option value=""></option>
                {% for r in (ale_rows or []) %}
                  {% set ale_display = r.ale ~ ('/' ~ r.responsibility if r.responsibility else '') %}
                  <option value="{{ r.ale }}"
                          data-ale-display="{{ ale_display }}">
                    {{ ale_display }}{% if r.description %} — {{ r.description }}{% endif %}
                  </option>
                {% endfor %}
              </select>
              <div class="form-text">Πηγή: Ρυθμίσεις → ΑΛΕ-ΚΑΕ.</div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Κατανομή</label>
            <div class="col-8">
              <select name="allocation" class="form-select form-select-sm">
                <option value="">(—)</option>
                {% for v in allocation_options %}
                  <option value="{{ v }}">{{ v }}</option>
                {% endfor %}
              </select>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Τριμηνιαία</label>
            <div class="col-8">
              <select name="quarterly" class="form-select form-select-sm">
                <option value="">(—)</option>
                {% for v in quarterly_options %}
                  <option value="{{ v }}">{{ v }}</option>
                {% endfor %}
              </select>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Κατάσταση</label>
            <div class="col-8">
              <select name="status" class="form-select form-select-sm">
                <option value="">(—)</option>
                {% for v in status_options %}
                  <option value="{{ v }}">{{ v }}</option>
                {% endfor %}
              </select>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Στάδιο</label>
            <div class="col-8">
              <select name="stage" class="form-select form-select-sm">
                <option value="">(—)</option>
                {% for v in stage_options %}
                  <option value="{{ v }}">{{ v }}</option>
                {% endfor %}
              </select>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Χειριστής</label>
            <div class="col-8">
              <select
                name="handler_assignment_id"
                class="form-select form-select-sm js-handler-assignment-select"
                data-placeholder="Αναζήτηση Χειριστή..."
              >
                <option value=""></option>
                {% for a in handler_assignments %}
                  <option
                    value="{{ a.id }}"
                    data-selected-label="{{ a.display_selected_label() }}"
                  >
                    {{ a.display_option_label() }}
                  </option>
                {% endfor %}
              </select>
              <div class="form-text">
                Αναζήτηση με μορφή: ΒΑΘΜΟΣ ΕΙΔΙΚΟΤΗΤΑ ΟΝΟΜΑ ΕΠΩΝΥΜΟ / ΤΜΗΜΑ / ΔΙΕΥΘΥΝΣΗ.
                Μετά την επιλογή εμφανίζεται: ΒΑΘΜΟΣ ΕΙΔΙΚΟΤΗΤΑ ΟΝΟΜΑ ΕΠΩΝΥΜΟ / ΤΜΗΜΑ.
              </div>
            </div>
          </div>

        </div>

        <div class="col-12 col-lg-4">
          <div class="card bg-light border-0 h-100">
            <div class="card-body py-3 small">
              <div class="fw-bold mb-2">Κανόνες</div>
              <ul class="mb-0">
                <li>Ακυρωμένες: εμφανίζονται μόνο στις “Όλες”.</li>
                <li>Για “Εκκρεμείς Δαπάνες”: απαιτείται ΗΩΠ Έγκρισης + επιλογή μεταφοράς.</li>
                <li>Η υπηρεσία non-admin ορίζεται αυτόματα.</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      <hr class="my-3">

      <div class="row g-3">
        <div class="col-12 col-lg-8">

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Δέσμευσης</label>
            <div class="col-8"><input name="hop_commitment" class="form-control form-control-sm"></div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Προωθητικού Δέσμευσης 1</label>
            <div class="col-8"><input name="hop_forward1_commitment" class="form-control form-control-sm"></div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Προωθητικού Δέσμευσης 2</label>
            <div class="col-8"><input name="hop_forward2_commitment" class="form-control form-control-sm"></div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Έγκρισης Δέσμευσης</label>
            <div class="col-8"><input name="hop_approval_commitment" class="form-control form-control-sm"></div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Προέγκρισης</label>
            <div class="col-8"><input name="hop_preapproval" class="form-control form-control-sm"></div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Προωθητικού 1 (Προέγκρισης)</label>
            <div class="col-8"><input name="hop_forward1_preapproval" class="form-control form-control-sm"></div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Προωθητικού 2 (Προέγκρισης)</label>
            <div class="col-8"><input name="hop_forward2_preapproval" class="form-control form-control-sm"></div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΗΩΠ Έγκρισης</label>
            <div class="col-8"><input name="hop_approval" class="form-control form-control-sm"></div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΑΥ</label>
            <div class="col-8"><input name="aay" class="form-control form-control-sm"></div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Μεταφορά σε Εκκρεμείς Δαπάνες</label>
            <div class="col-8">
              <div class="form-check">
                <input class="form-check-input" type="checkbox" name="send_to_expenses" id="send_to_expenses">
                <label class="form-check-label" for="send_to_expenses">
                  Ναι (λειτουργεί μόνο αν υπάρχει ΗΩΠ Έγκρισης)
                </label>
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Κρατήσεις (Περιγραφή)</label>
            <div class="col-8">
              <select name="withholding_profile_id" class="form-select form-select-sm">
                <option value="">(—)</option>
                {% for p in withholding_profiles %}
                  <option value="{{ p.id }}">{{ p.description }}</option>
                {% endfor %}
              </select>
              <div class="form-text">Επιλέγεται η περιγραφή κρατήσεων που θα χρησιμοποιηθεί στην ανάλυση δαπάνης.</div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΦΠΑ</label>
            <div class="col-8">
              <input name="vat_rate" class="form-control form-control-sm" placeholder="24 ή 0.24">
            </div>
          </div>

        </div>

        <div class="col-12 col-lg-4">
          <div class="card bg-light border-0 h-100">
            <div class="card-body py-3 small">
              <div class="fw-bold mb-2">Παρατηρήσεις Προμήθειας</div>
              <textarea
                name="procurement_notes"
                class="form-control"
                rows="14"
                placeholder="Παρατηρήσεις χειριστή για την προμήθεια (εσωτερικές σημειώσεις)."
              ></textarea>
              <div class="form-text mt-2">
                Εσωτερικό πεδίο. Δεν επηρεάζει τα ποσά/υπολογισμούς.
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-3">
        <button class="btn btn-primary">Δημιουργία</button>
      </div>

    </form>
  </div>
</div>

<script>
(function() {
  if (!window.jQuery || !jQuery.fn || !jQuery.fn.select2) return;

  jQuery(".js-ale-select").each(function() {
    const $el = jQuery(this);
    if ($el.data("select2")) return;

    $el.select2({
      theme: "bootstrap-5",
      width: "100%",
      allowClear: true,
      placeholder: $el.data("placeholder") || "(αναζήτηση...)",
      templateResult: function(state) {
        if (!state || !state.element) return state.text;
        return state.text;
      },
      templateSelection: function(state) {
        if (!state || !state.element) return state.text;
        return state.element.getAttribute("data-ale-display") || state.text;
      }
    });
  });

  jQuery(".js-handler-assignment-select").each(function() {
    const $el = jQuery(this);
    if ($el.data("select2")) return;

    $el.select2({
      theme: "bootstrap-5",
      width: "100%",
      allowClear: true,
      placeholder: $el.data("placeholder") || "(αναζήτηση...)",
      templateResult: function(state) {
        if (!state || !state.text) return state.text;
        return state.text;
      },
      templateSelection: function(state) {
        if (!state || !state.element) return state.text;
        return state.element.getAttribute("data-selected-label") || state.text;
      }
    });
  });
})();
</script>
{% endblock %}

```

FILE: .\app\templates\settings\ale_kae.html
```html
{% extends "base.html" %}
{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">ΑΛΕ-ΚΑΕ</h1>
    <div class="text-muted small">Admin-only λίστα ΑΛΕ-ΚΑΕ με δυνατότητα εισαγωγής Excel.</div>
  </div>
</div>

<div class="card glass-card shadow-sm border-0 mb-3">
  <div class="card-body">
    <div class="d-flex flex-column flex-md-row align-items-start align-items-md-end justify-content-between gap-2">
      <div class="small text-muted">
        Excel headers: <span class="fw-semibold">ΑΛΕ</span>, ΠΑΛΙΟΣ ΚΑΕ, ΠΕΡΙΓΡΑΦΗ, ΑΡΜΟΔΙΟΤΗΤΑΣ
      </div>
      <form method="post" action="{{ url_for('settings.ale_kae_import') }}" enctype="multipart/form-data" class="d-flex gap-2">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="file" name="file" accept=".xlsx" class="form-control form-control-sm" required>
        <button class="btn btn-outline-primary btn-sm">Εισαγωγή Excel</button>
      </form>
    </div>
  </div>
</div>

<div class="card glass-card shadow-sm border-0 mb-3">
  <div class="card-body">
    <h2 class="h6 fw-bold mb-3">Νέα Εγγραφή</h2>

    <form method="post" action="{{ url_for('settings.ale_kae') }}">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <input type="hidden" name="action" value="create">

      <div class="row g-2">
        <div class="col-12 col-md-2">
          <label class="form-label small">ΑΛΕ *</label>
          <input name="ale" class="form-control form-control-sm" required>
        </div>

        <div class="col-12 col-md-2">
          <label class="form-label small">ΠΑΛΙΟΣ ΚΑΕ</label>
          <input name="old_kae" class="form-control form-control-sm">
        </div>

        <div class="col-12 col-md-5">
          <label class="form-label small">ΠΕΡΙΓΡΑΦΗ</label>
          <input name="description" class="form-control form-control-sm">
        </div>

        <div class="col-12 col-md-3">
          <label class="form-label small">ΑΡΜΟΔΙΟΤΗΤΑΣ</label>
          <input name="responsibility" class="form-control form-control-sm">
        </div>

        <div class="col-12">
          <button class="btn btn-primary btn-sm">Προσθήκη</button>
        </div>
      </div>
    </form>
  </div>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    <h2 class="h6 fw-bold mb-3">Υπάρχουσες Εγγραφές</h2>

    {% if rows %}
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr>
              <th>ΑΛΕ</th>
              <th>ΠΑΛΙΟΣ ΚΑΕ</th>
              <th>ΠΕΡΙΓΡΑΦΗ</th>
              <th>ΑΡΜΟΔΙΟΤΗΤΑΣ</th>
              <th class="text-end"></th>
            </tr>
          </thead>
          <tbody>
            {% for r in rows %}
              <tr>
                <td style="min-width:140px;">
                  <form method="post" action="{{ url_for('settings.ale_kae') }}" class="d-flex gap-2">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <input type="hidden" name="action" value="update">
                    <input type="hidden" name="id" value="{{ r.id }}">
                    <input name="ale" class="form-control form-control-sm" value="{{ r.ale }}" required>
                </td>
                <td style="min-width:160px;">
                    <input name="old_kae" class="form-control form-control-sm" value="{{ r.old_kae or '' }}">
                </td>
                <td style="min-width:360px;">
                    <input name="description" class="form-control form-control-sm" value="{{ r.description or '' }}">
                </td>
                <td style="min-width:220px;">
                    <input name="responsibility" class="form-control form-control-sm" value="{{ r.responsibility or '' }}">
                </td>
                <td class="text-end" style="white-space:nowrap;">
                    <button class="btn btn-sm btn-outline-primary me-1">Αποθήκευση</button>
                  </form>

                  <form method="post" action="{{ url_for('settings.ale_kae') }}" class="d-inline">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <input type="hidden" name="action" value="delete">
                    <input type="hidden" name="id" value="{{ r.id }}">
                    <button class="btn btn-sm btn-outline-danger" onclick="return confirm('Διαγραφή;');">Διαγραφή</button>
                  </form>
                </td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <div class="small text-muted">Δεν υπάρχουν εγγραφές.</div>
    {% endif %}
  </div>
</div>
{% endblock %}


```

FILE: .\app\templates\settings\committees.html
```html
{% extends "base.html" %}
{% block content %}
<div class="container py-3">
  <div class="d-flex align-items-center justify-content-between mb-3">
    <div>
      <h1 class="h4 fw-bold mb-1">Επιτροπές Προμηθειών</h1>
      <div class="text-muted small">
        Διαχείριση επιτροπών ανά Υπηρεσία.
        Τα μέλη πρέπει να είναι ενεργό προσωπικό της ίδιας Υπηρεσίας.
      </div>
    </div>

    {% if is_admin %}
      <a href="{{ url_for('settings.service_units_list') }}" class="btn btn-outline-secondary btn-sm">
        &larr; Πίσω στις Υπηρεσίες
      </a>
    {% endif %}
  </div>

  {% if is_admin %}
    <div class="card glass-card shadow-sm border-0 mb-3">
      <div class="card-body">
        <form method="get" class="row g-2 align-items-end">
          <div class="col-12 col-md-8">
            <label class="form-label small text-muted mb-1">Υπηρεσία</label>
            <select name="service_unit_id" class="form-select form-select-sm">
              <option value="">(επιλέξτε υπηρεσία)</option>
              {% for su in service_units %}
                <option value="{{ su.id }}" {% if scope_service_unit_id == su.id %}selected{% endif %}>
                  {{ su.short_name or su.description }}
                </option>
              {% endfor %}
            </select>
          </div>

          <div class="col-12 col-md-4">
            <button class="btn btn-outline-primary btn-sm w-100">Φόρτωση</button>
          </div>
        </form>
      </div>
    </div>
  {% endif %}

  {% if scope_service_unit_id %}
    <div class="row g-3">
      <div class="col-12 col-xl-5">
        <div class="card glass-card shadow-sm border-0 h-100">
          <div class="card-header">
            <strong>Νέα Επιτροπή</strong>
          </div>
          <div class="card-body">
            <form method="post" action="{{ request.path }}">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
              <input type="hidden" name="action" value="create">
              <input type="hidden" name="service_unit_id" value="{{ scope_service_unit_id }}">

              <div class="row g-3">
                <div class="col-12">
                  <label class="form-label">Περιγραφή *</label>
                  <input name="description" class="form-control" required>
                </div>

                <div class="col-12">
                  <label class="form-label">Ταυτότητα</label>
                  <input name="identity_text" class="form-control" placeholder="ΑΔ Φ... / Σ....">
                </div>

                <div class="col-12">
                  <label class="form-label">Πρόεδρος</label>
                  <select
                    name="president_personnel_id"
                    class="form-select js-personnel-select"
                    data-placeholder="Αναζήτηση Προέδρου..."
                  >
                    <option value=""></option>
                    {% for p in personnel_list %}
                      <option value="{{ p.id }}">{{ p.display_option_label() }}</option>
                    {% endfor %}
                  </select>
                </div>

                <div class="col-12">
                  <label class="form-label">Α' Μέλος</label>
                  <select
                    name="member1_personnel_id"
                    class="form-select js-personnel-select"
                    data-placeholder="Αναζήτηση Α' Μέλους..."
                  >
                    <option value=""></option>
                    {% for p in personnel_list %}
                      <option value="{{ p.id }}">{{ p.display_option_label() }}</option>
                    {% endfor %}
                  </select>
                </div>

                <div class="col-12">
                  <label class="form-label">Β' Μέλος</label>
                  <select
                    name="member2_personnel_id"
                    class="form-select js-personnel-select"
                    data-placeholder="Αναζήτηση Β' Μέλους..."
                  >
                    <option value=""></option>
                    {% for p in personnel_list %}
                      <option value="{{ p.id }}">{{ p.display_option_label() }}</option>
                    {% endfor %}
                  </select>
                </div>

                <div class="col-12">
                  <div class="form-check">
                    <input class="form-check-input" type="checkbox" name="is_active" id="c_active_new" checked>
                    <label class="form-check-label" for="c_active_new">Ενεργό</label>
                  </div>
                </div>

                <div class="col-12">
                  <button class="btn btn-primary w-100">Προσθήκη</button>
                </div>
              </div>
            </form>

            <div class="form-text mt-3">
              Η περιγραφή πρέπει να είναι μοναδική μέσα στην ίδια Υπηρεσία.
            </div>
          </div>
        </div>
      </div>

      <div class="col-12 col-xl-7">
        <div class="card glass-card shadow-sm border-0 h-100">
          <div class="card-header">
            <strong>Υπάρχουσες Επιτροπές</strong>
          </div>
          <div class="card-body">
            {% if committees %}
              <div class="table-responsive">
                <table class="table table-sm align-middle mb-0">
                  <thead>
                    <tr>
                      <th>Περιγραφή</th>
                      <th>Ταυτότητα</th>
                      <th>Πρόεδρος</th>
                      <th>Α' Μέλος</th>
                      <th>Β' Μέλος</th>
                      <th>Ενεργό</th>
                      <th class="text-end">Ενέργειες</th>
                    </tr>
                  </thead>
                  <tbody>
                    {% for c in committees %}
                      <tr>
                        <td style="min-width: 180px;">
                          <form method="post" action="{{ request.path }}" class="d-flex gap-2">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            <input type="hidden" name="action" value="update">
                            <input type="hidden" name="service_unit_id" value="{{ scope_service_unit_id }}">
                            <input type="hidden" name="id" value="{{ c.id }}">
                            <input name="description" class="form-control form-control-sm" value="{{ c.description }}" required>
                        </td>

                        <td style="min-width: 180px;">
                          <input name="identity_text" class="form-control form-control-sm" value="{{ c.identity_text or '' }}">
                        </td>

                        <td style="min-width: 220px;">
                          <select
                            name="president_personnel_id"
                            class="form-select form-select-sm js-personnel-select"
                            data-placeholder="Αναζήτηση Προέδρου..."
                          >
                            <option value=""></option>
                            {% for p in personnel_list %}
                              <option value="{{ p.id }}" {% if c.president_personnel_id == p.id %}selected{% endif %}>
                                {{ p.display_option_label() }}
                              </option>
                            {% endfor %}
                          </select>
                        </td>

                        <td style="min-width: 220px;">
                          <select
                            name="member1_personnel_id"
                            class="form-select form-select-sm js-personnel-select"
                            data-placeholder="Αναζήτηση Α' Μέλους..."
                          >
                            <option value=""></option>
                            {% for p in personnel_list %}
                              <option value="{{ p.id }}" {% if c.member1_personnel_id == p.id %}selected{% endif %}>
                                {{ p.display_option_label() }}
                              </option>
                            {% endfor %}
                          </select>
                        </td>

                        <td style="min-width: 220px;">
                          <select
                            name="member2_personnel_id"
                            class="form-select form-select-sm js-personnel-select"
                            data-placeholder="Αναζήτηση Β' Μέλους..."
                          >
                            <option value=""></option>
                            {% for p in personnel_list %}
                              <option value="{{ p.id }}" {% if c.member2_personnel_id == p.id %}selected{% endif %}>
                                {{ p.display_option_label() }}
                              </option>
                            {% endfor %}
                          </select>
                        </td>

                        <td>
                          <input type="checkbox" name="is_active" {% if c.is_active %}checked{% endif %}>
                        </td>

                        <td class="text-end" style="min-width: 170px;">
                            <button class="btn btn-sm btn-outline-primary">Αποθήκευση</button>
                          </form>

                          <form method="post" action="{{ request.path }}" class="d-inline">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            <input type="hidden" name="action" value="delete">
                            <input type="hidden" name="service_unit_id" value="{{ scope_service_unit_id }}">
                            <input type="hidden" name="id" value="{{ c.id }}">
                            <button class="btn btn-sm btn-outline-danger" onclick="return confirm('Διαγραφή;');">
                              Διαγραφή
                            </button>
                          </form>
                        </td>
                      </tr>
                    {% endfor %}
                  </tbody>
                </table>
              </div>
            {% else %}
              <div class="alert alert-info mb-0">Δεν υπάρχουν επιτροπές.</div>
            {% endif %}
          </div>
        </div>
      </div>
    </div>
  {% else %}
    <div class="alert alert-info">Επίλεξε υπηρεσία για να δεις ή να ορίσεις επιτροπές.</div>
  {% endif %}
</div>

<script>
/**
 * Personnel Select2 rendering:
 * - Dropdown results: full option label with IDs
 * - Selected value: compact selected label without IDs
 *
 * SECURITY:
 * - Display only. Real validation is server-side.
 */
(function() {
  if (!window.jQuery || !jQuery.fn || !jQuery.fn.select2) return;

  function stripIds(text) {
    if (!text) return text;
    return String(text).replace(/\s*\([^)]*\)\s*$/, "").trim();
  }

  jQuery(".js-personnel-select").each(function() {
    const $el = jQuery(this);
    if ($el.data("select2")) return;

    $el.select2({
      theme: "bootstrap-5",
      width: "100%",
      allowClear: true,
      placeholder: $el.data("placeholder") || "(αναζήτηση...)",
      templateResult: function(state) {
        if (!state || !state.text) return state.text;
        return state.text;
      },
      templateSelection: function(state) {
        if (!state || !state.text) return state.text;
        return stripIds(state.text);
      }
    });
  });
})();
</script>
{% endblock %}


```

FILE: .\app\templates\settings\cpv.html
```html
{% extends "base.html" %}
{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">CPV</h1>
    <div class="text-muted small">Admin-only λίστα CPV με δυνατότητα εισαγωγής Excel.</div>
  </div>
</div>

<div class="card glass-card shadow-sm border-0 mb-3">
  <div class="card-body">
    <div class="d-flex flex-column flex-md-row align-items-start align-items-md-end justify-content-between gap-2">
      <div class="small text-muted">
        Excel headers: <span class="fw-semibold">CPV</span>, ΠΕΡΙΓΡΑΦΗ
      </div>
      <form method="post" action="{{ url_for('settings.cpv_import') }}" enctype="multipart/form-data" class="d-flex gap-2">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="file" name="file" accept=".xlsx" class="form-control form-control-sm" required>
        <button class="btn btn-outline-primary btn-sm">Εισαγωγή Excel</button>
      </form>
    </div>
  </div>
</div>

<div class="card glass-card shadow-sm border-0 mb-3">
  <div class="card-body">
    <h2 class="h6 fw-bold mb-3">Νέα Εγγραφή</h2>

    <form method="post" action="{{ url_for('settings.cpv') }}">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <input type="hidden" name="action" value="create">

      <div class="row g-2">
        <div class="col-12 col-md-3">
          <label class="form-label small">CPV *</label>
          <input name="cpv" class="form-control form-control-sm" required>
        </div>

        <div class="col-12 col-md-9">
          <label class="form-label small">ΠΕΡΙΓΡΑΦΗ</label>
          <input name="description" class="form-control form-control-sm">
        </div>

        <div class="col-12">
          <button class="btn btn-primary btn-sm">Προσθήκη</button>
        </div>
      </div>
    </form>
  </div>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    <h2 class="h6 fw-bold mb-3">Υπάρχουσες Εγγραφές</h2>

    {% if rows %}
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr>
              <th>CPV</th>
              <th>ΠΕΡΙΓΡΑΦΗ</th>
              <th class="text-end"></th>
            </tr>
          </thead>
          <tbody>
            {% for r in rows %}
              <tr>
                <td style="min-width:220px;">
                  <form method="post" action="{{ url_for('settings.cpv') }}" class="d-flex gap-2">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <input type="hidden" name="action" value="update">
                    <input type="hidden" name="id" value="{{ r.id }}">
                    <input name="cpv" class="form-control form-control-sm" value="{{ r.cpv }}" required>
                </td>
                <td style="min-width:520px;">
                    <input name="description" class="form-control form-control-sm" value="{{ r.description or '' }}">
                </td>
                <td class="text-end" style="white-space:nowrap;">
                    <button class="btn btn-sm btn-outline-primary me-1">Αποθήκευση</button>
                  </form>

                  <form method="post" action="{{ url_for('settings.cpv') }}" class="d-inline">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <input type="hidden" name="action" value="delete">
                    <input type="hidden" name="id" value="{{ r.id }}">
                    <button class="btn btn-sm btn-outline-danger" onclick="return confirm('Διαγραφή;');">Διαγραφή</button>
                  </form>
                </td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <div class="small text-muted">Δεν υπάρχουν εγγραφές.</div>
    {% endif %}
  </div>
</div>
{% endblock %}


```

FILE: .\app\templates\settings\feedback.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h3 fw-bold mb-1">Παράπονα / Αναφορά</h1>
    <div class="text-muted small">
      Περιγράψτε το πρόβλημα ή την πρότασή σας. Θα εξεταστεί από τον διαχειριστή.
    </div>
  </div>
</div>

<div class="card glass-card shadow-sm border-0 mb-4">
  <div class="card-body">
    <form method="post">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

      <div class="row g-3">
        <div class="col-12 col-md-4">
          <label class="form-label">Κατηγορία</label>
          <select name="category" class="form-select">
            {% for key, label in categories %}
              <option value="{{ key }}">{{ label }}</option>
            {% endfor %}
          </select>
        </div>

        <div class="col-12 col-md-8">
          <label class="form-label">Τίτλος</label>
          <input name="subject" class="form-control" required>
        </div>

        <div class="col-12">
          <label class="form-label">Μήνυμα</label>
          <textarea
            name="message"
            class="form-control"
            rows="5"
            placeholder="Περιγράψτε όσο πιο αναλυτικά γίνεται το ζήτημα ή την πρότασή σας."
            required
          ></textarea>
        </div>

        <div class="col-12 col-md-4">
          <label class="form-label">Σχετική προμήθεια (Α/Α)</label>
          <input
            name="related_procurement_id"
            class="form-control"
            placeholder="π.χ. 123"
          >
          <div class="form-text">
            Προαιρετικό: Α/Α προμήθειας από τη λίστα προμηθειών.
          </div>
        </div>
      </div>

      <div class="mt-4">
        <button class="btn btn-primary">
          Υποβολή
        </button>
      </div>
    </form>
  </div>
</div>

{% if recent_feedback %}
  <div class="card glass-card shadow-sm border-0">
    <div class="card-body">
      <h2 class="h6 fw-bold mb-3">Πρόσφατα μηνύματά σας</h2>
      <div class="list-group list-group-flush">
        {% for fb in recent_feedback %}
          <div class="list-group-item">
            <div class="d-flex justify-content-between align-items-start">
              <div>
                <div class="fw-semibold">{{ fb.subject }}</div>
                <div class="small text-muted">
                  {{ fb.created_at.strftime('%d/%m/%Y %H:%M') }}
                  {% if fb.category %}
                    •
                    {% if fb.category == 'complaint' %}Παράπονο{% endif %}
                    {% if fb.category == 'suggestion' %}Πρόταση{% endif %}
                    {% if fb.category == 'bug' %}Σφάλμα{% endif %}
                    {% if fb.category == 'other' %}Άλλο{% endif %}
                  {% endif %}
                  {% if fb.related_procurement_id %}
                    • Προμήθεια Α/Α: {{ fb.related_procurement_id }}
                  {% endif %}
                </div>
              </div>
              <div class="small text-muted">
                {{ fb.status or 'new' }}
              </div>
            </div>
            <div class="small mt-2 text-break">
              {{ fb.message }}
            </div>
          </div>
        {% endfor %}
      </div>
    </div>
  </div>
{% endif %}
{% endblock %}


```

FILE: .\app\templates\settings\feedback_admin.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h3 fw-bold mb-1">Διαχείριση Παραπόνων</h1>
    <div class="text-muted small">
      Προβολή και διαχείριση όλων των παραπόνων / αναφορών που έχουν υποβληθεί.
    </div>
  </div>
</div>

<div class="card glass-card shadow-sm border-0 mb-3">
  <div class="card-body">
    <form class="row g-3" method="get">
      <div class="col-12 col-md-4">
        <label class="form-label">Κατάσταση</label>
        <select name="status" class="form-select">
          <option value="">(Όλες)</option>
          {% for key, label in status_choices.items() %}
            <option value="{{ key }}" {% if status_filter == key %}selected{% endif %}>
              {{ label }}
            </option>
          {% endfor %}
        </select>
      </div>

      <div class="col-12 col-md-4">
        <label class="form-label">Κατηγορία</label>
        <select name="category" class="form-select">
          <option value="">(Όλες)</option>
          <option value="complaint" {% if category_filter == 'complaint' %}selected{% endif %}>Παράπονο</option>
          <option value="suggestion" {% if category_filter == 'suggestion' %}selected{% endif %}>Πρόταση</option>
          <option value="bug" {% if category_filter == 'bug' %}selected{% endif %}>Σφάλμα</option>
          <option value="other" {% if category_filter == 'other' %}selected{% endif %}>Άλλο</option>
        </select>
      </div>

      <div class="col-12 col-md-4 d-flex align-items-end">
        <button class="btn btn-outline-primary me-2">
          Φιλτράρισμα
        </button>
        <a href="{{ url_for('settings.feedback_admin') }}" class="btn btn-outline-secondary">
          Καθαρισμός
        </a>
      </div>
    </form>
  </div>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    {% if feedback_items %}
      <div class="table-responsive">
        <table class="table align-middle mb-0">
          <thead>
            <tr>
              <th>Ημ/νία</th>
              <th>Χρήστης</th>
              <th>Κατηγορία</th>
              <th>Τίτλος</th>
              <th>Μήνυμα</th>
              <th>Προμήθεια</th>
              <th>Κατάσταση</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {% for fb in feedback_items %}
              <tr>
                <td class="small text-muted">
                  {{ fb.created_at.strftime('%d/%m/%Y %H:%M') }}
                </td>
                <td class="small">
                  {{ fb.user.username if fb.user else '—' }}
                </td>
                <td class="small">
                  {{ category_labels.get(fb.category, '—') }}
                </td>
                <td class="small fw-semibold">
                  {{ fb.subject }}
                </td>
                <td class="small text-break" style="max-width: 280px;">
                  {{ fb.message }}
                </td>
                <td class="small">
                  {% if fb.related_procurement_id %}
                    Α/Α: {{ fb.related_procurement_id }}
                  {% else %}
                    —
                  {% endif %}
                </td>
                <td class="small">
                  {{ status_choices.get(fb.status or 'new', 'Νέο') }}
                </td>
                <td class="small">
                  <form method="post" class="d-flex align-items-center">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <input type="hidden" name="feedback_id" value="{{ fb.id }}">
                    <select name="status" class="form-select form-select-sm me-2">
                      {% for key, label in status_choices.items() %}
                        <option value="{{ key }}" {% if (fb.status or 'new') == key %}selected{% endif %}>
                          {{ label }}
                        </option>
                      {% endfor %}
                    </select>
                    <button class="btn btn-sm btn-primary">
                      Ενημέρωση
                    </button>
                  </form>
                </td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <div class="text-muted small">
        Δεν υπάρχουν καταχωρημένα παράπονα / αναφορές με τα συγκεκριμένα κριτήρια.
      </div>
    {% endif %}
  </div>
</div>
{% endblock %}


```

FILE: .\app\templates\settings\income_tax_rules.html
```html
{% extends "base.html" %}
{% block content %}
<div class="container py-3">
  <h3 class="mb-3">Φόρος Εισοδήματος</h3>

  <div class="card mb-4">
    <div class="card-header"><strong>Νέος Κανόνας</strong></div>
    <div class="card-body">
      <form method="post" action="{{ request.path }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="action" value="create">

        <div class="row g-3">
          <div class="col-md-6">
            <label class="form-label">Περιγραφή</label>
            <input name="description" class="form-control" required>
          </div>

          <div class="col-md-2">
            <label class="form-label">ΦΕ %</label>
            <input name="rate_percent" class="form-control" placeholder="8" required>
          </div>

          <div class="col-md-2">
            <label class="form-label">Όριο (€)</label>
            <input name="threshold_amount" class="form-control" value="150" required>
          </div>

          <div class="col-md-2 d-flex align-items-end">
            <div class="form-check">
              <input class="form-check-input" type="checkbox" name="is_active" id="active_new" checked>
              <label class="form-check-label" for="active_new">Ενεργό</label>
            </div>
          </div>

          <div class="col-12">
            <button class="btn btn-primary">Προσθήκη</button>
          </div>
        </div>
      </form>
      <div class="form-text mt-2">
        Το ΦΕ εφαρμόζεται μόνο όταν Σύνολο (προ ΦΠΑ) &gt; Όριο. Υπολογισμός: (Σύνολο - Κρατήσεις) * ΦΕ%.
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-header"><strong>Υπάρχοντες Κανόνες</strong></div>
    <div class="card-body">
      {% if rules %}
      <div class="table-responsive">
        <table class="table table-sm align-middle">
          <thead>
            <tr>
              <th>Περιγραφή</th>
              <th style="width: 120px;">ΦΕ %</th>
              <th style="width: 140px;">Όριο (€)</th>
              <th style="width: 90px;">Ενεργό</th>
              <th style="width: 220px;" class="text-end">Ενέργειες</th>
            </tr>
          </thead>
          <tbody>
            {% for r in rules %}
            <tr>
              <td>
                <form method="post" action="{{ request.path }}" class="d-flex gap-2">
                  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                  <input type="hidden" name="action" value="update">
                  <input type="hidden" name="id" value="{{ r.id }}">
                  <input name="description" class="form-control form-control-sm" value="{{ r.description }}" required>
              </td>

              <td>
                <input name="rate_percent" class="form-control form-control-sm" value="{{ r.rate_percent }}">
              </td>

              <td>
                <input name="threshold_amount" class="form-control form-control-sm" value="{{ r.threshold_amount }}">
              </td>

              <td>
                <input type="checkbox" name="is_active" {% if r.is_active %}checked{% endif %}>
              </td>

              <td class="text-end">
                  <button class="btn btn-sm btn-outline-primary">Αποθήκευση</button>
                </form>

                <form method="post" action="{{ request.path }}" class="d-inline">
                  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                  <input type="hidden" name="action" value="delete">
                  <input type="hidden" name="id" value="{{ r.id }}">
                  <button class="btn btn-sm btn-outline-danger" onclick="return confirm('Διαγραφή;');">Διαγραφή</button>
                </form>
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% else %}
        <div class="alert alert-info mb-0">Δεν υπάρχουν κανόνες.</div>
      {% endif %}
    </div>
  </div>
</div>
{% endblock %}


```

FILE: .\app\templates\settings\options_values.html
```html
{% extends "base.html" %}

{#
  settings/options_values.html

  Enterprise generic template for OptionValue pages.

  Pattern:
  - GET: renders values
  - POST: same endpoint (request.path) with hidden field "action" in {create, update, delete}

  SECURITY:
  - UI is not trusted; routes enforce permissions.
  - CSRF token must be posted as hidden field, not printed as text.
#}

{% block content %}
<div class="container py-3">

  <div class="d-flex align-items-center justify-content-between mb-3">
    <div>
      <h3 class="mb-1">{{ page_label or (category.label if category else "Λίστα") }}</h3>
      <div class="text-muted small">
        Διαχείριση τιμών λίστας (Create / Update / Delete). Οι αλλαγές καταγράφονται σε audit.
      </div>
    </div>
  </div>

  <!-- CREATE NEW OPTION VALUE -->
  <div class="card mb-4">
    <div class="card-header">
      <strong>Νέα Τιμή</strong>
    </div>
    <div class="card-body">
      <form method="post" action="{{ request.path }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="action" value="create">

        <div class="row g-3">
          <div class="col-md-6">
            <label class="form-label">Τιμή</label>
            <input type="text" name="value" class="form-control" maxlength="255" required>
          </div>

          <div class="col-md-3">
            <label class="form-label">Σειρά</label>
            <input type="number" name="sort_order" class="form-control" value="0" step="1">
          </div>

          <div class="col-md-3 d-flex align-items-end">
            <div class="form-check">
              <input class="form-check-input" type="checkbox" name="is_active" id="create_is_active" checked>
              <label class="form-check-label" for="create_is_active">
                Ενεργό
              </label>
            </div>
          </div>

          <div class="col-12">
            <button type="submit" class="btn btn-primary">
              Προσθήκη
            </button>
          </div>
        </div>
      </form>
    </div>
  </div>

  <!-- LIST / UPDATE / DELETE -->
  <div class="card">
    <div class="card-header">
      <strong>Υπάρχουσες Τιμές</strong>
    </div>

    <div class="card-body">
      {% if values and values|length > 0 %}
        <div class="table-responsive">
          <table class="table table-sm align-middle">
            <thead>
              <tr>
                <th style="width: 50px;">#</th>
                <th>Τιμή</th>
                <th style="width: 120px;">Σειρά</th>
                <th style="width: 120px;">Ενεργό</th>
                <th style="width: 220px;" class="text-end">Ενέργειες</th>
              </tr>
            </thead>
            <tbody>
              {% for v in values %}
                <tr>
                  <td class="text-muted">{{ loop.index }}</td>

                  <td>
                    <form method="post" action="{{ request.path }}" class="d-flex gap-2">
                      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                      <input type="hidden" name="action" value="update">
                      <input type="hidden" name="id" value="{{ v.id }}">

                      <input
                        type="text"
                        name="value"
                        class="form-control form-control-sm"
                        value="{{ v.value }}"
                        maxlength="255"
                        required
                      >
                  </td>

                  <td>
                      <input
                        type="number"
                        name="sort_order"
                        class="form-control form-control-sm"
                        value="{{ v.sort_order or 0 }}"
                        step="1"
                      >
                  </td>

                  <td>
                      <div class="form-check">
                        <input
                          class="form-check-input"
                          type="checkbox"
                          name="is_active"
                          id="is_active_{{ v.id }}"
                          {% if v.is_active %}checked{% endif %}
                        >
                        <label class="form-check-label small" for="is_active_{{ v.id }}">
                          {% if v.is_active %}Ναι{% else %}Όχι{% endif %}
                        </label>
                      </div>
                  </td>

                  <td class="text-end">
                      <button type="submit" class="btn btn-sm btn-outline-primary">
                        Αποθήκευση
                      </button>
                    </form>

                    <form method="post" action="{{ request.path }}" class="d-inline">
                      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                      <input type="hidden" name="action" value="delete">
                      <input type="hidden" name="id" value="{{ v.id }}">
                      <button
                        type="submit"
                        class="btn btn-sm btn-outline-danger"
                        onclick="return confirm('Σίγουρα θέλεις διαγραφή;');"
                      >
                        Διαγραφή
                      </button>
                    </form>
                  </td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      {% else %}
        <div class="alert alert-info mb-0">
          Δεν υπάρχουν ακόμη τιμές σε αυτή την κατηγορία.
        </div>
      {% endif %}
    </div>
  </div>

</div>
{% endblock %}


```

FILE: .\app\templates\settings\service_unit_form.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">{{ form_title }}</h1>
    <div class="text-muted small">
      Βασικά στοιχεία Υπηρεσίας.
      Οι ρόλοι Manager/Deputy ορίζονται ξεχωριστά από τη σελίδα
      <span class="fw-semibold">“Ορισμός Deputy/Manager”</span>,
      ενώ η οργανωτική δομή και οι ρόλοι Διευθυντών/Προϊσταμένων
      διαχειρίζονται από την ενιαία σελίδα
      <span class="fw-semibold">“Οργάνωση Υπηρεσίας”</span>.
    </div>
  </div>

  <div class="d-flex gap-2">
    <a href="{{ url_for('settings.service_units_list') }}" class="btn btn-outline-secondary btn-sm">
      &larr; Πίσω στη λίστα Υπηρεσιών
    </a>

    {% if unit %}
      <a href="{{ url_for('settings.service_unit_edit', unit_id=unit.id) }}" class="btn btn-outline-primary btn-sm">
        Ρόλοι
      </a>
      <a href="{{ url_for('admin.organization_setup', service_unit_id=unit.id) }}" class="btn btn-outline-success btn-sm">
        Οργάνωση
      </a>
      <a href="{{ url_for('settings.committees', service_unit_id=unit.id) }}" class="btn btn-outline-dark btn-sm">
        Επιτροπές
      </a>
    {% endif %}
  </div>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    <h2 class="h6 fw-bold mb-3">Βασικά στοιχεία Υπηρεσίας</h2>

    <form method="post">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

      <div class="row g-3">
        <div class="col-12 col-lg-8">

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Κωδικός</label>
            <div class="col-8">
              <input
                type="text"
                name="code"
                class="form-control form-control-sm"
                placeholder="π.χ. ΥΝΤΕΛ"
                value="{{ unit.code if unit and unit.code is not none else '' }}"
              >
              <div class="form-text">
                Προαιρετικό, αλλά αν συμπληρωθεί πρέπει να είναι μοναδικό.
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Περιγραφή *</label>
            <div class="col-8">
              <input
                type="text"
                name="description"
                class="form-control form-control-sm"
                placeholder="Πλήρης περιγραφή υπηρεσίας"
                value="{{ unit.description if unit and unit.description is not none else '' }}"
                required
              >
              <div class="form-text">
                Υποχρεωτικό και μοναδικό.
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Συντομογραφία</label>
            <div class="col-8">
              <input
                type="text"
                name="short_name"
                class="form-control form-control-sm"
                placeholder="Σύντομη ονομασία για λίστες"
                value="{{ unit.short_name if unit and unit.short_name is not none else '' }}"
              >
              <div class="form-text">
                Προαιρετικό, αλλά αν συμπληρωθεί πρέπει να είναι μοναδικό.
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΑΑΗΤ</label>
            <div class="col-8">
              <input
                type="text"
                name="aahit"
                class="form-control form-control-sm"
                placeholder="π.χ. 1011.2030000000.0001"
                value="{{ unit.aahit if unit and unit.aahit is not none else '' }}"
              >
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Email</label>
            <div class="col-8">
              <input
                type="email"
                name="email"
                class="form-control form-control-sm"
                placeholder="π.χ. unit@example.mil.gr"
                value="{{ unit.email if unit and unit.email is not none else '' }}"
              >
              <div class="form-text">
                Αποθηκεύεται ως email Υπηρεσίας.
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Διεύθυνση</label>
            <div class="col-8">
              <input
                type="text"
                name="address"
                class="form-control form-control-sm"
                placeholder="π.χ. ΑΓ. ΓΕΩΡΓΙΟΣ - ΛΕΡΟΣ"
                value="{{ unit.address if unit and unit.address is not none else '' }}"
              >
              <div class="form-text">
                Χρησιμοποιείται σε reports και σε βασική ταυτοποίηση της Υπηρεσίας.
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Περιοχή</label>
            <div class="col-8">
              <input
                type="text"
                name="region"
                class="form-control form-control-sm"
                placeholder="Περιοχή Υπηρεσίας"
                value="{{ unit.region if unit and unit.region is not none else '' }}"
              >
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Νομός</label>
            <div class="col-8">
              <input
                type="text"
                name="prefecture"
                class="form-control form-control-sm"
                placeholder="Νομός Υπηρεσίας"
                value="{{ unit.prefecture if unit and unit.prefecture is not none else '' }}"
              >
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Τηλέφωνο</label>
            <div class="col-8">
              <input
                type="text"
                name="phone"
                class="form-control form-control-sm"
                placeholder="π.χ. 22470xxxx"
                value="{{ unit.phone if unit and unit.phone is not none else '' }}"
              >
              <div class="form-text">
                Χρησιμοποιείται σε reports και επικοινωνία.
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Διοικητής/Κυβερνήτης</label>
            <div class="col-8">
              <input
                type="text"
                name="commander"
                class="form-control form-control-sm"
                value="{{ unit.commander if unit and unit.commander is not none else '' }}"
              >
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Τύπος Διοικητή/Κυβερνήτη</label>
            <div class="col-8">
              <select
                name="commander_role_type"
                class="form-select form-select-sm"
              >
                <option value="">-- Επιλογή --</option>
                {% for option in commander_role_type_options %}
                  <option
                    value="{{ option }}"
                    {% if unit and unit.commander_role_type == option %}selected{% endif %}
                  >
                    {{ option }}
                  </option>
                {% endfor %}
              </select>
              <div class="form-text">
                Επιλέγεις αν το πρόσωπο/ρόλος είναι Διοικητής ή Κυβερνήτης.
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Διαχειριστής Εφαρμογής</label>
            <div class="col-8">
              <input
                type="text"
                name="curator"
                class="form-control form-control-sm"
                value="{{ unit.curator if unit and unit.curator is not none else '' }}"
              >
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΔΙΕΥΘΥΝΣΗ Διαχειριστή Εφαρμογής</label>
            <div class="col-8">
              <input
                type="text"
                name="application_admin_directory"
                class="form-control form-control-sm"
                placeholder="Ελεύθερο κείμενο - δεν τραβάει δεδομένα από αλλού"
                value="{{ unit.application_admin_directory if unit and unit.application_admin_directory is not none else '' }}"
              >
              <div class="form-text">
                Αποθηκεύεται αυτούσιο ως απλό text.
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Υπόλογος εφοδιασμού</label>
            <div class="col-8">
              <input
                type="text"
                name="supply_officer"
                class="form-control form-control-sm"
                value="{{ unit.supply_officer if unit and unit.supply_officer is not none else '' }}"
              >
            </div>
          </div>

        </div>

        <div class="col-12 col-lg-4">
          <div class="card bg-light border-0 h-100">
            <div class="card-body py-3 small">
              <div class="fw-bold mb-2">Σημείωση</div>
              <ul class="mb-0">
                <li>Η φόρμα αυτή αφορά μόνο τα βασικά στοιχεία της Υπηρεσίας.</li>
                <li>Ο κωδικός, η περιγραφή και η συντομογραφία ελέγχονται για διπλότυπα server-side.</li>
                <li>Οι ρόλοι Manager/Deputy ορίζονται ξεχωριστά.</li>
                <li>Η οργανωτική δομή και οι λοιποί ρόλοι γίνονται από την ενιαία σελίδα “Οργάνωση”.</li>
                <li>Email, διεύθυνση, περιοχή, νομός και τηλέφωνο αποθηκεύονται στα βασικά στοιχεία της Υπηρεσίας.</li>
                <li>Η «ΔΙΕΥΘΥΝΣΗ Διαχειριστή Εφαρμογής» είναι free-text και δεν γίνεται lookup από άλλον πίνακα.</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-3">
        <button class="btn btn-primary btn-sm">
          {% if is_create %}
            Δημιουργία Υπηρεσίας
          {% else %}
            Αποθήκευση Υπηρεσίας
          {% endif %}
        </button>
      </div>
    </form>
  </div>
</div>
{% endblock %}

```

FILE: .\app\templates\settings\service_unit_roles_form.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">{{ form_title }}</h1>
    <div class="text-muted small">
      Ορίζεις Manager/Deputy για την υπηρεσία. Επιτρέπεται μόνο επιλογή από ενεργό Προσωπικό.
    </div>
  </div>
  <a href="{{ url_for('settings.service_units_roles_list') }}" class="btn btn-outline-secondary btn-sm">
    &larr; Πίσω στη λίστα Ρόλων
  </a>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">

    <div class="mb-3">
      <div class="small text-muted">Υπηρεσία</div>
      <div class="fw-semibold">
        {{ unit.short_name or unit.description }}
        {% if unit.code %}<span class="text-muted">• {{ unit.code }}</span>{% endif %}
      </div>
    </div>

    <form method="post">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

      <div class="row g-3">
        <div class="col-12 col-lg-8">

          <!-- UPDATED: Personnel dropdown rendering -->
          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Manager (Προσωπικό)</label>
            <div class="col-8">
              <select
                name="manager_personnel_id"
                class="form-select form-select-sm js-select2 personnel-select"
                data-placeholder="(κανένας)"
              >
                <option value=""></option>
                {% for p in personnel_list %}
                  <option
                    value="{{ p.id }}"
                    data-selected-label="{{ p.display_selected_label() }}"
                    {% if unit.manager_personnel_id == p.id %}selected{% endif %}
                  >
                    {{ p.display_option_label() }}
                  </option>
                {% endfor %}
              </select>
            </div>
          </div>

          <!-- UPDATED: Personnel dropdown rendering -->
          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Deputy (Προσωπικό)</label>
            <div class="col-8">
              <select
                name="deputy_personnel_id"
                class="form-select form-select-sm js-select2 personnel-select"
                data-placeholder="(κανένας)"
              >
                <option value=""></option>
                {% for p in personnel_list %}
                  <option
                    value="{{ p.id }}"
                    data-selected-label="{{ p.display_selected_label() }}"
                    {% if unit.deputy_personnel_id == p.id %}selected{% endif %}
                  >
                    {{ p.display_option_label() }}
                  </option>
                {% endfor %}
              </select>
              <div class="form-text">Δεν μπορεί να είναι το ίδιο άτομο με τον Manager.</div>
            </div>
          </div>

          <div class="mt-3">
            <button class="btn btn-primary btn-sm">Αποθήκευση Ρόλων</button>
          </div>

        </div>

        <div class="col-12 col-lg-4">
          <div class="card bg-light border-0 h-100">
            <div class="card-body py-3 small">
              <div class="fw-bold mb-2">Σημείωση</div>
              <ul class="mb-0">
                <li>Manager/Deputy = πλήρη CRUD στις προμήθειες της υπηρεσίας.</li>
                <li>Οι υπόλοιποι χρήστες είναι viewers (read-only).</li>
                <li>Οι επιλογές γίνονται μόνο από ενεργό Προσωπικό.</li>
              </ul>
            </div>
          </div>
        </div>

      </div>
    </form>

  </div>
</div>

<script>
/**
 * Personnel Select2 rendering:
 * - Options: show option text (includes "(ΑΕΜ ... ΑΓΜ)")
 * - Selected: show data-selected-label (without parentheses)
 *
 * SECURITY NOTE:
 * - UI-only. Server-side validation is enforced in routes.
 */
(function() {
  function initPersonnelSelect2() {
    if (!window.jQuery || !jQuery.fn || !jQuery.fn.select2) return;

    jQuery(".personnel-select").each(function() {
      const $el = jQuery(this);
      if ($el.data("select2")) return;

      const placeholder = $el.data("placeholder") || "(αναζήτηση...)";

      $el.select2({
        theme: "bootstrap-5",
        width: "100%",
        placeholder: placeholder,
        allowClear: true,
        templateSelection: function(state) {
          if (!state || !state.element) return state.text || "";
          const lbl = state.element.getAttribute("data-selected-label");
          return lbl || state.text || "";
        }
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPersonnelSelect2);
  } else {
    initPersonnelSelect2();
  }
})();
</script>
{% endblock %}


```

FILE: .\app\templates\settings\service_unit_structure.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">Δομή Υπηρεσίας</h1>
    <div class="text-muted small">
      Η σελίδα αυτή παραμένει μόνο για συμβατότητα παλιών συνδέσμων.
      Η οργανωτική διαχείριση γίνεται πλέον κεντρικά από τη σελίδα “Οργάνωση Υπηρεσίας”.
    </div>
  </div>

  <div class="d-flex gap-2">
    {% if unit %}
      <a href="{{ url_for('admin.organization_setup', service_unit_id=unit.id) }}" class="btn btn-success btn-sm">
        Μετάβαση στην Οργάνωση Υπηρεσίας
      </a>
    {% endif %}

    {% if current_user.is_admin %}
      <a href="{{ url_for('settings.service_units_list') }}" class="btn btn-outline-secondary btn-sm">
        &larr; Πίσω στις Υπηρεσίες
      </a>
    {% endif %}
  </div>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    {% if unit %}
      <div class="mb-3">
        <div class="small text-muted">Υπηρεσία</div>
        <div class="fw-semibold">
          {{ unit.short_name or unit.description }}
          {% if unit.code %}
            <span class="text-muted">• {{ unit.code }}</span>
          {% endif %}
        </div>
      </div>

      <div class="alert alert-info mb-0">
        Η διαχείριση
        <strong>Διευθύνσεων</strong>,
        <strong>Τμημάτων</strong>,
        <strong>Διευθυντών</strong>,
        <strong>Προϊσταμένων</strong>
        και
        <strong>Βοηθών</strong>
        έχει ενοποιηθεί στην κεντρική σελίδα οργάνωσης της Υπηρεσίας.
      </div>

      <div class="mt-3">
        <a href="{{ url_for('admin.organization_setup', service_unit_id=unit.id) }}" class="btn btn-outline-primary btn-sm">
          Άνοιγμα Κεντρικής Σελίδας Οργάνωσης
        </a>
      </div>
    {% else %}
      <div class="alert alert-warning mb-0">
        Δεν βρέθηκε Υπηρεσία.
      </div>
    {% endif %}
  </div>
</div>
{% endblock %}


```

FILE: .\app\templates\settings\service_units.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">Υπηρεσίες</h1>
    <div class="text-muted small">
      Κεντρική σελίδα πρόσβασης για τη διαχείριση Υπηρεσιών.
      Από εδώ μεταβαίνεις στα βασικά στοιχεία, στους ρόλους Manager/Deputy,
      στην οργάνωση της Υπηρεσίας και στις επιτροπές προμηθειών.
    </div>
  </div>
</div>

<div class="row g-3">

  <div class="col-12 col-md-6">
    <div class="card glass-card shadow-sm border-0 h-100">
      <div class="card-body">
        <h2 class="h6 fw-bold mb-2">Λίστα Υπηρεσιών</h2>
        <p class="small text-muted mb-3">
          Προβολή όλων των Υπηρεσιών και πρόσβαση σε:
          βασικά στοιχεία, ρόλους, οργάνωση και επιτροπές ανά Υπηρεσία.
        </p>
        <a href="{{ url_for('settings.service_units_list') }}" class="btn btn-outline-primary btn-sm">
          Προβολή λίστας
        </a>
      </div>
    </div>
  </div>

  <div class="col-12 col-md-6">
    <div class="card glass-card shadow-sm border-0 h-100">
      <div class="card-body">
        <h2 class="h6 fw-bold mb-2">Ορισμός Deputy/Manager</h2>
        <p class="small text-muted mb-3">
          Ανάθεση ρόλων Manager/Deputy ανά Υπηρεσία.
          Επιτρέπεται μόνο επιλογή από ενεργό προσωπικό.
        </p>
        <a href="{{ url_for('settings.service_units_roles_list') }}" class="btn btn-outline-primary btn-sm">
          Μετάβαση στους ρόλους
        </a>
      </div>
    </div>
  </div>

  <div class="col-12 col-md-6">
    <div class="card glass-card shadow-sm border-0 h-100">
      <div class="card-body">
        <h2 class="h6 fw-bold mb-2">Οργάνωση Υπηρεσίας</h2>
        <p class="small text-muted mb-3">
          Κεντρική διαχείριση οργανωτικής δομής:
          Διευθύνσεις, Τμήματα, Διευθυντές, Προϊστάμενοι και Βοηθοί.
        </p>
        <a href="{{ url_for('admin.organization_setup') }}" class="btn btn-outline-success btn-sm">
          Άνοιγμα οργάνωσης
        </a>
      </div>
    </div>
  </div>

  <div class="col-12 col-md-6">
    <div class="card glass-card shadow-sm border-0 h-100">
      <div class="card-body">
        <h2 class="h6 fw-bold mb-2">Επιτροπές Προμηθειών</h2>
        <p class="small text-muted mb-3">
          Διαχείριση επιτροπών ανά Υπηρεσία.
          Για admin υπάρχει επιλογή υπηρεσίας, ενώ οι managers/deputies βλέπουν μόνο τη δική τους.
        </p>
        <a href="{{ url_for('settings.committees') }}" class="btn btn-outline-dark btn-sm">
          Άνοιγμα επιτροπών
        </a>
      </div>
    </div>
  </div>

  <div class="col-12">
    <div class="card glass-card shadow-sm border-0">
      <div class="card-body">
        <div class="fw-bold mb-1">Σημείωση</div>
        <div class="small text-muted">
          Η παλιά ξεχωριστή λογική “Δομή Υπηρεσίας” διατηρείται μόνο για συμβατότητα παλιών συνδέσμων.
          Πλέον όλη η οργανωτική διαχείριση γίνεται από την ενιαία σελίδα
          <b>“Οργάνωση Υπηρεσίας”</b>.
        </div>
      </div>
    </div>
  </div>

</div>
{% endblock %}


```

FILE: .\app\templates\settings\service_units_list.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">Υπηρεσίες</h1>
    <div class="text-muted small">
      Διαχείριση βασικών στοιχείων Υπηρεσιών και πρόσβαση στις επιμέρους σελίδες:
      Ρόλοι, Οργάνωση Υπηρεσίας και Επιτροπές.
    </div>
  </div>
  <div class="d-flex gap-2">
    <a href="{{ url_for('settings.service_unit_create') }}" class="btn btn-primary btn-sm">
      Νέα Υπηρεσία
    </a>
  </div>
</div>

<div class="card glass-card shadow-sm border-0 mb-3">
  <div class="card-body">
    <div class="d-flex flex-column flex-md-row align-items-start align-items-md-end justify-content-between gap-2">
      <div class="small text-muted">
        Excel import: στήλες
        <span class="fw-semibold">Κωδικός</span>,
        <span class="fw-semibold">Περιγραφή</span>,
        <span class="fw-semibold">Συντομογραφία</span>
        και προαιρετικά
        <span class="fw-semibold">ΑΑΗΤ</span>,
        <span class="fw-semibold">Διεύθυνση</span>,
        <span class="fw-semibold">Τηλέφωνο</span>,
        <span class="fw-semibold">Διοικητής</span>,
        <span class="fw-semibold">Επιμελητής</span>,
        <span class="fw-semibold">Υπόλογος εφοδιασμού</span>.
      </div>

      <form method="post" action="{{ url_for('settings.service_units_import') }}" enctype="multipart/form-data" class="d-flex gap-2">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="file" name="file" accept=".xlsx" class="form-control form-control-sm" required>
        <button class="btn btn-outline-primary btn-sm">
          Εισαγωγή Excel
        </button>
      </form>
    </div>
  </div>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    {% if units %}
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr>
              <th>Κωδικός</th>
              <th>Περιγραφή</th>
              <th>Συντομογραφία</th>
              <th>Διεύθυνση</th>
              <th>Τηλέφωνο</th>
              <th class="text-end"></th>
            </tr>
          </thead>
          <tbody>
            {% for u in units %}
              <tr>
                <td class="small"><code>{{ u.code or '—' }}</code></td>
                <td class="small fw-semibold">{{ u.description }}</td>
                <td class="small">{{ u.short_name or '—' }}</td>
                <td class="small">{{ u.address or '—' }}</td>
                <td class="small">{{ u.phone or '—' }}</td>

                <td class="text-end">
                  <a href="{{ url_for('settings.service_unit_edit_info', unit_id=u.id) }}"
                     class="btn btn-sm btn-outline-secondary me-1">
                    Βασικά Στοιχεία
                  </a>

                  <a href="{{ url_for('settings.service_unit_edit', unit_id=u.id) }}"
                     class="btn btn-sm btn-outline-primary me-1">
                    Ρόλοι
                  </a>

                  <a href="{{ url_for('admin.organization_setup', service_unit_id=u.id) }}"
                     class="btn btn-sm btn-outline-success me-1">
                    Οργάνωση
                  </a>

                  <a href="{{ url_for('settings.committees', service_unit_id=u.id) }}"
                     class="btn btn-sm btn-outline-dark me-1">
                    Επιτροπές
                  </a>

                  <form
                    method="post"
                    action="{{ url_for('settings.service_unit_delete', unit_id=u.id) }}"
                    style="display:inline"
                    onsubmit="return confirm('Σίγουρα θέλετε να διαγράψετε την υπηρεσία;');"
                  >
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <button class="btn btn-sm btn-outline-danger">
                      Διαγραφή
                    </button>
                  </form>
                </td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>

      <div class="form-text mt-3">
        Η παλιά ξεχωριστή σελίδα “Δομή” διατηρείται μόνο για συμβατότητα και ανακατευθύνει πλέον στην κεντρική σελίδα “Οργάνωση”.
      </div>
    {% else %}
      <div class="small text-muted">
        Δεν υπάρχουν καταχωρημένες υπηρεσίες.
      </div>
    {% endif %}
  </div>
</div>
{% endblock %}


```

FILE: .\app\templates\settings\service_units_roles_list.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">Ορισμός Deputy / Manager</h1>
    <div class="text-muted small">
      Ανάθεση ρόλων ανά Υπηρεσία. Επιτρέπεται επιλογή μόνο από ενεργό Προσωπικό.
      Η οργανωτική δομή και οι ρόλοι Διευθυντών/Προϊσταμένων διαχειρίζονται από την ενιαία σελίδα
      <span class="fw-semibold">“Οργάνωση Υπηρεσίας”</span>.
    </div>
  </div>

  <div class="d-flex gap-2">
    <a href="{{ url_for('settings.service_units_list') }}" class="btn btn-outline-secondary btn-sm">
      &larr; Πίσω στις Υπηρεσίες
    </a>
  </div>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    {% if units %}
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr>
              <th>Κωδικός</th>
              <th>Περιγραφή</th>
              <th>Συντομογραφία</th>
              <th>Manager</th>
              <th>Deputy</th>
              <th class="text-end"></th>
            </tr>
          </thead>
          <tbody>
            {% for u in units %}
              <tr>
                <td class="small"><code>{{ u.code or '—' }}</code></td>
                <td class="small fw-semibold">{{ u.description }}</td>
                <td class="small">{{ u.short_name or '—' }}</td>

                <td class="small">
                  {% if u.manager %}
                    {{ u.manager.display_selected_label() }}
                  {% else %}
                    —
                  {% endif %}
                </td>

                <td class="small">
                  {% if u.deputy %}
                    {{ u.deputy.display_selected_label() }}
                  {% else %}
                    —
                  {% endif %}
                </td>

                <td class="text-end">
                  <a href="{{ url_for('settings.service_unit_edit', unit_id=u.id) }}"
                     class="btn btn-sm btn-outline-primary me-1">
                    Ορισμός Ρόλων
                  </a>

                  <a href="{{ url_for('admin.organization_setup', service_unit_id=u.id) }}"
                     class="btn btn-sm btn-outline-success">
                    Οργάνωση
                  </a>
                </td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>

      <div class="form-text mt-3">
        Οι ρόλοι Manager/Deputy επηρεάζουν τα δικαιώματα διαχείρισης της συγκεκριμένης Υπηρεσίας.
        Δεν ορίζονται από checkbox σε χρήστη, αλλά από σύνδεση με ενεργό Προσωπικό.
      </div>
    {% else %}
      <div class="small text-muted">Δεν υπάρχουν καταχωρημένες υπηρεσίες.</div>
    {% endif %}
  </div>
</div>
{% endblock %}


```

FILE: .\app\templates\settings\supplier_form.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">{{ form_title }}</h1>
    <div class="text-muted small">
      Διαχείριση στοιχείων προμηθευτή (ΑΦΜ, επωνυμία, τηλέφωνο, Δ.Ο.Υ., διεύθυνση, IBAN κ.λπ.).
    </div>
  </div>
  <a href="{{ url_for('settings.suppliers_list') }}" class="btn btn-outline-secondary btn-sm">
    &larr; Πίσω στη λίστα Προμηθευτών
  </a>
</div>

<div class="card glass-card shadow-sm border-0 mb-3">
  <div class="card-body">
    <h2 class="h6 fw-bold mb-3">Βασικά στοιχεία Προμηθευτή</h2>

    <form method="post">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

      <div class="row g-3">
        <div class="col-12 col-lg-8">

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Α.Φ.Μ.</label>
            <div class="col-8">
              <input type="text"
                     name="afm"
                     class="form-control form-control-sm"
                     placeholder="9 ψηφία, π.χ. 012345678"
                     value="{{ supplier.afm if supplier and supplier.afm is not none else '' }}"
                     required>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Επωνυμία *</label>
            <div class="col-8">
              <input type="text"
                     name="name"
                     class="form-control form-control-sm"
                     value="{{ supplier.name if supplier and supplier.name is not none else '' }}"
                     required>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Τηλέφωνο</label>
            <div class="col-8">
              <input type="text"
                     name="phone"
                     class="form-control form-control-sm"
                     placeholder="π.χ. 2101234567"
                     value="{{ supplier.phone if supplier and supplier.phone is not none else '' }}">
              <div class="form-text">Χρησιμοποιείται στα στοιχεία επικοινωνίας του προμηθευτή και στα reports.</div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Email</label>
            <div class="col-8">
              <input type="email"
                     name="email"
                     class="form-control form-control-sm"
                     placeholder="supplier@example.com"
                     value="{{ supplier.email if supplier and supplier.email is not none else '' }}">
              <div class="form-text">Χρησιμοποιείται στο Προτιμολόγιο και σε λοιπά έγγραφα.</div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">ΕΜΠΑ</label>
            <div class="col-8">
              <input type="text"
                     name="emba"
                     class="form-control form-control-sm"
                     placeholder="ΕΜΠΑ (text)"
                     value="{{ supplier.emba if supplier and supplier.emba is not none else '' }}">
              <div class="form-text">Χρησιμοποιείται στο Προτιμολόγιο (Στοιχεία Αναδόχου).</div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Δ.Ο.Υ.</label>
            <div class="col-8">
              <input type="text"
                     name="doy"
                     class="form-control form-control-sm"
                     placeholder="π.χ. ΚΕΦΟΔΕ ΑΤΤΙΚΗΣ"
                     value="{{ supplier.doy if supplier and supplier.doy is not none else '' }}">
              <div class="form-text">Πεδίο μη υποχρεωτικό. Χρησιμοποιείται σε στοιχεία προμηθευτή.</div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Διεύθυνση</label>
            <div class="col-8">
              <input type="text"
                     name="address"
                     class="form-control form-control-sm"
                     value="{{ supplier.address if supplier and supplier.address is not none else '' }}">
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Τόπος</label>
            <div class="col-8">
              <input type="text"
                     name="city"
                     class="form-control form-control-sm"
                     value="{{ supplier.city if supplier and supplier.city is not none else '' }}">
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Τ.Κ.</label>
            <div class="col-8">
              <input type="text"
                     name="postal_code"
                     class="form-control form-control-sm"
                     value="{{ supplier.postal_code if supplier and supplier.postal_code is not none else '' }}">
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Χώρα</label>
            <div class="col-8">
              <input type="text"
                     name="country"
                     class="form-control form-control-sm"
                     value="{% if supplier and supplier.country is not none %}{{ supplier.country }}{% else %}Ελλάδα{% endif %}">
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Τράπεζα</label>
            <div class="col-8">
              <input type="text"
                     name="bank_name"
                     class="form-control form-control-sm"
                     value="{{ supplier.bank_name if supplier and supplier.bank_name is not none else '' }}">
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">IBAN</label>
            <div class="col-8">
              <input type="text"
                     name="iban"
                     class="form-control form-control-sm"
                     value="{{ supplier.iban if supplier and supplier.iban is not none else '' }}">
            </div>
          </div>
        </div>

        <div class="col-12 col-lg-4">
          <div class="card bg-light border-0 h-100">
            <div class="card-body py-3 small">
              <div class="fw-bold mb-2">Σημείωση</div>
              <p class="mb-2">
                Το ΑΦΜ είναι μοναδικό για κάθε προμηθευτή. Ο έλεγχος
                μοναδικότητας γίνεται στον κώδικα ώστε να μην δημιουργούνται
                διπλές εγγραφές.
              </p>
              <p class="mb-2">
                Το τηλέφωνο, το email, η Δ.Ο.Υ. και το ΕΜΠΑ αποθηκεύονται
                ως στοιχεία master data προμηθευτή.
              </p>
              <p class="mb-0 text-muted">
                Τα στοιχεία αυτά χρησιμοποιούνται στις φόρμες προμηθειών
                και στα reports.
              </p>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-3">
        <button class="btn btn-primary btn-sm">
          Αποθήκευση Προμηθευτή
        </button>
      </div>
    </form>
  </div>
</div>
{% endblock %}


```

FILE: .\app\templates\settings\suppliers.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">Προμηθευτές</h1>
    <div class="text-muted small">
      Διαχείριση προμηθευτών (ΑΦΜ, επωνυμία, διεύθυνση, IBAN κ.λπ.).
    </div>
  </div>
  <a href="{{ url_for('settings.data_overview') }}" class="btn btn-outline-secondary btn-sm">
    &larr; Στοιχεία / Πληροφορίες
  </a>
</div>

{# Φόρμα Προμηθευτή #}
{% include "settings/suppliers_form.html" %}

{# Λίστα Προμηθευτών #}
{% include "settings/suppliers_list.html" %}
{% endblock %}


```

FILE: .\app\templates\settings\suppliers_list.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">Προμηθευτές</h1>
    <div class="text-muted small">
      Διαχείριση προμηθευτών (ΑΦΜ, επωνυμία, τηλέφωνο, Δ.Ο.Υ., Email, ΕΜΠΑ, διεύθυνση, τόπος, Τ.Κ., χώρα, τράπεζα, IBAN).
    </div>
  </div>
  <a href="{{ url_for('settings.supplier_create') }}" class="btn btn-primary btn-sm">
    Νέος Προμηθευτής
  </a>
</div>

<div class="card glass-card shadow-sm border-0 mb-3">
  <div class="card-body">
    <div class="d-flex flex-column flex-md-row align-items-start align-items-md-end justify-content-between gap-2">
      <div class="small text-muted">
        Excel headers:
        <span class="fw-semibold">ΑΦΜ</span>,
        <span class="fw-semibold">ΕΠΩΝΥΜΙΑ</span> (ή ΟΝΟΜΑΣΙΑ),
        ΔΟΥ (ή Δ.Ο.Υ.),
        ΤΗΛΕΦΩΝΟ,
        EMAIL,
        ΕΜΠΑ,
        ΔΙΕΥΘΥΝΣΗ,
        ΤΟΠΟΣ,
        ΤΚ (ή Τ.Κ.),
        ΧΩΡΑ,
        ΤΡΑΠΕΖΑ,
        IBAN
        <span class="ms-2">(Duplicates: <span class="fw-semibold">SKIP</span>)</span>
      </div>

      <form method="post"
            action="{{ url_for('settings.suppliers_import') }}"
            enctype="multipart/form-data"
            class="d-flex gap-2">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="file" name="file" accept=".xlsx" class="form-control form-control-sm" required>
        <button class="btn btn-outline-primary btn-sm">Εισαγωγή Excel</button>
      </form>
    </div>
  </div>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    {% if suppliers %}
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr>
              <th>ΑΦΜ</th>
              <th>Επωνυμία</th>
              <th>Τηλέφωνο</th>
              <th>Δ.Ο.Υ.</th>
              <th>Email</th>
              <th>ΕΜΠΑ</th>
              <th>Διεύθυνση</th>
              <th>Τόπος</th>
              <th>Τ.Κ.</th>
              <th>Χώρα</th>
              <th>Τράπεζα</th>
              <th>IBAN</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {% for s in suppliers %}
              <tr>
                <td class="small fw-semibold">{{ s.afm }}</td>
                <td class="small">{{ s.name }}</td>
                <td class="small">{{ s.phone or '—' }}</td>
                <td class="small">{{ s.doy or '—' }}</td>
                <td class="small">{{ s.email or '—' }}</td>
                <td class="small">{{ s.emba or '—' }}</td>
                <td class="small">{{ s.address or '—' }}</td>
                <td class="small">{{ s.city or '—' }}</td>
                <td class="small">{{ s.postal_code or '—' }}</td>
                <td class="small">{{ s.country or '—' }}</td>
                <td class="small">{{ s.bank_name or '—' }}</td>
                <td class="small text-nowrap">{{ s.iban or '—' }}</td>
                <td class="text-end">
                  <a href="{{ url_for('settings.supplier_edit', supplier_id=s.id) }}" class="btn btn-sm btn-outline-secondary me-1">
                    Επεξεργασία
                  </a>
                  <form
                    method="post"
                    action="{{ url_for('settings.supplier_delete', supplier_id=s.id) }}"
                    style="display:inline"
                    onsubmit="return confirm('Σίγουρα θέλετε να διαγράψετε τον προμηθευτή;');"
                  >
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <button class="btn btn-sm btn-outline-danger">
                      Διαγραφή
                    </button>
                  </form>
                </td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <div class="small text-muted">
        Δεν υπάρχουν καταχωρημένοι προμηθευτές. Πατήστε "Νέος Προμηθευτής" για να προσθέσετε.
      </div>
    {% endif %}
  </div>
</div>
{% endblock %}


```

FILE: .\app\templates\settings\theme.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h3 fw-bold mb-1">Θέμα εμφάνισης</h1>
    <div class="text-muted small">
      Επιλέξτε πώς θέλετε να φαίνεται η εφαρμογή για τον λογαριασμό σας.
    </div>
  </div>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    <form method="post">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

      <div class="row g-3">
        {% for key, meta in themes.items() %}
          {% set label = meta[0] %}
          {% set description = meta[1] %}
          <div class="col-12 col-md-4">
            <div class="form-check theme-option-card p-3 border rounded h-100">
              <input
                class="form-check-input"
                type="radio"
                name="theme"
                id="theme-{{ key }}"
                value="{{ key }}"
                {% if current_user.theme == key %}checked{% endif %}
              >
              <label class="form-check-label fw-semibold" for="theme-{{ key }}">
                {{ label }}
              </label>
              <div class="small text-muted mt-1">
                {{ description }}
              </div>
            </div>
          </div>
        {% endfor %}
      </div>

      <div class="mt-4">
        <button class="btn btn-primary">
          Αποθήκευση
        </button>
      </div>
    </form>
  </div>
</div>
{% endblock %}


```

FILE: .\app\templates\settings\withholding_profiles.html
```html
{% extends "base.html" %}
{% block content %}
<div class="container py-3">
  <h3 class="mb-3">Κρατήσεις (Πίνακας)</h3>

  <div class="card mb-4">
    <div class="card-header"><strong>Νέο Προφίλ</strong></div>
    <div class="card-body">
      <form method="post" action="{{ request.path }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="action" value="create">

        <div class="row g-3">
          <div class="col-md-6">
            <label class="form-label">Περιγραφή</label>
            <input name="description" class="form-control" required>
          </div>

          <div class="col-md-2">
            <label class="form-label">ΜΤ-ΕΛΟΑ %</label>
            <input name="mt_eloa_percent" class="form-control" value="0">
          </div>

          <div class="col-md-2">
            <label class="form-label">ΕΑΔΗΣΥ %</label>
            <input name="eadhsy_percent" class="form-control" value="0">
          </div>

          <div class="col-md-2 d-flex align-items-end">
            <div class="form-check">
              <input class="form-check-input" type="checkbox" name="is_active" id="wp_active_new" checked>
              <label class="form-check-label" for="wp_active_new">Ενεργό</label>
            </div>
          </div>

          <div class="col-md-2">
            <label class="form-label">Κράτηση 1 %</label>
            <input name="withholding1_percent" class="form-control" value="0">
          </div>

          <div class="col-md-2">
            <label class="form-label">Κράτηση 2 %</label>
            <input name="withholding2_percent" class="form-control" value="0">
          </div>

          <div class="col-12">
            <button class="btn btn-primary">Προσθήκη</button>
          </div>
        </div>
      </form>

      <div class="form-text mt-2">
        Το “Σύνολο” είναι το άθροισμα: ΜΤ-ΕΛΟΑ + ΕΑΔΗΣΥ + Κράτηση 1 + Κράτηση 2.
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-header"><strong>Υπάρχοντα Προφίλ</strong></div>
    <div class="card-body">
      {% if profiles %}
      <div class="table-responsive">
        <table class="table table-sm align-middle">
          <thead>
            <tr>
              <th>Περιγραφή</th>
              <th style="width: 110px;">ΜΤ-ΕΛΟΑ</th>
              <th style="width: 110px;">ΕΑΔΗΣΥ</th>
              <th style="width: 110px;">Κράτηση 1</th>
              <th style="width: 110px;">Κράτηση 2</th>
              <th style="width: 90px;">Σύνολο</th>
              <th style="width: 80px;">Ενεργό</th>
              <th style="width: 220px;" class="text-end">Ενέργειες</th>
            </tr>
          </thead>
          <tbody>
            {% for p in profiles %}
            <tr>
              <td>
                <form method="post" action="{{ request.path }}" class="d-flex gap-2">
                  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                  <input type="hidden" name="action" value="update">
                  <input type="hidden" name="id" value="{{ p.id }}">
                  <input name="description" class="form-control form-control-sm" value="{{ p.description }}" required>
              </td>

              <td><input name="mt_eloa_percent" class="form-control form-control-sm" value="{{ p.mt_eloa_percent }}"></td>
              <td><input name="eadhsy_percent" class="form-control form-control-sm" value="{{ p.eadhsy_percent }}"></td>
              <td><input name="withholding1_percent" class="form-control form-control-sm" value="{{ p.withholding1_percent }}"></td>
              <td><input name="withholding2_percent" class="form-control form-control-sm" value="{{ p.withholding2_percent }}"></td>

              <td><span class="badge bg-secondary">{{ p.total_percent }}%</span></td>

              <td><input type="checkbox" name="is_active" {% if p.is_active %}checked{% endif %}></td>

              <td class="text-end">
                  <button class="btn btn-sm btn-outline-primary">Αποθήκευση</button>
                </form>

                <form method="post" action="{{ request.path }}" class="d-inline">
                  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                  <input type="hidden" name="action" value="delete">
                  <input type="hidden" name="id" value="{{ p.id }}">
                  <button class="btn btn-sm btn-outline-danger" onclick="return confirm('Διαγραφή;');">Διαγραφή</button>
                </form>
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% else %}
        <div class="alert alert-info mb-0">Δεν υπάρχουν προφίλ.</div>
      {% endif %}
    </div>
  </div>
</div>
{% endblock %}


```

FILE: .\app\templates\users\edit.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">Επεξεργασία Χρήστη</h1>
    <div class="text-muted small">
      Διαχείριση ρόλων, υπηρεσίας, κατάστασης και σύνδεσης με Προσωπικό.
    </div>
  </div>
  <a href="{{ url_for('users.list_users') }}" class="btn btn-outline-secondary btn-sm">
    &larr; Πίσω στη λίστα
  </a>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    <div class="row g-3">
      <div class="col-12 col-lg-8">
        <form method="post" id="user-edit-form">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Username</label>
            <div class="col-8">
              <input type="text" class="form-control form-control-sm" value="{{ user.username }}" disabled>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Νέο Password</label>
            <div class="col-8">
              <input type="password" name="password" class="form-control form-control-sm">
              <div class="form-text">
                Αν συμπληρωθεί, θα αντικαταστήσει το τρέχον password.
              </div>
            </div>
          </div>

          <hr class="my-3">

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Προσωπικό (1-1) *</label>
            <div class="col-8">
              <select
                name="personnel_id"
                class="form-select form-select-sm js-personnel-select"
                data-placeholder="Αναζήτηση Προσωπικού..."
                required
              >
                <option value=""></option>
                {% for p in personnel_list %}
                  <option value="{{ p.id }}" {% if user.personnel_id == p.id %}selected{% endif %}>
                    {{ p.display_option_label() }}
                  </option>
                {% endfor %}
              </select>
              <div class="form-text">
                Επιτρέπεται μόνο ενεργό προσωπικό χωρίς user (ή το ήδη συνδεδεμένο).
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Υπηρεσία</label>
            <div class="col-8">
              <select name="service_unit_id" id="service_unit_id" class="form-select form-select-sm">
                <option value="">(καμία)</option>
                {% for su in service_units %}
                  <option value="{{ su.id }}" {% if user.service_unit_id == su.id %}selected{% endif %}>
                    {{ su.short_name or su.description }}
                  </option>
                {% endfor %}
              </select>
              <div class="form-text" id="service-unit-help">
                Για non-admin χρήστες, η Υπηρεσία πρέπει να ταυτίζεται με την Υπηρεσία του επιλεγμένου Προσωπικού.
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Δικαιώματα</label>
            <div class="col-8">
              <div class="form-check mb-2">
                <input class="form-check-input" type="checkbox" name="is_admin" id="is_admin"
                       {% if user.is_admin %}checked{% endif %}>
                <label class="form-check-label" for="is_admin">Administrator</label>
              </div>

              <div class="form-check">
                <input class="form-check-input" type="checkbox" name="is_active" id="is_active"
                       {% if user.is_active %}checked{% endif %}>
                <label class="form-check-label" for="is_active">Ενεργός Χρήστης</label>
              </div>
            </div>
          </div>

          <div class="mt-3">
            <button class="btn btn-primary btn-sm">
              Αποθήκευση Αλλαγών
            </button>
          </div>
        </form>
      </div>

      <div class="col-12 col-lg-4">
        <div class="card bg-light border-0 h-100">
          <div class="card-body py-3 small">
            <div class="fw-bold mb-2">Σημείωση</div>
            <ul class="mb-0">
              <li>Η υπηρεσία καθορίζει την απομόνωση δεδομένων για non-admin χρήστες.</li>
              <li>Manager/Deputy καθορίζεται από την Υπηρεσία μέσω Προσωπικού.</li>
              <li>Αν απενεργοποιήσεις χρήστη, δεν μπορεί να κάνει login.</li>
              <li>Αν αλλάξεις σύνδεση Προσωπικού, κρατάς την 1-1 σχέση.</li>
              <li>Administrator = user χωρίς ανάθεση υπηρεσίας, αλλά με κανονικό linked Personnel.</li>
            </ul>
          </div>
        </div>
      </div>

    </div>
  </div>
</div>

<script>
/**
 * User form behavior.
 *
 * UI-only behavior:
 * - If "Administrator" is checked, the service unit field is disabled and cleared.
 * - Server-side remains the source of truth and will force service_unit_id = NULL for admins.
 */
(function() {
  function syncAdminState() {
    const isAdmin = document.getElementById("is_admin");
    const serviceUnit = document.getElementById("service_unit_id");
    const serviceUnitHelp = document.getElementById("service-unit-help");

    if (!isAdmin || !serviceUnit) return;

    if (isAdmin.checked) {
      serviceUnit.value = "";
      serviceUnit.setAttribute("disabled", "disabled");
      if (serviceUnitHelp) {
        serviceUnitHelp.textContent = "Για Administrator η Υπηρεσία δεν ορίζεται. Το πεδίο μηδενίζεται και αγνοείται server-side.";
      }
    } else {
      serviceUnit.removeAttribute("disabled");
      if (serviceUnitHelp) {
        serviceUnitHelp.textContent = "Για non-admin χρήστες, η Υπηρεσία πρέπει να ταυτίζεται με την Υπηρεσία του επιλεγμένου Προσωπικού.";
      }
    }
  }

  const isAdmin = document.getElementById("is_admin");
  if (isAdmin) {
    isAdmin.addEventListener("change", syncAdminState);
  }

  syncAdminState();
})();

/**
 * Personnel Select2 rendering:
 * - Dropdown results: full option label with IDs
 * - Selected value: compact selected label without IDs
 *
 * SECURITY:
 * - Display only. Real validation is server-side.
 */
(function() {
  if (!window.jQuery || !jQuery.fn || !jQuery.fn.select2) return;

  function stripIds(text) {
    if (!text) return text;
    return String(text).replace(/\s*\([^)]*\)\s*$/, "").trim();
  }

  jQuery(".js-personnel-select").each(function() {
    const $el = jQuery(this);
    if ($el.data("select2")) return;

    $el.select2({
      theme: "bootstrap-5",
      width: "100%",
      allowClear: true,
      placeholder: $el.data("placeholder") || "(αναζήτηση...)",
      templateResult: function(state) {
        if (!state || !state.text) return state.text;
        return state.text;
      },
      templateSelection: function(state) {
        if (!state || !state.text) return state.text;
        return stripIds(state.text);
      }
    });
  });
})();
</script>
{% endblock %}


```

FILE: .\app\templates\users\list.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">Χρήστες Συστήματος</h1>
    <div class="text-muted small">
      Διαχείριση χρηστών, ρόλων και ανάθεσης υπηρεσιών.
    </div>
  </div>
  <a href="{{ url_for('users.create_user') }}" class="btn btn-primary btn-sm">
    Νέος Χρήστης
  </a>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">

    {% if users %}
    <div class="table-responsive">
      <table class="table table-sm align-middle mb-0">
        <thead>
          <tr>
            <th>Username</th>
            <th>Προσωπικό</th>
            <th>Ρόλος</th>
            <th>Υπηρεσία</th>
            <th>Οργανική Θέση</th>
            <th>Κατάσταση</th>
            <th>Ημ/νία Δημιουργίας</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {% for user in users %}
          <tr>
            <td class="fw-semibold">{{ user.username }}</td>

            <td class="small">
              {% if user.personnel %}
                {{ user.personnel.display_selected_label() }}
              {% else %}
                —
              {% endif %}
            </td>

            <td>
              {% if user.is_admin %}
                <span class="badge bg-danger">Admin</span>
              {% elif user.can_manage() %}
                <span class="badge bg-primary">Manager/Deputy</span>
              {% else %}
                <span class="badge bg-secondary">Viewer</span>
              {% endif %}
            </td>

            <td class="small">
              {% if user.is_admin %}
                <span class="text-muted">—</span>
              {% elif user.service_unit %}
                {{ user.service_unit.short_name or user.service_unit.description }}
              {% else %}
                —
              {% endif %}
            </td>

            <td class="small">
              {% if user.personnel %}
                {% if user.personnel.service_unit or user.personnel.directory or user.personnel.department %}
                  {% if user.personnel.service_unit %}
                    <div>{{ user.personnel.service_unit.short_name or user.personnel.service_unit.description }}</div>
                  {% endif %}
                  {% if user.personnel.directory %}
                    <div class="text-muted">{{ user.personnel.directory.name }}</div>
                  {% endif %}
                  {% if user.personnel.department %}
                    <div class="text-muted">{{ user.personnel.department.name }}</div>
                  {% endif %}
                {% else %}
                  <span class="text-muted">Ουδέτερο Προσωπικό</span>
                {% endif %}
              {% else %}
                —
              {% endif %}
            </td>

            <td>
              {% if user.is_active %}
                <span class="badge bg-success">Ενεργός</span>
              {% else %}
                <span class="badge bg-secondary">Ανενεργός</span>
              {% endif %}
            </td>

            <td class="small text-muted">
              {{ user.created_at.strftime('%d/%m/%Y %H:%M') }}
            </td>

            <td class="text-end">
              <a href="{{ url_for('users.edit_user', user_id=user.id) }}"
                 class="btn btn-sm btn-outline-secondary">
                Επεξεργασία
              </a>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <div class="form-text mt-3">
      Για Administrator ισχύει το μοντέλο:
      σύνδεση 1-1 με κανονικό Προσωπικό, αλλά χωρίς ανάθεση υπηρεσίας στον ίδιο τον user.
      Έτσι αποφεύγεται λανθασμένη service isolation σε admin λογαριασμούς.
    </div>
    {% else %}
      <div class="small text-muted">
        Δεν υπάρχουν χρήστες στο σύστημα.
      </div>
    {% endif %}

  </div>
</div>
{% endblock %}


```

FILE: .\app\templates\users\new.html
```html
{% extends "base.html" %}

{% block content %}
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h1 class="h4 fw-bold mb-1">Νέος Χρήστης</h1>
    <div class="text-muted small">
      Δημιουργία νέου λογαριασμού χρήστη (σύνδεση 1-1 με Προσωπικό).
    </div>
  </div>
  <a href="{{ url_for('users.list_users') }}" class="btn btn-outline-secondary btn-sm">
    &larr; Πίσω στη λίστα
  </a>
</div>

<div class="card glass-card shadow-sm border-0">
  <div class="card-body">
    <div class="row g-3">
      <div class="col-12 col-lg-8">
        <form method="post" id="user-create-form">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Username *</label>
            <div class="col-8">
              <input type="text" name="username" class="form-control form-control-sm" required>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Password *</label>
            <div class="col-8">
              <input type="password" name="password" class="form-control form-control-sm" required>
            </div>
          </div>

          <hr class="my-3">

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Προσωπικό (υποχρεωτικό) *</label>
            <div class="col-8">
              <select
                name="personnel_id"
                class="form-select form-select-sm js-personnel-select"
                data-placeholder="Αναζήτηση Προσωπικού..."
                required
              >
                <option value=""></option>
                {% for p in personnel_list %}
                  <option value="{{ p.id }}">
                    {{ p.display_option_label() }}
                  </option>
                {% endfor %}
              </select>
              <div class="form-text">
                Εμφανίζονται μόνο ενεργοί που ΔΕΝ έχουν ήδη user (1-1).
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Υπηρεσία</label>
            <div class="col-8">
              <select name="service_unit_id" id="service_unit_id" class="form-select form-select-sm">
                <option value="">(καμία)</option>
                {% for su in service_units %}
                  <option value="{{ su.id }}">
                    {{ su.short_name or su.description }}
                  </option>
                {% endfor %}
              </select>
              <div class="form-text" id="service-unit-help">
                Για non-admin χρήστες, αυτή η ανάθεση πρέπει να ταυτίζεται με την Υπηρεσία του επιλεγμένου Προσωπικού.
              </div>
            </div>
          </div>

          <div class="mb-2 row align-items-center">
            <label class="col-4 col-form-label col-form-label-sm">Ρόλος</label>
            <div class="col-8">
              <div class="form-check">
                <input class="form-check-input" type="checkbox" name="is_admin" id="is_admin">
                <label class="form-check-label" for="is_admin">
                  Administrator (Πλήρης Πρόσβαση)
                </label>
              </div>
              <div class="form-text mt-1">
                Για Administrator, ο user δεν ανήκει σε Υπηρεσία. Παραμένει όμως συνδεδεμένος με κανονικό Personnel.
              </div>
            </div>
          </div>

          <div class="mt-3">
            <button class="btn btn-primary btn-sm">
              Δημιουργία Χρήστη
            </button>
          </div>
        </form>
      </div>

      <div class="col-12 col-lg-4">
        <div class="card bg-light border-0 h-100">
          <div class="card-body py-3 small">
            <div class="fw-bold mb-2">Σημείωση</div>
            <ul class="mb-0">
              <li>Κάθε χρήστης συνδέεται 1-1 με Προσωπικό.</li>
              <li>Admin βλέπει/διαχειρίζεται τα πάντα.</li>
              <li>Non-admin βλέπει μόνο την υπηρεσία του.</li>
              <li>Manager/Deputy προκύπτει από ανάθεση στο ServiceUnit, όχι από checkbox.</li>
              <li>Admin μπορεί να συνδεθεί με “ουδέτερο” Προσωπικό χωρίς Υπηρεσία / Διεύθυνση / Τμήμα.</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
/**
 * User form behavior.
 *
 * UI-only behavior:
 * - If "Administrator" is checked, the service unit field is disabled and cleared.
 * - Server-side remains the source of truth and will force service_unit_id = NULL for admins.
 */
(function() {
  function syncAdminState() {
    const isAdmin = document.getElementById("is_admin");
    const serviceUnit = document.getElementById("service_unit_id");
    const serviceUnitHelp = document.getElementById("service-unit-help");

    if (!isAdmin || !serviceUnit) return;

    if (isAdmin.checked) {
      serviceUnit.value = "";
      serviceUnit.setAttribute("disabled", "disabled");
      if (serviceUnitHelp) {
        serviceUnitHelp.textContent = "Για Administrator η Υπηρεσία δεν ορίζεται. Το πεδίο μηδενίζεται και αγνοείται server-side.";
      }
    } else {
      serviceUnit.removeAttribute("disabled");
      if (serviceUnitHelp) {
        serviceUnitHelp.textContent = "Για non-admin χρήστες, αυτή η ανάθεση πρέπει να ταυτίζεται με την Υπηρεσία του επιλεγμένου Προσωπικού.";
      }
    }
  }

  const isAdmin = document.getElementById("is_admin");
  if (isAdmin) {
    isAdmin.addEventListener("change", syncAdminState);
  }

  syncAdminState();
})();

/**
 * Personnel Select2 rendering:
 * - Dropdown results: full option label with IDs
 * - Selected value: compact selected label without IDs
 *
 * SECURITY:
 * - Display only. Real validation is server-side.
 */
(function() {
  if (!window.jQuery || !jQuery.fn || !jQuery.fn.select2) return;

  function stripIds(text) {
    if (!text) return text;
    return String(text).replace(/\s*\([^)]*\)\s*$/, "").trim();
  }

  jQuery(".js-personnel-select").each(function() {
    const $el = jQuery(this);
    if ($el.data("select2")) return;

    $el.select2({
      theme: "bootstrap-5",
      width: "100%",
      allowClear: true,
      placeholder: $el.data("placeholder") || "(αναζήτηση...)",
      templateResult: function(state) {
        if (!state || !state.text) return state.text;
        return state.text;
      },
      templateSelection: function(state) {
        if (!state || !state.text) return state.text;
        return stripIds(state.text);
      }
    });
  });
})();
</script>
{% endblock %}


```

FILE: .\app\utils.py
```python
"""
app/utils.py

Backward-compatible utility facade.

PURPOSE
-------
This module remains as a stable import surface for older code that imports
small shared helpers from `app.utils`.

CURRENT POLICY
--------------
`app.utils` should NOT become a generic dumping ground.

Presentation-oriented helpers now live in:
    app.presentation

Database-backed lookups already live in:
    app.services.master_data_service

WHY THIS FILE STILL EXISTS
--------------------------
The project may still contain imports such as:

    from app.utils import procurement_row_class

To avoid unnecessary churn during the refactor, this module re-exports the
public helper while keeping its role intentionally small.

CURRENT CONTENTS
----------------
- procurement_row_class:
    Presentation helper for procurement row CSS styling
"""

from __future__ import annotations

from .presentation import procurement_row_class

__all__ = ["procurement_row_class"]


```

