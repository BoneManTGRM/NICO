#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

import two_service_live_acceptance as acceptance
import unified_production_acceptance as production

VERSION = "nico.unified_production_acceptance.canonical_terminal_rendering.v6"


def _assessment_candidate(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _candidate_completeness(value: dict[str, Any]) -> int:
    maturity = acceptance.dict_value(value.get("maturity_signal"))
    score = maturity.get("presented_score", maturity.get("score"))
    sections = value.get("sections") if isinstance(value.get("sections"), list) else []
    return (
        (1000 if isinstance(score, (int, float)) and not isinstance(score, bool) else 0)
        + len(sections) * 10
        + (5 if acceptance.first_text(value.get("executive_summary")) else 0)
        + (3 if isinstance(value.get("evidence_coverage"), dict) else 0)
    )


def canonical_assessment_payload(service: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve the same assessment truth rendered by Markdown, HTML, and PDF.

    The terminal status payload can contain a lightweight stage-level ``assessment``
    before the report package's canonical JSON assessment. Selecting the first object
    made the browser display ``Awaiting stage`` and made acceptance expect ``NOT
    SCORED`` even though the completed report contained real scores. Prefer the
    canonical package assessment, then fall back to the most complete retained stage
    assessment without fabricating or relabeling any score.
    """

    package = acceptance.report_package(service, payload)
    canonical = acceptance.dict_value(package.get("json"))
    stages = acceptance.stage_results(payload)
    candidates = [
        _assessment_candidate(canonical.get("assessment")),
        _assessment_candidate(acceptance.dict_value(stages.get("final_comprehensive_report_generation")).get("assessment")),
        _assessment_candidate(acceptance.dict_value(stages.get("evidence_reconciliation_and_scoring")).get("assessment")),
        _assessment_candidate(payload.get("assessment")),
        payload if service == "express" and isinstance(payload.get("sections"), list) else {},
    ]
    populated = [item for item in candidates if item]
    if not populated:
        return {}
    return max(populated, key=_candidate_completeness)


def canonical_ui_state(page: Any) -> dict[str, str]:
    """Capture terminal state and prove report actions are reachable at mobile size."""

    section = page.locator('section[aria-live="polite"]').first
    return section.evaluate(
        """section => {
          const header = section.querySelector('.section-head');
          const phase = header?.querySelector('span')?.textContent?.trim() || '';
          const message = section.querySelector(':scope > p')?.textContent?.trim() || '';
          const articles = Array.from(section.querySelectorAll('article'));
          const find = labels => {
            const wanted = new Set(labels);
            const article = articles.find(item => wanted.has(item.querySelector('b')?.textContent?.trim() || ''));
            return article?.querySelector('span')?.textContent?.trim() || '';
          };
          const actions = section.querySelector('[data-assessment-report-actions="true"]');
          const pdf = Array.from(actions?.querySelectorAll('button') || []).find(button => /pdf|informe/i.test(button.textContent || ''));
          const rect = actions?.getBoundingClientRect();
          return {
            phase_label: phase,
            message,
            run_id: find(['Run ID']),
            commit_sha: find(['Immutable commit']),
            scanner: find(['Scanner', 'Evidence scanners']),
            report: find(['Report', 'Assessment package']),
            review: find(['Human review', 'Expert review']),
            score: find(['Technical score', 'Technical maturity']),
            report_actions_present: actions ? 'true' : 'false',
            report_actions_visible: actions && rect && rect.width > 0 && rect.height > 0 ? 'true' : 'false',
            pdf_action_enabled: pdf && !pdf.disabled ? 'true' : 'false',
            page_url: window.location.href,
          };
        }"""
    )


def main(argv: list[str] | None = None) -> int:
    acceptance.assessment_payload = canonical_assessment_payload
    acceptance.ui_state = canonical_ui_state
    return production.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
