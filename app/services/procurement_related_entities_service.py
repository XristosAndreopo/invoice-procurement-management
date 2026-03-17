"""
app/services/procurement_related_entities_service.py

Procurement related-entities service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.procurement.related_entities`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.procurement.related_entities import *  # noqa: F401,F403
