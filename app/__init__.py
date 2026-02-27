"""
app/__init__.py

Flask application factory for the Invoice / Procurement Management System.

Enterprise requirements:
- Production mindset: clear architecture, stable imports, defensive security.
- PostgreSQL-ready (SQLAlchemy + migrations) but SQLite is used for dev.
- UI is never trusted; server-side access control is enforced.

Navigation:
- Sidebar contains exactly 2 sections:
  1) Προμήθειες
  2) Διαχείριση
Items are filtered for visibility, BUT all permissions are enforced server-side.
"""

from __future__ import annotations

import click
from flask import Flask, redirect, url_for
from flask_login import current_user

from .extensions import csrf, db, login_manager, migrate
from .models import User
from .security import viewer_readonly_guard

# Blueprint imports kept inside create_app() where possible to reduce import side effects.


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
        "key": "management",
        "label": "Διαχείριση",
        "auth_required": True,
        # visible to all logged-in users, items filtered below
        "items": [
            # --- Admin-only master data ---
            {"label": "Προσωπικό", "endpoint": "admin.personnel_list", "admin_only": True},
            {"label": "Χρήστες", "endpoint": "users.list_users", "admin_only": True},
            {"label": "Υπηρεσίες", "endpoint": "settings.service_units_list", "admin_only": True},
            {"label": "Προμηθευτές", "endpoint": "settings.suppliers_list", "admin_only": True},
            # --- Option lists (Admin-only) ---
            {"label": "Κατάσταση", "endpoint": "settings.options_status", "admin_only": True},
            {"label": "Στάδιο", "endpoint": "settings.options_stage", "admin_only": True},
            {"label": "Κατανομή", "endpoint": "settings.options_allocation", "admin_only": True},
            {"label": "Τριμηνιαία", "endpoint": "settings.options_quarterly", "admin_only": True},
            {"label": "ΦΠΑ", "endpoint": "settings.options_vat", "admin_only": True},
            {"label": "Κρατήσεις", "endpoint": "settings.options_withholdings", "admin_only": True},
            # --- Committees (Manager + Admin) ---
            {"label": "Επιτροπές Προμηθειών", "endpoint": "settings.options_committees", "admin_only": False},
            # --- User utilities (All users) ---
            {"label": "Θέμα Εμφάνισης", "endpoint": "settings.theme", "admin_only": False},
            {"label": "Παράπονα/Αναφορά", "endpoint": "settings.feedback", "admin_only": False},
            # --- Feedback management (Admin-only) ---
            {"label": "Διαχείριση Παραπόνων", "endpoint": "settings.feedback_admin", "admin_only": True},
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
        """Load user for Flask-Login."""
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
        - This only filters visibility. Routes enforce permissions.
        """
        visible_sections = []

        for section in NAV_SECTIONS:
            if section.get("auth_required", False) and not current_user.is_authenticated:
                continue

            visible_items = []
            for item in section.get("items", []):
                if item.get("admin_only", False):
                    if not (current_user.is_authenticated and current_user.is_admin):
                        continue

                # Committees: allowed for manager+admin
                if item["endpoint"] == "settings.options_committees":
                    if not (
                        current_user.is_authenticated
                        and (current_user.is_admin or current_user.can_manage())
                    ):
                        continue

                visible_items.append(item)

            if visible_items:
                visible_sections.append(
                    {"key": section["key"], "label": section["label"], "items": visible_items}
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
        """Home: redirect to inbox or login."""
        if current_user.is_authenticated:
            return redirect(url_for("procurements.inbox_procurements"))
        return redirect(url_for("auth.login"))

    return app