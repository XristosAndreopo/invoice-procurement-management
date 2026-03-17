"""
app/services/parsing.py

Shared parsing helper compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.shared.parsing`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.shared.parsing import *  # noqa: F401,F403
