"""
app/utils.py

Backward-compatible utility facade.

PURPOSE
-------
This module remains as a stable import surface for older code that imports
small shared helpers from `app.utils`.

CURRENT POLICY
--------------
`app.utils` should NOT become a generic dumping ground.

Presentation-oriented helpers now live in:
    app.presentation

Database-backed lookups already live in:
    app.services.master_data_service

WHY THIS FILE STILL EXISTS
--------------------------
The project may still contain imports such as:

    from app.utils import procurement_row_class

To avoid unnecessary churn during the refactor, this module re-exports the
public helper while keeping its role intentionally small.

CURRENT CONTENTS
----------------
- procurement_row_class:
    Presentation helper for procurement row CSS styling
"""

from __future__ import annotations

from .presentation import procurement_row_class

__all__ = ["procurement_row_class"]