"""
app/extensions/extensions.py

Legacy extensions compatibility facade.

PURPOSE
-------
This file preserves the historical module path `app.extensions.extensions`
while `app.extensions` remains the canonical public registry surface.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not instantiate new extension objects here.
- Import from `app.extensions` in all new code.
"""

from __future__ import annotations

from . import *  # noqa: F401,F403
