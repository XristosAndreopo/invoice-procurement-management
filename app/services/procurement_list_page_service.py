"""
app/services/procurement_list_page_service.py

Procurement list page service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.procurement.list_pages`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.procurement.list_pages import *  # noqa: F401,F403
