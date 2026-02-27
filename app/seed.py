"""
app/seed.py

Seed default dropdown categories and values.

Enterprise rules:
- Safe to run multiple times (idempotent).
- Seeds canonical OptionCategory keys used by procurements/settings.
- Seeds enterprise master-data:
  - IncomeTaxRule (Φόρος Εισοδήματος)
  - WithholdingProfile (Κρατήσεις - Πίνακας)

NOTE:
- Personnel and Suppliers are not seeded here because they are first-class entities.
"""

from __future__ import annotations

from decimal import Decimal

from .extensions import db
from .models import OptionCategory, OptionValue, IncomeTaxRule, WithholdingProfile


DEFAULT_CATEGORIES = [
    ("KATASTASH", "Κατάσταση", ["-", "Εν Εξελίξει", "Ακυρωμένη", "Πέρας"]),
    (
        "STADIO",
        "Στάδιο",
        [
            "-",
            "Δέσμευση",
            "Πρόσκληση",
            "Προέγκριση",
            "Έγκριση",
            "Απόφαση Ανάθεσης",
            "Σύμβαση",
            "Τιμολόγιο",
            "Αποστολή Δαπάνης",
        ],
    ),
    (
        "KATANOMH",
        "Κατανομή",
        [
            "-",
            "Παγία",
            "Κατ' εξαίρεση",
            "Γραφική Ύλη",
            "Μικρογραφικά",
            "Ειδικές Διαχειρίσεις",
            "Καθαριότητα",
            "Λοιπές Προεγκρίσεις",
        ],
    ),
    (
        "TRIMHNIAIA",
        "Τριμηνιαία",
        ["-", "Α' ΤΡΙΜΗΝΙΑΙΑ", "Β' ΤΡΙΜΗΝΙΑΙΑ", "Γ' ΤΡΙΜΗΝΙΑΙΑ", "Δ' ΤΡΙΜΗΝΙΑΙΑ"],
    ),
    ("FPA", "ΦΠΑ", ["0", "6", "13", "24"]),
    # kept for legacy compatibility (some screens may still use option-values list)
    ("KRATHSEIS", "Κρατήσεις (Λίστα)", ["-"]),
    ("EPITROPES", "Επιτροπές (Λίστα)", ["-"]),
]


DEFAULT_INCOME_TAX_RULES = [
    # description, rate_percent, threshold_amount
    ("ΥΠΗΡΕΣΙΕΣ ΧΩΡΙΣ ΦΕ", Decimal("0.00"), Decimal("150.00")),
    ("ΥΠΗΡΕΣΙΕΣ ΜΕ ΦΕ", Decimal("8.00"), Decimal("150.00")),
    ("ΠΡΟΜΗΘΕΙΑ ΥΛΙΚΩΝ ΧΩΡΙΣ ΦΕ", Decimal("0.00"), Decimal("150.00")),
    ("ΠΡΟΜΗΘΕΙΑ ΥΛΙΚΩΝ ΜΕ ΦΕ", Decimal("4.00"), Decimal("150.00")),
]


DEFAULT_WITHHOLDING_PROFILES = [
    # description, mt_eloa, eadhsy, k1, k2
    ("ΔΑΠΑΝΕΣ <= 1000 (ΙΔΙΩΤΗΣ)", Decimal("6.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
    ("ΔΑΠΑΝΕΣ > 1000 (ΙΔΙΩΤΗΣ)", Decimal("6.00"), Decimal("0.10"), Decimal("0.00"), Decimal("0.00")),
    ("ΔΑΠΑΝΕΣ <= 1000 (ΣΤ. ΠΡΑΤΗΡΙΟ)", Decimal("6.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
    ("ΔΑΠΑΝΕΣ > 1000 (ΣΤ. ΠΡΑΤΗΡΙΟ)", Decimal("6.00"), Decimal("0.10"), Decimal("0.00"), Decimal("0.00")),
    ("ΔΑΠΑΝΕΣ <= 1000 (ΕΙΔΙΚΕΣ ΔΙΑΧΕΙΡΙΣΕΙΣ)", Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
    ("ΔΑΠΑΝΕΣ > 1000 (ΕΙΔΙΚΕΣ ΔΙΑΧΕΙΡΙΣΕΙΣ)", Decimal("0.00"), Decimal("0.10"), Decimal("0.00"), Decimal("0.00")),
]


def seed_default_options() -> None:
    """
    Create default OptionCategory and OptionValue rows if they don't exist.
    Also seeds IncomeTaxRule and WithholdingProfile defaults.

    Idempotent behavior:
    - If category exists, we don't recreate it.
    - If a value exists under category, we don't recreate it.
    - For IncomeTaxRule / WithholdingProfile: match by description.
    """
    # Seed OptionCategory/OptionValue
    for key, label, values in DEFAULT_CATEGORIES:
        category = OptionCategory.query.filter_by(key=key).first()
        if not category:
            category = OptionCategory(key=key, label=label)
            db.session.add(category)
            db.session.flush()
        else:
            if category.label != label:
                category.label = label
                db.session.flush()

        for idx, val in enumerate(values):
            exists = OptionValue.query.filter_by(category_id=category.id, value=val).first()
            if exists:
                continue
            db.session.add(
                OptionValue(
                    category_id=category.id,
                    value=val,
                    sort_order=idx,
                    is_active=True,
                )
            )

    db.session.flush()

    # Seed IncomeTaxRule
    for desc, rate, threshold in DEFAULT_INCOME_TAX_RULES:
        exists = IncomeTaxRule.query.filter_by(description=desc).first()
        if exists:
            # keep core values in sync
            exists.rate_percent = rate
            exists.threshold_amount = threshold
            if exists.is_active is None:
                exists.is_active = True
            continue

        db.session.add(
            IncomeTaxRule(
                description=desc,
                rate_percent=rate,
                threshold_amount=threshold,
                is_active=True,
            )
        )

    db.session.flush()

    # Seed WithholdingProfile
    for desc, mt, ea, k1, k2 in DEFAULT_WITHHOLDING_PROFILES:
        exists = WithholdingProfile.query.filter_by(description=desc).first()
        if exists:
            exists.mt_eloa_percent = mt
            exists.eadhsy_percent = ea
            exists.withholding1_percent = k1
            exists.withholding2_percent = k2
            if exists.is_active is None:
                exists.is_active = True
            continue

        db.session.add(
            WithholdingProfile(
                description=desc,
                mt_eloa_percent=mt,
                eadhsy_percent=ea,
                withholding1_percent=k1,
                withholding2_percent=k2,
                is_active=True,
            )
        )

    db.session.commit()