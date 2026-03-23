"""
Shared low-level DOCX helpers for report generation.

This module centralizes:
- placeholder replacement across split runs
- header/footer replacement
- paragraph insertion/cloning
- common font normalization
- table cleanup / alignment helpers

PERFORMANCE NOTES
-----------------
The DOCX report builders rely heavily on placeholder replacement.

The original implementation performed a full nested traversal:
- for every paragraph
- for every placeholder in the mapping
- with repeated run-aware replacement attempts

That approach is functionally correct but expensive for large templates because
most paragraphs do not contain placeholders, and the majority of placeholders do
not exist in any given paragraph.

The optimized implementation below preserves the public API and rendering
behavior while reducing unnecessary work by:

1. Quickly skipping paragraphs that do not contain the placeholder sentinel
   `{{`.
2. Pre-scanning each candidate paragraph to discover only the placeholders that
   are actually present.
3. Replacing only those discovered placeholders.
4. Keeping the same split-run replacement logic so placeholders broken across
   multiple runs still work exactly as before.

IMPORTANT COMPATIBILITY RULE
----------------------------
This file is intentionally implemented as a low-risk performance patch:
- function names stay the same
- signatures stay the same
- call sites do not need to change
- split-run placeholder support is preserved
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Iterable

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.shared import Pt

# Fast sentinel used to skip paragraphs/cells that obviously do not contain
# placeholders.
_PLACEHOLDER_SENTINEL = "{{"

# Extract placeholder-like tokens from paragraph text.
#
# The current template contract uses placeholders such as:
#   {{FIELD_NAME}}
#
# We intentionally keep this pattern conservative and literal so we can:
# - avoid scanning the entire mapping for every paragraph
# - preserve compatibility with the existing placeholder convention
#
# This regex matches balanced double-curly tokens that do not themselves contain
# nested braces.
_PLACEHOLDER_TOKEN_RE = re.compile(r"\{\{[^{}]+\}\}")


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


def find_run_index_at_offset(
    positions: list[tuple[int, int, int]],
    offset: int,
) -> int:
    """
    Find the run index containing the given character offset.
    """
    for run_index, start, end in positions:
        if start <= offset < end:
            return run_index

    if positions and offset == positions[-1][2]:
        return positions[-1][0]

    return -1


def replace_placeholder_once_in_paragraph(
    paragraph,
    placeholder: str,
    replacement: str,
) -> bool:
    """
    Replace one occurrence of a placeholder in a paragraph, even if it is split
    across multiple runs.

    The replacement text inherits the style of the first participating run.

    BEHAVIOR NOTES
    --------------
    This function intentionally preserves the current low-level behavior:
    - it replaces a single occurrence at a time
    - it supports split-run placeholders
    - it writes the final replacement into the first participating run
    - it clears the following participating runs

    The optimized higher-level helpers call this function fewer times by first
    detecting which placeholders are actually present in a paragraph.
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


def replace_placeholder_all_in_paragraph(
    paragraph,
    placeholder: str,
    replacement: str,
) -> None:
    """
    Replace all occurrences of a placeholder in a paragraph, robustly across
    runs.
    """
    while replace_placeholder_once_in_paragraph(paragraph, placeholder, replacement):
        pass


def _extract_present_placeholders(text: str, mapping: dict[str, str]) -> list[str]:
    """
    Return the placeholder keys from `mapping` that are actually present in
    `text`.

    WHY THIS EXISTS
    ---------------
    The original implementation looped through every mapping key for every
    paragraph. That is the dominant cost observed in report timings.

    This helper performs a lightweight paragraph-local pre-scan:
    - skip immediately when `{{` does not exist
    - extract only placeholder-like tokens from the paragraph text
    - keep only tokens that actually exist in the provided mapping

    ORDERING
    --------
    We preserve first-seen paragraph order for discovered placeholders and
    remove duplicates. This keeps replacement stable and avoids repeated work
    for the same placeholder token within the same paragraph discovery pass.
    """
    if not text or _PLACEHOLDER_SENTINEL not in text:
        return []

    tokens = _PLACEHOLDER_TOKEN_RE.findall(text)
    if not tokens:
        return []

    seen: set[str] = set()
    present: list[str] = []

    for token in tokens:
        if token in seen:
            continue
        if token not in mapping:
            continue
        seen.add(token)
        present.append(token)

    return present


def _replace_present_placeholders_in_paragraph(paragraph, mapping: dict[str, str]) -> None:
    """
    Replace only the placeholders that are actually present in a paragraph.

    This is the main optimization entrypoint used by the shared traversal
    helpers. It keeps the low-level split-run replacement logic unchanged while
    drastically reducing unnecessary placeholder checks.
    """
    text = paragraph.text or ""
    present_placeholders = _extract_present_placeholders(text, mapping)
    if not present_placeholders:
        return

    for placeholder in present_placeholders:
        replace_placeholder_all_in_paragraph(
            paragraph,
            placeholder,
            str(mapping[placeholder]),
        )


def _replace_placeholders_in_table(table, mapping: dict[str, str]) -> None:
    """
    Replace placeholders in every paragraph of a table.

    This includes nested traversal of rows -> cells -> paragraphs while applying
    the same paragraph-local fast skip logic.
    """
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                _replace_present_placeholders_in_paragraph(paragraph, mapping)


def _replace_placeholders_in_container(container, mapping: dict[str, str]) -> None:
    """
    Replace placeholders in a header/footer-like container.

    Supported content:
    - direct paragraphs
    - table cell paragraphs
    """
    for paragraph in container.paragraphs:
        _replace_present_placeholders_in_paragraph(paragraph, mapping)

    for table in container.tables:
        _replace_placeholders_in_table(table, mapping)


def replace_placeholders_everywhere(doc: Document, mapping: dict[str, str]) -> None:
    """
    Replace placeholders across all document paragraphs and table paragraphs.

    OPTIMIZATION STRATEGY
    ---------------------
    This function keeps the same public behavior while reducing work:
    - body paragraphs are skipped immediately when they do not contain `{{`
    - table cell paragraphs are treated the same way
    - only placeholders that actually exist in each paragraph are processed
    """
    if not mapping:
        return

    for paragraph in doc.paragraphs:
        _replace_present_placeholders_in_paragraph(paragraph, mapping)

    for table in doc.tables:
        _replace_placeholders_in_table(table, mapping)


def replace_placeholders_in_headers_and_footers(
    doc: Document,
    mapping: dict[str, str],
) -> None:
    """
    Replace placeholders in all header/footer variants for every section:
    - default header/footer
    - first-page header/footer
    - even-page header/footer

    The same paragraph-local optimization used in the body is applied here as
    well.
    """
    if not mapping:
        return

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
            _replace_placeholders_in_container(container, mapping)


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
    Clone paragraph properties XML including tabs, indents, spacing and
    alignment.
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
    Yield all body paragraphs and all table-cell paragraphs in document order
    blocks.

    This helper is useful for search-style traversal where body + tables are
    both valid search locations.
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