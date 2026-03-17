"""
app/models/procurement.py

Procurement workflow models.

CONTAINS
--------
- ProcurementCommittee
- Procurement
- ProcurementSupplier
- MaterialLine

WHY THESE MODELS LIVE TOGETHER
------------------------------
These entities form the transactional procurement domain:

- ProcurementCommittee:
    service-unit-scoped committee metadata used by procurements

- Procurement:
    main workflow / document / financial aggregate root

- ProcurementSupplier:
    supplier participation rows under a procurement

- MaterialLine:
    line items that drive totals and classifications

These models are tightly related by foreign keys, workflow usage, and UI flows,
so keeping them together in one module is appropriate at this stage.

IMPORTANT ARCHITECTURAL BOUNDARY
--------------------------------
This module defines:
- persistence schema
- relationships
- lightweight display helpers
- small entity-local convenience methods
- delegation hooks into calculation services

This module must NOT become the place for:
- route flow
- complex query orchestration
- list filtering / eager-loading strategy
- form parsing
- authorization logic
- heavy financial calculation logic

Those responsibilities belong in:
- app.services.procurement_service
- app.services.procurement_calculations
- app.security
- route/service layers

DESIGN NOTE
-----------
Heavy procurement calculations are intentionally delegated to the service layer.

This keeps the ORM model focused on:
- persistence
- relationships
- lightweight convenience behavior

while complex numeric domain logic remains testable and reusable outside the
SQLAlchemy model class.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from ..extensions import db
from .helpers import _money, _to_decimal

if TYPE_CHECKING:
    from .supplier import Supplier


class ProcurementCommittee(db.Model):
    """
    Procurement committee scoped to a ServiceUnit.

    ACCESS / OWNERSHIP
    ------------------
    Managed by:
    - admins for all service units
    - managers / deputies for their own service unit

    IMPORTANT
    ---------
    Membership validation cannot be enforced purely by foreign keys.
    Routes/services must still ensure that selected committee members belong to
    the correct organizational scope.
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

    service_unit = db.relationship(
        "ServiceUnit",
        backref=db.backref("committees", lazy=True),
    )

    president = db.relationship("Personnel", foreign_keys=[president_personnel_id])
    member1 = db.relationship("Personnel", foreign_keys=[member1_personnel_id])
    member2 = db.relationship("Personnel", foreign_keys=[member2_personnel_id])

    __table_args__ = (
        db.UniqueConstraint(
            "service_unit_id",
            "description",
            name="uq_committee_serviceunit_desc",
        ),
    )

    @property
    def display_name(self) -> str:
        """
        Preferred human-readable committee label.
        """
        return (self.description or "").strip()

    def members_display(self) -> str:
        """
        Return a one-line committee summary for UI use.
        """
        parts = []

        if self.president:
            parts.append(f"Πρόεδρος: {self.president.full_name()}")

        if self.member1:
            parts.append(f"Α' Μέλος: {self.member1.full_name()}")

        if self.member2:
            parts.append(f"Β' Μέλος: {self.member2.full_name()}")

        return " | ".join(parts) if parts else "—"

    def __repr__(self) -> str:
        return f"<ProcurementCommittee {self.id}: {self.display_name}>"


class Procurement(db.Model):
    """
    Main procurement aggregate.

    RESPONSIBILITIES
    ----------------
    Stores:
    - workflow metadata
    - owning service unit
    - selected tax / withholding / committee references
    - supplier participation links
    - material/service lines
    - invitation / award / contract / invoice / protocol fields

    CALCULATION BOUNDARY
    --------------------
    This model delegates heavy financial logic to:
        app.services.procurement_calculations.ProcurementCalculationService

    That keeps the model light and avoids embedding large business-calculation
    rules directly in the ORM layer.
    """

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

    # Legacy text field retained for compatibility with older records / flows.
    handler = db.Column(db.String(255), index=True)

    handler_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    handler_personnel = db.relationship("Personnel", foreign_keys=[handler_personnel_id])

    income_tax_rule_id = db.Column(
        db.Integer,
        db.ForeignKey("income_tax_rules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    income_tax_rule = db.relationship("IncomeTaxRule", foreign_keys=[income_tax_rule_id])

    withholding_profile_id = db.Column(
        db.Integer,
        db.ForeignKey("withholding_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    withholding_profile = db.relationship(
        "WithholdingProfile",
        foreign_keys=[withholding_profile_id],
    )

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

    hop_commitment = db.Column(db.String(50), nullable=True, index=True)
    hop_forward1_commitment = db.Column(db.String(50), nullable=True, index=True)
    hop_forward2_commitment = db.Column(db.String(50), nullable=True, index=True)
    hop_approval_commitment = db.Column(db.String(50), nullable=True, index=True)
    hop_preapproval = db.Column(db.String(50), nullable=True, index=True)
    hop_forward1_preapproval = db.Column(db.String(50), nullable=True, index=True)
    hop_forward2_preapproval = db.Column(db.String(50), nullable=True, index=True)
    hop_approval = db.Column(db.String(50), nullable=True, index=True)

    aay = db.Column(db.String(50), nullable=True, index=True)

    adam_aay = db.Column(db.String(100), nullable=True, index=True)
    ada_aay = db.Column(db.String(100), nullable=True, index=True)

    # Invitation document fields
    identity_prosklisis = db.Column(db.String(255), nullable=True)
    adam_prosklisis = db.Column(db.String(100), nullable=True, index=True)

    # Award decision fields
    identity_apofasis_anathesis = db.Column(db.String(255), nullable=True)
    adam_apofasis_anathesis = db.Column(db.String(100), nullable=True, index=True)

    contract_number = db.Column(db.String(100), nullable=True, index=True)
    adam_contract = db.Column(db.String(100), nullable=True, index=True)

    # Invoice / receipt fields
    invoice_number = db.Column(db.String(100), nullable=True, index=True)
    invoice_date = db.Column(db.Date, nullable=True, index=True)
    materials_receipt_date = db.Column(db.Date, nullable=True, index=True)
    invoice_receipt_date = db.Column(db.Date, nullable=True, index=True)

    protocol_number = db.Column(db.String(100), nullable=True, index=True)

    procurement_notes = db.Column(db.Text, nullable=True)

    send_to_expenses = db.Column(db.Boolean, default=False, nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

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
    def display_name(self) -> str:
        """
        Preferred human-readable procurement label.
        """
        serial_no = (self.serial_no or "").strip()
        description = (self.description or "").strip()

        if serial_no and description:
            return f"{serial_no} - {description}"
        return serial_no or description or f"Procurement #{self.id}"

    @property
    def winner_link(self) -> ProcurementSupplier | None:
        """
        Return the winner association row, if any.
        """
        for link in self.supplies_links or []:
            if link.is_winner:
                return link
        return None

    @property
    def winner_supplier_display(self) -> str | None:
        """
        Legacy display helper: 'AFM - Name' for the winning supplier.
        """
        winner_link = self.winner_link
        if not winner_link or not winner_link.supplier:
            return None

        supplier = winner_link.supplier
        return f"{supplier.afm} - {supplier.name}"

    @property
    def winner_supplier_afm(self) -> str | None:
        """
        Return the winning supplier AFM, if any.
        """
        winner_link = self.winner_link
        if winner_link and winner_link.supplier:
            return winner_link.supplier.afm
        return None

    @property
    def winner_supplier_name(self) -> str | None:
        """
        Return the winning supplier name, if any.
        """
        winner_link = self.winner_link
        if winner_link and winner_link.supplier:
            return winner_link.supplier.name
        return None

    def winner_supplier_obj(self) -> Supplier | None:
        """
        Return the Supplier entity for the winning supplier, if any.
        """
        winner_link = self.winner_link
        if winner_link and winner_link.supplier:
            return winner_link.supplier
        return None

    @property
    def handler_display(self) -> str | None:
        """
        Display the handler name using linked Personnel first, then legacy text.
        """
        if self.handler_personnel:
            return self.handler_personnel.full_name()
        return self.handler or None

    @property
    def aa2_description(self) -> str | None:
        """
        Backward-compatible accessor for procurement type description.
        """
        if self.income_tax_rule and self.income_tax_rule.description:
            return self.income_tax_rule.description
        return None

    @property
    def requested_amount_money(self) -> Decimal:
        """
        Requested amount rounded to standard money precision.
        """
        return _money(_to_decimal(self.requested_amount))

    @property
    def approved_amount_money(self) -> Decimal:
        """
        Approved amount rounded to standard money precision.
        """
        return _money(_to_decimal(self.approved_amount))

    @property
    def sum_total_money(self) -> Decimal:
        """
        Stored pre-VAT total rounded to standard money precision.
        """
        return _money(_to_decimal(self.sum_total))

    @property
    def vat_amount_money(self) -> Decimal:
        """
        Stored VAT amount rounded to standard money precision.
        """
        return _money(_to_decimal(self.vat_amount))

    @property
    def grand_total_money(self) -> Decimal:
        """
        Stored grand total rounded to standard money precision.
        """
        return _money(_to_decimal(self.grand_total))

    @property
    def materials_total_pre_vat(self) -> Decimal:
        """
        Sum line totals from material/service lines.

        NOTE
        ----
        This is a lightweight convenience property for display/comparison.
        Canonical recalculation logic still belongs to the calculation service.
        """
        total = Decimal("0.00")
        for line in self.materials or []:
            total += _to_decimal(line.total_pre_vat)
        return _money(total)

    def recalc_totals(self) -> None:
        """
        Recalculate sum_total, vat_amount, and grand_total.

        IMPLEMENTATION NOTE
        -------------------
        Delegates to the procurement calculation service so the model does not
        own heavy numeric logic directly.
        """
        from ..services.procurement_calculations import ProcurementCalculationService

        ProcurementCalculationService.recalc_totals(self)

    def compute_public_withholdings(self) -> dict:
        """
        Compute public withholding breakdown using the selected profile.
        """
        from ..services.procurement_calculations import ProcurementCalculationService

        return ProcurementCalculationService.compute_public_withholdings(self)

    def compute_income_tax(self) -> dict:
        """
        Compute income tax based on current procurement state.
        """
        from ..services.procurement_calculations import ProcurementCalculationService

        return ProcurementCalculationService.compute_income_tax(self)

    def compute_payment_analysis(self) -> dict:
        """
        Compute full payment analysis for UI and reports.
        """
        from ..services.procurement_calculations import ProcurementCalculationService

        return ProcurementCalculationService.compute_payment_analysis(self)

    def __repr__(self) -> str:
        return f"<Procurement {self.id}: {self.display_name}>"


class ProcurementSupplier(db.Model):
    """
    Association object between Procurement and Supplier.

    PURPOSE
    -------
    Represents supplier participation in a procurement and stores
    procurement-specific metadata such as:
    - offered amount
    - result
    - winner flag
    - notes
    """

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

    supplier = db.relationship(
        "Supplier",
        backref=db.backref("procurement_links", lazy=True),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "procurement_id",
            "supplier_id",
            name="uq_procurement_supplier",
        ),
    )

    @property
    def offered_amount_money(self) -> Decimal:
        """
        Offered amount rounded to standard money precision.
        """
        return _money(_to_decimal(self.offered_amount))

    @property
    def display_name(self) -> str:
        """
        Human-readable participant label.
        """
        if self.supplier:
            return getattr(self.supplier, "display_label", None) or self.supplier.name
        return f"SupplierLink #{self.id}"

    def __repr__(self) -> str:
        supplier_part = self.supplier.afm if self.supplier else self.supplier_id
        return f"<ProcurementSupplier procurement={self.procurement_id} supplier={supplier_part}>"


class MaterialLine(db.Model):
    """
    Material or service line under a procurement.

    PURPOSE
    -------
    This is the primary line-level source used to calculate pre-VAT procurement
    totals.

    IMPORTANT
    ---------
    Line-level totals are lightweight and local enough to remain on the model.
    Aggregate procurement totals still belong to the calculation service.
    """

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
    def total_pre_vat(self) -> Decimal:
        """
        Compute line total before VAT.

        RETURNS
        -------
        Decimal
            quantity * unit_price, rounded to 2 decimal places.
        """
        quantity = _to_decimal(self.quantity)
        unit_price = _to_decimal(self.unit_price)

        if quantity == Decimal("0.00") or unit_price == Decimal("0.00"):
            return Decimal("0.00")

        return (quantity * unit_price).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    @property
    def display_name(self) -> str:
        """
        Preferred human-readable line description.
        """
        return (self.description or "").strip()

    def __repr__(self) -> str:
        return f"<MaterialLine {self.id}: line_no={self.line_no}>"

