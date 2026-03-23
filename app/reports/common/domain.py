"""
Shared report-domain resolution helpers.

These helpers intentionally centralize repeated report rules such as:
- handler directory/department resolution from handler assignment
- procurement type resolution from material lines
- service-unit place fallback
- monetary total resolution
- supplier formatting lines
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from .amounts import money_plain, to_decimal
from .formatting import safe_text, upper_no_accents


def resolve_is_services(procurement: Any) -> bool:
    """
    Canonical rule:
    if any procurement material line has is_service == True,
    the procurement is treated as services.
    """
    materials = list(getattr(procurement, "materials", []) or [])
    return any(bool(getattr(line, "is_service", False)) for line in materials)


def resolve_proc_type_lower(procurement: Any) -> str:
    """
    Return lower-case procurement type phrase based on procurement materials.
    """
    return "παροχή υπηρεσιών" if resolve_is_services(procurement) else "προμήθεια υλικών"


def resolve_handler_directory(procurement: Any, *, uppercase: bool = False) -> str:
    """
    Resolve handler directory from selected handler assignment first.

    Priority:
    1. procurement.handler_assignment.directory.name
    2. procurement.handler_personnel.directory.name
    """
    assignment = getattr(procurement, "handler_assignment", None)
    if assignment is not None:
        directory = getattr(assignment, "directory", None)
        if directory is not None:
            value = safe_text(getattr(directory, "name", None))
            return upper_no_accents(value) if uppercase else value

    handler = getattr(procurement, "handler_personnel", None)
    directory = getattr(handler, "directory", None)
    value = safe_text(getattr(directory, "name", None))
    return upper_no_accents(value) if uppercase else value


def resolve_handler_department(procurement: Any) -> str:
    """
    Resolve handler department from selected handler assignment first.

    Priority:
    1. procurement.handler_assignment.department.name
    2. procurement.handler_personnel.department.name
    """
    assignment = getattr(procurement, "handler_assignment", None)
    if assignment is not None:
        department = getattr(assignment, "department", None)
        if department is not None:
            return safe_text(getattr(department, "name", None))

    handler = getattr(procurement, "handler_personnel", None)
    department = getattr(handler, "department", None)
    return safe_text(getattr(department, "name", None))


def resolve_service_unit_place(service_unit: Any) -> str:
    """
    Conservative service-unit place resolution.

    Current resolution order:
    1. service_unit.region
    2. service_unit.prefecture
    3. "—"
    """
    region = getattr(service_unit, "region", None)
    if region:
        return safe_text(region)

    prefecture = getattr(service_unit, "prefecture", None)
    if prefecture:
        return safe_text(prefecture)

    return "—"


def resolve_document_total_value(procurement: Any, analysis: dict[str, Any]) -> Any:
    """
    Resolve the numeric total value that should be rendered in the document.

    Resolution order:
    1. procurement.grand_total
    2. analysis["payable_total"]
    3. analysis["sum_total"]
    4. 0
    """
    grand_total = getattr(procurement, "grand_total", None)
    if grand_total is not None:
        return grand_total

    payable_total = analysis.get("payable_total")
    if payable_total is not None:
        return payable_total

    return analysis.get("sum_total", 0)


def resolve_document_total(procurement: Any, analysis: dict[str, Any]) -> str:
    """
    Resolve the display monetary total shown in the document.
    """
    return money_plain(resolve_document_total_value(procurement, analysis))


def resolve_analysis_total(procurement: Any, analysis: dict[str, Any]) -> Decimal:
    """
    Resolve the amount threshold used by supporting-document logic.

    Resolution order:
    1. analysis["sum_total"]
    2. analysis["payable_total"]
    3. procurement.grand_total
    4. Decimal("0.00")
    """
    if analysis is None:
        analysis = {}

    candidate = analysis.get("sum_total", None)
    if candidate is not None:
        return to_decimal(candidate)

    candidate = analysis.get("payable_total", None)
    if candidate is not None:
        return to_decimal(candidate)

    candidate = getattr(procurement, "grand_total", None)
    if candidate is not None:
        return to_decimal(candidate)

    return Decimal("0.00")


def winner_supplier_line(winner: Any) -> str:
    """
    Build a supplier identity line suitable for report body usage.
    """
    if winner is None:
        return "—"

    name = safe_text(getattr(winner, "name", None), default="—")
    afm = safe_text(getattr(winner, "afm", None), default="—")
    address = safe_text(getattr(winner, "address", None), default="—")
    city = safe_text(getattr(winner, "city", None), default="—")
    phone = safe_text(getattr(winner, "phone", None), default="—")
    doy = safe_text(getattr(winner, "doy", None), default="—")
    email = safe_text(getattr(winner, "email", None), default="—")

    return (
        f"{name} με ΑΦΜ: {afm}, διεύθυνση: {address}, {city}, "
        f"τηλέφωνο: {phone}, Δ.Ο.Υ.: {doy}, email: {email}"
    )


def format_recipients_block(suppliers: Iterable[Any]) -> str:
    """
    Render one supplier per line, wrapped in Greek quotes.
    """
    rows: list[str] = []
    for supplier in list(suppliers or []):
        rows.append(f"«{winner_supplier_line(supplier)}»")

    return "\n".join(rows) if rows else "—"


def participating_supplier_objects(procurement: Any) -> list[Any]:
    """
    Return supplier objects participating in procurement via supplies_links.
    """
    suppliers: list[Any] = []

    for link in list(getattr(procurement, "supplies_links", []) or []):
        supplier = getattr(link, "supplier", None)
        if supplier is not None:
            suppliers.append(supplier)

    return suppliers


def supplier_full_info(supplier: Any) -> str:
    """
    Format supplier full info for invitation-style rendering.

    Requested output shape:
    NAME, ΑΦΜ: XXXXXXXXX, Διεύθυνση: ..., τηλέφωνο: ..., email
    """
    if supplier is None:
        return "—"

    parts: list[str] = []

    name = safe_text(getattr(supplier, "name", None), default="")
    afm = safe_text(getattr(supplier, "afm", None), default="")
    address = safe_text(getattr(supplier, "address", None), default="")
    city = safe_text(getattr(supplier, "city", None), default="")
    phone = safe_text(getattr(supplier, "phone", None), default="")
    email = safe_text(getattr(supplier, "email", None), default="")

    if name:
        parts.append(name)
    if afm:
        parts.append(f"ΑΦΜ: {afm}")

    address_parts: list[str] = []
    if address:
        address_parts.append(address)
    if city:
        address_parts.append(city)

    if address_parts:
        parts.append(f"Διεύθυνση: {', '.join(address_parts)}")

    if phone:
        parts.append(f"τηλέφωνο: {phone}")
    if email:
        parts.append(email)

    return ", ".join(parts).strip() or "—"


def invited_suppliers_inline(procurement: Any) -> str:
    """
    Inline sentence version:
    «supplier1 ...», «supplier2 ...»
    """
    suppliers = participating_supplier_objects(procurement)
    if not suppliers:
        return "—"

    return ", ".join(f"«{supplier_full_info(supplier)}»" for supplier in suppliers)


def recipients_block(procurement: Any) -> str:
    """
    Recipients block version:
    one supplier per line
    """
    suppliers = participating_supplier_objects(procurement)
    if not suppliers:
        return "—"

    return "\n".join(f"«{supplier_full_info(supplier)}»" for supplier in suppliers)


def economic_operator_label(procurement: Any) -> str:
    """
    Resolve singular/plural economic operator wording.

    - 1 supplier  -> στον οικονομικό φορέα
    - many        -> στους οικονομικούς φορείς
    """
    suppliers = participating_supplier_objects(procurement)
    if len(suppliers) == 1:
        return "στον οικονομικό φορέα"
    return "στους οικονομικούς φορείς"


__all__ = [
    "resolve_is_services",
    "resolve_proc_type_lower",
    "resolve_handler_directory",
    "resolve_handler_department",
    "resolve_service_unit_place",
    "resolve_document_total_value",
    "resolve_document_total",
    "resolve_analysis_total",
    "winner_supplier_line",
    "format_recipients_block",
    "participating_supplier_objects",
    "supplier_full_info",
    "invited_suppliers_inline",
    "recipients_block",
    "economic_operator_label",
]