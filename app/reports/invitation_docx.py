"""
app/reports/invitation_docx.py

Generate "ΠΡΟΣΚΛΗΣΗ" as DOCX bytes using a Word template and placeholder
replacement.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from docx import Document
from docx.shared import Pt


def _safe(value: Any, default: str = "—") -> str:
    text = ("" if value is None else str(value)).strip()
    return text if text else default


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0.00")


def _money_plain(value: Any) -> str:
    amount = _to_decimal(value).quantize(Decimal("0.01"))
    text = f"{amount:,.2f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _upper_no_accents(value: Any, default: str = "—") -> str:
    text = _safe(value, default=default)
    normalized = unicodedata.normalize("NFD", text)
    no_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", no_marks).upper()


def _lower_preserve_accents(value: Any, default: str = "—") -> str:
    """
    Return lowercase text while preserving accents/diacritics.
    """
    text = _safe(value, default=default)
    return text.lower()


def _format_date(value: Any, default: str = "—") -> str:
    if value is None:
        return default

    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    try:
        return value.strftime("%d/%m/%Y")
    except Exception:
        text = str(value).strip()
        return text if text else default


def _short_date_el(value: Any | None = None) -> str:
    months = {
        1: "Ιαν",
        2: "Φεβ",
        3: "Μαρ",
        4: "Απρ",
        5: "Μαϊ",
        6: "Ιουν",
        7: "Ιουλ",
        8: "Αυγ",
        9: "Σεπ",
        10: "Οκτ",
        11: "Νοε",
        12: "Δεκ",
    }

    dt = value or datetime.now()

    try:
        day = int(dt.day)
        month = int(dt.month)
        year_2d = int(dt.year) % 100
    except Exception:
        dt = datetime.now()
        day = dt.day
        month = dt.month
        year_2d = dt.year % 100

    month_label = months.get(month, "")
    return f"{day:02d} {month_label} {year_2d:02d}".strip()


def _template_path() -> Path:
    app_dir = Path(__file__).resolve().parents[1]
    return app_dir / "templates" / "docx" / "invitation_template.docx"


def _set_global_font_arial_12(doc: Document) -> None:
    try:
        style = doc.styles["Normal"]
        style.font.name = "Arial"
        style.font.size = Pt(12)
    except Exception:
        pass


def _paragraph_runs_text(paragraph) -> tuple[str, list[tuple[int, int, int]]]:
    pieces: list[str] = []
    positions: list[tuple[int, int, int]] = []

    cursor = 0
    for idx, run in enumerate(paragraph.runs):
        text = run.text or ""
        pieces.append(text)
        start = cursor
        end = start + len(text)
        positions.append((idx, start, end))
        cursor = end

    return "".join(pieces), positions


def _find_run_index_at_offset(positions: list[tuple[int, int, int]], offset: int) -> int:
    for run_index, start, end in positions:
        if start <= offset < end:
            return run_index

    if positions and offset == positions[-1][2]:
        return positions[-1][0]

    return -1


def _replace_placeholder_once_in_paragraph(paragraph, placeholder: str, replacement: str) -> bool:
    full_text, positions = _paragraph_runs_text(paragraph)
    if not full_text or placeholder not in full_text:
        return False

    start = full_text.find(placeholder)
    end = start + len(placeholder)

    start_run_idx = _find_run_index_at_offset(positions, start)
    end_run_idx = _find_run_index_at_offset(positions, end - 1)

    if start_run_idx < 0 or end_run_idx < 0:
        return False

    start_run = paragraph.runs[start_run_idx]
    end_run = paragraph.runs[end_run_idx]

    start_run_global_start = positions[start_run_idx][1]
    end_run_global_start = positions[end_run_idx][1]

    prefix = start_run.text[: start - start_run_global_start]
    suffix = end_run.text[(end - end_run_global_start):]

    start_run.text = f"{prefix}{replacement}{suffix}"

    for idx in range(start_run_idx + 1, end_run_idx + 1):
        paragraph.runs[idx].text = ""

    return True


def _replace_placeholder_all_in_paragraph(paragraph, placeholder: str, replacement: str) -> None:
    while _replace_placeholder_once_in_paragraph(paragraph, placeholder, replacement):
        pass


def _replace_placeholders_everywhere(doc: Document, mapping: dict[str, str]) -> None:
    for paragraph in doc.paragraphs:
        for placeholder, replacement in mapping.items():
            _replace_placeholder_all_in_paragraph(paragraph, placeholder, replacement)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for placeholder, replacement in mapping.items():
                        _replace_placeholder_all_in_paragraph(paragraph, placeholder, replacement)


def _resolve_proc_type(procurement: Any) -> str:
    materials = list(getattr(procurement, "materials", []) or [])
    is_services = any(bool(getattr(line, "is_service", False)) for line in materials)
    return "παροχή υπηρεσιών" if is_services else "προμήθεια υλικών"


def _resolve_handler_directory(procurement: Any) -> str:
    assignment = getattr(procurement, "handler_assignment", None)
    directory = getattr(assignment, "directory", None)
    return _upper_no_accents(getattr(directory, "name", None))


def _resolve_service_unit_place(service_unit: Any) -> str:
    return "—"


def _participating_supplier_objects(procurement: Any) -> list[Any]:
    suppliers: list[Any] = []

    for link in list(getattr(procurement, "supplies_links", []) or []):
        supplier = getattr(link, "supplier", None)
        if supplier is not None:
            suppliers.append(supplier)

    return suppliers


def _economic_operator_label(procurement: Any) -> str:
    """
    - 1 supplier  -> στον οικονομικό φορέα
    - many        -> στους οικονομικούς φορείς
    """
    suppliers = _participating_supplier_objects(procurement)
    if len(suppliers) == 1:
        return "στον οικονομικό φορέα"
    return "στους οικονομικούς φορείς"


def _supplier_full_info(supplier: Any) -> str:
    """
    Requested format:
    NAME, ΑΦΜ: XXXXXXXXX, Διεύθυνση: ..., τηλέφωνο: ..., email
    """
    if supplier is None:
        return "—"

    parts: list[str] = []

    name = _safe(getattr(supplier, "name", None), default="")
    afm = _safe(getattr(supplier, "afm", None), default="")
    address = _safe(getattr(supplier, "address", None), default="")
    city = _safe(getattr(supplier, "city", None), default="")
    phone = _safe(getattr(supplier, "phone", None), default="")
    email = _safe(getattr(supplier, "email", None), default="")

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


def _invited_suppliers_inline(procurement: Any) -> str:
    """
    Inline sentence version:
    «supplier1 ...», «supplier2 ...»
    """
    suppliers = _participating_supplier_objects(procurement)
    if not suppliers:
        return "—"

    return ", ".join(f"«{_supplier_full_info(supplier)}»" for supplier in suppliers)


def _recipients_block(procurement: Any) -> str:
    """
    Recipients section version:
    one supplier per line
    """
    suppliers = _participating_supplier_objects(procurement)
    if not suppliers:
        return "—"

    return "\n".join(f"«{_supplier_full_info(supplier)}»" for supplier in suppliers)


def _material_lines_block(procurement: Any) -> dict[str, str]:
    lines = list(getattr(procurement, "materials", []) or [])
    if not lines:
        return {
            "{{ML_NO}}": "—",
            "{{ML_DESC}}": "—",
            "{{ML_UNIT}}": "—",
            "{{ML_QTY}}": "—",
            "{{ML_CPV}}": "—",
        }

    nos: list[str] = []
    descs: list[str] = []
    units: list[str] = []
    qtys: list[str] = []
    cpvs: list[str] = []

    for idx, line in enumerate(lines, start=1):
        nos.append(str(idx))
        descs.append(_safe(getattr(line, "description", None)))
        units.append(_safe(getattr(line, "unit", None)))
        qty_value = getattr(line, "quantity", None)
        qtys.append(_money_plain(qty_value) if qty_value is not None else "—")
        cpvs.append(_safe(getattr(line, "cpv", None)))

    return {
        "{{ML_NO}}": "\n".join(nos),
        "{{ML_DESC}}": "\n".join(descs),
        "{{ML_UNIT}}": "\n".join(units),
        "{{ML_QTY}}": "\n".join(qtys),
        "{{ML_CPV}}": "\n".join(cpvs),
    }


@dataclass(frozen=True)
class InvitationConstants:
    pass


def build_invitation_docx(
    *,
    procurement: Any,
    service_unit: Any,
    winner: Optional[Any],
    analysis: dict[str, Any],
    constants: Optional[InvitationConstants] = None,
) -> bytes:
    _ = winner
    _ = analysis
    _ = constants

    template_path = _template_path()
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    doc = Document(str(template_path))

    materials_mapping = _material_lines_block(procurement)
    invited_suppliers_inline = _invited_suppliers_inline(procurement)
    recipients_info = _recipients_block(procurement)

    mapping: dict[str, str] = {
        "{{SERVICE_UNIT_NAME}}": _upper_no_accents(getattr(service_unit, "description", None)),
        "{{SERVICE_UNIT_DESCRIPTION}}": _safe(getattr(service_unit, "description", None)),
        "{{PROCUREMENT_SHORT_DESCRIPTION}}": _lower_preserve_accents(
            getattr(procurement, "description", None)
        ),
        "{{HANDLER_DIRECTORY}}": _resolve_handler_directory(procurement),
        "{{SERVICE_UNIT_PHONE}}": _safe(getattr(service_unit, "phone", None)),
        "{{ SERVICE_UNIT_PHONE}}": _safe(getattr(service_unit, "phone", None)),
        "{{SERVICE_UNIT_REGION}}": _safe(getattr(service_unit, "region", None)),
        "{{SHORT_DATE}}": _short_date_el(),
        "{{PROC_TYPE}}": _resolve_proc_type(procurement),
        "{{ECONOMIC_OPERATOR_LABEL}}": _economic_operator_label(procurement),
        "{{procurement.aay}}": _safe(getattr(procurement, "aay", None)),
        "{{procurement.adam_aay}}": _safe(getattr(procurement, "adam_aay", None)),
        "{{procurement hop_approval_commitment}}": _safe(
            getattr(procurement, "hop_approval_commitment", None)
        ),
        "{{INVITED_SUPPLIERS_INLINE}}": invited_suppliers_inline,
        "{{RECIPIENTS_INFO}}": recipients_info,

        # Backward compatibility
        "{{WINNER_SUPPLIER_LINE}}": invited_suppliers_inline,

        "{{SERVICE_UNIT_ADRESS}}": _safe(getattr(service_unit, "address", None)),
        "{{ SERVICE_UNIT_ADRESS}}": _safe(getattr(service_unit, "address", None)),
        "{{SERVICE_UNIT_PLACE}}": _resolve_service_unit_place(service_unit),
        "{{SERVICE_UNIT_POSTAL_CODE}}": _safe(getattr(service_unit, "postal_code", None)),
        "{{ SERVICE_UNIT_EMAIL}}": _safe(getattr(service_unit, "email", None)),
        "{{SERVICE_UNIT_EMAIL}}": _safe(getattr(service_unit, "email", None)),
        "{{service.commander}}": _safe(getattr(service_unit, "commander", None)),
        "{{COMMANDER_ROLE_TYPE}}": _safe(getattr(service_unit, "commander_role_type", None)),
    }

    mapping.update(materials_mapping)

    _replace_placeholders_everywhere(doc, mapping)
    _set_global_font_arial_12(doc)

    output = BytesIO()
    doc.save(output)
    return output.getvalue()


def build_invitation_filename(
    *,
    procurement: Any,
    winner: Optional[Any],
) -> str:
    _ = winner

    description = _safe(
        getattr(procurement, "description", None),
        default=f"Προμήθεια #{getattr(procurement, 'id', '—')}",
    )
    return f"Πρόσκληση Υποβολής Προσφοράς για την {description}.docx"