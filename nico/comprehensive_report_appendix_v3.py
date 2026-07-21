from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from nico import comprehensive_report_package as base_report

VERSION = "nico.comprehensive_report_appendix.v4"
APPENDIX_HEADING = "## Evidence Appendix"
REVIEW_HEADING = "## Human Review and Acceptance Gate"
LEGACY_REVIEW_HEADING = "## Human Review Checklist"


def _text(value: Any, limit: int = 1200) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _items(values: Any, *, empty: str) -> list[str]:
    if not isinstance(values, list):
        return [f"- {empty}"]
    output = [f"- {_text(value, 1200)}" for value in values if _text(value, 1200)]
    return output or [f"- {empty}"]


def _appendix(stage_summaries: Any) -> str:
    stages = stage_summaries if isinstance(stage_summaries, list) else []
    lines = [
        APPENDIX_HEADING,
        "The appendix preserves bounded stage evidence for the exact immutable run. "
        "It is separated from the decision-oriented body so reviewers can trace conclusions "
        "without turning the executive report into an evidence dump.",
    ]
    if not stages:
        lines.extend(
            [
                "",
                "- No structured stage summary was retained. This absence requires human review.",
            ]
        )
        return "\n".join(lines)

    for index, stage in enumerate(stages, start=1):
        if not isinstance(stage, dict):
            continue
        title = _text(stage.get("title") or stage.get("stage_id") or f"Stage {index}", 180)
        stage_id = _text(stage.get("stage_id") or "unknown_stage", 120)
        status = _text(stage.get("status") or "unknown", 40).upper()
        summary = _text(stage.get("summary") or "No stage summary was retained.", 1800)
        lines.extend(
            [
                "",
                f"### A{index}. {title} — {status}",
                f"- Stage ID: `{stage_id}`",
                f"- Summary: {summary}",
                "",
                "Evidence:",
                *_items(
                    stage.get("evidence"),
                    empty="No structured evidence line was retained for this stage.",
                ),
            ]
        )
        findings = stage.get("findings")
        if isinstance(findings, list) and findings:
            lines.extend(["", "Findings:", *_items(findings, empty="No finding retained.")])
        unavailable = stage.get("unavailable")
        if isinstance(unavailable, list) and unavailable:
            lines.extend(
                [
                    "",
                    "Unavailable or limited evidence:",
                    *_items(unavailable, empty="No unavailable-evidence note retained."),
                ]
            )
    return "\n".join(lines)


def _normalize_review_heading(markdown: str) -> str:
    if REVIEW_HEADING in markdown:
        return markdown
    return markdown.replace(LEGACY_REVIEW_HEADING, REVIEW_HEADING, 1)


def _insert_before_review(markdown: str, appendix: str) -> str:
    markdown = _normalize_review_heading(markdown)
    if APPENDIX_HEADING in markdown:
        return markdown
    marker = f"\n{REVIEW_HEADING}\n"
    if marker in markdown:
        return markdown.replace(marker, f"\n{appendix}\n{marker}", 1)
    return markdown.rstrip() + f"\n\n{appendix}\n\n{REVIEW_HEADING}\n"


def build_comprehensive_report_package(
    *,
    identity: dict[str, Any],
    stage_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build one report package with matching appendix and review-gate headings.

    The base PDF contains both the Evidence Appendix and Human Review and Acceptance
    Gate. Production acceptance proved that the source Markdown used a shorter legacy
    review heading. This wrapper preserves the canonical JSON and valid PDF, inserts
    the bounded appendix, normalizes the human-review heading, regenerates semantic
    HTML from that exact Markdown, and records rendered artifact hashes.
    """

    result = base_report.build_comprehensive_report_package(
        identity=identity,
        stage_results=stage_results,
    )
    if str(result.get("status") or "blocked") != "complete":
        return result

    output = deepcopy(result)
    package = output.get("report_package")
    if not isinstance(package, dict):
        return {
            **output,
            "status": "blocked",
            "reason": "comprehensive_report_package_missing",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    markdown = str(package.get("markdown") or "")
    appendix = _appendix(output.get("stage_summaries"))
    markdown = _insert_before_review(markdown, appendix)
    title = f"NICO Comprehensive Technical Assessment — {_text(identity.get('repository'), 220)}"
    rendered_html = base_report._semantic_html(markdown, title)

    package["markdown"] = markdown
    package["html"] = rendered_html
    package["markdown_sha256"] = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    package["html_sha256"] = hashlib.sha256(rendered_html.encode("utf-8")).hexdigest()
    package["appendix_contract_schema"] = VERSION
    package["evidence_appendix_present"] = True
    package["human_review_acceptance_gate_present"] = True
    package["human_review_required"] = True
    package["client_delivery_allowed"] = False

    quality = dict(package.get("report_quality_contract") or {})
    quality.update(
        {
            "appendix_contract_schema": VERSION,
            "full_evidence_appendix": True,
            "markdown_evidence_appendix": APPENDIX_HEADING in markdown,
            "html_evidence_appendix": "<h2>Evidence Appendix</h2>" in rendered_html,
            "markdown_human_review_acceptance_gate": REVIEW_HEADING in markdown,
            "html_human_review_acceptance_gate": "<h2>Human Review and Acceptance Gate</h2>" in rendered_html,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    package["report_quality_contract"] = quality
    output["report_package"] = package
    output["report_quality_contract"] = quality
    output["appendix_contract_schema"] = VERSION
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False

    required = (
        quality["markdown_evidence_appendix"],
        quality["html_evidence_appendix"],
        quality["markdown_human_review_acceptance_gate"],
        quality["html_human_review_acceptance_gate"],
    )
    if not all(required):
        output["status"] = "blocked"
        output["reason"] = "comprehensive_cross_format_chapter_missing"
    return output


def install_native_provider_binding() -> dict[str, Any]:
    """Bind the cross-format chapter-aware builder into native providers once."""

    from nico import comprehensive_native_providers as providers

    providers.build_comprehensive_report_package = build_comprehensive_report_package
    return {
        "artifact_schema": VERSION,
        "bound": providers.build_comprehensive_report_package is build_comprehensive_report_package,
        "markdown_evidence_appendix": True,
        "html_evidence_appendix": True,
        "pdf_evidence_appendix": True,
        "markdown_human_review_acceptance_gate": True,
        "html_human_review_acceptance_gate": True,
        "pdf_human_review_acceptance_gate": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "APPENDIX_HEADING",
    "LEGACY_REVIEW_HEADING",
    "REVIEW_HEADING",
    "VERSION",
    "build_comprehensive_report_package",
    "install_native_provider_binding",
]
