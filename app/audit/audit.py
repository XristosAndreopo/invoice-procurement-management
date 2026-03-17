"""
app/audit/audit.py

Legacy audit compatibility facade.

PURPOSE
-------
This file preserves the historical module path `app.audit.audit` while
`app.audit` remains the canonical public facade.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add audit logic here.
- Import from `app.audit` in all new code.
"""

from __future__ import annotations

from . import *  # noqa: F401,F403
