from __future__ import annotations

from pathlib import Path

from nico.express_assurance_projection_compat_v45 import (
    canonical_assurance_label,
    canonical_risk_label,
)
from nico.report_semantic_cleanup_v46 import normalize_final_report_semantics


ROOT = Path(__file__).resolve().parents[1]


def _payload() -> dict:
    return {
        "canonical_report_truth": {"delivery_status": "Draft only"},
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 86,
                "assurance_label": "VERIFIED",
                "confidence": "review-limited",
                "evidence": [
                    "No test-path signals were found in fetched text files.",
                    "Test evidence reconciled across scopes: the recursive repository tree contains 626 test-path signal(s).",
                ],
                "findings": ["No test-path signals were found in fetched text files."],
                "unavailable": [],
            },
            {
                "id": "velocity_complexity",
                "label": "Velocity / Complexity",
                "score": 72,
                "assurance_label": "VERIFIED",
                "confidence": "review-limited",
                "evidence": [],
                "findings": [],
                "unavailable": [
                    "Precise story-point expectation requires stakeholder context.",
                    "Client/human acceptance evidence unavailable: no approved final report record was found.",
                ],
            },
            {
                "id": "client_human_acceptance",
                "label": "Client / Human Acceptance",
                "score": None,
                "assurance_label": "PENDING HUMAN APPROVAL",
                "confidence": "review-limited",
                "evidence": [],
                "findings": ["No approved final report record exists."],
                "unavailable": ["Approval pending."],
            },
        ],
        "priority_actions": [
            "No test-path signals were found in fetched text files.",
            "Repair a verified release defect.",
        ],
        "repair_intelligence": {
            "candidates": [
                {"title": "No test-path signals were found in fetched text files."},
                {"title": "Repair a verified release defect."},
            ]
        },
    }


def test_explicit_assurance_overrides_stale_confidence() -> None:
    section = {"assurance_label": "VERIFIED", "confidence": "review-limited", "status": "yellow"}

    assert canonical_assurance_label(section) == "VERIFIED"


def test_risk_disposition_is_independent_from_score_and_assurance() -> None:
    assert canonical_risk_label({"score": 92, "assurance_label": "VERIFIED", "findings": []}) == "NO MATERIAL FINDING"
    assert canonical_risk_label({"score": 92, "assurance_label": "VERIFIED", "review_items": ["Review one item"]}) == "HUMAN TRIAGE REQUIRED"


def test_cleanup_removes_bounded_sample_false_priority() -> None:
    result = normalize_final_report_semantics(_payload())
    code = next(item for item in result["sections"] if item["id"] == "code_audit")

    assert code["findings"] == []
    assert "context only" in code["bounded_sample_context"]
    assert result["priority_actions"] == ["Repair a verified release defect."]
    assert result["repair_intelligence"]["candidates"] == [{"title": "Repair a verified release defect."}]


def test_cleanup_moves_acceptance_out_of_velocity_and_matches_confidence() -> None:
    result = normalize_final_report_semantics(_payload())
    velocity = next(item for item in result["sections"] if item["id"] == "velocity_complexity")
    acceptance = next(item for item in result["sections"] if item["id"] == "client_human_acceptance")

    assert velocity["confidence"] == "high"
    assert velocity["unavailable"] == ["Precise story-point expectation requires stakeholder context."]
    assert acceptance["score"] is None
    assert acceptance["technical_section"] is False
    assert acceptance["section_group"] == "review_delivery"
    assert acceptance["findings"] == []
    assert acceptance["unavailable"] == []
    assert any("approved final report" in item for item in acceptance["review_items"])
    assert result["report_finality"] == "final"
    assert result["approval_status"] == "pending_human_approval"
    assert result["client_delivery_allowed"] is False


def test_source_acceptance_uses_semantic_contract_not_page_quota() -> None:
    source = (ROOT / "scripts" / "two_service_live_acceptance.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "two-service-production-acceptance.yml").read_text(encoding="utf-8")

    assert 'pdf["page_count"] >= 30' not in source
    assert '"semantic_contract"' in source
    assert 'semantic_contract"]["status"] == "passed"' in workflow


def test_report_source_uses_final_pending_approval_language_and_safe_bullet() -> None:
    source = (ROOT / "nico" / "mid_assessment_report.py").read_text(encoding="utf-8")

    assert 'DRAFT_LABEL = "FINAL REPORT - PENDING HUMAN APPROVAL"' in source
    assert 'canvas.drawString(LEFT + 2, y, "-")' in source
    assert "DRAFT — HUMAN REVIEW REQUIRED" not in source
