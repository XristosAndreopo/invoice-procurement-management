"""
Utility functions shared across the app. This includes:
- get_active_options: Fetch active options for dropdowns based on category key.
- procurement_row_class: Determine CSS class for procurement rows based on status and stage.
"""

from .models import OptionCategory, OptionValue


def get_active_options(category_key: str):
    """
    Return a list of active option strings for a given category key.

    This will be used later in forms to populate dropdowns.
    """
    category = OptionCategory.query.filter_by(key=category_key).first()
    if not category:
        return []

    values = (
        OptionValue.query
        .filter_by(category_id=category.id, is_active=True)
        .order_by(OptionValue.sort_order.asc(), OptionValue.value.asc())
        .all()
    )
    return [v.value for v in values]


def procurement_row_class(proc):
    """
    Compute CSS class for a procurement row based on your priority rules:

    Priority:
    1) Ακυρωμένη (status) -> red
    2) Πέρας (status) -> green-yellow
    3) Αποστολή Δαπάνης (stage) -> orange
    4) Έγκριση (stage) -> light yellow
    """
    status = (proc.status or "").strip()
    stage = (proc.stage or "").strip()

    if status == "Ακυρωμένη":
        return "row-cancelled"
    if status == "Πέρας":
        return "row-complete"
    if stage == "Αποστολή Δαπάνης":
        return "row-expense"
    if stage == "Έγκριση":
        return "row-approval"

    return ""