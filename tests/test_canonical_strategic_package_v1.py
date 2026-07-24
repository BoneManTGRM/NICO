from __future__ import annotations

import json

from nico.canonical_express_binding_v1 import _canonical_core_response
from nico.canonical_strategic_package_v1 import (
    ARTIFACT_DEFINITIONS,
    STRATEGIC_MODULES,
    TECHNICAL_MODULES,
    attach_canonical_strategic_package,
    build_canonical_run_manifest,
    build_code_remediation_plan,
    validate_final_accepted_package,
)


def _section(
    section_id: str,
    score: int | None,
    *,
    assurance: str = "VERIFIED",
    risk: str = "GREEN",
) -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "presented_score": score,
        "score_band_label": "STRONG" if score is not None and score >= 80 else "NOT SCORED",
        "assurance_label": assurance,
        "risk_disposition": risk,
        "evidence": [f"Exact evidence for {section_id}"],
        "findings": [],
        "unavailable": [],
    }


def _payload(*, depth: str = "strategic") -> dict:
    sections = [
        _section("code_audit", 86),
        _section("dependency_health", 90),
        _section("secrets_review", 84, assurance="REVIEW LIMITED", risk="YELLOW"),
        _section("static_analysis", 82),
        _section("ci_cd", 80),
        _section("architecture_debt", 78, assurance="REVIEW LIMITED", risk="YELLOW"),
        _section("velocity_complexity", 84),
    ]
    finding = {
        "id": "architecture-assessment-workspace",
        "priority": "P1",
        "category": "architecture",
        "title": "AssessmentWorkspace contains concentrated lifecycle complexity",
        "impact": "A change to polling or report actions can regress unrelated assessment behavior.",
        "confidence": "high",
        "evidence": "Measured cyclomatic complexity exceeds the approved threshold.",
        "location": "apps/web/app/assessment/AssessmentWorkspace.tsx:180",
        "recommendation": "Extract request, polling, terminal-state, report-action, and localization responsibilities into tested modules.",
        "effort": "L",
        "owner_role": "Product Engineering Architect",
        "acceptance_criteria": "The component delegates bounded responsibilities and the full assessment regression suite passes.",
    }
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "run_id": "assessment_run_canonical_contract",
        "customer_id": "customer_canonical",
        "project_id": "project_canonical",
        "assessment_type": depth,
        "service_tier": depth,
        "report_language": "en",
        "repository_snapshot": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "tree_sha": "b" * 40,
        },
        "scanner": {
            "status": "complete",
            "scan_id": "scan_canonical_contract",
            "snapshot_match": True,
            "normalized_fingerprint": "c" * 64,
            "repeatability_status": "verified",
        },
        "assessment": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "assessment_run_canonical_contract",
            "sections": sections,
            "findings_register": [finding],
            "executive_risk_register": [],
        },
        "reports": {
            "markdown": "# NICO\n" + "Evidence-bound report. " * 40,
            "html": "<html><body>" + "<p>Evidence-bound report.</p>" * 40 + "</body></html>",
            "pdf_base64": "JVBERi0xLjQK" + "A" * 200,
            "pdf_sha256": "d" * 64,
        },
        "evidence_artifact_bundle": {"bundle_hash": "e" * 64},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_canonical_manifest_uses_one_identity_and_separates_score_assurance_and_risk() -> None:
    manifest = build_canonical_run_manifest(_payload(), depth="strategic")

    assert manifest["status"] == "complete"
    assert manifest["identity"]["repository"] == "BoneManTGRM/NICO"
    assert manifest["identity"]["commit_sha"] == "a" * 40
    assert manifest["identity"]["tree_sha"] == "b" * 40
    assert manifest["identity"]["scanner_run_id"] == "scan_canonical_contract"
    assert manifest["identity"]["scanner_repeatability"] == "verified"
    assert manifest["one_canonical_run_required"] is True
    assert manifest["independent_core_and_strategic_scorecards_allowed"] is False

    secrets = next(item for item in manifest["canonical_score_and_assurance_ledger"] if item["control_id"] == "secrets_review")
    assert secrets["technical_score"] == 84
    assert secrets["technical_band"] == "STRONG"
    assert secrets["evidence_assurance"] == "REVIEW LIMITED"
    assert secrets["risk_disposition"] == "YELLOW"


def test_remediation_plan_is_code_specific_but_never_claims_an_unreviewed_patch() -> None:
    plan = build_code_remediation_plan(_payload())

    assert plan["status"] == "complete"
    assert plan["automatic_code_change_performed"] is False
    assert plan["remediation_item_count"] == 1
    item = plan["items"][0]
    assert item["finding_id"] == "architecture-assessment-workspace"
    assert item["exact_location"] == "apps/web/app/assessment/AssessmentWorkspace.tsx:180"
    assert item["affected_files"] == ["apps/web/app/assessment/AssessmentWorkspace.tsx"]
    assert item["recommended_change"].startswith("Extract request, polling")
    assert item["proposed_diff"] == ""
    assert item["proposed_diff_status"] == "requires_exact_source_review"
    assert item["requires_human_engineering_review"] is True
    assert item["auto_patch_eligible"] is False
    assert item["verification_tests"]
    assert item["rollback_plan"]
    assert item["exit_criteria"]


def test_strategic_package_exports_decision_grade_machine_readable_artifacts() -> None:
    package = attach_canonical_strategic_package(_payload(), depth="strategic")

    assert package["canonical_package_contract"]["status"] == "complete"
    assert package["canonical_package_contract"]["automatic_approval"] is False
    assert package["canonical_package_contract"]["proposed_code_changes_are_review_only"] is True
    assert package["code_remediation_plan"]["remediation_item_count"] == 1
    assert package["risk_register"]
    assert len(package["premium_artifact_manifest"]) == len(ARTIFACT_DEFINITIONS)

    reports = package["reports"]
    assert "architecture-assessment-workspace" in reports["remediation_backlog_csv"]
    assert "risk_id" in reports["risk_register_csv"]
    assert json.loads(reports["findings_register_json"])[0]["id"] == "architecture-assessment-workspace"
    assert json.loads(reports["score_assurance_ledger_json"])[0]["control_id"] == "code_audit"
    assert json.loads(reports["evidence_manifest_json"])["raw_secret_material_included"] is False


def test_core_and_strategic_share_the_same_contract_and_core_does_not_fake_human_modules() -> None:
    core_payload = _payload(depth="core")
    core = _canonical_core_response(core_payload["run_id"], core_payload, core_payload)

    assert core["canonical_core_contract"]["same_contract_used_by_strategic"] is True
    assert core["canonical_core_contract"]["independent_core_scorecard_allowed"] is False
    assert core["canonical_run_manifest"]["identity"]["assessment_depth"] == "core"
    statuses = {item["module_id"]: item["status"] for item in core["canonical_run_manifest"]["module_status"]}
    human_evidence_modules = {
        "functional_qa",
        "platform_parity",
        "accessibility_ux",
        "stakeholder_context",
        "decision_log",
    }
    for module_id in human_evidence_modules:
        assert statuses[module_id] == "not_in_core_scope"
    assert statuses["business_consequences"] == "complete"


def test_final_accepted_gate_blocks_missing_strategic_human_evidence_and_named_approval() -> None:
    package = attach_canonical_strategic_package(_payload(), depth="strategic")
    gate = validate_final_accepted_package(package)

    assert gate["status"] == "blocked"
    assert gate["final_accepted_allowed"] is False
    assert any(item.startswith("strategic_modules_not_assessed:") for item in gate["blockers"])
    assert "named_human_approval_missing" in gate["blockers"]
    assert "named_reviewer_missing" in gate["blockers"]
    assert gate["human_review_required"] is True


def test_contract_defines_all_required_module_families() -> None:
    assert len(TECHNICAL_MODULES) >= 13
    assert len(STRATEGIC_MODULES) >= 12
    assert len(ARTIFACT_DEFINITIONS) >= 16
