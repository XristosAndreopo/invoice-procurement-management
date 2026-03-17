"""
app/seed.py

Public seed facade for the Invoice / Procurement Management System.

PURPOSE
-------
This module remains the stable import surface for application reference-data
seeding.

After refactoring, responsibilities are split as follows:

- `app.seed_defaults`
    Canonical static default values

- `app.seed_reference_data`
    Idempotent database seeding logic

- `app.seed`
    Backwards-compatible public facade and CLI command

WHY THIS STRUCTURE IS BETTER
----------------------------
Previously, one file mixed:
- static seed defaults
- database seeding helpers
- orchestration / commit logic
- CLI entrypoints

Those concerns are related, but keeping them together makes the file harder to
scan and maintain.

Now:
- seed data is defined in one place
- seeding behavior lives in one place
- old imports continue to work

SCOPE
-----
This module seeds only reference data such as:
- dropdown categories / values
- income tax rules
- withholding profiles

It intentionally does NOT seed first-class business entities like:
- Personnel
- Suppliers
- Users
"""

from __future__ import annotations

import click

from .defaults import (
    DEFAULT_INCOME_TAX_RULES,
    DEFAULT_OPTION_CATEGORIES,
    DEFAULT_WITHHOLDING_PROFILES,
)
from .reference_data import (
    get_or_create_option_category,
    seed_income_tax_rules,
    seed_option_categories_and_values,
    seed_reference_data,
    seed_withholding_profiles,
)

# -------------------------------------------------------------------
# Backwards-compatible public name
# -------------------------------------------------------------------
# The rest of the application currently imports and calls:
#
#     from app.seed import seed_default_options
#
# so we preserve that stable name.
def seed_default_options() -> None:
    """
    Backwards-compatible public entrypoint for reference-data seeding.

    Delegates to `seed_reference_data()`.

    IMPORTANT
    ---------
    This function preserves the old import and call style used by the
    application bootstrap / CLI wiring.
    """
    seed_reference_data()


@click.command("seed-options")
def seed_options_command() -> None:
    """
    CLI command for seeding default option categories and reference-data.
    """
    seed_default_options()
    click.echo("Seeding completed.")


__all__ = [
    # Seed defaults
    "DEFAULT_OPTION_CATEGORIES",
    "DEFAULT_INCOME_TAX_RULES",
    "DEFAULT_WITHHOLDING_PROFILES",

    # Low-level helpers
    "get_or_create_option_category",
    "seed_option_categories_and_values",
    "seed_income_tax_rules",
    "seed_withholding_profiles",

    # Public orchestration
    "seed_reference_data",
    "seed_default_options",
    "seed_options_command",
]

