from __future__ import annotations

from nico.roadmap_generator import build_six_month_roadmap
from nico.service_workflows import build_mid_assessment


def test_six_month_roadmap_uses_discovery_qa_and_risk_inputs():
    roadmap = build_six_month_roadmap(
        {
            "stakeholder_goals": "Launch audit-ready product",
            "target_users": "Client approver",
            "pain_points": "Reports are hard to defend",
            "constraints": "Budget is fixed",
            "success_metrics": "Client acceptance approved",
            "decision_makers": "Founder signs off",
            "qa_evidence": "PASS iOS login works\nFAIL Android payment checkout crash",
            "parity_notes": "iOS and Android labels match",
            "known_risks": "Critical blocker: Android payment checkout crash",
            "roadmap_notes": "Month 1 stabilize QA evidence",
        }
    )

    assert roadmap["artifact_schema"] == "nico.six_month_roadmap.v1"
    assert roadmap["status"] == "blocked_by_qa_or_delivery_risk"
    assert roadmap["readiness_score"] <= 70
    assert len(roadmap["month_plan"]) == 6
    assert len(roadmap["roadmap_summary"]) == 6
    assert roadmap["source_counts"]["roadmap_notes"] == 1
    assert roadmap["human_review_required"] is True


def test_six_month_roadmap_marks_missing_inputs():
    roadmap = build_six_month_roadmap({})

    assert roadmap["status"] == "needs_more_evidence"
    assert len(roadmap["month_plan"]) == 6
    assert any("Stakeholder discovery is incomplete" in item for item in roadmap["unavailable"])
    assert any("No explicit roadmap notes" in item for item in roadmap["unavailable"])


def test_mid_assessment_attaches_generated_six_month_roadmap():
    result = build_mid_assessment(
        {
            "authorized": True,
            "qa_evidence": "PASS iOS login works\nPASS Android login works",
            "parity_notes": "iOS and Android login copy matches",
            "stakeholder_notes": "Goal is launch faster\nUser is client approver\nProblem is unclear evidence\nBudget constraint is fixed\nSuccess metric is signed acceptance\nDecision maker is CEO",
            "roadmap_notes": "Month 1 QA stabilization",
            "known_risks": "No known launch blocker",
        }
    )

    assert result["status"] == "complete"
    assert result["six_month_roadmap_artifact"]["artifact_schema"] == "nico.six_month_roadmap.v1"
    assert len(result["six_month_roadmap"]) == 6
    roadmap_section = next(item for item in result["sections"] if item["id"] == "roadmap_planning")
    assert any("Generated roadmap status" in item for item in roadmap_section["evidence"])
