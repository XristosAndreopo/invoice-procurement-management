"""
app/bootstrap/navigation.py

Sidebar navigation configuration and presentation-only visibility helpers.

PURPOSE
-------
This module centralizes application navigation metadata and the logic that
decides which navigation items are visible to the current user.

WHY THIS FILE EXISTS
--------------------
Previously, navigation metadata and filtering logic lived inside
`app/__init__.py`. That made the application factory file responsible for both:

- application bootstrapping
- UI navigation presentation rules

Those are different responsibilities.

This module keeps navigation concerns isolated so that:
- `app/__init__.py` stays focused on application creation
- sidebar structure becomes easier to maintain
- visibility logic can evolve independently from app bootstrapping

IMPORTANT SECURITY NOTE
-----------------------
Navigation filtering is PRESENTATION ONLY.

Showing or hiding a menu item does NOT grant or deny access by itself.
Real authorization must continue to be enforced in route handlers,
decorators, and security helpers.

CURRENT MODEL
-------------
The application groups sidebar items into sections. Each section may require
authentication, and each item may define extra visibility rules such as:

- admin_only
- endpoint-specific custom visibility rules

PUBLIC API
----------
This module exposes:

- NAV_SECTIONS
- is_nav_item_visible(item)
- build_visible_nav_sections()

The context processor in bootstrap code should call `build_visible_nav_sections()`
and inject its result into templates.

PERFORMANCE INSTRUMENTATION
---------------------------
This module includes lightweight request-local timing/mark instrumentation for:
- item-level visibility checks
- full navigation tree building

IMPORTANT
---------
The instrumentation is observability-only:
- no authorization changes
- no visibility-rule changes
- no navigation contract changes
"""

from __future__ import annotations

import time

from flask import g, has_request_context
from flask_login import current_user


def _current_request_timing():
    """
    Return the active request timing collector when available.

    RETURNS
    -------
    RequestInstrumentation | None
        The request-local collector stored on Flask's `g`, or None when
        instrumentation is unavailable or the call happens outside request
        context.

    WHY THIS HELPER EXISTS
    ----------------------
    Navigation code is used from template context processors and must remain
    safe even when instrumentation is absent.
    """
    if not has_request_context():
        return None
    return getattr(g, "request_timing", None)


# -------------------------------------------------------------------
# NAVIGATION STRUCTURE (presentation only; real auth is server-side)
# -------------------------------------------------------------------
NAV_SECTIONS = [
    {
        "key": "procurements",
        "label": "Προμήθειες",
        "auth_required": True,
        "items": [
            {
                "label": "Λίστα Προμηθειών (μη εγκεκριμένες)",
                "endpoint": "procurements.inbox_procurements",
                "admin_only": False,
            },
            {
                "label": "Εκκρεμείς Δαπάνες",
                "endpoint": "procurements.pending_expenses",
                "admin_only": False,
            },
            {
                "label": "Όλες οι Προμήθειες",
                "endpoint": "procurements.all_procurements",
                "admin_only": False,
            },
        ],
    },
    {
        "key": "settings",
        "label": "Ρυθμίσεις",
        "auth_required": True,
        "items": [
            # ---------------------------------------------------------
            # ΔΕΔΟΜΕΝΑ
            # ---------------------------------------------------------
            {"type": "header", "label": "Δεδομένα"},
            {
                "label": "Προμηθευτές",
                "endpoint": "settings.suppliers_list",
                "admin_only": True,
            },
            {
                "label": "Κατάσταση",
                "endpoint": "settings.options_status",
                "admin_only": True,
            },
            {
                "label": "Στάδιο",
                "endpoint": "settings.options_stage",
                "admin_only": True,
            },
            {
                "label": "Κατανομή",
                "endpoint": "settings.options_allocation",
                "admin_only": True,
            },
            {
                "label": "Τριμηνιαία",
                "endpoint": "settings.options_quarterly",
                "admin_only": True,
            },
            {
                "label": "ΦΠΑ",
                "endpoint": "settings.options_vat",
                "admin_only": True,
            },
            {
                "label": "Φόρος Εισοδήματος",
                "endpoint": "settings.income_tax_rules",
                "admin_only": True,
            },
            {
                "label": "Κρατήσεις",
                "endpoint": "settings.withholding_profiles",
                "admin_only": True,
            },
            {
                "label": "Επιτροπές Προμηθειών",
                "endpoint": "settings.committees",
                "admin_only": False,
            },
            {
                "label": "ΑΛΕ-ΚΑΕ",
                "endpoint": "settings.ale_kae",
                "admin_only": True,
            },
            {
                "label": "CPV",
                "endpoint": "settings.cpv",
                "admin_only": True,
            },

            # ---------------------------------------------------------
            # ΟΡΓΑΝΙΣΜΟΣ
            # ---------------------------------------------------------
            {"type": "header", "label": "Οργανισμός"},
            {
                "label": "Υπηρεσίες",
                "endpoint": "settings.service_units_list",
                "admin_only": True,
            },
            {
                "label": "Προσωπικό",
                "endpoint": "admin.personnel_list",
                "admin_only": False,
            },
            {
                "label": "Ορισμός Deputy/Manager",
                "endpoint": "settings.service_units_roles_list",
                "admin_only": True,
            },
            {
                "label": "Οργάνωση Υπηρεσίας",
                "endpoint": "admin.organization_setup",
                "admin_only": False,
            },
            {
                "label": "Χρήστες",
                "endpoint": "users.list_users",
                "admin_only": True,
            },

            # ---------------------------------------------------------
            # ΠΑΡΑΠΟΝΑ / ΠΡΟΤΑΣΕΙΣ
            # ---------------------------------------------------------
            {"type": "header", "label": "Παράπονα/Προτάσεις"},
            {
                "label": "Παράπονα/Προτάσεις",
                "endpoint": "settings.feedback",
                "admin_only": False,
            },
            {
                "label": "Διαχείριση Παραπόνων/Προτάσεων",
                "endpoint": "settings.feedback_admin",
                "admin_only": True,
            },

            # ---------------------------------------------------------
            # ΛΟΙΠΕΣ ΡΥΘΜΙΣΕΙΣ
            # ---------------------------------------------------------
            {"type": "header", "label": "Λοιπές Ρυθμίσεις"},
            {
                "label": "Θέμα Εμφάνισης",
                "endpoint": "settings.theme",
                "admin_only": False,
            },
        ],
    },
]


def is_nav_item_visible(item: dict) -> bool:
    """
    Determine whether a navigation item should be visible for the current user.

    IMPORTANT
    ---------
    This function controls only what is shown in the sidebar.
    It does NOT grant permission. Real security is still enforced in routes.

    VISIBILITY RULES
    ----------------
    - Section headers are always visible if their group survives filtering.
    - admin_only items are visible only to authenticated admins.
    - Certain endpoints have custom visibility rules.

    PARAMETERS
    ----------
    item:
        A navigation item dict from NAV_SECTIONS.

    RETURNS
    -------
    bool
        True if the item should be shown in the sidebar for the current user.

    PERFORMANCE NOTE
    ----------------
    This function emits request-local timing and lightweight metadata logs when
    global request instrumentation is active. It does not alter visibility
    behavior.
    """
    request_timing = _current_request_timing()
    started_at = time.perf_counter()

    item_type = item.get("type")
    endpoint = item.get("endpoint")

    try:
        if item_type == "header":
            return True

        if item.get("admin_only", False):
            if not (current_user.is_authenticated and current_user.is_admin):
                return False

        # Committees: visible to admin OR manager/deputy
        if endpoint == "settings.committees":
            return bool(
                current_user.is_authenticated
                and (current_user.is_admin or current_user.can_manage())
            )

        # Consolidated organization page:
        # visible to admin OR manager (not deputy)
        if endpoint == "admin.organization_setup":
            if not current_user.is_authenticated:
                return False
            if current_user.is_admin:
                return True
            is_mgr = getattr(current_user, "is_manager", None)
            return bool(callable(is_mgr) and is_mgr())

        # Personnel list:
        # visible to admin OR manager (not deputy)
        if endpoint == "admin.personnel_list":
            if not current_user.is_authenticated:
                return False
            if current_user.is_admin:
                return True
            is_mgr = getattr(current_user, "is_manager", None)
            return bool(callable(is_mgr) and is_mgr())

        return True
    finally:
        if request_timing is not None:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
            item_key = endpoint or item.get("label") or item_type or "unknown"
            request_timing.add_timing(f"nav_item:{item_key}", elapsed_ms)


def build_visible_nav_sections() -> list[dict]:
    """
    Build the navigation tree filtered by the current user.

    UX RULE
    -------
    A header is rendered only if at least one visible child item exists under it.

    RETURNS
    -------
    list[dict]
        The final sidebar sections to inject into templates.

    PERFORMANCE NOTE
    ----------------
    This function emits request-local timing/marks when available, but does not
    alter the resulting navigation structure.
    """
    request_timing = _current_request_timing()
    started_at = time.perf_counter()

    visible_sections: list[dict] = []
    sections_seen = 0
    items_seen = 0
    visible_items_count = 0
    headers_rendered = 0

    try:
        for section in NAV_SECTIONS:
            sections_seen += 1

            if section.get("auth_required", False) and not current_user.is_authenticated:
                continue

            section_items = section.get("items", [])
            built_items: list[dict] = []

            current_header: dict | None = None
            current_group: list[dict] = []

            def _flush_group() -> None:
                """
                Flush the current header-group pair into built_items.

                Behavior:
                - If there is no header, append the group directly.
                - If there is a header, append the header only when there is at least
                  one visible non-header child item in that group.
                """
                nonlocal current_header, current_group, built_items, headers_rendered

                if current_header is None:
                    built_items.extend(current_group)
                else:
                    if any(i.get("type") != "header" for i in current_group):
                        built_items.append(current_header)
                        built_items.extend(current_group)
                        headers_rendered += 1

                current_header = None
                current_group = []

            for item in section_items:
                items_seen += 1

                if item.get("type") == "header":
                    _flush_group()
                    current_header = item
                    current_group = []
                    continue

                if not is_nav_item_visible(item):
                    continue

                current_group.append(item)
                visible_items_count += 1

            _flush_group()

            if built_items:
                visible_sections.append(
                    {
                        "key": section["key"],
                        "label": section["label"],
                        "items": built_items,
                    }
                )

        return visible_sections
    finally:
        if request_timing is not None:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
            request_timing.add_timing("build_visible_nav_sections", elapsed_ms)
            request_timing.mark("nav_sections_seen", sections_seen)
            request_timing.mark("nav_items_seen", items_seen)
            request_timing.mark("nav_visible_items", visible_items_count)
            request_timing.mark("nav_headers_rendered", headers_rendered)
            request_timing.mark("nav_visible_sections", len(visible_sections))