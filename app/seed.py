"""
app/seed.py

Seed default dropdown categories and values.

Enterprise rules:
- This function is safe to run multiple times (idempotent).
- We seed ONLY canonical categories that the app actually uses.
- Handler/Suppliers are NOT seeded here because they are first-class entities
  (Personnel, Supplier) and not generic OptionValues.

Canonical keys (must match routes and procurement module):
- KATASTASH   (Κατάσταση)
- STADIO      (Στάδιο)
- KATANOMH    (Κατανομή)
- TRIMHNIAIA  (Τριμηνιαία)
- FPA         (ΦΠΑ)
- KRATHSEIS   (Κρατήσεις)
- EPITROPES   (Επιτροπές Προμηθειών)
"""

from __future__ import annotations

from .extensions import db
from .models import OptionCategory, OptionValue


# Default values based on current V2 requirements.
# NOTE: values are examples; adjust freely.
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
    # VAT rates stored as OptionValues for dropdown convenience.
    # Your Procurement model uses vat_rate as Decimal, so you can store numeric strings here.
    ("FPA", "ΦΠΑ", ["0", "6", "13", "24"]),
    # Withholdings can be labels or percentages depending on your workflow.
    # Keep simple labels for now; you can expand later.
    ("KRATHSEIS", "Κρατήσεις", ["-", "0%", "4%", "8%", "14%"]),
    # Committees list (manager/admin will manage this list).
    ("EPITROPES", "Επιτροπές Προμηθειών", ["-"]),
]


def seed_default_options() -> None:
    """
    Create default OptionCategory and OptionValue rows if they don't exist.

    Idempotent behavior:
    - If category exists, we don't recreate it.
    - If a value exists under category, we don't recreate it.
    - sort_order is set on first creation only.
    """
    for key, label, values in DEFAULT_CATEGORIES:
        category = OptionCategory.query.filter_by(key=key).first()
        if not category:
            category = OptionCategory(key=key, label=label)
            db.session.add(category)
            db.session.flush()  # ensure category.id is available for OptionValue inserts
        else:
            # Optional: keep label synced if you rename labels later
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

    db.session.commit()