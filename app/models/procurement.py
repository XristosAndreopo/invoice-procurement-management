"""
app/models/procurement.py

Procurement workflow models.
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
        return (self.description or "").strip()

    def members_display(self) -> str:
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

    handler = db.Column(db.String(255), index=True)

    handler_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    handler_personnel = db.relationship("Personnel", foreign_keys=[handler_personnel_id])

    handler_assignment_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel_department_assignments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    handler_assignment = db.relationship(
        "PersonnelDepartmentAssignment",
        foreign_keys=[handler_assignment_id],
    )

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

    identity_prosklisis = db.Column(db.String(255), nullable=True)
    adam_prosklisis = db.Column(db.String(100), nullable=True, index=True)

    identity_apofasis_anathesis = db.Column(db.String(255), nullable=True)
    adam_apofasis_anathesis = db.Column(db.String(100), nullable=True, index=True)

    contract_number = db.Column(db.String(100), nullable=True, index=True)
    adam_contract = db.Column(db.String(100), nullable=True, index=True)

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
        serial_no = (self.serial_no or "").strip()
        description = (self.description or "").strip()

        if serial_no and description:
            return f"{serial_no} - {description}"
        return serial_no or description or f"Procurement #{self.id}"

    @property
    def winner_link(self) -> ProcurementSupplier | None:
        for link in self.supplies_links or []:
            if link.is_winner:
                return link
        return None

    @property
    def winner_supplier_display(self) -> str | None:
        winner_link = self.winner_link
        if not winner_link or not winner_link.supplier:
            return None

        supplier = winner_link.supplier
        return f"{supplier.afm} - {supplier.name}"

    @property
    def winner_supplier_afm(self) -> str | None:
        winner_link = self.winner_link
        if winner_link and winner_link.supplier:
            return winner_link.supplier.afm
        return None

    @property
    def winner_supplier_name(self) -> str | None:
        winner_link = self.winner_link
        if winner_link and winner_link.supplier:
            return winner_link.supplier.name
        return None

    def winner_supplier_obj(self) -> Supplier | None:
        winner_link = self.winner_link
        if winner_link and winner_link.supplier:
            return winner_link.supplier
        return None

    @property
    def handler_display(self) -> str | None:
        if self.handler_personnel:
            return self.handler_personnel.full_name()
        return self.handler or None

    @property
    def handler_directory_name(self) -> str | None:
        if self.handler_assignment and self.handler_assignment.directory:
            return self.handler_assignment.directory.name
        return None

    @property
    def handler_department_name(self) -> str | None:
        if self.handler_assignment and self.handler_assignment.department:
            return self.handler_assignment.department.name
        return None

    @property
    def aa2_description(self) -> str | None:
        if self.income_tax_rule and self.income_tax_rule.description:
            return self.income_tax_rule.description
        return None

    @property
    def requested_amount_money(self) -> Decimal:
        return _money(_to_decimal(self.requested_amount))

    @property
    def approved_amount_money(self) -> Decimal:
        return _money(_to_decimal(self.approved_amount))

    @property
    def sum_total_money(self) -> Decimal:
        return _money(_to_decimal(self.sum_total))

    @property
    def vat_amount_money(self) -> Decimal:
        return _money(_to_decimal(self.vat_amount))

    @property
    def grand_total_money(self) -> Decimal:
        return _money(_to_decimal(self.grand_total))

    @property
    def materials_total_pre_vat(self) -> Decimal:
        total = Decimal("0.00")
        for line in self.materials or []:
            total += _to_decimal(line.total_pre_vat)
        return _money(total)

    def recalc_totals(self) -> None:
        from ..services.procurement_calculations import ProcurementCalculationService
        ProcurementCalculationService.recalc_totals(self)

    def compute_public_withholdings(self) -> dict:
        from ..services.procurement_calculations import ProcurementCalculationService
        return ProcurementCalculationService.compute_public_withholdings(self)

    def compute_income_tax(self) -> dict:
        from ..services.procurement_calculations import ProcurementCalculationService
        return ProcurementCalculationService.compute_income_tax(self)

    def compute_payment_analysis(self) -> dict:
        from ..services.procurement_calculations import ProcurementCalculationService
        return ProcurementCalculationService.compute_payment_analysis(self)

    def __repr__(self) -> str:
        return f"<Procurement {self.id}: {self.display_name}>"


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
        return _money(_to_decimal(self.offered_amount))

    @property
    def display_name(self) -> str:
        if self.supplier:
            return getattr(self.supplier, "display_label", None) or self.supplier.name
        return f"SupplierLink #{self.id}"

    def __repr__(self) -> str:
        supplier_part = self.supplier.afm if self.supplier else self.supplier_id
        return f"<ProcurementSupplier procurement={self.procurement_id} supplier={supplier_part}>"


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
    def total_pre_vat(self) -> Decimal:
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
        return (self.description or "").strip()

    def __repr__(self) -> str:
        return f"<MaterialLine {self.id}: line_no={self.line_no}>"