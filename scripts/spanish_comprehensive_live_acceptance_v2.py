#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

import mobile_restart_live_acceptance_v1 as recovery
import spanish_comprehensive_live_acceptance_v1 as proof

VERSION = "nico.spanish_comprehensive_live_acceptance.telemetry.v2"
FINAL_REPORT_STAGE_ID = "final_comprehensive_report_generation"
_FAILURE_PHASES = {
    "Assessment requires attention",
    "La evaluación requiere atención",
}

_OUTPUT_PATH = Path("audit-results/spanish-comprehensive-live-proof.json")
_FRONTEND_ORIGIN = ""


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any, limit: int = 800) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _number(value: Any) -> float | int | None:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    return int(normalized) if normalized.is_integer() else round(normalized, 3)


def _telemetry_seconds() -> float:
    try:
        value = float(os.getenv("NICO_SPANISH_PROOF_TELEMETRY_SECONDS", "30"))
    except (TypeError, ValueError):
        value = 30.0
    return max(5.0, min(300.0, value))


def _progress_path() -> Path:
    return _OUTPUT_PATH.with_suffix(".progress.json")


def _write_progress(payload: dict[str, Any]) -> None:
    path = _progress_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def _fetch_run_payload(page: Any, run_id: str) -> dict[str, Any]:
    try:
        response = page.request.get(
            f"{_FRONTEND_ORIGIN}/api/nico/assessment/comprehensive-run/{run_id}",
            headers={
                "Accept": "application/json",
                recovery.BROWSER_PROJECTION_HEADER: recovery.BROWSER_PROJECTION_VALUE,
                "Cache-Control": "no-store",
            },
            timeout=60_000,
        )
        if not response.ok:
            return {
                "telemetry_transport_status": "http_error",
                "telemetry_http_status": response.status,
            }
        payload = response.json()
        if not isinstance(payload, dict):
            return {"telemetry_transport_status": "invalid_payload"}
        return payload
    except Exception as exc:
        return {
            "telemetry_transport_status": "request_error",
            "telemetry_error": f"{type(exc).__name__}: {_text(exc, 400)}",
        }


def _pick(sources: list[dict[str, Any]], *keys: str, limit: int = 800) -> str:
    for source in sources:
        for key in keys:
            value = _text(source.get(key), limit)
            if value:
                return value
    return ""


def _worker_failure(payload: dict[str, Any]) -> dict[str, Any]:
    run_record = _record(payload.get("record"))
    stage_results = _record(run_record.get("stage_results") or payload.get("stage_results"))
    stage = _record(stage_results.get(FINAL_REPORT_STAGE_ID))
    stage_execution = _record(stage.get("stage_execution"))
    active_execution = _record(
        payload.get("active_stage_execution") or run_record.get("active_stage_execution")
    )
    normalized = _record(
        payload.get("worker_failure")
        or run_record.get("worker_failure")
        or stage.get("worker_failure")
    )
    sources = [normalized, stage, stage_execution, active_execution, run_record, payload]

    raw_exit: Any = None
    for source in sources:
        if "worker_exit_code" in source:
            raw_exit = source.get("worker_exit_code")
            break
        if "exit_code" in source:
            raw_exit = source.get("exit_code")
            break
    exit_code = _number(raw_exit)
    failure = {
        "reason": _pick(sources, "reason", "error_code", "failure_code", limit=160),
        "worker_model": _pick(sources, "worker_model", "model", limit=80),
        "worker_exit_code": exit_code,
        "worker_exit_signal": _pick(sources, "worker_exit_signal", "exit_signal", limit=80),
        "worker_error_type": _pick(sources, "worker_error_type", "error_type", limit=160),
        "worker_error": _pick(sources, "worker_error", "error", limit=1_200),
        "worker_failure_class": _pick(
            sources,
            "worker_failure_class",
            "failure_class",
            limit=120,
        ),
        "worker_bootstrap": _pick(sources, "worker_bootstrap", "bootstrap", limit=240),
    }
    return {
        key: value
        for key, value in failure.items()
        if value not in {"", None}
    }


def _active_execution(payload: dict[str, Any]) -> dict[str, Any]:
    run_record = _record(payload.get("record"))
    active = _record(
        payload.get("active_stage_execution") or run_record.get("active_stage_execution")
    )
    allowed = (
        "state",
        "stage_id",
        "worker_model",
        "lease_id",
        "heartbeat_age_seconds",
        "elapsed_seconds",
        "deadline_seconds",
        "deadline_phase",
        "overdue",
        "durable_lease_found",
        "killable_worker",
    )
    return {
        key: active.get(key)
        for key in allowed
        if active.get(key) not in {"", None}
    }


def _snapshot(
    *,
    page: Any,
    run_id: str,
    payload: dict[str, Any],
    started_monotonic: float,
    terminal: bool,
) -> dict[str, Any]:
    ui = recovery._ui_state(page)
    run_record = _record(payload.get("record"))
    return {
        "artifact_schema": VERSION,
        "status": "terminal_observed" if terminal else "running",
        "run_id": run_id,
        "observed_at_epoch": time.time(),
        "elapsed_seconds": round(max(0.0, time.monotonic() - started_monotonic), 3),
        "ui": {
            "phase": _text(ui.get("phase"), 120),
            "run_id": _text(ui.get("run_id"), 160),
            "commit_sha": _text(ui.get("commit_sha"), 80),
            "report": _text(ui.get("report"), 160),
            "review": _text(ui.get("review"), 160),
            "score": _text(ui.get("score"), 120),
        },
        "lifecycle": {
            "status": _text(payload.get("status") or run_record.get("status"), 80),
            "current_stage": _text(
                payload.get("current_stage") or run_record.get("current_stage"),
                120,
            ),
            "progress_percent": _number(
                payload.get("progress_percent") or run_record.get("progress_percent")
            ),
            "terminal": bool(payload.get("terminal") or run_record.get("terminal")),
        },
        "active_stage_execution": _active_execution(payload),
        "failure": _worker_failure(payload),
        "telemetry_transport_status": _text(
            payload.get("telemetry_transport_status") or "ok",
            80,
        ),
        "telemetry_http_status": _number(payload.get("telemetry_http_status")),
        "telemetry_error": _text(payload.get("telemetry_error"), 400),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _emit(snapshot: dict[str, Any]) -> None:
    _write_progress(snapshot)
    print(
        "SPANISH_PROOF_PROGRESS "
        + json.dumps(snapshot, sort_keys=True, ensure_ascii=False),
        flush=True,
    )


def _wait_for_terminal_with_telemetry(
    page: Any,
    run_id: str,
    timeout_seconds: float,
) -> dict[str, str]:
    deadline = time.monotonic() + timeout_seconds
    started = time.monotonic()
    next_telemetry = 0.0
    last_payload: dict[str, Any] = {}
    last_ui: dict[str, str] = {}

    while time.monotonic() < deadline:
        now = time.monotonic()
        last_ui = recovery._ui_state(page)
        terminal = bool(
            last_ui.get("run_id") == run_id
            and last_ui.get("phase") in recovery.TERMINAL_PHASES
        )
        failed = last_ui.get("phase") in _FAILURE_PHASES

        if now >= next_telemetry or terminal or failed:
            last_payload = _fetch_run_payload(page, run_id)
            _emit(
                _snapshot(
                    page=page,
                    run_id=run_id,
                    payload=last_payload,
                    started_monotonic=started,
                    terminal=terminal,
                )
            )
            next_telemetry = now + _telemetry_seconds()

        if terminal:
            return last_ui
        if failed:
            raise AssertionError(
                "Assessment failed before terminal Spanish proof: "
                + _text(
                    {
                        "ui": last_ui,
                        "failure": _worker_failure(last_payload),
                    },
                    1_500,
                )
            )
        page.wait_for_timeout(1_000)

    last_payload = _fetch_run_payload(page, run_id)
    snapshot = _snapshot(
        page=page,
        run_id=run_id,
        payload=last_payload,
        started_monotonic=started,
        terminal=False,
    )
    snapshot["status"] = "timed_out"
    _emit(snapshot)
    raise AssertionError(
        f"Timed out waiting for terminal Spanish run {run_id}: {_text(snapshot, 1_500)}"
    )


def _parse_wrapper_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    values, _ = parser.parse_known_args(argv)
    return values


def main(argv: list[str] | None = None) -> int:
    global _OUTPUT_PATH
    global _FRONTEND_ORIGIN

    wrapper = _parse_wrapper_args(argv)
    _OUTPUT_PATH = wrapper.output
    _FRONTEND_ORIGIN = wrapper.frontend_url.rstrip("/")
    original_wait = recovery._wait_for_terminal
    recovery._wait_for_terminal = _wait_for_terminal_with_telemetry
    try:
        return proof.main(argv)
    finally:
        recovery._wait_for_terminal = original_wait


if __name__ == "__main__":
    raise SystemExit(main())
