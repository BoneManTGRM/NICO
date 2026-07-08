from __future__ import annotations

from nico.service_catalog import build_service_intake_readiness, get_service_catalog_item, list_service_catalog


def test_service_catalog_lists_core_workflows():
    catalog = list_service_catalog()

    assert catalog["artifact_schema"] == "nico.service_catalog.v1"
    assert catalog["status"] == "ok"
    assert set(catalog["services"]) == {"express", "mid", "retainer"}
    assert catalog["services"]["express"]["workflow_endpoint"] == "POST /assessment/github"
    assert catalog["services"]["mid"]["target_coverage"] == "75-85%"
    assert catalog["services"]["retainer"]["deliverables"]


def test_service_catalog_item_returns_required_fields():
    item = get_service_catalog_item("mid")

    assert item["status"] == "ok"
    assert item["workflow"] == "mid"
    assert "qa_evidence" in item["required_fields"]
    assert "stakeholder_notes" in item["required_fields"]


def test_service_intake_readiness_blocks_express_without_authorization():
    readiness = build_service_intake_readiness(
        {
            "workflow": "express",
            "repository": "BoneManTGRM/NICO",
            "authorized": False,
            "scanner_worker_artifact": {"status": "complete"},
        }
    )

    assert readiness["recommended_workflow"] == "express"
    assert readiness["status"] == "blocked_missing_authorization"
    assert readiness["blockers"]
    assert "authorized" in readiness["missing_fields"]


def test_service_intake_readiness_recommends_mid_from_qa_and_discovery():
    readiness = build_service_intake_readiness(
        {
            "qa_evidence": "PASS iOS login works",
            "parity_notes": "iOS and Android labels match",
            "stakeholder_notes": "Goal is launch faster",
            "roadmap_notes": "Month 1 QA stabilization",
            "known_risks": "No known launch blocker",
        }
    )

    assert readiness["recommended_workflow"] == "mid"
    assert readiness["status"] == "ready_for_workflow_request"
    assert readiness["readiness_score"] == 100
    assert readiness["missing_fields"] == []


def test_service_intake_readiness_recommends_retainer_and_tracks_missing_fields():
    readiness = build_service_intake_readiness(
        {
            "commit_summary": "Fixed report export path",
            "pr_summary": "Opened retainer module PR",
            "issue_summary": "Client wants weekly status",
        }
    )

    assert readiness["recommended_workflow"] == "retainer"
    assert readiness["status"] == "needs_more_intake_evidence"
    assert "release_notes" in readiness["missing_fields"]
    assert "blockers" in readiness["missing_fields"]
    assert readiness["next_action"].startswith("Collect missing intake fields")
