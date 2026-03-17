"""
app/services/procurement/implementation.py

Focused page/update services for the procurement implementation phase route.

PURPOSE
-------
This module extracts non-HTTP orchestration from:

    /procurements/<id>/implementation

It keeps the route thin by moving out:
- GET page-context assembly
- POST validation / mutation orchestration

ARCHITECTURAL INTENT
--------------------
This module follows the agreed project direction:

- function-first
- explicit helpers
- no unnecessary service classes
- shared lightweight result types where multiple services need the same shape

BOUNDARY
--------
This module MAY:
- assemble implementation-page template context
- validate submitted implementation form values
- mutate Procurement state
- perform audit logging and commit

This module MUST NOT:
- register routes
- call render_template(...)
- call redirect(...)
- call flash(...)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import IncomeTaxRule, Procurement, ProcurementCommittee, WithholdingProfile
from ..master_data_service import get_active_option_values
from ..shared.operation_results import FlashMessage, OperationResult
from ..shared.parsing import parse_decimal, parse_optional_date, parse_optional_int
from ..procurement_service import (
    active_income_tax_rules,
    active_withholding_profiles,
    committees_for_service_unit,
)


def build_implementation_procurement_page_context(
    procurement: Procurement,
    next_url: str,
    *,
    can_edit: bool,
) -> dict[str, Any]:
    """
    Build template context for the implementation-phase procurement page.
    """
    return {
        "procurement": procurement,
        "income_tax_rules": active_income_tax_rules(),
        "withholding_profiles": active_withholding_profiles(),
        "committees": committees_for_service_unit(procurement.service_unit_id),
        "analysis": procurement.compute_payment_analysis(),
        "can_edit": can_edit,
        "status_options": get_active_option_values("KATASTASH"),
        "stage_options": get_active_option_values("STADIO"),
        "next_url": next_url,
    }


def execute_implementation_procurement_update(
    procurement: Procurement,
    form_data: Mapping[str, Any],
) -> OperationResult:
    """
    Execute the POST workflow for the implementation-phase procurement page.
    """
    before_snapshot = serialize_model(procurement)

    status_options = get_active_option_values("KATASTASH")
    stage_options = get_active_option_values("STADIO")

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

    procurement.hop_preapproval = (form_data.get("hop_preapproval") or "").strip() or None
    procurement.hop_approval = (form_data.get("hop_approval") or "").strip() or None
    procurement.aay = (form_data.get("aay") or "").strip() or None
    procurement.procurement_notes = (form_data.get("procurement_notes") or "").strip() or None

    procurement.identity_prosklisis = (form_data.get("identity_prosklisis") or "").strip() or None

    committee_id = parse_optional_int(form_data.get("committee_id"))
    if committee_id:
        committee = ProcurementCommittee.query.get(committee_id)
        if not committee or not committee.is_active or committee.service_unit_id != procurement.service_unit_id:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρη επιτροπή για την υπηρεσία.", "danger"),),
            )
        procurement.committee_id = committee.id
    else:
        procurement.committee_id = None

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

    procurement.vat_rate = parse_decimal(form_data.get("vat_rate"))

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

    flashes.append(FlashMessage("Η προμήθεια (φάση υλοποίησης) ενημερώθηκε.", "success"))

    return OperationResult(
        ok=True,
        flashes=tuple(flashes),
    )

