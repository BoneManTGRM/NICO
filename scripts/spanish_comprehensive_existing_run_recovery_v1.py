#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

# Release automation invokes this file by path. Keep repository imports stable
# without depending on the runner's current-directory import behavior.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from comprehensive_production_run_handoff_v1 import source_binding_marker
import spanish_comprehensive_live_acceptance_v1 as base
import spanish_comprehensive_live_acceptance_v3 as spanish


VERSION = "nico.spanish_comprehensive_existing_run_recovery.v1"
FAILED_SOURCE_SCHEMA = "nico.spanish_comprehensive_live_acceptance.v1"
RUN_ID_PATTERN = re.compile(r"^comprun_[0-9a-f]{32}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
FAILED_TERMINAL_STATES = {
    "blocked",
    "cancelled",
    "canceled",
    "error",
    "failed",
    "interrupted",
    "rejected",
}
MAX_SOURCE_LOG_BYTES = 20_000_000


def _text(value: Any) -> str:
    return str(value or "").strip()


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _require_sha256(value: Any, *, code: str) -> str:
    candidate = _text(value).lower()
    if not SHA256_PATTERN.fullmatch(candidate):
        raise ValueError(code)
    return candidate


def _require_git_sha(value: Any, *, code: str) -> str:
    candidate = _text(value).lower()
    if not GIT_SHA_PATTERN.fullmatch(candidate):
        raise ValueError(code)
    return candidate


def _load_failed_source(
    path: Path,
    *,
    expected_sha: str,
    repository: str,
) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("failed_source_proof_must_be_mapping")
    run_id = _text(value.get("run_id"))
    cleanup = value.get("production_proof_cleanup")
    cleanup = cleanup if isinstance(cleanup, Mapping) else {}
    error = _text(value.get("error"))
    checks = {
        "failed_source_schema_invalid": _text(value.get("artifact_schema"))
        == FAILED_SOURCE_SCHEMA,
        "failed_source_status_invalid": _text(value.get("status")) == "failed",
        "failed_source_release_sha_mismatch": _text(value.get("expected_sha"))
        == expected_sha,
        "failed_source_repository_mismatch": _text(value.get("repository")).casefold()
        == repository.casefold(),
        "failed_source_language_mismatch": _text(value.get("report_language_requested"))
        == "es-MX",
        "failed_source_run_id_invalid": bool(RUN_ID_PATTERN.fullmatch(run_id)),
        "failed_source_not_visibility_timeout": (
            error.startswith("TimeoutError:")
            and "Page.wait_for_function" in error
            and "Timeout" in error
        ),
        "failed_source_cleanup_unproven": cleanup.get("attempted") is True,
        "failed_source_run_was_cancelled": cleanup.get("succeeded") is False,
    }
    failures = sorted(code for code, passed in checks.items() if not passed)
    if failures:
        raise ValueError(",".join(failures))
    return {
        "run_id": run_id,
        "failed_source_proof_sha256": hashlib.sha256(raw).hexdigest(),
        "failed_source_error": error,
        "failed_source_cleanup": dict(cleanup),
    }


def _load_and_validate_source_job_log(
    path: Path,
    *,
    expected_sha: str,
    source_workflow_run_id: str,
    source_workflow_run_attempt: str,
) -> dict[str, Any]:
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_SOURCE_LOG_BYTES:
        raise ValueError("failed_source_job_log_size_invalid")
    log = raw.decode("utf-8-sig", errors="replace")
    required = (
        f"RELEASE_SHA: {expected_sha}",
        f"SOURCE_RUN_ID: {source_workflow_run_id}",
        f"SOURCE_RUN_ATTEMPT: {source_workflow_run_attempt}",
        "spanish_comprehensive_live_acceptance_v3.py",
        "in _commercial_spanish_run_proof",
        "running_visibility = base.recovery._prove_visibility_hidden_visible(",
        "in _prove_visibility_hidden_visible",
        "document.hidden === true && document.visibilityState === 'hidden'",
        "TimeoutError: Page.wait_for_function: Timeout",
        "Process completed with exit code 1",
    )
    missing = [marker for marker in required if marker not in log]
    if missing:
        raise ValueError("failed_source_job_log_control_flow_invalid:" + ",".join(missing))
    return {
        "failed_source_job_log_sha256": hashlib.sha256(raw).hexdigest(),
        "failed_source_job_log_size_bytes": len(raw),
        "failed_source_control_flow_reached_running_visibility": True,
        "failed_source_prior_intake_assertions_completed": True,
        "failed_source_running_reload_completed_before_visibility": True,
    }


def _validate_immutable_source_script(
    path: Path,
    *,
    expected_sha256: str,
) -> dict[str, Any]:
    raw = path.read_bytes()
    observed = hashlib.sha256(raw).hexdigest()
    if observed != expected_sha256:
        raise ValueError("immutable_source_script_sha256_mismatch")
    source = raw.decode("utf-8")
    boundary = source.split("def _commercial_spanish_run_proof", 1)
    if len(boundary) != 2:
        raise ValueError("immutable_source_commercial_proof_missing")
    commercial = boundary[1].split("def install_spanish_terminal_boundary", 1)[0]
    # Cursor-based lookup is intentional: the start-count assertion appears more
    # than once, and the second occurrence is the one proving reload did not start
    # another assessment before the source proof entered the visibility boundary.
    ordered_markers = (
        "assert base.recovery._start_count(requests) == 1",
        "browser_intake = _verify_actual_browser_intake(requests)",
        "initial_engagement = _fetch_and_verify_durable_engagement(",
        "running_reload = base.recovery._reload_and_restore(",
        "assert base.recovery._start_count(requests) == 1",
        "running_visibility = base.recovery._prove_visibility_hidden_visible(",
    )
    cursor = 0
    for marker in ordered_markers:
        position = commercial.find(marker, cursor)
        if position < 0:
            raise ValueError("immutable_source_control_flow_order_invalid")
        cursor = position + len(marker)
    return {
        "source_script_sha256": observed,
        "source_script_control_flow_order_verified": True,
    }


def _projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    record = payload.get("record") if isinstance(payload.get("record"), Mapping) else {}
    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    engagement = payload.get("engagement_metadata")
    if not isinstance(engagement, Mapping):
        engagement = record.get("engagement_metadata")
    if not isinstance(engagement, Mapping):
        engagement = {}
    return {
        "run_id": _text(payload.get("run_id") or identity.get("run_id")),
        "repository": _text(payload.get("repository") or identity.get("repository")),
        "commit_sha": _text(payload.get("commit_sha") or identity.get("commit_sha")),
        "status": _text(payload.get("status") or record.get("status") or "unknown"),
        "current_stage": _text(
            payload.get("current_stage") or record.get("current_stage")
        ),
        "terminal": bool(
            payload.get("terminal")
            if "terminal" in payload
            else record.get("terminal")
        ),
        "revision": payload.get("revision", record.get("revision")),
        "progress_percent": payload.get(
            "progress_percent", record.get("progress_percent")
        ),
        "report_language": _text(
            payload.get("report_language")
            or record.get("report_language")
            or engagement.get("report_language")
        ),
        "evidence_ledger_id": _text(
            payload.get("evidence_ledger_id")
            or record.get("evidence_ledger_id")
            or identity.get("evidence_ledger_id")
        ),
        "human_review_required": bool(
            payload.get(
                "human_review_required",
                record.get("human_review_required", True),
            )
        ),
        "client_delivery_allowed": bool(
            payload.get(
                "client_delivery_allowed",
                record.get("client_delivery_allowed", False),
            )
        ),
    }


def _get_exact_run(
    page: Any,
    *,
    origin: str,
    run_id: str,
    expected_sha: str,
    repository: str,
    expected_evidence_ledger_id: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    response = page.request.get(
        f"{origin}/api/nico/assessment/comprehensive-run/{run_id}",
        headers={
            "Accept": "application/json",
            base.recovery.BROWSER_PROJECTION_HEADER: base.recovery.BROWSER_PROJECTION_VALUE,
            "Cache-Control": "no-store",
        },
        timeout=90_000,
    )
    if not response.ok:
        raise AssertionError(f"Exact recovery run returned HTTP {response.status}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise AssertionError("Exact recovery run did not return a JSON object")
    view = _projection(payload)
    assert view["run_id"] == run_id, view
    assert view["repository"].casefold() == repository.casefold(), view
    assert view["commit_sha"] == expected_sha, view
    assert view["evidence_ledger_id"], view
    if expected_evidence_ledger_id:
        assert view["evidence_ledger_id"] == expected_evidence_ledger_id, view
    assert view["human_review_required"] is True, view
    assert view["client_delivery_allowed"] is False, view
    if view["terminal"]:
        assert view["status"].casefold() not in FAILED_TERMINAL_STATES, view
    return payload, view


def _activity_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    record = payload.get("record") if isinstance(payload.get("record"), Mapping) else {}
    activity = payload.get("active_stage_execution")
    if not isinstance(activity, Mapping):
        activity = record.get("active_stage_execution")
    if not isinstance(activity, Mapping):
        activity = {}
    allowed = (
        "artifact_schema",
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
        "human_review_required",
        "client_delivery_allowed",
    )
    return {key: activity.get(key) for key in allowed if key in activity}


def _wait_existing_run_to_terminal(
    page: Any,
    *,
    origin: str,
    run_id: str,
    expected_sha: str,
    repository: str,
    expected_evidence_ledger_id: str,
    initial_payload: dict[str, Any],
    initial_view: dict[str, Any],
    timeout_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Observe one already-running producer lease without issuing any mutation.

    The production final-report worker owns its durable lease independently of the
    failed browser proof. GET status may expose fresh heartbeat/activity evidence;
    this verifier never guesses that a stable revision is abandoned and never POSTs
    a continuation. A stale/nonterminal run therefore fails closed for an authorized
    operator instead of risking a duplicate write.
    """

    deadline = time.monotonic() + timeout_seconds
    payload = initial_payload
    view = initial_view
    observations: list[dict[str, Any]] = [
        {**dict(view), "active_stage_execution": _activity_projection(payload)}
    ]
    previous_fingerprint = json.dumps(observations[-1], sort_keys=True, default=str)
    while not view["terminal"] and time.monotonic() < deadline:
        page.wait_for_timeout(10_000)
        payload, view = _get_exact_run(
            page,
            origin=origin,
            run_id=run_id,
            expected_sha=expected_sha,
            repository=repository,
            expected_evidence_ledger_id=expected_evidence_ledger_id,
        )
        observation = {
            **dict(view),
            "active_stage_execution": _activity_projection(payload),
        }
        fingerprint = json.dumps(observation, sort_keys=True, default=str)
        if fingerprint != previous_fingerprint or view["terminal"]:
            observations.append(observation)
            previous_fingerprint = fingerprint
    if not view["terminal"]:
        raise AssertionError(
            "Existing producer run did not reach terminal state through its durable "
            f"worker within the bounded observation window: {observations[-1]}"
        )
    assert view["status"].casefold() not in FAILED_TERMINAL_STATES, view
    return payload, view, observations


def run_recovery(browser: Any, args: argparse.Namespace) -> dict[str, Any]:
    origin = args.frontend_url.rstrip("/")
    expected_sha = _require_git_sha(
        args.expected_sha,
        code="expected_sha_invalid",
    )
    source_marker = source_binding_marker(
        args.source_workflow_run_id,
        args.source_workflow_run_attempt,
    )
    failed = _load_failed_source(
        args.failed_source_proof,
        expected_sha=expected_sha,
        repository=args.repository,
    )
    source_log = _load_and_validate_source_job_log(
        args.failed_source_job_log,
        expected_sha=expected_sha,
        source_workflow_run_id=args.source_workflow_run_id,
        source_workflow_run_attempt=args.source_workflow_run_attempt,
    )
    expected_source_script_sha256 = _require_sha256(
        args.expected_source_script_sha256,
        code="expected_source_script_sha256_invalid",
    )
    source_script = _validate_immutable_source_script(
        args.source_script,
        expected_sha256=expected_source_script_sha256,
    )
    source_artifact_digest = _require_sha256(
        args.source_artifact_digest.removeprefix("sha256:"),
        code="source_artifact_digest_invalid",
    )
    proof_tool_sha = _require_git_sha(args.proof_tool_sha, code="proof_tool_sha_invalid")
    run_id = failed["run_id"]
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        locale="es-MX",
        service_workers="block",
        extra_http_headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
    page = context.new_page()
    guarded_requests: list[dict[str, str]] = []

    def mutation_guard(route: Any, request: Any) -> None:
        parsed = urlparse(request.url)
        method = str(request.method).upper()
        is_intake = (
            method == "POST"
            and parsed.path == "/api/nico/assessment/comprehensive-intake"
        )
        is_continuation = (
            method == "POST"
            and parsed.path.startswith("/api/nico/assessment/comprehensive-run/")
            and parsed.path.endswith("/continue")
        )
        if is_intake or is_continuation:
            guarded_requests.append({"method": method, "path": parsed.path})
            route.abort("blockedbyclient")
            return
        route.continue_()

    page.route("**/*", mutation_guard)
    started_at = time.time()
    try:
        # Establish exact immutable identity before loading any client UI. The page
        # route is already installed, but this APIRequestContext GET cannot dispatch
        # an intake or continuation request.
        initial_payload, initial_view = _get_exact_run(
            page,
            origin=origin,
            run_id=run_id,
            expected_sha=expected_sha,
            repository=args.repository,
        )
        evidence_ledger_id = initial_view["evidence_ledger_id"]
        assert initial_view["report_language"] == "es-MX", initial_view
        initial_engagement = spanish._fetch_and_verify_durable_engagement(
            page,
            frontend_origin=origin,
            run_id=run_id,
            boundary="existing_recovery_initial",
        )
        proof_scope = base._verify_proof_scope(page, origin, run_id)

        page.goto(
            f"{origin}/es/assessment?tier=comprehensive&run_id={run_id}"
            f"&expected_commit_sha={expected_sha}"
            f"&existing_producer_recovery={time.time_ns()}#assessment",
            wait_until="domcontentloaded",
            timeout=args.navigation_timeout_ms,
        )
        base._wait_for_spanish_hydration(page, args.navigation_timeout_ms)
        assert page.evaluate("() => document.documentElement.lang") == "es-MX"
        initial_ui = base.recovery._wait_for_same_run_ui(page, run_id, 120.0)
        running_reload: dict[str, Any] = {}
        running_visibility: dict[str, Any] = {}
        running_after_foreground: dict[str, Any] = {}
        if not initial_view["terminal"]:
            running_reload = base.recovery._reload_and_restore(
                page,
                run_id,
                args.navigation_timeout_ms,
                expect_active_storage=True,
            )
            running_visibility = base.recovery._prove_visibility_hidden_visible(
                page,
                context,
                timeout_ms=args.navigation_timeout_ms,
            )
            running_after_foreground = base.recovery._wait_for_same_run_ui(
                page,
                run_id,
                120.0,
            )
        intake_attempts = [
            item
            for item in guarded_requests
            if item["path"] == "/api/nico/assessment/comprehensive-intake"
        ]
        assert not intake_attempts, intake_attempts
        ui_continuation_attempts = [
            item for item in guarded_requests if item["path"].endswith("/continue")
        ]
        assert len(ui_continuation_attempts) <= 2, ui_continuation_attempts

        _, terminal_view, durable_worker_observations = (
            _wait_existing_run_to_terminal(
                page,
                origin=origin,
                run_id=run_id,
                expected_sha=expected_sha,
                repository=args.repository,
                expected_evidence_ledger_id=evidence_ledger_id,
                initial_payload=initial_payload,
                initial_view=initial_view,
                timeout_seconds=args.timeout_seconds,
            )
        )
        assert terminal_view["terminal"] is True, terminal_view
        assert terminal_view["human_review_required"] is True, terminal_view
        assert terminal_view["client_delivery_allowed"] is False, terminal_view

        guarded_before_terminal_ui = len(guarded_requests)
        page.reload(wait_until="domcontentloaded", timeout=args.navigation_timeout_ms)
        base._wait_for_spanish_hydration(page, args.navigation_timeout_ms)
        terminal = base.recovery._wait_for_terminal_ui_ready(
            page,
            run_id,
            expected_sha,
            240.0,
        )
        terminal_visibility = base.recovery._prove_visibility_hidden_visible(
            page,
            context,
            timeout_ms=args.navigation_timeout_ms,
        )
        terminal_after_foreground = base.recovery._wait_for_terminal_ui_ready(
            page,
            run_id,
            expected_sha,
            120.0,
        )
        terminal_ui_mutation_attempts = guarded_requests[guarded_before_terminal_ui:]
        assert not terminal_ui_mutation_attempts, terminal_ui_mutation_attempts
        guarded_before_artifacts = len(guarded_requests)
        artifacts = spanish._verify_localized_spanish_terminal_artifacts(
            page,
            frontend_origin=origin,
            run_id=run_id,
        )
        assert len(guarded_requests) == guarded_before_artifacts, guarded_requests
        terminal_engagement = spanish._fetch_and_verify_durable_engagement(
            page,
            frontend_origin=origin,
            run_id=run_id,
            boundary="existing_recovery_terminal",
        )
        assert terminal_engagement == initial_engagement
        _, final_view = _get_exact_run(
            page,
            origin=origin,
            run_id=run_id,
            expected_sha=expected_sha,
            repository=args.repository,
            expected_evidence_ledger_id=evidence_ledger_id,
        )
        assert final_view == terminal_view, {
            "terminal_state_before_artifact_reads": terminal_view,
            "terminal_state_after_artifact_reads": final_view,
        }

        screenshot_path = args.output.with_suffix(".png")
        screenshot_error = ""
        try:
            page.screenshot(
                path=str(screenshot_path),
                full_page=False,
                timeout=15_000,
                animations="disabled",
            )
        except Exception as exc:
            screenshot_error = f"{type(exc).__name__}: {base._bounded(exc, 320)}"

        result = {
            "artifact_schema": VERSION,
            "status": "passed",
            "frontend_url": origin,
            "repository": args.repository,
            "expected_sha": expected_sha,
            "proof_tool_sha": proof_tool_sha,
            "source_workflow_run_id": str(args.source_workflow_run_id),
            "source_workflow_run_attempt": str(args.source_workflow_run_attempt),
            "source_binding": source_marker.removeprefix("source:"),
            "source_artifact_digest": source_artifact_digest,
            "run_id": run_id,
            "report_language_requested": "es-MX",
            "spanish_route_verified": True,
            "document_language_verified": True,
            "intake_report_language_verified": True,
            **proof_scope,
            **failed,
            **source_log,
            **source_script,
            "source_failure_classified_as_proof_harness_visibility_only": True,
            "source_producer_lineage_start_request_count": 1,
            "recovery_start_request_count": 0,
            "fresh_assessment_count_during_recovery": 0,
            "duplicate_intake_absent": True,
            "intake_route_guard_verified": True,
            "uncontrolled_continuation_route_guard_verified": True,
            "blocked_ui_continuation_attempt_count": len(ui_continuation_attempts),
            "terminal_ui_mutation_attempt_count": len(terminal_ui_mutation_attempts),
            "explicit_same_run_continuation_count": 0,
            "explicit_same_run_continuation_paths": [],
            "no_client_mutation_terminal_observation": True,
            "initial_canonical_state": initial_view,
            "terminal_canonical_state": terminal_view,
            "durable_worker_observations": durable_worker_observations,
            "same_run_recovery_verified": True,
            "same_commit_recovery_verified": True,
            "same_evidence_ledger_verified": True,
            "evidence_ledger_id": evidence_ledger_id,
            "initial_persistence": {"run_id": run_id, "source": "failed_producer_artifact"},
            "initial_ui": initial_ui,
            "running_reload": running_reload,
            "running_visibility": running_visibility,
            "running_after_foreground": running_after_foreground,
            "running_reload_recovery_verified": bool(running_reload),
            "running_background_foreground_recovery_verified": bool(running_visibility),
            "terminal": terminal,
            "terminal_visibility": terminal_visibility,
            "terminal_after_foreground": terminal_after_foreground,
            "terminal_background_foreground_recovery_verified": True,
            "durable_engagement_metadata_verified_on_recovery": True,
            "durable_engagement_metadata_on_recovery": initial_engagement,
            "source_intake_evidence_class": (
                "immutable_source_control_flow_plus_durable_exact_run_state"
            ),
            "exact_run_identity_preserved": True,
            "commercial_proof_client_name": spanish.PROOF_CLIENT_NAME,
            "commercial_proof_project_name": spanish.PROOF_PROJECT_NAME,
            "commercial_proof_primary_technical_contact": (
                spanish.PROOF_PRIMARY_TECHNICAL_CONTACT
            ),
            "commercial_proof_access_method": spanish.PROOF_ACCESS_METHOD,
            "commercial_proof_authorized_scope": spanish.PROOF_AUTHORIZED_SCOPE,
            "started_at_epoch": started_at,
            "finished_at_epoch": time.time(),
            **artifacts,
            "screenshot": screenshot_path.as_posix() if screenshot_path.exists() else "",
            "screenshot_sha256": (
                hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
                if screenshot_path.exists()
                else ""
            ),
            "screenshot_error": screenshot_error,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        return result
    finally:
        context.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recover the exact run retained by a failed Spanish producer without "
            "starting a second Comprehensive assessment."
        )
    )
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--proof-tool-sha", required=True)
    parser.add_argument("--failed-source-proof", type=Path, required=True)
    parser.add_argument("--failed-source-job-log", type=Path, required=True)
    parser.add_argument("--source-script", type=Path, required=True)
    parser.add_argument("--expected-source-script-sha256", required=True)
    parser.add_argument("--source-artifact-digest", required=True)
    parser.add_argument("--source-workflow-run-id", required=True)
    parser.add_argument("--source-workflow-run-attempt", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=5_400.0)
    parser.add_argument("--navigation-timeout-ms", type=int, default=120_000)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    spanish.install_spanish_terminal_boundary()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                result = run_recovery(browser, args)
            finally:
                browser.close()
    except Exception as exc:
        failure = {
            "artifact_schema": VERSION,
            "status": "failed",
            "frontend_url": args.frontend_url.rstrip("/"),
            "repository": args.repository,
            "expected_sha": args.expected_sha,
            "proof_tool_sha": args.proof_tool_sha,
            "source_workflow_run_id": str(args.source_workflow_run_id),
            "source_workflow_run_attempt": str(args.source_workflow_run_attempt),
            "fresh_assessment_count_during_recovery": 0,
            "error": f"{type(exc).__name__}: {base._bounded(exc, 2_000)}",
            "finished_at_epoch": time.time(),
        }
        _write(args.output, failure)
        raise
    _write(args.output, result)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
