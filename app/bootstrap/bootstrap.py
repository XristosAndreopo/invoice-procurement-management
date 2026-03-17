"""
app/bootstrap/bootstrap.py

Legacy bootstrap compatibility facade.

PURPOSE
-------
This file preserves the historical module path `app.bootstrap.bootstrap` while
making `app.bootstrap` the single canonical implementation surface.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add wiring logic here.
- Import from `app.bootstrap` in all new code.
"""

from __future__ import annotations

from . import *  # noqa: F401,F403
