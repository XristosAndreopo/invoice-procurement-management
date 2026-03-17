"""
app/models/supplier.py

Supplier master-data model.

PURPOSE
-------
This module defines the Supplier master-data entity used throughout the
procurement workflow.

WHY THIS FILE EXISTS
--------------------
Suppliers are reference/master records used by procurements, but they deserve
their own dedicated module because:

- they are a distinct business entity
- they typically have their own admin CRUD screens
- they are reused across many procurement records
- they contain business-facing contact and payment metadata

ARCHITECTURAL BOUNDARY
----------------------
This module defines:
- persistence schema
- lightweight display helpers
- supplier identity / contact / payment fields

This module must NOT become the place for:
- AFM validation workflows
- duplicate-detection orchestration
- procurement participation logic
- supplier import/export orchestration
- route-level form handling

Those responsibilities belong in:
- app.services.*
- app.routes / blueprints
- import services

IMPORTANT
---------
This is generally admin-managed master data. Server-side validation must still
be enforced by the calling service/route layer, especially for:
- AFM uniqueness
- IBAN normalization/validation
- email normalization
- required-field policies
"""

from __future__ import annotations

from datetime import datetime

from ..extensions import db


class Supplier(db.Model):
    """
    Supplier master data.

    KEY FIELDS
    ----------
    - afm:
        Tax identifier / ΑΦΜ. Intended to be unique per supplier.

    - name:
        Supplier legal or display name.

    - doy:
        Tax office / Δ.Ο.Υ.

    - phone, email:
        Contact details.

    - address, city, postal_code, country:
        Address metadata.

    - bank_name, iban:
        Payment / banking details.

    - emba:
        Reporting or compliance metadata field retained from the existing app.

    DESIGN NOTE
    -----------
    This model intentionally stays simple and schema-focused. It is a reusable
    supplier directory record, not a transactional procurement object.
    """

    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)

    afm = db.Column(db.String(9), nullable=False, unique=True, index=True)
    name = db.Column(db.String(255), nullable=False, index=True)

    # Supplier tax office (Δ.Ο.Υ.)
    doy = db.Column(db.String(255), nullable=True)

    # Contact information
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(255), nullable=True)

    # Reporting / compliance field
    emba = db.Column(db.String(255), nullable=True)

    # Address / location
    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(100), nullable=True)

    # Payment details
    bank_name = db.Column(db.String(120), nullable=True)
    iban = db.Column(db.String(34), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @property
    def display_name(self) -> str:
        """
        Preferred human-readable supplier label.
        """
        return (self.name or "").strip()

    @property
    def display_label(self) -> str:
        """
        Useful compact label for dropdowns or summary views.

        FORMAT
        ------
        "Επωνυμία (ΑΦΜ)"
        """
        name = (self.name or "").strip()
        afm = (self.afm or "").strip()

        if name and afm:
            return f"{name} ({afm})"
        return name or afm

    @property
    def location_label(self) -> str:
        """
        Compact city/country display label for UI/report usage.
        """
        city = (self.city or "").strip()
        country = (self.country or "").strip()

        if city and country:
            return f"{city}, {country}"
        return city or country

    @property
    def has_payment_details(self) -> bool:
        """
        Return True when at least one payment-related field is present.
        """
        return bool(
            (self.bank_name and str(self.bank_name).strip())
            or (self.iban and str(self.iban).strip())
        )

    @property
    def has_contact_details(self) -> bool:
        """
        Return True when at least one contact-related field is present.
        """
        return bool(
            (self.phone and str(self.phone).strip())
            or (self.email and str(self.email).strip())
            or (self.address and str(self.address).strip())
        )

    def __repr__(self) -> str:
        return f"<Supplier {self.afm} - {self.name}>"

