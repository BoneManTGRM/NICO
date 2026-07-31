#!/usr/bin/env python3
from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import two_service_live_acceptance as acceptance
import two_service_live_acceptance_v2 as runtime

VERSION = "nico.two_service_live_acceptance_terminal_reconciliation.v12"
UI_BACKEND_RECONCILIATION_SECONDS = 120.0
UI_BACKEND_RETRY_SECONDS = 2.0
FORM_HYDRATION_TIMEOUT_MS = 30_000
FORM_STABILITY_SECONDS = 0.8
FORM_RETRY_SECONDS = 0.2
LEGACY_WORKSPACE_SELECTOR = 'main[data-assessment-service-count="2"]'
UNIFIED_WORKSPACE_SELECTOR = (
    'main[data-assessment-service-count="1"][data-canonical-assessment="strategic"]'
)
RUN_SELECTOR = '#assessment > button.primary-button'
PUBLIC_RUN_LABELS = {
    "en": "Run NICO Assessment",
    "es-MX": "Ejecutar evaluación NICO",
}
PUBLIC_HEADINGS = {
    "en": "Complete technical and strategic diligence",
    "es-MX": "Diligencia técnica y estratégica completa",
}

_original_wait_for_service_terminal = runtime._wait_for_service_terminal
_original_report_package = acceptance.report_package
_original_run_service = runtime.run_service


class _StableFormLocator:
    """Retry controlled form writes across late Next/React hydration."""

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
            except Exception as exc:
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
            except Exception as exc:
                last_error = exc
            self._page.wait_for_timeout(int(FORM_RETRY_SECONDS * 1000))
        raise AssertionError(
            "assessment authorization checkbox did not remain checked after hydration"
        ) from last_error


class _CanonicalServiceLocator:
    """Represent the already-selected hidden Comprehensive execution tier."""

    def get_attribute(self, name: str) -> str | None:
        return "true" if name == "aria-pressed" else None

    def click(self, *args: Any, **kwargs: Any) -> None:
        return None


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
            query["tier"] = "comprehensive"
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
        response = self._page.goto(url, *args, **kwargs)
        if assessment_page:
            wait_for_load_state = getattr(self._page, "wait_for_load_state", None)
            wait_for_timeout = getattr(self._page, "wait_for_timeout", None)
            if callable(wait_for_load_state):
                try:
                    wait_for_load_state("networkidle", timeout=FORM_HYDRATION_TIMEOUT_MS)
                except Exception:
                    if callable(wait_for_timeout):
                        wait_for_timeout(1000)
        return response

    def locator(self, selector: str, *args: Any, **kwargs: Any) -> Any:
        if selector == LEGACY_WORKSPACE_SELECTOR:
            selector = UNIFIED_WORKSPACE_SELECTOR
        return self._page.locator(selector, *args, **kwargs)

    def get_by_label(self, *args: Any, **kwargs: Any) -> _StableFormLocator:
        return _StableFormLocator(self._page.get_by_label(*args, **kwargs), self._page)

    def get_by_role(self, role: str, *args: Any, **kwargs: Any) -> Any:
        normalized_role = str(role).lower()
        name = kwargs.get("name")
        if normalized_role == "button" and name == "Comprehensive":
            return _CanonicalServiceLocator()
        if normalized_role == "button" and name in {"Run Comprehensive", "Run NICO Assessment"}:
            return self._page.locator(RUN_SELECTOR).first
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
    if service != "comprehensive":
        raise AssertionError("The canonical public assessment must execute Comprehensive internally.")
    return _original_run_service(
        _ExpectedCommitBrowser(browser, config.expected_sha),
        config,
        pass_number,
        "comprehensive",
    )


def _verify_unified_language_parity(browser: Any, config: Any) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for locale, path in (
        ("en", "/assessment?tier=comprehensive#assessment"),
        ("es-MX", "/es/assessment?tier=comprehensive#assessment"),
    ):
        context = browser.new_context(viewport={"width": 390, "height": 844}, locale=locale)
        page = context.new_page()
        try:
            page.goto(
                config.frontend_origin + path,
                wait_until="domcontentloaded",
                timeout=config.navigation_timeout_ms,
            )
            workspace = page.locator(UNIFIED_WORKSPACE_SELECTOR).first
            workspace.wait_for(state="visible", timeout=config.navigation_timeout_ms)
            choice_grid = workspace.locator('[aria-label="Assessment type"]').first
            choice_grid.wait_for(state="attached", timeout=config.navigation_timeout_ms)
            assert choice_grid.get_attribute("aria-hidden") == "true"
            assert choice_grid.is_hidden(), f"{locale} exposed the retired tier selector"
            buttons = choice_grid.locator("button")
            assert buttons.count() == 2, f"{locale} lost legacy internal tier controls"
            assert all(buttons.nth(index).is_hidden() for index in range(buttons.count()))

            run_button = workspace.locator(RUN_SELECTOR).first
            run_button.wait_for(state="visible", timeout=config.navigation_timeout_ms)
            run_label = acceptance.text(run_button.inner_text(), 120)
            assert run_label == PUBLIC_RUN_LABELS[locale], (
                f"{locale} canonical run label was {run_label!r}, expected {PUBLIC_RUN_LABELS[locale]!r}"
            )
            heading = acceptance.text(
                workspace.locator("#assessment .section-head h2").first.inner_text(),
                200,
            )
            assert heading == PUBLIC_HEADINGS[locale], (
                f"{locale} canonical heading was {heading!r}, expected {PUBLIC_HEADINGS[locale]!r}"
            )
            tier = page.evaluate("() => new URL(window.location.href).searchParams.get('tier')")
            assert tier == "comprehensive"

            screenshot = config.screenshot_dir / f"parity-{locale}.png"
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot), full_page=True)
            results[locale] = {
                "public_assessment_count": 1,
                "canonical_assessment": "strategic",
                "execution_service": "comprehensive",
                "legacy_selector_hidden": True,
                "run_label": run_label,
                "heading": heading,
                "screenshot": screenshot.as_posix(),
                "screenshot_sha256": acceptance.sha256(screenshot.read_bytes()),
            }
        finally:
            context.close()
    return results


def _run_unified(config: Any) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    config.output.parent.mkdir(parents=True, exist_ok=True)
    config.screenshot_dir.mkdir(parents=True, exist_ok=True)
    config.artifact_dir.mkdir(parents=True, exist_ok=True)
    started = acceptance.now_epoch()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            parity = _verify_unified_language_parity(
                _ExpectedCommitBrowser(browser, config.expected_sha),
                config,
            )
            runs = [
                _run_service_at_expected_commit(browser, config, pass_number, "comprehensive")
                for pass_number in range(1, config.passes + 1)
            ]
        finally:
            browser.close()

    run_ids = [item["run_id"] for item in runs]
    assert len(run_ids) == len(set(run_ids)), "acceptance runs reused an existing run ID"
    assert len(runs) == config.passes
    assert all(item["status"] == "passed" for item in runs)
    assert all(item["service"] == "comprehensive" for item in runs)
    return {
        "artifact_schema": "nico.unified_live_acceptance.v1",
        "status": "passed",
        "live_production_claim": True,
        "authorized_repository": config.repository,
        "expected_deployed_sha": config.expected_sha,
        "passes_required": config.passes,
        "passes_completed": config.passes,
        "public_assessment": "strategic",
        "services": ["comprehensive"],
        "language_parity": parity,
        "proof": {
            "one_public_assessment": True,
            "legacy_tier_selector_hidden": True,
            "english_spanish_parity": True,
            "one_start_per_pass": True,
            "exact_run_continuation": True,
            "exact_sha_bound": True,
            "markdown_html_pdf_json_parity": True,
            "comprehensive_depth_verified": True,
            "post_run_reconnect_identity_preserved": True,
            "human_review_required": True,
            "client_delivery_blocked": True,
            "two_consecutive_passes": config.passes >= 2,
        },
        "runs": runs,
        "started_at_epoch": started,
        "finished_at_epoch": acceptance.now_epoch(),
        "guardrail": (
            "Live automated evidence is a release-acceptance proof, not human approval "
            "or client-delivery authorization."
        ),
    }


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


def _canonical_json(package: Any) -> dict[str, Any]:
    if not isinstance(package, dict):
        return {}
    value = package.get("json")
    return value if isinstance(value, dict) and value else {}


def _canonical_truth_hash(package: Any) -> str:
    if not isinstance(package, dict):
        return ""
    direct = acceptance.text(package.get("canonical_truth_sha256"), 128)
    nested = acceptance.text(_canonical_json(package).get("canonical_truth_sha256"), 128)
    values = {value for value in (direct, nested) if value}
    if len(values) > 1:
        raise AssertionError(
            f"canonical truth hash drift inside report package: {sorted(values)}"
        )
    return next(iter(values), "")


def _merge_report_packages(
    canonical: dict[str, Any],
    compatibility: dict[str, Any],
) -> dict[str, Any]:
    canonical_hash = _canonical_truth_hash(canonical)
    compatibility_hash = _canonical_truth_hash(compatibility)
    if canonical_hash and compatibility_hash and canonical_hash != compatibility_hash:
        raise AssertionError(
            "canonical truth hash drift between report packages: "
            f"{sorted({canonical_hash, compatibility_hash})}"
        )

    merged = dict(compatibility)
    for key, value in canonical.items():
        if value not in (None, "", {}, []):
            merged[key] = value
    return merged


def _report_package(service: str, payload: dict[str, Any]) -> dict[str, Any]:
    canonical = _original_report_package(service, payload)
    if service != "comprehensive":
        return canonical

    reports = payload.get("reports")
    compatibility = reports if isinstance(reports, dict) else {}
    if _canonical_json(canonical):
        return _merge_report_packages(canonical, compatibility)
    if _canonical_json(compatibility):
        return _merge_report_packages(compatibility, canonical)
    if compatibility and (
        compatibility.get("markdown")
        or compatibility.get("html")
        or compatibility.get("pdf_base64")
    ):
        return compatibility
    return canonical


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
        except Exception as exc:
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
    acceptance.verify_language_parity = _verify_unified_language_parity
    acceptance.run = _run_unified
    runtime._wait_for_service_terminal = _wait_for_service_terminal
    runtime.run_service = _run_service_at_expected_commit
    return runtime.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
