"""
app/security/security.py

Legacy security compatibility facade.

PURPOSE
-------
This file preserves the historical module path `app.security.security` while
`app.security` remains the canonical public security facade.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add authorization logic here.
- Import from `app.security` in all new code.
"""

from __future__ import annotations

from . import *  # noqa: F401,F403
