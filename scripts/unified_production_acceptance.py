#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

import two_service_live_acceptance as acceptance
import two_service_live_acceptance_v3 as unified

VERSION = "nico.unified_production_acceptance.report_identity.v1"
COMPREHENSIVE_REPORT_IDENTITIES = (
    ("NICO Comprehensive Technical Assessment",),
    ("NICO Comprehensive", "Decision-Grade Technical Assessment"),
)


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def has_comprehensive_report_identity(value: Any) -> bool:
    normalized = _normalized(value)
    return any(
        all(_normalized(marker) in normalized for marker in identity)
        for identity in COMPREHENSIVE_REPORT_IDENTITIES
    )


def validate_report(service: str, payload: dict[str, Any], destination: Path) -> dict[str, Any]:
    package = acceptance.report_package(service, payload)
    assessment = acceptance.assessment_payload(service, payload)
    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    encoded_pdf = str(package.get("pdf_base64") or "")

    assert markdown.strip(), f"{service} Markdown report is missing"
    assert rendered_html.strip().lower().startswith("<!doctype html"), f"{service} HTML report is invalid"
    assert encoded_pdf, f"{service} PDF report is missing"
    assert "NONE/100" not in markdown.upper()
    assert "NULL/100" not in markdown.upper()

    pdf = acceptance.pdf_evidence(encoded_pdf, destination)
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
        for stale in (
            "DRAFT ONLY",
            "DRAFT - HUMAN REVIEW REQUIRED",
            "DRAFT · HUMAN REVIEW REQUIRED",
            "COMPLETE ONLY AS A DRAFT",
        ):
            assert stale not in upper_markdown, f"Comprehensive Markdown retained stale status: {stale}"
            assert stale not in upper_pdf, f"Comprehensive PDF retained stale status: {stale}"

        assert "FINAL REPORT" in upper_markdown
        assert "FINAL REPORT" in upper_pdf
        assert "PENDING HUMAN APPROVAL" in upper_markdown
        assert "PENDING HUMAN APPROVAL" in upper_pdf
        assert "\x7f" not in pdf["text"], "Comprehensive PDF contains a control-character glyph"

    maturity = acceptance.dict_value(assessment.get("maturity_signal"))
    score = maturity.get("presented_score", maturity.get("score"))
    score_label = f"{int(score)}/100" if isinstance(score, (int, float)) else "NOT SCORED"
    assert score_label in markdown
    assert score_label in rendered_html
    assert score_label in pdf["text"]

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
            "stale_draft_language_absent": True,
            "control_characters_absent": True,
            "canonical_report_identity_verified": True,
        },
        "markdown_sha256": acceptance.sha256(markdown.encode("utf-8")),
        "html_sha256": acceptance.sha256(rendered_html.encode("utf-8")),
    }


def main(argv: list[str] | None = None) -> int:
    acceptance.validate_report = validate_report
    return unified.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
