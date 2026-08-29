#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Browser, Page, sync_playwright

from comprehensive_production_run_handoff_v1 import (
    load_source_proof,
    require_canonical_json_digest,
    require_matching_canonical_truth_digest,
    source_binding_marker,
)

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
HEADED_CHROMIUM_ENV = "NICO_PROOF_HEADED_CHROMIUM"
HEADED_WEBKIT_ENV = "NICO_PROOF_HEADED_WEBKIT"
NATIVE_VISIBILITY_ENV = "NICO_PROOF_NATIVE_VISIBILITY"
NATIVE_VISIBILITY_RUNTIME = "nico.playwright_native_visibility.v1"
WEBKIT_NATIVE_VISIBILITY_RUNTIME = "nico.x11_window_visibility.v1"
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


def _require_existing_source_args(args: argparse.Namespace) -> str:
    source_proof = getattr(args, "source_proof", None)
    if not isinstance(source_proof, Path) or not source_proof.is_file():
        raise ValueError("existing_run_source_proof_required")
    marker = source_binding_marker(
        getattr(args, "source_workflow_run_id", ""),
        getattr(args, "source_workflow_run_attempt", ""),
    )
    if float(getattr(args, "observation_seconds", 0.0) or 0.0) < 90.0:
        raise ValueError("terminal_observation_must_be_at_least_90_seconds")
    if getattr(args, "ui_locale", "") not in {"en", "es-MX"}:
        raise ValueError("supported_ui_locale_required")
    return marker


def _ui_state(page: Page) -> dict[str, str]:
    value = page.evaluate(
        r"""selector => {
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
    canonical_truth_sha256 = str(
        reports.get("canonical_truth_sha256") or ""
    ).lower()
    assert re.fullmatch(r"[0-9a-f]{64}", canonical_truth_sha256), {
        "missing_or_invalid_manifest_canonical_truth_sha256": canonical_truth_sha256,
    }
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
    assert re.fullmatch(r"[0-9a-f]{64}", expected_sha), {
        "missing_or_invalid_artifact_sha256_header": expected_sha,
    }
    assert expected_sha == observed_sha
    assert pdf.headers.get("x-nico-run-id") == run_id
    pdf_canonical_truth_sha256 = require_matching_canonical_truth_digest(
        canonical_truth_sha256,
        pdf.headers.get("x-nico-canonical-truth-sha256"),
    )
    return {
        "terminal_manifest_size_bytes": len(status_bytes),
        "terminal_manifest_bounded": True,
        "report_artifact_delivery": reports.get("artifact_delivery"),
        "pdf_size_bytes": len(pdf_bytes),
        "pdf_sha256": observed_sha,
        "pdf_artifact_hash_header_verified": True,
        "canonical_truth_sha256": pdf_canonical_truth_sha256,
        "pdf_canonical_truth_digest_verified": True,
        "pdf_signature_verified": True,
        "pdf_run_identity_verified": True,
    }


def run_proof(browser: Browser, args: argparse.Namespace) -> dict[str, Any]:
    _require_existing_source_args(args)
    return run_existing_proof(browser, args)


def _continuation_count(requests: list[dict[str, str]]) -> int:
    return sum(
        1
        for item in requests
        if item.get("method") == "POST"
        and item.get("path", "").startswith("/api/nico/assessment/comprehensive-run/")
        and item.get("path", "").endswith("/continue")
    )


def _blocking_overlay_count(page: Any) -> int:
    return int(
        page.evaluate(
            """() => Array.from(document.querySelectorAll('body *')).filter(node => {
              const style = getComputedStyle(node);
              const rect = node.getBoundingClientRect();
              return style.position === 'fixed'
                && style.display !== 'none'
                && style.visibility !== 'hidden'
                && Number(style.opacity || 1) > 0
                && style.pointerEvents !== 'none'
                && rect.width >= innerWidth * 0.7
                && rect.height >= innerHeight * 0.7;
            }).length"""
        )
    )


def _headed_chromium_requested() -> bool:
    configured = os.getenv(HEADED_CHROMIUM_ENV, "").strip()
    if configured not in {"", "0", "1"}:
        raise RuntimeError("nico_proof_headed_chromium_setting_invalid")
    return configured == "1"


def _native_visibility_requested() -> bool:
    configured = os.getenv(NATIVE_VISIBILITY_ENV, "").strip()
    if configured not in {"", "0", "1"}:
        raise RuntimeError("nico_proof_native_visibility_setting_invalid")
    return configured == "1"


def _headed_webkit_requested() -> bool:
    configured = os.getenv(HEADED_WEBKIT_ENV, "").strip()
    if configured not in {"", "0", "1"}:
        raise RuntimeError("nico_proof_headed_webkit_setting_invalid")
    return configured == "1"


def _grant_supported_clipboard_permissions(context: Any, *, origin: str) -> str:
    """Grant only the clipboard permissions supported by the active engine.

    Chromium needs the explicit grant for the two real Copy Markdown gestures.
    Playwright WebKit rejects ``clipboard-write`` as an unknown permission before
    the first page can open; its trusted button gesture exercises clipboard write
    without a synthetic browser-context grant.
    """

    raw_context = getattr(context, "_context", context)
    browser = getattr(raw_context, "browser", None)
    browser_type = getattr(browser, "browser_type", None)
    browser_engine = str(getattr(browser_type, "name", "") or "").strip().lower()
    if browser_engine == "chromium":
        raw_context.grant_permissions(
            ["clipboard-read", "clipboard-write"],
            origin=origin,
        )
    elif browser_engine != "webkit":
        raise RuntimeError(
            f"unsupported_clipboard_permission_browser_engine:{browser_engine or 'unknown'}"
        )
    return browser_engine


def _launch_chromium(playwright: Any) -> Any:
    headed = _headed_chromium_requested()
    if headed and not os.getenv("DISPLAY", "").strip():
        raise RuntimeError("headed_chromium_proof_requires_x_display")
    if headed and not _native_visibility_requested():
        raise RuntimeError(
            "headed_chromium_proof_requires_native_visibility_runtime"
        )
    return playwright.chromium.launch(headless=not headed)


def _launch_webkit(playwright: Any) -> Any:
    headed = _headed_webkit_requested()
    if headed and not os.getenv("DISPLAY", "").strip():
        raise RuntimeError("headed_webkit_proof_requires_x_display")
    if headed and shutil.which("xdotool") is None:
        raise RuntimeError("headed_webkit_proof_requires_xdotool")
    return playwright.webkit.launch(headless=not headed)


def _visible_webkit_window_ids(*, timeout_ms: int) -> list[int]:
    xdotool = shutil.which("xdotool")
    if xdotool is None:
        raise RuntimeError("headed_webkit_proof_requires_xdotool")
    completed = subprocess.run(
        [
            xdotool,
            "search",
            "--onlyvisible",
            "--maxdepth",
            "1",
            "--class",
            "MiniBrowser",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=max(1.0, min(timeout_ms / 1_000, 30.0)),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "webkit_native_window_search_failed: "
            f"returncode={completed.returncode} stderr={_bounded(completed.stderr)}"
        )
    try:
        window_ids = sorted({int(value) for value in completed.stdout.split()})
    except ValueError as exc:
        raise RuntimeError("webkit_native_window_id_invalid") from exc
    if len(window_ids) != 1:
        raise RuntimeError(
            f"webkit_subject_window_count_must_equal_one:{len(window_ids)}"
        )
    return window_ids


def _set_webkit_windows_mapped(
    window_ids: list[int],
    *,
    mapped: bool,
    timeout_ms: int,
) -> None:
    xdotool = shutil.which("xdotool")
    if xdotool is None:
        raise RuntimeError("headed_webkit_proof_requires_xdotool")
    action = "windowmap" if mapped else "windowunmap"
    for window_id in window_ids:
        subprocess.run(
            [xdotool, action, "--sync", str(window_id)],
            check=True,
            capture_output=True,
            text=True,
            timeout=max(1.0, min(timeout_ms / 1_000, 30.0)),
        )


def _prove_visibility_hidden_visible(
    page: Any,
    context: Any,
    *,
    timeout_ms: int,
) -> dict[str, Any]:
    raw_context = getattr(context, "_context", context)
    raw_page = getattr(page, "_page", page)
    browser = getattr(raw_context, "browser", None)
    browser_type = getattr(browser, "browser_type", None)
    browser_engine = str(getattr(browser_type, "name", "") or "").strip().lower()
    initial = str(raw_page.evaluate("() => document.visibilityState"))
    assert initial == "visible", f"Assessment page was not initially visible: {initial}"
    raw_page.evaluate(
        """() => {
          window.__nicoVisibilityTransitions = [];
          if (typeof window.__nicoVisibilityObserver !== 'function') {
            window.__nicoVisibilityObserver = () => {
              window.__nicoVisibilityTransitions.push(document.visibilityState);
            };
            document.addEventListener(
              'visibilitychange',
              window.__nicoVisibilityObserver,
            );
          }
        }"""
    )
    if browser_engine == "chromium" and not _headed_chromium_requested():
        raise RuntimeError(
            "chromium_visibility_proof_requires_headed_browser_under_xvfb"
        )
    # Current Chromium headless targets report every Page as visible. The pinned proof
    # runtime prevents Playwright's private focus-emulation session from registering a
    # visible capturer before target initialization. An opener-created sibling tab in
    # the same native window can therefore exercise Chromium's browser-owned Page
    # Visibility boundary without redefining document properties or dispatching events.
    # WebKit already exposes a native tab boundary in its Playwright runtime.
    if browser_engine == "chromium" and not _native_visibility_requested():
        raise RuntimeError(
            "chromium_visibility_proof_requires_native_visibility_runtime"
        )
    if browser_engine == "webkit" and not _headed_webkit_requested():
        raise RuntimeError(
            "webkit_visibility_proof_requires_headed_browser_under_xvfb"
        )
    if browser_engine not in {"chromium", "webkit"}:
        raise RuntimeError(
            f"unsupported_visibility_browser_engine:{browser_engine or 'unknown'}"
        )
    subject_session = None
    background_session = None
    background = None
    subject_window_id: int | None = None
    background_window_id: int | None = None
    subject_target_id = ""
    background_target_id = ""
    subject_target_type = ""
    background_target_type = ""
    webkit_window_ids: list[int] = []
    webkit_windows_unmapped = False
    transitions: list[str] = []
    try:
        if browser_engine == "chromium":
            with raw_page.expect_popup(timeout=timeout_ms) as popup:
                opened = raw_page.evaluate(
                    "() => Boolean(window.open('about:blank', '_blank'))"
                )
                assert opened is True, "chromium_same_window_popup_was_blocked"
            background = popup.value
            background.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            subject_session = raw_context.new_cdp_session(raw_page)
            background_session = raw_context.new_cdp_session(background)
            subject_target = subject_session.send("Target.getTargetInfo")
            background_target = background_session.send("Target.getTargetInfo")
            subject_target_id = str(subject_target["targetInfo"]["targetId"])
            background_target_id = str(background_target["targetInfo"]["targetId"])
            subject_target_type = str(subject_target["targetInfo"].get("type", ""))
            background_target_type = str(
                background_target["targetInfo"].get("type", "")
            )
            if subject_target_type != "page" or background_target_type != "page":
                raise AssertionError(
                    "chromium_visibility_targets_must_be_pages: "
                    f"subject_type={subject_target_type!r} "
                    f"background_type={background_target_type!r}"
                )
            subject_window = subject_session.send(
                "Browser.getWindowForTarget",
                {"targetId": subject_target_id},
            )
            background_window = background_session.send(
                "Browser.getWindowForTarget",
                {"targetId": background_target_id},
            )
            subject_window_id = int(subject_window["windowId"])
            background_window_id = int(background_window["windowId"])
            if subject_window_id != background_window_id:
                raise AssertionError(
                    "chromium_visibility_tabs_not_in_same_native_window: "
                    f"subject_window={subject_window_id} "
                    f"background_window={background_window_id} "
                    f"subject_target={subject_target_id!r} "
                    f"background_target={background_target_id!r}"
                )
        else:
            webkit_window_ids = _visible_webkit_window_ids(timeout_ms=timeout_ms)
        raw_page.bring_to_front()
        prepared_visibility = str(
            raw_page.evaluate("() => document.visibilityState")
        )
        assert prepared_visibility == "visible", prepared_visibility
        raw_page.evaluate("() => { window.__nicoVisibilityTransitions = []; }")
        if browser_engine == "chromium":
            background.bring_to_front()
        else:
            _set_webkit_windows_mapped(
                webkit_window_ids,
                mapped=False,
                timeout_ms=timeout_ms,
            )
            webkit_windows_unmapped = True
        # Background documents suppress requestAnimationFrame; bounded interval
        # polling can observe the real hidden state without changing page globals.
        raw_page.wait_for_function(
            "() => document.hidden === true && document.visibilityState === 'hidden'",
            polling=100,
            timeout=timeout_ms,
        )
        hidden = str(raw_page.evaluate("() => document.visibilityState"))
        if browser_engine == "webkit":
            _set_webkit_windows_mapped(
                webkit_window_ids,
                mapped=True,
                timeout_ms=timeout_ms,
            )
            webkit_windows_unmapped = False
        raw_page.bring_to_front()
        raw_page.wait_for_function(
            "() => document.hidden === false && document.visibilityState === 'visible'",
            polling=100,
            timeout=timeout_ms,
        )
        visible = str(raw_page.evaluate("() => document.visibilityState"))
        transitions = list(
            raw_page.evaluate(
                "() => Array.from(window.__nicoVisibilityTransitions || [])"
            )
            or []
        )
    finally:
        try:
            if webkit_windows_unmapped:
                _set_webkit_windows_mapped(
                    webkit_window_ids,
                    mapped=True,
                    timeout_ms=timeout_ms,
                )
            raw_page.bring_to_front()
        finally:
            try:
                if background_session is not None:
                    background_session.detach()
            finally:
                try:
                    if subject_session is not None:
                        subject_session.detach()
                finally:
                    if background is not None:
                        background.close()
    mechanism = (
        "opener_tab_activation_without_playwright_focus_emulation"
        if browser_engine == "chromium"
        else "x11_window_unmap_map"
    )
    assert hidden == "hidden" and visible == "visible", transitions
    assert transitions[-2:] == ["hidden", "visible"], transitions
    return {
        "initial_visibility": initial,
        "terminal_visibility_transitions": ["hidden", "visible"],
        "observed_visibility_transitions": transitions,
        "browser_engine": browser_engine or "unknown",
        "browser_launch_mode": (
            "headed_xvfb"
            if (
                browser_engine == "chromium" and _headed_chromium_requested()
            ) or (
                browser_engine == "webkit" and _headed_webkit_requested()
            )
            else "headless"
        ),
        "visibility_transition_mechanism": mechanism,
        "native_visibility_runtime": (
            NATIVE_VISIBILITY_RUNTIME
            if browser_engine == "chromium"
            else WEBKIT_NATIVE_VISIBILITY_RUNTIME
        ),
        "playwright_focus_emulation_enabled": (
            False if browser_engine == "chromium" else None
        ),
        "shared_native_window": (
            subject_window_id == background_window_id
            if browser_engine == "chromium"
            else None
        ),
        "subject_window_id": subject_window_id,
        "webkit_window_ids": webkit_window_ids,
        "background_window_id": background_window_id,
        "subject_target_id": subject_target_id,
        "background_target_id": background_target_id,
        "subject_target_type": subject_target_type,
        "background_target_type": background_target_type,
        "document_hidden_observed": True,
        "document_visible_after_foreground": True,
    }


def _verify_canonical_truth(
    page: Any,
    *,
    frontend_origin: str,
    run_id: str,
    expected_sha: str,
    expected_digest: str,
) -> dict[str, Any]:
    status = page.request.get(
        f"{frontend_origin}/api/nico/assessment/comprehensive-run/{run_id}",
        headers={
            "Accept": "application/json",
            BROWSER_PROJECTION_HEADER: BROWSER_PROJECTION_VALUE,
            "Cache-Control": "no-store",
        },
        timeout=60_000,
    )
    assert status.ok, f"Canonical terminal status returned HTTP {status.status}"
    payload = status.json()
    reports = payload.get("reports") if isinstance(payload.get("reports"), dict) else {}
    assert payload.get("run_id") == run_id
    assert payload.get("commit_sha") == expected_sha
    assert payload.get("terminal") is True
    assert payload.get("human_review_required") is True
    assert payload.get("client_delivery_allowed") is False

    report = page.request.get(
        f"{frontend_origin}/api/nico/assessment/comprehensive-run/{run_id}/report/json",
        headers={"Accept": "application/json", "Cache-Control": "no-store"},
        timeout=120_000,
    )
    assert report.ok, f"Canonical report JSON returned HTTP {report.status}"
    canonical = report.json()
    assert isinstance(canonical, dict)
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), dict) else {}
    lifecycle = canonical.get("lifecycle") if isinstance(canonical.get("lifecycle"), dict) else {}
    assert str(identity.get("run_id") or "") == run_id
    assert str(identity.get("commit_sha") or "") == expected_sha
    computed_digest = require_canonical_json_digest(
        canonical,
        report.headers.get("x-nico-canonical-truth-sha256"),
    )
    digest = require_matching_canonical_truth_digest(
        expected_digest,
        reports.get("canonical_truth_sha256"),
        computed_digest,
    )
    return {
        "canonical_truth_sha256": digest,
        "canonical_run_id": run_id,
        "canonical_commit_sha": expected_sha,
        "canonical_truth_digest_computed_from_json": True,
        "lifecycle_status": str(payload.get("status") or ""),
        "current_stage": str(payload.get("current_stage") or ""),
        "revision": payload.get("revision"),
        "integrity_sha256": str(payload.get("integrity_sha256") or ""),
        "human_review_required": payload.get("human_review_required"),
        "client_delivery_allowed": payload.get("client_delivery_allowed"),
        "human_review_status": str(
            canonical.get("human_review_status")
            or lifecycle.get("human_review_status")
            or ""
        ),
        "approval_status": str(canonical.get("approval_status") or ""),
        "canonical_client_delivery_allowed": canonical.get(
            "client_delivery_allowed"
        ),
    }


def _mobile_locale_surface(page: Any, locale: str, run_id: str) -> dict[str, Any]:
    spanish = locale == "es-MX"
    expected_path = "/es/assessment" if spanish else "/assessment"
    value = dict(
        page.evaluate(
            """() => ({
              pathname: window.location.pathname,
              document_language: String(document.documentElement.lang || ''),
              workspace_locale: String(document.querySelector('main[data-workspace="assessment"]')?.getAttribute('data-assessment-locale') || ''),
            })"""
        )
        or {}
    )
    assert str(value.get("pathname") or "").startswith(expected_path), value
    assert str(value.get("document_language") or "").lower().startswith(
        "es" if spanish else "en"
    ), value
    assert str(value.get("workspace_locale") or "") == (
        "es-MX" if spanish else "en"
    ), value
    query = parse_qs(urlparse(str(page.url)).query)
    assert query.get("run_id") == [run_id], query
    assert "report_language" not in query, query
    body = page.locator(WORKSPACE_SELECTOR).first.inner_text()
    expected_authored = "Identidad técnica" if spanish else "Technical identity"
    assert expected_authored in body
    if spanish:
        for leaked in (
            "Start new assessment",
            "Internal review required",
            "Technical identity",
        ):
            assert leaked not in body, {"english_leak": leaked}
    return {
        **value,
        "ui_locale": locale,
        "run_id": run_id,
        "authored_copy_localized": True,
    }


def _mobile_review_locale_surface(
    page: Any,
    locale: str,
    run_id: str,
) -> dict[str, Any]:
    spanish = locale == "es-MX"
    query = parse_qs(urlparse(str(page.url)).query)
    assert query.get("run_id") == [run_id], query
    if spanish:
        assert query.get("lang") == ["es-MX"], query
    document_language = str(
        page.evaluate("() => document.documentElement.lang || ''")
    )
    assert document_language.lower().startswith("es" if spanish else "en")
    workspace = page.locator("main[data-review-contract='accepted-edition-v2']")
    workspace.wait_for(state="visible", timeout=120_000)
    expected_heading = (
        "Revisión final interna y autorización para el cliente."
        if spanish
        else "Internal final review and client-ready authorization."
    )
    heading = workspace.locator("h1").inner_text().strip()
    assert heading == expected_heading
    return {
        "ui_locale": locale,
        "document_language": document_language,
        "heading": heading,
        "run_id_preserved": True,
        "requested_locale_preserved": True,
    }


def _mobile_locale_round_trip(
    page: Any,
    *,
    source_locale: str,
    run_id: str,
    expected_sha: str,
    timeout_ms: int,
) -> dict[str, Any]:
    target_locale = "en" if source_locale == "es-MX" else "es-MX"
    source_surface = _mobile_locale_surface(page, source_locale, run_id)
    switcher = page.locator(
        'a.language-switcher[data-preserves-assessment-state="true"]'
    ).first
    switcher.wait_for(state="visible", timeout=timeout_ms)
    switcher.click()
    page.locator(WORKSPACE_SELECTOR).first.wait_for(state="visible", timeout=timeout_ms)
    target_terminal = _wait_for_terminal_ui_ready(
        page,
        run_id,
        expected_sha,
        120.0,
    )
    target_surface = _mobile_locale_surface(page, target_locale, run_id)

    return_switcher = page.locator(
        'a.language-switcher[data-preserves-assessment-state="true"]'
    ).first
    return_switcher.wait_for(state="visible", timeout=timeout_ms)
    return_switcher.click()
    page.locator(WORKSPACE_SELECTOR).first.wait_for(state="visible", timeout=timeout_ms)
    source_terminal_after = _wait_for_terminal_ui_ready(
        page,
        run_id,
        expected_sha,
        120.0,
    )
    source_surface_after = _mobile_locale_surface(page, source_locale, run_id)
    return {
        "source_locale": source_locale,
        "target_locale": target_locale,
        "source_surface": source_surface,
        "target_surface": target_surface,
        "source_surface_after_round_trip": source_surface_after,
        "target_terminal_run_id": target_terminal.get("run_id"),
        "source_terminal_run_id_after_round_trip": source_terminal_after.get("run_id"),
        "locale_control_used_twice": True,
        "same_run_preserved": True,
        "same_commit_preserved": True,
        "authored_copy_localized": True,
    }


def _mobile_terminal_layout(page: Any) -> dict[str, Any]:
    metrics = dict(
        page.evaluate(
            f"""() => {{
              const state = document.querySelector('[data-assessment-run-state="true"]');
              const runHeader = state?.querySelector(':scope > .section-head');
              const runStatus = runHeader?.querySelector(':scope > .status');
              const runHeading = state?.querySelector(':scope > .section-head h2');
              const runHeaderRect = runHeader?.getBoundingClientRect();
              const runHeaderStyle = runHeader ? getComputedStyle(runHeader) : null;
              const runStatusRect = runStatus?.getBoundingClientRect();
              const runHeadingParent = runHeading?.parentElement;
              const runHeadingRect = runHeading?.getBoundingClientRect();
              const runHeadingParentRect = runHeadingParent?.getBoundingClientRect();
              const viewportWidth = document.documentElement.clientWidth;
              const visibleBodyElements = Array.from(document.body.querySelectorAll('*'))
                .map((node) => {{
                  const rect = node.getBoundingClientRect();
                  const style = getComputedStyle(node);
                  return {{node, rect, style}};
                }})
                .filter((item) => (
                  item.style.display !== 'none'
                  && item.style.visibility !== 'hidden'
                  && item.rect.width > 0
                  && item.rect.height > 0
                ));
              const overflowIdentity = (item) => ({{
                tag: String(item.node.tagName || '').toLowerCase(),
                id: String(item.node.id || '').slice(0, 120),
                class_name: String(item.node.className || '').slice(0, 180),
                data_keys: Array.from(item.node.attributes || [])
                  .map((attribute) => String(attribute.name || ''))
                  .filter((name) => name.startsWith('data-'))
                  .slice(0, 8),
                left: item.rect.left,
                right: item.rect.right,
                width: item.rect.width,
                scroll_width: item.node.scrollWidth || 0,
                client_width: item.node.clientWidth || 0,
                overflow_x: item.style.overflowX,
                position: item.style.position,
                white_space: item.style.whiteSpace,
              }});
              const viewportOverflowingElements = visibleBodyElements
                .filter((item) => item.rect.left < -1 || item.rect.right > viewportWidth + 1)
                .sort((left, right) => (
                  Math.max(-right.rect.left, right.rect.right - viewportWidth)
                  - Math.max(-left.rect.left, left.rect.right - viewportWidth)
                ))
                .slice(0, 20)
                .map(overflowIdentity);
              const intrinsicOverflowElements = visibleBodyElements
                .filter((item) => item.node.scrollWidth > item.node.clientWidth + 1)
                .sort((left, right) => (
                  (right.node.scrollWidth - right.node.clientWidth)
                  - (left.node.scrollWidth - left.node.clientWidth)
                ))
                .slice(0, 20)
                .map(overflowIdentity);
              const targets = Array.from(document.querySelectorAll(
                '{REPORT_ACTIONS_SELECTOR} button, [data-assessment-internal-review="true"]'
              )).map((node) => {{
                const rect = node.getBoundingClientRect();
                const style = getComputedStyle(node);
                return {{
                  label: String(node.textContent || '').trim(),
                  width: rect.width,
                  height: rect.height,
                  left: rect.left,
                  right: rect.right,
                  display: style.display,
                  visibility: style.visibility,
                  pointer_events: style.pointerEvents,
                }};
              }});
              return {{
                viewport_width: document.documentElement.clientWidth,
                document_scroll_width: document.documentElement.scrollWidth,
                body_scroll_width: document.body.scrollWidth,
                viewport_overflowing_elements: viewportOverflowingElements,
                intrinsic_overflow_elements: intrinsicOverflowElements,
                run_header: {{
                  left: runHeaderRect?.left ?? -1,
                  right: runHeaderRect?.right ?? -1,
                  width: runHeaderRect?.width ?? 0,
                  flex_direction: runHeaderStyle?.flexDirection ?? '',
                  status_left: runStatusRect?.left ?? -1,
                  status_right: runStatusRect?.right ?? -1,
                  status_width: runStatusRect?.width ?? 0,
                }},
                run_heading: {{
                  text: String(runHeading?.textContent || '').trim(),
                  left: runHeadingRect?.left ?? -1,
                  right: runHeadingRect?.right ?? -1,
                  width: runHeadingRect?.width ?? 0,
                  scroll_width: runHeading?.scrollWidth ?? 0,
                  client_width: runHeading?.clientWidth ?? 0,
                  parent_left: runHeadingParentRect?.left ?? -1,
                  parent_right: runHeadingParentRect?.right ?? -1,
                  parent_client_width: runHeadingParent?.clientWidth ?? 0,
                }},
                targets,
              }};
            }}"""
        )
        or {{}}
    )
    viewport_width = float(metrics.get("viewport_width") or 0)
    assert viewport_width > 0, metrics
    assert float(metrics.get("document_scroll_width") or 0) <= viewport_width + 1, metrics
    assert float(metrics.get("body_scroll_width") or 0) <= viewport_width + 1, metrics
    assert not list(metrics.get("viewport_overflowing_elements") or []), metrics
    header = dict(metrics.get("run_header") or {})
    assert header.get("flex_direction") == "column", metrics
    assert float(header.get("left", -1)) >= 0, metrics
    assert float(header.get("right", viewport_width + 1)) <= viewport_width + 1, metrics
    assert float(header.get("width") or 0) > 0, metrics
    assert float(header.get("status_left", -1)) >= 0, metrics
    assert float(header.get("status_right", viewport_width + 1)) <= viewport_width + 1, metrics
    assert float(header.get("status_width") or 0) <= float(header.get("width") or 0) + 1, metrics
    heading = dict(metrics.get("run_heading") or {})
    assert str(heading.get("text") or "").strip(), metrics
    assert float(heading.get("parent_client_width") or 0) > 0, metrics
    assert float(heading.get("left", -1)) >= 0, metrics
    assert float(heading.get("right", viewport_width + 1)) <= viewport_width + 1, metrics
    assert float(heading.get("parent_left", -1)) >= 0, metrics
    assert float(heading.get("parent_right", viewport_width + 1)) <= viewport_width + 1, metrics
    assert float(heading.get("scroll_width") or 0) <= float(
        heading.get("parent_client_width") or 0
    ) + 1, metrics
    targets = list(metrics.get("targets") or [])
    assert len(targets) >= 3, metrics
    for target in targets:
        assert float(target.get("width") or 0) >= 44, target
        assert float(target.get("height") or 0) >= 44, target
        assert float(target.get("left", -1)) >= 0, target
        assert float(target.get("right", viewport_width + 1)) <= viewport_width + 1, target
        assert target.get("display") != "none", target
        assert target.get("visibility") != "hidden", target
        assert target.get("pointer_events") != "none", target
    return {
        **metrics,
        "horizontal_overflow_absent": True,
        "minimum_touch_target_px": 44,
        "terminal_actions_reachable": True,
    }


def _active_report_language(page: Any) -> str:
    language = str(
        page.evaluate(
            f"""() => {{
              const actions = document.querySelector('{REPORT_ACTIONS_SELECTOR}');
              return String(actions?.getAttribute('data-requested-report-language') || '');
            }}"""
        )
    ).strip()
    assert language in {"en", "es-MX"}, {
        "unsupported_requested_report_language": language,
    }
    return language


def _click_markdown_and_verify(
    page: Any,
    run_id: str,
    *,
    expected_sha: str,
    expected_canonical_digest: str,
) -> dict[str, Any]:
    actions = page.locator(REPORT_ACTIONS_SELECTOR).first
    markdown = actions.get_by_role("button", name=re.compile("markdown", re.I)).first
    report_language = _active_report_language(page)
    markdown_kind = str(
        markdown.get_attribute("data-assessment-markdown-kind") or ""
    ).strip()
    button_language = str(markdown.get_attribute("data-report-language") or "").strip()
    assert markdown_kind in {
        "accepted-source-rendering",
        "localized-draft-pending-approval",
    }, {"markdown_action_kind": markdown_kind}
    assert button_language == report_language
    markdown_path = (
        f"/api/nico/assessment/comprehensive-run/{run_id}/"
        f"localized-report/{report_language}"
    )
    origin = urlparse(str(page.url))
    response = page.request.get(
        f"{origin.scheme}://{origin.netloc}{markdown_path}",
        headers={"Accept": "application/json", "Cache-Control": "no-store"},
        timeout=120_000,
    )
    body = response.body()
    assert response.ok, f"Markdown action returned HTTP {response.status}"
    assert body.strip(), "Localized Markdown route returned an empty response"
    payload = response.json()
    report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
    localized_lifecycle = (
        payload.get("localized_artifact_lifecycle")
        if isinstance(payload.get("localized_artifact_lifecycle"), dict)
        else {}
    )
    rendered_markdown = str(report.get("markdown") or "")
    assert payload.get("run_id") == run_id
    assert payload.get("commit_sha") == expected_sha
    assert payload.get("report_language") == report_language
    assert payload.get("assessment_rerun") is False
    assert rendered_markdown.strip(), "Localized Markdown payload was empty"
    canonical_digest = require_matching_canonical_truth_digest(
        expected_canonical_digest,
        payload.get("canonical_truth_sha256"),
        report.get("canonical_truth_sha256"),
    )
    if markdown_kind == "accepted-source-rendering":
        assert payload.get("source_report_language") == report_language
        assert payload.get("localized_artifact_requires_new_approval") is False
    else:
        assert localized_lifecycle.get("client_delivery_allowed") is False
        assert report.get("client_delivery_allowed") is False

    markdown.click()
    gesture_count = 1
    deadline = time.monotonic() + 30.0
    last = ""
    while time.monotonic() < deadline:
        last = actions.inner_text()
        if (
            ("Markdown copied" in last or "Markdown copiado" in last)
            and markdown.is_enabled()
        ):
            break
        ready_to_copy = (
            "Markdown ready. Click Copy Markdown." in last
            or "Markdown listo. Pulsa Copiar Markdown." in last
        )
        if ready_to_copy and gesture_count == 1:
            page.wait_for_timeout(1_250)
            markdown.click()
            gesture_count += 1
        page.wait_for_timeout(100)
    else:
        raise AssertionError(f"Markdown action did not report success: {last}")
    return {
        "http_status": response.status,
        "size_bytes": len(body),
        "markdown_size_bytes": len(rendered_markdown.encode("utf-8")),
        "report_language": report_language,
        "markdown_action_kind": markdown_kind,
        "markdown_route": markdown_path,
        "canonical_truth_sha256": canonical_digest,
        "assessment_rerun_verified_false": True,
        "run_identity_verified": True,
        "commit_identity_verified": True,
        "locale_identity_verified": True,
        "lifecycle_contract_verified": True,
        "verification_get_count": 1,
        "user_gesture_count": gesture_count,
        "localized_success": "Markdown copiado" if "Markdown copiado" in last else "Markdown copied",
        "action_reenabled": True,
    }


def _observe_terminal_stability(
    page: Any,
    *,
    run_id: str,
    expected_sha: str,
    expected_canonical_digest: str,
    seconds: float,
    requests: list[dict[str, Any]],
) -> dict[str, Any]:
    if seconds < 90.0:
        raise ValueError("terminal_observation_must_be_at_least_90_seconds")
    started = time.monotonic()
    baseline_index = len(requests)
    stable_url = str(page.url)
    report_language = _active_report_language(page)
    markdown_proofs = [
        _click_markdown_and_verify(
            page,
            run_id,
            expected_sha=expected_sha,
            expected_canonical_digest=expected_canonical_digest,
        )
    ]
    samples: list[dict[str, Any]] = []
    deadline = started + seconds
    while time.monotonic() < deadline:
        state = _ui_state(page)
        assert _terminal_ui_ready(state, run_id, expected_sha), state
        assert str(page.url) == stable_url, {
            "expected_terminal_url": stable_url,
            "observed_terminal_url": str(page.url),
        }
        assert _blocking_overlay_count(page) == 0
        assert page.evaluate("() => getComputedStyle(document.body).pointerEvents") != "none"
        review = page.locator('[data-assessment-internal-review="true"]').first
        assert review.is_visible(), "Professional review action was not visible"
        assert run_id in str(review.get_attribute("href") or "")
        scroll = page.evaluate(
            """() => {
              window.scrollTo(0, document.documentElement.scrollHeight);
              const bottom = window.scrollY;
              window.scrollTo(0, 0);
              return {
                bottom,
                top: window.scrollY,
                scroll_height: document.documentElement.scrollHeight,
                viewport_height: window.innerHeight,
              };
            }"""
        )
        assert float(scroll.get("scroll_height") or 0) > float(
            scroll.get("viewport_height") or 0
        ), scroll
        assert float(scroll.get("bottom") or 0) > 0, scroll
        assert float(scroll.get("top", -1)) == 0, scroll
        samples.append(
            {
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "run_id": state.get("run_id"),
                "commit_sha": state.get("commit_sha"),
                "phase": state.get("phase"),
                "blocking_overlay_count": 0,
                "scroll": scroll,
                "request_count": len(requests) - baseline_index,
            }
        )
        remaining = deadline - time.monotonic()
        if remaining > 0:
            page.wait_for_timeout(int(min(5.0, remaining) * 1000))
    markdown_proofs.append(
        _click_markdown_and_verify(
            page,
            run_id,
            expected_sha=expected_sha,
            expected_canonical_digest=expected_canonical_digest,
        )
    )
    duration = time.monotonic() - started
    observed = requests[baseline_index:]
    status_path = f"/api/nico/assessment/comprehensive-run/{run_id}"
    markdown_path = status_path + f"/localized-report/{report_language}"
    legacy_markdown_path = status_path + "/report/markdown"
    posts = [item for item in observed if item.get("method") == "POST"]
    status_gets = [
        item
        for item in observed
        if item.get("method") == "GET" and item.get("path") == status_path
    ]
    markdown_gets = [
        item
        for item in observed
        if item.get("method") == "GET" and item.get("path") == markdown_path
    ]
    legacy_markdown_gets = [
        item
        for item in observed
        if item.get("method") == "GET" and item.get("path") == legacy_markdown_path
    ]
    unexpected = [
        item
        for item in observed
        if item.get("path", "").startswith("/api/nico/assessment/")
        and not (
            item.get("method") == "GET"
            and item.get("path") in {status_path, markdown_path}
        )
    ]
    buckets: dict[int, int] = {}
    for item in observed:
        bucket = int(max(0.0, float(item.get("monotonic") or started) - started) // 5)
        buckets[bucket] = buckets.get(bucket, 0) + 1
    assert duration >= seconds
    assert not posts, posts
    assert len(status_gets) <= 4, status_gets
    assert len(markdown_gets) <= 2, markdown_gets
    assert not legacy_markdown_gets, legacy_markdown_gets
    assert len(markdown_proofs) == 2
    assert not unexpected, unexpected
    assert max(buckets.values(), default=0) <= 4, buckets
    return {
        "required_seconds": seconds,
        "observed_seconds": round(duration, 2),
        "sample_count": len(samples),
        "status_get_count": len(status_gets),
        "markdown_get_count": len(markdown_gets),
        "localized_markdown_get_count": len(markdown_gets),
        "legacy_markdown_get_count": len(legacy_markdown_gets),
        "markdown_action_success_count": len(markdown_proofs),
        "markdown_verification_get_count": sum(
            int(item["verification_get_count"]) for item in markdown_proofs
        ),
        "markdown_report_language": report_language,
        "markdown_network_path": markdown_path,
        "post_request_count": len(posts),
        "unexpected_assessment_request_count": len(unexpected),
        "max_requests_per_five_seconds": max(buckets.values(), default=0),
        "terminal_polling_bounded": True,
        "network_activity_bounded": True,
        "markdown_network_bounded": True,
        "blocking_overlay_absent": True,
        "pointer_interaction_enabled": True,
        "scroll_responsive": True,
        "professional_review_action_reachable": True,
        "markdown_action_proofs": markdown_proofs,
        "samples": samples,
    }


def run_existing_proof(browser: Browser, args: argparse.Namespace) -> dict[str, Any]:
    source_marker = _require_existing_source_args(args)
    handoff = load_source_proof(
        args.source_proof,
        expected_sha=args.expected_sha,
        repository=args.repository,
        source_workflow_run_id=args.source_workflow_run_id,
        source_workflow_run_attempt=args.source_workflow_run_attempt,
        expected_proof_tool_sha=args.expected_proof_tool_sha,
    )
    run_id = str(handoff["run_id"])
    origin = args.frontend_url.rstrip("/")
    requests: list[dict[str, Any]] = []
    prohibited_attempts: list[dict[str, Any]] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    crashes: list[str] = []
    open_contexts: list[Any] = []

    def record_request(request: Any) -> None:
        parsed = urlparse(request.url)
        if parsed.path.startswith("/api/nico/assessment/"):
            requests.append(
                {
                    "method": str(request.method).upper(),
                    "path": parsed.path,
                    "resource_type": str(getattr(request, "resource_type", "")),
                    "monotonic": time.monotonic(),
                }
            )

    def mutation_guard(route: Any, request: Any) -> None:
        parsed = urlparse(request.url)
        prohibited = request.method == "POST" and (
            parsed.path == "/api/nico/assessment/comprehensive-intake"
            or (
                parsed.path.startswith("/api/nico/assessment/comprehensive-run/")
                and parsed.path.endswith("/continue")
            )
        )
        if prohibited:
            prohibited_attempts.append(
                {
                    "method": str(request.method).upper(),
                    "path": parsed.path,
                    "monotonic": time.monotonic(),
                }
            )
            route.abort("blockedbyclient")
            return
        route.continue_()

    def new_surface(label: str) -> tuple[Any, Any]:
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            locale="es-MX" if args.ui_locale == "es-MX" else "en-US",
            service_workers="block",
            extra_http_headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )
        _grant_supported_clipboard_permissions(context, origin=origin)
        page = context.new_page()
        page.on("request", record_request)
        page.on(
            "console",
            lambda message: console_errors.append(f"{label}: {message.text}")
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: page_errors.append(f"{label}: {error}"))
        page.on("crash", lambda: crashes.append(f"{label}: page_crashed"))
        page.route("**/*", mutation_guard)
        open_contexts.append(context)
        return context, page

    def exact_url(probe: str) -> str:
        assessment_path = "/es/assessment" if args.ui_locale == "es-MX" else "/assessment"
        return (
            f"{origin}{assessment_path}?tier=comprehensive"
            f"&run_id={run_id}&expected_commit_sha={args.expected_sha}"
            f"&{probe}={time.time_ns()}#assessment"
        )

    started_at = time.time()
    first_context: Any | None = None
    second_context: Any | None = None
    try:
        first_context, first_page = new_surface("initial_context")
        first_context_identity = id(getattr(first_context, "_context", first_context))
        first_page.goto(
            exact_url("existing_run_probe"),
            wait_until="domcontentloaded",
            timeout=args.navigation_timeout_ms,
        )
        first_page.locator(WORKSPACE_SELECTOR).first.wait_for(
            state="visible", timeout=args.navigation_timeout_ms
        )
        initial = _wait_for_same_run_ui(first_page, run_id, 120.0)
        terminal_before_reload = _wait_for_terminal_ui_ready(
            first_page, run_id, args.expected_sha, 240.0
        )
        first_locale_surface = _mobile_locale_surface(
            first_page, args.ui_locale, run_id
        )
        terminal_reload = _reload_and_restore(
            first_page,
            run_id,
            args.navigation_timeout_ms,
            expect_active_storage=False,
        )
        terminal_after_reload = _wait_for_terminal_ui_ready(
            first_page, run_id, args.expected_sha, 120.0
        )
        initial_visibility = _prove_visibility_hidden_visible(
            first_page,
            first_context,
            timeout_ms=args.navigation_timeout_ms,
        )
        terminal_after_foreground = _wait_for_terminal_ui_ready(
            first_page, run_id, args.expected_sha, 120.0
        )

        first_context.close()
        open_contexts.remove(first_context)
        first_context = None

        second_context, page = new_surface("clean_reopen_context")
        second_context_identity = id(getattr(second_context, "_context", second_context))
        assert second_context_identity != first_context_identity
        page.goto(
            exact_url("clean_context_reopen_probe"),
            wait_until="domcontentloaded",
            timeout=args.navigation_timeout_ms,
        )
        page.locator(WORKSPACE_SELECTOR).first.wait_for(
            state="visible", timeout=args.navigation_timeout_ms
        )
        terminal_after_context_reopen = _wait_for_terminal_ui_ready(
            page, run_id, args.expected_sha, 240.0
        )
        reopened_locale_surface = _mobile_locale_surface(
            page, args.ui_locale, run_id
        )
        reopened_storage = _stored_run(page)
        assert not reopened_storage.get("run_id"), reopened_storage
        assert reopened_storage.get("url_run_id") == run_id

        observation = _observe_terminal_stability(
            page,
            run_id=run_id,
            expected_sha=args.expected_sha,
            expected_canonical_digest=handoff["canonical_truth_sha256"],
            seconds=args.observation_seconds,
            requests=requests,
        )
        terminal_layout = _mobile_terminal_layout(page)
        terminal_visibility = _prove_visibility_hidden_visible(
            page,
            second_context,
            timeout_ms=args.navigation_timeout_ms,
        )
        terminal_after_second_foreground = _wait_for_terminal_ui_ready(
            page, run_id, args.expected_sha, 120.0
        )

        raw_page = getattr(page, "_page", page)
        raw_page.goto(
            f"{origin}/privacy",
            wait_until="domcontentloaded",
            timeout=args.navigation_timeout_ms,
        )
        raw_page.go_back(wait_until="domcontentloaded", timeout=args.navigation_timeout_ms)
        page.locator(WORKSPACE_SELECTOR).first.wait_for(
            state="visible", timeout=args.navigation_timeout_ms
        )
        terminal_after_navigation = _wait_for_terminal_ui_ready(
            page, run_id, args.expected_sha, 120.0
        )
        navigation_locale_surface = _mobile_locale_surface(
            page, args.ui_locale, run_id
        )
        locale_round_trip = _mobile_locale_round_trip(
            page,
            source_locale=args.ui_locale,
            run_id=run_id,
            expected_sha=args.expected_sha,
            timeout_ms=args.navigation_timeout_ms,
        )

        review_action = page.locator('[data-assessment-internal-review="true"]').first
        review_action.wait_for(state="visible", timeout=args.navigation_timeout_ms)
        review_href = str(review_action.get_attribute("href") or "")
        assert run_id in review_href and "final-review" in review_href, review_href
        review_action.click()
        page.wait_for_load_state("domcontentloaded", timeout=args.navigation_timeout_ms)
        mobile_review_surface = _mobile_review_locale_surface(
            page, args.ui_locale, run_id
        )
        page.go_back(wait_until="domcontentloaded", timeout=args.navigation_timeout_ms)
        page.locator(WORKSPACE_SELECTOR).first.wait_for(
            state="visible", timeout=args.navigation_timeout_ms
        )
        terminal_after_review_navigation = _wait_for_terminal_ui_ready(
            page, run_id, args.expected_sha, 120.0
        )
        after_review_locale_surface = _mobile_locale_surface(
            page, args.ui_locale, run_id
        )

        canonical_truth = _verify_canonical_truth(
            page,
            frontend_origin=origin,
            run_id=run_id,
            expected_sha=args.expected_sha,
            expected_digest=handoff["canonical_truth_sha256"],
        )
        artifacts = _verify_manifest_and_pdf(page, origin, run_id)
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
            screenshot_error = f"{type(exc).__name__}: {_bounded(exc, 320)}"

        assert not prohibited_attempts, {
            "prohibited_mutation_attempts": prohibited_attempts,
        }
        assert _start_count(requests) == 0
        assert _continuation_count(requests) == 0
        relevant_console = [
            value
            for value in console_errors
            if "favicon" not in value.casefold() and "404" not in value.casefold()
        ]
        assert not relevant_console, relevant_console
        assert not page_errors, page_errors
        assert not crashes, crashes
        return {
            "artifact_schema": VERSION,
            "status": "passed",
            "frontend_url": args.frontend_url.rstrip("/"),
            "repository": args.repository,
            "expected_sha": args.expected_sha,
            "run_id": run_id,
            "viewport": {"width": 390, "height": 844},
            "ui_locale": args.ui_locale,
            "assessment_path": (
                "/es/assessment" if args.ui_locale == "es-MX" else "/assessment"
            ),
            "browser_evidence_class": (
                "Playwright Chromium iPhone-sized mobile emulation"
            ),
            "safari_equivalent_evidence": "not tested by this Chromium consumer",
            "real_device_tested": False,
            "started_at_epoch": started_at,
            "finished_at_epoch": time.time(),
            "source_proof_sha256": handoff["source_proof_sha256"],
            "source_workflow_run_id": handoff["source_workflow_run_id"],
            "source_workflow_run_attempt": handoff["source_workflow_run_attempt"],
            "source_binding": source_marker.removeprefix("source:"),
            "canonical_truth_sha256": canonical_truth["canonical_truth_sha256"],
            "fresh_assessment_count": 0,
            "start_request_count": 0,
            "continuation_post_count": 0,
            "prohibited_mutation_attempt_count": 0,
            "prohibited_mutation_guard_verified": True,
            "start_dispatch": "not_dispatched_existing_run",
            "initial_restoration": initial,
            "terminal_before_reload": terminal_before_reload,
            "first_locale_surface": first_locale_surface,
            "terminal_reload": terminal_reload,
            "terminal_after_reload": terminal_after_reload,
            "initial_context_visibility": initial_visibility,
            "terminal_after_foreground": terminal_after_foreground,
            "terminal_after_context_reopen": terminal_after_context_reopen,
            "reopened_locale_surface": reopened_locale_surface,
            "reopened_storage": reopened_storage,
            "terminal_observation": observation,
            "terminal_mobile_layout": terminal_layout,
            "terminal_horizontal_overflow_absent": True,
            "terminal_touch_targets_verified": True,
            "terminal_visibility": terminal_visibility,
            "terminal_visibility_transitions": ["hidden", "visible"],
            "terminal_after_second_foreground": terminal_after_second_foreground,
            "terminal_after_navigation": terminal_after_navigation,
            "navigation_locale_surface": navigation_locale_surface,
            "mobile_locale_round_trip": locale_round_trip,
            "mobile_locale_switch_control_verified": True,
            "terminal_after_review_navigation": terminal_after_review_navigation,
            "after_review_locale_surface": after_review_locale_surface,
            "professional_review_href": review_href,
            "professional_review_locale_surface": mobile_review_surface,
            "professional_review_navigation_verified": True,
            "professional_review_locale_preserved": True,
            "browser_context_count": 2,
            "first_context_closed_before_reopen": True,
            "clean_context_reopen_verified": True,
            "terminal_observation_at_least_90_seconds": True,
            "terminal_restart_recovery_verified": True,
            "terminal_background_foreground_recovery_verified": True,
            "terminal_navigation_recovery_verified": True,
            "terminal_locale_preserved_across_recovery": True,
            "exact_run_identity_preserved": True,
            "report_actions_recovered": True,
            "canonical_truth": canonical_truth,
            "console_errors": relevant_console,
            "page_errors": page_errors,
            "page_crashes": crashes,
            **artifacts,
            "screenshot": screenshot_path.as_posix() if screenshot_path.exists() else "",
            "screenshot_sha256": hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
            if screenshot_path.exists()
            else "",
            "screenshot_error": screenshot_error,
        }
    finally:
        for context in list(open_contexts):
            context.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prove mobile assessment recovery across browser restarts.")
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=7_200.0)
    parser.add_argument("--navigation-timeout-ms", type=int, default=120_000)
    parser.add_argument("--source-proof", type=Path, required=True)
    parser.add_argument("--source-workflow-run-id", required=True)
    parser.add_argument("--source-workflow-run-attempt", required=True)
    parser.add_argument("--expected-proof-tool-sha", required=True)
    parser.add_argument("--observation-seconds", type=float, default=90.0)
    parser.add_argument("--ui-locale", choices=("en", "es-MX"), default="en")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _require_existing_source_args(args)
    failure: dict[str, Any] | None = None
    try:
        with sync_playwright() as playwright:
            browser = _launch_chromium(playwright)
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
