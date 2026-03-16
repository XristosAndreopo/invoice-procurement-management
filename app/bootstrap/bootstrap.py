"""
app/bootstrap.py

Application bootstrap helpers for the Invoice / Procurement Management System.

PURPOSE
-------
This module contains the wiring logic that prepares a Flask application after
the application object is created and configuration is loaded.

WHY THIS FILE EXISTS
--------------------
Previously, `app/__init__.py` contained:
- extension initialization
- Flask-Login setup
- blueprint registration
- request hooks
- context processors
- CLI registration
- root route registration

That made the application factory file harder to scan and made bootstrap code
mixed with unrelated concerns such as navigation metadata.

This module keeps bootstrap orchestration in one place while allowing
`app/__init__.py` to remain a small entrypoint.

DESIGN GOALS
------------
- Keep behavior unchanged
- Reduce the size and responsibility of `app/__init__.py`
- Keep imports stable and explicit
- Avoid route/business logic in the application factory
- Keep bootstrapping steps easy to test and extend

PUBLIC API
----------
This module exposes:

- init_extensions(app)
- configure_login(app)
- register_blueprints(app)
- register_request_hooks(app)
- register_context_processors(app)
- register_cli_commands(app)
- register_root_routes(app)
- configure_app(app)

The recommended usage from `app/__init__.py` is:

    app = Flask(__name__)
    app.config.from_object("config.Config")
    configure_app(app)

SECURITY NOTES
--------------
- Navigation injection is presentation-only
- Viewer guard is a safety net, not a replacement for route security
- Real authorization remains server-side in routes and services
"""

from __future__ import annotations

import click
from flask import Flask, redirect, url_for
from flask_login import current_user

from ..extensions import csrf, db, login_manager, migrate
from navigation import build_visible_nav_sections
from ..security import viewer_readonly_guard


def init_extensions(app: Flask) -> None:
    """
    Initialize Flask extensions.

    PARAMETERS
    ----------
    app:
        The Flask application instance.
    """
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)


def configure_login(app: Flask) -> None:
    """
    Configure Flask-Login and user loading.

    PARAMETERS
    ----------
    app:
        The Flask application instance.

    NOTES
    -----
    The user loader imports User lazily to keep the bootstrap module light and
    to reduce unnecessary import coupling at module import time.
    """
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id: str):
        """
        Load the logged-in user for Flask-Login.

        SECURITY / STABILITY
        --------------------
        Any exception returns None instead of failing the request lifecycle.
        """
        from ..models import User

        try:
            return User.query.get(int(user_id))
        except Exception:
            return None


def register_blueprints(app: Flask) -> None:
    """
    Register all application blueprints.

    PARAMETERS
    ----------
    app:
        The Flask application instance.
    """
    from ..blueprints.auth.routes import auth_bp
    from ..blueprints.procurements.routes import procurements_bp
    from ..blueprints.settings.routes import settings_bp
    from ..blueprints.users import users_bp
    from ..blueprints.admin.routes import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(procurements_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(admin_bp)


def register_cli_commands(app: Flask) -> None:
    """
    Register Flask CLI commands.

    PARAMETERS
    ----------
    app:
        The Flask application instance.
    """

    @app.cli.command("seed-options")
    def seed_options_command():
        """
        Seed default dropdown options and enterprise master-data.
        """
        from ..seed import seed_default_options

        seed_default_options()
        click.echo("Default dropdown options seeded.")


def register_request_hooks(app: Flask) -> None:
    """
    Register global request hooks.

    CURRENT HOOKS
    -------------
    - Viewer read-only enforcement

    IMPORTANT
    ---------
    This is a safety net, not the primary authorization mechanism.
    Routes must still enforce their own security checks.

    PARAMETERS
    ----------
    app:
        The Flask application instance.
    """

    @app.before_request
    def _viewer_guard_hook():
        """
        Block unsafe mutating requests for read-only viewer users.
        """
        result = viewer_readonly_guard()
        if result is not None:
            return result
        return None


def register_context_processors(app: Flask) -> None:
    """
    Register context processors for templates.

    Currently injects:
    - config
    - filtered navigation sections

    PARAMETERS
    ----------
    app:
        The Flask application instance.
    """

    @app.context_processor
    def inject_globals():
        """
        Inject global template context.

        SECURITY NOTE
        -------------
        Navigation is visibility-only.
        Route handlers remain the source of truth for authorization.
        """
        return {
            "config": app.config,
            "nav_sections": build_visible_nav_sections(),
        }


def register_root_routes(app: Flask) -> None:
    """
    Register simple application-level routes.

    PARAMETERS
    ----------
    app:
        The Flask application instance.
    """

    @app.route("/")
    def index():
        """
        Home route.

        Behavior:
        - Authenticated users -> procurement inbox
        - Anonymous users -> login page
        """
        if current_user.is_authenticated:
            return redirect(url_for("procurements.inbox_procurements"))
        return redirect(url_for("auth.login"))


def configure_app(app: Flask) -> None:
    """
    Run the full application bootstrap sequence.

    BOOTSTRAP FLOW
    --------------
    1. Initialize extensions
    2. Configure Flask-Login
    3. Register request hooks
    4. Register blueprints
    5. Register context processors
    6. Register CLI commands
    7. Register root routes

    PARAMETERS
    ----------
    app:
        The Flask application instance.
    """
    init_extensions(app)
    configure_login(app)
    register_request_hooks(app)
    register_blueprints(app)
    register_context_processors(app)
    register_cli_commands(app)
    register_root_routes(app)