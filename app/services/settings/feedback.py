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

IMPORTANT IMPLEMENTATION NOTE
-----------------------------
The active Feedback model in the project stores only the fields that are
actually present in `app/models/feedback.py`:

- name
- email
- subject
- message
- status
- created_at / updated_at

This service therefore intentionally avoids assumptions about fields that are
not present in the current persisted model, such as:
- user_id
- category
- related_procurement_id

This keeps the feedback flow production-safe without requiring a schema
migration.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flask_login import current_user

from ...extensions import db
from ...models import Feedback
from ..shared.operation_results import FlashMessage, OperationResult

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


def _current_user_sender_name() -> str:
    """
    Build a best-effort sender display name from the authenticated user.

    RETURNS
    -------
    str
        Human-readable sender name suitable for Feedback.name.

    FALLBACK ORDER
    --------------
    1. current_user.display_name when available and non-empty
    2. current_user.username when available and non-empty
    3. generic fallback label
    """
    display_name = getattr(current_user, "display_name", None)
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()

    username = getattr(current_user, "username", None)
    if isinstance(username, str) and username.strip():
        return username.strip()

    return "Χρήστης εφαρμογής"


def _current_user_sender_email() -> str | None:
    """
    Return a best-effort sender email for Feedback.email.

    RETURNS
    -------
    str | None
        Currently None unless a real email field is present on the active user
        object in the running project.

    WHY THIS HELPER EXISTS
    ----------------------
    The current visible source of truth does not guarantee that User has an
    email field. This helper therefore remains defensive and avoids
    assumptions.
    """
    email = getattr(current_user, "email", None)
    if isinstance(email, str) and email.strip():
        return email.strip()

    return None


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

    IMPORTANT
    ---------
    The active Feedback model does not contain a user_id field. Therefore the
    "recent feedback" section is intentionally omitted in this hotfix path to
    avoid unsafe filtering assumptions.
    """
    return {
        "categories": FEEDBACK_CATEGORIES,
        "recent_feedback": [],
    }


def execute_feedback_submission(*, user_id: int, form_data: Mapping[str, object]) -> OperationResult:
    """
    Validate and create a feedback entry submitted by a logged-in user.

    PARAMETERS
    ----------
    user_id:
        Authenticated user id. Retained for route compatibility, but not
        persisted because the current Feedback model has no user_id field.
    form_data:
        Submitted form payload.

    RETURNS
    -------
    OperationResult
        Result object for route flashing/redirecting.

    HOTFIX STORAGE POLICY
    ---------------------
    This implementation persists only fields that are present in the active
    Feedback model:
    - name
    - email
    - subject
    - message
    - status

    Extra form fields such as category or related procurement id are ignored
    intentionally in this compatibility-safe hotfix.
    """
    _ = user_id  # Route contract retained intentionally.

    subject = (form_data.get("subject") or "").strip()
    message = (form_data.get("message") or "").strip()

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

    feedback_row = Feedback(
        name=_current_user_sender_name(),
        email=_current_user_sender_email(),
        subject=subject,
        message=message,
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
        Template context with filters and the filtered feedback list.

    IMPORTANT
    ---------
    Category filtering is intentionally unsupported in this hotfix because the
    active Feedback model does not define a category field.
    """
    status_filter = (args.get("status") or "").strip() or None

    query = Feedback.query

    if status_filter and status_filter in FEEDBACK_STATUS_CHOICES:
        query = query.filter(Feedback.status == status_filter)

    feedback_items = query.order_by(Feedback.created_at.desc()).all()

    return {
        "feedback_items": feedback_items,
        "status_choices": FEEDBACK_STATUS_CHOICES,
        "status_filter": status_filter,
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

    try:
        feedback_id = int(feedback_id_raw)
    except (TypeError, ValueError):
        feedback_id = None

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
    "build_feedback_page_context",
    "execute_feedback_submission",
    "build_feedback_admin_page_context",
    "execute_feedback_admin_status_update",
]