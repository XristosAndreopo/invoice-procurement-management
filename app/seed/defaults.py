"""
app/seed_defaults.py

Canonical default reference-data values for initial application seeding.

PURPOSE
-------
This module contains only the static default values used by the seed process.

WHY THIS FILE EXISTS
--------------------
Previously, `app/seed.py` mixed:
- constant default data
- database seeding logic
- execution entrypoints

Those are related, but they are not the same responsibility.

This module isolates the canonical defaults so that:
- seed data is easy to inspect and review
- business defaults can be updated without scanning DB logic
- seeding behavior can evolve independently from the data itself

IMPORTANT
---------
This file contains no database access and no Flask-specific behavior.
It is intentionally pure data.

SEED DATA INCLUDED
------------------
- Generic dropdown categories / values
- Income tax rule defaults
- Withholding profile defaults

SEED DATA EXCLUDED
------------------
This file intentionally does NOT define defaults for:
- Personnel
- Suppliers
- Users

Those are first-class business entities, not generic reference-data rows.
"""

from __future__ import annotations

from decimal import Decimal

# -------------------------------------------------------------------
# Generic option categories / values
# -------------------------------------------------------------------
# Tuple format:
#   (category_key, category_label, [option_value_1, option_value_2, ...])
DEFAULT_OPTION_CATEGORIES = [
    (
        "KATASTASH",
        "Κατάσταση",
        [
            "-",
            "ΣΕ ΕΞΕΛΙΞΗ",
            "ΟΛΟΚΛΗΡΩΘΗΚΕ",
            "ΑΚΥΡΩΘΗΚΕ",
        ],
    ),
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
        [
            "-",
            "Α' ΤΡΙΜΗΝΙΑΙΑ",
            "Β' ΤΡΙΜΗΝΙΑΙΑ",
            "Γ' ΤΡΙΜΗΝΙΑΙΑ",
            "Δ' ΤΡΙΜΗΝΙΑΙΑ",
        ],
    ),
    (
        "FPA",
        "ΦΠΑ",
        ["0", "6", "13", "24"],
    ),

    # ---------------------------------------------------------------
    # Legacy compatibility categories
    # ---------------------------------------------------------------
    # These are intentionally kept because older screens / flows may still
    # expect these categories to exist even if richer models now back the
    # real domain behavior.
    (
        "KRATHSEIS",
        "Κρατήσεις (Λίστα)",
        ["-"],
    ),
    (
        "EPITROPES",
        "Επιτροπές (Λίστα)",
        ["-"],
    ),
]


# -------------------------------------------------------------------
# Income tax rules
# -------------------------------------------------------------------
# Tuple format:
#   (description, rate_percent, threshold_amount)
DEFAULT_INCOME_TAX_RULES = [
    ("ΥΠΗΡΕΣΙΕΣ ΧΩΡΙΣ ΦΕ", Decimal("0.00"), Decimal("150.00")),
    ("ΥΠΗΡΕΣΙΕΣ ΜΕ ΦΕ", Decimal("8.00"), Decimal("150.00")),
    ("ΠΡΟΜΗΘΕΙΑ ΥΛΙΚΩΝ ΧΩΡΙΣ ΦΕ", Decimal("0.00"), Decimal("150.00")),
    ("ΠΡΟΜΗΘΕΙΑ ΥΛΙΚΩΝ ΜΕ ΦΕ", Decimal("4.00"), Decimal("150.00")),
]


# -------------------------------------------------------------------
# Withholding profiles
# -------------------------------------------------------------------
# Tuple format:
#   (description, mt_eloa_percent, eadhsy_percent, withholding1_percent, withholding2_percent)
DEFAULT_WITHHOLDING_PROFILES = [
    ("ΔΑΠΑΝΕΣ <= 1000 (ΙΔΙΩΤΗΣ)", Decimal("6.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
    ("ΔΑΠΑΝΕΣ > 1000 (ΙΔΙΩΤΗΣ)", Decimal("6.00"), Decimal("0.10"), Decimal("0.00"), Decimal("0.00")),
    ("ΔΑΠΑΝΕΣ <= 1000 (ΣΤ. ΠΡΑΤΗΡΙΟ)", Decimal("6.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
    ("ΔΑΠΑΝΕΣ > 1000 (ΣΤ. ΠΡΑΤΗΡΙΟ)", Decimal("6.00"), Decimal("0.10"), Decimal("0.00"), Decimal("0.00")),
    ("ΔΑΠΑΝΕΣ <= 1000 (ΔΗΜΟΣΙΟΣ ΦΟΡΕΑΣ)", Decimal("4.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
    ("ΔΑΠΑΝΕΣ > 1000 (ΔΗΜΟΣΙΟΣ ΦΟΡΕΑΣ)", Decimal("4.00"), Decimal("0.10"), Decimal("0.00"), Decimal("0.00")),
]