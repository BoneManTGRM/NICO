from __future__ import annotations

import html
from typing import Any


_PATCH_MARKER = "_nico_mid_report_v5_compat"
_TECHNICAL_IDS = {
    "code_audit",
    "dependency_health",
    "secrets_review",
    "static_analysis",
    "ci_cd",
    "architecture_debt",
    "velocity_complexity",
}


def _sections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("sections")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _markdown_contract(current_markdown, payload: dict[str, Any]) -> str:
    text = current_markdown(payload)
    text = text.replace(
        "# NICO MID TECHNICAL ASSESSMENT",
        "# NICO MID ASSESSMENT\n\n## NICO MID TECHNICAL ASSESSMENT",
        1,
    )
    text = text.replace("## Executive decision", "## Decision summary", 1)
    text = text.replace(
        "The technical score is the weighted result of seven controls.",
        "The score is the weighted result of seven technical sections.",
        1,
    )

    context_count = sum(1 for item in _sections(payload) if str(item.get("id") or "") not in _TECHNICAL_IDS)
    score_marker = "- Human review: **REQUIRED**"
    if score_marker in text:
        text = text.replace(
            score_marker,
            f"- Human-context sections unscored: {context_count}\n{score_marker}",
            1,
        )

    truth_lines = []
    for section in _sections(payload):
        label = section.get("label") or section.get("id") or "Assessment section"
        truth = section.get("truth_status") or section.get("status") or "Unknown"
        truth_lines.append(f"- {label}: Truth status: **{truth}**")
    truth_summary = "### Truth status summary\n" + "\n".join(truth_lines) + "\n\n"
    text = text.replace("### Priority controls\n", truth_summary + "### Priority controls\n", 1)

    coverage = payload.get("evidence_coverage") if isinstance(payload.get("evidence_coverage"), dict) else {}
    coverage_note = (
        "## Automated evidence coverage\n\n"
        f"Evidence-unit coverage is {coverage.get('percent', 0)}% "
        f"({coverage.get('numerator', 0)}/{coverage.get('denominator', 0)} explicit units). "
        "It measures availability, not analyzer completion, finding severity, or reviewer disposition.\n\n"
    )
    text = text.replace("## Method and score sensitivity\n", coverage_note + "## Method and score sensitivity\n", 1)
    text = text.replace("## Repair and verification plan", "## Prioritized repair intelligence", 1)
    text = text.replace("## Review exceptions and integrity", "## Review by exception and integrity", 1)
    return text


def install_mid_report_v5_compat() -> dict[str, Any]:
    from nico import mid_assessment_report as report_module

    if getattr(report_module, _PATCH_MARKER, False):
        return {"status": "already_installed"}

    current_markdown = report_module._markdown

    def markdown_compat(payload: dict[str, Any]) -> str:
        return _markdown_contract(current_markdown, payload)

    def html_compat(payload: dict[str, Any]) -> str:
        escaped = html.escape(markdown_compat(payload))
        return (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>NICO MID ASSESSMENT</title></head>"
            f"<body><pre>{escaped}</pre></body></html>"
        )

    report_module._markdown = markdown_compat
    report_module._html = html_compat
    setattr(report_module, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "legacy_markdown_contract_preserved": True,
        "legacy_pdf_headings_preserved_by_stable_alias": True,
        "request_time_global_patch_removed": True,
        "canonical_v5_presentation_preserved": True,
    }


__all__ = ["install_mid_report_v5_compat"]
