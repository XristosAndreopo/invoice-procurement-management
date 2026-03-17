"""
app/services/settings/theme.py

Theme settings page/use-case helpers.

PURPOSE
-------
This module extracts the non-HTTP theme selection logic from
`app/blueprints/settings/routes.py`.

CURRENT ROUTES SUPPORTED
------------------------
- /settings/theme

ARCHITECTURAL INTENT
--------------------
The route should remain responsible only for:
- decorators
- reading request.form
- flashing returned messages
- redirect / render decisions

This module is responsible for:
- publishing supported theme metadata for the page
- validating submitted theme selection
- applying the selected theme to the current user
- committing the change

DESIGN CHOICE
-------------
A small function-first module is sufficient here.
No class abstraction is justified for a single, simple settings use-case.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...extensions import db
from ..shared.operation_results import FlashMessage, OperationResult

THEME_CHOICES: dict[str, tuple[str, str]] = {
    "default": ("Προεπιλογή", "Φωτεινό θέμα με ουδέτερα χρώματα."),
    "dark": ("Σκούρο", "Σκούρο θέμα κατάλληλο για χαμηλό φωτισμό."),
    "ocean": ("Ocean", "Απαλό μπλε θέμα."),
}


def build_theme_page_context() -> dict[str, Any]:
    """
    Build template context for the theme settings page.

    RETURNS
    -------
    dict[str, Any]
        Template context with the supported theme choices.
    """
    return {
        "themes": THEME_CHOICES,
    }


def execute_theme_update(user: Any, form_data: Mapping[str, object]) -> OperationResult:
    """
    Validate and persist a user's theme selection.

    PARAMETERS
    ----------
    user:
        The authenticated User ORM entity.
    form_data:
        Submitted form payload.

    RETURNS
    -------
    OperationResult
        Generic service-layer result for route flashing/redirecting.
    """
    selected = form_data.get("theme")
    if selected not in THEME_CHOICES:
        return OperationResult(
            ok=False,
            flashes=(FlashMessage("Μη έγκυρο θέμα.", "danger"),),
        )

    user.theme = str(selected)
    db.session.commit()

    return OperationResult(
        ok=True,
        flashes=(FlashMessage("Το θέμα ενημερώθηκε.", "success"),),
    )


__all__ = [
    "THEME_CHOICES",
    "build_theme_page_context",
    "execute_theme_update",
]

