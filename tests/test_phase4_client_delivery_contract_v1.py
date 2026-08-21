from __future__ import annotations

import base64
import io
from copy import deepcopy

import pytest
from pypdf import PdfWriter

from nico.comprehensive_client_delivery_contract_v1 import (
    ClientDeliveryContractError,
    PRODUCT_NAME,
    artifact_digests,
    build_approval_receipt,
    canonical_sha256,
    operational_metrics,
    validate_approval_receipt,
    validate_full_lifecycle,
)


def _pdf() -> str:
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(buffer)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _record(ecosystem: str = "python") -> dict:
    run_id = f"comprun_phase4_{ecosystem}"
    repo = f"OutsideOrg/{ecosystem}-service"
    commit = {"python": "a", "node": "b", "mixed": "c"}[ecosystem] * 40
    project_id = f"project-{ecosystem}"
    client_id = f"client-{ecosystem}"
    candidate = {
        "candidate_id": f"candidate-{ecosystem}-1",
        "finding_id": f"finding-{ecosystem}-1",
        "cluster_id": f"cluster-{ecosystem}-1",
        "severity": "medium",
        "scanner": {"python": "bandit", "node": "semgrep", "mixed": "semgrep"}[ecosystem],
        "path": {"python": "src/app.py", "node": "src/app.ts", "mixed": "backend/app.py"}[ecosystem],
        "candidate_lineage_version": "nico.candidate_lineage.v1",
        "lineage": {"version": "nico.candidate_lineage.v1", "status": "newly_observed"},
        "technical_triage": {
            "version": "nico.technical_triage.v1",
            "verdict": "needs_review",
            "confidence": 0.91,
        },
        "review_requires_individual_attention": True,
        "grouped_review_eligible": False,
        "human_disposition": {
            "decision": "confirmed_material",
            "reviewer": "Alice Security",
            "reviewer_role": "Cybersecurity specialist",
        },
    }
    register = {
        "artifact_schema": "nico.canonical_scanner_finding_register.v1",
        "candidate_lineage_version": "nico.candidate_lineage.v1",
        "candidate_record_count": 1,
        "findings": [candidate],
        "technical_triage": {
            "version": "nico.technical_triage.v1",
            "total_candidates": 1,
            "triaged_candidates": 1,
        },
        "scanner_versions": {candidate["scanner"]: "fixture-1.0"},
    }
    canonical = {
        "product_name": PRODUCT_NAME,
        "identity": {
            "run_id": run_id,
            "repository": repo,
            "commit_sha": commit,
            "evidence_ledger_id": f"ledger-{ecosystem}",
        },
        "assessment": {"canonical_scanner_finding_register": register},
        "generator_versions": {
            "assessment_engine_version": "nico.engine.v1",
            "scoring_model_version": "nico.score.v1",
            "report_renderer_version": "nico.renderer.v1",
            "artifact_generation_version": "nico.artifacts.v1",
            "candidate_lineage_version": "nico.candidate_lineage.v1",
            "technical_triage_version": "nico.technical_triage.v1",
            "scanner_versions": register["scanner_versions"],
            "nico_backend_build_commit": "d" * 40,
            "frontend_build_commit": "e" * 40,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    package = {
        "artifact_schema": "nico.comprehensive_report.v1",
        "product_name": PRODUCT_NAME,
        "report_product": PRODUCT_NAME,
        "package_classification": "client_final",
        "markdown": f"# {PRODUCT_NAME}\n\nExact source: {candidate['path']}\n",
        "html": f"<html><body><h1>{PRODUCT_NAME}</h1></body></html>",
        "pdf_base64": _pdf(),
        "json": canonical,
        "findings_csv": "finding_id,path\n" + candidate["finding_id"] + "," + candidate["path"] + "\n",
        "evidence_csv": "evidence_id,source\nev-1,scanner\n",
        "jira_csv": "summary,verification\nFix fixture,Run exact test\n",
        "candidate_register_csv": "candidate_id,disposition\n" + candidate["candidate_id"] + ",confirmed_material\n",
    }
    required_scanner = candidate["scanner"]
    scope = {
        "customer_id": f"customer-{ecosystem}",
        "client_id": client_id,
        "project_id": project_id,
        "workspace_id": f"workspace-{ecosystem}",
        "tenant_id": f"tenant-{ecosystem}",
    }
    ledger = {
        "artifact_schema": "nico.comprehensive_review_work_ledger.v2",
        "run_id": run_id,
        "repository": repo,
        "commit_sha": commit,
        "evidence_ledger_id": f"ledger-{ecosystem}",
        "scope_binding": scope,
        "review_source_sha256": "f" * 64,
        "human_dispositions_pending": 0,
        "human_dispositions_completed": 1,
        "confirmed_material_findings": 1,
        "quality_control_sample_size": 1,
        "dispositions": {candidate["candidate_id"]: candidate["human_disposition"]},
        "audit_events": [
            {
                "sequence": 1,
                "action": "disposition_candidate",
                "reviewer": "Alice Security",
                "reviewer_role": "Cybersecurity specialist",
            }
        ],
        "operational_timing": {
            "assessment_runtime_seconds": 600,
            "automated_processing_duration_seconds": 540,
            "review_elapsed_minutes": 50,
            "review_active_minutes": 45,
            "estimated_combined_specialist_hours": 0.75,
        },
    }
    return {
        "artifact_schema": "nico.comprehensive_run.v1",
        "identity": {
            "run_id": run_id,
            "repository": repo,
            "commit_sha": commit,
            "evidence_ledger_id": f"ledger-{ecosystem}",
            **scope,
            "assessment_depth": "comprehensive",
            "report_language": "en",
        },
        "status": "review_required",
        "terminal": True,
        "revision": 8,
        "package_classification": "client_final",
        "human_evidence": {
            "modules": {
                "stakeholder_context": {
                    "evidence": {
                        "engagement_mode": ["client"],
                        "client_identity": [f"Acme {ecosystem.title()}"],
                        "project_identity": [f"{ecosystem.title()} security review"],
                        "repository_identity": [repo],
                        "primary_technical_contact": ["security@example.test"],
                        "access_method": ["GitHub App read-only access"],
                        "authorized_scope": ["Entire repository at immutable commit"],
                        "authorization_confirmation": ["confirmed"],
                    }
                }
            }
        },
        "scanner_execution_contract": {
            "support_status": "supported",
            "ecosystem": ecosystem,
            "required_scanners": [required_scanner],
            "executions": [
                {
                    "scanner": required_scanner,
                    "status": "completed",
                    "version": "fixture-1.0",
                    "artifact_sha256": "1" * 64,
                }
            ],
        },
        "stage_results": {
            "immutable_repository_snapshot": {
                "snapshot": {"commit_sha": commit, "tree_sha": "2" * 40, "read_only": True}
            },
            "final_comprehensive_report_generation": {"report_package": package},
        },
        "review_work_ledger": ledger,
        "generator_versions": canonical["generator_versions"],
        "integrity_sha256": "3" * 64,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _manifest(record: dict) -> dict:
    digests = artifact_digests(record)
    manifest = {
        "artifact_schema": "nico.decision_grade_accepted_edition.v2",
        "accepted_edition": True,
        "client_delivery_allowed": True,
        "artifact_digests": {key: digests[key] for key in ("markdown", "html", "pdf", "json")},
        "review": {
            "reviewer": "Alice Security",
            "reviewer_role": "Cybersecurity specialist",
            "decision": "approved",
            "reason": "Exact evidence and residual risk were reviewed and accepted.",
            "decided_at": "2026-08-21T15:00:00+00:00",
        },
    }
    manifest["accepted_edition_manifest_sha256"] = canonical_sha256(manifest)
    return manifest


@pytest.mark.parametrize("ecosystem", ["python", "node", "mixed"])
def test_outside_structure_fixtures_prove_complete_preapproval_contract(ecosystem: str) -> None:
    result = validate_full_lifecycle(_record(ecosystem))
    assert result["status"] == "ready_for_explicit_human_approval"
    assert result["validation_errors"] == []
    assert result["one_product"] == PRODUCT_NAME
    assert result["one_client_report"] is True
    assert result["client_delivery_authorized"] is False
    assert result["version_truth"]["deployment_identity_established"] is True


def test_explicit_human_approval_receipt_binds_exact_client_project_run_and_artifacts() -> None:
    record = _record()
    manifest = _manifest(record)
    receipt = build_approval_receipt(
        record,
        manifest,
        reviewer="Alice Security",
        reviewer_role="Cybersecurity specialist",
        decision="approved",
        decided_at="2026-08-21T15:00:00+00:00",
        decision_reason="Exact evidence and residual risk were reviewed and accepted.",
    )
    assert receipt["client_identity"] == "Acme Python"
    assert receipt["project_identity"] == "Python security review"
    assert receipt["assessment_run_id"] == "comprun_phase4_python"
    assert receipt["pdf_sha256"] == manifest["artifact_digests"]["pdf"]["sha256"]
    assert receipt["canonical_json_sha256"] == manifest["artifact_digests"]["json"]["sha256"]
    assert receipt["review"]["human_action_required"] is True
    assert receipt["review"]["automation_may_not_approve"] is True
    assert validate_approval_receipt(record, manifest, receipt)["status"] == "valid"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda r: r["human_evidence"]["modules"]["stakeholder_context"]["evidence"].update({"authorization_confirmation": ["not_confirmed"]}), "assessment_authorization_missing"),
        (lambda r: r["human_evidence"]["modules"]["stakeholder_context"]["evidence"].update({"repository_identity": ["OtherOrg/other"]}), "repository_outside_approved_scope"),
        (lambda r: r["human_evidence"]["modules"]["stakeholder_context"]["evidence"].update({"access_method": ["write-enabled personal token"]}), "repository_access_not_read_only"),
        (lambda r: r["identity"].update({"commit_sha": "unresolved"}), "unresolved_assessed_commit"),
        (lambda r: r["stage_results"]["immutable_repository_snapshot"]["snapshot"].update({"commit_sha": "9" * 40}), "report_attached_to_wrong_assessed_commit"),
        (lambda r: r["scanner_execution_contract"]["executions"][0].update({"status": "failed"}), "required_scanner_execution_failed"),
        (lambda r: r["scanner_execution_contract"].update({"support_status": "unsupported_not_assessed"}), "unsupported_ecosystem_not_assessed"),
        (lambda r: r["stage_results"]["final_comprehensive_report_generation"]["report_package"]["json"]["assessment"]["canonical_scanner_finding_register"].update({"candidate_record_count": 2}), "candidate_register_count_mismatch"),
        (lambda r: r["stage_results"]["final_comprehensive_report_generation"]["report_package"]["json"]["assessment"]["canonical_scanner_finding_register"]["findings"][0].pop("candidate_lineage_version"), None),
        (lambda r: (r["stage_results"]["final_comprehensive_report_generation"]["report_package"]["json"]["assessment"]["canonical_scanner_finding_register"]["findings"][0].pop("human_disposition"), r["review_work_ledger"]["dispositions"].clear()), "mandatory_individual_review_unresolved"),
        (lambda r: r["review_work_ledger"].update({"human_dispositions_pending": 1}), "human_dispositions_pending"),
        (lambda r: r["review_work_ledger"]["scope_binding"].update({"project_id": "other-project"}), "cross_project_id_review_mismatch"),
        (lambda r: r["stage_results"]["final_comprehensive_report_generation"]["report_package"].update({"package_classification": "internal_test"}), "internal_or_test_package_presented_as_client_final"),
        (lambda r: r["stage_results"]["final_comprehensive_report_generation"]["report_package"].update({"product_name": "NICO Express"}), "alternate_report_product_rejected"),
    ],
)
def test_fail_closed_lifecycle_matrix(mutation, expected: str | None) -> None:
    record = _record()
    mutation(record)
    result = validate_full_lifecycle(record)
    if expected is None:
        assert result["status"] == "ready_for_explicit_human_approval"
    else:
        assert result["status"] == "blocked"
        assert expected in result["validation_errors"]


def test_material_regeneration_invalidates_stale_approval_receipt() -> None:
    record = _record()
    manifest = _manifest(record)
    receipt = build_approval_receipt(
        record,
        manifest,
        reviewer="Alice Security",
        reviewer_role="Cybersecurity specialist",
        decision="approved",
        decided_at="2026-08-21T15:00:00+00:00",
        decision_reason="Exact evidence and residual risk were reviewed and accepted.",
    )
    changed = deepcopy(record)
    changed["stage_results"]["final_comprehensive_report_generation"]["report_package"]["markdown"] += "\nChanged after approval.\n"
    result = validate_approval_receipt(changed, manifest, receipt)
    assert result["status"] == "invalid"
    assert "artifact_hash_mismatch" in result["validation_errors"]


@pytest.mark.parametrize(("field", "value"), [("reviewer", "automation"), ("reviewer_role", "sales representative"), ("reviewer_role", "security sales representative")])
def test_automation_or_unauthorized_role_cannot_approve(field: str, value: str) -> None:
    record = _record()
    manifest = _manifest(record)
    kwargs = {
        "reviewer": "Alice Security",
        "reviewer_role": "Cybersecurity specialist",
        "decision": "approved",
        "decided_at": "2026-08-21T15:00:00+00:00",
        "decision_reason": "Exact evidence and residual risk were reviewed and accepted.",
    }
    kwargs[field] = value
    with pytest.raises(ClientDeliveryContractError):
        build_approval_receipt(record, manifest, **kwargs)


def test_every_declared_required_scanner_has_a_retained_execution() -> None:
    record = _record()
    record["scanner_execution_contract"]["required_scanners"].append("semgrep")
    result = validate_full_lifecycle(record)
    assert result["status"] == "blocked"
    assert "required_scanner_execution_missing" in result["validation_errors"]


def test_candidate_dispositions_reconcile_exactly_with_the_canonical_register() -> None:
    missing = _record()
    candidate = missing["stage_results"]["final_comprehensive_report_generation"]["report_package"]["json"]["assessment"]["canonical_scanner_finding_register"]["findings"][0]
    candidate["review_requires_individual_attention"] = False
    candidate.pop("human_disposition", None)
    missing["review_work_ledger"]["dispositions"].clear()
    missing["review_work_ledger"]["human_dispositions_pending"] = 0
    missing_result = validate_full_lifecycle(missing)
    assert missing_result["status"] == "blocked"
    assert "human_dispositions_pending" in missing_result["validation_errors"]

    unexpected = _record()
    unexpected["review_work_ledger"]["dispositions"]["candidate-ghost"] = {
        "decision": "false_positive",
        "reviewer": "Alice Security",
        "reviewer_role": "Cybersecurity specialist",
    }
    unexpected_result = validate_full_lifecycle(unexpected)
    assert unexpected_result["status"] == "blocked"
    assert "candidate_disposition_register_mismatch" in unexpected_result["validation_errors"]


def test_structurally_invalid_pdf_is_not_digestable_as_a_client_final_artifact() -> None:
    record = _record()
    package = record["stage_results"]["final_comprehensive_report_generation"]["report_package"]
    package["pdf_base64"] = base64.b64encode(b"not-a-pdf").decode("ascii")
    result = validate_full_lifecycle(record)
    assert result["status"] == "blocked"
    assert "final_pdf_invalid" in result["validation_errors"]


def test_self_asserted_reviewer_authorization_basis_is_rejected() -> None:
    record = _record()
    manifest = _manifest(record)
    with pytest.raises(ClientDeliveryContractError, match="reviewer_authorization_basis_invalid"):
        build_approval_receipt(
            record,
            manifest,
            reviewer="Alice Security",
            reviewer_role="Cybersecurity specialist",
            decision="approved",
            decided_at="2026-08-21T15:00:00+00:00",
            decision_reason="Exact evidence and residual risk were reviewed and accepted.",
            authorization_basis="self_asserted",
        )



def test_operational_workload_target_is_visible_but_never_a_score_or_approval_shortcut() -> None:
    record = _record()
    record["review_work_ledger"]["operational_timing"]["estimated_combined_specialist_hours"] = 6.5
    metrics = operational_metrics(record)
    assert metrics["estimated_combined_specialist_hours"] == 6.5
    assert metrics["four_hour_design_target_exceeded"] is True
    assert metrics["metrics_are_not_security_or_maturity_scores"] is True
    assert validate_full_lifecycle(record)["status"] == "ready_for_explicit_human_approval"
