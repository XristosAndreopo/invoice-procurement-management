"""
Invoice Management System – Enterprise Domain Models (V3+)

Enterprise add-ons in this revision:
- Personnel belongs to a ServiceUnit (optional) for handler filtering.
- Procurement.handler_personnel_id (FK) instead of free-text handler.
- Procurement workflow fields (ΗΩΠ*) and send_to_expenses flag.
- ProcurementSupplier.notes for offer observations.

NEW in this revision (per UX request):
- Add preapproval forward fields:
  - hop_forward1_preapproval
  - hop_forward2_preapproval
- Add AAΥ field (aay) under approval.
- Add Procurement notes (procurement_notes) for handler observations.
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import db


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

    # ✅ Personnel assigned to a ServiceUnit (for handler selection)
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

    # ✅ handler as Personnel FK (preferred)
    handler_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    handler_personnel = db.relationship("Personnel", foreign_keys=[handler_personnel_id])

    requested_amount = db.Column(db.Numeric(12, 2))
    approved_amount = db.Column(db.Numeric(12, 2))

    vat_rate = db.Column(db.Numeric(5, 4))
    sum_total = db.Column(db.Numeric(12, 2))
    vat_amount = db.Column(db.Numeric(12, 2))
    grand_total = db.Column(db.Numeric(12, 2))

    # ✅ ΗΩΠ workflow fields (stored as text identifiers)
    hop_commitment = db.Column(db.String(50), nullable=True, index=True)
    hop_forward1_commitment = db.Column(db.String(50), nullable=True, index=True)
    hop_forward2_commitment = db.Column(db.String(50), nullable=True, index=True)

    hop_preapproval = db.Column(db.String(50), nullable=True, index=True)

    # ✅ NEW: preapproval forwards (under hop_preapproval in UI)
    hop_forward1_preapproval = db.Column(db.String(50), nullable=True, index=True)
    hop_forward2_preapproval = db.Column(db.String(50), nullable=True, index=True)

    hop_approval = db.Column(db.String(50), nullable=True, index=True)

    # ✅ NEW: AAΥ (below approval)
    aay = db.Column(db.String(50), nullable=True, index=True)

    # ✅ NEW: procurement notes (handler observations)
    procurement_notes = db.Column(db.Text, nullable=True)

    # ✅ explicit switch to move to Pending Expenses (only valid after approval)
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
        winner_link = None
        for link in self.supplies_links or []:
            if link.is_winner:
                winner_link = link
                break
        if not winner_link or not winner_link.supplier:
            return None
        return f"{winner_link.supplier.afm} - {winner_link.supplier.name}"

    @property
    def handler_display(self):
        """Preferred handler display (Personnel). Falls back to legacy handler string."""
        if self.handler_personnel:
            return self.handler_personnel.full_name()
        return self.handler or None

    def recalc_totals(self):
        total = Decimal("0.00")
        for line in self.materials:
            if line.quantity and line.unit_price:
                total += Decimal(str(line.quantity)) * Decimal(str(line.unit_price))

        self.sum_total = total.quantize(Decimal("0.01"))

        if not self.vat_rate:
            self.vat_amount = Decimal("0.00")
            self.grand_total = self.sum_total
            return

        rate = Decimal(str(self.vat_rate))
        if rate > 1:
            rate = rate / Decimal("100")

        vat = (self.sum_total * rate).quantize(Decimal("0.01"))
        self.vat_amount = vat
        self.grand_total = (self.sum_total + vat).quantize(Decimal("0.01"))


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

    # ✅ large notes/observations for offers
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