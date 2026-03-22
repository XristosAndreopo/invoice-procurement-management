"""
app/reports/expense_transmittal_docx.py

Generate "ΔΙΑΒΙΒΑΣΤΙΚΟ ΔΑΠΑΝΗΣ" as DOCX bytes using a Word template
and placeholder replacement.

SOURCE OF TRUTH
---------------
This implementation is aligned strictly to the provided current template and
the current ServiceUnit / Procurement contract.

IMPORTANT FIELD MAPPING RULES
-----------------------------
The uploaded DOCX contains placeholders that must be resolved from the current
domain objects only.

Current source-of-truth fields used:
- procurement.hop_approval
- procurement.hop_preapproval
- procurement.aay
- procurement.protocol_number
- procurement.committee.identity_text
- procurement.invoice_number
- procurement.invoice_date
- procurement.invoice_receipt_date
- procurement.identity_prosklisis
- service_unit.description
- service_unit.phone
- service_unit.region
- service_unit.curator                     -> APPLICATION_ADMIN
- service_unit.application_admin_directory -> APPLICATION_ADMIN_DIRECTORY

IMPORTANT RENDERING RULES
-------------------------
1. {{SUPPORTING_DOCUMENTS_BLOCK}} must be placed alone in its own paragraph.
2. The supporting-documents block is rendered as separate paragraphs.
3. There must be NO blank paragraphs between η., θ., ι., ...
4. Each generated line must begin with exactly two tab characters.
5. Paragraph tab stops / paragraph properties are cloned from paragraph 'ζ.'.
6. Placeholder replacement must work even when placeholders are split across runs.
7. Run-level formatting in the template must be preserved as much as possible.
"""

from __future__ import annotations

import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from docx import Document
from docx.oxml import OxmlElement
from docx.shared import Pt


# ---------------------------------------------------------------------------
# Generic formatting helpers
# ---------------------------------------------------------------------------

def _safe(value: Any, default: str = "—") -> str:
    """
    Convert any value to a stripped display string.
    """
    text = ("" if value is None else str(value)).strip()
    return text if text else default


def _to_decimal(value: Any) -> Decimal:
    """
    Safely convert numeric-like input to Decimal.
    """
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0.00")


def _money_plain(value: Any) -> str:
    """
    Format decimal-like value using Greek-style separators without currency.

    Example
    -------
    1700.5 -> "1.700,50"
    """
    amount = _to_decimal(value).quantize(Decimal("0.01"))
    text = f"{amount:,.2f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _upper_no_accents(value: Any, default: str = "—") -> str:
    """
    Return uppercase Greek/Latin text without accents/diacritics.
    """
    text = _safe(value, default=default)
    normalized = unicodedata.normalize("NFD", text)
    no_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", no_marks).upper()


def _upper_service_name(name: str) -> str:
    """
    Uppercase service name without accents for official document styling.
    """
    return _upper_no_accents(name)


def _format_date(value: Any, default: str = "—") -> str:
    """
    Format a date value as DD/MM/YYYY.
    """
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
    """
    Return date in Greek short format: DD Mon YY.

    Examples:
    - 07 Μαρ 26
    - 22 Μαρ 26
    """
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


def _int_to_greek_words_genitive(n: int) -> str:
    """
    Convert a non-negative integer to Greek words in genitive case,
    suitable for phrases like:

    - συνολικής αξίας ...
    - ποσού ...

    Examples:
    1755 -> χιλίων επτακοσίων πενήντα πέντε
    20   -> είκοσι
    200  -> διακοσίων
    """
    if n < 0:
        raise ValueError("Negative values are not supported.")
    if n == 0:
        return "μηδενός"

    units = {
        0: "",
        1: "ενός",
        2: "δύο",
        3: "τριών",
        4: "τεσσάρων",
        5: "πέντε",
        6: "έξι",
        7: "επτά",
        8: "οκτώ",
        9: "εννέα",
    }

    teens = {
        10: "δέκα",
        11: "έντεκα",
        12: "δώδεκα",
        13: "δεκατριών",
        14: "δεκατεσσάρων",
        15: "δεκαπέντε",
        16: "δεκαέξι",
        17: "δεκαεπτά",
        18: "δεκαοκτώ",
        19: "δεκαεννέα",
    }

    tens = {
        2: "είκοσι",
        3: "τριάντα",
        4: "σαράντα",
        5: "πενήντα",
        6: "εξήντα",
        7: "εβδομήντα",
        8: "ογδόντα",
        9: "ενενήντα",
    }

    hundreds = {
        1: "εκατόν",
        2: "διακοσίων",
        3: "τριακοσίων",
        4: "τετρακοσίων",
        5: "πεντακοσίων",
        6: "εξακοσίων",
        7: "επτακοσίων",
        8: "οκτακοσίων",
        9: "εννιακοσίων",
    }

    def two_digits(num: int) -> str:
        if num < 10:
            return units[num]
        if 10 <= num <= 19:
            return teens[num]

        t = num // 10
        u = num % 10
        if u == 0:
            return tens[t]
        return f"{tens[t]} {units[u]}".strip()

    def three_digits(num: int) -> str:
        if num < 100:
            return two_digits(num)

        h = num // 100
        rem = num % 100

        if rem == 0:
            if h == 1:
                return "εκατό"
            return hundreds[h]

        return f"{hundreds[h]} {two_digits(rem)}".strip()

    parts: list[str] = []

    millions = n // 1_000_000
    remainder = n % 1_000_000

    thousands = remainder // 1_000
    below_thousand = remainder % 1_000

    if millions:
        if millions == 1:
            parts.append("ενός εκατομμυρίου")
        else:
            parts.append(f"{three_digits(millions)} εκατομμυρίων")

    if thousands:
        if thousands == 1:
            parts.append("χιλίων")
        else:
            parts.append(f"{three_digits(thousands)} χιλιάδων")

    if below_thousand:
        parts.append(three_digits(below_thousand))

    return " ".join(p for p in parts if p).strip()


def _money_words_el(value: Any) -> str:
    """
    Convert a numeric amount to Greek words in genitive case, suitable for:
    'συνολικής αξίας ...' or 'ποσού ...'

    Examples:
    1755.00 -> χιλίων επτακοσίων πενήντα πέντε ευρώ
    1755.20 -> χιλίων επτακοσίων πενήντα πέντε ευρώ και είκοσι λεπτών
    12.40   -> δώδεκα ευρώ και σαράντα λεπτών
    """
    amount = _to_decimal(value).quantize(Decimal("0.01"))

    euros = int(amount)
    cents = int((amount - Decimal(euros)) * 100)

    euro_words = _int_to_greek_words_genitive(euros)

    if cents == 0:
        return f"{euro_words} ευρώ"

    cents_words = _int_to_greek_words_genitive(cents)
    return f"{euro_words} ευρώ και {cents_words} λεπτών"


def _template_path() -> Path:
    """
    Resolve the DOCX template path.
    """
    app_dir = Path(__file__).resolve().parents[1]
    return app_dir / "templates" / "docx" / "expense_transmittal_template.docx"


# ---------------------------------------------------------------------------
# DOCX low-level helpers
# ---------------------------------------------------------------------------

def _clone_paragraph_properties(src_paragraph, dst_paragraph) -> None:
    """
    Clone paragraph properties XML (including tabs, indents, spacing, alignment).
    """
    dst_p = dst_paragraph._p
    src_p = src_paragraph._p

    if dst_p.pPr is not None:
        dst_p.remove(dst_p.pPr)

    if src_p.pPr is not None:
        dst_p.insert(0, deepcopy(src_p.pPr))


def _copy_run_style(src_run, dst_run) -> None:
    """
    Copy run-level style.
    """
    if src_run is None:
        return

    dst_run.bold = src_run.bold
    dst_run.italic = src_run.italic
    dst_run.underline = src_run.underline
    dst_run.font.name = src_run.font.name
    dst_run.font.size = src_run.font.size

    try:
        if src_run.font.color is not None and src_run.font.color.rgb is not None:
            dst_run.font.color.rgb = src_run.font.color.rgb
    except Exception:
        pass

    try:
        dst_run.font.highlight_color = src_run.font.highlight_color
    except Exception:
        pass


def _insert_paragraph_after(paragraph):
    """
    Insert and return a new paragraph immediately after the given paragraph.
    """
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    return paragraph._parent.add_paragraph().__class__(new_p, paragraph._parent)


def _clear_paragraph_runs(paragraph) -> None:
    """
    Remove all runs from a paragraph while preserving paragraph properties.
    """
    p = paragraph._p
    for child in list(p):
        if child.tag.endswith("}r") or child.tag.endswith("}hyperlink"):
            p.remove(child)


def _set_global_font_arial_12(doc: Document) -> None:
    """
    Normalize generated report font to Arial 12 where possible.
    """
    try:
        style = doc.styles["Normal"]
        style.font.name = "Arial"
        style.font.size = Pt(12)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Placeholder replacement across runs
# ---------------------------------------------------------------------------

def _paragraph_runs_text(paragraph) -> tuple[str, list[tuple[int, int, int]]]:
    """
    Return paragraph full text and positional map.

    The map contains tuples:
    (run_index, start_offset_in_full_text, end_offset_in_full_text)
    """
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
    """
    Find the run index containing the given character offset.
    """
    for run_index, start, end in positions:
        if start <= offset < end:
            return run_index

    if positions and offset == positions[-1][2]:
        return positions[-1][0]

    return -1


def _replace_placeholder_once_in_paragraph(paragraph, placeholder: str, replacement: str) -> bool:
    """
    Replace one occurrence of a placeholder in a paragraph, even if the
    placeholder is split across multiple runs.

    The replacement inherits the style of the first run participating in the
    placeholder.
    """
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
    """
    Replace all occurrences of a placeholder in a paragraph, robustly across runs.
    """
    while _replace_placeholder_once_in_paragraph(paragraph, placeholder, replacement):
        pass


def _replace_placeholders_everywhere(doc: Document, mapping: dict[str, str]) -> None:
    """
    Replace placeholders across all paragraphs and table paragraphs.
    """
    for paragraph in doc.paragraphs:
        for placeholder, replacement in mapping.items():
            _replace_placeholder_all_in_paragraph(paragraph, placeholder, replacement)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for placeholder, replacement in mapping.items():
                        _replace_placeholder_all_in_paragraph(paragraph, placeholder, replacement)


# ---------------------------------------------------------------------------
# Domain formatting helpers
# ---------------------------------------------------------------------------

def _resolve_document_total(procurement: Any, analysis: dict[str, Any]) -> str:
    """
    Resolve the monetary total shown in the transmittal document.

    Resolution order:
    1. procurement.grand_total
    2. analysis["payable_total"]
    3. analysis["sum_total"]
    4. 0.00
    """
    grand_total = getattr(procurement, "grand_total", None)
    if grand_total is not None:
        return _money_plain(grand_total)

    payable_total = analysis.get("payable_total")
    if payable_total is not None:
        return _money_plain(payable_total)

    return _money_plain(analysis.get("sum_total", 0))


def _resolve_document_total_value(procurement: Any, analysis: dict[str, Any]) -> Any:
    """
    Resolve the numeric total value shown in the transmittal document
    for both numeric and text rendering.
    """
    grand_total = getattr(procurement, "grand_total", None)
    if grand_total is not None:
        return grand_total

    payable_total = analysis.get("payable_total")
    if payable_total is not None:
        return payable_total

    return analysis.get("sum_total", 0)


def _resolve_analysis_total(procurement: Any, analysis: dict[str, Any]) -> Decimal:
    """
    Resolve the amount threshold used for supporting-documents visibility.

    The user explicitly requested the amount from the analysis total.
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
        return _to_decimal(candidate)

    candidate = analysis.get("payable_total", None)
    if candidate is not None:
        return _to_decimal(candidate)

    candidate = getattr(procurement, "grand_total", None)
    if candidate is not None:
        return _to_decimal(candidate)

    return Decimal("0.00")


def _winner_supplier_line(winner: Any) -> str:
    """
    Build a supplier identity line suitable for the report body.
    """
    if winner is None:
        return "—"

    name = _safe(getattr(winner, "name", None), default="—")
    afm = _safe(getattr(winner, "afm", None), default="—")
    address = _safe(getattr(winner, "address", None), default="—")
    city = _safe(getattr(winner, "city", None), default="—")
    phone = _safe(getattr(winner, "phone", None), default="—")
    doy = _safe(getattr(winner, "doy", None), default="—")
    email = _safe(getattr(winner, "email", None), default="—")

    return (
        f"{name} με ΑΦΜ: {afm}, διεύθυνση: {address}, {city}, "
        f"τηλέφωνο: {phone}, Δ.Ο.Υ.: {doy}, email: {email}"
    )


def _resolve_proc_type(procurement: Any) -> str:
    """
    Resolve whether the procurement concerns services or goods.
    """
    materials = list(getattr(procurement, "materials", []) or [])
    is_services = any(bool(getattr(line, "is_service", False)) for line in materials)
    return "παροχής υπηρεσιών" if is_services else "προμήθειας υλικών"


def _resolve_committee_description(procurement: Any) -> str:
    """
    Resolve the linked committee identity text.

    SOURCE OF TRUTH
    ---------------
    ProcurementCommittee exposes both:
    - description
    - identity_text

    The user requested that the document must show the committee identity,
    therefore this field must resolve `identity_text`.
    """
    committee = getattr(procurement, "committee", None)
    if committee is None:
        return "—"
    return _safe(getattr(committee, "identity_text", None))


def _resolve_application_admin(service_unit: Any) -> str:
    """
    Resolve application administrator text.

    SOURCE OF TRUTH
    ---------------
    In the current ServiceUnit model:
    - curator = Διαχειριστής Εφαρμογής
    """
    return _safe(getattr(service_unit, "curator", None))


def _resolve_application_admin_directory(service_unit: Any) -> str:
    """
    Resolve the free-text application-admin directory field.

    SOURCE OF TRUTH
    ---------------
    In the current ServiceUnit model:
    - application_admin_directory = free-text ΔΙΕΥΘΥΝΣΗ
    """
    return _safe(getattr(service_unit, "application_admin_directory", None))


def _greek_enumeration_labels() -> list[str]:
    """
    Ordered Greek labels for the supporting-documents block.
    """
    return [
        "η.",
        "θ.",
        "ι.",
        "ια.",
        "ιβ.",
        "ιγ.",
        "ιδ.",
        "ιε.",
        "ιστ.",
        "ιζ.",
        "ιη.",
        "ιθ.",
        "κ.",
    ]


def _build_supporting_document_items(procurement: Any, analysis: dict[str, Any]) -> list[str]:
    """
    Build the supporting-document item texts according to the requested amount thresholds.
    """
    total_amount = _resolve_analysis_total(procurement, analysis)

    full_items = [
        f"Πρόσκληση Υποβολής Προσφοράς με {_safe(getattr(procurement, 'identity_prosklisis', None))}.",
        "Βεβαίωση ΙΒΑΝ.",
        "Υπεύθυνη δήλωση στοιχείων επικοινωνίας και τραπεζικών στοιχείων.",
        "Πιστοποιητικό Εκπροσώπησης.",
        "Υπεύθυνη Δήλωση μη υποχρέωσης ένταξης στο Εθνικό Μητρώο Παραγωγών.",
        "Υπεύθυνη Δήλωση μη δωροδοκίας.",
        "Αντίγραφο Ποινικού Μητρώου.",
        "Αποδεικτικό Φορολογικής Ενημερότητας.",
        "Αποδεικτικό Ασφαλιστικής Ενημερότητας.",
    ]

    if total_amount < Decimal("1500"):
        return [
            "Βεβαίωση ΙΒΑΝ.",
            "Υπεύθυνη δήλωση στοιχείων επικοινωνίας και τραπεζικών στοιχείων.",
        ]

    if total_amount < Decimal("2500"):
        return [
            "Βεβαίωση ΙΒΑΝ.",
            "Υπεύθυνη δήλωση στοιχείων επικοινωνίας και τραπεζικών στοιχείων.",
            "Αποδεικτικό Φορολογικής Ενημερότητας.",
        ]

    return full_items


# ---------------------------------------------------------------------------
# Supporting documents block rendering
# ---------------------------------------------------------------------------

def _find_reference_paragraph_for_supporting_block(doc: Document):
    """
    Find the paragraph that starts with 'ζ.' and use it as the formatting
    source for the generated supporting-documents block.
    """
    def _matches(paragraph) -> bool:
        text = (paragraph.text or "").strip()
        return text.startswith("ζ.")

    for paragraph in doc.paragraphs:
        if _matches(paragraph):
            return paragraph

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    if _matches(paragraph):
                        return paragraph

    return None


def _render_supporting_documents_block_in_paragraph(
    paragraph,
    items: list[str],
    formatting_source_paragraph=None,
) -> None:
    """
    Render supporting documents as consecutive paragraphs.

    The generated η./θ./ι./... paragraphs inherit paragraph formatting from
    paragraph 'ζ.' (tabs, alignment, spacing, line spacing, indentation).
    """
    labels = _greek_enumeration_labels()

    source_paragraph = formatting_source_paragraph or paragraph
    template_run = source_paragraph.runs[0] if source_paragraph.runs else (
        paragraph.runs[0] if paragraph.runs else None
    )

    _clear_paragraph_runs(paragraph)
    _clone_paragraph_properties(source_paragraph, paragraph)

    anchor = paragraph

    for idx, item in enumerate(items):
        if idx >= len(labels):
            raise ValueError("Not enough Greek enumeration labels for supporting documents block.")

        target = anchor if idx == 0 else _insert_paragraph_after(anchor)
        _clone_paragraph_properties(source_paragraph, target)

        run = target.add_run(f"\t\t{labels[idx]}\t{item}")
        _copy_run_style(template_run, run)

        anchor = target


def _render_supporting_documents_block(doc: Document, placeholder: str, items: list[str]) -> None:
    """
    Find the placeholder paragraph and replace it with the rendered block.

    The generated paragraphs inherit formatting from the paragraph that starts
    with 'ζ.'.
    """
    formatting_source_paragraph = _find_reference_paragraph_for_supporting_block(doc)

    for paragraph in doc.paragraphs:
        if placeholder in paragraph.text:
            _render_supporting_documents_block_in_paragraph(
                paragraph=paragraph,
                items=items,
                formatting_source_paragraph=formatting_source_paragraph,
            )
            return

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    if placeholder in paragraph.text:
                        _render_supporting_documents_block_in_paragraph(
                            paragraph=paragraph,
                            items=items,
                            formatting_source_paragraph=formatting_source_paragraph,
                        )
                        return


# ---------------------------------------------------------------------------
# Public report API
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExpenseTransmittalConstants:
    """
    Future-proof constants container.
    """
    pass


def build_expense_transmittal_docx(
    *,
    procurement: Any,
    service_unit: Any,
    winner: Optional[Any],
    analysis: dict[str, Any],
    constants: Optional[ExpenseTransmittalConstants] = None,
) -> bytes:
    """
    Build the expense transmittal DOCX as bytes.
    """
    _ = constants

    template_path = _template_path()
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    doc = Document(str(template_path))

    proc_type = _resolve_proc_type(procurement)
    winner_line = _winner_supplier_line(winner)
    ml_total = _resolve_document_total(procurement, analysis)
    ml_total_words = _money_words_el(_resolve_document_total_value(procurement, analysis))
    committee_description = _resolve_committee_description(procurement)
    application_admin = _resolve_application_admin(service_unit)
    application_admin_directory = _resolve_application_admin_directory(service_unit)
    supporting_items = _build_supporting_document_items(procurement, analysis)

    invoice_number = _safe(getattr(procurement, "invoice_number", None))
    invoice_date = _format_date(getattr(procurement, "invoice_date", None))
    invoice_receipt_date = _format_date(getattr(procurement, "invoice_receipt_date", None))
    identity_prosklisis = _safe(getattr(procurement, "identity_prosklisis", None))

    mapping: dict[str, str] = {
        "{{SERVICE_UNIT_NAME}}": _upper_service_name(
            _safe(getattr(service_unit, "description", None), default="—")
        ),
        "{{APPLICATION_ADMIN_DIRECTORY}}": application_admin_directory,
        "{{APPLICATION_ADMIN}}": application_admin,
        "{{SERVICE_UNIT_PHONE}}": _safe(getattr(service_unit, "phone", None)),
        "{{SERVICE_UNIT_REGION}}": _safe(getattr(service_unit, "region", None)),
        "{{SHORT_DATE}}": _short_date_el(),
        "{{PROC_TYPE}}": proc_type,
        "{{procurement.hop_approval}}": _safe(getattr(procurement, "hop_approval", None)),
        "{{procurement.hop_preapproval}}": _safe(getattr(procurement, "hop_preapproval", None)),
        "{{procurement. hop_preapproval}}": _safe(getattr(procurement, "hop_preapproval", None)),
        "{{procurement.aay}}": _safe(getattr(procurement, "aay", None)),
        "{{procurement.protocol_number}}": _safe(getattr(procurement, "protocol_number", None)),
        "{{procurement. protocol_number}}": _safe(getattr(procurement, "protocol_number", None)),
        "{{procurement.committee_description}}": committee_description,
        "{{WINNER_SUPPLIER_LINE}}": winner_line,
        "{{procurement.invoice_number}}": invoice_number,
        "{{procurement.invoice_date}}": invoice_date,
        "{{ML_TOTAL}}": ml_total,
        "{{ML_TOTAL_WORDS}}": ml_total_words,
        "{{procurement.invoice_receipt_date}}": invoice_receipt_date,
        "{{procurement.identity_prosklisis}}": identity_prosklisis,

        # Legacy placeholders retained defensively
        "{{ProcurementCommittee.description}}": committee_description,
        "{{procurement.invoice}}": invoice_number,
        "{{procurement.date}}": invoice_date,
        "{{MANAGER_SERVICE}}": application_admin,
    }

    _replace_placeholders_everywhere(doc, mapping)

    _render_supporting_documents_block(
        doc=doc,
        placeholder="{{SUPPORTING_DOCUMENTS_BLOCK}}",
        items=supporting_items,
    )

    _set_global_font_arial_12(doc)

    output = BytesIO()
    doc.save(output)
    return output.getvalue()


def build_expense_transmittal_filename(
    *,
    procurement: Any,
    winner: Optional[Any],
) -> str:
    """
    Build a readable output filename for the generated DOCX.
    """
    supplier_name = _safe(getattr(winner, "name", None), default="—")

    grand_total = getattr(procurement, "grand_total", None)
    if grand_total is None and hasattr(procurement, "compute_payment_analysis"):
        try:
            computed_analysis = procurement.compute_payment_analysis()
            grand_total = computed_analysis.get("payable_total")
        except Exception:
            grand_total = None

    total_str = _money_plain(grand_total)
    return f"Διαβιβαστικό Δαπάνης {supplier_name} {total_str}.docx"