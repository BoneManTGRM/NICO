#!/usr/bin/env python3
from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import two_service_live_acceptance as acceptance
import two_service_live_acceptance_v2 as runtime

VERSION = "nico.two_service_live_acceptance_terminal_reconciliation.v7"
UI_BACKEND_RECONCILIATION_SECONDS = 120.0
UI_BACKEND_RETRY_SECONDS = 2.0

_original_wait_for_service_terminal = runtime._wait_for_service_terminal
_original_report_package = acceptance.report_package
_original_run_service = runtime.run_service


class _ExpectedCommitPage:
    def __init__(self, page: Any, expected_sha: str) -> None:
        self._page = page
        self._expected_sha = expected_sha

    def __getattr__(self, name: str) -> Any:
        return getattr(self._page, name)

    def goto(self, url: str, *args: Any, **kwargs: Any) -> Any:
        parts = urlsplit(url)
        if parts.path.endswith("/assessment"):
            query = dict(parse_qsl(parts.query, keep_blank_values=True))
            query["expected_commit_sha"] = self._expected_sha
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
        return self._page.goto(url, *args, **kwargs)


class _ExpectedCommitContext:
    def __init__(self, context: Any, expected_sha: str) -> None:
        self._context = context
        self._expected_sha = expected_sha

    def __getattr__(self, name: str) -> Any:
        return getattr(self._context, name)

    def new_page(self) -> _ExpectedCommitPage:
        return _ExpectedCommitPage(self._context.new_page(), self._expected_sha)


class _ExpectedCommitBrowser:
    def __init__(self, browser: Any, expected_sha: str) -> None:
        self._browser = browser
        self._expected_sha = expected_sha

    def __getattr__(self, name: str) -> Any:
        return getattr(self._browser, name)

    def new_context(self, *args: Any, **kwargs: Any) -> _ExpectedCommitContext:
        return _ExpectedCommitContext(self._browser.new_context(*args, **kwargs), self._expected_sha)


def _run_service_at_expected_commit(
    browser: Any,
    config: Any,
    pass_number: int,
    service: str,
) -> dict[str, Any]:
    return _original_run_service(
        _ExpectedCommitBrowser(browser, config.expected_sha),
        config,
        pass_number,
        service,
    )


def _fallback_ui_state(page: Any) -> dict[str, str]:
    return {
        "phase_label": "unavailable",
        "message": "",
        "run_id": "",
        "commit_sha": "",
        "scanner": "",
        "report": "",
        "review": "",
        "score": "",
        "page_url": acceptance.text(getattr(page, "url", ""), 500),
    }


def _safe_ui_state(page: Any) -> dict[str, str]:
    """Read the live panel immediately without a locator auto-wait.

    The former ``locator.evaluate`` path could spend 30 seconds waiting for a live
    region that React had briefly unmounted, converting a transient UI condition into
    the acceptance failure while the same exact backend run was still advancing.
    """

    fallback = _fallback_ui_state(page)
    try:
        value = page.evaluate(
            """() => {
              const section = document.querySelector('section[aria-live="polite"]');
              if (!section) {
                return {
                  phase_label: 'unavailable', message: '', run_id: '', commit_sha: '',
                  scanner: '', report: '', review: '', score: '', page_url: window.location.href,
                };
              }
              const header = section.querySelector('.section-head');
              const phase = header?.querySelector('span')?.textContent?.trim() || '';
              const message = section.querySelector(':scope > p')?.textContent?.trim() || '';
              const articles = Array.from(section.querySelectorAll('article'));
              const find = label => articles.find(article => article.querySelector('b')?.textContent?.trim() === label)?.querySelector('span')?.textContent?.trim() || '';
              return {
                phase_label: phase,
                message,
                run_id: find('Run ID'),
                commit_sha: find('Immutable commit'),
                scanner: find('Scanner'),
                report: find('Report'),
                review: find('Human review'),
                score: find('Technical score'),
                page_url: window.location.href,
              };
            }"""
        )
    except Exception:
        return fallback
    if not isinstance(value, dict):
        return fallback
    return {key: acceptance.text(value.get(key, fallback[key]), 500) for key in fallback}


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
    acceptance.ui_state = _safe_ui_state
    acceptance.report_package = _report_package
    runtime._wait_for_service_terminal = _wait_for_service_terminal
    runtime.run_service = _run_service_at_expected_commit
    return runtime.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
