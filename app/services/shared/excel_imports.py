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

