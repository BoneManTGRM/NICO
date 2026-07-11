from __future__ import annotations

import nico.approval_queue as approval_queue
import nico.final_review_workflow as final_review_workflow
import nico.reports as reports
from nico.full_assessment_idempotency import (
    full_run_approval_identity,
    full_run_report_identity,
)
from nico.storage import MemoryAdapter


def _assessment(run_id: str) -> dict:
    return {
        "status": "draft",
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "cust-a",
        "project_id": "proj-a",
        "client_name": "Client A",
        "project_name": "Project A",
        "source_scope": "BoneManTGRM/NICO",
        "authorization_statement": "Authorized repository assessment.",
        "executive_summary": "Evidence-bound draft assessment.",
        "maturity_signal": {"level": "Evidence Attached", "score": 90},
        "client_delivery_verdict": {
            "status": "human_review_required",
            "confidence": "limited",
            "blockers": ["Human approval required."],
            "unavailable_items": 0,
        },
        "sections": [],
        "findings": [],
        "unavailable_data_notes": [],
        "next_steps": ["Request final review."],
        "truthfulness_rules": ["Completed evidence only"],
        "human_review_required": True,
    }


def _patch_store(monkeypatch, store: MemoryAdapter) -> None:
    monkeypatch.setattr(reports, "STORE", store)
    monkeypatch.setattr(approval_queue, "STORE", store)
    monkeypatch.setattr(final_review_workflow, "STORE", store)


def test_full_run_artifact_identities_are_stable_and_scan_bound() -> None:
    first = full_run_report_identity("fullrun_a", "scan_a")
    same = full_run_report_identity("fullrun_a", "scan_a")
    different_scan = full_run_report_identity("fullrun_a", "scan_b")

    assert first == same
    assert first["report_id"].startswith("report_fullrun_")
    assert first["report_id"] != different_scan["report_id"]
    assert first["idempotency_key"] != different_scan["idempotency_key"]

    approval = full_run_approval_identity("fullrun_a", first["report_id"])
    approval_same = full_run_approval_identity("fullrun_a", first["report_id"])
    assert approval == approval_same
    assert approval["approval_id"].startswith("approval_fullrun_")


def test_report_package_reuses_same_run_and_scan_record(monkeypatch) -> None:
    store = MemoryAdapter()
    _patch_store(monkeypatch, store)
    identity = full_run_report_identity("fullrun_report", "scan_report")

    first = reports.build_report_package(
        _assessment("fullrun_report"),
        report_id=identity["report_id"],
        idempotency_key=identity["idempotency_key"],
    )
    second = reports.build_report_package(
        _assessment("fullrun_report"),
        report_id=identity["report_id"],
        idempotency_key=identity["idempotency_key"],
    )

    assert first["report_id"] == second["report_id"]
    assert first["idempotent_reuse"] is False
    assert second["idempotent_reuse"] is True
    assert len(store.list("reports")) == 1


def test_final_review_reuses_same_report_approval(monkeypatch) -> None:
    store = MemoryAdapter()
    _patch_store(monkeypatch, store)
    report_identity = full_run_report_identity("fullrun_review", "scan_review")
    reports.build_report_package(
        _assessment("fullrun_review"),
        report_id=report_identity["report_id"],
        idempotency_key=report_identity["idempotency_key"],
    )
    approval_identity = full_run_approval_identity("fullrun_review", report_identity["report_id"])
    payload = {
        "approval_id": approval_identity["approval_id"],
        "idempotency_key": approval_identity["idempotency_key"],
        "run_id": "fullrun_review",
        "report_id": report_identity["report_id"],
        "customer_id": "cust-a",
        "project_id": "proj-a",
        "repository": "BoneManTGRM/NICO",
        "requester": "test",
    }

    first = final_review_workflow.request_final_review(payload)
    second = final_review_workflow.request_final_review(payload)

    assert first["approval"]["approval_id"] == second["approval"]["approval_id"]
    assert first["idempotent_reuse"] is False
    assert second["idempotent_reuse"] is True
    assert len(store.list("approvals")) == 1


def test_idempotent_review_reuse_preserves_human_approval(monkeypatch) -> None:
    store = MemoryAdapter()
    _patch_store(monkeypatch, store)
    report_identity = full_run_report_identity("fullrun_approved", "scan_approved")
    reports.build_report_package(
        _assessment("fullrun_approved"),
        report_id=report_identity["report_id"],
        idempotency_key=report_identity["idempotency_key"],
    )
    approval_identity = full_run_approval_identity("fullrun_approved", report_identity["report_id"])
    payload = {
        "approval_id": approval_identity["approval_id"],
        "idempotency_key": approval_identity["idempotency_key"],
        "run_id": "fullrun_approved",
        "report_id": report_identity["report_id"],
        "customer_id": "cust-a",
        "project_id": "proj-a",
        "repository": "BoneManTGRM/NICO",
        "requester": "test",
    }

    first = final_review_workflow.request_final_review(payload)
    approval_queue.transition_approval(first["approval"]["approval_id"], "approved", actor="human-reviewer")
    reused = final_review_workflow.request_final_review(payload)

    assert reused["idempotent_reuse"] is True
    assert reused["approval"]["status"] == "approved"
    assert reused["approval"]["approver"] == "human-reviewer"
    assert len(store.list("approvals")) == 1
