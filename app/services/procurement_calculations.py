"""
app/services/procurement_calculations.py

Conservative procurement calculation service.

PURPOSE
-------
`app/models/procurement.py` delegates financial calculations to
`ProcurementCalculationService`, but that implementation file was not present in
the uploaded `combined_project.md` snapshot.

This module provides the missing canonical implementation so the documented
model contract resolves to a concrete service.

IMPORTANT SCOPE NOTE
--------------------
The formulas implemented here are intentionally conservative and are derived
only from data structures visible in the uploaded source:

- line totals are summed from `procurement.materials[*].total_pre_vat`
- VAT uses `procurement.vat_rate` as a fractional rate when <= 1, otherwise as
  a percentage value
- withholding profile percentages are treated as true percent values, matching
  `WithholdingProfile.total_fraction`
- income tax is applied only when the pre-VAT subtotal exceeds the configured
  threshold, matching the visible `IncomeTaxRule` model docstring

If the original project has additional domain rules that were not included in
`combined_project.md`, reconcile them explicitly before production use.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .shared.parsing import parse_decimal
from ..models.helpers import _money, _normalize_percent, _percent_to_fraction, _to_decimal


class ProcurementCalculationService:
    """
    Stateless financial calculation service for Procurement aggregates.

    DESIGN
    ------
    Class-based only because `app.models.procurement.Procurement` already
    imports this symbol by name. Methods remain stateless and explicit.
    """

    @staticmethod
    def _subtotal(procurement: Any) -> Decimal:
        total = Decimal("0.00")
        for line in getattr(procurement, "materials", []) or []:
            total += _to_decimal(getattr(line, "total_pre_vat", None))
        return _money(total)

    @staticmethod
    def _vat_fraction(procurement: Any) -> Decimal:
        return _normalize_percent(_to_decimal(getattr(procurement, "vat_rate", None)))

    @staticmethod
    def compute_public_withholdings(procurement: Any) -> dict[str, Decimal]:
        subtotal = ProcurementCalculationService._subtotal(procurement)
        profile = getattr(procurement, "withholding_profile", None)
        if not profile:
            return {
                "mt_eloa_amount": Decimal("0.00"),
                "eadhsy_amount": Decimal("0.00"),
                "withholding1_amount": Decimal("0.00"),
                "withholding2_amount": Decimal("0.00"),
                "total_amount": Decimal("0.00"),
                "total_percent": Decimal("0.00"),
            }

        mt = _money(subtotal * _percent_to_fraction(getattr(profile, "mt_eloa_percent", 0)))
        eadhsy = _money(subtotal * _percent_to_fraction(getattr(profile, "eadhsy_percent", 0)))
        w1 = _money(subtotal * _percent_to_fraction(getattr(profile, "withholding1_percent", 0)))
        w2 = _money(subtotal * _percent_to_fraction(getattr(profile, "withholding2_percent", 0)))
        total = _money(mt + eadhsy + w1 + w2)
        return {
            "mt_eloa_amount": mt,
            "eadhsy_amount": eadhsy,
            "withholding1_amount": w1,
            "withholding2_amount": w2,
            "total_amount": total,
            "total_percent": _money(getattr(profile, "total_percent", Decimal("0.00"))),
        }

    @staticmethod
    def compute_income_tax(procurement: Any) -> dict[str, Decimal | bool]:
        subtotal = ProcurementCalculationService._subtotal(procurement)
        rule = getattr(procurement, "income_tax_rule", None)
        if not rule:
            return {
                "applies": False,
                "rate_percent": Decimal("0.00"),
                "threshold_amount": Decimal("0.00"),
                "amount": Decimal("0.00"),
            }

        threshold = _money(getattr(rule, "threshold_amount", Decimal("0.00")))
        if subtotal <= threshold:
            return {
                "applies": False,
                "rate_percent": _money(getattr(rule, "rate_percent", Decimal("0.00"))),
                "threshold_amount": threshold,
                "amount": Decimal("0.00"),
            }

        amount = _money(subtotal * _percent_to_fraction(getattr(rule, "rate_percent", 0)))
        return {
            "applies": True,
            "rate_percent": _money(getattr(rule, "rate_percent", Decimal("0.00"))),
            "threshold_amount": threshold,
            "amount": amount,
        }

    @staticmethod
    def compute_payment_analysis(procurement: Any) -> dict[str, Any]:
        subtotal = ProcurementCalculationService._subtotal(procurement)
        vat_fraction = ProcurementCalculationService._vat_fraction(procurement)
        vat_amount = _money(subtotal * vat_fraction)
        grand_total = _money(subtotal + vat_amount)
        public_withholdings = ProcurementCalculationService.compute_public_withholdings(procurement)
        income_tax = ProcurementCalculationService.compute_income_tax(procurement)
        payable_total = _money(
            grand_total
            - _to_decimal(public_withholdings.get("total_amount"))
            - _to_decimal(income_tax.get("amount"))
        )
        return {
            "sum_total": subtotal,
            "vat_percent": _money(vat_fraction * Decimal("100")),
            "vat_amount": vat_amount,
            "grand_total": grand_total,
            "public_withholdings": public_withholdings,
            "income_tax": income_tax,
            "payable_total": payable_total,
        }

    @staticmethod
    def recalc_totals(procurement: Any) -> None:
        analysis = ProcurementCalculationService.compute_payment_analysis(procurement)
        procurement.sum_total = analysis["sum_total"]
        procurement.vat_amount = analysis["vat_amount"]
        procurement.grand_total = analysis["grand_total"]
