"""
app/models/organization.py

Organizational structure models.

CONTAINS
--------
- Personnel
- ServiceUnit
- Directory
- Department

WHY THESE MODELS LIVE TOGETHER
------------------------------
These entities form the organizational hierarchy of the application:

    ServiceUnit -> Directory -> Department
                   ^
                   |
                Personnel assignments / leadership roles

They are highly related conceptually and through foreign keys, so grouping them
in one module improves readability more than splitting each class into its own
file.

ARCHITECTURAL BOUNDARY
----------------------
This module defines:
- organizational persistence schema
- relationships
- lightweight display helpers

This module must NOT become the place for:
- scope validation
- manager/admin authorization rules
- directory/department ownership enforcement
- cross-entity query orchestration

Those responsibilities belong in:
    app/services/organization_service.py

SECURITY NOTE
-------------
Foreign keys alone do NOT enforce all business constraints.

For example:
- a Directory director should belong to the same ServiceUnit
- a Department head should belong to the same ServiceUnit / Directory chain
- a Personnel assignment should be validated server-side

Those rules must continue to be enforced in routes / services.
"""

from __future__ import annotations

from datetime import datetime

from ..extensions import db


class Personnel(db.Model):
    """
    Organizational directory person (admin-managed).

    ORGANIZATIONAL ASSIGNMENT
    -------------------------
    A person may be linked to:
    - conceptually one ServiceUnit
    - optionally one Directory
    - optionally one Department

    IMPORTANT
    ---------
    `service_unit_id` is nullable for historical compatibility, but in business
    terms the person is expected to belong to a service unit.

    UI DISPLAY RULES
    ----------------
    Dropdown option:
        "Βαθμός Ειδικότητα Όνομα Επώνυμο (ΑΕΜ ... ΑΓΜ)"

    Selected value:
        "Βαθμός Ειδικότητα Όνομα Επώνυμο"
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

    directory_id = db.Column(
        db.Integer,
        db.ForeignKey("directories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # 1-to-1 link to system user account
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

    directory = db.relationship("Directory", foreign_keys=[directory_id])
    department = db.relationship("Department", foreign_keys=[department_id])

    def full_name(self) -> str:
        """
        Return a compact legacy display name.

        FORMAT
        ------
        "Βαθμός Επώνυμο Όνομα"

        NOTE
        ----
        This method is preserved for backward compatibility because other parts
        of the application may already depend on this formatting.
        """
        parts = []
        if self.rank:
            parts.append(str(self.rank).strip())
        if self.last_name:
            parts.append(str(self.last_name).strip())
        if self.first_name:
            parts.append(str(self.first_name).strip())
        return " ".join([p for p in parts if p]).strip()

    def _name_core(self) -> str:
        """
        Build the main display label without AEM / AGM metadata.

        RETURNS
        -------
        str
            "Βαθμός Ειδικότητα Όνομα Επώνυμο"
        """
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
        """
        Canonical display name for already-selected UI contexts.

        This is the most useful general-purpose read-only label for templates,
        reports, and dropdown-selected values.
        """
        return self.display_selected_label()

    def display_selected_label(self) -> str:
        """
        Label used when the person is already selected in the UI.
        """
        return self._name_core() or self.full_name()

    def display_option_label(self) -> str:
        """
        Label used in dropdown options.

        Includes identifying metadata to help distinguish people with similar
        names.
        """
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

    This is a top-level organizational entity that can own:
    - personnel
    - users
    - directories
    - departments
    - committees
    - procurements

    LEADERSHIP
    ----------
    Manager and deputy are selected from Personnel, but same-service validation
    must still be enforced server-side.
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

    # Report header / contact fields
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

    @property
    def display_name(self) -> str:
        """
        Preferred human-readable label for UI use.
        """
        return (self.short_name or self.description or "").strip()

    def __repr__(self) -> str:
        return f"<ServiceUnit {self.id}: {self.display_name}>"


class Directory(db.Model):
    """
    Directory / Διεύθυνση under a ServiceUnit.

    ROLE
    ----
    `director_personnel_id` represents:
        "Τμηματάρχης/Διευθυντής"

    SECURITY NOTE
    -------------
    Server-side logic must verify the selected director belongs to the same
    ServiceUnit.
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

    service_unit = db.relationship(
        "ServiceUnit",
        backref=db.backref("directories", lazy=True, cascade="all, delete-orphan"),
    )
    director = db.relationship("Personnel", foreign_keys=[director_personnel_id])

    __table_args__ = (
        db.UniqueConstraint("service_unit_id", "name", name="uq_directory_serviceunit_name"),
    )

    @property
    def display_name(self) -> str:
        """
        Preferred human-readable directory label.
        """
        return (self.name or "").strip()

    def __repr__(self) -> str:
        return f"<Directory {self.id}: {self.display_name}>"


class Department(db.Model):
    """
    Department / Τμήμα under a Directory.

    ROLE FIELDS
    -----------
    - head_personnel_id:
        "Προϊστάμενος/Αξιωματικός"

    - assistant_personnel_id:
        optional helper / future UI support

    SECURITY NOTE
    -------------
    Server-side logic must ensure head / assistant belong to the proper
    ServiceUnit / Directory scope.
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

    directory = db.relationship(
        "Directory",
        backref=db.backref("departments", lazy=True, cascade="all, delete-orphan"),
    )
    service_unit = db.relationship(
        "ServiceUnit",
        backref=db.backref("departments", lazy=True, cascade="all, delete-orphan"),
    )

    head = db.relationship("Personnel", foreign_keys=[head_personnel_id])
    assistant = db.relationship("Personnel", foreign_keys=[assistant_personnel_id])

    __table_args__ = (
        db.UniqueConstraint("directory_id", "name", name="uq_department_directory_name"),
    )

    @property
    def display_name(self) -> str:
        """
        Preferred human-readable department label.
        """
        return (self.name or "").strip()

    def __repr__(self) -> str:
        return f"<Department {self.id}: {self.display_name}>"