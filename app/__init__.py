"""
app/__init__.py

Flask application factory for the Invoice / Procurement Management System.

Enterprise requirements:
- Production mindset: clear architecture, stable imports, defensive security.
- PostgreSQL-ready (SQLAlchemy + migrations) but SQLite is used for dev.
- UI is never trusted; server-side access control is enforced.

Navigation:
- Sidebar contains:
  1) Προμήθειες
  2) Ρυθμίσεις (with grouped headings)
- Items are filtered for visibility, BUT all permissions are enforced server-side.

UPDATED NAVIGATION MODEL:
- Organizational management is now centered around the consolidated page:
  /admin/organization-setup
- Legacy structure route remains only for compatibility and redirects server-side.
"""

from __future__ import annotations

import click
from flask import Flask, redirect, url_for
from flask_login import current_user

from .extensions import csrf, db, login_manager, migrate
from .models import User
from .security import viewer_readonly_guard

# -------------------------------------------------------------------
# NAVIGATION STRUCTURE (UI visibility only; security enforced in routes)
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
            # -------------------------
            # ΔΕΔΟΜΕΝΑ
            # -------------------------
            {"type": "header", "label": "Δεδομένα"},
            {"label": "Προμηθευτές", "endpoint": "settings.suppliers_list", "admin_only": True},
            {"label": "Κατάσταση", "endpoint": "settings.options_status", "admin_only": True},
            {"label": "Στάδιο", "endpoint": "settings.options_stage", "admin_only": True},
            {"label": "Κατανομή", "endpoint": "settings.options_allocation", "admin_only": True},
            {"label": "Τριμηνιαία", "endpoint": "settings.options_quarterly", "admin_only": True},
            {"label": "ΦΠΑ", "endpoint": "settings.options_vat", "admin_only": True},
            {"label": "Φόρος Εισοδήματος", "endpoint": "settings.income_tax_rules", "admin_only": True},
            {"label": "Κρατήσεις", "endpoint": "settings.withholding_profiles", "admin_only": True},
            {"label": "Επιτροπές Προμηθειών", "endpoint": "settings.committees", "admin_only": False},
            {"label": "ΑΛΕ-ΚΑΕ", "endpoint": "settings.ale_kae", "admin_only": True},
            {"label": "CPV", "endpoint": "settings.cpv", "admin_only": True},

            # -------------------------
            # ΟΡΓΑΝΙΣΜΟΣ
            # -------------------------
            {"type": "header", "label": "Οργανισμός"},
            {"label": "Υπηρεσίες", "endpoint": "settings.service_units_list", "admin_only": True},
            {"label": "Προσωπικό", "endpoint": "admin.personnel_list", "admin_only": False},
            {"label": "Ορισμός Deputy/Manager", "endpoint": "settings.service_units_roles_list", "admin_only": True},
            {
                "label": "Οργάνωση Υπηρεσίας",
                "endpoint": "admin.organization_setup",
                "admin_only": False,
            },
            {"label": "Χρήστες", "endpoint": "users.list_users", "admin_only": True},

            # -------------------------
            # ΠΑΡΑΠΟΝΑ / ΠΡΟΤΑΣΕΙΣ
            # -------------------------
            {"type": "header", "label": "Παράπονα/Προτάσεις"},
            {"label": "Παράπονα/Προτάσεις", "endpoint": "settings.feedback", "admin_only": False},
            {"label": "Διαχείριση Παραπόνων/Προτάσεων", "endpoint": "settings.feedback_admin", "admin_only": True},

            # -------------------------
            # ΛΟΙΠΕΣ ΡΥΘΜΙΣΕΙΣ
            # -------------------------
            {"type": "header", "label": "Λοιπές Ρυθμίσεις"},
            {"label": "Θέμα Εμφάνισης", "endpoint": "settings.theme", "admin_only": False},
        ],
    },
]


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object("config.Config")

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        """
        Load user for Flask-Login.

        SECURITY:
        - Any exception returns None instead of failing the whole request.
        """
        try:
            return User.query.get(int(user_id))
        except Exception:
            return None

    # ----------------------------------------------------------------------
    # GLOBAL SECURITY NET: Viewer read-only guard (server-side).
    # ----------------------------------------------------------------------
    @app.before_request
    def _viewer_guard_hook():
        """
        Viewer read-only enforcement (POST/PUT/PATCH/DELETE blocked).

        This is a safety net. Each route must still enforce its own permissions.
        """
        result = viewer_readonly_guard()
        if result is not None:
            return result
        return None

    # ----------------------------------------------------------------------
    # Blueprints
    # ----------------------------------------------------------------------
    from .blueprints.auth.routes import auth_bp
    from .blueprints.procurements.routes import procurements_bp
    from .blueprints.settings.routes import settings_bp
    from .blueprints.users import users_bp
    from .blueprints.admin.routes import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(procurements_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(admin_bp)

    # ----------------------------------------------------------------------
    # Context globals (navigation)
    # ----------------------------------------------------------------------
    @app.context_processor
    def inject_globals():
        """
        Inject navigation filtered by user.

        SECURITY NOTE:
        - This only filters visibility.
        - Real authorization is always enforced in routes.
        """
        visible_sections = []

        def _is_item_visible(item: dict) -> bool:
            """Visibility filtering for a single nav item."""
            if item.get("type") == "header":
                return True

            if item.get("admin_only", False):
                if not (current_user.is_authenticated and current_user.is_admin):
                    return False

            endpoint = item.get("endpoint")

            # Committees: allowed for manager+admin (visibility only)
            if endpoint == "settings.committees":
                return bool(
                    current_user.is_authenticated
                    and (current_user.is_admin or current_user.can_manage())
                )

            # Consolidated organization page:
            # visible to admin OR manager (not deputy).
            if endpoint == "admin.organization_setup":
                if not current_user.is_authenticated:
                    return False
                if current_user.is_admin:
                    return True
                is_mgr = getattr(current_user, "is_manager", None)
                return bool(callable(is_mgr) and is_mgr())

            # Personnel list: visible to admin OR manager (not deputy).
            if endpoint == "admin.personnel_list":
                if not current_user.is_authenticated:
                    return False
                if current_user.is_admin:
                    return True
                is_mgr = getattr(current_user, "is_manager", None)
                return bool(callable(is_mgr) and is_mgr())

            return True

        for section in NAV_SECTIONS:
            if section.get("auth_required", False) and not current_user.is_authenticated:
                continue

            section_items = section.get("items", [])
            built_items: list[dict] = []

            current_header: dict | None = None
            current_group: list[dict] = []

            def _flush_group():
                """
                Flush the current header-group pair into the visible items.

                UX NOTE:
                - A header is rendered only if at least one visible child item exists.
                """
                nonlocal current_header, current_group, built_items
                if current_header is None:
                    built_items.extend(current_group)
                else:
                    if any(i.get("type") != "header" for i in current_group):
                        built_items.append(current_header)
                        built_items.extend(current_group)
                current_header = None
                current_group = []

            for item in section_items:
                if item.get("type") == "header":
                    _flush_group()
                    current_header = item
                    current_group = []
                    continue

                if not _is_item_visible(item):
                    continue

                current_group.append(item)

            _flush_group()

            if built_items:
                visible_sections.append(
                    {"key": section["key"], "label": section["label"], "items": built_items}
                )

        return {"config": app.config, "nav_sections": visible_sections}

    # ----------------------------------------------------------------------
    # CLI
    # ----------------------------------------------------------------------
    @app.cli.command("seed-options")
    def seed_options_command():
        """Seed default dropdown options."""
        from .seed import seed_default_options

        seed_default_options()
        click.echo("Default dropdown options seeded.")

    # ----------------------------------------------------------------------
    # Home
    # ----------------------------------------------------------------------
    @app.route("/")
    def index():
        """
        Home route.

        Behavior:
        - Authenticated users -> inbox procurements
        - Anonymous users -> login
        """
        if current_user.is_authenticated:
            return redirect(url_for("procurements.inbox_procurements"))
        return redirect(url_for("auth.login"))

    return app