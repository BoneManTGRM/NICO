from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.assessment_execution_checkpoints import (
    ASSESSMENT_CHECKPOINT_SCHEMA,
    build_checkpoint_result,
    make_checkpoint_writer,
    persist_assessment_checkpoint,
)


class _Store:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}

    def status(self) -> dict[str, Any]:
        return {"adapter": "postgres", "persistence_available": True}

    def get(self, table: str, item_id: str) -> dict[str, Any] | None:
        assert table == "assessment_runs"
        value = self.records.get(item_id)
        return deepcopy(value) if value else None

    def put(self, table: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert table == "assessment_runs"
        self.records[item_id] = deepcopy(payload)
        return deepcopy(payload)


def _result(run_id: str = "fullrun_1234567890abcdef") -> dict[str, Any]:
    return {
        "status": "planned",
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_1",
        "project_id": "project_1",
        "progress": [
            {"step": "authorization", "status": "complete"},
            {"step": "repo_evidence", "status": "complete"},
            {"step": "scanner_worker", "status": "running"},
        ],
        "scanner": {"scan_id": "scan_123", "status": "running"},
        "reports": {"pdf_base64": "do-not-retain", "report_id": ""},
        "approval": {},
    }


def test_checkpoint_result_records_heartbeat_completed_steps_and_hash() -> None:
    checkpointed = build_checkpoint_result(
        _result(),
        step="scanner_worker",
        phase="step_started",
        recovery_attempt=2,
    )

    assert checkpointed["status"] == "running"
    checkpoint = checkpointed["execution_checkpoint"]
    assert checkpoint["artifact_schema"] == ASSESSMENT_CHECKPOINT_SCHEMA
    assert checkpoint["current_step"] == "scanner_worker"
    assert checkpoint["phase"] == "step_started"
    assert checkpoint["completed_steps"] == ["authorization", "repo_evidence"]
    assert len(checkpoint["progress_sha256"]) == 64
    assert checkpoint["recovery_attempt"] == 2
    assert checkpointed["recovery"]["state"] == "active"
    assert checkpointed["client_delivery_allowed"] is False


def test_final_checkpoint_preserves_terminal_status() -> None:
    result = _result()
    result["status"] = "complete"

    checkpointed = build_checkpoint_result(
        result,
        step="orchestration",
        phase="orchestration_finalized",
    )

    assert checkpointed["status"] == "complete"
    assert checkpointed["recovery"]["state"] == "complete"


def test_checkpoint_persistence_preserves_scope_and_strips_pdf_bytes() -> None:
    store = _Store()
    payload = {
        "run_id": "fullrun_1234567890abcdef",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_1",
        "project_id": "project_1",
        "authorized_by": "owner",
        "authorization_scope": "repository assessment only",
        "authorization_confirmed": True,
        "build_reports": True,
        "create_final_review_request": True,
    }
    checkpointed = build_checkpoint_result(
        _result(),
        step="scanner_worker",
        phase="step_completed",
    )

    stored = persist_assessment_checkpoint(
        checkpointed,
        payload,
        workflow="full_assessment",
        service_tier="full",
        store=store,
    )

    assert stored["workflow"] == "full_assessment"
    assert stored["run_id"] == payload["run_id"]
    assert stored["customer_id"] == "customer_1"
    assert stored["project_id"] == "project_1"
    assert stored["scan_id"] == "scan_123"
    assert stored["request"]["build_reports"] is True
    assert stored["response"]["reports"]["pdf_base64"] == ""
    assert "do-not-retain" not in repr(stored)


def test_completion_intent_remains_monotonic_across_polling_checkpoints() -> None:
    store = _Store()
    initial = {
        "run_id": "fullrun_1234567890abcdef",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_1",
        "project_id": "project_1",
        "authorized_by": "owner",
        "authorization_scope": "repository assessment only",
        "authorization_confirmed": True,
        "build_reports": True,
        "create_final_review_request": True,
    }
    writer = make_checkpoint_writer(
        initial,
        workflow="full_assessment",
        service_tier="full",
        store=store,
    )
    writer(_result(), "preflight", "preflight")

    polling = dict(initial)
    polling["build_reports"] = False
    polling["create_final_review_request"] = False
    polling_writer = make_checkpoint_writer(
        polling,
        workflow="full_assessment",
        service_tier="full",
        store=store,
    )
    polling_writer(_result(), "scanner_worker", "step_started")

    record = store.records[initial["run_id"]]
    assert record["request"]["build_reports"] is True
    assert record["request"]["create_final_review_request"] is True
