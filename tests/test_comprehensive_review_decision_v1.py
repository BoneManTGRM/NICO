from __future__ import annotations

import base64
import io
import zipfile
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pypdf import PdfReader

from nico.comprehensive_approved_delivery_v1 import validate_approved_delivery_package
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_review_decision_v1 import (
    build_reviewed_edition,
    review_artifact_identity,
)
from nico.comprehensive_run_record import (
    apply_comprehensive_review_decision,
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
    validate_comprehensive_run_record,
)
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from tests.test_v2_premium_report_renderer import _package


def _exact_report(
    record: dict,
    *,
    regenerated: bool = False,
    omit_strategic_identity: bool = False,
) -> dict:
    identity = record["identity"]
    source = _package(identity["report_language"])
    source["json"]["identity"].update(
        {
            "repository": identity["repository"],
            "commit_sha": identity["commit_sha"],
            "run_id": identity["run_id"],
            "evidence_ledger_id": identity["evidence_ledger_id"],
            "customer_id": identity["customer_id"],
            "project_id": identity["project_id"],
            "assessment_depth": identity["assessment_depth"],
            "report_language": identity["report_language"],
        }
    )
    if regenerated:
        source["json"]["generated_at"] = "2026-07-26T01:19:00Z"
        source["json"]["identity"]["generated_at"] = (
            "2026-07-26T01:19:00Z"
        )
    if omit_strategic_identity:
        source["json"]["identity"].pop("assessment_depth")
        source["json"]["identity"].pop("report_language")
    return rebuild_client_artifacts(source)


def _review_ready_record(
    *,
    report_language: str = "en",
    omit_strategic_report_identity: bool = False,
) -> dict:
    record = create_comprehensive_run_record(
        run_id=f"comprun_review_{report_language}",
        repository="owner/repo",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger-review-1",
        customer_id="customer-1",
        project_id="project-1",
        authorized=True,
        assessment_depth="strategic",
        report_language=report_language,
        human_evidence={
            "modules": {
                "stakeholder_context": {
                    "evidence": {
                        "engagement_mode": ["client"],
                        "client_identity": ["Test Client"],
                        "project_identity": ["Approved report finalization"],
                        "repository_identity": ["owner/repo"],
                        "primary_technical_contact": ["security@example.test"],
                        "access_method": ["GitHub App read-only access"],
                        "authorized_scope": ["Entire repository at immutable commit"],
                        "authorization_confirmation": ["confirmed"],
                    }
                }
            }
        },
        now=datetime(2026, 7, 26, 1, 0, tzinfo=UTC),
    )
    package = _exact_report(
        record,
        omit_strategic_identity=omit_strategic_report_identity,
    )
    for stage_id in COMPREHENSIVE_STAGES:
        result: dict = {"status": "complete", "summary": stage_id}
        if stage_id == "immutable_repository_snapshot":
            result["snapshot"] = {"tree_sha": "b" * 40}
        if stage_id == "dependency_security_static_analysis":
            result["scan_id"] = "scan-review-1"
        if stage_id == "final_comprehensive_report_generation":
            result["report_package"] = deepcopy(package)
            result["assessment"] = {"status": "complete"}
        if stage_id == "client_acceptance_pending":
            result["status"] = "review_required"
        record = apply_comprehensive_stage_result(
            record,
            stage_id=stage_id,
            result=result,
            now=datetime(2026, 7, 26, 1, 1, tzinfo=UTC),
        )
    assert record["status"] == "review_required"
    assert validate_comprehensive_run_record(record)["status"] == "valid"
    return record


def _manifest(record: dict, decision: str = "approved") -> dict:
    return build_reviewed_edition(
        record,
        reviewer="reviewer@example.com",
        reviewer_role="Security reviewer",
        decision=decision,
        decision_reason="The exact immutable evidence and report artifacts were reviewed.",
        decided_at="2026-07-26T01:05:00+00:00",
    )


def test_approved_review_binds_exact_artifacts_without_authorizing_delivery() -> None:
    record = _review_ready_record()
    manifest = _manifest(record)
    approved = apply_comprehensive_review_decision(record, manifest=manifest)

    assert approved["status"] == "approved"
    assert approved["client_delivery_allowed"] is False
    assert approved["human_review_completed"] is True
    assert approved["accepted_edition"]["accepted_edition"] is True
    assert approved["review_context"]["report_regenerated_during_review"] is False
    assert validate_comprehensive_run_record(approved)["status"] == "valid"


def test_approval_uses_trusted_run_identity_for_older_exact_report_package() -> None:
    record = _review_ready_record(omit_strategic_report_identity=True)
    package = record["stage_results"]["final_comprehensive_report_generation"][
        "report_package"
    ]
    assert "assessment_depth" not in package["json"]["identity"]
    assert package["json"]["identity"]["report_language"] == "en"

    manifest = _manifest(record)
    approved = apply_comprehensive_review_decision(record, manifest=manifest)

    assert approved["status"] == "approved"
    assert approved["accepted_edition"]["assessment_depth"] == "strategic"
    assert approved["accepted_edition"]["report_language"] == "en"
    assert validate_comprehensive_run_record(approved)["status"] == "valid"


def test_rejection_and_more_evidence_never_unlock_delivery() -> None:
    record = _review_ready_record()
    rejected = apply_comprehensive_review_decision(
        record,
        manifest=_manifest(record, "rejected"),
    )
    assert rejected["status"] == "rejected"
    assert rejected["client_delivery_allowed"] is False
    assert "accepted_edition" not in rejected

    requested = apply_comprehensive_review_decision(
        record,
        manifest=_manifest(record, "request_more_evidence"),
    )
    assert requested["status"] == "review_required"
    assert requested["human_review_completed"] is False
    assert requested["client_delivery_allowed"] is False


def test_request_more_evidence_preserves_review_history_before_later_approval() -> None:
    record = _review_ready_record()
    requested = apply_comprehensive_review_decision(
        record,
        manifest=_manifest(record, "request_more_evidence"),
    )
    approved_manifest = build_reviewed_edition(
        requested,
        reviewer="reviewer@example.com",
        reviewer_role="Security reviewer",
        decision="approved",
        decision_reason="The requested evidence was supplied and reviewed.",
        decided_at="2026-07-26T01:10:00+00:00",
    )
    approved = apply_comprehensive_review_decision(requested, manifest=approved_manifest)

    assert approved["status"] == "approved"
    assert len(approved["review_history"]) == 2
    assert approved["review_history"][0]["review"]["decision"] == "request_more_evidence"
    assert approved["review_history"][1]["review"]["decision"] == "approved"


def test_artifact_change_after_review_manifest_creation_fails_closed() -> None:
    record = _review_ready_record()
    manifest = _manifest(record)
    record["stage_results"]["final_comprehensive_report_generation"]["report_package"]["markdown"] += "changed"
    record["integrity_sha256"] = "tampered"

    with pytest.raises(ValueError, match="invalid_run_record"):
        apply_comprehensive_review_decision(record, manifest=manifest)


class _MemoryStore:
    def __init__(self, record: dict) -> None:
        self.record = deepcopy(record)

    def load(self, run_id: str) -> dict:
        assert run_id == self.record["identity"]["run_id"]
        return deepcopy(self.record)

    def save(self, record: dict, *, expected_revision: int) -> dict:
        assert record["revision"] == expected_revision + 1
        self.record = deepcopy(record)
        return deepcopy(record)


def test_service_persists_human_approval_with_delivery_blocked() -> None:
    record = _review_ready_record()
    store = _MemoryStore(record)
    service = ComprehensiveRunService(store, {})  # type: ignore[arg-type]

    approved = service.review(
        record["identity"]["run_id"],
        reviewer="reviewer@example.com",
        reviewer_role="Security reviewer",
        decision="approved",
        decision_reason="Approved after exact-artifact review.",
        decided_at="2026-07-26T01:15:00+00:00",
        expected_artifact_identity=review_artifact_identity(record),
    )

    assert approved["revision"] == record["revision"] + 1
    assert store.record["status"] == "approved"
    assert store.record["client_delivery_allowed"] is False
    assert "approved_delivery_package" not in store.record
    assert "delivery_authorization" not in store.record
    assert store.record["accepted_edition"]["delivery_status"] == "pending_authorization"


def _pdf_text(encoded: str) -> str:
    payload = base64.b64decode(encoded, validate=True)
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(payload)).pages)


def test_approved_delivery_uses_a_final_pdf_without_stale_blocked_language() -> None:
    record = _review_ready_record()
    source_pdf_sha256 = record["stage_results"]["final_comprehensive_report_generation"][
        "report_package"
    ]["pdf_sha256"]
    store = _MemoryStore(record)
    service = ComprehensiveRunService(store, {})  # type: ignore[arg-type]

    approved = service.review(
        record["identity"]["run_id"],
        reviewer="Authorized Test Reviewer",
        reviewer_role="Security reviewer",
        decision="approved",
        decision_reason="Exact review package approved for finalization testing.",
        decided_at="2026-07-26T01:15:00+00:00",
        expected_artifact_identity=review_artifact_identity(record),
    )
    approved_report = approved["stage_results"][
        "final_comprehensive_report_generation"
    ]["report_package"]
    approved_text = _pdf_text(approved_report["pdf_base64"]).upper()

    assert approved_report["pdf_sha256"] != source_pdf_sha256
    assert "APPROVED FINAL" in approved_text
    assert "AUTOMATED DRAFT" not in approved_text
    assert "PENDING HUMAN APPROVAL" not in approved_text
    assert "CLIENT DELIVERY BLOCKED" not in approved_text
    assert "CLIENT DELIVERY: BLOCKED" not in approved_text
    assert "BLOCKED - AUTHORIZED HUMAN APPROVAL" not in approved_text
    assert approved_report["pdf_filename"].endswith("-APPROVED-FINAL.pdf")
    assert "APPROVED-APPROVED" not in approved_report["pdf_filename"]
    assert validate_comprehensive_run_record(approved)["status"] == "valid"
    assert approved["review_source_artifact_identity"]["artifact_digests"]["pdf"][
        "sha256"
    ] == source_pdf_sha256

    with pytest.raises(ValueError, match="stale_review_artifact_identity"):
        service.authorize_delivery(
            record["identity"]["run_id"],
            authorizer="Authorized Test Reviewer",
            authorizer_role="Security reviewer",
            authorization_reason="Stale source PDF must not authorize delivery.",
            authorized_at="2026-07-26T01:19:00+00:00",
            expected_artifact_identity=review_artifact_identity(record),
        )

    authorized = service.authorize_delivery(
        record["identity"]["run_id"],
        authorizer="Authorized Test Reviewer",
        authorizer_role="Security reviewer",
        authorization_reason="Authorize delivery of the exact approved PDF.",
        authorized_at="2026-07-26T01:20:00+00:00",
        expected_artifact_identity=review_artifact_identity(approved),
    )
    delivery = authorized["approved_delivery_package"]
    archive = base64.b64decode(delivery["zip_base64"], validate=True)
    with zipfile.ZipFile(io.BytesIO(archive), "r") as bundle:
        delivered_pdf = bundle.read("01_nico_comprehensive_report.pdf")

    assert delivered_pdf == base64.b64decode(
        approved_report["pdf_base64"], validate=True
    )
    delivered_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(delivered_pdf)).pages
    ).upper()
    assert "APPROVED FINAL" in delivered_text
    assert "AUTOMATED DRAFT" not in delivered_text
    assert "PENDING HUMAN APPROVAL" not in delivered_text
    assert "CLIENT DELIVERY BLOCKED" not in delivered_text
    assert authorized["client_delivery_allowed"] is True


def test_spanish_approval_finalizes_lifecycle_markers_without_changing_analysis() -> None:
    record = _review_ready_record(report_language="es-MX")
    store = _MemoryStore(record)
    service = ComprehensiveRunService(store, {})  # type: ignore[arg-type]

    approved = service.review(
        record["identity"]["run_id"],
        reviewer="Revisora Autorizada",
        reviewer_role="Cybersecurity specialist",
        decision="approved",
        decision_reason="Se revisó el paquete exacto para probar la finalización.",
        decided_at="2026-07-26T01:15:00+00:00",
        expected_artifact_identity=review_artifact_identity(record),
    )
    approved_report = approved["stage_results"][
        "final_comprehensive_report_generation"
    ]["report_package"]
    approved_text = _pdf_text(approved_report["pdf_base64"]).upper()

    assert "FINAL APROBADO" in approved_text
    assert "BORRADOR AUTOMATIZADO" not in approved_text
    assert "APROBACIÓN HUMANA PENDIENTE" not in approved_text
    assert "ENTREGA AL CLIENTE BLOQUEADA" not in approved_text
    assert approved_report["analysis_regenerated_during_approval"] is False


def test_service_blocks_approval_of_unchanged_report_after_more_evidence_request() -> None:
    record = _review_ready_record()
    store = _MemoryStore(record)
    service = ComprehensiveRunService(store, {})  # type: ignore[arg-type]

    service.review(
        record["identity"]["run_id"],
        reviewer="reviewer@example.com",
        reviewer_role="Security reviewer",
        decision="request_more_evidence",
        decision_reason="Executed QA evidence is still missing.",
        decided_at="2026-07-26T01:15:00+00:00",
        expected_artifact_identity=review_artifact_identity(record),
    )

    with pytest.raises(
        ValueError,
        match="approval_requires_new_evidence_bound_report_after_request_more_evidence",
    ):
        service.review(
            record["identity"]["run_id"],
            reviewer="reviewer@example.com",
            reviewer_role="Security reviewer",
            decision="approved",
            decision_reason="Approve unchanged report.",
            decided_at="2026-07-26T01:20:00+00:00",
            expected_artifact_identity=review_artifact_identity(store.record),
        )


def test_service_rejects_stale_artifact_identity_after_review_download() -> None:
    record = _review_ready_record()
    downloaded_identity = review_artifact_identity(record)
    store = _MemoryStore(record)
    service = ComprehensiveRunService(store, {})  # type: ignore[arg-type]
    regenerated = _exact_report(store.record, regenerated=True)
    final_stage = store.record["stage_results"]["final_comprehensive_report_generation"]
    final_stage["report_package"] = regenerated
    final_stage["assessment"] = deepcopy(regenerated["json"]["assessment"])
    store.record["revision"] += 1

    with pytest.raises(ValueError, match="stale_review_artifact_identity"):
        service.review(
            record["identity"]["run_id"],
            reviewer="reviewer@example.com",
            reviewer_role="Security reviewer",
            decision="approved",
            decision_reason="Attempted approval of a stale download.",
            decided_at="2026-07-26T01:20:00+00:00",
            expected_artifact_identity=downloaded_identity,
        )
