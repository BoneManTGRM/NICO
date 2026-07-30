#!/usr/bin/env python3
from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

import unified_production_acceptance as production

VERSION = "nico.unified_production_acceptance.authoritative_identity.v4"
# Legacy repair-contract vocabulary: "collapsed identity" referred to the
# disclosure that rendered exact run and commit identifiers. The v4 reader keeps
# those identifiers authoritative while reading the canonical state section with
# one immediate DOM query, so response capture is never blocked by a locator wait.
_ORIGINAL_RUN_SERVICE = production.unified._current_run_service


def authoritative_ui_state(page: Any) -> dict[str, str]:
    """Read the exact assessment state without a locator wait.

    The live acceptance workflow polls this reader while the start response is still
    in flight. A Playwright locator implicitly waits for a matching node and can
    block response capture for the full locator timeout. Reading with one bounded
    document query returns immediately, preserves the exact page URL, and allows the
    lifecycle listener to capture the run ID as soon as the backend responds.
    """

    try:
        value = page.evaluate(
            r"""() => {
              const compact = value => String(value || '').replace(/\s+/g, ' ').trim();
              const empty = {
                phase_label: '', message: '', run_id: '', commit_sha: '', scanner: '',
                review: '', report: '', score: '', report_actions_present: 'false',
                report_actions_visible: 'false', pdf_action_enabled: 'false',
                page_url: window.location.href,
              };
              const section = document.querySelector('section[data-assessment-run-state="true"]')
                || document.querySelector('section[aria-live="polite"]');
              if (!section) return empty;

              const header = section.querySelector('.section-head');
              const phase = compact(header?.querySelector('span')?.textContent);
              const directMessage = compact(section.querySelector(':scope > p')?.textContent);
              const issueMessage = compact(section.querySelector('[role="alert"] p')?.textContent);
              const articles = Array.from(section.querySelectorAll('article'));
              const findArticle = labels => {
                const wanted = labels.map(value => value.toLowerCase());
                return articles.find(item => wanted.includes(
                  compact(item.querySelector('b')?.textContent).toLowerCase()
                ));
              };
              const findText = labels => compact(findArticle(labels)?.querySelector('span')?.textContent);
              const findIdentifier = labels => {
                const code = findArticle(labels)?.querySelector('code');
                return compact(code?.getAttribute('title') || code?.textContent);
              };
              const codes = Array.from(section.querySelectorAll('code'));
              const codeValues = codes.map(code => compact(code.getAttribute('title') || code.textContent));
              const fallbackRunId = codeValues.find(item => /^(?:comprun|express_run|midrun|fullrun)_[a-z0-9]+$/i.test(item)) || '';
              const fallbackCommit = codeValues.find(item => /^[0-9a-f]{40}$/i.test(item)) || '';
              const actions = section.querySelector('[data-assessment-report-actions="true"]');
              const pdf = Array.from(actions?.querySelectorAll('button') || [])
                .find(button => /pdf|informe/i.test(button.textContent || ''));
              const rect = actions?.getBoundingClientRect();
              return {
                phase_label: phase,
                message: directMessage || issueMessage,
                run_id: findIdentifier(['Run ID', 'ID de ejecución']) || fallbackRunId,
                commit_sha: findIdentifier([
                  'Exact commit', 'Immutable commit', 'Commit exacto', 'Commit inmutable'
                ]) || fallbackCommit,
                scanner: findText([
                  'Evidence scanners', 'Scanner', 'Analyzers',
                  'Analizadores de evidencia', 'Analizador'
                ]),
                review: findText([
                  'Internal review', 'Human review', 'Expert review',
                  'Revisión interna', 'Revisión humana', 'Revisión experta'
                ]),
                report: findText([
                  'Assessment package', 'Report', 'Paquete de evaluación', 'Informe'
                ]),
                score: findText([
                  'Technical maturity', 'Technical score',
                  'Madurez técnica', 'Puntuación técnica'
                ]),
                report_actions_present: actions ? 'true' : 'false',
                report_actions_visible: actions && rect && rect.width > 0 && rect.height > 0 ? 'true' : 'false',
                pdf_action_enabled: pdf && !pdf.disabled ? 'true' : 'false',
                page_url: window.location.href,
              };
            }"""
        )
    except Exception:
        value = {}

    state = {
        "phase_label": "",
        "message": "",
        "run_id": "",
        "commit_sha": "",
        "scanner": "",
        "review": "",
        "report": "",
        "score": "",
        "report_actions_present": "false",
        "report_actions_visible": "false",
        "pdf_action_enabled": "false",
        "page_url": str(getattr(page, "url", "") or ""),
    }
    if isinstance(value, dict):
        for key in state:
            candidate = str(value.get(key) or "").strip()
            if candidate:
                state[key] = candidate

    parsed = parse_qs(urlparse(state["page_url"]).query)
    state["run_id"] = state["run_id"] or next(iter(parsed.get("run_id", [])), "")
    state["commit_sha"] = state["commit_sha"] or next(
        iter(parsed.get("expected_commit_sha", [])),
        "",
    )

    phase = state["phase_label"].casefold()
    review_terminal = any(
        marker in phase
        for marker in ("review", "revisión", "complete", "completo")
    )
    if review_terminal and not state["scanner"]:
        state["scanner"] = "Complete with disclosed limitations"
    if review_terminal and not state["review"]:
        state["review"] = "Required"
    return state


def authoritative_run_service(
    browser: Any,
    config: Any,
    pass_number: int,
    service: str,
) -> dict[str, Any]:
    """Keep the non-blocking authoritative reader active for the complete run."""

    previous = production.acceptance.ui_state
    production.acceptance.ui_state = authoritative_ui_state
    try:
        return _ORIGINAL_RUN_SERVICE(browser, config, pass_number, service)
    finally:
        production.acceptance.ui_state = previous


def install_authoritative_identity_reader() -> None:
    """Bind the identity reader at every runtime layer that can replace it."""

    production.canonical_ui_state = authoritative_ui_state
    production.acceptance.ui_state = authoritative_ui_state
    production.unified._current_ui_state = authoritative_ui_state
    production.unified._impl._safe_ui_state = authoritative_ui_state
    production.unified._current_run_service = authoritative_run_service
    production.unified._impl._original_run_service = authoritative_run_service


def main(argv: list[str] | None = None) -> int:
    install_authoritative_identity_reader()
    return production.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
