"""
Shared low-level DOCX helpers for report generation.

This module centralizes:
- placeholder replacement across split runs
- header/footer replacement
- paragraph insertion/cloning
- common font normalization
- table cleanup / alignment helpers
"""

from __future__ import annotations

from copy import deepcopy
from typing import Iterable

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.shared import Pt


def set_global_font_arial_12(doc: Document) -> None:
    """
    Normalize generated document font to Arial 12 where possible.

    This keeps current behavior consistent with the existing report modules.
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

    for section in doc.sections:
        containers = [
            section.header,
            section.footer,
            section.first_page_header,
            section.first_page_footer,
            section.even_page_header,
            section.even_page_footer,
        ]

        for container in containers:
            if container is None:
                continue

            for paragraph in container.paragraphs:
                for run in paragraph.runs:
                    run.font.name = "Arial"
                    run.font.size = Pt(12)

            for table in container.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                run.font.name = "Arial"
                                run.font.size = Pt(12)


def paragraph_runs_text(paragraph) -> tuple[str, list[tuple[int, int, int]]]:
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


def find_run_index_at_offset(positions: list[tuple[int, int, int]], offset: int) -> int:
    """
    Find the run index containing the given character offset.
    """
    for run_index, start, end in positions:
        if start <= offset < end:
            return run_index

    if positions and offset == positions[-1][2]:
        return positions[-1][0]

    return -1


def replace_placeholder_once_in_paragraph(paragraph, placeholder: str, replacement: str) -> bool:
    """
    Replace one occurrence of a placeholder in a paragraph, even if it is split
    across multiple runs.

    The replacement text inherits the style of the first participating run.
    """
    full_text, positions = paragraph_runs_text(paragraph)
    if not full_text or placeholder not in full_text:
        return False

    start = full_text.find(placeholder)
    end = start + len(placeholder)

    start_run_idx = find_run_index_at_offset(positions, start)
    end_run_idx = find_run_index_at_offset(positions, end - 1)

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


def replace_placeholder_all_in_paragraph(paragraph, placeholder: str, replacement: str) -> None:
    """
    Replace all occurrences of a placeholder in a paragraph, robustly across runs.
    """
    while replace_placeholder_once_in_paragraph(paragraph, placeholder, replacement):
        pass


def replace_placeholders_everywhere(doc: Document, mapping: dict[str, str]) -> None:
    """
    Replace placeholders across all document paragraphs and table paragraphs.
    """
    for paragraph in doc.paragraphs:
        for placeholder, replacement in mapping.items():
            replace_placeholder_all_in_paragraph(paragraph, placeholder, replacement)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for placeholder, replacement in mapping.items():
                        replace_placeholder_all_in_paragraph(paragraph, placeholder, replacement)


def replace_placeholders_in_headers_and_footers(doc: Document, mapping: dict[str, str]) -> None:
    """
    Replace placeholders in all header/footer variants for every section:
    - default header/footer
    - first-page header/footer
    - even-page header/footer
    """
    for section in doc.sections:
        containers = [
            section.header,
            section.footer,
            section.first_page_header,
            section.first_page_footer,
            section.even_page_header,
            section.even_page_footer,
        ]

        for container in containers:
            if container is None:
                continue

            for paragraph in container.paragraphs:
                for placeholder, replacement in mapping.items():
                    replace_placeholder_all_in_paragraph(paragraph, placeholder, replacement)

            for table in container.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            for placeholder, replacement in mapping.items():
                                replace_placeholder_all_in_paragraph(paragraph, placeholder, replacement)


def replace_literal_text_everywhere(doc: Document, replacements: dict[str, str]) -> None:
    """
    Replace literal fallback text in document body paragraphs and table cells.

    This is kept for backward compatibility with older templates that still
    contain slash-based wording instead of explicit placeholders.
    """
    for paragraph in doc.paragraphs:
        original = paragraph.text or ""
        updated = original
        for src, dst in replacements.items():
            if src in updated:
                updated = updated.replace(src, dst)
        if updated != original:
            paragraph.text = updated

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    original = paragraph.text or ""
                    updated = original
                    for src, dst in replacements.items():
                        if src in updated:
                            updated = updated.replace(src, dst)
                    if updated != original:
                        paragraph.text = updated


def clear_table_body_keep_header(table, header_rows: int = 1) -> None:
    """
    Remove all table rows after the given header row count.
    """
    while len(table.rows) > header_rows:
        tbl = table._tbl
        tr = table.rows[header_rows]._tr
        tbl.remove(tr)


def set_cell_alignment(
    cell,
    *,
    horizontal: WD_ALIGN_PARAGRAPH = WD_ALIGN_PARAGRAPH.CENTER,
    vertical: WD_ALIGN_VERTICAL = WD_ALIGN_VERTICAL.CENTER,
) -> None:
    """
    Apply horizontal and vertical alignment to every paragraph in a cell.
    """
    cell.vertical_alignment = vertical
    for paragraph in cell.paragraphs:
        paragraph.alignment = horizontal


def clone_paragraph_properties(src_paragraph, dst_paragraph) -> None:
    """
    Clone paragraph properties XML including tabs, indents, spacing and alignment.
    """
    dst_p = dst_paragraph._p
    src_p = src_paragraph._p

    if dst_p.pPr is not None:
        dst_p.remove(dst_p.pPr)

    if src_p.pPr is not None:
        dst_p.insert(0, deepcopy(src_p.pPr))


def copy_run_style(src_run, dst_run) -> None:
    """
    Copy run-level style from one run to another.
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


def insert_paragraph_after(paragraph):
    """
    Insert and return a new paragraph immediately after the given paragraph.
    """
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    return paragraph._parent.add_paragraph().__class__(new_p, paragraph._parent)


def clear_paragraph_runs(paragraph) -> None:
    """
    Remove all runs from a paragraph while preserving paragraph properties.
    """
    p = paragraph._p
    for child in list(p):
        if child.tag.endswith("}r") or child.tag.endswith("}hyperlink"):
            p.remove(child)


def iter_document_paragraphs(doc: Document) -> Iterable:
    """
    Yield all body paragraphs and all table-cell paragraphs in document order blocks.

    This helper is useful for search-style traversal where body + tables are both
    valid search locations.
    """
    for paragraph in doc.paragraphs:
        yield paragraph

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    yield paragraph


__all__ = [
    "set_global_font_arial_12",
    "paragraph_runs_text",
    "find_run_index_at_offset",
    "replace_placeholder_once_in_paragraph",
    "replace_placeholder_all_in_paragraph",
    "replace_placeholders_everywhere",
    "replace_placeholders_in_headers_and_footers",
    "replace_literal_text_everywhere",
    "clear_table_body_keep_header",
    "set_cell_alignment",
    "clone_paragraph_properties",
    "copy_run_style",
    "insert_paragraph_after",
    "clear_paragraph_runs",
    "iter_document_paragraphs",
]