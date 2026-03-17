# app/reports/proforma_invoice.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from typing import Any, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import os

@dataclass(frozen=True)
class ProformaConstants:
    pn_afm: str
    pn_doy: str
    reference_goods: str


def _money(v: Any) -> str:
    try:
        d = Decimal(str(v or "0"))
    except Exception:
        d = Decimal("0")
    d = d.quantize(Decimal("0.01"))
    # ελληνικό friendly: 1.234,56
    s = f"{d:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


def _safe(v: Any) -> str:
    s = ("" if v is None else str(v)).strip()
    return s if s else "—"


def _register_greek_font() -> str:
    """
    Ensure a TTF font that supports Greek is registered.

    Strategy:
    1) Try DejaVu Sans if available (best cross-platform if you ship it).
    2) Try Windows Arial.
    3) Fall back to Helvetica (may break Greek glyphs on some machines).
    """
    here = os.path.dirname(__file__)
    dejavu_path = os.path.join(here, "..", "static", "fonts", "DejaVuSans.ttf")
    dejavu_path = os.path.normpath(dejavu_path)

    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", dejavu_path))
        return "DejaVuSans"
    except Exception:
        pass
    
    candidates = [
        # ("DejaVuSans", "app/static/fonts/DejaVuSans.ttf"),
        ("Arial", r"C:\Windows\Fonts\arial.ttf"),
        ("ArialUnicode", r"C:\Windows\Fonts\arialuni.ttf"),
    ]
    for name, path in candidates:
        try:
            pdfmetrics.registerFont(TTFont(name, path))
            return name
        except Exception:
            continue
    return "Helvetica"


def build_proforma_invoice_pdf(
    procurement: Any,
    service_unit: Any,
    winner: Optional[Any],
    analysis: dict,
    table_title: str,
    constants: ProformaConstants,
) -> bytes:
    font_name = _register_greek_font()

    styles = getSampleStyleSheet()
    base = ParagraphStyle(
        "base",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10,
        leading=12,
        spaceAfter=0,
    )
    small = ParagraphStyle(
        "small",
        parent=base,
        fontSize=9,
        leading=11,
    )
    title = ParagraphStyle(
        "title",
        parent=base,
        fontSize=14,
        leading=16,
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    h = ParagraphStyle(
        "h",
        parent=base,
        fontSize=11,
        leading=13,
        spaceBefore=6,
        spaceAfter=4,
    )
    right = ParagraphStyle("right", parent=base, alignment=TA_RIGHT)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Προτιμολόγιο",
        author="Invoice Management System",
        subject="Προτιμολόγιο",
    )

    elems = []
    elems.append(Paragraph("ΠΡΟΤΙΜΟΛΟΓΙΟ", title))
    elems.append(Spacer(1, 6))

    # -------------------------
    # HEADER (2 columns)
    # -------------------------
    left_lines = [
        "<b>ΣΤΟΙΧΕΙΑ ΠΟΛΕΜΙΚΟΥ ΝΑΥΤΙΚΟΥ</b>",
        f"<b>ΕΠΩΝΥΜΙΑ:</b> ΠΟΛΕΜΙΚΟ ΝΑΥΤΙΚΟ - {_safe(getattr(service_unit, 'description', None))}",
        f"<b>ΔΙΕΥΘΥΝΣΗ:</b> {_safe(getattr(service_unit, 'address', None))}",
    ]
    phone = _safe(getattr(service_unit, "phone", None))
    if phone != "—":
        left_lines.append(f"<b>ΤΗΛΕΦΩΝΟ:</b> {phone}")

    left_lines += [
        f"<b>ΑΦΜ:</b> {constants.pn_afm}",
        f"<b>ΔΟΥ:</b> {constants.pn_doy}",
        f"<b>ΑΡΙΘΜΟΣ ΑΑΗΤ:</b> {_safe(getattr(service_unit, 'aahit', None))}",
        f"<b>ΣΤΟΙΧΕΙΟ ΑΝΑΦΟΡΑΣ ΑΓΑΘΟΥ:</b> {constants.reference_goods}",
    ]

    right_lines = [
        "<b>ΣΤΟΙΧΕΙΑ ΑΝΑΔΟΧΟΥ ΦΟΡΕΑ</b>",
        f"<b>ΕΠΩΝΥΜΙΑ:</b> {_safe(getattr(winner, 'name', None) if winner else None)}",
        f"<b>ΑΦΜ:</b> {_safe(getattr(winner, 'afm', None) if winner else None)}",
        f"<b>EMAIL:</b> {_safe(getattr(winner, 'email', None) if winner else None)}",
        f"<b>ΕΜΠΑ:</b> {_safe(getattr(winner, 'emba', None) if winner else None)}",
        f"<b>ΔΙΕΥΘΥΝΣΗ:</b> {_safe(getattr(winner, 'address', None) if winner else None)}",
        f"<b>ΠΟΛΗ:</b> {_safe(getattr(winner, 'city', None) if winner else None)}",
        f"<b>Τ.Κ.:</b> {_safe(getattr(winner, 'postal_code', None) if winner else None)}",
        f"<b>ΧΩΡΑ:</b> {_safe(getattr(winner, 'country', None) if winner else None)}",
    ]

    header_table = Table(
        [
            [
                Paragraph("<br/>".join(left_lines), small),
                Paragraph("<br/>".join(right_lines), small),
            ]
        ],
        colWidths=[(A4[0] - 28 * mm) / 2, (A4[0] - 28 * mm) / 2],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (0, 0), 0.8, colors.black),
                ("BOX", (1, 0), (1, 0), 0.8, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elems.append(header_table)
    elems.append(Spacer(1, 10))

    # -------------------------
    # META
    # -------------------------
    elems.append(Paragraph(f"<b>Σύντομη Περιγραφή:</b> {_safe(getattr(procurement, 'description', None))}", base))
    elems.append(Paragraph(f"<b>ΑΛΕ:</b> {_safe(getattr(procurement, 'ale', None))}", base))
    elems.append(Spacer(1, 10))

    # -------------------------
    # LINES TABLE
    # -------------------------
    elems.append(Paragraph(table_title, ParagraphStyle("tt", parent=h, alignment=TA_CENTER)))
    elems.append(Spacer(1, 4))

    data = [
        [
            Paragraph("<b>Α/Α</b>", small),
            Paragraph("<b>ΠΕΡΙΓΡΑΦΗ</b>", small),
            Paragraph("<b>CPV</b>", small),
            Paragraph("<b>Μ/Μ</b>", small),
            Paragraph("<b>ΠΟΣΟΤΗΤΑ</b>", small),
            Paragraph("<b>ΤΙΜ. ΜΟΝ.</b>", small),
            Paragraph("<b>ΣΥΝΟΛΟ</b>", small),
        ]
    ]

    lines = list(getattr(procurement, "materials", []) or [])
    if lines:
        for i, ln in enumerate(lines, start=1):
            qty = getattr(ln, "quantity", None)
            unit_price = getattr(ln, "unit_price", None)
            total_pre_vat = getattr(ln, "total_pre_vat", None)

            data.append(
                [
                    Paragraph(str(i), small),
                    Paragraph(_safe(getattr(ln, "description", None)), small),
                    Paragraph(_safe(getattr(ln, "cpv", None)), small),
                    Paragraph(_safe(getattr(ln, "unit", None)), small),
                    Paragraph(_safe(qty), ParagraphStyle("rq", parent=small, alignment=TA_RIGHT)),
                    Paragraph(_safe(unit_price), ParagraphStyle("rup", parent=small, alignment=TA_RIGHT)),
                    Paragraph(_money(total_pre_vat), ParagraphStyle("rt", parent=small, alignment=TA_RIGHT)),
                ]
            )
    else:
        data.append([Paragraph("—", small)] + [Paragraph("Δεν υπάρχουν γραμμές υλικών/υπηρεσιών.", small)] + [Paragraph("", small)] * 5)

    col_widths = [14 * mm, 78 * mm, 20 * mm, 18 * mm, 18 * mm, 22 * mm, 24 * mm]
    lines_table = Table(data, colWidths=col_widths, repeatRows=1)
    lines_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.7, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    elems.append(lines_table)
    elems.append(Spacer(1, 10))

    # -------------------------
    # ANALYSIS
    # -------------------------
    elems.append(Paragraph("ΑΝΑΛΥΣΗ ΔΑΠΑΝΗΣ", h))

    pw = analysis.get("public_withholdings") or {}
    it = analysis.get("income_tax") or {}

    analysis_rows = [
        ["ΠΙΣΤΩΣΗ ΧΩΡΙΣ ΦΠΑ", _money(analysis.get("sum_total"))],
        [f"ΚΡΑΤΗΣΕΙΣ ΥΠΕΡ ΔΗΜΟΣΙΟΥ ({_safe(pw.get('total_percent'))}%)", _money(pw.get("total_amount"))],
    ]
    items = pw.get("items") or []
    if items:
        for item in items:
            analysis_rows.append(
                [f"— {_safe(item.get('label'))} ({_safe(item.get('percent'))}%)", _money(item.get("amount"))]
            )
    else:
        analysis_rows.append(["— (Δεν υπάρχουν επιλεγμένες κρατήσεις)", "0,00 €"])

    analysis_rows += [
        [f"ΦΟΡΟΣ ΕΙΣΟΔΗΜΑΤΟΣ ({_safe(it.get('rate_percent'))}%)", _money(it.get("amount"))],
        [f"ΦΠΑ ({_safe(analysis.get('vat_percent'))}%)", _money(analysis.get("vat_amount"))],
        ["ΤΕΛΙΚΟ ΠΛΗΡΩΤΕΟ ΠΟΣΟ", _money(analysis.get("payable_total"))],
    ]

    analysis_tbl = Table(
        [[Paragraph(_safe(a), base), Paragraph(_safe(b), ParagraphStyle("ar", parent=base, alignment=TA_RIGHT))] for a, b in analysis_rows],
        colWidths=[(A4[0] - 28 * mm) * 0.72, (A4[0] - 28 * mm) * 0.28],
    )
    analysis_tbl.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.7, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elems.append(analysis_tbl)
    elems.append(Spacer(1, 10))

    # -------------------------
    # JUSTIFICATIONS (conditional)
    # -------------------------
    elems.append(Paragraph("ΔΙΚΑΙΟΛΟΓΗΤΙΚΑ ΠΛΗΡΩΜΗΣ ΤΙΜΟΛΟΓΙΟΥ", h))

    base_amount = analysis.get("sum_total") or Decimal("0")
    try:
        base_amount_dec = Decimal(str(base_amount))
    except Exception:
        base_amount_dec = Decimal("0")

    items = []
    items.append(" Υπεύθυνη Δήλωση.")
    items.append(" Βεβαίωση ΙΒΑΝ (εάν αναγράφεται στο τιμολόγιο δεν χρειάζεται).")

    if base_amount >= Decimal("1500"):
        items.append(" Πιστοποιητικό Φορολογικής Ενημερότητας.")

    if base_amount >= Decimal("2500"):
        items.append(" Πιστοποιητικό Ασφαλιστικής Ενημερότητας.")
        items.append(" Πιστοποιητικό Νόμιμης Εκπροσώπησης (πρέπει να αναγράφονται αναλυτικά οι εκπρόσωποι).")
        items.append(" Αντίγραφο Ποινικού Μητρώου.")

    elems.append(Paragraph("• " + "<br/>• ".join(items), base))
    elems.append(Spacer(1, 4))
    

    doc.build(elems)
    return buf.getvalue()

