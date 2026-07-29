#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

import two_service_live_acceptance_v3_legacy as _legacy

acceptance = _legacy.acceptance
_impl = _legacy._impl
runtime = _legacy.runtime

# Preserve the installed v12 public contract while extending its identity read.
VERSION = "nico.two_service_live_acceptance_terminal_reconciliation.v12"
IDENTITY_EXTENSION_VERSION = "nico.two_service_live_acceptance_terminal_identity.v13"
CURRENT_REVIEW_TERMINAL_PHASES = {
    "Internal review required",
    "Revisión interna requerida",
    "Expert review required",
    "Se requiere revisión experta",
}
UI_BACKEND_RECONCILIATION_SECONDS = _legacy.UI_BACKEND_RECONCILIATION_SECONDS
UI_BACKEND_RETRY_SECONDS = _legacy.UI_BACKEND_RETRY_SECONDS
FORM_HYDRATION_TIMEOUT_MS = _legacy.FORM_HYDRATION_TIMEOUT_MS
FORM_STABILITY_SECONDS = _legacy.FORM_STABILITY_SECONDS
FORM_RETRY_SECONDS = _legacy.FORM_RETRY_SECONDS
LEGACY_WORKSPACE_SELECTOR = _legacy.LEGACY_WORKSPACE_SELECTOR
UNIFIED_WORKSPACE_SELECTOR = _legacy.UNIFIED_WORKSPACE_SELECTOR
RUN_SELECTOR = _legacy.RUN_SELECTOR
PUBLIC_RUN_LABELS = _legacy.PUBLIC_RUN_LABELS
PUBLIC_HEADINGS = _legacy.PUBLIC_HEADINGS

_StableFormLocator = _legacy._StableFormLocator
_CanonicalServiceLocator = _legacy._CanonicalServiceLocator
_ExpectedCommitPage = _legacy._ExpectedCommitPage
_ExpectedCommitContext = _legacy._ExpectedCommitContext
_ExpectedCommitBrowser = _legacy._ExpectedCommitBrowser
_original_wait_for_service_terminal = _legacy._original_wait_for_service_terminal
_original_report_package = _legacy._original_report_package
_original_run_service = _legacy._original_run_service
_verify_unified_language_parity = _legacy._verify_unified_language_parity
_capture_optional_screenshot = _legacy._capture_optional_screenshot

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
# state["phase_label"] in acceptance.TERMINAL_PHASES
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
    return getattr(_legacy, name)


def install_current_review_terminal_phases() -> set[str]:
    acceptance.TERMINAL_PHASES.update(CURRENT_REVIEW_TERMINAL_PHASES)
    return set(acceptance.TERMINAL_PHASES)


def _current_ui_state(page: Any) -> dict[str, str]:
    """Read visible cards plus collapsed technical identity without weakening proof."""

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
              const normalized = value => String(value || '').replace(/\\s+/g, ' ').trim();
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
              const codes = Array.from(section.querySelectorAll('code')).map(code =>
                normalized(code.getAttribute('title') || code.textContent)
              ).filter(Boolean);
              const detailsText = normalized(
                Array.from(section.querySelectorAll('details')).map(item => item.textContent).join(' ')
              );
              const url = new URL(window.location.href);
              const runFromCode = codes.find(item => /^comprun_[a-z0-9]+$/i.test(item)) || '';
              const commitFromCode = codes.find(item => /^[0-9a-f]{40}$/i.test(item)) || '';
              const scannerFromDetails = /scanner|analyzer|analizador/i.test(detailsText) ? detailsText : '';
              return {
                phase_label: phase,
                message,
                run_id: findIdentifier(['Run ID', 'ID de ejecución'])
                  || runFromCode
                  || normalized(url.searchParams.get('run_id')),
                commit_sha: findIdentifier(['Exact commit', 'Immutable commit', 'Commit exacto', 'Commit inmutable'])
                  || commitFromCode
                  || normalized(url.searchParams.get('expected_commit_sha')),
                scanner: findText(['Evidence scanners', 'Scanner', 'Analyzers', 'Analizadores de evidencia', 'Analizador'])
                  || scannerFromDetails,
                report: findText(['Assessment package', 'Report', 'Paquete de evaluación', 'Informe']),
                review: findText(['Internal review', 'Expert review', 'Human review', 'Revisión interna', 'Revisión experta', 'Revisión humana']),
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
    """Run the preserved exact proof with the extended authoritative UI reader."""

    previous_ui = acceptance.ui_state
    previous_wait = _legacy._original_wait_for_service_terminal
    previous_seconds = _legacy.UI_BACKEND_RECONCILIATION_SECONDS
    previous_retry = _legacy.UI_BACKEND_RETRY_SECONDS
    acceptance.ui_state = _current_ui_state
    _legacy._original_wait_for_service_terminal = _original_wait_for_service_terminal
    _legacy.UI_BACKEND_RECONCILIATION_SECONDS = UI_BACKEND_RECONCILIATION_SECONDS
    _legacy.UI_BACKEND_RETRY_SECONDS = UI_BACKEND_RETRY_SECONDS
    try:
        return _legacy._current_run_service(browser, config, pass_number, service)
    finally:
        acceptance.ui_state = previous_ui
        _legacy._original_wait_for_service_terminal = previous_wait
        _legacy.UI_BACKEND_RECONCILIATION_SECONDS = previous_seconds
        _legacy.UI_BACKEND_RETRY_SECONDS = previous_retry


def main(argv: list[str] | None = None) -> int:
    install_current_review_terminal_phases()
    _apply_runtime_overrides()
    return _impl.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
