"""
app/services/shared/operation_results.py

Shared lightweight result objects for service-layer orchestration.

PURPOSE
-------
This module centralizes a few small structured return types used by multiple
service modules.

WHY THIS FILE EXISTS
--------------------
The current procurement refactor introduces several service-layer functions that
need to return:
- success/failure state
- flash-style user messages
- optional identifiers
- optional "not found" semantics

Keeping these tiny dataclasses in one place avoids repetition without
introducing heavy abstraction.

ARCHITECTURAL INTENT
--------------------
This module is intentionally conservative:
- plain dataclasses
- no inheritance trees
- no result monads
- no framework-specific behavior

These are simple transport objects between service layer and routes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FlashMessage:
    """
    Structured flash-style message returned from service-layer execution.
    """

    message: str
    category: str


@dataclass(frozen=True)
class OperationResult:
    """
    Generic service-layer result with one or more flash-style messages.

    FIELDS
    ------
    ok:
        Whether the operation succeeded.
    flashes:
        Flash-style messages for the route to emit.
    entity_id:
        Optional created/target entity id, when useful to the caller.
    not_found:
        Optional flag for routes that should translate the outcome to 404.
    """

    ok: bool
    flashes: tuple[FlashMessage, ...]
    entity_id: int | None = None
    not_found: bool = False

