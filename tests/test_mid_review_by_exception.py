from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from nico import mid_review_api
from nico.mid_review_by_exception import PACKET_VERSION, build_mid_review_packet
from nico.mid_review_api import mid_review_packet_response
from nico.storage import STORE


def _run_id() -> str:
    return f"midrun_review_{uuid4().hex[:12]}"


def _section(section_id: str, status: str, *, score=88, findings=None, evidence=None, missing=None, failed=None, conflicts=None, source="repository"):
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": score,
        "truth_status": status,
        "summary": f"Summary for {section_id}.",
        "evidence": evidence or [f"Evidence for {section_id}."],
        "findings": findings or [],
        "missing_evidence_sources": missing or [],
        "failed_evidence_tools": failed or [],
        "unavailable": [],
        "conflicts": conflicts or [],
        "source_classification": source,
    }


def _record(run_id: str) -> dict:
    sections = [
        _section("code_audit", "Verified"),
        _section("dependency_health", "Verified with limitations", missing=["dependency_scanners"]),
        _section("secrets_review", "Verified", findings=["Critical credential exposure requires remediation."]),
        _section("static_analysis", "Failed", failed=["semgrep"], missing=["static_scanners"]),
        _section("ci_cd", "Verified with limitations", conflicts=["Workflow configuration requires tests but runtime evidence is incomplete."], missing=["ci_runtime"]),
        _section("functional_qa", "Human review required", score=None, evidence=["User submitted field: application_url"], source="user_submitted_external_context"),
        _section("platform_parity", "Unavailable", score=None, evidence=[], missing=["ios_build_access", "android_build_access"]),
    ]
    truth = {
        "version": "mid-truth-status-v1",
        "sections": sections,
        "summary": {
            "section_count": len(sections),
            "verified": 2,
            "verified_with_limitations": 2,
            "unavailable": 1,
            "failed": 1,
            "human_review_required": 1,
            "items_requiring_review": 5,
            "unavailable_evidence_sources": 6,
            "unsupported_claims_permitted": 0,
        },
        "unsupported_claims_permitted": 0,
        "evidence_coverage": {
            "label": "Automated evidence coverage",
            "calculated": True,
            "percent": 75,
            "numerator": 9,
            "denominator": 12,
            "units": [
                {"id": "repository_snapshot", "label": "Exact repository snapshot", "available": True, "status": "Verified", "evidence": "snapshot attached", "limitation": ""},
                {"id": "activity_history", "label": "Activity history", "available": False, "status": "Unavailable", "evidence": "", "limitation": "Activity history unavailable."},
                {"id": "static_scanners", "label": "Static scanners", "available": False, "status": "Unavailable", "evidence": "", "limitation": "Semgrep failed."},
            ],
        },
    }
    return {
        "run_id": run_id,
        "customer_id": "customer_review",
        "project_id": "project_review",
        "workflow": "mid_assessment",
        "service_tier": "mid",
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "snapshot_id": f"snapshot_{run_id}",
        "snapshot_commit_sha": "a" * 40,
        "request": {"mode": "mid"},
        "response": {
            "status": "complete",
            "run_id": run_id,
            "repository": "BoneManTGRM/NICO",
            "mid_truth_status": truth,
            "evidence_coverage": truth["evidence_coverage"],
            "scanner_evidence": {"status": "attached", "failed_tools": ["semgrep"]},
            "optional_evidence": {"status": "submitted"},
            "assessment": {"sections": sections},
            "export_truth_gate": {"status": "review_required", "blockers": ["Static scanner evidence failed."]},
        },
    }


@pytest.fixture(autouse=True)
def admin_token(monkeypatch):
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "test-admin-token")


def _put(run_id: str) -> None:
    STORE.put("assessment_runs", run_id, _record(run_id))


def test_review_packet_requires_admin_authentication():
    run_id = _run_id()
    _put(run_id)

    result = build_mid_review_packet(run_id, "customer_review", "project_review", admin_token="wrong")

    assert result["status"] == "blocked"
    assert result["admin_write"]["configured"] is True
    assert "Admin authentication" in result["error"]


def test_review_packet_is_exact_scope_and_hides_cross_scope_runs():
    run_id = _run_id()
    _put(run_id)

    wrong_customer = build_mid_review_packet(run_id, "wrong", "project_review", admin_token="test-admin-token")
    wrong_project = build_mid_review_packet(run_id, "customer_review", "wrong", admin_token="test-admin-token")

    assert wrong_customer["status"] == "not_found"
    assert wrong_project["status"] == "not_found"
    assert "snapshot" not in repr(wrong_customer).lower()


def test_packet_contains_only_clean_verified_sections_in_collapsed_list():
    run_id = _run_id()
    _put(run_id)

    packet = build_mid_review_packet(run_id, "customer_review", "project_review", admin_token="test-admin-token")

    assert packet["status"] == "ready_for_review"
    assert packet["packet_version"] == PACKET_VERSION
    verified_ids = {item["section_id"] for item in packet["verified_sections"]}
    assert verified_ids == {"code_audit"}
    assert packet["verified_sections"][0]["collapsed_by_default"] is True
    assert packet["verified_sections"][0]["evidence_count"] == 1
    assert "secrets_review" not in verified_ids


def test_packet_surfaces_every_required_exception_category():
    run_id = _run_id()
    _put(run_id)

    packet = build_mid_review_packet(run_id, "customer_review", "project_review", admin_token="test-admin-token")
    categories = {item["category"] for item in packet["exceptions"]}

    assert "critical_or_high_risk_finding" in categories
    assert "conflicting_evidence" in categories
    assert "low_confidence_or_limited_conclusion" in categories
    assert "incomplete_tool_execution" in categories
    assert "score_changing_claim" in categories
    assert "missing_evidence_affecting_delivery" in categories
    assert "inference_or_external_context" in categories
    assert packet["summary"]["critical_items"] >= 1
    assert packet["summary"]["high_items"] >= 1
    assert packet["summary"]["inference_items"] >= 1
    assert packet["summary"]["score_changing_items"] >= 1
    assert packet["summary"]["unsupported_claims_permitted"] == 0


def test_failed_tools_are_not_converted_to_clean_or_low_risk_results():
    run_id = _run_id()
    _put(run_id)

    packet = build_mid_review_packet(run_id, "customer_review", "project_review", admin_token="test-admin-token")
    static_items = [item for item in packet["exceptions"] if item["section_id"] == "static_analysis"]

    assert static_items
    incomplete = next(item for item in static_items if item["category"] == "incomplete_tool_execution")
    assert incomplete["severity"] == "high"
    assert "semgrep" in incomplete["blockers"]
    assert incomplete["score_change_material"] is True
    assert incomplete["requires_human_review"] is True


def test_external_context_remains_inference_based_and_cannot_be_auto_approved():
    run_id = _run_id()
    _put(run_id)

    packet = build_mid_review_packet(run_id, "customer_review", "project_review", admin_token="test-admin-token")
    item = next(item for item in packet["exceptions"] if item["section_id"] == "functional_qa")

    assert item["category"] == "inference_or_external_context"
    assert item["inference_based"] is True
    assert item["requires_human_review"] is True
    assert packet["human_approval_required"] is True
    assert packet["approval_controls_available"] is False
    assert "exact Mid draft report" in packet["approval_controls_note"]


def test_packet_identity_is_deterministic_for_unchanged_source_state():
    run_id = _run_id()
    _put(run_id)

    first = build_mid_review_packet(run_id, "customer_review", "project_review", admin_token="test-admin-token")
    second = build_mid_review_packet(run_id, "customer_review", "project_review", admin_token="test-admin-token")

    assert first["review_packet_id"] == second["review_packet_id"]
    assert first["review_packet_sha256"] == second["review_packet_sha256"]
    assert first["source_identity"] == second["source_identity"]
    assert first["exceptions"] == second["exceptions"]
    stored = STORE.get("evidence_items", first["review_packet_id"])
    assert stored["evidence"]["review_packet_sha256"] == first["review_packet_sha256"]
    assert stored["run_id"] == run_id


def test_source_change_changes_packet_hash_and_identity():
    run_id = _run_id()
    _put(run_id)
    first = build_mid_review_packet(run_id, "customer_review", "project_review", admin_token="test-admin-token")
    record = STORE.get("assessment_runs", run_id)
    record["response"]["mid_truth_status"]["sections"][0]["summary"] = "Changed evidence-bound summary."
    STORE.put("assessment_runs", run_id, record)

    second = build_mid_review_packet(run_id, "customer_review", "project_review", admin_token="test-admin-token")

    assert first["review_packet_sha256"] != second["review_packet_sha256"]
    assert first["review_packet_id"] != second["review_packet_id"]


def test_api_returns_packet_and_uses_generic_auth_and_not_found_errors():
    run_id = _run_id()
    _put(run_id)

    response = mid_review_packet_response(run_id, "customer_review", "project_review", x_nico_admin_token="test-admin-token")
    assert response["status"] == "ready_for_review"

    with pytest.raises(HTTPException) as unauthorized:
        mid_review_packet_response(run_id, "customer_review", "project_review", x_nico_admin_token="wrong")
    with pytest.raises(HTTPException) as missing:
        mid_review_packet_response(run_id, "wrong", "project_review", x_nico_admin_token="test-admin-token")
    assert unauthorized.value.status_code == 403
    assert missing.value.status_code == 404
    assert missing.value.detail["message"] == "Mid Assessment run not found."
