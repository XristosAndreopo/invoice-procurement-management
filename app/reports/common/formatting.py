"""
Shared formatting helpers for report generation.

These helpers are intentionally pure and reusable across all report modules.
"""

from __future__ import annotations

import unicodedata
from datetime import date, datetime
from typing import Any


def safe_text(value: Any, default: str = "—") -> str:
    """
    Convert any value to a stripped display string.

    PARAMETERS
    ----------
    value:
        Any incoming value.

    default:
        Fallback string used when the normalized text is empty.

    RETURNS
    -------
    str
        The normalized display string.
    """
    text = ("" if value is None else str(value)).strip()
    return text if text else default


def upper_no_accents(value: Any, default: str = "—") -> str:
    """
    Return uppercase Greek/Latin text without accents/diacritics.

    This is used for official document styling where all-caps Greek text
    without tonos is required.
    """
    text = safe_text(value, default=default)
    normalized = unicodedata.normalize("NFD", text)
    no_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", no_marks).upper()


def upper_service_name(value: Any, default: str = "—") -> str:
    """
    Return service-unit display name in uppercase without accents.
    """
    return upper_no_accents(value, default=default)


def lower_preserve_accents(value: Any, default: str = "—") -> str:
    """
    Return lowercase text while preserving accents/diacritics.
    """
    return safe_text(value, default=default).lower()


def format_date_ddmmyyyy(value: Any, default: str = "—") -> str:
    """
    Format a date-like value as DD/MM/YYYY.

    Accepted inputs:
    - datetime/date
    - any object exposing strftime
    - fallback to stripped text
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


def short_date_el(value: Any | None = None) -> str:
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


__all__ = [
    "safe_text",
    "upper_no_accents",
    "upper_service_name",
    "lower_preserve_accents",
    "format_date_ddmmyyyy",
    "short_date_el",
]