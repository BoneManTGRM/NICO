from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "scripts/phase1_structured_artifact_audit_v1.py"
MOBILE_PROOF = ROOT / "scripts/mobile_restart_live_acceptance_v1.py"
TWO_SERVICE_WORKFLOW = ROOT / ".github/workflows/two-service-production-acceptance.yml"
IOS_WORKFLOW = ROOT / ".github/workflows/ios-webkit-paint-proof.yml"
MOBILE_WORKFLOW = ROOT / ".github/workflows/mobile-restart-production-proof.yml"
MOBILE_CONCURRENCY = "group: nico-production-assessment-proof-${{ github.ref }}"
IOS_CONCURRENCY = "group: nico-production-ios-webkit-proof-${{ github.ref }}"
TWO_SERVICE_CONCURRENCY = "group: unified-production-acceptance-${{ github.ref }}"


def _load_audit_module() -> Any:
    spec = importlib.util.spec_from_file_location("phase1_structured_artifact_audit_v1", AUDIT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _synthetic_payload(module: Any) -> dict[str, Any]:
    commit_sha = "a" * 40
    record = {
        "candidate_id": "candidate-1",
        "category": "static",
        "scanner": "bandit",
        "tool": "bandit",
        "rule": "B101",
        "exact_commit_sha": commit_sha,
        "source_path": "nico/example.py",
        "line": 12,
        "technical_triage_status": "complete",
        "technical_triage_verdict": "needs_review",
        "technical_triage_confidence": "medium",
        "technical_triage_rationale": "Executable context requires authorized human review.",
        "technical_triage_rationale_code": "insufficient_context",
        "technical_triage_source": "fresh_deterministic_context",
        "technical_triage_model_or_version": "test.v1",
        "technical_triage_boundary_assessment": "first_party_source",
        "technical_triage_proof_gaps": ["manual_source_review"],
        "technical_triage_recommended_next_step": "Review the exact source context.",
        "lineage_status": "newly_observed",
        "evidence_changed": False,
        "review_routing_class": "HUMAN_TECHNICAL_REVIEW",
        "grouped_review_eligible": False,
        "review_requires_individual_attention": True,
        "human_approval_status": "pending",
        "human_review_required": True,
        "human_approval_carried_forward": False,
        "technical_triage_client_delivery_allowed": False,
        "human_disposition": "",
        "reviewer_identity": "",
        "evidence_digest_sha256": "b" * 64,
        "raw_fingerprint": "c" * 64,
        "proof_gaps": ["manual_source_review"],
        "cluster_id": "cluster-1",
        "cluster_candidate_ids": ["candidate-1"],
        "cluster_size": 1,
        "representative_candidate_id": "candidate-1",
        "homogeneous_evidence": True,
        "homogeneous_verdict": True,
    }
    register = {
        "candidate_record_count": 1,
        "count_parity_verified": True,
        "mutually_exclusive_dispositions_verified": True,
        "findings": [record],
        "technical_triage": {
            "human_disposition_created": False,
            "human_approval_status": "pending",
            "client_delivery_allowed": False,
            "not_actionable_count": 0,
            "needs_review_count": 1,
            "confirmed_count": 0,
            "human_review_work_units": 1,
            "candidates_requiring_individual_human_attention": 1,
            "candidates_eligible_for_grouped_review": 0,
            "quality_control_sample_pool": 0,
        },
        "candidate_retained_triage_revalidation": {
            "artifact_schema": "nico.candidate-retained-triage-revalidation.v1",
            "status": "complete",
            "revalidated_candidate_count": 0,
            "revalidated_candidate_ids": [],
            "current_contract": "unresolved_dependency_reachability_requires_explicit_proof_gap_or_fresh_determination",
            "candidate_counts_changed": False,
            "scanner_evidence_changed": False,
            "canonical_dispositions_changed": False,
            "human_disposition_created": False,
            "reviewer_identity_created": False,
            "human_approval_created": False,
            "client_delivery_allowed": False,
            "score_effect": "none",
        },
        "candidate_review_workload_refinement": {
            "candidate_counts_changed": False,
            "canonical_dispositions_changed": False,
            "technical_verdicts_changed": False,
            "score_effect": "none",
            "human_disposition_created": False,
            "human_approval_created": False,
            "risk_acceptance_created": False,
        },
    }
    register_bytes = module._canonical_bytes(register)
    identity = {
        "run_id": "comprun_test",
        "commit_sha": commit_sha,
        "repository": "example/repository",
        "customer_id": "customer",
        "project_id": "project",
        "evidence_ledger_id": "ledger",
    }
    return {
        "identity": identity,
        "assessment": {"canonical_scanner_finding_register": register},
        "artifact_manifest": {
            "artifacts": [
                {
                    "artifact_type": "candidate_register_json",
                    "filename": "nico-comprun_test-candidate-register.json",
                    "run_id": identity["run_id"],
                    "commit_sha": identity["commit_sha"],
                    "repository": identity["repository"],
                    "customer_id": identity["customer_id"],
                    "project_id": identity["project_id"],
                    "evidence_ledger_id": identity["evidence_ledger_id"],
                    "sha256": module.hashlib.sha256(register_bytes).hexdigest(),
                    "size_bytes": len(register_bytes),
                }
            ]
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
        "approval_state": "pending",
        "review_package_ready": True,
    }


def test_production_assessment_proofs_serialize_without_pending_cancellation() -> None:
    ios = IOS_WORKFLOW.read_text(encoding="utf-8")
    mobile = MOBILE_WORKFLOW.read_text(encoding="utf-8")
    two_service = TWO_SERVICE_WORKFLOW.read_text(encoding="utf-8")
    ios_header = ios.split("\njobs:", 1)[0]
    mobile_header = mobile.split("\njobs:", 1)[0]

    assert IOS_CONCURRENCY in ios_header
    assert MOBILE_CONCURRENCY not in ios_header
    assert MOBILE_CONCURRENCY in mobile_header
    assert IOS_CONCURRENCY not in mobile_header
    assert MOBILE_CONCURRENCY not in two_service
    assert IOS_CONCURRENCY not in two_service
    assert TWO_SERVICE_CONCURRENCY in two_service
    assert all("cancel-in-progress: false" in source for source in (ios, mobile, two_service))

    assert "Wait for exact-SHA Mobile production proof" in ios
    assert "NICO Mobile Restart Production Proof" in ios
    assert "The exact-SHA Mobile production proof failed before WebKit proof" in ios
    assert ios.index("Wait for exact-SHA Mobile production proof") < ios.index(
        "Prove WebKit intake, bilingual failure layout, recovery, and review PDF download"
    )

    assert "Wait for serialized Mobile and iOS production proofs" in two_service
    assert "NICO Mobile Restart Production Proof" in two_service
    assert "NICO iOS WebKit Paint Proof" in two_service
    assert "A prerequisite production proof failed for the exact release" in two_service


def test_mobile_proof_waits_for_complete_terminal_report_ui() -> None:
    source = MOBILE_PROOF.read_text(encoding="utf-8")
    assert "def _terminal_ui_ready(" in source
    assert "def _wait_for_terminal_ui_ready(" in source
    assert "Terminal phase did not converge to the complete exact-run report UI" in source
    assert 'state.get("markdown_enabled") == "true"' in source
    assert 'state.get("pdf_enabled") == "true"' in source
    assert "terminal_before_reload = _wait_for_terminal_ui_ready" in source
    assert "terminal_after_reload = _wait_for_terminal_ui_ready" in source


def test_two_service_acceptance_requires_structured_phase1_audit() -> None:
    source = TWO_SERVICE_WORKFLOW.read_text(encoding="utf-8")
    assert "Audit Phase 1 structured candidate artifacts" in source
    assert "scripts/phase1_structured_artifact_audit_v1.py" in source
    assert "pass-2-comprehensive.json" in source
    assert "audit-results/phase1-structured-artifact-audit.json" in source
    assert 'test "${{ steps.phase1_audit.outcome }}" = "success"' in source
    assert 'audit["candidate_register_sha256_expected"] == audit["candidate_register_sha256_observed"]' in source
    assert 'audit["client_delivery_allowed"] is False' in source


def test_structured_artifact_audit_accepts_complete_exact_run_contract() -> None:
    module = _load_audit_module()
    payload = _synthetic_payload(module)
    result = module.audit(payload, expected_sha="a" * 40)
    assert result["status"] == "passed"
    assert result["candidate_count"] == 1
    assert result["human_review_work_units"] == 1
    assert result["client_delivery_allowed"] is False
    assert result["errors"] == []


def test_structured_artifact_audit_rejects_automated_human_disposition() -> None:
    module = _load_audit_module()
    payload = _synthetic_payload(module)
    payload["assessment"]["canonical_scanner_finding_register"]["findings"][0]["human_disposition"] = "accepted"
    result = module.audit(payload, expected_sha="a" * 40)
    assert result["status"] == "failed"
    assert any("automation_created_human_disposition" in item for item in result["errors"])
