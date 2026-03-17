"""
app/services/procurement/edit.py

Focused edit-page services for the main procurement edit route.

PURPOSE
-------
This module extracts non-HTTP orchestration from:

    /procurements/<id>/edit

It keeps the route thin by moving out:
- GET page-context assembly
- POST validation / mutation orchestration

ARCHITECTURAL INTENT
--------------------
This module is intentionally conservative.

We do NOT introduce:
- generic command buses
- class-heavy use-case hierarchies
- abstract base layers
- one-class-per-route patterns

Instead we follow the agreed direction:
- function-first
- small, explicit helpers
- shared lightweight result types where multiple services need the same shape

BOUNDARY
--------
This module MAY:
- assemble edit-page template context
- validate submitted edit form values
- mutate Procurement state
- perform audit logging and commit

This module MUST NOT:
- register routes
- call render_template(...)
- call redirect(...)
- call flash(...)

SECURITY NOTE
-------------
This module assumes route-level access control is already applied via:
- login_required
- procurement_access_required(load_procurement)

The route should still enforce any edit-specific permission gate before
calling the POST executor.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import IncomeTaxRule, Procurement, ServiceUnit, Supplier, WithholdingProfile
from ..master_data_service import (
    active_ale_rows,
    active_cpv_rows,
    get_active_option_values,
    validate_ale_or_none,
)
from ..shared.operation_results import FlashMessage, OperationResult
from ..shared.parsing import parse_decimal, parse_optional_date, parse_optional_int
from ..procurement_service import (
    active_income_tax_rules,
    active_withholding_profiles,
    handler_candidate_ids,
    handler_candidates,
    opened_from_all_list,
)


def build_edit_procurement_page_context(
    procurement: Procurement,
    next_url: str,
) -> dict[str, Any]:
    """
    Build template context for the main procurement edit page.
    """
    return {
        "procurement": procurement,
        "service_units": ServiceUnit.query.order_by(ServiceUnit.description.asc()).all(),
        "suppliers": Supplier.query.order_by(Supplier.name.asc()).all(),
        "allocation_options": get_active_option_values("KATANOMH"),
        "quarterly_options": get_active_option_values("TRIMHNIAIA"),
        "status_options": get_active_option_values("KATASTASH"),
        "stage_options": get_active_option_values("STADIO"),
        "handler_candidates": handler_candidates(procurement.service_unit_id),
        "income_tax_rules": active_income_tax_rules(),
        "withholding_profiles": active_withholding_profiles(),
        "committees": [],
        "analysis": procurement.compute_payment_analysis(),
        "next_url": next_url,
        "show_all_report_buttons": opened_from_all_list(next_url),
        "ale_rows": active_ale_rows(),
        "cpv_rows": active_cpv_rows(),
    }


def execute_edit_procurement(
    procurement: Procurement,
    form_data: Mapping[str, Any],
    *,
    is_admin: bool,
) -> OperationResult:
    """
    Execute the POST edit workflow for a procurement.
    """
    before_snapshot = serialize_model(procurement)

    status_options = get_active_option_values("KATASTASH")
    stage_options = get_active_option_values("STADIO")

    if is_admin:
        new_service_unit_id = parse_optional_int(form_data.get("service_unit_id"))
        if new_service_unit_id is None:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Η Υπηρεσία είναι υποχρεωτική.", "danger"),),
            )

        service_unit = ServiceUnit.query.get(new_service_unit_id)
        if not service_unit:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρη Υπηρεσία.", "danger"),),
            )

        procurement.service_unit_id = service_unit.id

    procurement.serial_no = (form_data.get("serial_no") or "").strip() or None
    procurement.description = (form_data.get("description") or "").strip() or None
    if not procurement.description:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η σύντομη περιγραφή είναι υποχρεωτική.", "danger"),),
        )

    ale_raw = (form_data.get("ale") or "").strip()
    procurement.ale = validate_ale_or_none(ale_raw)
    if ale_raw and procurement.ale is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο ΑΛΕ (δεν υπάρχει στη λίστα ΑΛΕ-ΚΑΕ).", "danger"),),
        )

    procurement.allocation = (form_data.get("allocation") or "").strip() or None
    procurement.quarterly = (form_data.get("quarterly") or "").strip() or None

    new_status = (form_data.get("status") or "").strip() or None
    if new_status and new_status not in status_options:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Κατάσταση.", "danger"),),
        )
    procurement.status = new_status

    new_stage = (form_data.get("stage") or "").strip() or None
    if new_stage and new_stage not in stage_options:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο Στάδιο.", "danger"),),
        )
    procurement.stage = new_stage

    procurement.vat_rate = parse_decimal(form_data.get("vat_rate"))

    procurement.hop_commitment = (form_data.get("hop_commitment") or "").strip() or None
    procurement.hop_forward1_commitment = (form_data.get("hop_forward1_commitment") or "").strip() or None
    procurement.hop_forward2_commitment = (form_data.get("hop_forward2_commitment") or "").strip() or None
    procurement.hop_approval_commitment = (form_data.get("hop_approval_commitment") or "").strip() or None
    procurement.hop_preapproval = (form_data.get("hop_preapproval") or "").strip() or None
    procurement.hop_forward1_preapproval = (form_data.get("hop_forward1_preapproval") or "").strip() or None
    procurement.hop_forward2_preapproval = (form_data.get("hop_forward2_preapproval") or "").strip() or None
    procurement.hop_approval = (form_data.get("hop_approval") or "").strip() or None
    procurement.aay = (form_data.get("aay") or "").strip() or None
    procurement.procurement_notes = (form_data.get("procurement_notes") or "").strip() or None

    procurement.identity_prosklisis = (form_data.get("identity_prosklisis") or "").strip() or None
    procurement.adam_aay = (form_data.get("adam_aay") or "").strip() or None
    procurement.ada_aay = (form_data.get("ada_aay") or "").strip() or None
    procurement.adam_prosklisis = (form_data.get("adam_prosklisis") or "").strip() or None

    procurement.identity_apofasis_anathesis = (form_data.get("identity_apofasis_anathesis") or "").strip() or None
    procurement.adam_apofasis_anathesis = (form_data.get("adam_apofasis_anathesis") or "").strip() or None
    procurement.contract_number = (form_data.get("contract_number") or "").strip() or None
    procurement.adam_contract = (form_data.get("adam_contract") or "").strip() or None

    invoice_number_raw = form_data.get("invoice_number")
    invoice_date_raw = form_data.get("invoice_date")
    materials_receipt_date_raw = form_data.get("materials_receipt_date")
    invoice_receipt_date_raw = form_data.get("invoice_receipt_date")

    procurement.invoice_number = (invoice_number_raw or "").strip() or None

    parsed_invoice_date = parse_optional_date(invoice_date_raw)
    if (invoice_date_raw or "").strip() and parsed_invoice_date is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Ημερομηνία Τιμολογίου.", "danger"),),
        )
    procurement.invoice_date = parsed_invoice_date

    parsed_materials_receipt_date = parse_optional_date(materials_receipt_date_raw)
    if (materials_receipt_date_raw or "").strip() and parsed_materials_receipt_date is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Ημερομηνία Παραλαβής Υλικών.", "danger"),),
        )
    procurement.materials_receipt_date = parsed_materials_receipt_date

    parsed_invoice_receipt_date = parse_optional_date(invoice_receipt_date_raw)
    if (invoice_receipt_date_raw or "").strip() and parsed_invoice_receipt_date is None:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρη Ημερομηνία Παραλαβής Τιμολογίου.", "danger"),),
        )
    procurement.invoice_receipt_date = parsed_invoice_receipt_date

    procurement.protocol_number = (form_data.get("protocol_number") or "").strip() or None

    handler_pid = parse_optional_int(form_data.get("handler_personnel_id"))
    if handler_pid:
        allowed_ids = handler_candidate_ids(procurement.service_unit_id)
        if handler_pid not in allowed_ids:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρος Χειριστής για την υπηρεσία.", "danger"),),
            )
        procurement.handler_personnel_id = handler_pid
    else:
        procurement.handler_personnel_id = None

    income_tax_rule_id = parse_optional_int(form_data.get("income_tax_rule_id"))
    if income_tax_rule_id:
        rule = IncomeTaxRule.query.get(income_tax_rule_id)
        if not rule or not rule.is_active:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρος κανόνας Φόρου Εισοδήματος.", "danger"),),
            )
        procurement.income_tax_rule_id = rule.id
    else:
        procurement.income_tax_rule_id = None

    withholding_profile_id = parse_optional_int(form_data.get("withholding_profile_id"))
    if withholding_profile_id:
        profile = WithholdingProfile.query.get(withholding_profile_id)
        if not profile or not profile.is_active:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρο προφίλ κρατήσεων.", "danger"),),
            )
        procurement.withholding_profile_id = profile.id
    else:
        procurement.withholding_profile_id = None

    flashes: list[FlashMessage] = []

    send_to_expenses = bool(form_data.get("send_to_expenses"))
    if send_to_expenses and not procurement.hop_approval:
        procurement.send_to_expenses = False
        flashes.append(
            FlashMessage(
                "Για μεταφορά σε Εκκρεμείς Δαπάνες απαιτείται ΗΩΠ Έγκρισης.",
                "warning",
            )
        )
    else:
        procurement.send_to_expenses = bool(send_to_expenses and procurement.hop_approval)

    procurement.recalc_totals()
    db.session.flush()
    log_action(procurement, "UPDATE", before=before_snapshot, after=serialize_model(procurement))
    db.session.commit()

    flashes.append(FlashMessage("Η προμήθεια ενημερώθηκε.", "success"))

    return OperationResult(
        ok=True,
        flashes=tuple(flashes),
    )

