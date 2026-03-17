"""
app/presentation/presentation.py

Legacy presentation compatibility facade.

PURPOSE
-------
This file preserves the historical module path `app.presentation.presentation`
while `app.presentation` remains the canonical public surface.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add presentation rules here.
- Import from `app.presentation` in all new code.
"""

from __future__ import annotations

from . import *  # noqa: F401,F403
