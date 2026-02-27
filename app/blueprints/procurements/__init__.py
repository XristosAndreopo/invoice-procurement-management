"""
app/blueprints/procurements/__init__.py

Blueprint package export.

IMPORTANT:
- Must expose procurements_bp for app factory registration.
- Keep import minimal to avoid side effects.
"""

from __future__ import annotations

from .routes import procurements_bp  # noqa: F401