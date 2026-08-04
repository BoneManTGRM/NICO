from __future__ import annotations

from nico import comprehensive_run_service as service_module
from nico.comprehensive_final_report_execution_boundary_v4 import FINAL_REPORT_STAGE_ID
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_service import ComprehensiveRunService


class _Store:
    def save(self, record, *, expected_revision):
        assert expected_revision == 7
        return record


def _record() -> dict:
    final_index = COMPREHENSIVE_STAGES.index(FINAL_REPORT_STAGE_ID)
    completed = list(COMPREHENSIVE_STAGES[:final_index])
    stage_results = {
        stage_id: {
            "status": "complete",
            "evidence": {"marker": object()},
        }
        for stage_id in completed
    }
    return {
        "artifact_schema": "nico.comprehensive-run.v1",
        "identity": {
            "run_id": "comprun_final_context",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "2c059af469fedcf3664a3f431fd1a51bcb145f91",
            "evidence_ledger_id": "ledger_final_context",
            "customer_id": "customer",
            "project_id": "project",
            "assessment_depth": "strategic",
            "report_language": "en",
        },
        "completed_stages": completed,
        "stage_results": stage_results,
        "human_evidence": {},
        "recovery_history": [],
        "revision": 7,
        "terminal": False,
    }


def test_final_stage_uses_loaded_stage_result_snapshot_by_reference(monkeypatch) -> None:
    record = _record()
    observed: dict = {}

    def final_executor(context):
        raise AssertionError("executor should be intercepted by the atomic boundary")

    def execute_final_report_stage(executor, context):
        observed["executor"] = executor
        observed["context"] = context
        return {
            "status": "blocked",
            "reason": "test_boundary",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    def apply_result(source, *, stage_id, result):
        assert stage_id == FINAL_REPORT_STAGE_ID
        assert result["reason"] == "test_boundary"
        return {**source, "revision": 8, "captured_result": result}

    monkeypatch.setattr(
        service_module,
        "execute_final_report_stage",
        execute_final_report_stage,
    )
    monkeypatch.setattr(
        service_module,
        "apply_comprehensive_stage_result",
        apply_result,
    )

    service = object.__new__(ComprehensiveRunService)
    service._store = _Store()
    service._stage_executors = {FINAL_REPORT_STAGE_ID: final_executor}

    updated = service._run_next_stage(record)

    assert observed["executor"] is final_executor
    assert observed["context"]["prior_stage_results"] is record["stage_results"]
    assert observed["context"]["human_review_required"] is True
    assert observed["context"]["client_delivery_allowed"] is False
    assert updated["captured_result"]["status"] == "blocked"


def test_nonfinal_stage_still_receives_an_isolated_copy(monkeypatch) -> None:
    first_stage = COMPREHENSIVE_STAGES[0]
    record = _record()
    record["completed_stages"] = []
    record["stage_results"] = {"retained": {"status": "complete"}}
    observed: dict = {}

    def executor(context):
        return {
            "status": "complete",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    def execute_stage(executor_value, context, *, stage_id):
        observed["context"] = context
        assert stage_id == first_stage
        return executor_value(context)

    def apply_result(source, *, stage_id, result):
        return {**source, "revision": 8, "captured_result": result}

    monkeypatch.setattr(service_module, "execute_stage_with_timeout", execute_stage)
    monkeypatch.setattr(service_module, "apply_stage_watchdog", lambda record, **kwargs: kwargs["result"])
    monkeypatch.setattr(service_module, "apply_comprehensive_stage_result", apply_result)

    service = object.__new__(ComprehensiveRunService)
    service._store = _Store()
    service._stage_executors = {first_stage: executor}

    service._run_next_stage(record)

    assert observed["context"]["prior_stage_results"] == record["stage_results"]
    assert observed["context"]["prior_stage_results"] is not record["stage_results"]
