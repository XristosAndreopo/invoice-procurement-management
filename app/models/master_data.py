"""
app/models/master_data.py

Reference / master-data models.

CONTAINS
--------
- OptionCategory
- OptionValue
- AleKae
- Cpv
- IncomeTaxRule
- WithholdingProfile

WHY THESE MODELS LIVE TOGETHER
------------------------------
These entities are configuration / lookup tables used by the procurement
workflow.

They are:
- not transactional workflow entities
- not organizational hierarchy entities
- not user/account entities

Grouping them together makes the architecture clearer:
these are reusable master-data records that support the rest of the system.

ARCHITECTURAL BOUNDARY
----------------------
This module defines:
- persistence schema
- relationships
- lightweight display helpers
- small computed properties tightly coupled to the entity itself

This module must NOT become the place for:
- dropdown query orchestration
- import/export logic
- Excel parsing
- route validation flow
- CRUD service orchestration

Those responsibilities belong in:
- app.services.master_data_service
- app.services.excel_imports
- route/service layers

IMPORTANT NUMERIC NOTE
----------------------
Some financial master-data fields are stored as PERCENT VALUES, not fractions.

Example:
- 6.00 means 6.00%
- 0.10 means 0.10%

So any business calculation must be explicit about whether it expects:
- display percent
- stored percent
- normalized fraction

The conversion helpers in `app.models.helpers` exist to make that distinction
safe and predictable.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ..extensions import db
from .helpers import _display_percent, _money, _percent_to_fraction, _to_decimal


class OptionCategory(db.Model):
    """
    Generic option category used to group dropdown values.

    EXAMPLES
    --------
    Typical categories may represent:
    - status
    - stage
    - allocation
    - quarterly
    - VAT

    DESIGN NOTE
    -----------
    This is intentionally generic master data rather than a separate table per
    simple dropdown.
    """

    __tablename__ = "option_categories"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    label = db.Column(db.String(120), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def display_name(self) -> str:
        """
        Preferred human-readable category label.
        """
        return (self.label or self.key or "").strip()

    def __repr__(self) -> str:
        return f"<OptionCategory {self.key}>"


class OptionValue(db.Model):
    """
    Generic option value under an OptionCategory.

    RULES
    -----
    - belongs to one category
    - value must be unique within that category
    - may be active/inactive
    - may have explicit sort order
    """

    __tablename__ = "option_values"

    id = db.Column(db.Integer, primary_key=True)

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("option_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    value = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    sort_order = db.Column(db.Integer, default=0, nullable=False)

    category = db.relationship(
        "OptionCategory",
        backref=db.backref("values", lazy=True, cascade="all, delete-orphan"),
    )

    __table_args__ = (
        db.UniqueConstraint("category_id", "value", name="uq_category_value"),
    )

    @property
    def display_name(self) -> str:
        """
        Preferred human-readable option label.
        """
        return (self.value or "").strip()

    def __repr__(self) -> str:
        return f"<OptionValue {self.category_id}:{self.value}>"


class AleKae(db.Model):
    """
    ALE–KAE master directory (admin-managed).

    COLUMNS
    -------
    - ale
    - old_kae
    - description
    - responsibility

    USE CASE
    --------
    Supports procurement classification and reporting metadata.
    """

    __tablename__ = "ale_kae"

    id = db.Column(db.Integer, primary_key=True)

    ale = db.Column(db.String(80), nullable=False, unique=True, index=True)
    old_kae = db.Column(db.String(80), nullable=True, index=True)
    description = db.Column(db.Text, nullable=True)
    responsibility = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def display_name(self) -> str:
        """
        Human-readable label for dropdowns / admin lists.
        """
        ale = (self.ale or "").strip()
        desc = (self.description or "").strip()
        return f"{ale} - {desc}" if desc else ale

    def __repr__(self) -> str:
        return f"<AleKae {self.ale}>"


class Cpv(db.Model):
    """
    CPV master directory (admin-managed).

    USE CASE
    --------
    Supports line-level procurement classification and validation.
    """

    __tablename__ = "cpv"

    id = db.Column(db.Integer, primary_key=True)

    cpv = db.Column(db.String(50), nullable=False, unique=True, index=True)
    description = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def display_name(self) -> str:
        """
        Human-readable CPV label.
        """
        cpv = (self.cpv or "").strip()
        desc = (self.description or "").strip()
        return f"{cpv} - {desc}" if desc else cpv

    def __repr__(self) -> str:
        return f"<Cpv {self.cpv}>"


class IncomeTaxRule(db.Model):
    """
    Income tax rule (Φόρος Εισοδήματος).

    PURPOSE
    -------
    Used as procurement master data to determine:
    - tax description
    - rate percent
    - threshold amount

    Example logic:
    - if base total <= threshold -> no income tax amount
    - otherwise calculate based on selected rule

    IMPORTANT
    ---------
    `rate_percent` is stored as a percent-style value.
    For example:
    - 4.00 means 4.00%
    - 8.00 means 8.00%
    """

    __tablename__ = "income_tax_rules"

    id = db.Column(db.Integer, primary_key=True)

    description = db.Column(db.String(255), nullable=False, unique=True, index=True)
    rate_percent = db.Column(db.Numeric(6, 2), nullable=False, default=Decimal("0.00"))
    threshold_amount = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def rate_percent_display(self) -> Decimal:
        """
        Display-ready percent for UI/report usage.

        RETURNS
        -------
        Decimal
            Example:
            - stored 4.00 -> 4.00
            - stored 0.04 -> 4.00
        """
        return _display_percent(_to_decimal(self.rate_percent))

    @property
    def rate_fraction(self) -> Decimal:
        """
        Fractional form of the stored percent.

        Example:
        - 4.00 -> 0.04
        - 8.00 -> 0.08

        USE CASE
        --------
        Safe to use in calculations that multiply by a base amount.
        """
        return _percent_to_fraction(_to_decimal(self.rate_percent))

    @property
    def threshold_amount_money(self) -> Decimal:
        """
        Threshold rounded to standard money precision.
        """
        return _money(_to_decimal(self.threshold_amount))

    @property
    def display_name(self) -> str:
        """
        Preferred human-readable label for lists/dropdowns.
        """
        return (self.description or "").strip()

    def __repr__(self) -> str:
        return f"<IncomeTaxRule {self.description}>"


class WithholdingProfile(db.Model):
    """
    Withholding profile / κρατήσεις.

    PURPOSE
    -------
    Groups withholding components used during procurement calculations.

    COMPONENTS
    ----------
    - mt_eloa_percent
    - eadhsy_percent
    - withholding1_percent
    - withholding2_percent

    IMPORTANT STORAGE RULE
    ----------------------
    These fields are stored as true percent values.

    Example:
    - 0.10 means 0.10%
    - 6.00 means 6.00%

    This is why calculations must not use mixed percent normalization logic
    blindly. Conversion to fraction must be explicit.
    """

    __tablename__ = "withholding_profiles"

    id = db.Column(db.Integer, primary_key=True)

    description = db.Column(db.String(255), nullable=False, unique=True, index=True)

    mt_eloa_percent = db.Column(db.Numeric(6, 2), nullable=False, default=Decimal("0.00"))
    eadhsy_percent = db.Column(db.Numeric(6, 2), nullable=False, default=Decimal("0.00"))
    withholding1_percent = db.Column(db.Numeric(6, 2), nullable=False, default=Decimal("0.00"))
    withholding2_percent = db.Column(db.Numeric(6, 2), nullable=False, default=Decimal("0.00"))

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def total_percent(self) -> Decimal:
        """
        Sum all withholding components as display percent.

        RETURNS
        -------
        Decimal
            Rounded total percentage.
        """
        total = (
            _to_decimal(self.mt_eloa_percent)
            + _to_decimal(self.eadhsy_percent)
            + _to_decimal(self.withholding1_percent)
            + _to_decimal(self.withholding2_percent)
        )
        return _money(total)

    @property
    def total_fraction(self) -> Decimal:
        """
        Sum all withholding components as a fractional rate.

        Example:
        - total_percent == 6.10
        - total_fraction == 0.061
        """
        return (
            _percent_to_fraction(_to_decimal(self.mt_eloa_percent))
            + _percent_to_fraction(_to_decimal(self.eadhsy_percent))
            + _percent_to_fraction(_to_decimal(self.withholding1_percent))
            + _percent_to_fraction(_to_decimal(self.withholding2_percent))
        ).quantize(Decimal("0.0000001"))

    @property
    def display_name(self) -> str:
        """
        Preferred human-readable profile label.
        """
        return (self.description or "").strip()

    def __repr__(self) -> str:
        return f"<WithholdingProfile {self.description}>"