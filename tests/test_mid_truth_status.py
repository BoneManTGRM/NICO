from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from nico.mid_assessment_runs import load_mid_assessment_run, persist_mid_assessment_run
from nico.mid_truth_status import (
    ALLOWED_SECTION_STATUSES,
    FAILED,
    HUMAN_REVIEW_REQUIRED,
    UNAVAILABLE,
    VERIFIED,
    VERIFIED_WITH_LIMITATIONS,
    attach_mid_truth_status,
    build_mid_evidence_coverage,
    build_mid_truth_status,
)


def _section(section_id: str, *, unavailable: list[str] | None = None) -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": 88,
        "status": "green",
        "summary": "Evidence-bound section summary.",
        "evidence": [f"Direct evidence for {section_id}."],
        "verified_claims": [f"Direct evidence for {section_id}."],
        "findings": [],
        "unavailable": unavailable or [],
        "unverified_claims": unavailable or [],
        "confidence": "standard",
    }


def _result() -> dict:
    run_id = f"midrun_truth_{uuid4().hex[:10]}"
    tools = ["pip-audit", "gitleaks", "semgrep"]
    return {
        "status": "complete",
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_truth",
        "project_id": "project_truth",
        "repository_snapshot": {
            "status": "attached",
            "snapshot_id": f"snapshot_{run_id}",
            "commit_sha": "a" * 40,
            "tree_sha": "b" * 40,
        },
        "repository_evidence": {
            "status": "attached",
            "snapshot_commit_sha": "a" * 40,
            "file_evidence": {"files_profiled": 25},
            "dependency_evidence": {"manifest_paths": ["requirements.txt"], "dependency_entries": 8},
            "workflow_evidence": {
                "workflow_file_count": 2,
                "workflow_configuration_snapshot_sha": "a" * 40,
                "jobs_observed": 5,
                "deployments_observed": 1,
            },
            "activity_evidence": {"commits_returned": 12, "pull_requests_returned": 4},
        },
        "complexity_evidence": {
            "status": "attached",
            "files_analyzed": 20,
            "snapshot_commit_sha": "a" * 40,
        },
        "scanner_evidence": {
            "status": "attached",
            "scan_id": f"scan_{run_id}",
            "snapshot_match": True,
            "tools_run": tools,
            "failed_tools": [],
            "timed_out_tools": [],
            "unavailable_tools": [],
        },
        "optional_evidence": {
            "status": "not_submitted",
            "section_availability": {
                "functional_qa": {"section": "Functional QA", "status": "unavailable", "submitted_fields": [], "message": "Functional QA evidence unavailable."},
                "platform_parity": {"section": "Platform parity", "status": "unavailable", "submitted_fields": [], "message": "Platform evidence unavailable."},
                "architecture_context": {"section": "Architecture context", "status": "unavailable", "submitted_fields": [], "message": "External architecture context unavailable."},
                "stakeholder_alignment": {"section": "Stakeholder alignment", "status": "unavailable", "submitted_fields": [], "message": "Stakeholder evidence unavailable."},
                "business_roadmap": {"section": "Business-aligned roadmap", "status": "unavailable", "submitted_fields": [], "message": "Business context unavailable."},
            },
        },
        "assessment": {
            "status": "draft",
            "maturity_signal": {"level": "Senior", "score": 95},
            "sections": [
                _section("code_audit"),
                _section("dependency_health"),
                _section("secrets_review"),
                _section("static_analysis"),
                _section("ci_cd"),
                _section("architecture_debt"),
                _section("velocity_complexity"),
            ],
            "evidence_ledger": {
                "status": "available",
                "entry_count": 15,
                "verified_entry_count": 15,
                "unavailable_entry_count": 0,
            },
        },
        "reports": {"pdf_base64": ""},
    }


def test_coverage_uses_twelve_explicit_evidence_units_not_maturity_score():
    result = _result()
    coverage = build_mid_evidence_coverage(result)

    assert coverage["calculated"] is True
    assert coverage["label"] == "Automated evidence coverage"
    assert coverage["numerator"] == 12
    assert coverage["denominator"] == 12
    assert coverage["percent"] == 100
    assert len(coverage["units"]) == 12
    assert "Maturity scores do not affect coverage" in coverage["method"]

    changed = deepcopy(result)
    changed["assessment"]["maturity_signal"]["score"] = 1
    assert build_mid_evidence_coverage(changed)["percent"] == coverage["percent"]


def test_missing_scanner_units_reduce_measured_coverage_without_claiming_clean_results():
    result = _result()
    result["scanner_evidence"].update({
        "status": "not_attached",
        "snapshot_match": False,
        "tools_run": [],
        "unavailable_tools": ["pip-audit", "gitleaks", "semgrep"],
    })
    coverage = build_mid_evidence_coverage(result)
    by_id = {unit["id"]: unit for unit in coverage["units"]}

    assert coverage["numerator"] == 8
    assert coverage["percent"] == 67
    assert by_id["snapshot_scanner_match"]["status"] == UNAVAILABLE
    assert by_id["dependency_scanners"]["status"] == UNAVAILABLE
    assert by_id["secret_scanners"]["status"] == UNAVAILABLE
    assert by_id["static_scanners"]["status"] == UNAVAILABLE
    assert "unavailable" in by_id["secret_scanners"]["limitation"].lower()


def test_all_report_sections_receive_one_allowed_truth_status():
    truth = build_mid_truth_status(_result())

    assert len(truth["sections"]) == 12
    assert all(item["truth_status"] in ALLOWED_SECTION_STATUSES for item in truth["sections"])
    technical = {item["id"]: item for item in truth["sections"][:7]}
    assert technical["code_audit"]["truth_status"] == VERIFIED
    assert technical["dependency_health"]["truth_status"] == VERIFIED
    assert technical["secrets_review"]["truth_status"] == VERIFIED
    assert technical["static_analysis"]["truth_status"] == VERIFIED
    external = {item["id"]: item for item in truth["sections"][7:]}
    assert all(item["truth_status"] == UNAVAILABLE for item in external.values())
    assert truth["summary"]["unsupported_claims_permitted"] == 0
    assert truth["unsupported_claims_permitted"] == 0


def test_missing_secondary_evidence_becomes_verified_with_limitations():
    result = _result()
    result["repository_evidence"]["activity_evidence"] = {"commits_returned": 0, "pull_requests_returned": 0}
    result["repository_evidence"]["workflow_evidence"].update({"jobs_observed": 0, "deployments_observed": 0})
    truth = build_mid_truth_status(result)
    by_id = {item["id"]: item for item in truth["sections"]}

    assert by_id["code_audit"]["truth_status"] == VERIFIED_WITH_LIMITATIONS
    assert by_id["ci_cd"]["truth_status"] == VERIFIED_WITH_LIMITATIONS
    assert by_id["velocity_complexity"]["truth_status"] == UNAVAILABLE
    assert "activity_history" in by_id["code_audit"]["missing_evidence_sources"]
    assert "ci_runtime" in by_id["ci_cd"]["missing_evidence_sources"]


def test_failed_required_scanner_is_failed_not_zero_findings():
    result = _result()
    result["scanner_evidence"].update({
        "tools_run": ["pip-audit", "gitleaks"],
        "failed_tools": ["semgrep"],
    })
    truth = build_mid_truth_status(result)
    by_id = {item["id"]: item for item in truth["sections"]}

    assert by_id["static_analysis"]["truth_status"] == FAILED
    assert by_id["static_analysis"]["failed_evidence_tools"] == ["semgrep"]
    assert by_id["static_analysis"]["human_review_required"] is True
    assert by_id["static_analysis"]["unsupported_claims_permitted"] is False


def test_submitted_external_context_is_human_review_required_not_verified():
    result = _result()
    result["optional_evidence"] = {
        "status": "submitted",
        "section_availability": {
            "functional_qa": {"section": "Functional QA", "submitted_fields": ["application_url"], "message": "User context submitted."},
            "platform_parity": {"section": "Platform parity", "submitted_fields": ["ios_build_access"], "message": "One platform submitted."},
            "stakeholder_alignment": {"section": "Stakeholder alignment", "submitted_fields": ["meeting_transcripts"], "message": "Transcript context submitted."},
            "business_roadmap": {"section": "Business-aligned roadmap", "submitted_fields": ["business_priorities"], "message": "Business context submitted."},
        },
    }
    truth = build_mid_truth_status(result)
    external = {item["id"]: item for item in truth["sections"] if item["id"] in result["optional_evidence"]["section_availability"]}

    assert all(item["truth_status"] == HUMAN_REVIEW_REQUIRED for item in external.values())
    assert all(item["direct_repository_proof"] is False for item in external.values())
    assert all(item["score_change_allowed_without_review"] is False for item in external.values())
    assert truth["summary"]["human_review_required"] == 4


def test_attach_updates_assessment_sections_coverage_and_review_summary():
    result = _result()
    attached = attach_mid_truth_status(result)

    assert attached["mid_truth_status"]["version"] == "mid-truth-status-v1"
    assert attached["evidence_coverage"]["percent"] == 100
    assert attached["assessment"]["evidence_coverage"]["percent"] == 100
    assert attached["assessment"]["unsupported_claims_permitted"] == 0
    assert all("truth_status" in section for section in attached["assessment"]["sections"])
    assert attached["review_summary"]["unsupported_claims_permitted"] == 0
    assert attached["review_summary"]["sections_verified"] == 7


def test_persisted_mid_run_retains_truth_status_but_not_optional_capability_token():
    result = _result()
    run_id = result["run_id"]
    persist_mid_assessment_run(
        result,
        {
            "run_id": run_id,
            "repository": result["repository"],
            "customer_id": result["customer_id"],
            "project_id": result["project_id"],
            "authorized": True,
            "authorization_confirmed": True,
            "mode": "mid",
            "build_reports": False,
            "create_final_review_request": False,
        },
    )

    token = result["optional_evidence_submission"]["token"]
    stored = load_mid_assessment_run(run_id)
    assert stored is not None
    assert stored["response"]["mid_truth_status"]["version"] == "mid-truth-status-v1"
    assert stored["response"]["evidence_coverage"]["calculated"] is True
    assert "optional_evidence_submission" not in stored["response"]
    assert token not in repr(stored)
