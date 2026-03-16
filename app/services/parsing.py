"""
app/services/parsing.py

Shared parsing and safe-navigation helpers for the application.

PURPOSE
-------
This module centralizes small, repeated parsing utilities that previously
appeared across many route files.

Typical duplicated examples in the project were:
- parse optional integer ids from forms / query strings
- parse Decimal values that may use comma or dot
- parse optional HTML date input values
- normalize digit-only values (AFM / VAT-like filters)
- safely resolve the "next" redirect target

WHY THIS MODULE EXISTS
----------------------
Without a shared parsing module, route files tend to accumulate many small
helpers such as:

    _parse_optional_int(...)
    _parse_decimal(...)
    _parse_optional_date(...)
    _safe_next_url(...)
    _get_next_from_request(...)

Those helpers are easy to duplicate, but duplication causes problems:
- inconsistent behavior between blueprints
- slightly different validation rules
- harder maintenance
- more noise inside route files

This module provides a single canonical implementation for those concerns.

SECURITY NOTES
--------------
The application follows the rule:

    UI is never trusted.

That means parsing is not just about convenience; it is part of defensive
server-side validation.

Especially for redirect targets:
- never trust arbitrary "next" URLs from user input
- only allow local, relative application paths
- reject external redirects

FUNCTIONS PROVIDED
------------------
- parse_optional_int(value)
- parse_decimal(value)
- parse_optional_date(value)
- normalize_digits(value)
- safe_next_url(raw_next, fallback_endpoint)
- next_from_request(fallback_endpoint)

DEPENDENCIES
------------
- Standard library only, except:
  - flask.request / flask.url_for for redirect helpers
"""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from flask import request, url_for


def parse_optional_int(value: str | None) -> int | None:
    """
    Parse an optional integer value.

    PARAMETERS
    ----------
    value:
        A string-like value from form/query input, or None.

    RETURNS
    -------
    int | None
        - Returns int(value) when the input is a valid integer string.
        - Returns None when:
            * the input is None
            * the input is empty/whitespace
            * the input is invalid

    EXAMPLES
    --------
    parse_optional_int("15")      -> 15
    parse_optional_int(" 15 ")    -> 15
    parse_optional_int("")        -> None
    parse_optional_int(None)      -> None
    parse_optional_int("abc")     -> None

    WHY THIS HELPER EXISTS
    ----------------------
    Many route handlers receive optional foreign-key ids from forms and query
    strings. Repeating this logic everywhere creates noise and inconsistency.

    DESIGN DECISION
    ---------------
    Invalid input returns None instead of raising ValueError because route
    handlers usually want to respond with a user-facing flash message instead
    of crashing the request.
    """
    if value is None:
        return None

    raw = str(value).strip()
    if raw == "":
        return None

    try:
        return int(raw)
    except ValueError:
        return None


def parse_decimal(value: str | None) -> Decimal | None:
    """
    Parse a Decimal from user input.

    PARAMETERS
    ----------
    value:
        String-like numeric input from form/query values.

    RETURNS
    -------
    Decimal | None
        - Returns Decimal for valid numeric input
        - Returns None for empty or invalid input

    SUPPORTED INPUT STYLES
    ----------------------
    Both dot and comma decimals are supported:

    - "12.50" -> Decimal("12.50")
    - "12,50" -> Decimal("12.50")

    EXAMPLES
    --------
    parse_decimal("10")      -> Decimal("10")
    parse_decimal("10.25")   -> Decimal("10.25")
    parse_decimal("10,25")   -> Decimal("10.25")
    parse_decimal("")        -> None
    parse_decimal("abc")     -> None

    WHY THIS HELPER EXISTS
    ----------------------
    Greek / European users often type decimal numbers with commas. Supporting
    both comma and dot avoids unnecessary input friction while keeping the
    stored type consistent.

    DESIGN DECISION
    ---------------
    Invalid numeric input returns None so the caller can decide:
    - whether None is acceptable
    - whether to flash an error message
    - whether to fall back to a default value
    """
    if value is None:
        return None

    raw = str(value).strip().replace(",", ".")
    if raw == "":
        return None

    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def parse_optional_date(value: str | None) -> date | None:
    """
    Parse an optional HTML date input string (YYYY-MM-DD).

    PARAMETERS
    ----------
    value:
        String-like date value, usually from an <input type="date"> field.

    RETURNS
    -------
    date | None
        A Python date instance for valid input, otherwise None.

    EXPECTED FORMAT
    ---------------
    HTML date inputs usually submit values as:

        YYYY-MM-DD

    EXAMPLES
    --------
    parse_optional_date("2025-01-10") -> date(2025, 1, 10)
    parse_optional_date("")           -> None
    parse_optional_date(None)         -> None
    parse_optional_date("10/01/2025") -> None

    WHY THIS HELPER EXISTS
    ----------------------
    Many procurement forms contain optional date fields:
    - invoice_date
    - materials_receipt_date
    - invoice_receipt_date

    The route layer typically needs "safe optional parsing" rather than
    exception-driven parsing.
    """
    if value is None:
        return None

    raw = str(value).strip()
    if raw == "":
        return None

    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def normalize_digits(value: str | None) -> str:
    """
    Keep only numeric digits from a value.

    PARAMETERS
    ----------
    value:
        Any string-like value that may contain formatting characters.

    RETURNS
    -------
    str
        A string containing only digit characters.

    EXAMPLES
    --------
    normalize_digits("094-123-456") -> "094123456"
    normalize_digits(" 12 34 ")     -> "1234"
    normalize_digits(None)          -> ""

    COMMON USE CASES
    ----------------
    - AFM filtering
    - phone / number cleanup
    - VAT-like filter normalization

    WHY THIS HELPER EXISTS
    ----------------------
    Filters often need a loose, user-friendly search. Users may type separators,
    spaces, or punctuation. Normalizing to digits makes comparisons easier.
    """
    if not value:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def safe_next_url(raw_next: str | None, fallback_endpoint: str) -> str:
    """
    Safely resolve a user-provided "next" URL.

    PARAMETERS
    ----------
    raw_next:
        The raw "next" value from query string or form data.
    fallback_endpoint:
        Flask endpoint name used when raw_next is missing or unsafe.

    RETURNS
    -------
    str
        A safe local URL:
        - returns raw_next only if it is a relative local path
        - otherwise returns url_for(fallback_endpoint)

    SECURITY RULES
    --------------
    This helper intentionally rejects:
    - absolute URLs with scheme, e.g. https://example.com/...
    - URLs with netloc/domain
    - non-path values not starting with "/"

    WHY THIS HELPER EXISTS
    ----------------------
    Redirecting to unvalidated "next" parameters can create open redirect
    vulnerabilities.

    SAFE EXAMPLES
    -------------
    raw_next = "/procurements/all?page=2"
    -> allowed

    UNSAFE EXAMPLES
    ---------------
    raw_next = "https://evil.example"
    -> rejected, fallback used

    raw_next = "procurements/all"
    -> rejected, fallback used
    """
    if not raw_next:
        return url_for(fallback_endpoint)

    try:
        parsed = urlparse(raw_next)
    except Exception:
        return url_for(fallback_endpoint)

    if parsed.scheme or parsed.netloc:
        return url_for(fallback_endpoint)

    if not raw_next.startswith("/"):
        return url_for(fallback_endpoint)

    return raw_next


def next_from_request(fallback_endpoint: str) -> str:
    """
    Read "next" from the current request and return a safe local URL.

    PARAMETERS
    ----------
    fallback_endpoint:
        Flask endpoint name used as a safe fallback when no valid "next"
        parameter is available.

    RETURNS
    -------
    str
        Safe redirect target.

    RESOLUTION ORDER
    ----------------
    This helper checks:
    1. request.args["next"]
    2. request.form["next"]

    It then passes the result to safe_next_url(...).

    WHY THIS HELPER EXISTS
    ----------------------
    Many views support the pattern:
    - user opens edit page from a filtered list
    - after save/delete, user should return to the same logical list
    - the "next" value may come from either GET or POST

    Centralizing this logic avoids repeating the same secure redirect code in
    every route file.
    """
    raw_next = request.args.get("next") or request.form.get("next")
    return safe_next_url(raw_next, fallback_endpoint=fallback_endpoint)