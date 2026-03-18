"""
app/services/procurement/create.py

Focused page/update services for the procurement create route.

PURPOSE
-------
This module extracts non-HTTP orchestration from:

    /procurements/new

It keeps the route thin by moving out:
- GET page-context assembly
- POST validation / creation orchestration

ARCHITECTURAL INTENT
--------------------
This module follows the agreed project direction:

- function-first
- explicit helpers
- no unnecessary service classes
- shared lightweight result types where multiple services need the same shape

IMPORTANT CHANGE
----------------
Handler selection is assignment-based, not just person-based.

That means the procurement form stores:
- handler_personnel_id: who the handler is
- handler_assignment_id: the exact organizational assignment selected
  (Directory + Department)

WHY THIS CHANGE EXISTS
----------------------
A single person may belong to multiple Departments / Directories.
The procurement must therefore store the exact organizational context selected
at the time of assignment, so reports (e.g. Award Decision) can render the
correct:
- Department
- Directory

CANONICAL TEMPLATE / SERVICE CONTRACT
-------------------------------------
The UI field name for handler selection is:

- handler_assignment_id

The page context collection exposed to templates is:

- handler_assignments

This module must stay aligned with the templates. Historically, a mismatch
between:
- handler_candidates vs handler_assignments
- handler_personnel_id vs handler_assignment_id

caused the handler dropdown to render empty and the submitted value not to be
read correctly on POST.

BOUNDARY
--------
This module MAY:
- assemble create-page template context
- validate submitted create form values
- create Procurement rows
- perform audit logging and commit

This module MUST NOT:
- register routes
- call render_template(...)
- call redirect(...)
- call flash(...)
"""

from __future__ import annotations

from collections.abc import Mapping

from ...audit import log_action, serialize_model
from ...extensions import db
from ...models import (
    IncomeTaxRule,
    Procurement,
    ServiceUnit,
    WithholdingProfile,
)
from ..master_data_service import (
    active_ale_rows,
    get_active_option_values,
    validate_ale_or_none,
)
from ..shared.operation_results import FlashMessage, OperationResult
from ..shared.parsing import parse_decimal, parse_optional_int
from .reference_data import (
    active_income_tax_rules,
    active_withholding_profiles,
    handler_candidate_ids,
    handler_candidates,
)


def build_create_procurement_page_context(
    *,
    is_admin: bool,
    current_service_unit_id: int | None,
) -> dict[str, object]:
    """
    Build template context for the procurement creation page.

    BEHAVIOR
    --------
    - Admin may choose service unit first, so handler list starts empty.
    - Non-admin is scoped to one service unit, so assignment-based handler
      candidates are loaded immediately.

    RETURNS
    -------
    dict[str, object]
        Context for `procurements/new.html`.

    IMPORTANT TEMPLATE CONTRACT
    ---------------------------
    The template expects:
    - handler_assignments

    and not:
    - handler_candidates

    The list contents are still produced by `handler_candidates(...)`, but the
    exposed template key must remain stable and aligned with the form template.
    """
    handler_list = []
    if not is_admin and current_service_unit_id:
        handler_list = handler_candidates(current_service_unit_id)

    return {
        "service_units": ServiceUnit.query.order_by(ServiceUnit.description.asc()).all(),
        "allocation_options": get_active_option_values("KATANOMH"),
        "quarterly_options": get_active_option_values("TRIMHNIAIA"),
        "status_options": get_active_option_values("KATASTASH"),
        "stage_options": get_active_option_values("STADIO"),
        "handler_assignments": handler_list,
        "income_tax_rules": active_income_tax_rules(),
        "withholding_profiles": active_withholding_profiles(),
        "committees": [],
        "ale_rows": active_ale_rows(),
    }


def execute_create_procurement(
    form_data: Mapping[str, object],
    *,
    is_admin: bool,
    current_service_unit_id: int | None,
) -> OperationResult:
    """
    Execute the POST workflow for procurement creation.

    SECURITY / VALIDATION
    ---------------------
    - ServiceUnit is validated server-side.
    - Handler selection is validated against the assignment ids that belong
      to the selected ServiceUnit.
    - UI-submitted values are never trusted.

    IMPORTANT HANDLER RULE
    ----------------------
    The submitted form field is:

        handler_assignment_id

    This value contains the selected `PersonnelDepartmentAssignment.id`.

    From that assignment we derive:
    - procurement.handler_assignment_id
    - procurement.handler_personnel_id

    WHY THIS MATTERS
    ----------------
    The procurement must preserve the exact organizational context selected by
    the user, so later reporting can display the correct Department/Directory.
    """
    if is_admin:
        service_unit_id = parse_optional_int(form_data.get("service_unit_id"))
        if service_unit_id is None:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Η Υπηρεσία είναι υποχρεωτική.", "danger"),),
            )

        service_unit = ServiceUnit.query.get(service_unit_id)
        if not service_unit:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρη Υπηρεσία.", "danger"),),
            )
    else:
        if not current_service_unit_id:
            raise PermissionError("Non-admin procurement creation requires assigned service unit.")
        service_unit_id = current_service_unit_id

    description = (form_data.get("description") or "").strip()
    if not description:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Η σύντομη περιγραφή είναι υποχρεωτική.", "danger"),),
        )

    handler_assignment_id = parse_optional_int(form_data.get("handler_assignment_id"))
    selected_assignment = None
    if handler_assignment_id:
        allowed_ids = handler_candidate_ids(service_unit_id)
        if handler_assignment_id not in allowed_ids:
            return OperationResult(
                ok=False,
                flashes=(
                    FlashMessage(
                        "Μη έγκυρος Χειριστής για την επιλεγμένη υπηρεσία.",
                        "danger",
                    ),
                ),
            )

        selected_assignment = next(
            (row for row in handler_candidates(service_unit_id) if row.id == handler_assignment_id),
            None,
        )
        if selected_assignment is None:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Αδυναμία φόρτωσης του επιλεγμένου χειριστή.", "danger"),),
            )

    income_tax_rule_id = parse_optional_int(form_data.get("income_tax_rule_id"))
    if income_tax_rule_id:
        rule = IncomeTaxRule.query.get(income_tax_rule_id)
        if not rule or not rule.is_active:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρος κανόνας Φόρου Εισοδήματος.", "danger"),),
            )
    else:
        rule = None

    withholding_profile_id = parse_optional_int(form_data.get("withholding_profile_id"))
    if withholding_profile_id:
        profile = WithholdingProfile.query.get(withholding_profile_id)
        if not profile or not profile.is_active:
            return OperationResult(
                ok=False,
                flashes=(FlashMessage("Μη έγκυρο προφίλ κρατήσεων.", "danger"),),
            )
    else:
        profile = None

    ale_value = validate_ale_or_none(form_data.get("ale"))
    if (form_data.get("ale") or "").strip() and not ale_value:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο ΑΛΕ (δεν υπάρχει στη λίστα ΑΛΕ-ΚΑΕ).", "danger"),),
        )

    procurement = Procurement(
        service_unit_id=service_unit_id,
        serial_no=(form_data.get("serial_no") or "").strip() or None,
        description=description,
        ale=ale_value,
        allocation=(form_data.get("allocation") or "").strip() or None,
        quarterly=(form_data.get("quarterly") or "").strip() or None,
        status=(form_data.get("status") or "").strip() or None,
        stage=(form_data.get("stage") or "").strip() or None,
        vat_rate=parse_decimal(form_data.get("vat_rate")),
        hop_commitment=(form_data.get("hop_commitment") or "").strip() or None,
        hop_forward1_commitment=(form_data.get("hop_forward1_commitment") or "").strip() or None,
        hop_forward2_commitment=(form_data.get("hop_forward2_commitment") or "").strip() or None,
        hop_approval_commitment=(form_data.get("hop_approval_commitment") or "").strip() or None,
        hop_preapproval=(form_data.get("hop_preapproval") or "").strip() or None,
        hop_forward1_preapproval=(form_data.get("hop_forward1_preapproval") or "").strip() or None,
        hop_forward2_preapproval=(form_data.get("hop_forward2_preapproval") or "").strip() or None,
        hop_approval=(form_data.get("hop_approval") or "").strip() or None,
        aay=(form_data.get("aay") or "").strip() or None,
        procurement_notes=(form_data.get("procurement_notes") or "").strip() or None,
        handler_personnel_id=(
            selected_assignment.personnel_id if selected_assignment is not None else None
        ),
        handler_assignment_id=(
            selected_assignment.id if selected_assignment is not None else None
        ),
        income_tax_rule_id=rule.id if rule else None,
        withholding_profile_id=profile.id if profile else None,
        committee_id=None,
        invoice_number=None,
        invoice_date=None,
        materials_receipt_date=None,
        invoice_receipt_date=None,
    )

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

    db.session.add(procurement)
    procurement.recalc_totals()
    db.session.flush()
    log_action(procurement, "CREATE", before=None, after=serialize_model(procurement))
    db.session.commit()

    flashes.append(FlashMessage("Η προμήθεια δημιουργήθηκε.", "success"))

    return OperationResult(
        ok=True,
        flashes=tuple(flashes),
        entity_id=procurement.id,
    )