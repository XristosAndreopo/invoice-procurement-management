"""
Application factory.

Enterprise navigation:
- Sidebar contains only:
  1) Προμήθειες
  2) Διαχείριση

All admin/master data pages live under "Διαχείριση".
Theme/Feedback are also listed under "Διαχείριση" as requested.
"""

from flask import Flask, redirect, url_for
from flask_login import current_user
import click

from .extensions import db, migrate, login_manager, csrf
from .models import User
from .blueprints.users import users_bp
from .blueprints.admin.routes import admin_bp

# -------------------------------------------------------------------
# NAVIGATION STRUCTURE
# -------------------------------------------------------------------
NAV_SECTIONS = [
    {
        "key": "procurements",
        "label": "Προμήθειες",
        "auth_required": True,
        "admin_only": False,
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
        "key": "admin",
        "label": "Διαχείριση",
        "auth_required": True,
        "admin_only": False,  # visible to all logged-in users, items filtered below
        "items": [
            # --- Admin-only ---
            {"label": "Προσωπικό", "endpoint": "admin.personnel_list", "admin_only": True},
            {"label": "Χρήστες", "endpoint": "users.list_users", "admin_only": True},
            {"label": "Υπηρεσίες", "endpoint": "settings.service_units_list", "admin_only": True},
            {"label": "Προμηθευτές", "endpoint": "settings.suppliers_list", "admin_only": True},

            # Option lists (Admin-only)
            {"label": "Κατάσταση", "endpoint": "settings.options_status", "admin_only": True},
            {"label": "Στάδιο", "endpoint": "settings.options_stage", "admin_only": True},
            {"label": "Κατανομή", "endpoint": "settings.options_allocation", "admin_only": True},
            {"label": "Τριμηνιαία", "endpoint": "settings.options_quarterly", "admin_only": True},
            {"label": "ΦΠΑ", "endpoint": "settings.options_vat", "admin_only": True},
            {"label": "Κρατήσεις", "endpoint": "settings.options_withholdings", "admin_only": True},

            # Committees (Manager + Admin)
            {"label": "Επιτροπές Προμηθειών", "endpoint": "settings.options_committees", "admin_only": False},

            # User utilities (All users)
            {"label": "Θέμα Εμφάνισης", "endpoint": "settings.theme", "admin_only": False},
            {"label": "Παράπονα/Αναφορά", "endpoint": "settings.feedback", "admin_only": False},

            # Feedback management (Admin-only)
            {"label": "Διαχείριση Παραπόνων", "endpoint": "settings.feedback_admin", "admin_only": True},
        ],
    },
]


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object("config.Config")

    app.register_blueprint(users_bp)
    app.register_blueprint(admin_bp)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        """Load user for Flask-Login."""
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_globals():
        """
        Inject navigation filtered by user.

        SECURITY NOTE:
        This filters only what is shown. Routes enforce permissions.
        """
        visible_sections = []

        for section in NAV_SECTIONS:
            if section.get("auth_required", False) and not current_user.is_authenticated:
                continue

            # Build visible items
            visible_items = []
            for item in section.get("items", []):
                if item.get("admin_only", False):
                    if not (current_user.is_authenticated and current_user.is_admin):
                        continue
                # committees: allowed for manager+admin
                if item["endpoint"] == "settings.options_committees":
                    if not (current_user.is_authenticated and (current_user.is_admin or current_user.can_manage())):
                        continue

                visible_items.append(item)

            if not visible_items:
                continue

            visible_sections.append(
                {"key": section["key"], "label": section["label"], "items": visible_items}
            )

        return {"config": app.config, "nav_sections": visible_sections}

    from .blueprints.auth.routes import auth_bp
    from .blueprints.procurements.routes import procurements_bp
    from .blueprints.settings.routes import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(procurements_bp)
    app.register_blueprint(settings_bp)

    @app.cli.command("seed-options")
    def seed_options_command():
        """Seed default dropdown options."""
        from .seed import seed_default_options
        seed_default_options()
        click.echo("Default dropdown options seeded.")

    @app.route("/")
    def index():
        """Home: redirect to inbox or login."""
        if current_user.is_authenticated:
            return redirect(url_for("procurements.inbox_procurements"))
        return redirect(url_for("auth.login"))

    return app