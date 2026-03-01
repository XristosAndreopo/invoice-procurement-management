# C:\Users\xrist\vs code projects\Invoice Management System\app\models.py
"""
Invoice Management System – Enterprise Domain Models (V4)

Includes existing V3+ models and adds enterprise master-data for:
- Income Tax Rules (Φόρος Εισοδήματος / Α/Α 2 description source)
- Withholding Profiles (Κρατήσεις υπέρ δημοσίου multi-column)
- Procurement Committees (ανά ServiceUnit, managed by Manager/Admin)

Procurement enhancements:
- income_tax_rule_id (drives Α/Α 2 description + FE calculation)
- withholding_profile_id (drives κρατήσεις selection + breakdown)
- committee_id (service-specific committee selection)

NEW (V4.1) – Procurement implementation phase fields:
- adam_aay, ada_aay
- adam_prosklisis, adam_apofasis_anathesis
- contract_number, adam_contract, protocol_number

IMPORTANT:
- UI is never trusted. Any selection must be validated server-side in routes.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import db


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _to_decimal(value) -> Decimal:
    """Convert Numeric/None to Decimal safely."""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value))


def _normalize_percent(rate: Decimal) -> Decimal:
    """
    Normalize percent value to fraction (for inputs that may be percent or fraction):
    - If rate is 6    => 0.06
    - If rate is 0.06 => 0.06

    IMPORTANT:
    - Keep this behavior for fields where UI may send 24 or 0.24 (e.g. VAT).
    - For master-data percents that are always stored as percent (e.g. 0.10 means 0.10%),
      DO NOT use this helper. Use _percent_to_fraction().
    """
    if rate > Decimal("1"):
        return (rate / Decimal("100")).quantize(Decimal("0.0000001"))
    return rate.quantize(Decimal("0.0000001"))


def _percent_to_fraction(percent_value: Decimal) -> Decimal:
    """
    Convert a percent value (ALWAYS percent) to fraction:
      0.10% => 0.001
      6.00% => 0.06

    This is required for WithholdingProfile where stored values are percents,
    including sub-1% values like 0.10%.
    """
    return (percent_value / Decimal("100")).quantize(Decimal("0.0000001"))


def _display_percent(rate: Decimal) -> Decimal:
    """
    Display percent for UI:
    - If stored as 24 => 24
    - If stored as 0.24 => 24
    """
    if rate <= Decimal("1") and rate != Decimal("0"):
        return (rate * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _money(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------
# Core directory & users
# ---------------------------------------------------------------------
class Personnel(db.Model):
    """Organizational directory person (Admin-managed)."""

    __tablename__ = "personnel"

    id = db.Column(db.Integer, primary_key=True)

    agm = db.Column(db.String(50), nullable=False, unique=True, index=True)
    aem = db.Column(db.String(50), nullable=True, index=True)

    rank = db.Column(db.String(100), nullable=True)
    specialty = db.Column(db.String(150), nullable=True)

    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

    # Personnel assigned to a ServiceUnit (for handler selection)
    service_unit_id = db.Column(
        db.Integer,
        db.ForeignKey("service_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship(
        "User",
        back_populates="personnel",
        uselist=False,
        cascade="all, delete",
    )

    service_unit = db.relationship(
        "ServiceUnit",
        foreign_keys=[service_unit_id],
        backref=db.backref("personnel_members", lazy=True),
    )

    def full_name(self):
        return f"{self.rank or ''} {self.last_name} {self.first_name}".strip()

    def __repr__(self):
        return f"<Personnel {self.full_name()}>"


class User(UserMixin, db.Model):
    """System login user (1-1 with Personnel)."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    is_admin = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    theme = db.Column(db.String(20), nullable=True, default="default")

    personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    service_unit_id = db.Column(
        db.Integer,
        db.ForeignKey("service_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    personnel = db.relationship("Personnel", back_populates="user")

    service_unit = db.relationship(
        "ServiceUnit",
        back_populates="users",
        foreign_keys=[service_unit_id],
    )

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def is_manager(self):
        if not self.service_unit:
            return False
        return self.service_unit.manager_personnel_id == self.personnel_id

    def is_deputy(self):
        if not self.service_unit:
            return False
        return self.service_unit.deputy_personnel_id == self.personnel_id

    def can_manage(self):
        return self.is_admin or self.is_manager() or self.is_deputy()

    def can_view(self):
        return self.is_admin or self.service_unit_id is not None

    def __repr__(self):
        return f"<User {self.username}>"


# ---------------------------------------------------------------------
# Generic option lists (existing)
# ---------------------------------------------------------------------
class OptionCategory(db.Model):
    __tablename__ = "option_categories"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    label = db.Column(db.String(120), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class OptionValue(db.Model):
    __tablename__ = "option_values"

    id = db.Column(db.Integer, primary_key=True)

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("option_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    value = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)

    category = db.relationship(
        "OptionCategory",
        backref=db.backref("values", lazy=True, cascade="all, delete-orphan"),
    )

    __table_args__ = (db.UniqueConstraint("category_id", "value", name="uq_category_value"),)


# ---------------------------------------------------------------------
# Enterprise master-data (NEW)
# ---------------------------------------------------------------------
class IncomeTaxRule(db.Model):
    """
    Income tax rule (Φόρος Εισοδήματος).

    This is the source of the 'Α/Α 2 description' selection in Procurement.
    Calculation uses:
    - threshold_amount (e.g. 150.00)
    - rate_percent (e.g. 8.00 or 4.00)
    """

    __tablename__ = "income_tax_rules"

    id = db.Column(db.Integer, primary_key=True)

    description = db.Column(db.String(255), nullable=False, unique=True, index=True)

    # Stored as percent (e.g. 8.00). Normalized in calculations.
    rate_percent = db.Column(db.Numeric(6, 2), nullable=False, default=Decimal("0.00"))

    # Threshold pre-VAT amount (e.g. 150.00)
    threshold_amount = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("150.00"))

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class WithholdingProfile(db.Model):
    """
    Withholding profile (Κρατήσεις υπέρ δημοσίου).

    Fields are stored as percent values:
    - mt_eloa_percent (e.g. 6.00)
    - eadhsy_percent (e.g. 0.10)
    - withholding1_percent, withholding2_percent (reserved for future use)

    IMPORTANT:
    - 0.10 means 0.10% (not 10%).
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
        total = (
            _to_decimal(self.mt_eloa_percent)
            + _to_decimal(self.eadhsy_percent)
            + _to_decimal(self.withholding1_percent)
            + _to_decimal(self.withholding2_percent)
        )
        return _money(total)


class ProcurementCommittee(db.Model):
    """
    Procurement committee per ServiceUnit.

    Managed by:
    - Admin (all)
    - Manager/Deputy of the specific service unit (server-side enforced in routes)

    Each member is a Personnel of the same ServiceUnit (validated server-side).
    """

    __tablename__ = "procurement_committees"

    id = db.Column(db.Integer, primary_key=True)

    service_unit_id = db.Column(
        db.Integer,
        db.ForeignKey("service_units.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    description = db.Column(db.String(255), nullable=False, index=True)
    identity_text = db.Column(db.String(255), nullable=True)

    president_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    member1_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    member2_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    service_unit = db.relationship("ServiceUnit", backref=db.backref("committees", lazy=True))

    president = db.relationship("Personnel", foreign_keys=[president_personnel_id])
    member1 = db.relationship("Personnel", foreign_keys=[member1_personnel_id])
    member2 = db.relationship("Personnel", foreign_keys=[member2_personnel_id])

    __table_args__ = (
        db.UniqueConstraint("service_unit_id", "description", name="uq_committee_serviceunit_desc"),
    )

    def members_display(self) -> str:
        parts = []
        if self.president:
            parts.append(f"Πρόεδρος: {self.president.full_name()}")
        if self.member1:
            parts.append(f"Α' Μέλος: {self.member1.full_name()}")
        if self.member2:
            parts.append(f"Β' Μέλος: {self.member2.full_name()}")
        return " | ".join(parts) if parts else "—"


# ---------------------------------------------------------------------
# Service unit, suppliers
# ---------------------------------------------------------------------
class ServiceUnit(db.Model):
    """Organizational unit. Manager/Deputy selected from Personnel."""

    __tablename__ = "service_units"

    id = db.Column(db.Integer, primary_key=True)

    code = db.Column(db.String(50))
    description = db.Column(db.String(255), nullable=False)
    short_name = db.Column(db.String(100))

    aahit = db.Column(db.String(100))
    commander = db.Column(db.String(255))
    curator = db.Column(db.String(255))
    supply_officer = db.Column(db.String(255))

    manager_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    deputy_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    manager = db.relationship("Personnel", foreign_keys=[manager_personnel_id], backref="managed_units")
    deputy = db.relationship("Personnel", foreign_keys=[deputy_personnel_id], backref="deputy_units")

    users = db.relationship("User", back_populates="service_unit", lazy=True)

    procurements = db.relationship(
        "Procurement",
        back_populates="service_unit",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<ServiceUnit {self.short_name or self.description}>"


class Supplier(db.Model):
    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)

    afm = db.Column(db.String(9), nullable=False, unique=True, index=True)
    name = db.Column(db.String(255), nullable=False)

    address = db.Column(db.String(255))
    city = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    country = db.Column(db.String(100))
    bank_name = db.Column(db.String(120))
    iban = db.Column(db.String(34))

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<Supplier {self.afm} - {self.name}>"


# ---------------------------------------------------------------------
# Procurement domain
# ---------------------------------------------------------------------
class Procurement(db.Model):
    __tablename__ = "procurements"

    id = db.Column(db.Integer, primary_key=True)

    fiscal_year = db.Column(db.Integer, index=True)

    service_unit_id = db.Column(
        db.Integer,
        db.ForeignKey("service_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    service = db.Column(db.String(255))
    serial_no = db.Column(db.String(50))
    description = db.Column(db.Text)
    ale = db.Column(db.String(50), index=True)

    allocation = db.Column(db.String(80), index=True)
    quarterly = db.Column(db.String(80), index=True)
    status = db.Column(db.String(80), index=True)
    stage = db.Column(db.String(80), index=True)

    # legacy free text
    handler = db.Column(db.String(255), index=True)

    # handler as Personnel FK (preferred)
    handler_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    handler_personnel = db.relationship("Personnel", foreign_keys=[handler_personnel_id])

    # AA 2 description source (Income Tax Rule)
    income_tax_rule_id = db.Column(
        db.Integer,
        db.ForeignKey("income_tax_rules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    income_tax_rule = db.relationship("IncomeTaxRule", foreign_keys=[income_tax_rule_id])

    # Withholding selection (table profile)
    withholding_profile_id = db.Column(
        db.Integer,
        db.ForeignKey("withholding_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    withholding_profile = db.relationship("WithholdingProfile", foreign_keys=[withholding_profile_id])

    # Committee selection (service-specific) – selected in implementation phase
    committee_id = db.Column(
        db.Integer,
        db.ForeignKey("procurement_committees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    committee = db.relationship("ProcurementCommittee", foreign_keys=[committee_id])

    requested_amount = db.Column(db.Numeric(12, 2))
    approved_amount = db.Column(db.Numeric(12, 2))

    vat_rate = db.Column(db.Numeric(5, 4))
    sum_total = db.Column(db.Numeric(12, 2))
    vat_amount = db.Column(db.Numeric(12, 2))
    grand_total = db.Column(db.Numeric(12, 2))

    # ΗΩΠ workflow fields
    hop_commitment = db.Column(db.String(50), nullable=True, index=True)
    hop_forward1_commitment = db.Column(db.String(50), nullable=True, index=True)
    hop_forward2_commitment = db.Column(db.String(50), nullable=True, index=True)
    hop_approval_commitment = db.Column(db.String(50), nullable=True, index=True)
    hop_preapproval = db.Column(db.String(50), nullable=True, index=True)
    hop_forward1_preapproval = db.Column(db.String(50), nullable=True, index=True)
    hop_forward2_preapproval = db.Column(db.String(50), nullable=True, index=True)
    hop_approval = db.Column(db.String(50), nullable=True, index=True)

    aay = db.Column(db.String(50), nullable=True, index=True)

    # Implementation phase fields
    adam_aay = db.Column(db.String(100), nullable=True, index=True)  # ΑΔΑΜ ΑΑΥ
    ada_aay = db.Column(db.String(100), nullable=True, index=True)  # ΑΔΑ ΑΑΥ
    adam_prosklisis = db.Column(db.String(100), nullable=True, index=True)  # ΑΔΑΜ ΠΡΟΣΚΛΗΣΗΣ
    adam_apofasis_anathesis = db.Column(db.String(100), nullable=True, index=True)  # ΑΔΑΜ ΑΠΟΦΑΣΗΣ ΑΝΑΘΕΣΗΣ
    contract_number = db.Column(db.String(100), nullable=True, index=True)  # ΑΡΙΘΜΟΣ ΣΥΜΒΑΣΗΣ
    adam_contract = db.Column(db.String(100), nullable=True, index=True)  # ΑΔΑΜ ΣΥΜΒΑΣΗΣ
    protocol_number = db.Column(db.String(100), nullable=True, index=True)  # ΑΡΙΘΜΟΣ ΠΡΩΤΟΚΟΛΛΟΥ

    procurement_notes = db.Column(db.Text, nullable=True)

    send_to_expenses = db.Column(db.Boolean, default=False, nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    service_unit = db.relationship("ServiceUnit", back_populates="procurements")

    supplies_links = db.relationship(
        "ProcurementSupplier",
        backref="procurement",
        lazy=True,
        cascade="all, delete-orphan",
    )

    materials = db.relationship(
        "MaterialLine",
        back_populates="procurement",
        cascade="all, delete-orphan",
    )

    @property
    def winner_supplier_display(self):
        """
        Legacy display: "AFM - Name" for winner supplier (if any).

        NOTE:
        - Keep for backward compatibility.
        - For list columns requiring separate AFM and Name, use:
            - winner_supplier_afm
            - winner_supplier_name
        """
        winner_link = None
        for link in self.supplies_links or []:
            if link.is_winner:
                winner_link = link
                break
        if not winner_link or not winner_link.supplier:
            return None
        return f"{winner_link.supplier.afm} - {winner_link.supplier.name}"

    @property
    def winner_supplier_afm(self) -> str | None:
        """
        Winner supplier AFM (separate column use).

        IMPORTANT:
        - UI requires AFM as its own field in procurement lists.
        """
        for link in self.supplies_links or []:
            if link.is_winner and link.supplier:
                return link.supplier.afm
        return None

    @property
    def winner_supplier_name(self) -> str | None:
        """
        Winner supplier Name (separate column use).

        IMPORTANT:
        - UI requires only the supplier's name in "Μειοδότης" column.
        """
        for link in self.supplies_links or []:
            if link.is_winner and link.supplier:
                return link.supplier.name
        return None

    @property
    def handler_display(self):
        """Preferred handler display (Personnel). Falls back to legacy handler string."""
        if self.handler_personnel:
            return self.handler_personnel.full_name()
        return self.handler or None

    @property
    def aa2_description(self) -> str | None:
        """Α/Α 2 description derived from selected IncomeTaxRule."""
        if self.income_tax_rule and self.income_tax_rule.description:
            return self.income_tax_rule.description
        return None

    def recalc_totals(self):
        total = Decimal("0.00")
        for line in self.materials:
            if line.quantity and line.unit_price:
                total += Decimal(str(line.quantity)) * Decimal(str(line.unit_price))

        self.sum_total = _money(total)

        if not self.vat_rate:
            self.vat_amount = Decimal("0.00")
            self.grand_total = self.sum_total
            return

        rate = Decimal(str(self.vat_rate))
        rate = _normalize_percent(rate)

        vat = _money(self.sum_total * rate)
        self.vat_amount = vat
        self.grand_total = _money(self.sum_total + vat)

    # -----------------------------
    # Enterprise payment breakdown
    # -----------------------------
    def compute_public_withholdings(self) -> dict:
        """
        Compute public withholdings breakdown based on selected WithholdingProfile.

        IMPORTANT:
        - WithholdingProfile percent fields are ALWAYS percents (0.10 means 0.10%).
        - Therefore we must always convert by dividing by 100.
        """
        base = _to_decimal(self.sum_total)
        profile = self.withholding_profile

        if not profile or not profile.is_active:
            return {"items": [], "total_percent": Decimal("0.00"), "total_amount": Decimal("0.00")}

        parts = [
            ("ΜΤ-ΕΛΟΑ", _to_decimal(profile.mt_eloa_percent)),
            ("ΕΑΔΗΣΥ", _to_decimal(profile.eadhsy_percent)),
            ("ΚΡΑΤΗΣΗ 1", _to_decimal(profile.withholding1_percent)),
            ("ΚΡΑΤΗΣΗ 2", _to_decimal(profile.withholding2_percent)),
        ]

        items = []
        total_amount = Decimal("0.00")
        total_percent = Decimal("0.00")

        for label, pct in parts:
            pct_money = _money(pct or Decimal("0.00"))
            if pct_money == Decimal("0.00"):
                continue

            frac = _percent_to_fraction(pct_money)
            amt = _money(base * frac)

            items.append({"label": label, "percent": pct_money, "amount": amt})
            total_amount += amt
            total_percent += pct_money

        return {
            "items": items,
            "total_percent": _money(total_percent),
            "total_amount": _money(total_amount),
        }

    def compute_income_tax(self) -> dict:
        """
        Compute income tax (ΦΕ) based on selected IncomeTaxRule and threshold.

        Formula per requirement:
          FE = (SumTotal - PublicWithholdingsTotal) * rate%
        """
        base_total = _to_decimal(self.sum_total)
        withh = self.compute_public_withholdings()
        after_withholdings = _money(base_total - _to_decimal(withh["total_amount"]))

        rule = self.income_tax_rule
        if not rule or not rule.is_active:
            return {
                "description": None,
                "rate_percent": Decimal("0.00"),
                "threshold": Decimal("0.00"),
                "amount": Decimal("0.00"),
            }

        threshold = _to_decimal(rule.threshold_amount)
        rate_pct = _to_decimal(rule.rate_percent)

        if base_total <= threshold:
            return {
                "description": rule.description,
                "rate_percent": _money(rate_pct),
                "threshold": _money(threshold),
                "amount": Decimal("0.00"),
            }

        rate_frac = _normalize_percent(rate_pct)
        amt = _money(after_withholdings * rate_frac)

        return {
            "description": rule.description,
            "rate_percent": _money(rate_pct),
            "threshold": _money(threshold),
            "amount": amt,
        }

    def compute_payment_analysis(self) -> dict:
        """
        Full payment analysis required by UX.
        """
        sum_total = _to_decimal(self.sum_total)
        public_withh = self.compute_public_withholdings()
        income_tax = self.compute_income_tax()

        vat_pct_raw = _to_decimal(self.vat_rate)
        vat_frac = _normalize_percent(vat_pct_raw) if vat_pct_raw else Decimal("0.00")
        vat_amount = _money(sum_total * vat_frac)

        payable = _money(
            sum_total
            - _to_decimal(public_withh["total_amount"])
            - _to_decimal(income_tax["amount"])
            + vat_amount
        )

        return {
            "sum_total": _money(sum_total),
            "public_withholdings": public_withh,
            "income_tax": income_tax,
            # For UI: always show percent number (24.00) even if stored as 0.24
            "vat_percent": _display_percent(vat_pct_raw),
            "vat_amount": _money(vat_amount),
            "payable_total": _money(payable),
        }


class ProcurementSupplier(db.Model):
    __tablename__ = "procurement_suppliers"

    id = db.Column(db.Integer, primary_key=True)

    procurement_id = db.Column(
        db.Integer,
        db.ForeignKey("procurements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    result = db.Column(db.String(80))
    is_winner = db.Column(db.Boolean, default=False)
    offered_amount = db.Column(db.Numeric(12, 2))

    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    supplier = db.relationship("Supplier", backref=db.backref("procurement_links", lazy=True))

    __table_args__ = (
        db.UniqueConstraint("procurement_id", "supplier_id", name="uq_procurement_supplier"),
    )


class MaterialLine(db.Model):
    __tablename__ = "material_lines"

    id = db.Column(db.Integer, primary_key=True)

    procurement_id = db.Column(
        db.Integer,
        db.ForeignKey("procurements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    line_no = db.Column(db.Integer)
    is_service = db.Column(db.Boolean, default=False)
    description = db.Column(db.Text, nullable=False)
    cpv = db.Column(db.String(50))
    nsn = db.Column(db.String(50))
    unit = db.Column(db.String(50))

    quantity = db.Column(db.Numeric(12, 2), nullable=False, default=1)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    procurement = db.relationship("Procurement", back_populates="materials")

    @property
    def total_pre_vat(self):
        if not self.quantity or not self.unit_price:
            return Decimal("0.00")

        return (Decimal(str(self.quantity)) * Decimal(str(self.unit_price))).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )


class Feedback(db.Model):
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    related_procurement_id = db.Column(db.Integer, db.ForeignKey("procurements.id", ondelete="SET NULL"), index=True)

    category = db.Column(db.String(50))
    subject = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default="new", index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship("User", backref="feedback_items")
    related_procurement = db.relationship("Procurement", backref=db.backref("feedback_entries", lazy=True))


class AuditLog(db.Model):
    """Enterprise-grade audit logging."""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    username_snapshot = db.Column(db.String(150), nullable=True)

    entity_type = db.Column(db.String(50), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)

    action = db.Column(db.String(20), nullable=False, index=True)

    before_data = db.Column(db.Text, nullable=True)
    after_data = db.Column(db.Text, nullable=True)

    ip_address = db.Column(db.String(45), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship("User", backref=db.backref("audit_entries", lazy=True))