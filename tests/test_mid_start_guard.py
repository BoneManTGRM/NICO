from __future__ import annotations

from copy import deepcopy

from nico import mid_assessment_api as api
from nico import mid_start_guard as guard
from nico.storage import MemoryAdapter


def _request() -> api.MidAssessmentRunRequest:
    return api.MidAssessmentRunRequest(
        repository="https://github.com/Owner/Repository.git",
        customer_id="customer_guard",
        project_id="project_guard",
        authorization_confirmed=True,
        authorized=True,
        auto_continue=True,
    )


def _record(run_id: str = "midrun_existing_guard") -> dict:
    return {
        "run_id": run_id,
        "workflow": "mid_assessment",
        "status": "running",
        "repository": "owner/repository",
        "customer_id": "customer_guard",
        "project_id": "project_guard",
        "created_at": "2026-07-15T23:00:00Z",
        "updated_at": "2026-07-15T23:05:00Z",
        "request": {
            "repository": "owner/repository",
            "customer_id": "customer_guard",
            "project_id": "project_guard",
        },
        "response": {
            "status": "running",
            "run_id": run_id,
            "repository": "owner/repository",
            "current_stage": "scanner_worker",
            "progress_percent": 47,
            "scanner": {"scan_id": "scan_existing_guard", "status": "running"},
            "human_review_required": True,
            "client_ready": False,
        },
    }


def test_active_same_repository_run_is_reused_instead_of_starting_duplicate(monkeypatch) -> None:
    store = MemoryAdapter()
    existing = _record()
    store.put("assessment_runs", existing["run_id"], existing)
    monkeypatch.setattr(guard, "STORE", store)
    monkeypatch.setattr(
        guard,
        "_live_state",
        lambda record, customer_id, project_id: deepcopy(record["response"]),
    )
    starts = {"count": 0}

    def fake_start(_req):
        starts["count"] += 1
        return {"status": "running", "run_id": "midrun_new_should_not_exist"}

    monkeypatch.setattr(api, "mid_assessment_response", fake_start)
    result = guard.install_mid_start_guard()
    response = api.mid_assessment_response(_request())

    assert result["server_side_duplicate_prevention"] is True
    assert starts["count"] == 0
    assert response["run_id"] == existing["run_id"]
    assert response["idempotent_start_reuse"] is True
    assert response["duplicate_start_prevented"] is True
    assert response["start_guard"]["decision"] == "reuse_existing_exact_run"


def test_completed_report_and_review_run_releases_new_start(monkeypatch) -> None:
    store = MemoryAdapter()
    existing = _record()
    existing["status"] = "complete"
    existing["response"].update(
        {
            "status": "complete",
            "report_generation_status": "complete",
            "approval_request": {"approval_id": "approval_guard", "status": "pending"},
        }
    )
    existing["response"]["scanner"] = {"scan_id": "scan_existing_guard", "status": "complete"}
    store.put("assessment_runs", existing["run_id"], existing)
    monkeypatch.setattr(guard, "STORE", store)
    monkeypatch.setattr(
        guard,
        "_live_state",
        lambda record, customer_id, project_id: deepcopy(record["response"]),
    )
    starts = {"count": 0}

    def fake_start(_req):
        starts["count"] += 1
        return {"status": "running", "run_id": "midrun_new_guard"}

    monkeypatch.setattr(api, "mid_assessment_response", fake_start)
    guard.install_mid_start_guard()
    response = api.mid_assessment_response(_request())

    assert starts["count"] == 1
    assert response["run_id"] == "midrun_new_guard"


def test_recovery_required_exact_run_blocks_replacement() -> None:
    assert guard._blocks_new_start(
        {
            "status": "interrupted",
            "run_id": "midrun_recovery_guard",
            "recovery_required": True,
            "scanner": {"status": "recovery_required"},
        }
    ) is True


def test_terminal_failed_run_does_not_permanently_block_a_new_assessment() -> None:
    assert guard._blocks_new_start(
        {
            "status": "failed",
            "run_id": "midrun_failed_guard",
            "scanner": {"status": "failed"},
        }
    ) is False


def test_repository_identity_is_normalized_for_server_side_deduplication() -> None:
    assert guard._canonical_repository("https://github.com/Owner/Repository.git?x=1") == "owner/repository"
    assert guard._canonical_repository("owner/repository/") == "owner/repository"
