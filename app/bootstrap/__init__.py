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

PERFORMANCE INSTRUMENTATION
---------------------------
This bootstrap module now also wires lightweight structured timing logs for:

- whole-request timing
- Flask-Login user loader timing
- context processor timing
- navigation build timing

IMPORTANT
---------
These additions are instrumentation-only:
- no authorization changes
- no query changes
- no response-body changes
- no template-context contract changes

Any SQL query counting / slow-query logging must be attached separately at the
SQLAlchemy engine layer.
"""

from __future__ import annotations

import time

import click
from flask import Flask, g, has_request_context, redirect, request, url_for
from flask_login import current_user

from ..extensions import csrf, db, login_manager, migrate, register_sqlalchemy_instrumentation
from ..reports.instrumentation import begin_request_timing
from ..security import viewer_readonly_guard
from .navigation import build_visible_nav_sections


def _current_request_timing():
    """
    Return the active request timing collector from Flask's request-local `g`.

    RETURNS
    -------
    RequestInstrumentation | None
        The active collector when present, otherwise None.

    WHY THIS HELPER EXISTS
    ----------------------
    Bootstrap-level instrumentation is optional and must never raise just
    because a timing collector is missing or a call happens outside request
    context.
    """
    if not has_request_context():
        return None
    return getattr(g, "request_timing", None)


def init_extensions(app: Flask) -> None:
    """
    Initialize Flask extensions for the application.
    """
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    register_sqlalchemy_instrumentation(app)


def configure_login(app: Flask) -> None:
    """
    Configure Flask-Login and user loading.
    """
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id: str):
        """
        Load the authenticated user for Flask-Login.

        PERFORMANCE NOTE
        ----------------
        This function is instrumented to expose the timing cost of user loading.
        It intentionally preserves the existing query behavior and exception
        handling semantics.
        """
        from ..models import User

        request_timing = _current_request_timing()
        started_at = time.perf_counter()

        try:
            return User.query.get(int(user_id))
        except Exception:
            return None
        finally:
            if request_timing is not None:
                request_timing.add_timing(
                    "user_loader",
                    round((time.perf_counter() - started_at) * 1000.0, 2),
                )


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

    HOOKS INSTALLED
    ---------------
    - before_request:
        creates a request-local timing collector and runs the existing viewer
        readonly guard

    - after_request:
        emits one structured request summary timing log

    IMPORTANT
    ---------
    These hooks are instrumentation-only and preserve existing behavior.
    """

    @app.before_request
    def _request_timing_start():
        """
        Create one request-local timing collector for the active request.
        """
        g.request_timing = begin_request_timing()
        g.request_started_at = time.perf_counter()

    @app.before_request
    def _viewer_guard_hook():
        """
        Preserve the existing readonly guard behavior.

        The guard remains functionally unchanged; only the elapsed timing is
        recorded when request instrumentation is active.
        """
        request_timing = _current_request_timing()
        started_at = time.perf_counter()

        try:
            result = viewer_readonly_guard()
            if result is not None:
                return result
            return None
        finally:
            if request_timing is not None:
                request_timing.add_timing(
                    "viewer_readonly_guard",
                    round((time.perf_counter() - started_at) * 1000.0, 2),
                )

    @app.after_request
    def _request_timing_finish(response):
        """
        Emit one structured request timing summary after the response is built.

        LOGGING POLICY
        --------------
        - INFO for ordinary requests
        - WARNING for obviously slow requests

        This does not alter the response object.
        """
        request_timing = _current_request_timing()
        if request_timing is None:
            return response

        total_ms = request_timing.finish(
            status_code=response.status_code,
        )

        log_payload = {
            "trace_id": request_timing.trace_id,
            "method": request.method if has_request_context() else None,
            "path": request.path if has_request_context() else None,
            "endpoint": request.endpoint if has_request_context() else None,
            "status_code": response.status_code,
            "total_ms": total_ms,
            "sql_query_count": getattr(request_timing, "sql_query_count", 0),
            "sql_total_ms": getattr(request_timing, "sql_total_ms", 0.0),
        }

        if total_ms >= 800:
            app.logger.warning("HTTP_REQUEST_SLOW %s", log_payload)
        else:
            app.logger.info("HTTP_REQUEST %s", log_payload)

        return response


def register_context_processors(app: Flask) -> None:
    """
    Register context processors for templates.
    """

    @app.context_processor
    def inject_globals():
        """
        Inject application-wide template globals.

        PERFORMANCE NOTE
        ----------------
        This context processor is instrumented because it runs broadly across
        rendered pages and may contribute to request-wide overhead.
        """
        request_timing = _current_request_timing()

        context_started_at = time.perf_counter()
        nav_started_at = time.perf_counter()
        nav_sections = build_visible_nav_sections()
        nav_elapsed_ms = round((time.perf_counter() - nav_started_at) * 1000.0, 2)

        if request_timing is not None:
            request_timing.add_timing("navigation_build", nav_elapsed_ms)
            request_timing.add_timing(
                "context_processor.inject_globals",
                round((time.perf_counter() - context_started_at) * 1000.0, 2),
            )
            request_timing.mark("nav_sections_count", len(nav_sections))

        return {
            "config": app.config,
            "nav_sections": nav_sections,
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