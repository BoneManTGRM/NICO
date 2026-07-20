from __future__ import annotations

from nico.service_catalog import build_service_intake_readiness, get_service_catalog_item, list_service_catalog


def _comprehensive_payload(**overrides):
    payload = {
        "workflow": "comprehensive",
        "repository": "BoneManTGRM/NICO",
        "authorized": True,
        "authorized_by": "reviewer",
        "authorization_scope": "repository assessment only",
        "qa_evidence": "PASS iOS login works",
        "parity_notes": "iOS and Android labels match",
        "stakeholder_notes": "Goal is launch faster",
        "roadmap_notes": "Month 1 QA stabilization",
        "known_risks": "No known launch blocker",
    }
    payload.update(overrides)
    return payload


def test_service_catalog_lists_only_two_customer_assessments():
    catalog = list_service_catalog()

    assert catalog["artifact_schema"] == "nico.service_catalog.v2"
    assert catalog["status"] == "ok"
    assert set(catalog["services"]) == {"express", "comprehensive"}
    assert catalog["customer_assessment_count"] == 2
    assert "mid" not in catalog["services"]
    assert "full" not in catalog["services"]
    assert "retainer" not in catalog["services"]
    assert catalog["services"]["comprehensive"]["deliverables"][0] == "everything included in Express"
    assert "monitor_execute" in catalog["recurring_services"]


def test_service_catalog_item_normalizes_internal_aliases_without_exposing_them_as_products():
    item = get_service_catalog_item("mid")

    assert item["status"] == "ok"
    assert item["workflow"] == "comprehensive"
    assert item["requested_workflow"] == "mid"
    assert item["internal_execution_profile"] == "mid"
    assert item["legacy_alias_used"] is True
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


def test_service_intake_readiness_builds_ready_comprehensive_request():
    readiness = build_service_intake_readiness(_comprehensive_payload())

    assert readiness["recommended_workflow"] == "comprehensive"
    assert readiness["status"] == "ready_for_workflow_request"
    assert readiness["readiness_score"] == 100
    assert readiness["missing_fields"] == []
    assert readiness["service"]["deliverables"][0] == "everything included in Express"


def test_mid_full_and_deep_are_internal_aliases_for_comprehensive():
    for alias in ("mid", "full", "deep"):
        readiness = build_service_intake_readiness(_comprehensive_payload(workflow=alias))
        assert readiness["recommended_workflow"] == "comprehensive"
        assert readiness["internal_execution_profile"] == alias
        assert readiness["legacy_alias_used"] is True
