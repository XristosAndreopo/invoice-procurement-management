"""
app/reports/contract_docx.py

Generate "ΣΥΜΒΑΣΗ" as DOCX bytes using the provided Word template
`contact_template.docx`.

SOURCE OF TRUTH
---------------
This implementation is aligned to:
- combined_project.md
- current uploaded `contact_template.docx`
- current Procurement / ServiceUnit / Supplier / Organization models
- current payment-analysis service

IMPORTANT BUSINESS RULE
-----------------------
The document switches wording dynamically between:
- υπηρεσίες
- υλικά

Canonical project rule:
- if any procurement material line has `is_service == True`
  -> services contract
- otherwise
  -> goods/materials contract

TEMPLATE CONTRACT
-----------------
This implementation supports:
1. explicit placeholders such as:
   - {{CONTRACT_KIND_TITLE}}
   - {{TABLE_REFERENCE_PHRASE}}
   - {{DELIVERY_SENTENCE}}
   - {{DEADLINE_PHRASE}}
   - {{COMPLETION_PHRASE}}
   - {{NONCONFORMITY_SUBJECT}}
   - {{TABLE_TITLE}}
   - {{VAT_SENTENCE}}
   - {{PROC_TYPE_LOWER}}
   - {{DELIVERY_TO_SERVICE_SENTENCE}}

2. legacy / typo placeholders kept for backward compatibility, such as:
   - {{WINNER_SUPPLIER_DESCREIPTION}}
   - {{PROCUREMENT_INDENTITY_PROSKLISIS}}
   - {{PROCUREMENT_INDENTITY_APOFASIS_ANATHESIS}}

KNOWN MODEL LIMITATIONS
-----------------------
The current source-of-truth models do NOT provide dedicated fields for:
- supplier legal representative name
- representative ID card number
- dedicated contract signing place
- explicit contract delivery deadline date

Therefore:
- {{SERVICE_UNIT_PLACE}} resolves conservatively to:
  service_unit.region -> service_unit.prefecture -> "—"
- legal-representative free text remains template-owned if present outside
  placeholders
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH

from .common.amounts import money_plain, money_words_el, percent, to_decimal
from .common.docx_utils import (
    clear_table_body_keep_header,
    replace_literal_text_everywhere,
    replace_placeholders_everywhere,
    replace_placeholders_in_headers_and_footers,
    set_cell_alignment,
    set_global_font_arial_12,
)
from .common.domain import (
    resolve_document_total,
    resolve_document_total_value,
    resolve_handler_directory,
    resolve_is_services,
    resolve_service_unit_place,
)
from .common.formatting import safe_text, upper_service_name
from .instrumentation import ReportInstrumentation


def _timed(
    instrumentation: Optional[ReportInstrumentation],
    detail_name: str,
    **extra: Any,
):
    if instrumentation is None:
        return nullcontext()
    return instrumentation.timed_detail(detail_name, **extra)


def _template_path() -> Path:
    """
    Resolve the DOCX template path for the contract document.
    """
    app_dir = Path(__file__).resolve().parents[1]
    return app_dir / "templates" / "docx" / "contact_template.docx"


def _resolve_proc_type(is_services: bool) -> str:
    return "ΠΑΡΟΧΗΣ ΥΠΗΡΕΣΙΩΝ" if is_services else "ΠΡΟΜΗΘΕΙΑΣ ΥΛΙΚΩΝ"


def _resolve_proc_type_lower(is_services: bool) -> str:
    return "παροχή υπηρεσιών" if is_services else "προμήθεια υλικών"


def _resolve_contract_kind_title(is_services: bool) -> str:
    return "Παροχής Υπηρεσιών" if is_services else "Προμήθειας Υλικών"


def _resolve_table_title(is_services: bool) -> str:
    return (
        "ΠΙΝΑΚΑΣ ΠΑΡΟΧΗΣ ΥΠΗΡΕΣΙΩΝ"
        if is_services
        else "ΠΙΝΑΚΑΣ ΥΠΟ ΠΡΟΜΗΘΕΙΑ ΥΛΙΚΩΝ"
    )


def _resolve_table_reference_phrase(is_services: bool) -> str:
    return (
        "πίνακα παρεχόμενων υπηρεσιών"
        if is_services
        else "πίνακα υπό προμήθεια υλικών"
    )


def _resolve_delivery_sentence(is_services: bool) -> str:
    return (
        "Οι υπηρεσίες θα παρασχεθούν"
        if is_services
        else "Τα υπό προμήθεια υλικά θα παραδοθούν"
    )


def _resolve_delivery_to_service_sentence(is_services: bool) -> str:
    return (
        "Οι υπηρεσίες θα εκτελεστούν"
        if is_services
        else "Τα υλικά θα παραδοθούν στην υπηρεσία"
    )


def _resolve_deadline_phrase(is_services: bool) -> str:
    return "εκτέλεσης εργασιών" if is_services else "παράδοσης των υλικών"


def _resolve_completion_phrase(is_services: bool) -> str:
    return "εκτέλεσης εργασιών" if is_services else "παράδοσης υλικών"


def _resolve_nonconformity_subject(is_services: bool) -> str:
    return "οι παρεχόμενες υπηρεσίες" if is_services else "τα υπό προμήθεια υλικά"


def _resolve_item_label_plural(is_services: bool) -> str:
    return "υπηρεσιών" if is_services else "υλικών"


def _resolve_vat_sentence(analysis: dict[str, Any], is_services: bool) -> str:
    vat_percent = to_decimal(analysis.get("vat_percent", 0)).quantize(to_decimal("0.01"))
    subject = "παρεχόμενων υπηρεσιών" if is_services else "υπό προμήθεια υλικών"

    if vat_percent == to_decimal("0.00"):
        return f"Η τιμή των {subject} απαλλάσσεται Φόρου Προστιθέμενης Αξίας (Φ.Π.Α.)."

    return (
        f"Η τιμή των {subject} επιβαρύνεται με {percent(vat_percent)}% "
        "Φόρου Προστιθέμενης Αξίας (Φ.Π.Α.)."
    )


def _winner_supplier_name(winner: Any) -> str:
    return safe_text(getattr(winner, "name", None), default="—")


def _winner_supplier_afm(winner: Any) -> str:
    return safe_text(getattr(winner, "afm", None), default="—")


def _winner_supplier_emba(winner: Any) -> str:
    return safe_text(getattr(winner, "emba", None), default="—")


def _resolve_krathseis_label(analysis: dict[str, Any]) -> str:
    public_withholdings = analysis.get("public_withholdings") or {}
    return f"{percent(public_withholdings.get('total_percent', 0))}%"


def _resolve_fe_label(analysis: dict[str, Any]) -> str:
    income_tax = analysis.get("income_tax") or {}
    return percent(income_tax.get("rate_percent", 0))


def _resolve_fpa_label(analysis: dict[str, Any]) -> str:
    return f"{percent(analysis.get('vat_percent', 0))}%"


def _find_contract_table(doc: Document):
    """
    Find the main contract pricing table.

    Current expected shape:
    - 6 columns
    - header includes: ΠΕΡΙΓΡΑΦΗ, ΤΙΜΗ, ΣΥΝΟΛΟ
    """
    for table in doc.tables:
        if len(table.columns) != 6 or not table.rows:
            continue

        header = " ".join(cell.text for cell in table.rows[0].cells).upper()
        if "ΠΕΡΙΓΡΑΦΗ" in header and "ΤΙΜΗ" in header and "ΣΥΝΟΛΟ" in header:
            return table

    return None


def _add_summary_row(table, label: str, amount: Any) -> None:
    """
    Add one merged summary row to the contract pricing table.
    """
    row = table.add_row().cells
    merged = row[0].merge(row[4])
    merged.text = label
    row[5].text = money_plain(amount)

    set_cell_alignment(
        merged,
        horizontal=WD_ALIGN_PARAGRAPH.RIGHT,
        vertical=WD_ALIGN_VERTICAL.CENTER,
    )
    set_cell_alignment(
        row[5],
        horizontal=WD_ALIGN_PARAGRAPH.CENTER,
        vertical=WD_ALIGN_VERTICAL.CENTER,
    )


def _fill_contract_table(table, procurement: Any, analysis: dict[str, Any]) -> None:
    """
    Fill the main contract pricing table and append summary rows.
    """
    clear_table_body_keep_header(table, header_rows=1)

    lines = list(getattr(procurement, "materials", []) or [])

    if not lines:
        row = table.add_row().cells
        row[0].text = "—"
        row[1].text = "Δεν υπάρχουν γραμμές υλικών/υπηρεσιών."
        row[2].text = "—"
        row[3].text = "—"
        row[4].text = "—"
        row[5].text = "—"
        for cell in row:
            set_cell_alignment(cell)
        return

    for idx, line in enumerate(lines, start=1):
        row = table.add_row().cells
        row[0].text = str(idx)
        row[1].text = safe_text(getattr(line, "description", None), default="")
        row[2].text = safe_text(getattr(line, "unit", None))
        row[3].text = safe_text(getattr(line, "quantity", None))
        row[4].text = money_plain(getattr(line, "unit_price", None))
        row[5].text = money_plain(getattr(line, "total_pre_vat", None))

        for cell in row:
            set_cell_alignment(cell)

    public_withholdings = analysis.get("public_withholdings") or {}
    income_tax = analysis.get("income_tax") or {}

    _add_summary_row(table, "Μερικό Σύνολο", analysis.get("sum_total", 0))
    _add_summary_row(
        table,
        f"Κρατήσεις Υπέρ Δημοσίου ({percent(public_withholdings.get('total_percent', 0))}%)",
        public_withholdings.get("total_amount", 0),
    )
    _add_summary_row(
        table,
        f"Φόρος Εισοδήματος ({percent(income_tax.get('rate_percent', 0))}%)",
        income_tax.get("amount", 0),
    )
    _add_summary_row(
        table,
        f"ΦΠΑ ({percent(analysis.get('vat_percent', 0))}%)",
        analysis.get("vat_amount", 0),
    )
    _add_summary_row(table, "Τελικό Σύνολο", analysis.get("payable_total", 0))


def _apply_legacy_goods_services_wording(
    doc: Document,
    *,
    is_services: bool,
    analysis: dict[str, Any],
) -> None:
    """
    Defensive fallback for older template versions that still contain slash
    wording instead of explicit placeholders.
    """
    replacements = {
        "Παροχής Υπηρεσιών/Προμήθειας Υλικών": _resolve_contract_kind_title(is_services),
        "πίνακα παρεχόμενων υπηρεσιών/υπό προμήθεια υλικών": _resolve_table_reference_phrase(
            is_services
        ),
        "πίνακα παρεχόμενων υπηρεσιών/προμηθευτέων υλικών": _resolve_table_reference_phrase(
            is_services
        ),
        "Οι υπηρεσίες θα παρασχεθούν/Τα υπό προμήθεια υλικά θα παραδοθούν":
            _resolve_delivery_sentence(is_services),
        "Τα υλικά θα παραδοθούν στην υπηρεσία /Οι υπηρεσίες θα εκτελεστούν":
            _resolve_delivery_to_service_sentence(is_services),
        "Τα υλικά θα παραδοθούν στην υπηρεσία/Οι υπηρεσίες θα εκτελεστούν":
            _resolve_delivery_to_service_sentence(is_services),
        "παράδοσης των υλικών/εκτέλεσης εργασιών": _resolve_deadline_phrase(is_services),
        "παράδοσης υλικών/εκτέλεσης εργασιών": _resolve_completion_phrase(is_services),
        "τα υπό προμήθεια υλικά/οι παρεχόμενες υπηρεσίες": _resolve_nonconformity_subject(
            is_services
        ),
        "ΠΙΝΑΚΑΣ ΠΑΡΟΧΗΣ ΥΠΗΡΕΣΙΩΝ/ΥΠΟ ΠΡΟΜΗΘΕΙΑ ΥΛΙΚΩΝ": _resolve_table_title(is_services),
        "ΠΡΟΜΗΘΕΙΑΣ ΥΛΙΚΩΝ/ΠΑΡΟΧΗΣ ΥΠΗΡΕΣΙΩΝ": _resolve_proc_type(is_services),
        "προμήθειας υλικών/παροχής υπηρεσιών": _resolve_proc_type_lower(is_services),
        "προμήθειας υλικών / παροχής υπηρεσιών": _resolve_proc_type_lower(is_services),
        "Η τιμή των παρεχόμενων υπηρεσιών/προμηθευτέων υλικών απαλλάσσεται Φόρου Προστιθέμενης Αξίας (Φ.Π.Α.)/ επιβαρύνεται με {{PROCUREMENT_FPA}} Φόρου Προστιθέμενης Αξίας (Φ.Π.Α.).":
            _resolve_vat_sentence(analysis, is_services),
        "Η τιμή των παρεχόμενων υπηρεσιών/προμηθυτέων υλικών απαλλάσσεται Φόρου Προστιθέμενης Αξίας (Φ.Π.Α.)/ επιβαρύνεται με {{PROCUREMENT_FPA}} Φόρου Προστιθέμενης Αξίας (Φ.Π.Α.).":
            _resolve_vat_sentence(analysis, is_services),
        "Επί της καθαρής αξίας των υπηρεσιών υπολογίζονται κρατήσεις":
            f"Επί της καθαρής αξίας των {_resolve_item_label_plural(is_services)} υπολογίζονται κρατήσεις",
    }

    replace_literal_text_everywhere(doc, replacements)


@dataclass(frozen=True)
class ContractConstants:
    """
    Future-proof constants container for contract report generation.
    """
    pass


def build_contract_docx(
    *,
    procurement: Any,
    service_unit: Any,
    winner: Optional[Any],
    analysis: dict[str, Any],
    constants: Optional[ContractConstants] = None,
    instrumentation: Optional[ReportInstrumentation] = None,
) -> bytes:
    """
    Build the contract DOCX and return it as bytes.
    """
    _ = constants

    template_path = _template_path()
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    with _timed(instrumentation, "load_template"):
        doc = Document(str(template_path))

    is_services = resolve_is_services(procurement)

    with _timed(instrumentation, "build_mapping"):
        mapping: dict[str, str] = {
            "{{SERVICE_UNIT_NAME}}": upper_service_name(
                safe_text(getattr(service_unit, "description", None), default="—")
            ),
            "{{HANDLER_DIRECTORY}}": resolve_handler_directory(procurement, uppercase=True),
            "{{SERVICE_UNIT_PHONE}}": safe_text(getattr(service_unit, "phone", None)),
            "{{PROC_TYPE}}": _resolve_proc_type(is_services),
            "{{PROC_TYPE_LOWER}}": _resolve_proc_type_lower(is_services),
            "{{PROCUREMENT_CONTRACT_NUMBER}}": safe_text(getattr(procurement, "contract_number", None)),
            "{{WINNER_SUPPLIER_AFM}}": _winner_supplier_afm(winner),
            "{{ WINNER_SUPPLIER_AFM}}": _winner_supplier_afm(winner),
            "{{WINNER_SUPPLIER_DESCRIPTION}}": _winner_supplier_name(winner),
            "{{WINNER_SUPPLIER_DESCREIPTION}}": _winner_supplier_name(winner),
            "{{WINNER_SUPPLIER_EMBA}}": _winner_supplier_emba(winner),
            "{{PROCUREMENT_HOP_APPROVAL}}": safe_text(getattr(procurement, "hop_approval", None)),
            "{{PROCUREMENT_AAY}}": safe_text(getattr(procurement, "aay", None)),
            "{{PROCUREMENT_ADAM_AAY}}": safe_text(getattr(procurement, "adam_aay", None)),
            "{{PROCUREMENT_ADA_AAY}}": safe_text(getattr(procurement, "ada_aay", None)),
            "{{PROCUREMENT_IDENTITY_PROSKLISIS}}": safe_text(
                getattr(procurement, "identity_prosklisis", None)
            ),
            "{{PROCUREMENT_INDENTITY_PROSKLISIS}}": safe_text(
                getattr(procurement, "identity_prosklisis", None)
            ),
            "{{PROCUREMENT_ADAM_PROSKLISIS}}": safe_text(
                getattr(procurement, "adam_prosklisis", None)
            ),
            "{{ PROCUREMENT_ADAM_PROSKLISIS}}": safe_text(
                getattr(procurement, "adam_prosklisis", None)
            ),
            "{{PROCUREMENT_IDENTITY_APOFASIS_ANATHESIS}}": safe_text(
                getattr(procurement, "identity_apofasis_anathesis", None)
            ),
            "{{PROCUREMENT_INDENTITY_APOFASIS_ANATHESIS}}": safe_text(
                getattr(procurement, "identity_apofasis_anathesis", None)
            ),
            "{{PROCUREMENT_ADAM_APOFASIS_ANATHESIS}}": safe_text(
                getattr(procurement, "adam_apofasis_anathesis", None)
            ),
            "{{SERVICE_UNIT_PLACE}}": resolve_service_unit_place(service_unit),
            "{{COMMANDER_ROLE_TYPE}}": safe_text(getattr(service_unit, "commander_role_type", None)),
            "{{SERVICE_COMMANDER}}": safe_text(getattr(service_unit, "commander", None)),
            "{{SERVICE_UNIT_COMMANDER}}": safe_text(getattr(service_unit, "commander", None)),
            "{{SERVICE.AAHT}}": safe_text(getattr(service_unit, "aahit", None)),
            "{{PROCUREMENT_ALE}}": safe_text(getattr(procurement, "ale", None)),
            "{{CURRENT_YEAR}}": str(getattr(procurement, "fiscal_year", None) or ""),
            "{{ML_TOTAL_WORDS}}": money_words_el(resolve_document_total_value(procurement, analysis)),
            "{{ML_TOTAL}}": resolve_document_total(procurement, analysis),
            "{{PROCUREMENT_KRATHSEIS_SYNOLO}}": _resolve_krathseis_label(analysis),
            "{{PROCUREMENT_FE}}": _resolve_fe_label(analysis),
            "{{PROCUREMENT_FPA}}": _resolve_fpa_label(analysis),
            "{{AN_SUM_TOTAL}}": money_plain(analysis.get("sum_total", 0)),
            "{{VAT_SENTENCE}}": _resolve_vat_sentence(analysis, is_services),
            "{{CONTRACT_KIND_TITLE}}": _resolve_contract_kind_title(is_services),
            "{{TABLE_REFERENCE_PHRASE}}": _resolve_table_reference_phrase(is_services),
            "{{DELIVERY_SENTENCE}}": _resolve_delivery_sentence(is_services),
            "{{DELIVERY_TO_SERVICE_SENTENCE}}": _resolve_delivery_to_service_sentence(is_services),
            "{{DEADLINE_PHRASE}}": _resolve_deadline_phrase(is_services),
            "{{COMPLETION_PHRASE}}": _resolve_completion_phrase(is_services),
            "{{NONCONFORMITY_SUBJECT}}": _resolve_nonconformity_subject(is_services),
            "{{TABLE_TITLE}}": _resolve_table_title(is_services),
        }

    with _timed(instrumentation, "replace_placeholders_body", placeholders=len(mapping)):
        replace_placeholders_everywhere(doc, mapping)

    with _timed(instrumentation, "replace_headers_footers", placeholders=len(mapping)):
        replace_placeholders_in_headers_and_footers(doc, mapping)

    with _timed(instrumentation, "apply_legacy_wording"):
        _apply_legacy_goods_services_wording(doc, is_services=is_services, analysis=analysis)

    with _timed(instrumentation, "locate_tables", materials_count=len(list(getattr(procurement, "materials", []) or []))):
        contract_table = _find_contract_table(doc)

    if contract_table is not None:
        with _timed(
            instrumentation,
            "fill_contract_table",
            materials_count=len(list(getattr(procurement, "materials", []) or [])),
        ):
            _fill_contract_table(contract_table, procurement, analysis)

    with _timed(instrumentation, "set_global_font"):
        set_global_font_arial_12(doc)

    with _timed(instrumentation, "save_docx"):
        output = BytesIO()
        doc.save(output)

    return output.getvalue()


def build_contract_filename(
    *,
    procurement: Any,
    winner: Optional[Any],
    is_services: bool,
) -> str:
    """
    Build a human-readable filename for the generated contract document.
    """
    kind = "Παροχής Υπηρεσιών" if is_services else "Προμήθειας Υλικών"
    supplier_name = safe_text(getattr(winner, "name", None), default="—")
    total_str = resolve_document_total(procurement, {})

    return f"Σύμβαση {kind} {supplier_name} {total_str}.docx"