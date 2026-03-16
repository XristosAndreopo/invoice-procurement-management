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

from typing import Any


def _as_clean_text(value: Any) -> str:
    """
    Normalize a value into a stripped display string.
    """
    if value is None:
        return ""
    return str(value).strip()


def procurement_row_class(proc: Any) -> str:
    """
    Compute CSS class for a procurement row based on status / stage priority.
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


__all__ = ["procurement_row_class"]