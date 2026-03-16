"""
app/seed/__init__.py

Public seed facade for the Invoice / Procurement Management System.

PURPOSE
-------
This package provides the stable public import surface for application
reference-data seeding.

PACKAGE STRUCTURE
-----------------
- app.seed.defaults
    Canonical static default values

- app.seed.reference_data
    Idempotent database seeding logic

- app.seed
    Backwards-compatible public facade and CLI helper

SCOPE
-----
This package seeds only reference data such as:
- dropdown categories / values
- income tax rules
- withholding profiles
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


def seed_default_options() -> None:
    """
    Backwards-compatible public entrypoint for reference-data seeding.
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
    "DEFAULT_OPTION_CATEGORIES",
    "DEFAULT_INCOME_TAX_RULES",
    "DEFAULT_WITHHOLDING_PROFILES",
    "get_or_create_option_category",
    "seed_option_categories_and_values",
    "seed_income_tax_rules",
    "seed_withholding_profiles",
    "seed_reference_data",
    "seed_default_options",
    "seed_options_command",
]