"""
app/models/helpers.py

Shared numeric and percentage helpers for model-adjacent financial logic.

PURPOSE
-------
This module contains small, reusable helpers that support model properties and
financial calculations closely related to the ORM layer.

WHY THIS FILE EXISTS
--------------------
The old monolithic `models.py` contained helper functions reused by multiple
entities and business calculations. Those helpers do not logically belong to
one specific SQLAlchemy model, so they live in this dedicated module.

This keeps model files focused on:
- schema definition
- relationships
- lightweight entity behavior

while shared numeric conversion / normalization / rounding logic lives here.

IMPORTANT DESIGN DECISION
-------------------------
These helpers are intentionally model-adjacent, not general-purpose utilities
for the whole application.

In other words:
- if a helper is specifically about procurement percentages, taxes, money, and
  SQLAlchemy numeric fields, it belongs here
- if later you need broader generic helpers (strings, dates, HTTP, etc.),
  those should live elsewhere

BOUNDARY
--------
This module may:
- convert values to Decimal
- normalize percent representations
- convert percent values to fractions
- prepare display percent values
- round monetary values deterministically

This module must NOT:
- query the database
- perform authorization
- depend on Flask request context
- contain route/service orchestration
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def _to_decimal(value: Any) -> Decimal:
    """
    Convert an arbitrary value to Decimal safely.

    PARAMETERS
    ----------
    value:
        Can be None, Decimal, int, float-like, or string-like.

    RETURNS
    -------
    Decimal
        - Decimal("0.00") when value is None
        - Decimal(str(value)) otherwise

    WHY THIS IMPLEMENTATION
    -----------------------
    Converting through `str(value)` avoids common binary float issues and works
    well with values coming from SQLAlchemy, forms, JSON, or mixed sources.

    EXAMPLES
    --------
    _to_decimal(None)      -> Decimal("0.00")
    _to_decimal("12.34")   -> Decimal("12.34")
    _to_decimal(5)         -> Decimal("5")
    """
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value))


def _normalize_percent(rate: Decimal | Any) -> Decimal:
    """
    Normalize a percentage-like input into fractional form.

    SUPPORTED INPUT STYLES
    ----------------------
    - 24    -> 0.24
    - 0.24  -> 0.24
    - 6     -> 0.06
    - 0.06  -> 0.06

    USE CASE
    --------
    This helper is intended for values where the UI or upstream input may send
    either:
    - a display percent (24)
    - or an already fractional value (0.24)

    IMPORTANT
    ---------
    Do NOT use this helper for master-data fields that are always stored as
    true percent values and may legitimately contain sub-1% rates such as
    0.10%.

    Those cases must use `_percent_to_fraction()`.

    PARAMETERS
    ----------
    rate:
        Decimal-like numeric value representing either percent or fraction.

    RETURNS
    -------
    Decimal
        Fractional representation quantized to 7 decimal places.
    """
    rate_dec = _to_decimal(rate)

    if rate_dec > Decimal("1"):
        return (rate_dec / Decimal("100")).quantize(Decimal("0.0000001"))

    return rate_dec.quantize(Decimal("0.0000001"))


def _percent_to_fraction(percent_value: Decimal | Any) -> Decimal:
    """
    Convert a true percentage value into fractional form.

    THIS DIFFERS FROM `_normalize_percent`
    --------------------------------------
    Here we assume the stored value is ALWAYS a percent.

    Examples
    --------
    - 0.10% -> 0.001
    - 6.00% -> 0.06

    PRIMARY USE
    -----------
    Master-data percentages such as withholding components where:
    - 0.10 means 0.10%
    - 6.00 means 6.00%

    PARAMETERS
    ----------
    percent_value:
        Decimal-like numeric value representing a true percent.

    RETURNS
    -------
    Decimal
        Fractional representation quantized to 7 decimal places.
    """
    percent_dec = _to_decimal(percent_value)
    return (percent_dec / Decimal("100")).quantize(Decimal("0.0000001"))


def _display_percent(rate: Decimal | Any) -> Decimal:
    """
    Convert an internally stored rate into display-percent form.

    SUPPORTED BEHAVIOR
    ------------------
    - stored as 24    -> display 24.00
    - stored as 0.24  -> display 24.00
    - stored as 0     -> display 0.00

    PARAMETERS
    ----------
    rate:
        Decimal-like numeric value stored internally either as:
        - percent (24)
        - fraction (0.24)
        - zero

    RETURNS
    -------
    Decimal
        Display percent rounded to 2 decimal places using ROUND_HALF_UP.
    """
    rate_dec = _to_decimal(rate)

    if rate_dec <= Decimal("1") and rate_dec != Decimal("0"):
        return (rate_dec * Decimal("100")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    return rate_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _money(value: Decimal | Any) -> Decimal:
    """
    Round a numeric value to standard money precision.

    WHY THIS HELPER EXISTS
    ----------------------
    Procurement calculations must produce deterministic monetary values for:
    - VAT
    - withholding amounts
    - income tax amounts
    - payable totals
    - report rendering

    PARAMETERS
    ----------
    value:
        Decimal-like numeric value.

    RETURNS
    -------
    Decimal
        Rounded to Decimal("0.01") using ROUND_HALF_UP.
    """
    return _to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

