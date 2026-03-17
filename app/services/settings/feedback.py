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

