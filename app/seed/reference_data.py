"""
app/seed_reference_data.py

Idempotent reference-data seeding for the Invoice / Procurement Management
System.

PURPOSE
-------
This module contains the database logic that ensures core reference-data rows
exist and remain aligned with the canonical defaults.

WHY THIS FILE EXISTS
--------------------
Previously, `app/seed.py` mixed:
- constant default values
- database upsert-like seeding logic
- execution entrypoints

This module isolates the database-facing seeding behavior so that:
- idempotent seed logic is easier to test and review
- constant defaults stay separate from persistence logic
- the public seed facade stays small and stable

SEEDING PRINCIPLES
------------------
1. Safe to run multiple times
2. Existing canonical rows are updated when needed
3. Missing canonical rows are created
4. Data is flushed as needed, then committed once at the orchestration layer

IMPORTANT
---------
This module does NOT commit inside low-level helper functions.
The orchestration function decides the transaction boundary.

SEEDED DOMAINS
--------------
- Generic option categories / values
- Income tax rules
- Withholding profiles

EXCLUDED DOMAINS
----------------
This module intentionally does NOT seed:
- Personnel
- Suppliers
- Users

Those are first-class business entities rather than simple reference data.
"""

from __future__ import annotations

from ..extensions import db
from ..models import (
    IncomeTaxRule,
    OptionCategory,
    OptionValue,
    WithholdingProfile,
)
from .defaults import (
    DEFAULT_INCOME_TAX_RULES,
    DEFAULT_OPTION_CATEGORIES,
    DEFAULT_WITHHOLDING_PROFILES,
)


def get_or_create_option_category(key: str, label: str) -> OptionCategory:
    """
    Ensure an OptionCategory exists and return it.

    BEHAVIOR
    --------
    - Finds by canonical key
    - Updates the label if the row already exists
    - Creates the row if missing

    PARAMETERS
    ----------
    key:
        Canonical category key.
    label:
        Human-readable category label.

    RETURNS
    -------
    OptionCategory
        Existing or newly created category row.
    """
    category = OptionCategory.query.filter_by(key=key).first()

    if category:
        category.label = label
        return category

    category = OptionCategory(key=key, label=label)
    db.session.add(category)
    db.session.flush()
    return category


def seed_option_categories_and_values() -> None:
    """
    Seed canonical OptionCategory and OptionValue rows.

    IDEMPOTENT BEHAVIOR
    -------------------
    - Matches categories by key
    - Updates category labels if they changed
    - Creates missing categories
    - Creates missing values
    - Updates sort_order of canonical values
    - Reactivates canonical values if they already exist but were inactive

    IMPORTANT
    ---------
    This function does not remove non-canonical extra values.
    That is intentional, because administrators may have introduced local
    business-specific values that should not be deleted automatically.
    """
    for category_key, category_label, values in DEFAULT_OPTION_CATEGORIES:
        category = get_or_create_option_category(category_key, category_label)

        for sort_order, value_text in enumerate(values, start=1):
            existing = OptionValue.query.filter_by(
                category_id=category.id,
                value=value_text,
            ).first()

            if existing:
                existing.sort_order = sort_order
                if existing.is_active is None or existing.is_active is False:
                    existing.is_active = True
                continue

            db.session.add(
                OptionValue(
                    category_id=category.id,
                    value=value_text,
                    sort_order=sort_order,
                    is_active=True,
                )
            )

    db.session.flush()


def seed_income_tax_rules() -> None:
    """
    Seed canonical IncomeTaxRule defaults.

    IDEMPOTENT BEHAVIOR
    -------------------
    - Matches existing rows by description
    - Updates rate/threshold if the row already exists
    - Creates missing rows
    """
    for description, rate_percent, threshold_amount in DEFAULT_INCOME_TAX_RULES:
        existing = IncomeTaxRule.query.filter_by(description=description).first()

        if existing:
            existing.rate_percent = rate_percent
            existing.threshold_amount = threshold_amount

            if existing.is_active is None:
                existing.is_active = True

            continue

        db.session.add(
            IncomeTaxRule(
                description=description,
                rate_percent=rate_percent,
                threshold_amount=threshold_amount,
                is_active=True,
            )
        )

    db.session.flush()


def seed_withholding_profiles() -> None:
    """
    Seed canonical WithholdingProfile defaults.

    IDEMPOTENT BEHAVIOR
    -------------------
    - Matches existing rows by description
    - Updates component values if the row already exists
    - Creates missing rows
    """
    for description, mt_eloa, eadhsy, withholding1, withholding2 in DEFAULT_WITHHOLDING_PROFILES:
        existing = WithholdingProfile.query.filter_by(description=description).first()

        if existing:
            existing.mt_eloa_percent = mt_eloa
            existing.eadhsy_percent = eadhsy
            existing.withholding1_percent = withholding1
            existing.withholding2_percent = withholding2

            if existing.is_active is None:
                existing.is_active = True

            continue

        db.session.add(
            WithholdingProfile(
                description=description,
                mt_eloa_percent=mt_eloa,
                eadhsy_percent=eadhsy,
                withholding1_percent=withholding1,
                withholding2_percent=withholding2,
                is_active=True,
            )
        )

    db.session.flush()


def seed_reference_data() -> None:
    """
    Seed all default reference data.

    EXECUTION ORDER
    ---------------
    1. Option categories / values
    2. Income tax rules
    3. Withholding profiles

    TRANSACTION
    -----------
    A single commit at the end keeps the seed operation reasonably atomic for
    normal application use.

    IMPORTANT
    ---------
    This function owns the commit boundary for the overall reference-data seed.
    """
    seed_option_categories_and_values()
    seed_income_tax_rules()
    seed_withholding_profiles()
    db.session.commit()