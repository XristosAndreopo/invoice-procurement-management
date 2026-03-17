"""
app/services/settings_master_data_admin_service.py

Settings master-data admin service compatibility facade.

PURPOSE
-------
This file preserves the historical flat import surface while the canonical
implementation now lives in `app.services.settings.master_data_admin`.

POLICY
------
- Keep this file as a pure re-export facade.
- Do not add new logic here.
- Prefer importing the canonical module in all new code.
"""

from __future__ import annotations

from app.services.settings.master_data_admin import *  # noqa: F401,F403
