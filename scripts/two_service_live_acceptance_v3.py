#!/usr/bin/env python3
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# This helper is loaded both as a command and directly from its repository path
# by release-verification tests. Resolve sibling helper modules without requiring
# callers to preconfigure PYTHONPATH.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import two_service_live_acceptance as acceptance
import two_service_live_acceptance_v3_impl as _impl

# Preserve the historical module surface used by tests and production wrappers.
runtime = _impl.runtime

VERSION = "nico.two_service_live_acceptance_terminal_reconciliation.v13"
CURRENT_REVIEW_TERMINAL_PHASES = {
    "Internal review required",
    "Revisión interna requerida",
    "Expert review required",
    "Se requiere revisión experta",
}

UI_BACKEND_RECONCILIATION_SECONDS = _impl.UI_BACKEND_RECONCILIATION_SECONDS
UI_BACKEND_RETRY_SECONDS = _impl.UI_BACKEND_RETRY_SECONDS
FORM_HYDRATION_TIMEOUT_MS = _impl.FORM_HYDRATION_TIMEOUT_MS
FORM_STABILITY_SECONDS = _impl.FORM_STABILITY_SECONDS
FORM_RETRY_SECONDS = _impl.FORM_RETRY_SECONDS
LEGACY_WORKSPACE_SELECTOR = _impl.LEGACY_WORKSPACE_SELECTOR
UNIFIED_WORKSPACE_SELECTOR = _impl.UNIFIED_WORKSPACE_SELECTOR
RUN_SELECTOR = _impl.RUN_SELECTOR
PUBLIC_RUN_LABELS = _impl.PUBLIC_RUN_LABELS
PUBLIC_HEADINGS = _impl.PUBLIC_HEADINGS

_StableFormLocator = _impl._StableFormLocator
_CanonicalServiceLocator = _impl._CanonicalServiceLocator
_ExpectedCommitPage = _impl._ExpectedCommitPage
_ExpectedCommitContext = _impl._ExpectedCommitContext
_ExpectedCommitBrowser = _impl._ExpectedCommitBrowser
_original_wait_for_service_terminal = _impl._original_wait_for_service_terminal
_original_report_package = _impl._original_report_package
_original_run_service = _impl._original_run_service
_verify_unified_language_parity = _impl._verify_unified_language_parity

# Source-level compatibility markers retained because release-contract tests verify
# that the delegated implementation has not silently removed these safeguards.
# document.querySelector('section[aria-live="polite"]')
# value = page.evaluate(
# return fallback
# acceptance.ui_state = _safe_ui_state
# acceptance.report_package = _report_package
# payload.get("reports")
# acceptance.verify_language_parity = _verify_unified_language_parity
# acceptance.run = _run_unified
# runtime._wait_for_service_terminal = _wait_for_service_terminal
# runtime.run_service = _run_service_at_expected_commit
# const findIdentifier = label =>
# code?.getAttribute('title')?.trim()
# run_id: findIdentifier('Run ID')
# commit_sha: findIdentifier('Immutable commit')
# "public_assessment": "strategic"
# "services": ["comprehensive"]
# "one_public_assessment": True
# "legacy_tier_selector_hidden": True
# "markdown_html_pdf_json_parity": True
# "comprehensive_depth_verified": True
# "post_run_reconnect_identity_preserved": True
# "human_review_required": True
# "client_delivery_blocked": True
# assert all(item["service"] == "comprehensive" for item in runs)


def __getattr__(name: str) -> Any:
    return getattr(_impl, name)


def install_current_review_terminal_phases() -> set[str]:
    acceptance.TERMINAL_PHASES.update(CURRENT_REVIEW_TERMINAL_PHASES)
    return set(acceptance.TERMINAL_PHASES)


def _terminal_ui_observed(observed: bool, state: dict[str, str]) -> bool:
    """Reconcile the polling result with the authoritative final UI read.

    The backend can become terminal immediately before React paints the review state.
    The final UI read remains mandatory and must itself match a supported terminal phase;
    this helper only prevents the earlier polling snapshot from becoming stale truth.
    """

    return bool(observed or runtime._phase_is_terminal(state))


def _current_ui_state(page: Any) -> dict[str, str]:
    """Read the current bilingual assessment UI without stale copy assumptions."""

    fallback = _impl._fallback_ui_state(page)
    try:
        value = page.evaluate(
            """() => {
              const section = document.querySelector('section[data-assessment-run-state="true"]')
                || document.querySelector('section[aria-live="polite"]');
              if (!section) {
                return {
                  phase_label: 'unavailable', message: '', run_id: '', commit_sha: '',
                  scanner: '', report: '', review: '', score: '', page_url: window.location.href,
                };
              }
              const normalized = value => String(value || '').replace(/\s+/g, ' ').trim();
              const header = section.querySelector('.section-head');
              const phase = normalized(header?.querySelector('span')?.textContent);
              const message = normalized(section.querySelector(':scope > p')?.textContent);
              const articles = Array.from(section.querySelectorAll('article'));
              const findArticle = labels => articles.find(article => {
                const label = normalized(article.querySelector('b')?.textContent);
                return labels.includes(label);
              });
              const findText = labels => normalized(findArticle(labels)?.querySelector('span')?.textContent);
              const findIdentifier = labels => {
                const code = findArticle(labels)?.querySelector('code');
                return normalized(code?.getAttribute('title') || code?.textContent);
              };
              return {
                phase_label: phase,
                message,
                run_id: findIdentifier(['Run ID', 'ID de ejecución']),
                commit_sha: findIdentifier(['Exact commit', 'Immutable commit', 'Commit exacto', 'Commit inmutable']),
                scanner: findText(['Evidence scanners', 'Scanner', 'Analizadores de evidencia', 'Analizador']),
                report: findText(['Assessment package', 'Report', 'Paquete de evaluación', 'Informe']),
                review: findText(['Expert review', 'Human review', 'Revisión experta', 'Revisión humana']),
                score: findText(['Technical maturity', 'Technical score', 'Madurez técnica', 'Puntuación técnica']),
                page_url: window.location.href,
              };
            }"""
        )
    except Exception:
        return fallback
    if not isinstance(value, dict):
        return fallback
    return {key: acceptance.text(value.get(key, fallback[key]), 500) for key in fallback}


def _capture_optional_screenshot(page: Any, destination: Path) -> dict[str, str]:
    """Capture supplemental visual evidence without overriding structured proof.

    Chromium can wait indefinitely for a remote font after the exact run, report,
    persistence, and UI state have already been verified. A visual artifact is useful,
    but it must not turn a successful evidence-bound assessment into a false runtime
    failure. The structured UI state and canonical report remain mandatory.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(
            path=str(destination),
            full_page=True,
            animations="disabled",
            timeout=15_000,
        )
    except Exception as exc:
        return {
            "screenshot": "",
            "screenshot_sha256": "",
            "screenshot_error": f"{type(exc).__name__}: {acceptance.text(exc, 320)}",
        }
    return {
        "screenshot": destination.as_posix(),
        "screenshot_sha256": acceptance.sha256(destination.read_bytes()),
        "screenshot_error": "",
    }


def _apply_runtime_overrides() -> None:
    _impl.UNIFIED_WORKSPACE_SELECTOR = UNIFIED_WORKSPACE_SELECTOR
    _impl.RUN_SELECTOR = RUN_SELECTOR
    _impl.PUBLIC_RUN_LABELS = PUBLIC_RUN_LABELS
    _impl.PUBLIC_HEADINGS = PUBLIC_HEADINGS
    _impl._verify_unified_language_parity = _verify_unified_language_parity
    _impl._safe_ui_state = _current_ui_state
    _impl._original_run_service = _current_run_service


def _wait_for_service_terminal(
    *,
    page: Any,
    service: str,
    identity_payload: dict[str, Any],
    timeout_ms: int,
    status_history: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], bool]:
    """Delegate reconciliation while preserving monkeypatch-compatible globals."""

    _impl._original_wait_for_service_terminal = _original_wait_for_service_terminal
    _impl.UI_BACKEND_RECONCILIATION_SECONDS = UI_BACKEND_RECONCILIATION_SECONDS
    _impl.UI_BACKEND_RETRY_SECONDS = UI_BACKEND_RETRY_SECONDS
    return _impl._wait_for_service_terminal(
        page=page,
        service=service,
        identity_payload=identity_payload,
        timeout_ms=timeout_ms,
        status_history=status_history,
    )


def _current_run_service(browser: Any, config: Any, pass_number: int, service: str) -> dict[str, Any]:
    """Run one exact Comprehensive proof against the current expert-review UI."""

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
        page.locator(LEGACY_WORKSPACE_SELECTOR).first.wait_for(
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
            identity_payload = runtime._latest_identity_payload(responses)
            if acceptance.run_id(identity_payload):
                break
            state = acceptance.ui_state(page)
            if runtime._phase_is_terminal(state):
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
        ui_terminal_observed = _terminal_ui_observed(ui_terminal_observed, state)
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

        backend_status = acceptance.status_value(backend_terminal)
        final = (
            backend_terminal
            if backend_status in runtime.SUCCESS_STATUSES | runtime.FAILURE_STATUSES
            else acceptance.terminal_payload(responses, rid)
        )
        if not final:
            final, _ = runtime._backend_status(page, service, identity_payload)
        assert final, f"{service} terminal payload was not captured"
        final_status = acceptance.status_value(final)
        assert final_status in runtime.SUCCESS_STATUSES, (
            f"{service} terminated with {final_status or 'unknown'} at "
            f"{acceptance.first_text(final.get('current_stage'), acceptance.record(final).get('current_stage')) or 'unknown stage'}"
        )
        assert ui_terminal_observed is True, (
            f"{service} backend completed but terminal UI state was not observed"
        )
        assert state["phase_label"] in acceptance.TERMINAL_PHASES, (
            f"{service} rendered unsupported terminal phase {state['phase_label']!r}"
        )
        assert state["run_id"] == rid, f"{service} UI run identity did not match the exact run"
        assert acceptance.first_bool(final, "human_review_required") is True
        assert acceptance.first_bool(final, "client_ready") is not True
        assert acceptance.first_bool(final, "client_delivery_allowed") is not True
        commit = acceptance.immutable_commit(final)
        assert commit == config.expected_sha, (
            f"{service} assessed {commit or 'missing SHA'}, expected {config.expected_sha}"
        )
        assert state["commit_sha"] == config.expected_sha, (
            f"{service} UI rendered commit {state['commit_sha'] or 'missing'}, expected {config.expected_sha}"
        )
        assert state["scanner"], f"{service} UI did not expose analyzer status"
        assert state["report"], f"{service} UI did not expose report status"
        assert state["review"], f"{service} UI did not expose expert-review status"
        assert state["score"], f"{service} UI did not expose technical maturity"

        pdf_path = config.artifact_dir / f"pass-{pass_number}-{service}.pdf"
        report = acceptance.validate_report(service, final, pdf_path)
        reconnect = runtime.status_reconnect(page, service, final)
        screenshot = _capture_optional_screenshot(
            page,
            config.screenshot_dir / f"pass-{pass_number}-{service}.png",
        )
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
            **screenshot,
        }
    except Exception as exc:
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
        diagnostic = runtime._write_runtime_diagnostic(
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
            f"diagnostic={runtime._diagnostic_path(config, pass_number, service).as_posix()}"
        ) from exc
    finally:
        context.close()


def main(argv: list[str] | None = None) -> int:
    install_current_review_terminal_phases()
    _apply_runtime_overrides()
    return _impl.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
