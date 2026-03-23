"""
app/reports/instrumentation.py

Structured timing instrumentation for report-generation requests.

PURPOSE
-------
This module provides lightweight, request-local timing helpers for report
generation and download endpoints.

It supports two timing levels:
1. route-level stage timings
2. deep builder-level detail timings

The deep detail timings are used inside the report builders to break down the
single "build_docx" stage into internal steps such as:
- load_template
- build_mapping
- replace_placeholders_body
- replace_headers_footers
- locate_tables
- fill_tables
- set_global_font
- save_docx

DESIGN GOALS
------------
- zero behavior change
- no dependency on external APM tooling
- structured logs via Flask's standard app logger
- safe to leave enabled in production
- easy to extend later

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

from flask import current_app, request


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
                "path": request.path if request else None,
                "method": request.method if request else None,
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


def begin_report_timing(report_name: str, procurement_id: int | None = None) -> ReportInstrumentation:
    """
    Create a report timing collector for one request.
    """
    return ReportInstrumentation(
        report_name=str(report_name),
        procurement_id=procurement_id,
    )


__all__ = [
    "ReportInstrumentation",
    "begin_report_timing",
]