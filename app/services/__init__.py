"""
app/services/__init__.py

Canonical services package.

PURPOSE
-------
This package groups application services by domain while preserving the
existing project policy of function-first orchestration.

PACKAGE GROUPS
--------------
- app.services.admin
- app.services.organization
- app.services.procurement
- app.services.settings
- app.services.shared

IMPORTANT
---------
This file intentionally exports no large wildcard public API.
Callers should import from the concrete canonical module they need.
"""

from __future__ import annotations
