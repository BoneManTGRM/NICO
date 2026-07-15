from __future__ import annotations

from copy import deepcopy

from nico import mid_assessment_api as api
from nico import mid_status_read_path as read_path


def _record() -> dict:
    return {
        "run_id": "midrun_fast_status_test",
        "workflow": "mid_assessment",
        "status": "running",
        "repository": "owner/repository",
        "customer_id": "customer_fast",
        "project_id": "project_fast",
        "scan_id": "scan_snapshot_fast_status",
        "snapshot_id": "snapshot_fast_status",
        "snapshot_commit_sha": "a" * 40,
        "request": {
            "repository": "owner/repository",
            "customer_id": "customer_fast",
            "project_id": "project_fast",
            "scan_id": "scan_snapshot_fast_status",
            "authorization_confirmed": True,
            "authorized": True,
            "auto_continue": True,
        },
        "response": {
            "status": "running",
            "run_id": "midrun_fast_status_test",
            "repository": "owner/repository",
            "customer_id": "customer_fast",
            "project_id": "project_fast",
            "assessment_type": "mid",
            "service_tier": "mid",
            "report_generation_status": "mid_report_generation_pending",
            "repository_snapshot": {
                "status": "attached",
                "snapshot_id": "snapshot_fast_status",
                "commit_sha": "a" * 40,
            },
            "repository_evidence": {"status": "attached", "evidence_id": "evidence_fast_status"},
            "progress": [
                {"step": "repo_evidence", "status": "complete", "message": "Repository evidence attached."},
                {"step": "scanner_worker", "status": "running", "message": "Scanner is running."},
                {"step": "evidence_attachment", "status": "pending", "message": "Waiting for scanner."},
                {"step": "scoring", "status": "planned", "message": "Waiting for evidence."},
                {"step": "reports", "status": "planned", "message": "Waiting for scoring."},
                {"step": "approval_request", "status": "planned", "message": "Waiting for report."},
            ],
            "human_review_required": True,
            "client_ready": False,
        },
    }


def _request() -> api.MidAssessmentStatusRequest:
    return api.MidAssessmentStatusRequest(
        repository="owner/repository",
        scan_id="scan_snapshot_fast_status",
        customer_id="customer_fast",
        project_id="project_fast",
        authorization_confirmed=True,
        authorized=True,
        auto_continue=True,
    )


def test_active_scanner_status_uses_durable_read_path_without_repository_recapture(monkeypatch) -> None:
    record = _record()
    scanner = {
        "scan_id": "scan_snapshot_fast_status",
        "run_id": "midrun_fast_status_test",
        "repository": "owner/repository",
        "customer_id": "customer_fast",
        "project_id": "project_fast",
        "status": "running",
        "current_stage": "scanner_suite",
        "progress_percent": 67,
        "active_tool": "trufflehog",
        "tools_requested": ["pip-audit", "bandit", "gitleaks", "trufflehog"],
        "tools_run": ["pip-audit", "bandit", "gitleaks"],
        "snapshot_id": "snapshot_fast_status",
        "snapshot_commit_sha": "a" * 40,
        "updated_at": "2026-07-15T22:00:00Z",
    }

    monkeypatch.setattr(
        read_path,
        "build_mid_status_payload",
        lambda run_id, request_payload, explicit: (
            {**deepcopy(record["request"]), "run_id": run_id, "mode": "mid"},
            deepcopy(record),
        ),
    )
    monkeypatch.setattr(read_path, "get_scan", lambda scan_id: deepcopy(scanner))

    # Any repository recapture would prove the endpoint re-entered the heavy
    # orchestration path while the scanner was still active.
    import nico.snapshot_assessment_handlers as snapshot_handlers

    monkeypatch.setattr(
        snapshot_handlers,
        "capture_repository_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("repository recaptured during status poll")),
    )

    result = api.mid_assessment_status_response("midrun_fast_status_test", _request())

    assert result["status"] == "running"
    assert result["run_id"] == "midrun_fast_status_test"
    assert result["scanner"]["status"] == "running"
    assert result["scanner"]["active_tool"] == "trufflehog"
    assert result["scanner_progress_percent"] == 67
    assert result["progress_percent"] == 47
    assert result["repository_evidence"]["evidence_id"] == "evidence_fast_status"
    assert result["status_read_path"] == {
        "version": read_path.MID_STATUS_READ_PATH_VERSION,
        "mode": "durable_scanner_read",
        "orchestrator_reentered": False,
        "repository_recaptured": False,
        "assessment_run_rewritten": False,
        "read_only": True,
    }
    scanner_step = next(item for item in result["progress"] if item["step"] == "scanner_worker")
    assert scanner_step["status"] == "running"
    assert "trufflehog" in scanner_step["message"]


def test_final_mid_status_reuses_retained_final_artifacts_without_scanner_or_orchestrator(monkeypatch) -> None:
    record = _record()
    record["status"] = "complete"
    record["response"].update(
        {
            "status": "complete",
            "report_generation_status": "complete",
            "approval_request": {"approval_id": "approval_fast_status", "status": "pending"},
            "mid_report": {"report_id": "report_fast_status", "status": "complete"},
        }
    )

    monkeypatch.setattr(
        read_path,
        "build_mid_status_payload",
        lambda run_id, request_payload, explicit: (
            {**deepcopy(record["request"]), "run_id": run_id, "mode": "mid"},
            deepcopy(record),
        ),
    )
    monkeypatch.setattr(
        read_path,
        "get_scan",
        lambda _scan_id: (_ for _ in ()).throw(AssertionError("final retained status should not reload scanner")),
    )

    result = api.mid_assessment_status_response("midrun_fast_status_test", _request())

    assert result["status"] == "complete"
    assert result["progress_percent"] == 100
    assert result["approval_request"]["approval_id"] == "approval_fast_status"
    assert result["mid_report"]["report_id"] == "report_fast_status"
    assert result["status_read_path"]["mode"] == "retained_final"
    assert result["status_read_path"]["orchestrator_reentered"] is False


def test_status_fast_path_preserves_typed_fastapi_signature() -> None:
    import inspect

    signature = inspect.signature(api.mid_assessment_status_response)

    assert signature.parameters["run_id"].annotation is str
    assert signature.parameters["req"].annotation is api.MidAssessmentStatusRequest
