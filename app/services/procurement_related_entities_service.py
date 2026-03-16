"""
app/services/procurement_related_entities_service.py

Focused mutation services for procurement-related child entities.

PURPOSE
-------
This module extracts non-HTTP orchestration from child-entity POST routes under
a procurement, specifically:

- supplier participation rows
- material/service lines

ARCHITECTURAL INTENT
--------------------
This module follows the agreed direction:

- function-first
- explicit action-oriented helpers
- no generic repository / command framework
- shared lightweight result types where multiple services need the same shape

BOUNDARY
--------
This module MAY:
- validate submitted child-entity form data
- load and validate child entities against a parent procurement
- perform ORM mutations
- perform audit logging and commit

This module MUST NOT:
- register routes
- call render_template(...)
- call redirect(...)
- call flash(...)
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from ..audit import log_action, serialize_model
from ..extensions import db
from ..models import MaterialLine, Procurement, ProcurementSupplier, Supplier
from .master_data_service import validate_cpv_or_none
from .operation_results import FlashMessage, OperationResult
from .parsing import parse_decimal, parse_optional_int


def execute_add_procurement_supplier(
    procurement: Procurement,
    form_data: Mapping[str, object],
) -> OperationResult:
    """
    Add a supplier participation row to a procurement.
    """
    supplier_id = parse_optional_int(form_data.get("supplier_id"))
    if not supplier_id:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρος προμηθευτής.", "danger"),),
        )

    supplier = Supplier.query.get(supplier_id)
    if not supplier:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Ο προμηθευτής δεν βρέθηκε.", "danger"),),
        )

    exists = ProcurementSupplier.query.filter_by(
        procurement_id=procurement.id,
        supplier_id=supplier_id,
    ).first()
    if exists:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Ο συγκεκριμένος προμηθευτής έχει ήδη προστεθεί σε αυτή την προμήθεια.", "warning"),),
        )

    offered_amount = parse_decimal(form_data.get("offered_amount"))
    is_winner = bool(form_data.get("is_winner"))
    notes = (form_data.get("notes") or "").strip() or None

    if is_winner:
        for link in procurement.supplies_links:
            link.is_winner = False

    link = ProcurementSupplier(
        procurement_id=procurement.id,
        supplier_id=supplier_id,
        offered_amount=offered_amount,
        is_winner=is_winner,
        notes=notes,
    )

    db.session.add(link)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Ο συγκεκριμένος προμηθευτής έχει ήδη προστεθεί σε αυτή την προμήθεια.", "warning"),),
        )

    procurement.recalc_totals()
    db.session.flush()
    log_action(link, "CREATE", before=None, after=serialize_model(link))
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Ο προμηθευτής προστέθηκε.", "success"),),
    )


def execute_delete_procurement_supplier(
    procurement: Procurement,
    link_id: int,
) -> OperationResult:
    """
    Delete a supplier participation row from a procurement.
    """
    link = ProcurementSupplier.query.get(link_id)
    if link is None or link.procurement_id != procurement.id:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η συμμετοχή προμηθευτή δεν βρέθηκε.", "danger"),),
            not_found=True,
        )

    before_snapshot = serialize_model(link)

    db.session.delete(link)
    procurement.recalc_totals()
    db.session.flush()
    log_action(link, "DELETE", before=before_snapshot, after=None)
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Ο προμηθευτής διαγράφηκε.", "success"),),
    )


def execute_add_material_line(
    procurement: Procurement,
    form_data: Mapping[str, object],
) -> OperationResult:
    """
    Add a material/service line to a procurement.
    """
    description = (form_data.get("description") or "").strip()
    if not description:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η περιγραφή γραμμής είναι υποχρεωτική.", "danger"),),
        )

    quantity = parse_decimal(form_data.get("quantity")) or Decimal("0")
    unit_price = parse_decimal(form_data.get("unit_price")) or Decimal("0")

    cpv_raw = (form_data.get("cpv") or "").strip()
    cpv_value = validate_cpv_or_none(cpv_raw)
    if cpv_raw and cpv_value is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο CPV (δεν υπάρχει στη λίστα CPV).", "danger"),),
        )

    line = MaterialLine(
        procurement_id=procurement.id,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        cpv=cpv_value,
        nsn=(form_data.get("nsn") or "").strip() or None,
        unit=(form_data.get("unit") or "").strip() or None,
    )

    db.session.add(line)
    db.session.flush()
    procurement.recalc_totals()
    db.session.flush()
    log_action(line, "CREATE", before=None, after=serialize_model(line))
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Η γραμμή προστέθηκε.", "success"),),
    )


def execute_delete_material_line(
    procurement: Procurement,
    line_id: int,
) -> OperationResult:
    """
    Delete a material/service line from a procurement.
    """
    line = MaterialLine.query.get(line_id)
    if line is None or line.procurement_id != procurement.id:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η γραμμή δεν βρέθηκε.", "danger"),),
            not_found=True,
        )

    before_snapshot = serialize_model(line)

    db.session.delete(line)
    procurement.recalc_totals()
    db.session.flush()
    log_action(line, "DELETE", before=before_snapshot, after=None)
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Η γραμμή διαγράφηκε.", "success"),),
    )