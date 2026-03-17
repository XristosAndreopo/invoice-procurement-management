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