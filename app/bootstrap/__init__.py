"""
app/bootstrap/__init__.py

Application bootstrap helpers for the Invoice / Procurement Management System.

PURPOSE
-------
This package contains the wiring logic that prepares a Flask application after
the Flask app object is created and configuration is loaded.

WHY THIS PACKAGE EXISTS
-----------------------
Previously, application bootstrap code lived directly in `app/__init__.py`.
That made the application factory responsible for too many unrelated concerns.

This package centralizes bootstrap orchestration so that:

- `app/__init__.py` stays small and focused
- app wiring is easy to locate
- navigation injection stays grouped with bootstrap concerns

PUBLIC API
----------
- init_extensions(app)
- configure_login(app)
- register_blueprints(app)
- register_request_hooks(app)
- register_context_processors(app)
- register_cli_commands(app)
- register_root_routes(app)
- configure_app(app)
"""

from __future__ import annotations

import click
from flask import Flask, redirect, url_for
from flask_login import current_user

from ..extensions import csrf, db, login_manager, migrate
from ..security import viewer_readonly_guard
from .navigation import build_visible_nav_sections


def init_extensions(app: Flask) -> None:
    """
    Initialize Flask extensions for the application.
    """
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)


def configure_login(app: Flask) -> None:
    """
    Configure Flask-Login and user loading.
    """
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id: str):
        from ..models import User

        try:
            return User.query.get(int(user_id))
        except Exception:
            return None


def register_blueprints(app: Flask) -> None:
    """
    Register all application blueprints.
    """
    from ..blueprints.admin.routes import admin_bp
    from ..blueprints.auth.routes import auth_bp
    from ..blueprints.procurements.routes import procurements_bp
    from ..blueprints.settings.routes import settings_bp
    from ..blueprints.users import users_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(procurements_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(admin_bp)


def register_cli_commands(app: Flask) -> None:
    """
    Register Flask CLI commands.
    """

    @app.cli.command("seed-options")
    def seed_options_command():
        from ..seed import seed_default_options

        seed_default_options()
        click.echo("Default dropdown options seeded.")


def register_request_hooks(app: Flask) -> None:
    """
    Register global request hooks.
    """

    @app.before_request
    def _viewer_guard_hook():
        result = viewer_readonly_guard()
        if result is not None:
            return result
        return None


def register_context_processors(app: Flask) -> None:
    """
    Register context processors for templates.
    """

    @app.context_processor
    def inject_globals():
        return {
            "config": app.config,
            "nav_sections": build_visible_nav_sections(),
        }


def register_root_routes(app: Flask) -> None:
    """
    Register application-level routes.
    """

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("procurements.inbox_procurements"))
        return redirect(url_for("auth.login"))


def configure_app(app: Flask) -> None:
    """
    Run the full application bootstrap sequence.
    """
    init_extensions(app)
    configure_login(app)
    register_request_hooks(app)
    register_blueprints(app)
    register_context_processors(app)
    register_cli_commands(app)
    register_root_routes(app)


__all__ = [
    "init_extensions",
    "configure_login",
    "register_blueprints",
    "register_request_hooks",
    "register_context_processors",
    "register_cli_commands",
    "register_root_routes",
    "configure_app",
]