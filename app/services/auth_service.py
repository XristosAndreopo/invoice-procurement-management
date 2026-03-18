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