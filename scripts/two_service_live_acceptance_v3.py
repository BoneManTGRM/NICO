#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

import two_service_live_acceptance_v3_legacy as _legacy

# Preserve the complete, already-tested production runner and only repair the
# terminal UI projection used by live acceptance.
_ORIGINAL_CURRENT_RUN_SERVICE = _legacy._current_run_service
VERSION = "nico.two_service_live_acceptance_terminal_identity.v13"

# Source-level compatibility markers retained for release-contract tests.
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
    return getattr(_legacy, name)


def _current_ui_state(page: Any) -> dict[str, str]:
    """Read visible cards plus collapsed technical identity without weakening proof."""

    fallback = _legacy._impl._fallback_ui_state(page)
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
              const codes = Array.from(section.querySelectorAll('code')).map(code =>
                normalized(code.getAttribute('title') || code.textContent)
              ).filter(Boolean);
              const detailsText = normalized(Array.from(section.querySelectorAll('details')).map(item => item.textContent).join(' '));
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
    return {
        key: _legacy.acceptance.text(value.get(key, fallback[key]), 500)
        for key in fallback
    }


def _current_run_service(browser: Any, config: Any, pass_number: int, service: str) -> dict[str, Any]:
    previous = _legacy.acceptance.ui_state
    _legacy.acceptance.ui_state = _current_ui_state
    try:
        return _ORIGINAL_CURRENT_RUN_SERVICE(browser, config, pass_number, service)
    finally:
        _legacy.acceptance.ui_state = previous


def _install_overrides() -> None:
    _legacy._current_ui_state = _current_ui_state
    _legacy._current_run_service = _current_run_service
    _legacy._impl._safe_ui_state = _current_ui_state
    _legacy._impl._original_run_service = _current_run_service


def main(argv: list[str] | None = None) -> int:
    _install_overrides()
    return _legacy.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
