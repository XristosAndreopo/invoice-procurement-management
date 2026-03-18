"""
app/models/organization.py

Organizational structure models.
"""

from __future__ import annotations

from datetime import datetime

from ..extensions import db


class Personnel(db.Model):
    """
    Organizational directory person (admin-managed).
    """

    __tablename__ = "personnel"

    id = db.Column(db.Integer, primary_key=True)

    agm = db.Column(db.String(50), nullable=False, unique=True, index=True)
    aem = db.Column(db.String(50), nullable=True, index=True)

    rank = db.Column(db.String(100), nullable=True)
    specialty = db.Column(db.String(150), nullable=True)

    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

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

    def full_name(self) -> str:
        parts = []
        if self.rank:
            parts.append(str(self.rank).strip())
        if self.last_name:
            parts.append(str(self.last_name).strip())
        if self.first_name:
            parts.append(str(self.first_name).strip())
        return " ".join([p for p in parts if p]).strip()

    def _name_core(self) -> str:
        parts = []
        if self.rank:
            parts.append(str(self.rank).strip())
        if self.specialty:
            parts.append(str(self.specialty).strip())
        if self.first_name:
            parts.append(str(self.first_name).strip())
        if self.last_name:
            parts.append(str(self.last_name).strip())
        return " ".join([p for p in parts if p]).strip()

    @property
    def display_name(self) -> str:
        return self.display_selected_label()

    def display_selected_label(self) -> str:
        return self._name_core() or self.full_name()

    def display_option_label(self) -> str:
        base = self._name_core() or self.full_name()

        extra_parts = []
        if self.aem:
            extra_parts.append(f"ΑΕΜ {str(self.aem).strip()}")
        if self.agm:
            extra_parts.append(f"ΑΓΜ {str(self.agm).strip()}")

        extra = " ... ".join(extra_parts).strip()
        return f"{base} ({extra})" if extra else base

    def __repr__(self) -> str:
        return f"<Personnel {self.id}: {self.display_selected_label() or self.agm}>"


class ServiceUnit(db.Model):
    """
    Organizational service / unit.
    """

    __tablename__ = "service_units"

    id = db.Column(db.Integer, primary_key=True)

    code = db.Column(db.String(50))
    description = db.Column(db.String(255), nullable=False)
    short_name = db.Column(db.String(100))

    aahit = db.Column(db.String(100))
    commander = db.Column(db.String(255))
    curator = db.Column(db.String(255))
    supply_officer = db.Column(db.String(255))

    address = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(50), nullable=True)

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

    manager = db.relationship(
        "Personnel",
        foreign_keys=[manager_personnel_id],
        backref="managed_units",
    )
    deputy = db.relationship(
        "Personnel",
        foreign_keys=[deputy_personnel_id],
        backref="deputy_units",
    )

    users = db.relationship("User", back_populates="service_unit", lazy=True)

    procurements = db.relationship(
        "Procurement",
        back_populates="service_unit",
        cascade="all, delete-orphan",
    )

    directories = db.relationship(
        "Directory",
        back_populates="service_unit",
        cascade="all, delete-orphan",
        lazy=True,
    )

    departments = db.relationship(
        "Department",
        back_populates="service_unit",
        cascade="all, delete-orphan",
        lazy=True,
    )

    @property
    def display_name(self) -> str:
        return (self.short_name or self.description or "").strip()

    def __repr__(self) -> str:
        return f"<ServiceUnit {self.id}: {self.display_name}>"


class Directory(db.Model):
    """
    Directory / Διεύθυνση under a ServiceUnit.
    """

    __tablename__ = "directories"

    id = db.Column(db.Integer, primary_key=True)

    service_unit_id = db.Column(
        db.Integer,
        db.ForeignKey("service_units.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = db.Column(db.String(255), nullable=False, index=True)

    director_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    service_unit = db.relationship("ServiceUnit", back_populates="directories")
    director = db.relationship("Personnel", foreign_keys=[director_personnel_id])

    departments = db.relationship(
        "Department",
        back_populates="directory",
        cascade="all, delete-orphan",
        lazy=True,
    )

    __table_args__ = (
        db.UniqueConstraint("service_unit_id", "name", name="uq_directory_serviceunit_name"),
    )

    @property
    def display_name(self) -> str:
        return (self.name or "").strip()

    def __repr__(self) -> str:
        return f"<Directory {self.id}: {self.display_name}>"


class Department(db.Model):
    """
    Department / Τμήμα under a Directory.
    """

    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)

    service_unit_id = db.Column(
        db.Integer,
        db.ForeignKey("service_units.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    directory_id = db.Column(
        db.Integer,
        db.ForeignKey("directories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = db.Column(db.String(255), nullable=False, index=True)

    head_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    assistant_personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    directory = db.relationship("Directory", back_populates="departments")
    service_unit = db.relationship("ServiceUnit", back_populates="departments")

    head = db.relationship("Personnel", foreign_keys=[head_personnel_id])
    assistant = db.relationship("Personnel", foreign_keys=[assistant_personnel_id])

    assignments = db.relationship(
        "PersonnelDepartmentAssignment",
        back_populates="department",
        cascade="all, delete-orphan",
        lazy=True,
    )

    __table_args__ = (
        db.UniqueConstraint("directory_id", "name", name="uq_department_directory_name"),
    )

    @property
    def display_name(self) -> str:
        return (self.name or "").strip()

    def __repr__(self) -> str:
        return f"<Department {self.id}: {self.display_name}>"


class PersonnelDepartmentAssignment(db.Model):
    """
    Membership/assignment of a person to a department.

    PURPOSE
    -------
    A person may belong to multiple departments and, by extension,
    multiple directories within the same service unit.

    UI / REPORTING ROLE
    -------------------
    This model is also the canonical procurement-handler selection unit.

    That means one assignment row represents:
    - one specific person
    - one specific department
    - one specific directory

    The procurement UI stores the selected assignment id so downstream reports
    can render the exact organizational context used for that procurement.
    """

    __tablename__ = "personnel_department_assignments"

    id = db.Column(db.Integer, primary_key=True)

    personnel_id = db.Column(
        db.Integer,
        db.ForeignKey("personnel.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    service_unit_id = db.Column(
        db.Integer,
        db.ForeignKey("service_units.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    directory_id = db.Column(
        db.Integer,
        db.ForeignKey("directories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    is_primary = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    personnel = db.relationship(
        "Personnel",
        backref=db.backref(
            "department_assignments",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    service_unit = db.relationship("ServiceUnit")
    directory = db.relationship("Directory")
    department = db.relationship("Department", back_populates="assignments")

    __table_args__ = (
        db.UniqueConstraint(
            "personnel_id",
            "department_id",
            name="uq_personnel_department_assignment",
        ),
    )

    def _person_label(self) -> str:
        """
        Return the most useful person-centric label available.

        Falls back safely if the linked Personnel row is missing.
        """
        if not self.personnel:
            return "—"

        display_selected = getattr(self.personnel, "display_selected_label", None)
        if callable(display_selected):
            value = display_selected()
            if value:
                return value

        display_name = getattr(self.personnel, "display_name", None)
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()

        full_name = getattr(self.personnel, "full_name", None)
        if callable(full_name):
            value = full_name()
            if value:
                return value

        return "—"

    def display_selected_label(self) -> str:
        """
        Label used after selection in procurement handler dropdowns.

        FORMAT
        ------
        PERSON / ΤΜΗΜΑ
        """
        person_label = self._person_label()
        department_name = (self.department.name or "").strip() if self.department else ""
        if department_name:
            return f"{person_label} / {department_name}"
        return person_label

    def display_option_label(self) -> str:
        """
        Full searchable label used inside procurement handler dropdown options.

        FORMAT
        ------
        PERSON / ΤΜΗΜΑ / ΔΙΕΥΘΥΝΣΗ
        """
        person_label = self._person_label()
        department_name = (self.department.name or "").strip() if self.department else ""
        directory_name = (self.directory.name or "").strip() if self.directory else ""

        parts = [person_label]
        if department_name:
            parts.append(department_name)
        if directory_name:
            parts.append(directory_name)

        return " / ".join([p for p in parts if p]).strip()

    @property
    def display_name(self) -> str:
        return self.display_option_label()

    def __repr__(self) -> str:
        return f"<PersonnelDepartmentAssignment {self.id}: personnel={self.personnel_id} dept={self.department_id}>"