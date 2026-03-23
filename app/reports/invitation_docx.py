"""
app/reports/invitation_docx.py

Generate "ΠΡΟΣΚΛΗΣΗ" as DOCX bytes using a Word template and placeholder
replacement.

SOURCE OF TRUTH
---------------
This implementation is aligned to:
- current uploaded `invitation_template.docx`
- current Procurement / ServiceUnit / Supplier related models

IMPORTANT TABLE RULE
--------------------
The invitation document must render the materials/services table with:
- one document row per procurement line
- not multiline text packed into a single row

BUSINESS RULE
-------------
The document switches wording dynamically between:
- παροχή υπηρεσιών
- προμήθεια υλικών

Canonical project rule:
- if any procurement material line has `is_service == True`
  -> services wording
- otherwise
  -> goods/materials wording

KNOWN MODEL LIMITATIONS
-----------------------
The current source-of-truth models do NOT provide dedicated fields for:
- explicit service-unit place for signing/sending
- richer recipient metadata beyond supplier fields already present

Therefore:
- {{SERVICE_UNIT_PLACE}} resolves conservatively to "—"
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH

from .common.amounts import money_plain
from .common.docx_utils import (
    clear_table_body_keep_header,
    replace_placeholders_everywhere,
    set_cell_alignment,
    set_global_font_arial_12,
)
from .common.domain import (
    economic_operator_label,
    invited_suppliers_inline,
    recipients_block,
    resolve_proc_type_lower,
)
from .common.formatting import (
    lower_preserve_accents,
    safe_text,
    short_date_el,
    upper_no_accents,
)


def _template_path() -> Path:
    """
    Resolve the DOCX template path for the invitation document.
    """
    app_dir = Path(__file__).resolve().parents[1]
    return app_dir / "templates" / "docx" / "invitation_template.docx"


def _resolve_handler_directory(procurement: Any) -> str:
    """
    Invitation requires uppercase handler directory rendering.
    """
    assignment = getattr(procurement, "handler_assignment", None)
    if assignment is not None:
        directory = getattr(assignment, "directory", None)
        if directory is not None:
            return upper_no_accents(getattr(directory, "name", None))

    handler = getattr(procurement, "handler_personnel", None)
    directory = getattr(handler, "directory", None)
    return upper_no_accents(getattr(directory, "name", None))


def _resolve_service_unit_place(service_unit: Any) -> str:
    """
    Current source-of-truth does not provide a dedicated invitation place field.
    """
    _ = service_unit
    return "—"


def _find_invitation_table(doc: Document):
    """
    Find the main invitation materials/services table.

    Expected shape in current template:
    - 5 columns
    - header includes:
      Α/Α | ΠΕΡΙΓΡΑΦΗ | ΜΟΝ. ΜΕΤ. | ΣΥΝΟΛΙΚΗ ΠΟΣΟΤΗΤΑ | CPV
    """
    for table in doc.tables:
        if len(table.columns) != 5 or not table.rows:
            continue

        header = " ".join(cell.text.strip() for cell in table.rows[0].cells).upper()
        if (
            "Α/Α" in header
            and "ΠΕΡΙΓΡΑΦΗ" in header
            and "ΜΟΝ. ΜΕΤ." in header
            and "ΣΥΝΟΛΙΚΗ ΠΟΣΟΤΗΤΑ" in header
            and "CPV" in header
        ):
            return table

    return None


def _sorted_materials(procurement: Any) -> list[Any]:
    """
    Preserve source ordering by default.
    """
    return list(getattr(procurement, "materials", []) or [])


def _fill_invitation_table(table, procurement: Any) -> None:
    """
    Fill the invitation lines table with one row per procurement material line.
    """
    clear_table_body_keep_header(table, header_rows=1)

    lines = _sorted_materials(procurement)

    if not lines:
        row = table.add_row().cells
        row[0].text = "—"
        row[1].text = "Δεν υπάρχουν γραμμές υλικών/υπηρεσιών."
        row[2].text = "—"
        row[3].text = "—"
        row[4].text = "—"
        for cell in row:
            set_cell_alignment(cell)
        return

    for idx, line in enumerate(lines, start=1):
        row = table.add_row().cells
        row[0].text = str(idx)
        row[1].text = safe_text(getattr(line, "description", None))
        row[2].text = safe_text(getattr(line, "unit", None))

        qty_value = getattr(line, "quantity", None)
        row[3].text = money_plain(qty_value) if qty_value is not None else "—"

        row[4].text = safe_text(getattr(line, "cpv", None))

        set_cell_alignment(row[0])
        set_cell_alignment(row[1], horizontal=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_alignment(row[2])
        set_cell_alignment(row[3])
        set_cell_alignment(row[4])


@dataclass(frozen=True)
class InvitationConstants:
    """
    Future-proof constants container for invitation generation.
    """
    pass


def build_invitation_docx(
    *,
    procurement: Any,
    service_unit: Any,
    winner: Optional[Any],
    analysis: dict[str, Any],
    constants: Optional[InvitationConstants] = None,
) -> bytes:
    """
    Build the invitation DOCX and return it as bytes.
    """
    _ = winner
    _ = analysis
    _ = constants

    template_path = _template_path()
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    doc = Document(str(template_path))

    mapping: dict[str, str] = {
        "{{SERVICE_UNIT_NAME}}": upper_no_accents(getattr(service_unit, "description", None)),
        "{{SERVICE_UNIT_DESCRIPTION}}": safe_text(getattr(service_unit, "description", None)),
        "{{PROCUREMENT_SHORT_DESCRIPTION}}": lower_preserve_accents(
            getattr(procurement, "description", None)
        ),
        "{{HANDLER_DIRECTORY}}": _resolve_handler_directory(procurement),
        "{{SERVICE_UNIT_PHONE}}": safe_text(getattr(service_unit, "phone", None)),
        "{{ SERVICE_UNIT_PHONE}}": safe_text(getattr(service_unit, "phone", None)),
        "{{SERVICE_UNIT_REGION}}": safe_text(getattr(service_unit, "region", None)),
        "{{SHORT_DATE}}": short_date_el(),
        "{{PROC_TYPE}}": resolve_proc_type_lower(procurement),
        "{{ECONOMIC_OPERATOR_LABEL}}": economic_operator_label(procurement),
        "{{procurement.aay}}": safe_text(getattr(procurement, "aay", None)),
        "{{procurement.adam_aay}}": safe_text(getattr(procurement, "adam_aay", None)),
        "{{procurement hop_approval_commitment}}": safe_text(
            getattr(procurement, "hop_approval_commitment", None)
        ),
        "{{INVITED_SUPPLIERS_INLINE}}": invited_suppliers_inline(procurement),
        "{{RECIPIENTS_INFO}}": recipients_block(procurement),
        "{{WINNER_SUPPLIER_LINE}}": invited_suppliers_inline(procurement),
        "{{SERVICE_UNIT_ADRESS}}": safe_text(getattr(service_unit, "address", None)),
        "{{ SERVICE_UNIT_ADRESS}}": safe_text(getattr(service_unit, "address", None)),
        "{{SERVICE_UNIT_PLACE}}": _resolve_service_unit_place(service_unit),
        "{{SERVICE_UNIT_POSTAL_CODE}}": safe_text(getattr(service_unit, "postal_code", None)),
        "{{ SERVICE_UNIT_EMAIL}}": safe_text(getattr(service_unit, "email", None)),
        "{{SERVICE_UNIT_EMAIL}}": safe_text(getattr(service_unit, "email", None)),
        "{{service.commander}}": safe_text(getattr(service_unit, "commander", None)),
        "{{COMMANDER_ROLE_TYPE}}": safe_text(getattr(service_unit, "commander_role_type", None)),
        "{{ML_NO}}": "",
        "{{ML_DESC}}": "",
        "{{ML_UNIT}}": "",
        "{{ML_QTY}}": "",
        "{{ML_CPV}}": "",
    }

    replace_placeholders_everywhere(doc, mapping)

    invitation_table = _find_invitation_table(doc)
    if invitation_table is not None:
        _fill_invitation_table(invitation_table, procurement)

    set_global_font_arial_12(doc)

    output = BytesIO()
    doc.save(output)
    return output.getvalue()


def build_invitation_filename(
    *,
    procurement: Any,
    winner: Optional[Any],
) -> str:
    """
    Build a human-readable filename for the generated invitation document.
    """
    _ = winner

    description = safe_text(
        getattr(procurement, "description", None),
        default=f"Προμήθεια #{getattr(procurement, 'id', '—')}",
    )
    return f"Πρόσκληση Υποβολής Προσφοράς για την {description}.docx"