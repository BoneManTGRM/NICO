from __future__ import annotations

import base64
import hashlib
import io
import zipfile
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from nico.comprehensive_approved_delivery_v3 import (
    build_approved_delivery_package,
    validate_approved_delivery_package,
)
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_final_decision_truth_v1 import synchronize_final_decision_truth
from nico.comprehensive_review_decision_v1 import build_reviewed_edition
from nico.comprehensive_review_work_safe_v1 import apply_review_work_action


def _pdf() -> str:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    document.drawString(72, 720, "NICO Comprehensive exact reviewed analysis")
    document.save()
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _record() -> dict:
    identity = {
        "run_id": "comprun_final_truth_v3",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_final_truth_v3",
        "customer_id": "customer-final",
        "project_id": "project-final",
        "client_id": "client-final",
        "assessment_depth": "comprehensive",
        "report_language": "en",
    }
    finding = {
        "candidate_id": "candidate-final-1",
        "finding_id": "finding-final-1",
        "cluster_id": "cluster-final-1",
        "severity": "low",
        "scanner": "semgrep",
        "category": "security",
        "rule": "fixture-rule",
        "path": "src/final.py",
        "technical_triage_verdict": "not_actionable",
        "technical_triage_confidence": 0.99,
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
        "candidate_record_count": 1,
        "findings": [finding],
        "review_workload_clusters": [
            {
                "cluster_id": "cluster-final-1",
                "candidate_ids": ["candidate-final-1"],
                "candidate_record_count": 1,
                "cluster_size": 1,
                "representative_candidate_id": "candidate-final-1",
                "grouped_review_eligible": False,
                "grouped_human_review_cluster": False,
                "homogeneous_evidence": True,
                "homogeneous_verdict": True,
                "underlying_candidate_disposition_required": True,
            }
        ],
        "technical_triage": {"total_candidates": 1, "triaged_candidates": 1},
    }
    canonical = {
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
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    package = {
        "report_id": "report-final-truth-v3",
        "report_language": "en",
        "markdown": "# NICO Comprehensive\n\nDRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED\n",
        "html": "<html><body><main><article><h1>NICO Comprehensive</h1></article></main></body></html>",
        "pdf_base64": _pdf(),
        "pdf_page_count": 1,
        "json": canonical,
        "canonical_truth_sha256": "evidence-bundle-final-v3",
        "findings_csv": "finding_id,title\nfixture,Fixture\n",
        "evidence_csv": "evidence_id,source\nev-1,scanner\n",
        "jira_csv": "summary,description\nFixture,Remediation fixture\n",
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
        "stage_results": {
            "immutable_repository_snapshot": {"snapshot": {"tree_sha": "b" * 40}},
            "deep_scanner_triage": {"scanner_run_id": "scan-final-v3"},
            "final_comprehensive_report_generation": {"report_package": package},
        },
    }


def _reviewed_record() -> dict:
    record = _record()
    ledger = apply_review_work_action(
        record,
        {
            "action": "disposition_candidate",
            "candidate_id": "candidate-final-1",
            "disposition": "false_positive",
            "rationale": "Exact retained evidence supports a non-actionable human disposition.",
            "reviewer": "Alice",
            "reviewer_role": "Security specialist",
            "review_authorized": True,
            "authorization_confirmed": True,
        },
        now=datetime(2026, 8, 11, 13, 0, tzinfo=UTC),
    )
    record["review_work_ledger"] = ledger
    return record


def _authorized_packaging_projection(manifest: dict) -> dict:
    """V3 is the lower ZIP builder; V4 validates the separate receipt around it."""

    projected = deepcopy(manifest)
    projected["client_delivery_allowed"] = True
    projected["delivery_status"] = "approved_for_delivery"
    projected.pop("accepted_edition_manifest_sha256", None)
    projected["accepted_edition_manifest_sha256"] = canonical_sha256(projected)
    return projected


def test_final_human_decision_is_in_exact_artifacts_before_acceptance() -> None:
    record = synchronize_final_decision_truth(
        _reviewed_record(),
        decision="approved",
        reviewer="Alice",
        reviewer_role="Security specialist",
        decision_reason="All candidate-level review gates are complete.",
        decided_at="2026-08-11T13:30:00+00:00",
    )
    package = record["stage_results"]["final_comprehensive_report_generation"]["report_package"]
    truth = package["human_review_truth"]
    assert truth["authorized_human_disposition_completed"] == 1
    assert truth["final_human_approval_status"] == "approved"
    assert truth["client_delivery_authorization_status"] == "pending_authorization"
    assert "Final human approval: APPROVED" in package["markdown"]
    assert "Client-delivery authorization: PENDING_AUTHORIZATION" in package["markdown"]
    assert "APPROVED" in package["html"]


def test_approved_client_pdf_is_the_exact_reviewed_pdf_with_separate_certificate() -> None:
    decision_record = synchronize_final_decision_truth(
        _reviewed_record(),
        decision="approved",
        reviewer="Alice",
        reviewer_role="Security specialist",
        decision_reason="All candidate-level review gates are complete.",
        decided_at="2026-08-11T13:30:00+00:00",
    )
    manifest = build_reviewed_edition(
        decision_record,
        reviewer="Alice",
        reviewer_role="Security specialist",
        decision="approved",
        decision_reason="All candidate-level review gates are complete.",
        decided_at="2026-08-11T13:30:00+00:00",
    )
    assert manifest["accepted_edition"] is True
    packaging_manifest = _authorized_packaging_projection(manifest)
    approved_record = deepcopy(decision_record)
    approved_record["accepted_edition"] = deepcopy(packaging_manifest)
    delivery = build_approved_delivery_package(approved_record, packaging_manifest)
    assert delivery["one_client_report"] is True
    assert delivery["client_pdf_count"] == 1
    assert delivery["approval_certificate_page_appended"] is False
    assert delivery["approval_certificate_separate_json"] is True
    assert delivery["approved_report_pdf_preserved_exactly"] is True
    assert delivery["final_human_approval_status"] == "approved"
    assert delivery["client_delivery_authorization_status"] == "authorized"
    assert delivery["certificate"]["review_work_ledger_sha256"] == manifest["review_work_ledger_sha256"]

    archive = base64.b64decode(delivery["zip_base64"], validate=True)
    with zipfile.ZipFile(io.BytesIO(archive), "r") as zipped:
        pdf_names = [name for name in zipped.namelist() if name.endswith(".pdf")]
        assert pdf_names == ["01_nico_comprehensive_report.pdf"]
        pdf_bytes = zipped.read(pdf_names[0])
    reviewed_pdf = base64.b64decode(
        decision_record["stage_results"]["final_comprehensive_report_generation"][
            "report_package"
        ]["pdf_base64"],
        validate=True,
    )
    assert pdf_bytes == reviewed_pdf
    assert hashlib.sha256(pdf_bytes).hexdigest() == manifest["artifact_digests"][
        "pdf"
    ]["sha256"]

    validation_record = deepcopy(approved_record)
    validation_record["approved_delivery_package"] = deepcopy(delivery)
    validation = validate_approved_delivery_package(validation_record, delivery)
    assert validation["status"] == "valid"
    assert validation["validation_errors"] == []


def test_delivery_fails_if_review_ledger_changes_after_accepted_edition() -> None:
    decision_record = synchronize_final_decision_truth(
        _reviewed_record(),
        decision="approved",
        reviewer="Alice",
        reviewer_role="Security specialist",
        decision_reason="All candidate-level review gates are complete.",
        decided_at="2026-08-11T13:30:00+00:00",
    )
    manifest = build_reviewed_edition(
        decision_record,
        reviewer="Alice",
        reviewer_role="Security specialist",
        decision="approved",
        decision_reason="All candidate-level review gates are complete.",
        decided_at="2026-08-11T13:30:00+00:00",
    )
    tampered = deepcopy(decision_record)
    packaging_manifest = _authorized_packaging_projection(manifest)
    tampered["accepted_edition"] = deepcopy(packaging_manifest)
    tampered["review_work_ledger"]["dispositions"]["candidate-final-1"]["rationale"] = "tampered after acceptance"
    with pytest.raises(ValueError, match="approved_delivery_review_ledger_binding_mismatch"):
        build_approved_delivery_package(tampered, packaging_manifest)
