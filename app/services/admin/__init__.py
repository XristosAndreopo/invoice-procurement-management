"""
app/services/admin/__init__.py

Canonical admin service package.

This package contains non-HTTP orchestration used by the admin blueprint.
"""

from __future__ import annotations

from .organization_setup import *  # noqa: F401,F403
from .personnel import *  # noqa: F401,F403
