from __future__ import annotations

import base64
import io
import zipfile
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from nico.comprehensive_approved_delivery_v4 import (
    attach_approved_delivery_package,
    bind_phase4_approval_manifest,
    validate_approved_delivery_package,
)
from nico.comprehensive_final_decision_truth_v1 import synchronize_final_decision_truth
from nico.comprehensive_review_decision_v1 import build_reviewed_edition
from nico.comprehensive_review_work_safe_v1 import apply_review_work_action


def _pdf() -> str:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    document.drawString(72, 720, "NICO Comprehensive Phase 4 exact reviewed analysis")
    document.save()
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _record() -> dict:
    identity = {
        "run_id": "comprun_phase4_delivery",
        "repository": "OutsideOrg/python-service",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_phase4_delivery",
        "customer_id": "customer-phase4",
        "client_id": "client-phase4",
        "project_id": "project-phase4",
        "workspace_id": "workspace-phase4",
        "tenant_id": "tenant-phase4",
        "assessment_depth": "comprehensive",
        "report_language": "en",
    }
    finding = {
        "candidate_id": "candidate-phase4-1",
        "finding_id": "finding-phase4-1",
        "cluster_id": "cluster-phase4-1",
        "severity": "low",
        "scanner": "bandit",
        "category": "security",
        "rule": "fixture-rule",
        "path": "src/app.py",
        "candidate_lineage_version": "nico.candidate_lineage.v1",
        "lineage": {"version": "nico.candidate_lineage.v1", "status": "newly_observed"},
        "technical_triage_verdict": "not_actionable",
        "technical_triage_confidence": 0.99,
        "technical_triage": {
            "version": "nico.technical_triage.v1",
            "verdict": "not_actionable",
            "confidence": 0.99,
        },
        "evidence_change_state": "new",
        "grouped_review_eligible": False,
        "review_requires_individual_attention": False,
        "homogeneous_evidence": True,
        "homogeneous_verdict": True,
        "review_routing_class": "AUTOMATED_TRIAGE_COMPLETE",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    register = {
        "artifact_schema": "nico.canonical_scanner_finding_register.v1",
        "candidate_lineage_version": "nico.candidate_lineage.v1",
        "candidate_record_count": 1,
        "findings": [finding],
        "review_workload_clusters": [
            {
                "cluster_id": "cluster-phase4-1",
                "candidate_ids": ["candidate-phase4-1"],
                "candidate_record_count": 1,
                "cluster_size": 1,
                "representative_candidate_id": "candidate-phase4-1",
                "grouped_review_eligible": False,
                "grouped_human_review_cluster": False,
                "homogeneous_evidence": True,
                "homogeneous_verdict": True,
                "underlying_candidate_disposition_required": True,
            }
        ],
        "technical_triage": {
            "version": "nico.technical_triage.v1",
            "total_candidates": 1,
            "triaged_candidates": 1,
        },
        "scanner_versions": {"bandit": "1.9.0"},
    }
    canonical = {
        "product_name": "NICO Comprehensive",
        "identity": {
            key: identity[key]
            for key in ("run_id", "repository", "commit_sha", "evidence_ledger_id")
        },
        "report_language": "en",
        "assessment_depth": "comprehensive",
        "assessment": {"canonical_scanner_finding_register": register},
        "findings_register": [],
        "roadmap": [],
        "staffing_plan": [],
        "generator_versions": {
            "nico_backend_build_commit": "b" * 40,
            "frontend_build_commit": "c" * 40,
            "assessment_engine_version": "nico.engine.v1",
            "scoring_model_version": "nico.score.v1",
            "report_renderer_version": "nico.renderer.v1",
            "artifact_generation_version": "nico.artifacts.v1",
            "candidate_lineage_version": "nico.candidate_lineage.v1",
            "technical_triage_version": "nico.technical_triage.v1",
            "scanner_versions": {"bandit": "1.9.0"},
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    package = {
        "report_id": "report-phase4-delivery",
        "product_name": "NICO Comprehensive",
        "package_classification": "client_final",
        "report_language": "en",
        "markdown": "# NICO Comprehensive\n\nDRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED\n",
        "html": "<html><body><main><article><h1>NICO Comprehensive</h1></article></main></body></html>",
        "pdf_base64": _pdf(),
        "pdf_page_count": 1,
        "json": canonical,
        "canonical_truth_sha256": "evidence-bundle-phase4",
        "findings_csv": "finding_id,title\nfixture,Fixture\n",
        "evidence_csv": "evidence_id,source\nev-1,scanner\n",
        "jira_csv": "summary,description\nFixture,Remediation fixture\n",
        "candidate_register_csv": "candidate_id,disposition\ncandidate-phase4-1,false_positive\n",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return {
        "identity": identity,
        "status": "review_required",
        "terminal": True,
        "revision": 1,
        "human_review_completed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "human_evidence": {
            "modules": {
                "stakeholder_context": {
                    "evidence": {
                        "engagement_mode": ["client"],
                        "client_identity": ["Acme Holdings"],
                        "project_identity": ["Python service review"],
                        "repository_identity": [identity["repository"]],
                        "primary_technical_contact": ["security@example.test"],
                        "access_method": ["GitHub App read-only access"],
                        "authorized_scope": ["Entire repository at immutable commit"],
                        "authorization_confirmation": ["confirmed"],
                    }
                }
            }
        },
        "stage_results": {
            "immutable_repository_snapshot": {
                "snapshot": {"tree_sha": "d" * 40, "commit_sha": identity["commit_sha"]}
            },
            "deep_scanner_triage": {"scanner_run_id": "scan-phase4"},
            "final_comprehensive_report_generation": {"report_package": package},
        },
        "generator_versions": canonical["generator_versions"],
    }


def _reviewed_record() -> dict:
    record = _record()
    ledger = apply_review_work_action(
        record,
        {
            "action": "disposition_candidate",
            "candidate_id": "candidate-phase4-1",
            "disposition": "false_positive",
            "rationale": "Exact retained evidence supports a non-actionable human disposition.",
            "reviewer": "Alice Security",
            "reviewer_role": "Cybersecurity specialist",
            "review_authorized": True,
            "authorization_confirmed": True,
        },
        now=datetime(2026, 8, 21, 14, 0, tzinfo=UTC),
    )
    record["review_work_ledger"] = ledger
    return record


def _decision_and_manifest() -> tuple[dict, dict]:
    decision_record = synchronize_final_decision_truth(
        _reviewed_record(),
        decision="approved",
        reviewer="Alice Security",
        reviewer_role="Cybersecurity specialist",
        decision_reason="All exact candidate and residual-risk review gates are complete.",
        decided_at="2026-08-21T15:00:00+00:00",
    )
    manifest = build_reviewed_edition(
        decision_record,
        reviewer="Alice Security",
        reviewer_role="Cybersecurity specialist",
        decision="approved",
        decision_reason="All exact candidate and residual-risk review gates are complete.",
        decided_at="2026-08-21T15:00:00+00:00",
    )
    return decision_record, manifest


def test_phase4_approved_delivery_binds_full_identity_and_receipt_inside_one_report_package() -> None:
    decision_record, manifest = _decision_and_manifest()
    attached = attach_approved_delivery_package(decision_record, manifest)
    delivery = attached["approved_delivery_package"]
    receipt = delivery["phase4_approval_receipt"]
    certificate = delivery["certificate"]

    assert attached["accepted_edition"]["phase4_approval_binding"]["client_identity"] == "Acme Holdings"
    assert receipt["client_identity"] == "Acme Holdings"
    assert receipt["project_identity"] == "Python service review"
    assert receipt["assessment_run_id"] == "comprun_phase4_delivery"
    assert receipt["repository"] == "OutsideOrg/python-service"
    assert receipt["assessed_repository_commit"] == "a" * 40
    assert receipt["review"]["authorization_basis"] == "protected_admin_write_and_explicit_review_authorization"
    assert receipt["review"]["automation_may_not_approve"] is True
    assert certificate["phase4_approval_receipt_sha256"] == receipt["approval_receipt_sha256"]
    assert certificate["client_identity"] == "Acme Holdings"
    assert certificate["project_identity"] == "Python service review"
    assert delivery["one_client_report"] is True
    assert delivery["client_pdf_count"] == 1

    archive = base64.b64decode(delivery["zip_base64"], validate=True)
    with zipfile.ZipFile(io.BytesIO(archive), "r") as zipped:
        pdf_names = [name for name in zipped.namelist() if name.endswith(".pdf")]
        assert pdf_names == ["01_nico_comprehensive_report.pdf"]
        assert "12_phase4_approval_receipt.json" in zipped.namelist()
        assert "11_evidence_manifest.json" in zipped.namelist()

    validation = validate_approved_delivery_package(attached, delivery)
    assert validation["status"] == "valid"
    assert validation["validation_errors"] == []


def test_cross_project_mutation_invalidates_delivery() -> None:
    decision_record, manifest = _decision_and_manifest()
    attached = attach_approved_delivery_package(decision_record, manifest)
    tampered = deepcopy(attached)
    tampered["identity"]["project_id"] = "other-project"
    validation = validate_approved_delivery_package(tampered, tampered["approved_delivery_package"])
    assert validation["status"] == "invalid"
    assert any("project" in item for item in validation["validation_errors"])


def test_report_regeneration_after_approval_invalidates_receipt() -> None:
    decision_record, manifest = _decision_and_manifest()
    attached = attach_approved_delivery_package(decision_record, manifest)
    tampered = deepcopy(attached)
    package = tampered["stage_results"]["final_comprehensive_report_generation"]["report_package"]
    package["markdown"] += "\nRegenerated after approval.\n"
    validation = validate_approved_delivery_package(tampered, tampered["approved_delivery_package"])
    assert validation["status"] == "invalid"
    assert "artifact_hash_mismatch" in validation["validation_errors"]


def test_automation_identity_cannot_be_bound_as_final_approver() -> None:
    decision_record, manifest = _decision_and_manifest()
    manifest = deepcopy(manifest)
    manifest["review"]["reviewer"] = "automation"
    with pytest.raises(ValueError, match="automation_cannot_create_final_human_approval"):
        bind_phase4_approval_manifest(decision_record, manifest)


def test_internal_assessment_cannot_become_phase4_client_final() -> None:
    decision_record, manifest = _decision_and_manifest()
    decision_record = deepcopy(decision_record)
    evidence = decision_record["human_evidence"]["modules"]["stakeholder_context"]["evidence"]
    evidence["engagement_mode"] = ["internal"]
    with pytest.raises(ValueError, match="internal_or_test_package_not_client_final"):
        attach_approved_delivery_package(decision_record, manifest)
