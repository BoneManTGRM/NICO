#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import two_service_live_acceptance as acceptance
import two_service_live_acceptance_v3 as unified

VERSION = "nico.unified_production_acceptance.canonical_terminal_rendering.v6"
ASSESSMENT_WORKSPACE_SELECTOR = (
    'main[data-workspace="assessment"]'
    '[data-engagement-type="comprehensive"]'
    '[data-canonical-assessment="strategic"]'
)
ASSESSMENT_RUN_SELECTOR = '[data-assessment-primary-action="true"]'
ASSESSMENT_AUTHORIZATION_SELECTOR = '[data-assessment-authorization="true"]'
CLIENT_COPY_CONTRACT = "expert-engagement-hydrated-v1"
HYDRATION_TIMEOUT_SECONDS = 30.0
PUBLIC_RUN_LABELS = {
    "en": "Create engagement and capture repository snapshot",
    "es-MX": "Crear encargo y capturar instantánea del repositorio",
}
PUBLIC_HEADINGS = {
    "en": "Create assessment engagement",
    "es-MX": "Crear encargo de evaluación",
}
COMPREHENSIVE_REPORT_IDENTITIES = (
    ("NICO Comprehensive Technical Assessment",),
    ("NICO Comprehensive", "Decision-Grade Technical Assessment"),
)
LEGACY_DRAFT_PHRASES = (
    "DRAFT - HUMAN REVIEW REQUIRED",
    "DRAFT · HUMAN REVIEW REQUIRED",
    "COMPLETE ONLY AS A DRAFT",
)
RETIRED_TIER_SELECTOR = '[aria-label="Assessment type"]'


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def has_comprehensive_report_identity(value: Any) -> bool:
    normalized = _normalized(value)
    return any(
        all(_normalized(marker) in normalized for marker in identity)
        for identity in COMPREHENSIVE_REPORT_IDENTITIES
    )


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
    """Use the canonical report assessment instead of a lightweight terminal shell."""

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
    return max(populated, key=_candidate_completeness) if populated else {}


def canonical_ui_state(page: Any) -> dict[str, str]:
    """Capture mobile terminal state and report-control visibility."""

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


def validate_preapproval_delivery_posture(
    markdown: str,
    pdf_text: str,
    payload: dict[str, Any],
    assessment: dict[str, Any],
) -> dict[str, bool]:
    upper_markdown = markdown.upper()
    upper_pdf = pdf_text.upper()
    for stale in LEGACY_DRAFT_PHRASES:
        assert stale not in upper_markdown, f"Comprehensive Markdown retained stale status: {stale}"
        assert stale not in upper_pdf, f"Comprehensive PDF retained stale status: {stale}"

    draft_only_label_present = "DRAFT ONLY" in upper_markdown or "DRAFT ONLY" in upper_pdf
    if draft_only_label_present:
        assert "PENDING HUMAN APPROVAL" in upper_markdown
        assert "PENDING HUMAN APPROVAL" in upper_pdf
        assert payload.get("client_delivery_allowed") is not True
        assert assessment.get("client_delivery_allowed") is not True

    return {
        "stale_draft_language_absent": True,
        "preapproval_delivery_posture_verified": True,
        "draft_only_delivery_label_present": draft_only_label_present,
    }


def verify_retired_tier_selector(workspace: Any, locale: str) -> dict[str, bool]:
    """Accept complete removal or fully hidden legacy tier controls."""

    selector = workspace.locator(RETIRED_TIER_SELECTOR)
    count = selector.count()
    if count == 0:
        return {
            "legacy_selector_hidden": True,
            "legacy_selector_removed": True,
        }

    assert count == 1, f"{locale} rendered {count} retired tier selectors"
    choice_grid = selector.first
    assert choice_grid.get_attribute("aria-hidden") == "true"
    assert choice_grid.is_hidden(), f"{locale} exposed the retired tier selector"
    buttons = choice_grid.locator("button")
    assert buttons.count() == 2, f"{locale} retained an incomplete legacy tier control"
    assert all(buttons.nth(index).is_hidden() for index in range(buttons.count()))
    return {
        "legacy_selector_hidden": True,
        "legacy_selector_removed": False,
    }


def hydrated_workspace_matches(snapshot: dict[str, Any], *, locale: str, expected_sha: str) -> bool:
    return bool(
        snapshot.get("hydrated") == "true"
        and snapshot.get("client_copy_contract") == CLIENT_COPY_CONTRACT
        and snapshot.get("client_release_sha") == expected_sha
        and snapshot.get("client_copy_verified") == "true"
        and snapshot.get("observed_action") == PUBLIC_RUN_LABELS[locale]
        and snapshot.get("observed_heading") == PUBLIC_HEADINGS[locale]
    )


def _hydrated_workspace_snapshot(page: Any) -> dict[str, str]:
    value = page.evaluate(
        """selector => {
          const workspace = document.querySelector(selector);
          const action = workspace?.querySelector('[data-assessment-primary-action="true"]');
          const heading = workspace?.querySelector('#assessment .section-head h2');
          const compact = value => String(value || '').replace(/\s+/g, ' ').trim();
          return {
            hydrated: workspace?.getAttribute('data-assessment-hydrated') || 'missing',
            client_copy_contract: workspace?.getAttribute('data-assessment-client-copy-contract') || 'missing',
            client_release_sha: workspace?.getAttribute('data-assessment-client-release-sha') || 'missing',
            client_copy_verified: workspace?.getAttribute('data-assessment-client-copy-verified') || 'missing',
            observed_action: compact(action?.textContent),
            observed_heading: compact(heading?.textContent),
            source_copy_contract: workspace?.getAttribute('data-assessment-copy-contract') || 'missing',
            page_url: window.location.href,
          };
        }""",
        ASSESSMENT_WORKSPACE_SELECTOR,
    )
    if not isinstance(value, dict):
        return {"error": "hydrated_workspace_snapshot_not_object"}
    return {str(key): str(item or "") for key, item in value.items()}


def wait_for_hydrated_workspace(page: Any, *, locale: str, expected_sha: str) -> dict[str, str]:
    deadline = time.monotonic() + HYDRATION_TIMEOUT_SECONDS
    last: dict[str, str] = {}
    while time.monotonic() < deadline:
        last = _hydrated_workspace_snapshot(page)
        if hydrated_workspace_matches(last, locale=locale, expected_sha=expected_sha):
            return last
        page.wait_for_timeout(250)
    raise AssertionError(
        f"{locale} hydrated frontend release contract did not converge: "
        + json.dumps(
            {
                "expected_sha": expected_sha,
                "expected_client_copy_contract": CLIENT_COPY_CONTRACT,
                "expected_action": PUBLIC_RUN_LABELS[locale],
                "expected_heading": PUBLIC_HEADINGS[locale],
                "observed": last,
            },
            sort_keys=True,
        )
    )


def verify_unified_language_parity(browser: Any, config: Any) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for locale, path in (
        ("en", "/assessment?tier=comprehensive"),
        ("es-MX", "/es/assessment?tier=comprehensive"),
    ):
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            locale=locale,
            service_workers="block",
            extra_http_headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "CDN-Cache-Control": "no-store",
                "Vercel-CDN-Cache-Control": "no-store",
            },
        )
        page = context.new_page()
        try:
            page.goto(
                config.frontend_origin + path + f"&nico_browser_probe={time.time_ns()}#assessment",
                wait_until="domcontentloaded",
                timeout=config.navigation_timeout_ms,
            )
            workspace = page.locator(ASSESSMENT_WORKSPACE_SELECTOR).first
            workspace.wait_for(state="visible", timeout=config.navigation_timeout_ms)
            hydration_evidence = wait_for_hydrated_workspace(
                page,
                locale=locale,
                expected_sha=config.expected_sha,
            )
            selector_evidence = verify_retired_tier_selector(workspace, locale)

            run_button = workspace.locator(ASSESSMENT_RUN_SELECTOR).first
            run_button.wait_for(state="visible", timeout=config.navigation_timeout_ms)
            run_label = acceptance.text(run_button.inner_text(), 160)
            assert run_label == PUBLIC_RUN_LABELS[locale], (
                f"{locale} canonical run label was {run_label!r}, "
                f"expected {PUBLIC_RUN_LABELS[locale]!r}"
            )
            heading = acceptance.text(
                workspace.locator("#assessment .section-head h2").first.inner_text(),
                200,
            )
            assert heading == PUBLIC_HEADINGS[locale], (
                f"{locale} canonical heading was {heading!r}, "
                f"expected {PUBLIC_HEADINGS[locale]!r}"
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
                **selector_evidence,
                "hydrated_release_verified": True,
                "hydration": hydration_evidence,
                "run_label": run_label,
                "heading": heading,
                "screenshot": screenshot.as_posix(),
                "screenshot_sha256": acceptance.sha256(screenshot.read_bytes()),
            }
        finally:
            context.close()
    return results


def validate_report(service: str, payload: dict[str, Any], destination: Path) -> dict[str, Any]:
    package = acceptance.report_package(service, payload)
    assessment = acceptance.assessment_payload(service, payload)
    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    encoded_pdf = str(package.get("pdf_base64") or "")

    assert markdown.strip(), f"{service} Markdown report is missing"
    assert rendered_html.strip().lower().startswith("<!doctype html"), f"{service} HTML report is invalid"
    assert encoded_pdf, f"{service} PDF report is missing"
    assert "NONE/100" not in markdown.upper(), f"{service} Markdown contains NONE/100"
    assert "NULL/100" not in markdown.upper(), f"{service} Markdown contains NULL/100"

    pdf = acceptance.pdf_evidence(encoded_pdf, destination)
    delivery_posture = {
        "stale_draft_language_absent": True,
        "preapproval_delivery_posture_verified": True,
        "draft_only_delivery_label_present": False,
    }
    if service == "comprehensive":
        assert package.get("service_id") == "comprehensive"
        for format_name, content in (
            ("Markdown", markdown),
            ("HTML", rendered_html),
            ("PDF", pdf["text"]),
        ):
            assert has_comprehensive_report_identity(content), (
                f"Comprehensive {format_name} omitted the canonical report identity"
            )

        assert "NICO MID TECHNICAL" not in markdown.upper()
        assert "NICO MID TECHNICAL" not in pdf["text"].upper()
        semantic_markers = (
            "Functional QA",
            "Platform Parity",
            "Six-Month Roadmap",
            "Staffing, Sequencing, and Cost",
            "Evidence Appendix",
            "Human Review and Acceptance Gate",
        )
        for marker in semantic_markers:
            assert marker in markdown, f"Comprehensive Markdown omitted {marker}"
            assert marker in pdf["text"], f"Comprehensive PDF omitted {marker}"

        upper_markdown = markdown.upper()
        upper_pdf = pdf["text"].upper()
        assert "FINAL REPORT" in upper_markdown
        assert "FINAL REPORT" in upper_pdf
        assert "PENDING HUMAN APPROVAL" in upper_markdown
        assert "PENDING HUMAN APPROVAL" in upper_pdf
        delivery_posture = validate_preapproval_delivery_posture(
            markdown,
            pdf["text"],
            payload,
            assessment,
        )
        assert "\x7f" not in pdf["text"], "Comprehensive PDF contains a control-character glyph"

    maturity = acceptance.dict_value(assessment.get("maturity_signal"))
    score = maturity.get("presented_score", maturity.get("score"))
    assert isinstance(score, (int, float)) and not isinstance(score, bool), (
        f"{service} canonical assessment did not expose a numeric maturity score"
    )
    score_label = f"{int(score)}/100"
    assert score_label in markdown, f"{service} Markdown omitted canonical score {score_label}"
    assert score_label in rendered_html, f"{service} HTML omitted canonical score {score_label}"
    assert score_label in pdf["text"], f"{service} PDF omitted canonical score {score_label}"

    section_evidence = acceptance.section_parity(assessment, markdown, rendered_html, pdf["text"])
    truth_values = {
        acceptance.text(value, 128)
        for value in (
            package.get("canonical_truth_sha256"),
            acceptance.dict_value(package.get("json")).get("canonical_truth_sha256"),
            payload.get("canonical_truth_sha256"),
        )
        if acceptance.text(value, 128)
    }
    if len(truth_values) > 1:
        raise AssertionError(f"canonical truth hash drift: {sorted(truth_values)}")

    return {
        "report_id": acceptance.first_text(package.get("report_id"), payload.get("report_id")),
        "score": score_label,
        "maturity_level": acceptance.first_text(maturity.get("level")),
        "section_parity": section_evidence,
        "canonical_truth_sha256": next(iter(truth_values), ""),
        "pdf": {key: value for key, value in pdf.items() if key != "text"},
        "semantic_contract": {
            "status": "passed",
            "page_count_informational_only": True,
            "required_sections_verified": True,
            "final_report_language_verified": True,
            **delivery_posture,
            "control_characters_absent": True,
            "canonical_report_identity_verified": True,
            "canonical_score_verified": True,
        },
        "markdown_sha256": acceptance.sha256(markdown.encode("utf-8")),
        "html_sha256": acceptance.sha256(rendered_html.encode("utf-8")),
    }


def _canonical_get_by_role(self: Any, role: str, *args: Any, **kwargs: Any) -> Any:
    normalized_role = str(role).lower()
    name = kwargs.get("name")
    if normalized_role == "button" and name == "Comprehensive":
        return unified._CanonicalServiceLocator()
    if normalized_role == "button" and name in {
        "Run Comprehensive",
        "Run NICO Assessment",
        PUBLIC_RUN_LABELS["en"],
    }:
        return self._page.locator(ASSESSMENT_RUN_SELECTOR).first
    if normalized_role == "checkbox":
        locator = self._page.locator(ASSESSMENT_AUTHORIZATION_SELECTOR).first
        return unified._StableFormLocator(locator, self._page)
    return self._page.get_by_role(role, *args, **kwargs)


def install_unified_workspace_contract() -> None:
    unified.UNIFIED_WORKSPACE_SELECTOR = ASSESSMENT_WORKSPACE_SELECTOR
    unified.RUN_SELECTOR = ASSESSMENT_RUN_SELECTOR
    unified.PUBLIC_RUN_LABELS = PUBLIC_RUN_LABELS
    unified.PUBLIC_HEADINGS = PUBLIC_HEADINGS
    unified._ExpectedCommitPage.get_by_role = _canonical_get_by_role


def main(argv: list[str] | None = None) -> int:
    install_unified_workspace_contract()
    acceptance.assessment_payload = canonical_assessment_payload
    acceptance.ui_state = canonical_ui_state
    acceptance.validate_report = validate_report
    unified._verify_unified_language_parity = verify_unified_language_parity
    return unified.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
