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