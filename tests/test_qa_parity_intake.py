from __future__ import annotations

from nico.qa_parity_intake import build_qa_parity_intake
from nico.service_workflows import build_mid_assessment


def test_qa_parity_intake_maps_platforms_flows_and_blockers():
    payload = {
        "qa_evidence": "PASS iOS login works\nFAIL Android payment checkout crash\nPASS Web search create edit flow works",
        "parity_notes": "iPhone and Android labels match\nChrome web and mobile web responsive layout verified",
        "acceptance_criteria": "Login passes on iOS, Android, and web\nCheckout has no crash before release",
        "known_risks": "Critical blocker: Android payment checkout crash",
    }

    intake = build_qa_parity_intake(payload)

    assert intake["artifact_schema"] == "nico.qa_parity_intake.v1"
    assert intake["status"] == "blocked_by_critical_qa_or_parity_item"
    assert intake["platform_matrix"]["ios"]["covered"] is True
    assert intake["platform_matrix"]["android"]["covered"] is True
    assert intake["platform_matrix"]["web"]["covered"] is True
    assert intake["flow_matrix"]["authentication"]["covered"] is True
    assert intake["flow_matrix"]["payment_subscription"]["covered"] is True
    assert intake["status_counts"]["pass"] == 2
    assert intake["status_counts"]["fail"] == 1
    assert intake["blockers"]


def test_qa_parity_intake_marks_missing_evidence_as_unavailable():
    intake = build_qa_parity_intake({})

    assert intake["status"] == "incomplete_intake"
    assert intake["readiness_score"] < 50
    assert any("QA evidence is missing" in item for item in intake["unavailable"])
    assert any("Platform parity evidence is missing" in item for item in intake["unavailable"])


def test_mid_assessment_attaches_structured_qa_parity_intake():
    result = build_mid_assessment(
        {
            "authorized": True,
            "qa_evidence": "PASS iOS login works\nPASS Android login works",
            "parity_notes": "iOS and Android login copy matches",
            "stakeholder_notes": "Client wants audit-ready app release.",
            "roadmap_notes": "Month 1 QA stabilization.",
            "known_risks": "No known launch blocker.",
        }
    )

    assert result["status"] == "complete"
    assert result["qa_parity_intake"]["artifact_schema"] == "nico.qa_parity_intake.v1"
    assert result["qa_parity_intake"]["qa_item_count"] == 2
    qa_section = next(item for item in result["sections"] if item["id"] == "qa_functional")
    assert any("Structured QA intake status" in item for item in qa_section["evidence"])
