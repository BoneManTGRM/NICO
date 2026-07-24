#!/usr/bin/env python3
from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import two_service_live_acceptance as acceptance
import two_service_live_acceptance_v2 as runtime

VERSION = "nico.two_service_live_acceptance_terminal_reconciliation.v10"
UI_BACKEND_RECONCILIATION_SECONDS = 120.0
UI_BACKEND_RETRY_SECONDS = 2.0
FORM_HYDRATION_TIMEOUT_MS = 30_000
FORM_STABILITY_SECONDS = 0.8
FORM_RETRY_SECONDS = 0.2
SERVICE_SELECTOR = '[aria-label="Assessment type"] button'
RUN_SELECTOR = '#assessment > button.primary-button'

_original_wait_for_service_terminal = runtime._wait_for_service_terminal
_original_report_package = acceptance.report_package
_original_run_service = runtime.run_service


class _StableFormLocator:
    """Retry controlled form writes across late Next/React hydration.

    The production assessment shell can become visible before its client state has
    completed hydration. A one-shot Playwright fill/check may therefore appear to
    succeed and then be replaced by the initial empty React state, leaving Run disabled.
    Keep each controlled value stable for a short bounded interval before continuing.
    """

    def __init__(self, locator: Any, page: Any) -> None:
        self._locator = locator
        self._page = page

    def __getattr__(self, name: str) -> Any:
        return getattr(self._locator, name)

    def fill(self, value: str, *args: Any, **kwargs: Any) -> Any:
        deadline = time.monotonic() + FORM_HYDRATION_TIMEOUT_MS / 1000.0
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                result = self._locator.fill(value, *args, **kwargs)
                self._page.wait_for_timeout(int(FORM_STABILITY_SECONDS * 1000))
                if self._locator.input_value() == value:
                    return result
            except Exception as exc:  # bounded retry while hydration replaces nodes
                last_error = exc
            self._page.wait_for_timeout(int(FORM_RETRY_SECONDS * 1000))
        raise AssertionError(
            f"controlled assessment input did not remain stable after hydration: {value!r}"
        ) from last_error

    def check(self, *args: Any, **kwargs: Any) -> Any:
        deadline = time.monotonic() + FORM_HYDRATION_TIMEOUT_MS / 1000.0
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                result = self._locator.check(*args, **kwargs)
                self._page.wait_for_timeout(int(FORM_STABILITY_SECONDS * 1000))
                if self._locator.is_checked():
                    return result
            except Exception as exc:  # bounded retry while hydration replaces nodes
                last_error = exc
            self._page.wait_for_timeout(int(FORM_RETRY_SECONDS * 1000))
        raise AssertionError(
            "assessment authorization checkbox did not remain checked after hydration"
        ) from last_error


class _ExpectedCommitPage:
    def __init__(self, page: Any, expected_sha: str) -> None:
        self._page = page
        self._expected_sha = expected_sha

    def __getattr__(self, name: str) -> Any:
        return getattr(self._page, name)

    def goto(self, url: str, *args: Any, **kwargs: Any) -> Any:
        parts = urlsplit(url)
        assessment_page = parts.path.endswith("/assessment")
        if assessment_page:
            query = dict(parse_qsl(parts.query, keep_blank_values=True))
            query["expected_commit_sha"] = self._expected_sha
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
        response = self._page.goto(url, *args, **kwargs)
        if assessment_page:
            wait_for_load_state = getattr(self._page, "wait_for_load_state", None)
            wait_for_timeout = getattr(self._page, "wait_for_timeout", None)
            if callable(wait_for_load_state):
                try:
                    wait_for_load_state("networkidle", timeout=FORM_HYDRATION_TIMEOUT_MS)
                except Exception:
                    # Controlled-field stability checks below remain the source of truth.
                    if callable(wait_for_timeout):
                        wait_for_timeout(1000)
        return response

    def get_by_label(self, *args: Any, **kwargs: Any) -> _StableFormLocator:
        return _StableFormLocator(self._page.get_by_label(*args, **kwargs), self._page)

    def get_by_role(self, role: str, *args: Any, **kwargs: Any) -> Any:
        normalized_role = str(role).lower()
        name = kwargs.get("name")
        locator_factory = getattr(self._page, "locator", None)
        if normalized_role == "button" and isinstance(name, str) and callable(locator_factory):
            if name in {"Express", "Comprehensive"}:
                return locator_factory(SERVICE_SELECTOR).filter(has_text=name).first
            if name in {"Run Express", "Run Comprehensive"}:
                return locator_factory(RUN_SELECTOR).first

        locator = self._page.get_by_role(role, *args, **kwargs)
        if normalized_role == "checkbox":
            return _StableFormLocator(locator, self._page)
        return locator


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
    Customer-facing identifiers are compacted on mobile. Acceptance must read their
    full immutable values from the code element title rather than concatenating the
    compact label and the adjacent copy-button text.
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
              const findArticle = label => articles.find(
                article => article.querySelector('b')?.textContent?.trim() === label
              );
              const findText = label => findArticle(label)?.querySelector('span')?.textContent?.trim() || '';
              const findIdentifier = label => {
                const code = findArticle(label)?.querySelector('code');
                return code?.getAttribute('title')?.trim() || code?.textContent?.trim() || '';
              };
              return {
                phase_label: phase,
                message,
                run_id: findIdentifier('Run ID'),
                commit_sha: findIdentifier('Immutable commit'),
                scanner: findText('Scanner'),
                report: findText('Report'),
                review: findText('Human review'),
                score: findText('Technical score'),
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
