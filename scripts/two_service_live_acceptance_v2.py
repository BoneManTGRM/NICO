#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import two_service_live_acceptance as acceptance

VERSION = "nico.two_service_live_acceptance_reconnect.v3"
STATUS_POLL_SECONDS = 12.0
UI_POLL_SECONDS = 2.0
UI_TERMINAL_GRACE_SECONDS = 90.0
COMPREHENSIVE_STALE_SECONDS = 15 * 60.0
EXPRESS_STALE_SECONDS = 10 * 60.0
COMPREHENSIVE_HARD_EXTENSION_SECONDS = 30 * 60.0
SUCCESS_STATUSES = {"complete", "completed", "review_required"}
FAILURE_STATUSES = {"failed", "blocked", "error", "rejected", "interrupted", "timed_out"}


def _same_origin_url(page: Any, path: str) -> str:
    parsed = urlparse(str(page.url or ""))
    if parsed.scheme != "https" or not parsed.netloc:
        raise AssertionError("acceptance page did not expose an HTTPS origin for reconnect")
    if not path.startswith("/"):
        raise AssertionError("reconnect path must be same-origin absolute")
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _status_request(page: Any, service: str, payload: dict[str, Any]) -> Any:
    rid = acceptance.run_id(payload)
    if not rid:
        raise AssertionError(f"{service} status read is missing the exact run ID")

    if service == "express":
        customer = acceptance.first_text(payload.get("customer_id"))
        project = acceptance.first_text(payload.get("project_id"))
        path = f"/api/nico/assessment/express-run/{rid}/status"
        response = page.request.post(
            _same_origin_url(page, path),
            data={"customer_id": customer, "project_id": project},
            timeout=30_000,
        )
    elif service == "comprehensive":
        path = f"/api/nico/assessment/comprehensive-run/{rid}"
        response = page.request.get(_same_origin_url(page, path), timeout=30_000)
    else:
        raise AssertionError(f"unsupported acceptance service: {service}")
    return response, path


def status_reconnect(
    page: Any,
    service: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Reconnect to the exact completed run through an absolute same-origin URL.

    Playwright's page request context does not inherit the browser page URL as a
    base URL. Relative paths therefore raise ``APIRequestContext: Invalid URL``
    even when the deployed application and run completed correctly. Build the
    URL from the already validated browser origin and preserve the original
    exact-run identity and integrity assertions.
    """

    rid = acceptance.run_id(payload)
    response, path = _status_request(page, service, payload)
    assert 200 <= response.status < 300, (
        f"{service} reconnect returned HTTP {response.status}"
    )
    current = acceptance.response_json(response)
    assert acceptance.run_id(current) == rid, (
        f"{service} reconnect changed run identity"
    )

    before_revision, before_integrity = acceptance.integrity(payload)
    after_revision, after_integrity = acceptance.integrity(current)
    if before_revision is not None and after_revision is not None:
        assert after_revision >= before_revision
    if before_integrity and after_integrity:
        assert after_integrity == before_integrity

    return {
        "artifact_schema": VERSION,
        "http_status": response.status,
        "run_id": rid,
        "request_url": _same_origin_url(page, path),
        "revision_before": before_revision,
        "revision_after": after_revision,
        "integrity_before": before_integrity,
        "integrity_after": after_integrity,
        "identity_preserved": True,
    }


def _bounded_number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _status_summary(payload: dict[str, Any], *, http_status: int | None = None) -> dict[str, Any]:
    """Return bounded lifecycle evidence without report bodies or encoded PDFs."""

    record = acceptance.record(payload)
    completed = record.get("completed_stages")
    completed_stages = [acceptance.text(item, 100) for item in completed] if isinstance(completed, list) else []
    detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else {}
    persistence = payload.get("persistence") if isinstance(payload.get("persistence"), dict) else {}
    return {
        "observed_at_epoch": acceptance.now_epoch(),
        "http_status": http_status,
        "run_id": acceptance.run_id(payload),
        "status": acceptance.status_value(payload),
        "current_stage": acceptance.first_text(payload.get("current_stage"), record.get("current_stage")),
        "progress_percent": _bounded_number(payload.get("progress_percent")),
        "canonical_progress_percent": _bounded_number(payload.get("canonical_progress_percent")),
        "active_stage_progress_percent": _bounded_number(payload.get("active_stage_progress_percent")),
        "revision": _bounded_number(payload.get("revision", record.get("revision"))),
        "terminal": bool(payload.get("terminal", record.get("terminal", False))),
        "completed_stage_count": len(completed_stages),
        "completed_stages": completed_stages,
        "code": acceptance.first_text(detail.get("code"), payload.get("code")),
        "message": acceptance.text(
            acceptance.first_text(detail.get("message"), payload.get("message"), record.get("message")),
            320,
        ),
        "persistence": {
            "recorded": persistence.get("recorded"),
            "durable": persistence.get("durable"),
            "adapter": acceptance.first_text(persistence.get("adapter")),
            "storage_source": acceptance.first_text(persistence.get("storage_source")),
        },
    }


def _activity_signature(payload: dict[str, Any]) -> tuple[Any, ...]:
    summary = _status_summary(payload)
    return (
        summary["status"],
        summary["current_stage"],
        summary["progress_percent"],
        summary["canonical_progress_percent"],
        summary["active_stage_progress_percent"],
        summary["revision"],
        summary["completed_stage_count"],
        summary["terminal"],
    )


def _response_payloads(responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item["payload"] for item in responses if isinstance(item.get("payload"), dict)]


def _latest_identity_payload(responses: list[dict[str, Any]]) -> dict[str, Any]:
    for payload in reversed(_response_payloads(responses)):
        if acceptance.run_id(payload):
            return payload
    return {}


def _diagnostic_path(config: Any, pass_number: int, service: str) -> Path:
    return config.artifact_dir / f"pass-{pass_number}-{service}-runtime-diagnostic.json"


def _write_runtime_diagnostic(
    *,
    config: Any,
    pass_number: int,
    service: str,
    page: Any,
    run_payload: dict[str, Any],
    state: dict[str, str],
    status_history: list[dict[str, Any]],
    requests: list[dict[str, Any]],
    responses: list[dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    screenshot = config.screenshot_dir / f"pass-{pass_number}-{service}-runtime-diagnostic.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot_error = ""
    try:
        page.screenshot(path=str(screenshot), full_page=True)
    except Exception as exc:  # pragma: no cover - best effort after browser failure
        screenshot_error = f"{type(exc).__name__}: {acceptance.text(exc, 240)}"

    continuation_pattern = acceptance.CONTINUATION_PATTERNS[service]
    continuation_requests = [
        item for item in requests
        if continuation_pattern.fullmatch(str(item.get("path") or ""))
    ]
    bounded_responses = []
    for item in responses[-20:]:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        bounded_responses.append({
            "method": item.get("method"),
            "path": item.get("path"),
            "http_status": item.get("http_status"),
            "status": acceptance.status_value(payload),
            "run_id": acceptance.run_id(payload),
            "current_stage": acceptance.first_text(payload.get("current_stage"), acceptance.record(payload).get("current_stage")),
            "revision": _bounded_number(payload.get("revision", acceptance.record(payload).get("revision"))),
        })

    diagnostic = {
        "artifact_schema": VERSION,
        "status": "failed",
        "reason": acceptance.text(reason, 1000),
        "service": service,
        "pass": pass_number,
        "run_id": acceptance.run_id(run_payload) or state.get("run_id", ""),
        "page_url": acceptance.text(getattr(page, "url", ""), 500),
        "ui": state,
        "last_backend_status": status_history[-1] if status_history else {},
        "backend_status_history": status_history[-40:],
        "start_request_count": len([
            item for item in requests
            if item.get("method") == "POST" and item.get("path") == acceptance.START_PATHS[service]
        ]),
        "continuation_request_count": len(continuation_requests),
        "recent_responses": bounded_responses,
        "screenshot": screenshot.as_posix() if screenshot.exists() else "",
        "screenshot_sha256": acceptance.sha256(screenshot.read_bytes()) if screenshot.exists() else "",
        "screenshot_error": screenshot_error,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    destination = _diagnostic_path(config, pass_number, service)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(diagnostic, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return diagnostic


def _backend_status(
    page: Any,
    service: str,
    identity_payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    response, _ = _status_request(page, service, identity_payload)
    payload = acceptance.response_json(response)
    summary = _status_summary(payload, http_status=response.status)
    if not 200 <= response.status < 300:
        return {}, summary
    expected = acceptance.run_id(identity_payload)
    observed = acceptance.run_id(payload)
    if expected and observed != expected:
        raise AssertionError(
            f"{service} status read changed run identity from {expected} to {observed or 'missing'}"
        )
    return payload, summary


def _phase_is_terminal(state: dict[str, str]) -> bool:
    return state.get("phase_label", "") in acceptance.TERMINAL_PHASES


def _wait_for_service_terminal(
    *,
    page: Any,
    service: str,
    identity_payload: dict[str, Any],
    timeout_ms: int,
    status_history: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], bool]:
    """Observe both the browser and exact durable run until a truthful terminal state.

    The old acceptance proof waited on one DOM label for a full hour. When a live
    Comprehensive run did not render that label, the artifact contained no run ID,
    backend stage, revision, or progress. This loop treats the configured timeout as
    the normal budget, allows bounded extra time only while the exact persisted run is
    still making progress, and never replaces the exact run or starts a duplicate.
    """

    started = time.monotonic()
    normal_deadline = started + timeout_ms / 1000.0
    hard_deadline = normal_deadline + (
        COMPREHENSIVE_HARD_EXTENSION_SECONDS if service == "comprehensive" else 0.0
    )
    stale_window = COMPREHENSIVE_STALE_SECONDS if service == "comprehensive" else EXPRESS_STALE_SECONDS
    stale_deadline = min(normal_deadline, started + stale_window)
    last_status_read = 0.0
    last_signature: tuple[Any, ...] | None = None
    last_payload: dict[str, Any] = {}
    backend_terminal_at: float | None = None

    while True:
        now = time.monotonic()
        state = acceptance.ui_state(page)
        if _phase_is_terminal(state):
            return last_payload, state, True

        if now - last_status_read >= STATUS_POLL_SECONDS:
            last_status_read = now
            try:
                current, summary = _backend_status(page, service, identity_payload)
            except Exception as exc:
                current = {}
                summary = {
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
            status_history.append(summary)
            if current:
                last_payload = current
                signature = _activity_signature(current)
                if signature != last_signature:
                    last_signature = signature
                    stale_deadline = min(hard_deadline, now + stale_window)
                status = acceptance.status_value(current)
                terminal = bool(current.get("terminal", acceptance.record(current).get("terminal", False)))
                if status in FAILURE_STATUSES:
                    return current, state, False
                if status in SUCCESS_STATUSES or terminal:
                    if status not in SUCCESS_STATUSES:
                        return current, state, False
                    backend_terminal_at = backend_terminal_at or now
                    if now - backend_terminal_at >= UI_TERMINAL_GRACE_SECONDS:
                        raise AssertionError(
                            f"{service} backend reached {status} for run {acceptance.run_id(current)} "
                            f"but the browser did not render a terminal phase within "
                            f"{int(UI_TERMINAL_GRACE_SECONDS)} seconds; last UI phase was "
                            f"{state.get('phase_label') or 'missing'}"
                        )

        if now >= hard_deadline:
            summary = status_history[-1] if status_history else {}
            raise TimeoutError(
                f"{service} exact run {acceptance.run_id(identity_payload)} exceeded the bounded "
                f"{int((hard_deadline - started) / 60)}-minute acceptance ceiling; "
                f"last status={summary.get('status') or 'unknown'}, "
                f"stage={summary.get('current_stage') or 'unknown'}, "
                f"progress={summary.get('progress_percent')}, revision={summary.get('revision')}"
            )
        if now >= stale_deadline and backend_terminal_at is None:
            summary = status_history[-1] if status_history else {}
            raise TimeoutError(
                f"{service} exact run {acceptance.run_id(identity_payload)} made no observable "
                f"backend progress for {int(stale_window / 60)} minutes; "
                f"last status={summary.get('status') or 'unknown'}, "
                f"stage={summary.get('current_stage') or 'unknown'}, "
                f"progress={summary.get('progress_percent')}, revision={summary.get('revision')}"
            )

        page.wait_for_timeout(int(UI_POLL_SECONDS * 1000))


def run_service(browser: Any, config: Any, pass_number: int, service: str) -> dict[str, Any]:
    label = acceptance.SERVICE_LABELS[service]
    context = browser.new_context(viewport={"width": 390, "height": 844}, locale="en-US")
    page = context.new_page()
    requests: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    status_history: list[dict[str, Any]] = []
    identity_payload: dict[str, Any] = {}

    def on_request(request: Any) -> None:
        parsed = urlparse(request.url)
        if parsed.path.startswith("/api/nico/assessment/"):
            requests.append({"method": request.method, "path": parsed.path})

    def on_response(response: Any) -> None:
        parsed = urlparse(response.url)
        if not parsed.path.startswith("/api/nico/assessment/"):
            return
        responses.append({
            "method": response.request.method,
            "path": parsed.path,
            "http_status": response.status,
            "payload": acceptance.response_json(response),
        })

    page.on("request", on_request)
    page.on("response", on_response)
    started_at = acceptance.now_epoch()
    try:
        page.goto(
            f"{config.frontend_origin}/assessment?tier={service}#assessment",
            wait_until="domcontentloaded",
            timeout=config.navigation_timeout_ms,
        )
        page.locator('main[data-assessment-service-count="2"]').first.wait_for(
            state="visible",
            timeout=config.navigation_timeout_ms,
        )
        button = page.get_by_role("button", name=label, exact=True)
        if button.get_attribute("aria-pressed") != "true":
            button.click()
        client = f"Production Acceptance Pass {pass_number}"
        project = f"NICO {service.title()} Acceptance {pass_number}"
        page.get_by_label("Repository owner/name or GitHub URL").fill(config.repository)
        page.get_by_label("Client name, optional").fill(client)
        page.get_by_label("Project name, optional").fill(project)
        page.get_by_role(
            "checkbox",
            name="I confirm I own this target or have explicit permission to assess it.",
        ).check()
        page.get_by_role("button", name=f"Run {label}", exact=True).click()

        identity_deadline = time.monotonic() + min(180.0, config.navigation_timeout_ms / 1000.0)
        while time.monotonic() < identity_deadline:
            identity_payload = _latest_identity_payload(responses)
            if acceptance.run_id(identity_payload):
                break
            state = acceptance.ui_state(page)
            if _phase_is_terminal(state):
                break
            page.wait_for_timeout(500)
        if not acceptance.run_id(identity_payload):
            state = acceptance.ui_state(page)
            raise AssertionError(
                f"{service} start did not expose an exact run ID; UI phase was "
                f"{state.get('phase_label') or 'missing'}"
            )

        timeout = config.express_timeout_ms if service == "express" else config.comprehensive_timeout_ms
        backend_terminal, state, ui_terminal_observed = _wait_for_service_terminal(
            page=page,
            service=service,
            identity_payload=identity_payload,
            timeout_ms=timeout,
            status_history=status_history,
        )
        page.wait_for_timeout(1000)
        state = acceptance.ui_state(page)
        rid = state["run_id"] or acceptance.run_id(identity_payload)
        assert rid, f"{service} UI did not expose a run ID"

        start_requests = [
            item for item in requests
            if item["method"] == "POST" and item["path"] == acceptance.START_PATHS[service]
        ]
        assert len(start_requests) == 1, f"{service} emitted {len(start_requests)} start requests"
        continuation = [
            item for item in requests
            if acceptance.CONTINUATION_PATTERNS[service].fullmatch(item["path"])
        ]
        assert continuation, f"{service} emitted no exact-run continuation requests"
        assert all(
            acceptance.CONTINUATION_PATTERNS[service].fullmatch(item["path"]).group(1) == rid
            for item in continuation
        )
        observed_run_ids = {
            acceptance.run_id(item["payload"])
            for item in responses
            if acceptance.run_id(item["payload"])
        }
        observed_run_ids.update(
            str(item.get("run_id") or "") for item in status_history if item.get("run_id")
        )
        assert observed_run_ids == {rid}, f"{service} response identity drift: {sorted(observed_run_ids)}"

        final = backend_terminal or acceptance.terminal_payload(responses, rid)
        if not final:
            final, _ = _backend_status(page, service, identity_payload)
        assert final, f"{service} terminal payload was not captured"
        final_status = acceptance.status_value(final)
        assert final_status in SUCCESS_STATUSES, (
            f"{service} terminated with {final_status or 'unknown'} at "
            f"{acceptance.first_text(final.get('current_stage'), acceptance.record(final).get('current_stage')) or 'unknown stage'}"
        )
        assert ui_terminal_observed is True
        assert state["phase_label"] in {"Complete", "Human review required"}
        assert acceptance.first_bool(final, "human_review_required") is True
        assert acceptance.first_bool(final, "client_ready") is not True
        assert acceptance.first_bool(final, "client_delivery_allowed") is not True
        commit = acceptance.immutable_commit(final)
        assert commit == config.expected_sha, (
            f"{service} assessed {commit or 'missing SHA'}, expected {config.expected_sha}"
        )
        pdf_path = config.artifact_dir / f"pass-{pass_number}-{service}.pdf"
        report = acceptance.validate_report(service, final, pdf_path)
        reconnect = status_reconnect(page, service, final)
        screenshot = config.screenshot_dir / f"pass-{pass_number}-{service}.png"
        page.screenshot(path=str(screenshot), full_page=True)
        return {
            "status": "passed",
            "pass": pass_number,
            "service": service,
            "started_at_epoch": started_at,
            "finished_at_epoch": acceptance.now_epoch(),
            "run_id": rid,
            "repository": acceptance.first_text(final.get("repository"), config.repository),
            "commit_sha": commit,
            "evidence_ledger_id": acceptance.first_text(final.get("evidence_ledger_id")),
            "customer_id": acceptance.first_text(final.get("customer_id")),
            "project_id": acceptance.first_text(final.get("project_id")),
            "terminal_status": final_status,
            "ui": state,
            "ui_terminal_observed": True,
            "start_count": len(start_requests),
            "continuation_count": len(continuation),
            "continuation_paths": sorted({item["path"] for item in continuation}),
            "response_run_ids": sorted(observed_run_ids),
            "backend_status_poll_count": len(status_history),
            "backend_status_history": status_history,
            "human_review_required": True,
            "client_ready": False,
            "client_delivery_allowed": False,
            "report": report,
            "reconnect": reconnect,
            "screenshot": screenshot.as_posix(),
            "screenshot_sha256": acceptance.sha256(screenshot.read_bytes()),
        }
    except Exception as exc:
        state: dict[str, str]
        try:
            state = acceptance.ui_state(page)
        except Exception:
            state = {
                "phase_label": "unavailable",
                "message": "",
                "run_id": acceptance.run_id(identity_payload),
                "commit_sha": "",
                "scanner": "",
                "report": "",
                "review": "",
                "score": "",
                "page_url": acceptance.text(getattr(page, "url", ""), 500),
            }
        diagnostic = _write_runtime_diagnostic(
            config=config,
            pass_number=pass_number,
            service=service,
            page=page,
            run_payload=identity_payload,
            state=state,
            status_history=status_history,
            requests=requests,
            responses=responses,
            reason=f"{type(exc).__name__}: {acceptance.text(exc, 1000)}",
        )
        raise AssertionError(
            f"{service} production acceptance failed for run "
            f"{diagnostic.get('run_id') or 'missing'}: {acceptance.text(exc, 900)}; "
            f"diagnostic={_diagnostic_path(config, pass_number, service).as_posix()}"
        ) from exc
    finally:
        context.close()


def main(argv: list[str] | None = None) -> int:
    acceptance.status_reconnect = status_reconnect
    acceptance.run_service = run_service
    return acceptance.main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Configuration blocked: {exc}", file=sys.stderr)
        raise SystemExit(2)
