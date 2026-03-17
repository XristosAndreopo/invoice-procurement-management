# app/reports/award_decision_docx.py
"""
app/reports/award_decision_docx.py

Generate "ΑΠΟΦΑΣΗ ΑΝΑΘΕΣΗΣ" as DOCX bytes using a Word template
and placeholder replacement.

Template path:
  app/templates/docx/award_decision_template.docx

Rules / behavior:
  - Entire document is normalized to Arial 12.
  - Paragraph placeholders are replaced robustly, even when split across runs.
  - The materials table body is rebuilt from procurement.materials.
  - The cost table body is rebuilt from procurement.materials and analysis data.
  - Summary rows in the cost table are rendered like the approved copy:
      * first 5 cells merged into one label cell
      * last cell contains the amount
  - {{ML_TOTAL}} inside the first award paragraph is treated as the overall document
    total, not as a per-line material total.
  - {{service.commander}} is populated from service_unit.commander.
  - The award paragraph tail is conditional:
      * ", άνευ ΦΠΑ." when VAT percent == 0
      * " και ΦΠΑ." when VAT percent != 0

Supported placeholders include:
  {{PROC_TYPE}}
  {{SERVICE_UNIT_NAME}}
  {{SERVICE_UNIT_PHONE}}
  {{SERVICE_UNIT_LOCATION}}
  {{procurement.aay}}
  {{procurement.adam_aay}}
  {{procurement.identity_prosklisis}}
  {{procurement.adam_prosklisis}}
  {{procurement.ale}}
  {{current_year}}
  {{current year}}
  {{armodiothtas}}

Analysis placeholders:
  {{AN_PUBLIC_WITHHOLD_PERCENT}}
  {{AN_PUBLIC_WITHHOLD_AMOUNT}}
  {{AN_PUBLIC_WITHHOLD_TOTAL}}
  {{AN_INCOME_TAX_RATE}}
  {{AN_INCOME_TAX_AMOUNT}}
  {{AN_INCOME_TAX_TOTAL}}
  {{AN_VAT_PERCENT}}
  {{AN_VAT_AMOUNT}}
  {{AN_SUM_TOTAL}}
  {{AN_PAYABLE_TOTAL}}

Recipient placeholders:
  {{RECIPIENTS_ACTION}}
  {{RECIPIENTS_INFO}}

Winner / supplier placeholders:
  {{WINNER_SUPPLIER_LINE}}
  {{supplier.name}}
  {{supplier.afm}}

Service placeholders:
  {{service.commander}}
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Optional

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _safe(v: Any, default: str = "—") -> str:
    """
    Return a safe display string.

    Empty / None values are normalized to the provided default.
    """
    s = ("" if v is None else str(v)).strip()
    return s if s else default


def _to_decimal(v: Any) -> Decimal:
    """
    Convert arbitrary input to Decimal safely.

    Invalid values fall back to Decimal('0.00').
    """
    try:
        return Decimal(str(v or "0"))
    except Exception:
        return Decimal("0.00")


def _money_plain(v: Any) -> str:
    """
    Return a Greek-formatted money string without currency symbol.

    Example:
      1234.56 -> "1.234,56"
    """
    d = _to_decimal(v).quantize(Decimal("0.01"))
    s = f"{d:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def _money(v: Any) -> str:
    """
    Return a Greek-formatted money string with currency symbol.
    """
    return f"{_money_plain(v)} €"


def _percent(v: Any) -> str:
    """
    Return a Greek-formatted percentage number without the percent symbol.

    Example:
      17 -> "17,00"
      6.1 -> "6,10"
    """
    d = _to_decimal(v).quantize(Decimal("0.01"))
    s = f"{d:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def _upper_service_name(name: str) -> str:
    """
    Return uppercase service unit name without forced wrapping.

    Per current requirement, we do NOT insert line breaks when the text is long.
    Word/template layout must handle overflow naturally.
    """
    return (name or "").strip().upper() or "—"


def _template_path() -> Path:
    """
    Resolve the DOCX template path inside the Flask app.
    """
    app_dir = Path(__file__).resolve().parents[1]
    return app_dir / "templates" / "docx" / "award_decision_template.docx"


def _set_global_font_arial_12(doc: Document) -> None:
    """
    Force Arial 12 across the generated document.

    This is defensive because template styles may vary and paragraph text
    replacement can collapse original runs/styles.
    """
    try:
        style = doc.styles["Normal"]
        style.font.name = "Arial"
        style.font.size = Pt(12)
    except Exception:
        pass

    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            run.font.name = "Arial"
            run.font.size = Pt(12)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.name = "Arial"
                        run.font.size = Pt(12)


def _set_cell_alignment(
    cell,
    *,
    horizontal: WD_ALIGN_PARAGRAPH = WD_ALIGN_PARAGRAPH.CENTER,
    vertical: WD_ALIGN_VERTICAL = WD_ALIGN_VERTICAL.CENTER,
) -> None:
    """
    Apply paragraph and vertical alignment to a table cell.

    We normalize all paragraphs inside the cell because Word cells may contain
    multiple paragraphs, especially after template edits or merges.
    """
    cell.vertical_alignment = vertical
    for paragraph in cell.paragraphs:
        paragraph.alignment = horizontal


def _replace_in_paragraph(paragraph, mapping: dict[str, str]) -> None:
    """
    Replace placeholders inside a paragraph.

    We rebuild the full paragraph text so placeholders still work when split
    across multiple runs in the template.
    """
    original = paragraph.text
    updated = original

    for key, value in mapping.items():
        if key in updated:
            updated = updated.replace(key, value)

    if updated != original:
        paragraph.text = updated


def _replace_everywhere(doc: Document, mapping: dict[str, str]) -> None:
    """
    Replace placeholders in normal paragraphs and inside table cells.
    """
    for paragraph in doc.paragraphs:
        _replace_in_paragraph(paragraph, mapping)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _replace_in_paragraph(paragraph, mapping)


def _find_items_table(doc: Document):
    """
    Find the 5-column materials table by matching its header.
    """
    for table in doc.tables:
        if len(table.columns) != 5 or not table.rows:
            continue

        header_text = " ".join(cell.text for cell in table.rows[0].cells).upper()
        if "CPV" in header_text and "ΠΕΡΙΓΡΑΦΗ" in header_text:
            return table

    return None


def _find_cost_table(doc: Document):
    """
    Find the 6-column cost table by matching its header.
    """
    for table in doc.tables:
        if len(table.columns) != 6 or not table.rows:
            continue

        header_text = " ".join(cell.text for cell in table.rows[0].cells).upper()
        if "ΤΙΜΗ" in header_text and "ΜΟΝ" in header_text and "ΣΥΝΟΛΟ" in header_text:
            return table

    return None


def _clear_table_body_keep_header(table, header_rows: int = 1) -> None:
    """
    Remove all rows after the given number of header rows.

    Used when rebuilding dynamic table bodies from scratch.
    """
    while len(table.rows) > header_rows:
        tbl = table._tbl
        tr = table.rows[header_rows]._tr
        tbl.remove(tr)


def _fill_items_table(table, materials: list[Any]) -> None:
    """
    Populate the 5-column items table from procurement.materials.

    The template body rows are discarded and rebuilt from DB data.
    All cells are center / center.
    """
    _clear_table_body_keep_header(table, header_rows=1)

    if not materials:
        row = table.add_row().cells
        row[0].text = "—"
        row[1].text = "Δεν υπάρχουν γραμμές υλικών/υπηρεσιών."
        row[2].text = "—"
        row[3].text = "—"
        row[4].text = "—"
        for cell in row:
            _set_cell_alignment(cell, horizontal=WD_ALIGN_PARAGRAPH.CENTER, vertical=WD_ALIGN_VERTICAL.CENTER)
        return

    for i, line in enumerate(materials, start=1):
        row = table.add_row().cells
        row[0].text = str(i)
        row[1].text = _safe(getattr(line, "description", None), default="")
        row[2].text = _safe(getattr(line, "unit", None))
        row[3].text = _safe(getattr(line, "quantity", None))
        row[4].text = _safe(getattr(line, "cpv", None))

        for cell in row:
            _set_cell_alignment(cell, horizontal=WD_ALIGN_PARAGRAPH.CENTER, vertical=WD_ALIGN_VERTICAL.CENTER)


def _add_cost_summary_row(table, label: str, amount: Any) -> None:
    """
    Add one summary row to the 6-column cost table.

    Required visual behavior:
      - Cells 0..4 are merged into a single left label cell.
      - Merged label cell:
          * vertical alignment: center
          * paragraph alignment: right
      - Cell 5 contains the numeric amount:
          * vertical alignment: center
          * paragraph alignment: center
    """
    row = table.add_row()
    merged_cell = row.cells[0].merge(row.cells[4])
    merged_cell.text = label
    row.cells[5].text = _money_plain(amount)

    _set_cell_alignment(
        merged_cell,
        horizontal=WD_ALIGN_PARAGRAPH.RIGHT,
        vertical=WD_ALIGN_VERTICAL.CENTER,
    )
    _set_cell_alignment(
        row.cells[5],
        horizontal=WD_ALIGN_PARAGRAPH.CENTER,
        vertical=WD_ALIGN_VERTICAL.CENTER,
    )


def _fill_cost_table(table, materials: list[Any], analysis: dict[str, Any]) -> None:
    """
    Populate the 6-column cost table.

    Behavior:
      - Remove all body rows after the header.
      - Recreate material rows from procurement.materials.
      - Recreate summary rows from payment analysis.
      - Material rows use center / center in all cells.
      - Summary rows use:
          * merged label cell => center(vertical) / right(horizontal)
          * amount cell => center / center
    """
    _clear_table_body_keep_header(table, header_rows=1)

    if not materials:
        row = table.add_row().cells
        for i in range(6):
            row[i].text = "—"
        for cell in row:
            _set_cell_alignment(cell, horizontal=WD_ALIGN_PARAGRAPH.CENTER, vertical=WD_ALIGN_VERTICAL.CENTER)
    else:
        for i, line in enumerate(materials, start=1):
            qty = getattr(line, "quantity", None)
            unit_price = getattr(line, "unit_price", None)
            total_pre_vat = getattr(line, "total_pre_vat", None)

            row = table.add_row().cells
            row[0].text = str(i)
            row[1].text = _safe(getattr(line, "description", None), default="")
            row[2].text = _safe(getattr(line, "unit", None))
            row[3].text = _safe(qty)
            row[4].text = _money_plain(unit_price)
            row[5].text = _money_plain(total_pre_vat)

            for cell in row:
                _set_cell_alignment(
                    cell,
                    horizontal=WD_ALIGN_PARAGRAPH.CENTER,
                    vertical=WD_ALIGN_VERTICAL.CENTER,
                )

    public_withholdings = analysis.get("public_withholdings") or {}
    income_tax = analysis.get("income_tax") or {}

    public_pct = _percent(public_withholdings.get("total_percent", 0))
    income_tax_pct = _percent(income_tax.get("rate_percent", 0))
    vat_pct = _percent(analysis.get("vat_percent", 0))

    _add_cost_summary_row(table, "Μερικό Σύνολο", analysis.get("sum_total", 0))
    _add_cost_summary_row(
        table,
        f"Κρατήσεις Υπερ Δημοσίου ({public_pct}%)",
        public_withholdings.get("total_amount", 0),
    )
    _add_cost_summary_row(
        table,
        f"ΦΕ ({income_tax_pct}%)",
        income_tax.get("amount", 0),
    )
    _add_cost_summary_row(
        table,
        f"ΦΠΑ ({vat_pct}%)",
        analysis.get("vat_amount", 0),
    )
    _add_cost_summary_row(table, "Τελικό Σύνολο", analysis.get("payable_total", 0))


def _winner_supplier_line(winner: Any) -> str:
    """
    Return the supplier line used in body and recipients blocks.
    """
    name = _safe(getattr(winner, "name", None), default="—")
    afm = _safe(getattr(winner, "afm", None), default="—")
    addr = _safe(getattr(winner, "address", None), default="—")
    city = _safe(getattr(winner, "city", None), default="—")
    phone = _safe(getattr(winner, "phone", None), default="—")
    doy = _safe(getattr(winner, "doy", None), default="—")
    email = _safe(getattr(winner, "email", None), default="—")

    return (
        f"{name} με ΑΦΜ: {afm}, διεύθυνση: {addr}, {city}, "
        f"τηλέφωνο: {phone}, Δ.Ο.Υ.: {doy}, email: {email}"
    )


def _format_recipients(other_suppliers: Iterable[Any]) -> str:
    """
    Build the multi-line recipients block for 'Αποδέκτες για Πληροφορία'.
    """
    rows: list[str] = []
    for supplier in list(other_suppliers or []):
        rows.append(f"«{_winner_supplier_line(supplier)}»")

    return "\n".join(rows) if rows else "—"


def _resolve_armodiothtas(procurement: Any) -> str:
    """
    Resolve the responsibility text defensively.

    Resolution order:
      1. procurement.armodiothtas
      2. procurement.ale_kae.responsibility
      3. em dash
    """
    direct = getattr(procurement, "armodiothtas", None)
    if direct:
        return _safe(direct)

    ale_kae_obj = getattr(procurement, "ale_kae", None)
    if ale_kae_obj is not None:
        responsibility = getattr(ale_kae_obj, "responsibility", None)
        if responsibility:
            return _safe(responsibility)

    return "—"


def _resolve_document_total(procurement: Any, analysis: dict[str, Any]) -> str:
    """
    Resolve the overall total for the first award paragraph.

    Important:
      - {{ML_TOTAL}} in the first narrative paragraph is NOT a line total.
      - We prefer procurement.grand_total.
      - If unavailable, we fall back to analysis.payable_total.
      - Final fallback is analysis.sum_total.
    """
    grand_total = getattr(procurement, "grand_total", None)
    if grand_total is not None:
        return _money_plain(grand_total)

    payable_total = analysis.get("payable_total")
    if payable_total is not None:
        return _money_plain(payable_total)

    return _money_plain(analysis.get("sum_total", 0))


def _apply_award_paragraph_vat_text(doc: Document, proc_type: str, vat_percent: Any) -> None:
    """
    Fix the trailing VAT phrase in paragraph 1.

    The template currently ends the sentence with:
      '... συμπεριλαμβανομένων κρατήσεων, {{PROC_TYPE}}.'

    Business rule required now:
      - if VAT == 0 => ', άνευ ΦΠΑ.'
      - if VAT != 0 => ' και ΦΠΑ.'

    We patch only the paragraph that contains:
      'συμπεριλαμβανομένων κρατήσεων'
    so the rest of {{PROC_TYPE}} replacements remain intact elsewhere.
    """
    vat_is_zero = _to_decimal(vat_percent).quantize(Decimal("0.01")) == Decimal("0.00")
    replacement_tail = ", άνευ ΦΠΑ." if vat_is_zero else " και ΦΠΑ."

    targets = [
        f", {proc_type}.",
        f", {proc_type} .",
        f"/ {proc_type}.",
        f"/{proc_type}.",
    ]

    for paragraph in doc.paragraphs:
        text = paragraph.text or ""
        if "συμπεριλαμβανομένων κρατήσεων" not in text:
            continue

        new_text = text
        for target in targets:
            if target in new_text:
                new_text = new_text.replace(target, replacement_tail)

        new_text = new_text.replace(", άνευ ΦΠΑ/ και ΦΠΑ.", ", άνευ ΦΠΑ.")
        new_text = new_text.replace(", άνευ ΦΠΑ / και ΦΠΑ.", ", άνευ ΦΠΑ.")
        new_text = new_text.replace(", άνευ ΦΠΑ/και ΦΠΑ.", ", άνευ ΦΠΑ.")
        new_text = new_text.replace(", άνευ ΦΠΑ /και ΦΠΑ.", ", άνευ ΦΠΑ.")

        if new_text != text:
            paragraph.text = new_text
            break


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class AwardDecisionConstants:
    """
    Reserved for future report constants / policy flags.
    """
    pass


def build_award_decision_docx(
    *,
    procurement: Any,
    service_unit: Any,
    winner: Optional[Any],
    other_suppliers: Iterable[Any],
    analysis: dict,
    is_services: bool,
    constants: Optional[AwardDecisionConstants] = None,
) -> bytes:
    """
    Build and return the final DOCX bytes for the award decision.

    Security / correctness notes:
      - The function is pure report-generation logic.
      - It trusts only the server-side objects it receives.
      - It does not read values from UI state.
      - Table reconstruction is explicit to avoid leaving stale template rows.
    """
    _ = constants  # reserved for future use

    tpl_path = _template_path()
    if not tpl_path.exists():
        raise FileNotFoundError(f"Template not found: {tpl_path}")

    doc = Document(str(tpl_path))

    proc_type = "παροχή υπηρεσιών" if is_services else "προμήθεια υλικών"

    aay = _safe(getattr(procurement, "aay", None))
    adam_aay = _safe(getattr(procurement, "adam_aay", None))
    identity_prosklisis = _safe(getattr(procurement, "identity_prosklisis", None))
    adam_prosklisis = _safe(getattr(procurement, "adam_prosklisis", None))
    ale = _safe(getattr(procurement, "ale", None))
    current_year = str(getattr(procurement, "fiscal_year", None) or datetime.now().year)

    public_withholdings = analysis.get("public_withholdings") or {}
    income_tax = analysis.get("income_tax") or {}

    public_pct = _percent(public_withholdings.get("total_percent", 0))
    income_tax_pct = _percent(income_tax.get("rate_percent", 0))
    vat_pct = _percent(analysis.get("vat_percent", 0))

    winner_name = _safe(getattr(winner, "name", None), default="—")
    winner_afm = _safe(getattr(winner, "afm", None), default="—")
    winner_line = _winner_supplier_line(winner) if winner is not None else "—"
    commander = _safe(getattr(service_unit, "commander", None), default="—")
    document_total_plain = _resolve_document_total(procurement, analysis)
    handler = getattr(procurement, "handler_personnel", None)

    mapping: dict[str, str] = {
        "{{PROC_TYPE}}": proc_type,
        "{{SERVICE_UNIT_NAME}}": _upper_service_name(
            _safe(getattr(service_unit, "description", None), default="—")
        ),
        "{{SERVICE_UNIT_PHONE}}": _safe(getattr(service_unit, "phone", None)),
        "{{SERVICE_UNIT_LOCATION}}": _safe(
            getattr(service_unit, "address", None),
            default="Τοποθεσία",
        ),
        "{{procurement.aay}}": aay,
        "{{procurement.adam_aay}}": adam_aay,
        "{{procurement.identity_prosklisis}}": identity_prosklisis,
        "{{procurement.adam_prosklisis}}": adam_prosklisis,
        "{{ procurement.adam_prosklisis}}": adam_prosklisis,
        "{{procurement.ale}}": ale,
        "{{current_year}}": current_year,
        "{{current year}}": current_year,
        "{{armodiothtas}}": _resolve_armodiothtas(procurement),
        "{{WINNER_SUPPLIER_LINE}}": winner_line,
        "{{supplier.name}}": winner_name,
        "{{supplier.afm}}": winner_afm,
        "{{RECIPIENTS_ACTION}}": f"«{winner_line}»" if winner is not None else "—",
        "{{RECIPIENTS_INFO}}": _format_recipients(other_suppliers),
        "{{service.commander}}": commander,
        "{{AN_PUBLIC_WITHHOLD_PERCENT}}": f" ({public_pct}%)",
        "{{AN_PUBLIC_WITHHOLD_AMOUNT}}": _money_plain(public_withholdings.get("total_amount", 0)),
        "{{AN_PUBLIC_WITHHOLD_TOTAL}}": _money_plain(public_withholdings.get("total_amount", 0)),
        "{{AN_INCOME_TAX_RATE}}": f" ({income_tax_pct}%)",
        "{{AN_INCOME_TAX_AMOUNT}}": _money_plain(income_tax.get("amount", 0)),
        "{{AN_INCOME_TAX_TOTAL}}": _money_plain(income_tax.get("amount", 0)),
        "{{AN_VAT_PERCENT}}": vat_pct,
        "{{AN_VAT_AMOUNT}}": _money_plain(analysis.get("vat_amount", 0)),
        "{{AN_SUM_TOTAL}}": _money_plain(analysis.get("sum_total", 0)),
        "{{AN_PAYABLE_TOTAL}}": _money_plain(analysis.get("payable_total", 0)),
        "{{ML_TOTAL}}": document_total_plain,
        "{{HANDLER_DIRECTORY}}": _safe(
            getattr(getattr(handler, "directory", None), "name", None)
        ),
        "{{HANDLER_DEPARTMENT}}": _safe(
            getattr(getattr(handler, "department", None), "name", None)
        ),
    }

    _replace_everywhere(doc, mapping)
    _apply_award_paragraph_vat_text(doc, proc_type, analysis.get("vat_percent", 0))

    materials = list(getattr(procurement, "materials", []) or [])

    items_table = _find_items_table(doc)
    if items_table is not None:
        _fill_items_table(items_table, materials)

    cost_table = _find_cost_table(doc)
    if cost_table is not None:
        _fill_cost_table(cost_table, materials, analysis)

    _set_global_font_arial_12(doc)

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def build_award_decision_filename(
    *,
    procurement: Any,
    winner: Optional[Any],
    is_services: bool,
) -> str:
    """
    Build the output filename.

    Rule:
      Απόφαση Ανάθεσης (Προμήθειας Υλικών/Παροχής Υπηρεσιών)
      (ΠΕΡΙΓΡΑΦΗ ΠΡΟΜΗΘΕΥΤΗ) (ΓΕΝΙΚΟ ΣΥΝΟΛΟ).docx
    """
    kind = "Παροχής Υπηρεσιών" if is_services else "Προμήθειας Υλικών"
    supplier_name = _safe(getattr(winner, "name", None), default="—")

    grand_total = getattr(procurement, "grand_total", None)

    if grand_total is None and hasattr(procurement, "compute_payment_analysis"):
        try:
            analysis = procurement.compute_payment_analysis()
            grand_total = analysis.get("payable_total")
        except Exception:
            grand_total = None

    total_str = _money_plain(grand_total)
    return f"Απόφαση Ανάθεσης {kind} {supplier_name} {total_str}.docx"

