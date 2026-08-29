from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from copy import deepcopy
from datetime import UTC, datetime

import pytest

import nico.comprehensive_api_routes as routes
from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_review_decision_v1 import build_reviewed_edition
from nico.comprehensive_run_record import (
    _record_hash,
    _review_manifest_errors,
    apply_comprehensive_review_decision,
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
    validate_comprehensive_run_record,
)
from nico.comprehensive_run_store import ComprehensiveRunStore


def _review_ready_record() -> dict:
    record = create_comprehensive_run_record(
        run_id="comprun-receipt-projection-001",
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger-receipt-projection-001",
        customer_id="customer-receipt-projection-001",
        project_id="project-receipt-projection-001",
        authorized=True,
        assessment_depth="strategic",
        report_language="en",
        now=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
    )
    identity = record["identity"]
    canonical = {
        "report_id": "report-receipt-projection-001",
        "report_language": "en",
        "locale": "en",
        "identity": {
            "repository": identity["repository"],
            "commit_sha": identity["commit_sha"],
            "run_id": identity["run_id"],
            "evidence_ledger_id": identity["evidence_ledger_id"],
            "report_language": identity["report_language"],
            "assessment_depth": identity["assessment_depth"],
        },
        "assessment": {
            "report_language": "en",
            "locale": "en",
        },
        "findings_register": [],
        "executive_risk_register": [],
        "roadmap": [],
        "staffing_plan": [],
    }
    pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"
    package = {
        "service_id": "comprehensive",
        "report_id": canonical["report_id"],
        "report_language": "en",
        "locale": "en",
        "markdown": "# NICO Comprehensive\n\nHuman approval pending.\n",
        "html": "<html><body><h1>NICO Comprehensive</h1></body></html>",
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "pdf_filename": "nico-comprehensive-review.pdf",
        "pdf_page_count": 1,
        "canonical_truth_sha256": canonical_sha256(canonical),
        "json": canonical,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    for stage_id in COMPREHENSIVE_STAGES:
        result: dict = {"status": "complete", "summary": stage_id}
        if stage_id == "immutable_repository_snapshot":
            result["snapshot"] = {"tree_sha": "b" * 40}
        if stage_id == "dependency_security_static_analysis":
            result["scan_id"] = "scanner-receipt-projection-001"
        if stage_id == "final_comprehensive_report_generation":
            result["report_package"] = deepcopy(package)
            result["assessment"] = {"status": "complete"}
        if stage_id == "client_acceptance_pending":
            result["status"] = "review_required"
        record = apply_comprehensive_stage_result(
            record,
            stage_id=stage_id,
            result=result,
            now=datetime(2026, 8, 28, 12, 1, tzinfo=UTC),
        )

    assert record["status"] == "review_required"
    assert validate_comprehensive_run_record(record)["status"] == "valid"
    return record


def _receipt(record: dict, decision: str, *, reviewer: str, minute: int) -> dict:
    return build_reviewed_edition(
        record,
        reviewer=reviewer,
        reviewer_role="Security reviewer",
        decision=decision,
        decision_reason=f"Exact-artifact {decision} decision by {reviewer}.",
        decided_at=f"2026-08-28T12:{minute:02d}:00+00:00",
    )


def _project(record: dict) -> tuple[dict, dict]:
    response = ComprehensiveApiController._response(record, operation="status")
    return response, routes._review_projection(response, record)


@pytest.mark.parametrize(
    ("decision", "expected_status", "expected_approval_status"),
    [
        ("approved", "approved", "approved_final"),
        ("rejected", "rejected", "rejected"),
        (
            "request_more_evidence",
            "review_required",
            "pending_human_approval",
        ),
    ],
)
def test_canonical_final_review_receipt_is_exposed(
    decision: str,
    expected_status: str,
    expected_approval_status: str,
) -> None:
    record = _review_ready_record()
    receipt = _receipt(
        record,
        decision,
        reviewer="actual-reviewer@example.com",
        minute=5,
    )
    reviewed = apply_comprehensive_review_decision(record, manifest=receipt)

    response, projected = _project(reviewed)

    assert response["status"] == expected_status
    assert response["approval_status"] == expected_approval_status
    assert response["response_projection"]["review_decision_integrity_valid"] is True
    assert projected["review_decision"] == receipt
    assert projected["review_decision"]["review"]["reviewer"] == (
        "actual-reviewer@example.com"
    )


@pytest.mark.parametrize(
    (
        "decision",
        "expected_status",
        "expected_approval_status",
        "expected_human_review_completed",
        "expected_violations",
    ),
    [
        (
            "approved",
            "blocked",
            "invalidated_artifact_mismatch",
            False,
            {
                "review_decision_history_mismatch",
                "approved_accepted_edition_history_mismatch",
            },
        ),
        (
            "rejected",
            "blocked",
            "invalidated_review_receipt_mismatch",
            False,
            {"review_decision_history_mismatch"},
        ),
        (
            "request_more_evidence",
            "review_required",
            "pending_human_approval",
            False,
            {"review_decision_history_mismatch"},
        ),
    ],
)
def test_hash_valid_alternate_review_receipt_is_rejected_and_suppressed(
    decision: str,
    expected_status: str,
    expected_approval_status: str,
    expected_human_review_completed: bool,
    expected_violations: set[str],
) -> None:
    record = _review_ready_record()
    legitimate = _receipt(
        record,
        decision,
        reviewer="actual-reviewer@example.com",
        minute=5,
    )
    alternate = _receipt(
        record,
        decision,
        reviewer="alternate-reviewer@example.invalid",
        minute=6,
    )
    reviewed = apply_comprehensive_review_decision(record, manifest=legitimate)
    reviewed["review_decision"] = alternate
    reviewed["integrity_sha256"] = _record_hash(reviewed)

    # The alternate receipt is internally hash-valid and binds the same artifacts.
    # Its lack of authority is proved by exact transition identity: it is neither the
    # final history entry nor, for approval, the immutable accepted edition.
    assert _review_manifest_errors(reviewed, alternate) == []
    validation = validate_comprehensive_run_record(reviewed)
    assert validation["status"] == "invalid"
    assert expected_violations.issubset(set(validation["violations"]))
    assert reviewed["review_history"][-1] == legitimate
    assert reviewed["review_history"][-1] != alternate
    if decision == "approved":
        assert reviewed["accepted_edition"] == legitimate
        assert reviewed["accepted_edition"] != alternate

    response, projected = _project(reviewed)

    assert response["status"] == expected_status
    assert response["approval_status"] == expected_approval_status
    assert response["human_review_completed"] is expected_human_review_completed
    assert response["response_projection"]["review_decision_integrity_valid"] is False
    assert "review_decision" not in projected
    assert "review_context" not in projected
    if decision == "approved":
        assert "accepted_edition" not in response
        assert response["client_delivery_allowed"] is False
        assert response["delivery_status"] == "blocked_artifact_integrity"
    elif decision == "rejected":
        assert response["response_projection"][
            "rejection_invalidated_by_review_mismatch"
        ] is True
    else:
        assert response["canonical_status"] == "review_required"
        assert response["client_delivery_allowed"] is False


def test_approved_record_cannot_hide_split_accepted_edition_by_omitting_receipt(
) -> None:
    record = _review_ready_record()
    legitimate = _receipt(
        record,
        "approved",
        reviewer="actual-reviewer@example.com",
        minute=5,
    )
    alternate = _receipt(
        record,
        "approved",
        reviewer="alternate-reviewer@example.invalid",
        minute=6,
    )
    reviewed = apply_comprehensive_review_decision(record, manifest=legitimate)
    reviewed.pop("review_decision")
    reviewed["accepted_edition"] = alternate
    reviewed["integrity_sha256"] = _record_hash(reviewed)

    validation = validate_comprehensive_run_record(reviewed)

    assert validation["status"] == "invalid"
    assert "approved_review_decision_required" in validation["violations"]
    response, projected = _project(reviewed)
    assert response["status"] == "blocked"
    assert response["approval_status"] == "invalidated_artifact_mismatch"
    assert response["client_delivery_allowed"] is False
    assert "accepted_edition" not in response
    assert "review_decision" not in projected


def _sqlite_store(path) -> ComprehensiveRunStore:
    store = ComprehensiveRunStore(
        lambda: sqlite3.connect(path),
        dialect="sqlite",
    )
    store.ensure_schema()
    return store


def _erase_review_request(record: dict) -> dict:
    erased = deepcopy(record)
    for field in ("review_history", "review_decision", "review_context"):
        erased.pop(field, None)
    erased["integrity_sha256"] = _record_hash(erased)
    return erased


def test_sqlite_store_rejects_paired_review_history_deletion_after_evidence_request(
    tmp_path,
) -> None:
    record = _review_ready_record()
    receipt = _receipt(
        record,
        "request_more_evidence",
        reviewer="actual-reviewer@example.com",
        minute=10,
    )
    requested = apply_comprehensive_review_decision(record, manifest=receipt)
    store = _sqlite_store(tmp_path / "paired-review-history-deletion.sqlite3")
    store.create(requested)

    erased = _erase_review_request(requested)
    erased["revision"] = int(requested["revision"]) + 1
    erased["integrity_sha256"] = _record_hash(erased)
    assert validate_comprehensive_run_record(erased)["status"] == "valid"

    with pytest.raises(
        ValueError,
        match="review_history_commitment_cannot_be_truncated",
    ):
        store.save(erased, expected_revision=int(requested["revision"]))

    restored = store.load(requested["identity"]["run_id"])
    assert restored["review_history"] == [receipt]
    assert restored["review_decision"] == receipt


def test_sqlite_store_rejects_direct_payload_tamper_that_erases_review_history(
    tmp_path,
) -> None:
    record = _review_ready_record()
    receipt = _receipt(
        record,
        "request_more_evidence",
        reviewer="actual-reviewer@example.com",
        minute=11,
    )
    requested = apply_comprehensive_review_decision(record, manifest=receipt)
    database = tmp_path / "direct-review-history-tamper.sqlite3"
    store = _sqlite_store(database)
    store.create(requested)

    erased = _erase_review_request(requested)
    assert validate_comprehensive_run_record(erased)["status"] == "valid"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE nico_comprehensive_runs SET payload = ? WHERE run_id = ?",
            (
                json.dumps(erased, ensure_ascii=False, sort_keys=True),
                requested["identity"]["run_id"],
            ),
        )

    with pytest.raises(
        ValueError,
        match="review_history_commitment_cannot_be_truncated",
    ):
        store.load(requested["identity"]["run_id"])
