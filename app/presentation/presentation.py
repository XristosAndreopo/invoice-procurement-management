"""
app/presentation.py

Presentation-only helpers for the Invoice / Procurement Management System.

PURPOSE
-------
This module contains helpers that exist purely for UI rendering and visual
presentation decisions.

WHY THIS FILE EXISTS
--------------------
Historically, small generic helpers often accumulate in `app/utils.py`.
That tends to become a dumping ground over time.

This module gives presentation-specific helpers an explicit home so that:
- visual rendering rules stay separate from business logic
- route and service code do not re-implement UI decisions
- `app/utils.py` can remain a thin compatibility layer
- future developers have a clear place for template-facing helpers

IMPORTANT BOUNDARY
------------------
Helpers in this module may:
- inspect values already loaded into memory
- compute labels / CSS classes / display decisions

Helpers in this module must NOT:
- query the database
- perform authorization
- mutate application state
- enforce business rules

CURRENT CONTENTS
----------------
- procurement_row_class:
    Compute CSS class for procurement rows in list views
"""

from __future__ import annotations

from typing import Any


def _as_clean_text(value: Any) -> str:
    """
    Normalize a value into a stripped display string.

    PARAMETERS
    ----------
    value:
        Any object that should be interpreted as display text.

    RETURNS
    -------
    str
        Stripped string representation, or empty string when the value is None.

    WHY THIS EXISTS
    ---------------
    Presentation helpers often read values that may be:
    - None
    - already strings
    - lazy string-like values

    This helper keeps the normalization rule explicit and reusable.
    """
    if value is None:
        return ""
    return str(value).strip()


def procurement_row_class(proc: Any) -> str:
    """
    Compute CSS class for a procurement row based on status / stage priority.

    PRIORITY ORDER
    --------------
    1. status == "Ακυρωμένη"        -> "row-cancelled"
    2. status == "Πέρας"            -> "row-complete"
    3. stage == "Αποστολή Δαπάνης"  -> "row-expense"
    4. stage == "Έγκριση"           -> "row-approval"
    5. otherwise                    -> ""

    WHY PRIORITY MATTERS
    --------------------
    A procurement may have multiple relevant fields populated at the same time.
    We want one stable and deterministic visual result so list views render
    consistently.

    PARAMETERS
    ----------
    proc:
        Procurement-like object expected to expose `status` and `stage`
        attributes. A lightweight duck-typed contract is sufficient because
        this helper is presentation-only.

    RETURNS
    -------
    str
        CSS class name for row styling, or an empty string when no special
        styling applies.

    IMPORTANT
    ---------
    This helper is only for visual rendering. It must never be used for
    workflow decisions, filtering, permissions, or business-state validation.
    """
    status = _as_clean_text(getattr(proc, "status", None))
    stage = _as_clean_text(getattr(proc, "stage", None))

    if status == "Ακυρωμένη":
        return "row-cancelled"

    if status == "Πέρας":
        return "row-complete"

    if stage == "Αποστολή Δαπάνης":
        return "row-expense"

    if stage == "Έγκριση":
        return "row-approval"

    return ""