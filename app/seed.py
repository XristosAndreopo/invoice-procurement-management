"""
Seed default dropdown categories and values.

This runs automatically at app startup (inside app context)
and is safe to run multiple times (idempotent).
"""

from .extensions import db
from .models import OptionCategory, OptionValue

# Default values based on your requirements
DEFAULT_CATEGORIES = [
    ("KATASTASH", "ΚΑΤΑΣΤΑΣΗ", ["-", "Εν Εξελίξη", "Ακυρωμένη", "Πέρας"]),
    ("STADIO", "Στάδιο", [
        "-", "Δέσμευση", "Πρόσκληση", "Προέγκριση", "Έγκριση",
        "Απόφαση Ανάθεσης", "Σύμβαση", "Τιμολόγιο", "Αποστολή Δαπάνης"
    ]),
    ("KATANOMH", "ΚΑΤΑΝΟΜΗ", [
        "-", "Παγία", "Κατ' εξαίρεση", "Γραφική Ύλη", "Μικρογραφικά",
        "Ειδικές Διαχειρίσεις", "Καθαριότητα", "Λοιπές Προεγκρίσεις"
    ]),
    ("TRIMHNIAIA", "ΤΡΙΜΗΝΙΑΙΑ", [
        "-", "Α' ΤΡΙΜΗΝΙΑΙΑ", "Β' ΤΡΙΜΗΝΙΑΙΑ", "Γ' ΤΡΙΜΗΝΙΑΙΑ", "Δ' ΤΡΙΜΗΝΙΑΙΑ"
    ]),
    ("XEIRISTES", "ΧΕΙΡΙΣΤΗΣ", ["-"]),
    ("PROMHTHEFTES", "ΠΡΟΜΗΘΕΥΤΕΣ", ["-"]),
]


def seed_default_options():
    """
    Create default OptionCategory and OptionValue rows if they don't exist.

    This function is safe to call many times.
    """
    for key, label, values in DEFAULT_CATEGORIES:
        category = OptionCategory.query.filter_by(key=key).first()
        if not category:
            category = OptionCategory(key=key, label=label)
            db.session.add(category)
            db.session.flush()  # ensures category.id is available

        for idx, val in enumerate(values):
            exists = OptionValue.query.filter_by(
                category_id=category.id,
                value=val
            ).first()

            if not exists:
                db.session.add(OptionValue(
                    category_id=category.id,
                    value=val,
                    sort_order=idx,
                    is_active=True,
                ))

    db.session.commit()