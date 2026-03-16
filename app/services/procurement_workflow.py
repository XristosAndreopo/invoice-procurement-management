"""
app/services/procurement_workflow.py

Procurement workflow predicates and domain-state helpers.

PURPOSE
-------
This module contains small procurement workflow helpers that express
domain/application state rules without becoming route handlers.

CURRENT SCOPE
-------------
At this stage, this module intentionally remains small and focused:
- implementation-phase predicate

WHY THIS FILE EXISTS
--------------------
The previous procurement service module mixed:
- query helpers
- reference-data lookups
- workflow rules
- presentation/download helpers

Even though the current workflow surface is small, extracting it now creates a
clear boundary for future procurement-state rules without bloating query or
presentation modules.

ARCHITECTURAL BOUNDARY
----------------------
This module MAY:
- inspect Procurement state
- expose route-independent boolean predicates
- centralize repeated workflow interpretation rules

This module must NOT:
- render templates
- flash/redirect
- access request objects
- contain SQLAlchemy list/query orchestration
- contain UI-only helpers
"""

from __future__ import annotations

from ..models import Procurement


def is_in_implementation_phase(procurement: Procurement) -> bool:
    """
    Determine whether a procurement is in implementation / expenses phase.

    PARAMETERS
    ----------
    procurement:
        Procurement entity.

    RETURNS
    -------
    bool
        True when the procurement is considered to be in implementation phase.

    CURRENT RULE
    ------------
    A procurement is in implementation phase when:
    - send_to_expenses is True
    - hop_approval has a value

    WHY THIS HELPER EXISTS
    ----------------------
    This predicate appears repeatedly in navigation and implementation flows.
    Keeping it centralized ensures one business interpretation.
    """
    return bool(procurement.send_to_expenses and procurement.hop_approval)


__all__ = [
    "is_in_implementation_phase",
]