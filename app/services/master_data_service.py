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