from __future__ import annotations

import io

from nico.comprehensive_report_clarity_v8 import (
    VERSION,
    _front_matter_correction,
    clarify_comprehensive_assurance,
)


def test_assurance_clarity_preserves_canonical_status_and_names_the_reason() -> None:
    assessment = {
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "score_value": 90,
                "assurance_label": "REVIEW LIMITED",
                "findings": ["One candidate requires disposition."],
                "unavailable": [],
            },
            {
                "id": "velocity_complexity",
                "label": "Velocity / Complexity",
                "score_value": 84,
                "assurance_label": "VERIFIED",
                "findings": [],
                "unavailable": [],
            },
        ],
        "scoring_weights": [
            {"section_id": "dependency_health", "assurance": "REVIEW LIMITED"},
            {"section_id": "velocity_complexity", "assurance": "VERIFIED"},
        ],
    }

    result = clarify_comprehensive_assurance(assessment)
    dependency, velocity = result["sections"]

    assert dependency["assurance_label"] == "REVIEW LIMITED"
    assert dependency["assurance_display"] == "LIMITED · CANDIDATE DISPOSITION"
    assert dependency["assurance_reason"] == "candidate disposition"
    assert velocity["assurance_label"] == "VERIFIED"
    assert velocity["assurance_display"] == "VERIFIED"
    assert result["scoring_weights"][0]["assurance"] == "LIMITED · CANDIDATE DISPOSITION"
    assert result["scoring_weights"][0]["assurance_canonical"] == "REVIEW LIMITED"
    assert result["assurance_legend"]["version"] == VERSION
    assert result["assurance_legend"]["technical_score_independent"] is True


def test_assurance_reason_is_derived_from_the_actual_open_evidence_boundary() -> None:
    assessment = {
        "sections": [
            {
                "id": "secrets_review",
                "assurance_label": "REVIEW LIMITED",
                "unavailable": ["TruffleHog full history coverage was unavailable."],
                "findings": [],
            },
            {
                "id": "static_analysis",
                "assurance_label": "REVIEW LIMITED",
                "unavailable": ["Bandit analyzer execution did not complete."],
                "findings": [],
            },
            {
                "id": "ci_cd",
                "assurance_label": "REVIEW LIMITED",
                "unavailable": ["Historical CI failure cause classification is incomplete."],
                "findings": [],
            },
        ],
        "scoring_weights": [],
    }

    result = clarify_comprehensive_assurance(assessment)
    displays = {item["id"]: item["assurance_display"] for item in result["sections"]}

    assert displays["secrets_review"] == "LIMITED · HISTORY COVERAGE"
    assert displays["static_analysis"] == "LIMITED · ANALYZER COVERAGE"
    assert displays["ci_cd"] == "LIMITED · WORKFLOW CLASSIFICATION"


def test_front_matter_correction_is_a_two_page_pdf_with_decision_card() -> None:
    from pypdf import PdfReader

    payload = _front_matter_correction({
        "executive_risk_register": [
            {"title": "Concentrated frontend complexity"},
            {"title": "Historical CI failures need cause classification"},
            {"title": "Static-analysis assurance remains review-limited"},
        ]
    })

    reader = PdfReader(io.BytesIO(payload))
    assert len(reader.pages) == 2
    text = reader.pages[1].extract_text() or ""
    assert "TOP BUSINESS CONSEQUENCES" in text
    assert "Decision-relevant issues to address first" in text
    assert "Concentrated frontend complexity" in text
