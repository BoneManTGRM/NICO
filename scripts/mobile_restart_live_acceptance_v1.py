#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Browser, Page, sync_playwright

VERSION = "nico.mobile_restart_live_acceptance.v1"
WORKSPACE_SELECTOR = (
    'main[data-workspace="assessment"]'
    '[data-engagement-type="comprehensive"]'
    '[data-canonical-assessment="strategic"]'
)
STATE_SELECTOR = 'section[data-assessment-run-state="true"]'
ACTION_SELECTOR = '[data-assessment-primary-action="true"]'
AUTHORIZATION_SELECTOR = '[data-assessment-authorization="true"]'
REPORT_ACTIONS_SELECTOR = '[data-assessment-report-actions="true"]'
ACTIVE_RUN_STORAGE_KEY = "nico.comprehensive.active-run.v1"
BROWSER_PROJECTION_HEADER = "X-NICO-Browser-Projection"
BROWSER_PROJECTION_VALUE = "terminal-manifest-v1"
TERMINAL_PHASES = {
    "Internal review required",
    "Revisión interna requerida",
    # Historical aliases remain accepted for already-deployed editions.
    "Expert review required",
    "Se requiere revisión experta",
}
TERMINAL_UI_PENDING_SCORE_MARKERS = (
    "awaiting",
    "not scored",
    "en espera",
    "sin puntuar",
)


def _bounded(value: Any, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _ui_state(page: Page) -> dict[str, str]:
    value = page.evaluate(
        """selector => {
          const section = document.querySelector(selector);
          const compact = value => String(value || '').replace(/\s+/g, ' ').trim();
          if (!section) {
            return {
              phase: '', run_id: '', commit_sha: '', report: '', review: '', score: '',
              report_actions_present: 'false', report_actions_visible: 'false',
              markdown_enabled: 'false', pdf_enabled: 'false', page_url: window.location.href,
            };
          }
          // Desktop identity cards use <article>; the compact iPhone tree uses
          // lightweight <details><p> rows. Both are real rendered identity surfaces.
          const identityRows = Array.from(section.querySelectorAll('article, details p'));
          const find = labels => {
            const row = identityRows.find(item => labels.includes(compact(item.querySelector('b')?.textContent)));
            const code = row?.querySelector('code');
            return compact(code?.getAttribute('title') || code?.textContent || row?.querySelector('span')?.textContent);
          };
          const actions = section.querySelector('[data-assessment-report-actions="true"]');
          const buttons = Array.from(actions?.querySelectorAll('button') || []);
          const markdown = buttons.find(button => /markdown/i.test(button.textContent || ''));
          const pdf = buttons.find(button => /pdf/i.test(button.textContent || ''));
          const rect = actions?.getBoundingClientRect();
          return {
            phase: compact(section.querySelector('.section-head span')?.textContent),
            run_id: find(['Run ID', 'ID de ejecución']),
            commit_sha: find(['Exact commit', 'Immutable commit', 'Commit exacto', 'Commit inmutable']),
            report: find(['Assessment package', 'Report', 'Paquete de evaluación', 'Informe']),
            review: find(['Internal review', 'Expert review', 'Human review', 'Revisión interna', 'Revisión experta', 'Revisión humana']),
            score: find(['Technical maturity', 'Technical score', 'Madurez técnica', 'Puntuación técnica']),
            report_actions_present: actions ? 'true' : 'false',
            report_actions_visible: actions && rect && rect.width > 0 && rect.height > 0 ? 'true' : 'false',
            markdown_enabled: markdown && !markdown.disabled ? 'true' : 'false',
            pdf_enabled: pdf && !pdf.disabled ? 'true' : 'false',
            page_url: window.location.href,
          };
        }""",
        STATE_SELECTOR,
    )
    return {str(key): _bounded(item) for key, item in dict(value or {}).items()}


def _stored_run(page: Page) -> dict[str, Any]:
    value = page.evaluate(
        """key => {
          let parsed = {};
          try { parsed = JSON.parse(window.localStorage.getItem(key) || '{}'); } catch {}
          return {
            run_id: String(parsed.runId || ''),
            repository: String(parsed.repository || ''),
            started_at: Number(parsed.startedAt || 0),
            url_run_id: new URL(window.location.href).searchParams.get('run_id') || '',
          };
        }""",
        ACTIVE_RUN_STORAGE_KEY,
    )
    return dict(value or {})


def _wait_for_run_id(page: Page, timeout_seconds: float) -> tuple[str, dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = _stored_run(page)
        run_id = _bounded(last.get("run_id"), 160)
        if run_id and last.get("url_run_id") == run_id:
            return run_id, last
        page.wait_for_timeout(250)
    raise AssertionError(f"Browser never persisted the exact run identity: {last}")


def _wait_for_same_run_ui(page: Page, run_id: str, timeout_seconds: float) -> dict[str, str]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, str] = {}
    while time.monotonic() < deadline:
        last = _ui_state(page)
        if last.get("run_id") == run_id:
            return last
        page.wait_for_timeout(250)
    raise AssertionError(f"Reloaded page did not restore run {run_id}: {last}")


def _wait_for_terminal(page: Page, run_id: str, timeout_seconds: float) -> dict[str, str]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, str] = {}
    while time.monotonic() < deadline:
        last = _ui_state(page)
        if last.get("run_id") == run_id and last.get("phase") in TERMINAL_PHASES:
            return last
        if last.get("phase") in {"Assessment requires attention", "La evaluación requiere atención"}:
            raise AssertionError(f"Assessment failed before terminal recovery proof: {last}")
        page.wait_for_timeout(1000)
    raise AssertionError(f"Timed out waiting for terminal run {run_id}: {last}")


def _terminal_ui_ready(state: dict[str, str], run_id: str, expected_sha: str) -> bool:
    score = state.get("score", "").strip()
    lowered_score = score.lower()
    return bool(
        state.get("run_id") == run_id
        and state.get("phase") in TERMINAL_PHASES
        and state.get("commit_sha") == expected_sha
        and state.get("report_actions_present") == "true"
        and state.get("report_actions_visible") == "true"
        and state.get("markdown_enabled") == "true"
        and state.get("pdf_enabled") == "true"
        and score
        and not any(marker in lowered_score for marker in TERMINAL_UI_PENDING_SCORE_MARKERS)
    )


def _wait_for_terminal_ui_ready(
    page: Page,
    run_id: str,
    expected_sha: str,
    timeout_seconds: float,
) -> dict[str, str]:
    """Wait for the complete terminal UI contract, not only the phase label.

    The canonical run may reach ``review_required`` before React has projected the
    exact commit, score, and on-demand Markdown/PDF controls. Treat that interval
    as bounded UI synchronization rather than weakening any terminal assertion.
    """

    deadline = time.monotonic() + timeout_seconds
    last: dict[str, str] = {}
    while time.monotonic() < deadline:
        last = _ui_state(page)
        if _terminal_ui_ready(last, run_id, expected_sha):
            return last
        if last.get("phase") in {"Assessment requires attention", "La evaluación requiere atención"}:
            raise AssertionError(f"Assessment failed while waiting for terminal report UI: {last}")
        page.wait_for_timeout(500)
    raise AssertionError(
        f"Terminal phase did not converge to the complete exact-run report UI for {run_id}: {last}"
    )


def _start_count(requests: list[dict[str, str]]) -> int:
    return sum(
        1
        for item in requests
        if item.get("method") == "POST"
        and item.get("path") == "/api/nico/assessment/comprehensive-intake"
    )


def _reload_and_restore(page: Page, run_id: str, timeout_ms: int, *, expect_active_storage: bool) -> dict[str, Any]:
    page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
    page.locator(WORKSPACE_SELECTOR).first.wait_for(state="visible", timeout=timeout_ms)
    state = _wait_for_same_run_ui(page, run_id, min(120.0, timeout_ms / 1000.0))
    stored = _stored_run(page)
    if expect_active_storage:
        assert stored.get("run_id") == run_id
    else:
        assert not stored.get("run_id"), f"Terminal run remained active in localStorage: {stored}"
    assert stored.get("url_run_id") == run_id
    return {"ui": state, "stored": stored}


def _verify_manifest_and_pdf(page: Page, frontend_origin: str, run_id: str) -> dict[str, Any]:
    status = page.request.get(
        f"{frontend_origin}/api/nico/assessment/comprehensive-run/{run_id}",
        headers={
            "Accept": "application/json",
            BROWSER_PROJECTION_HEADER: BROWSER_PROJECTION_VALUE,
            "Cache-Control": "no-store",
        },
        timeout=60_000,
    )
    status_bytes = status.body()
    assert status.ok, f"Projected terminal status returned HTTP {status.status}"
    assert len(status_bytes) < 200_000, f"Projected terminal status was {len(status_bytes)} bytes"
    payload = status.json()
    reports = payload.get("reports") if isinstance(payload.get("reports"), dict) else {}
    assert payload.get("run_id") == run_id
    assert reports.get("response_bounded") is True
    assert reports.get("artifact_delivery") == "on_demand_exact_run"
    assert reports.get("pdf_available") is True
    assert reports.get("markdown_available") is True
    for embedded in ("pdf_base64", "markdown", "html", "json"):
        assert embedded not in reports, f"Projected browser response embedded {embedded}"

    pdf = page.request.get(
        f"{frontend_origin}/api/nico/assessment/comprehensive-run/{run_id}/report/pdf",
        headers={"Accept": "application/pdf", "Cache-Control": "no-store"},
        timeout=120_000,
    )
    pdf_bytes = pdf.body()
    assert pdf.ok, f"Exact-run PDF returned HTTP {pdf.status}"
    assert pdf_bytes.startswith(b"%PDF"), "Exact-run report did not have a PDF signature"
    observed_sha = hashlib.sha256(pdf_bytes).hexdigest()
    expected_sha = str(pdf.headers.get("x-nico-artifact-sha256") or "").lower()
    assert not expected_sha or expected_sha == observed_sha
    assert pdf.headers.get("x-nico-run-id") == run_id
    return {
        "terminal_manifest_size_bytes": len(status_bytes),
        "terminal_manifest_bounded": True,
        "report_artifact_delivery": reports.get("artifact_delivery"),
        "pdf_size_bytes": len(pdf_bytes),
        "pdf_sha256": observed_sha,
        "pdf_signature_verified": True,
        "pdf_run_identity_verified": True,
    }


def run_proof(browser: Browser, args: argparse.Namespace) -> dict[str, Any]:
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        locale="en-US",
        service_workers="block",
        extra_http_headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
    page = context.new_page()
    requests: list[dict[str, str]] = []

    def record_request(request: Any) -> None:
        parsed = urlparse(request.url)
        if parsed.path.startswith("/api/nico/assessment/"):
            requests.append({"method": request.method, "path": parsed.path})

    page.on("request", record_request)
    started_at = time.time()
    try:
        page.goto(
            f"{args.frontend_url.rstrip('/')}/assessment?tier=comprehensive&mobile_restart_probe={time.time_ns()}#assessment",
            wait_until="domcontentloaded",
            timeout=args.navigation_timeout_ms,
        )
        workspace = page.locator(WORKSPACE_SELECTOR).first
        workspace.wait_for(state="visible", timeout=args.navigation_timeout_ms)
        page.get_by_label("Repository owner/name or GitHub URL").fill(args.repository)
        # This production smoke is an internal assessment. Non-empty client/project
        # values invoke Phase 3 client-engagement validation and must never be
        # synthetic labels used only to identify an automated proof run.
        page.get_by_label("Client name, optional").fill("")
        page.get_by_label("Project name, optional").fill("")
        page.locator(AUTHORIZATION_SELECTOR).check()
        page.locator(ACTION_SELECTOR).click()

        run_id, initial_stored = _wait_for_run_id(page, 180.0)
        assert _start_count(requests) == 1

        running_reload = _reload_and_restore(page, run_id, args.navigation_timeout_ms, expect_active_storage=True)
        assert _start_count(requests) == 1, "Running-page reload created a duplicate assessment"

        _wait_for_terminal(page, run_id, args.timeout_seconds)
        terminal_before_reload = _wait_for_terminal_ui_ready(page, run_id, args.expected_sha, 240.0)

        terminal_storage = _stored_run(page)
        assert not terminal_storage.get("run_id"), terminal_storage
        assert terminal_storage.get("url_run_id") == run_id
        terminal_reload = _reload_and_restore(page, run_id, args.navigation_timeout_ms, expect_active_storage=False)
        _wait_for_terminal(page, run_id, 120.0)
        terminal_after_reload = _wait_for_terminal_ui_ready(page, run_id, args.expected_sha, 120.0)
        assert _start_count(requests) == 1, "Terminal-page reload created a duplicate assessment"

        actions = page.locator(REPORT_ACTIONS_SELECTOR).first
        actions.scroll_into_view_if_needed(timeout=args.navigation_timeout_ms)
        page.wait_for_timeout(250)
        scroll_before_resume = float(page.evaluate("() => window.scrollY"))
        status_before = sum(
            1
            for item in requests
            if item.get("method") == "GET" and item.get("path", "").endswith(run_id)
        )
        page.evaluate("() => window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")
        page.wait_for_timeout(750)
        scroll_after_resume = float(page.evaluate("() => window.scrollY"))
        terminal_after_pageshow = _ui_state(page)
        status_after = sum(
            1
            for item in requests
            if item.get("method") == "GET" and item.get("path", "").endswith(run_id)
        )
        assert terminal_after_pageshow.get("run_id") == run_id
        assert terminal_after_pageshow.get("phase") in TERMINAL_PHASES
        assert abs(scroll_after_resume - scroll_before_resume) <= 2
        assert status_after == status_before, "Terminal pageshow restarted exact-run recovery"
        artifacts = _verify_manifest_and_pdf(page, args.frontend_url.rstrip("/"), run_id)
        screenshot_path = args.output.with_suffix(".png")
        screenshot_error = ""
        try:
            page.screenshot(path=str(screenshot_path), full_page=False, timeout=15_000, animations="disabled")
        except Exception as exc:
            screenshot_error = f"{type(exc).__name__}: {_bounded(exc, 320)}"

        return {
            "artifact_schema": VERSION,
            "status": "passed",
            "frontend_url": args.frontend_url.rstrip("/"),
            "repository": args.repository,
            "expected_sha": args.expected_sha,
            "run_id": run_id,
            "viewport": {"width": 390, "height": 844},
            "started_at_epoch": started_at,
            "finished_at_epoch": time.time(),
            "start_request_count": _start_count(requests),
            "duplicate_intake_absent": True,
            "initial_persistence": initial_stored,
            "running_reload": running_reload,
            "terminal_before_reload": terminal_before_reload,
            "terminal_reload": terminal_reload,
            "terminal_after_reload": terminal_after_reload,
            "running_restart_recovery_verified": True,
            "terminal_restart_recovery_verified": True,
            "terminal_run_removed_from_active_storage": True,
            "terminal_pageshow_recovery_absent": True,
            "terminal_scroll_position_preserved": True,
            "terminal_storage": terminal_storage,
            "terminal_after_pageshow": terminal_after_pageshow,
            "exact_run_identity_preserved": True,
            "report_actions_recovered": True,
            **artifacts,
            "screenshot": screenshot_path.as_posix() if screenshot_path.exists() else "",
            "screenshot_sha256": hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
            if screenshot_path.exists()
            else "",
            "screenshot_error": screenshot_error,
        }
    finally:
        context.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prove mobile assessment recovery across browser restarts.")
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=7_200.0)
    parser.add_argument("--navigation-timeout-ms", type=int, default=120_000)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    failure: dict[str, Any] | None = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                result = run_proof(browser, args)
            finally:
                browser.close()
    except Exception as exc:
        failure = {
            "artifact_schema": VERSION,
            "status": "failed",
            "frontend_url": args.frontend_url.rstrip("/"),
            "repository": args.repository,
            "expected_sha": args.expected_sha,
            "error": f"{type(exc).__name__}: {_bounded(exc, 1500)}",
            "finished_at_epoch": time.time(),
        }
        _write(args.output, failure)
        raise
    _write(args.output, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())