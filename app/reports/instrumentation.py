"""
app/reports/instrumentation.py

Structured timing instrumentation for report-generation requests and
general HTTP request profiling.

PURPOSE
-------
This module provides lightweight, request-local timing helpers for:

1. report-generation and download endpoints
2. general Flask request timing / bootstrap timing instrumentation

It supports two main instrumentation families:

A. ReportInstrumentation
   Used by report routes/builders to capture:
   - route-level stage timings
   - deep builder-level detail timings

B. RequestInstrumentation
   Used by generic request/bootstrap hooks to capture:
   - whole-request duration
   - named timing parts such as:
     - user_loader
     - context_processor
     - navigation_build
     - list_context_build
   - optional SQL counters populated elsewhere

DESIGN GOALS
------------
- zero behavior change
- no dependency on external APM tooling
- structured logs via Flask's standard app logger
- safe to leave enabled in production
- easy to extend later
- request-local only
- must not swallow exceptions

IMPORTANT BOUNDARY
------------------
This module must NOT:
- query the database
- mutate domain state
- affect authorization
- swallow exceptions

It only measures and emits timing metadata.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from flask import current_app, has_request_context, request


def _now() -> float:
    """
    Return a monotonic timestamp suitable for duration measurement.
    """
    return time.perf_counter()


def _ms(start: float, end: float) -> float:
    """
    Convert two perf-counter timestamps to milliseconds.
    """
    return round((end - start) * 1000.0, 2)


def _request_path() -> str | None:
    """
    Return the active request path when a request context exists.
    """
    if not has_request_context():
        return None
    return request.path


def _request_method() -> str | None:
    """
    Return the active request method when a request context exists.
    """
    if not has_request_context():
        return None
    return request.method


def _request_endpoint() -> str | None:
    """
    Return the active request endpoint when a request context exists.
    """
    if not has_request_context():
        return None
    return request.endpoint


@dataclass
class ReportInstrumentation:
    """
    Request-local timing collector for one report response.

    ATTRIBUTES
    ----------
    report_name:
        Stable logical report identifier, e.g. 'award_decision_docx'.

    procurement_id:
        Procurement primary key associated with the request.

    trace_id:
        Short correlation id for grouping all logs from the same request.

    started_at:
        Perf-counter timestamp for whole-request measurement.

    stage_started_at:
        Current route-level stage start timestamp when a stage is active.

    stage_name:
        Name of the currently active route-level stage.

    stage_timings_ms:
        Mapping of route-level stage name -> measured milliseconds.

    detail_timings_ms:
        Mapping of builder-level detail name -> measured milliseconds.
    """

    report_name: str
    procurement_id: int | None = None
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: float = field(default_factory=_now)
    stage_started_at: float | None = None
    stage_name: str | None = None
    stage_timings_ms: dict[str, float] = field(default_factory=dict)
    detail_timings_ms: dict[str, float] = field(default_factory=dict)

    def start_stage(self, name: str) -> None:
        """
        Start a named route-level timing stage.

        If another stage is already active, this method ends it first.
        """
        if self.stage_name is not None:
            self.end_stage()

        self.stage_name = str(name)
        self.stage_started_at = _now()

    def end_stage(self, **extra: Any) -> float:
        """
        End the current route-level stage and emit a timing log.

        RETURNS
        -------
        float
            Measured stage duration in milliseconds.
        """
        if self.stage_name is None or self.stage_started_at is None:
            return 0.0

        ended_at = _now()
        elapsed_ms = _ms(self.stage_started_at, ended_at)
        stage_name = self.stage_name

        self.stage_timings_ms[stage_name] = elapsed_ms

        payload = self._base_payload()
        payload.update(
            {
                "stage": stage_name,
                "stage_ms": elapsed_ms,
            }
        )
        payload.update(extra)

        current_app.logger.info("REPORT_TIMING_STAGE %s", payload)

        self.stage_name = None
        self.stage_started_at = None
        return elapsed_ms

    def mark(self, name: str, value: Any) -> None:
        """
        Emit a lightweight metadata log associated with this report request.
        """
        payload = self._base_payload()
        payload.update(
            {
                "mark": str(name),
                "value": value,
            }
        )
        current_app.logger.info("REPORT_TIMING_MARK %s", payload)

    def log_detail(self, name: str, elapsed_ms: float, **extra: Any) -> None:
        """
        Emit one builder-level detail timing log.
        """
        detail_name = str(name)
        self.detail_timings_ms[detail_name] = elapsed_ms

        payload = self._base_payload()
        payload.update(
            {
                "detail": detail_name,
                "detail_ms": elapsed_ms,
            }
        )
        payload.update(extra)

        current_app.logger.info("REPORT_TIMING_DETAIL %s", payload)

    @contextmanager
    def timed_detail(self, name: str, **extra: Any) -> Iterator[None]:
        """
        Context manager for builder-level detail timing.

        Example
        -------
        with instrumentation.timed_detail("load_template"):
            doc = Document(...)
        """
        started_at = _now()
        try:
            yield
        finally:
            self.log_detail(name, _ms(started_at, _now()), **extra)

    def finish(self, **extra: Any) -> float:
        """
        Finish the instrumentation session and emit the summary log.

        RETURNS
        -------
        float
            Total measured request duration in milliseconds.
        """
        if self.stage_name is not None:
            self.end_stage()

        total_ms = _ms(self.started_at, _now())

        payload = self._base_payload()
        payload.update(
            {
                "total_ms": total_ms,
                "stages_ms": dict(self.stage_timings_ms),
                "details_ms": dict(self.detail_timings_ms),
                "path": _request_path(),
                "method": _request_method(),
                "endpoint": _request_endpoint(),
            }
        )
        payload.update(extra)

        current_app.logger.info("REPORT_TIMING_SUMMARY %s", payload)
        return total_ms

    def _base_payload(self) -> dict[str, Any]:
        """
        Build the common structured payload shared by all instrumentation logs.
        """
        return {
            "trace_id": self.trace_id,
            "report_name": self.report_name,
            "procurement_id": self.procurement_id,
        }


@dataclass
class RequestInstrumentation:
    """
    Request-local timing collector for one general Flask request.

    PURPOSE
    -------
    This collector supports global request timing without altering route
    behavior. It is intended for:
    - before_request / after_request instrumentation
    - login user-loader timing
    - context processor timing
    - navigation build timing
    - list-context builder timing
    - optional SQL counters populated elsewhere

    ATTRIBUTES
    ----------
    trace_id:
        Correlation id shared across all logs emitted during one request.

    started_at:
        Whole-request start timestamp.

    timings_ms:
        Mapping of logical timing part -> elapsed milliseconds.

    marks:
        Lightweight metadata emitted at summary time.

    sql_query_count:
        Optional SQL query count collected by SQLAlchemy event hooks.

    sql_total_ms:
        Optional aggregate SQL time collected by SQLAlchemy event hooks.
    """

    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: float = field(default_factory=_now)
    timings_ms: dict[str, float] = field(default_factory=dict)
    marks: dict[str, Any] = field(default_factory=dict)
    sql_query_count: int = 0
    sql_total_ms: float = 0.0

    def add_timing(self, name: str, elapsed_ms: float) -> float:
        """
        Add or overwrite a named timing part and emit a detail log.

        PARAMETERS
        ----------
        name:
            Stable logical timing name, e.g. 'user_loader'.
        elapsed_ms:
            Measured duration in milliseconds.

        RETURNS
        -------
        float
            The same elapsed value for convenience.
        """
        timing_name = str(name)
        elapsed = round(float(elapsed_ms), 2)
        self.timings_ms[timing_name] = elapsed

        payload = self._base_payload()
        payload.update(
            {
                "part": timing_name,
                "elapsed_ms": elapsed,
            }
        )
        current_app.logger.info("REQUEST_TIMING_PART %s", payload)
        return elapsed

    def increment_sql(self, elapsed_ms: float) -> None:
        """
        Increment SQL aggregate counters for the active request.

        PARAMETERS
        ----------
        elapsed_ms:
            Duration of one SQL statement in milliseconds.
        """
        self.sql_query_count += 1
        self.sql_total_ms = round(self.sql_total_ms + float(elapsed_ms), 2)

    def mark(self, name: str, value: Any) -> None:
        """
        Store lightweight metadata for the request summary and emit a mark log.
        """
        key = str(name)
        self.marks[key] = value

        payload = self._base_payload()
        payload.update(
            {
                "mark": key,
                "value": value,
            }
        )
        current_app.logger.info("REQUEST_TIMING_MARK %s", payload)

    @contextmanager
    def timed(self, name: str, **extra: Any) -> Iterator[None]:
        """
        Measure one named request-local timing part.

        Example
        -------
        with instrumentation.timed("context_processor"):
            build_context()
        """
        started_at = _now()
        try:
            yield
        finally:
            elapsed_ms = self.add_timing(name, _ms(started_at, _now()))
            if extra:
                payload = self._base_payload()
                payload.update(
                    {
                        "part": str(name),
                        "elapsed_ms": elapsed_ms,
                    }
                )
                payload.update(extra)
                current_app.logger.info("REQUEST_TIMING_PART_EXTRA %s", payload)

    def finish(self, **extra: Any) -> float:
        """
        Emit the final request summary log.

        RETURNS
        -------
        float
            Total request duration in milliseconds.
        """
        total_ms = _ms(self.started_at, _now())

        payload = self._base_payload()
        payload.update(
            {
                "total_ms": total_ms,
                "parts_ms": dict(self.timings_ms),
                "marks": dict(self.marks),
                "sql_query_count": self.sql_query_count,
                "sql_total_ms": round(self.sql_total_ms, 2),
                "path": _request_path(),
                "method": _request_method(),
                "endpoint": _request_endpoint(),
            }
        )
        payload.update(extra)

        current_app.logger.info("REQUEST_TIMING_SUMMARY %s", payload)
        return total_ms

    def _base_payload(self) -> dict[str, Any]:
        """
        Build the common structured payload shared by all request timing logs.
        """
        return {
            "trace_id": self.trace_id,
            "path": _request_path(),
            "method": _request_method(),
            "endpoint": _request_endpoint(),
        }


def begin_report_timing(
    report_name: str,
    procurement_id: int | None = None,
) -> ReportInstrumentation:
    """
    Create a report timing collector for one request.
    """
    return ReportInstrumentation(
        report_name=str(report_name),
        procurement_id=procurement_id,
    )


def begin_request_timing() -> RequestInstrumentation:
    """
    Create a general request timing collector for one active Flask request.
    """
    return RequestInstrumentation()


__all__ = [
    "ReportInstrumentation",
    "RequestInstrumentation",
    "begin_report_timing",
    "begin_request_timing",
]