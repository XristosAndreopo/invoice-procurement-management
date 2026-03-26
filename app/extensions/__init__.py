"""
app/extensions/__init__.py

Central Flask extension registry for the Invoice / Procurement Management
System.

PURPOSE
-------
This package defines the extension singletons used across the application.

DESIGN RULE
-----------
This module must remain a pure registry.

It may:
- instantiate Flask extension objects
- expose them for import elsewhere

It must NOT:
- initialize extensions with an app
- contain configuration logic
- contain business logic
- contain route logic

PERFORMANCE INSTRUMENTATION
---------------------------
This module now also provides optional SQLAlchemy engine listener helpers for:

- per-request SQL query counting
- aggregate SQL execution time
- slow-query logging

IMPORTANT
---------
The listener registration helpers are safe to import from bootstrap code and do
not alter database behavior. They only observe SQL execution and emit logs.

REGISTRY POLICY
---------------
The extension singletons remain defined here exactly once. Listener attachment
is exposed as an explicit helper so bootstrap code can opt in after the app and
engine are ready.
"""

from __future__ import annotations

import time
from typing import Any

from flask import current_app, g, has_request_context, request
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

# Default threshold for individual slow SQL statement logs.
#
# Chosen to be visible enough for PythonAnywhere-style latency debugging while
# avoiding excessive noise from very small statements.
_SLOW_SQL_THRESHOLD_MS = 100.0


def _compact_sql(statement: str | None, *, max_length: int = 500) -> str:
    """
    Compact a SQL statement into one log-friendly single-line preview.

    PARAMETERS
    ----------
    statement:
        Raw SQL statement string.
    max_length:
        Maximum number of characters to keep in the preview.

    RETURNS
    -------
    str
        Whitespace-normalized SQL preview, safely truncated when necessary.

    WHY THIS HELPER EXISTS
    ----------------------
    Slow-query logs should remain readable and bounded. Full raw SQL payloads
    can be excessively large and noisy in production logs.
    """
    if not statement:
        return ""

    compact = " ".join(str(statement).split())
    if len(compact) <= max_length:
        return compact
    return compact[: max_length - 1] + "…"


def _current_request_timing():
    """
    Return the active request timing collector from Flask's request-local `g`.

    RETURNS
    -------
    RequestInstrumentation | None
        The active request collector when present, otherwise None.

    WHY THIS HELPER EXISTS
    ----------------------
    SQLAlchemy engine event listeners may run both inside and outside a Flask
    request context. Listener code must remain safe in both cases.
    """
    if not has_request_context():
        return None
    return getattr(g, "request_timing", None)


def register_sqlalchemy_instrumentation(app) -> None:
    """
    Attach SQLAlchemy engine listeners for request-local SQL timing.

    PARAMETERS
    ----------
    app:
        The Flask application instance whose SQLAlchemy engine should be
        observed.

    INSTALLED OBSERVABILITY
    -----------------------
    - statement execution timing
    - per-request query count
    - per-request aggregate SQL time
    - individual slow-query warning logs
    - SQL error timing logs

    IMPORTANT
    ---------
    This function is idempotent per process. Repeated calls will not re-register
    the listeners once attached.
    """
    if getattr(db, "_performance_instrumentation_registered", False):
        return

    with app.app_context():
        engine = db.engine

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ) -> None:
        """
        Store a perf-counter timestamp before the DBAPI cursor executes.
        """
        context._query_started_at = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ) -> None:
        """
        Record SQL execution timing and emit slow-query logs when necessary.

        REQUEST-LOCAL SIDE EFFECTS
        --------------------------
        When a Flask request timing collector exists, this listener updates:
        - sql_query_count
        - sql_total_ms

        LOGGING
        -------
        A slow individual statement emits a WARNING log but does not affect the
        request or the transaction.
        """
        started_at = getattr(context, "_query_started_at", None)
        if started_at is None:
            return

        elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 2)

        request_timing = _current_request_timing()
        if request_timing is not None:
            request_timing.increment_sql(elapsed_ms)

        if elapsed_ms >= _SLOW_SQL_THRESHOLD_MS:
            log_payload: dict[str, Any] = {
                "elapsed_ms": elapsed_ms,
                "statement_preview": _compact_sql(statement),
                "executemany": bool(executemany),
                "rowcount": getattr(cursor, "rowcount", None),
                "path": request.path if has_request_context() else None,
                "method": request.method if has_request_context() else None,
                "endpoint": request.endpoint if has_request_context() else None,
            }

            if request_timing is not None:
                log_payload["trace_id"] = request_timing.trace_id

            current_app.logger.warning("SLOW_SQL %s", log_payload)

    @event.listens_for(engine, "handle_error")
    def _handle_sql_error(exception_context) -> None:
        """
        Emit a structured SQL timing/error log when statement execution fails.

        IMPORTANT
        ---------
        This listener does not swallow or transform exceptions. It only logs.
        """
        original_exception = getattr(exception_context, "original_exception", None)
        statement = getattr(exception_context, "statement", None)
        execution_context = getattr(exception_context, "execution_context", None)

        started_at = getattr(execution_context, "_query_started_at", None)
        elapsed_ms = None
        if started_at is not None:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 2)

        log_payload: dict[str, Any] = {
            "elapsed_ms": elapsed_ms,
            "statement_preview": _compact_sql(statement),
            "path": request.path if has_request_context() else None,
            "method": request.method if has_request_context() else None,
            "endpoint": request.endpoint if has_request_context() else None,
            "error_type": type(original_exception).__name__ if original_exception else None,
            "error": str(original_exception) if original_exception else None,
        }

        request_timing = _current_request_timing()
        if request_timing is not None:
            log_payload["trace_id"] = request_timing.trace_id

        current_app.logger.warning("SQL_EXECUTION_ERROR %s", log_payload)

    db._performance_instrumentation_registered = True


__all__ = [
    "db",
    "migrate",
    "login_manager",
    "csrf",
    "register_sqlalchemy_instrumentation",
]