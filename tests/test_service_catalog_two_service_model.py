from nico.service_catalog import (
    build_service_intake_readiness,
    get_service_catalog_item,
    list_service_catalog,
    normalize_service_id,
)


def test_customer_catalog_exposes_exactly_two_assessment_services() -> None:
    catalog = list_service_catalog()
    assert catalog["customer_assessment_count"] == 2
    assert set(catalog["assessment_services"]) == {"express", "comprehensive"}
    assert set(catalog["services"]) == {"express", "comprehensive"}
    assert "monitor_execute" not in catalog["services"]
    assert catalog["recurring_services"]["monitor_execute"]["category"] == "recurring_operations"
    assert catalog["recurring_services"]["monitor_execute"]["customer_selectable"] is False


def test_mid_full_and_deep_are_comprehensive_compatibility_aliases() -> None:
    for alias in ("mid", "full", "deep"):
        assert normalize_service_id(alias) == "comprehensive"
        item = get_service_catalog_item(alias)
        assert item["workflow"] == "comprehensive"
        assert item["requested_workflow"] == alias
        assert item["legacy_alias_used"] is True
        assert item["internal_execution_profile"] == alias
        assert item["service"]["label"] == "NICO Comprehensive Technical Assessment"


def test_retainer_is_recurring_monitor_execute_alias() -> None:
    item = get_service_catalog_item("retainer")
    assert item["workflow"] == "monitor_execute"
    assert item["internal_execution_profile"] == "retainer"
    assert item["service"]["customer_selectable"] is False


def test_comprehensive_intake_preserves_legacy_profile_and_requires_authorization() -> None:
    blocked = build_service_intake_readiness({"workflow": "full", "repository": "owner/repo", "authorized": False})
    assert blocked["recommended_workflow"] == "comprehensive"
    assert blocked["internal_execution_profile"] == "full"
    assert blocked["legacy_alias_used"] is True
    assert blocked["status"] == "blocked_missing_authorization"
    assert blocked["blockers"]


def test_comprehensive_ready_response_uses_existing_compatible_endpoint() -> None:
    payload = {
        "workflow": "comprehensive",
        "repository": "owner/repo",
        "authorized": True,
        "authorized_by": "reviewer",
        "authorization_scope": "repository assessment",
        "qa_evidence": "attached",
        "parity_notes": "not applicable",
        "stakeholder_notes": "attached",
        "roadmap_notes": "attached",
        "known_risks": "attached",
    }
    readiness = build_service_intake_readiness(payload)
    assert readiness["status"] == "ready_for_workflow_request"
    assert readiness["recommended_workflow"] == "comprehensive"
    assert readiness["service"]["workflow_endpoint"] == "POST /assessment/mid-run"
    assert readiness["human_review_required"] is True
