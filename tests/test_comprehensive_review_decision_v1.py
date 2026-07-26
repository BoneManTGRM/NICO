from __future__ import annotations

import base64
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_review_decision_v1 import build_reviewed_edition
from nico.comprehensive_run_record import (
    apply_comprehensive_review_decision,
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
    validate_comprehensive_run_record,
)
from nico.comprehensive_run_service import ComprehensiveRunService


def _review_ready_record() -> dict:
    record = create_comprehensive_run_record(
        run_id="comprun_review_1",
        repository="owner/repo",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger-review-1",
        customer_id="customer-1",
        project_id="project-1",
        authorized=True,
        assessment_depth="strategic",
        report_language="en",
        now=datetime(2026, 7, 26, 1, 0, tzinfo=UTC),
    )
    package = {
        "service_id": "comprehensive",
        "report_id": "report-review-1",
        "markdown": "# Immutable report\n",
        "html": "<html><body>Immutable report</body></html>",
        "pdf_base64": base64.b64encode(b"%PDF-1.7 immutable-review").decode("ascii"),
        "pdf_filename": "nico-review.pdf",
        "canonical_truth_sha256": "d" * 64,
        "json": {
            "identity": {
                "repository": "owner/repo",
                "commit_sha": "a" * 40,
                "run_id": "comprun_review_1",
                "report_language": "en",
                "assessment_depth": "strategic",
            },
            "canonical_truth_sha256": "d" * 64,
        },
    }
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
        reviewer_role="Principal Engineering Reviewer",
        decision=decision,
        decision_reason="The exact immutable evidence and report artifacts were reviewed.",
        decided_at="2026-07-26T01:05:00+00:00",
    )


def test_approved_review_unlocks_only_the_exact_existing_artifacts() -> None:
    record = _review_ready_record()
    manifest = _manifest(record)
    approved = apply_comprehensive_review_decision(record, manifest=manifest)

    assert approved["status"] == "approved"
    assert approved["client_delivery_allowed"] is True
    assert approved["human_review_completed"] is True
    assert approved["accepted_edition"]["accepted_edition"] is True
    assert approved["review_context"]["report_regenerated_during_review"] is False
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
        reviewer_role="Principal Engineering Reviewer",
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


def test_service_persists_the_review_with_one_revision_advance() -> None:
    record = _review_ready_record()
    store = _MemoryStore(record)
    service = ComprehensiveRunService(store, {})  # type: ignore[arg-type]

    approved = service.review(
        record["identity"]["run_id"],
        reviewer="reviewer@example.com",
        reviewer_role="Principal Engineering Reviewer",
        decision="approved",
        decision_reason="Approved after exact-artifact review.",
        decided_at="2026-07-26T01:15:00+00:00",
    )

    assert approved["revision"] == record["revision"] + 1
    assert store.record["status"] == "approved"
    assert store.record["client_delivery_allowed"] is True
