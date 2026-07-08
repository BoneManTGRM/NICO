from __future__ import annotations

from nico.stakeholder_discovery import build_stakeholder_discovery


def test_stakeholder_discovery_maps_structured_fields():
    discovery = build_stakeholder_discovery(
        {
            "stakeholder_goals": "Launch client audit product\nReduce manual review time",
            "target_users": "Founder\nTechnical reviewer\nClient approver",
            "pain_points": "Reports are hard to defend without evidence bundle",
            "constraints": "Budget is limited\nClient deadline is fixed",
            "success_metrics": "Client acceptance approval recorded\nAudit report delivered with no missing evidence blockers",
            "decision_makers": "Founder signs off\nClient representative approves delivery",
            "open_questions": "Confirm who owns final report delivery",
        }
    )

    assert discovery["artifact_schema"] == "nico.stakeholder_discovery.v1"
    assert discovery["status"] == "ready_for_human_review_with_open_questions"
    assert discovery["readiness_score"] >= 80
    assert discovery["complete_required_categories"] == discovery["required_category_count"]
    assert discovery["categories"]["goals"]
    assert discovery["categories"]["users"]
    assert discovery["categories"]["pain_points"]
    assert discovery["categories"]["constraints"]
    assert discovery["categories"]["success_metrics"]
    assert discovery["categories"]["decision_makers"]
    assert discovery["roadmap_inputs"]


def test_stakeholder_discovery_infers_categories_from_notes():
    discovery = build_stakeholder_discovery(
        {
            "stakeholder_notes": "Goal is launch faster\nUser is client approver\nProblem is unclear scope\nBudget constraint is fixed\nSuccess metric is signed acceptance\nDecision maker is CEO"
        }
    )

    assert discovery["status"] == "ready_for_human_review"
    assert discovery["missing_categories"] == []
    assert discovery["categories"]["goals"]
    assert discovery["categories"]["success_metrics"]


def test_stakeholder_discovery_marks_missing_categories():
    discovery = build_stakeholder_discovery({})

    assert discovery["status"] == "needs_more_discovery"
    assert discovery["readiness_score"] < 80
    assert "goals" in discovery["missing_categories"]
    assert any("No stakeholder discovery notes" in item for item in discovery["unavailable"])
