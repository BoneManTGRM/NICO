#!/usr/bin/env python3
from __future__ import annotations

import time
from typing import Any

import two_service_live_acceptance as acceptance
import two_service_live_acceptance_v2 as runtime

VERSION = "nico.two_service_live_acceptance_terminal_reconciliation.v5"
UI_BACKEND_RECONCILIATION_SECONDS = 120.0
UI_BACKEND_RETRY_SECONDS = 2.0

_original_wait_for_service_terminal = runtime._wait_for_service_terminal
_original_report_package = acceptance.report_package


def _backend_is_terminal(payload: dict[str, Any]) -> bool:
    if not payload:
        return False
    status = acceptance.status_value(payload)
    record = acceptance.record(payload)
    terminal = bool(payload.get("terminal", record.get("terminal", False)))
    return status in runtime.SUCCESS_STATUSES | runtime.FAILURE_STATUSES or terminal


def _report_package(service: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Read the terminal Comprehensive package from its bounded top-level field.

    Active Comprehensive responses intentionally omit generated reports and large
    stage payloads. At the terminal human-review boundary the API attaches one report
    package at ``reports`` rather than duplicating it inside the projected run record.
    """

    if service == "comprehensive":
        reports = payload.get("reports")
        if isinstance(reports, dict) and (
            reports.get("markdown") or reports.get("html") or reports.get("pdf_base64")
        ):
            return reports
    return _original_report_package(service, payload)


def _status_error_summary(identity_payload: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "observed_at_epoch": acceptance.now_epoch(),
        "http_status": None,
        "run_id": acceptance.run_id(identity_payload),
        "status": "status_read_error",
        "current_stage": "",
        "progress_percent": None,
        "canonical_progress_percent": None,
        "active_stage_progress_percent": None,
        "revision": None,
        "terminal": False,
        "completed_stage_count": 0,
        "completed_stages": [],
        "code": type(exc).__name__,
        "message": acceptance.text(exc, 320),
        "persistence": {},
    }


def _wait_for_service_terminal(
    *,
    page: Any,
    service: str,
    identity_payload: dict[str, Any],
    timeout_ms: int,
    status_history: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], bool]:
    """Reconcile a terminal browser state with the exact persisted run.

    Preserve the original bounded observer for normal execution. When the UI reaches
    a terminal state first, immediately re-read the same exact run until its status is
    terminal or the short reconciliation budget expires. No duplicate run is started,
    and no incomplete backend record is relabeled as successful.
    """

    backend_payload, state, ui_terminal_observed = _original_wait_for_service_terminal(
        page=page,
        service=service,
        identity_payload=identity_payload,
        timeout_ms=timeout_ms,
        status_history=status_history,
    )
    if not ui_terminal_observed or _backend_is_terminal(backend_payload):
        return backend_payload, state, ui_terminal_observed

    deadline = time.monotonic() + UI_BACKEND_RECONCILIATION_SECONDS
    last_summary = status_history[-1] if status_history else {}
    while time.monotonic() < deadline:
        try:
            current, summary = runtime._backend_status(page, service, identity_payload)
        except Exception as exc:  # temporary transport failures remain bounded
            current = {}
            summary = _status_error_summary(identity_payload, exc)
        status_history.append(summary)
        last_summary = summary
        if current and _backend_is_terminal(current):
            status = acceptance.status_value(current)
            return current, state, status in runtime.SUCCESS_STATUSES
        page.wait_for_timeout(int(UI_BACKEND_RETRY_SECONDS * 1000))

    raise AssertionError(
        f"{service} browser rendered {state.get('phase_label') or 'a terminal phase'} for exact run "
        f"{acceptance.run_id(identity_payload)}, but persisted status did not reconcile within "
        f"{int(UI_BACKEND_RECONCILIATION_SECONDS)} seconds; "
        f"last status={last_summary.get('status') or 'unknown'}, "
        f"stage={last_summary.get('current_stage') or 'unknown'}, "
        f"progress={last_summary.get('progress_percent')}, revision={last_summary.get('revision')}"
    )


def main(argv: list[str] | None = None) -> int:
    acceptance.report_package = _report_package
    runtime._wait_for_service_terminal = _wait_for_service_terminal
    return runtime.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
