from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import ComprehensiveRunStore


def _store(path: Path) -> ComprehensiveRunStore:
    store = ComprehensiveRunStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    return store


def _executors() -> dict[str, object]:
    result = {}
    for item in execution_plan():
        capability = item["capability"]

        def execute(context, *, _capability=capability):
            return {
                "status": "complete",
                "capability": _capability,
                "run_id": context["run_id"],
                "repository": context["repository"],
                "commit_sha": context["commit_sha"],
                "evidence_ledger_id": context["evidence_ledger_id"],
                "prior_count": len(context["prior_stage_results"]),
            }

        result[capability] = execute
    return result


def _start(service: ComprehensiveRunService) -> dict:
    return service.start(
        run_id="comprun_001",
        repository="BoneManTGRM/NICO",
        commit_sha="abc123",
        evidence_ledger_id="ledger_001",
        customer_id="customer_001",
        project_id="project_001",
        authorized=True,
    )


def test_service_persists_each_stage_and_resumes_after_restart(tmp_path: Path) -> None:
    database = tmp_path / "runs.db"
    first = ComprehensiveRunService(_store(database), _executors())
    _start(first)

    partial = first.resume("comprun_001", max_stages=3)
    assert partial["completed_stages"] == list(COMPREHENSIVE_STAGES[:3])
    assert partial["revision"] == 4
    assert partial["terminal"] is False

    restarted = ComprehensiveRunService(_store(database), _executors())
    final = restarted.run_to_review("comprun_001")

    assert final["completed_stages"] == list(COMPREHENSIVE_STAGES)
    assert final["status"] == "review_required"
    assert final["terminal"] is True
    assert final["progress_percent"] == 100.0
    assert final["human_review_required"] is True
    assert final["client_delivery_allowed"] is False


def test_prior_stage_evidence_is_forwarded_in_order(tmp_path: Path) -> None:
    service = ComprehensiveRunService(_store(tmp_path / "runs.db"), _executors())
    _start(service)
    final = service.resume("comprun_001", max_stages=4)

    for index, stage_id in enumerate(COMPREHENSIVE_STAGES[:4]):
        assert final["stage_results"][stage_id]["prior_count"] == index


def test_missing_capability_blocks_without_false_progress(tmp_path: Path) -> None:
    executors = _executors()
    first_capability = execution_plan()[0]["capability"]
    executors.pop(first_capability)
    service = ComprehensiveRunService(_store(tmp_path / "runs.db"), executors)
    _start(service)

    blocked = service.run_to_review("comprun_001")

    assert blocked["status"] == "blocked"
    assert blocked["terminal"] is True
    assert blocked["completed_stages"] == []
    assert blocked["progress_percent"] == 0.0
    assert blocked["stage_results"][COMPREHENSIVE_STAGES[0]]["reason"].startswith("missing_executor:")
    assert blocked["client_delivery_allowed"] is False


def test_terminal_record_is_idempotent_on_resume(tmp_path: Path) -> None:
    service = ComprehensiveRunService(_store(tmp_path / "runs.db"), _executors())
    _start(service)
    final = service.run_to_review("comprun_001")
    resumed = service.resume("comprun_001")

    assert resumed == final


def test_authorization_is_required_before_persistence(tmp_path: Path) -> None:
    service = ComprehensiveRunService(_store(tmp_path / "runs.db"), _executors())

    with pytest.raises(ValueError, match="explicit_authorization_required"):
        service.start(
            run_id="comprun_denied",
            repository="BoneManTGRM/NICO",
            commit_sha="abc123",
            evidence_ledger_id="ledger_denied",
            customer_id="customer_001",
            project_id="project_001",
            authorized=False,
        )


def test_identity_drift_is_rejected_before_save(tmp_path: Path) -> None:
    executors = _executors()
    first_capability = execution_plan()[0]["capability"]

    def drifting(context):
        return {"status": "complete", "commit_sha": "different"}

    executors[first_capability] = drifting
    service = ComprehensiveRunService(_store(tmp_path / "runs.db"), executors)
    _start(service)

    with pytest.raises(ValueError, match="commit_sha_identity_drift"):
        service.resume("comprun_001", max_stages=1)

    unchanged = service.load("comprun_001")
    assert unchanged["revision"] == 1
    assert unchanged["completed_stages"] == []
