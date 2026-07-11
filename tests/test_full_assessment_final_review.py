from __future__ import annotations

from nico.full_assessment_orchestrator import default_full_assessment_handlers, run_full_assessment_orchestration


def _completed_scan(scan_id: str) -> dict:
    return {
        "status": "complete",
        "scan_id": scan_id,
        "run_id": "fullrun_review",
        "customer_id": "cust-a",
        "project_id": "proj-a",
        "tools_requested": ["bandit"],
        "tools_run": ["bandit"],
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "scanner_results": [{"scanner": "bandit", "status": "passed"}],
        "evidence_summary": {"mode": "controlled_scanner_worker", "tools_run": 1},
        "unavailable_data_notes": [],
        "secret_redaction_applied": False,
        "retention_note": "Temporary scan workspace was deleted after completion.",
    }


def test_full_run_creates_final_review_request_after_report(monkeypatch) -> None:
    seen: dict = {}

    monkeypatch.setattr("nico.scanner_worker.get_scan", _completed_scan)

    def fake_request_final_review(payload: dict) -> dict:
        seen.update(payload)
        return {
            "status": "pending_review",
            "approval": {
                "approval_id": "approval_final_123",
                "status": "pending",
                "requested_action": "final_report_approval",
                "run_id": payload["run_id"],
                "report_id": payload["report_id"],
            },
            "review": {"review_status": "pending", "approval_id": "approval_final_123"},
        }

    monkeypatch.setattr("nico.final_review_workflow.request_final_review", fake_request_final_review)

    result = run_full_assessment_orchestration(
        {
            "repository": "BoneManTGRM/NICO",
            "authorization_confirmed": True,
            "authorized_by": "tester",
            "customer_id": "cust-a",
            "project_id": "proj-a",
            "run_id": "fullrun_review",
            "scan_id": "scan_review",
        },
        handlers=default_full_assessment_handlers(),
    )

    by_step = {item["step"]: item for item in result["progress"]}
    assert result["status"] == "complete"
    assert by_step["approval_request"]["status"] == "complete"
    assert result["approval"]["approval_id"] == "approval_final_123"
    assert result["approval"]["requested_action"] == "final_report_approval"
    assert result["approval"]["status"] == "pending"
    assert result["approval"]["run_id"] == "fullrun_review"
    assert result["approval"]["report_id"] == result["reports"]["report_id"]
    assert seen["customer_id"] == "cust-a"
    assert seen["project_id"] == "proj-a"
    assert seen["run_id"] == "fullrun_review"
    assert seen["report_id"] == result["reports"]["report_id"]
    assert seen["risk_level"] == "delivery_review"
    assert "human reviewer approves" in " ".join(seen["evidence"])
    assert result["human_review_required"] is True
    assert result["client_ready"] is False


def test_full_run_final_review_request_can_be_skipped(monkeypatch) -> None:
    monkeypatch.setattr("nico.scanner_worker.get_scan", _completed_scan)

    result = run_full_assessment_orchestration(
        {
            "repository": "BoneManTGRM/NICO",
            "authorization_confirmed": True,
            "authorized_by": "tester",
            "run_id": "fullrun_review",
            "scan_id": "scan_review",
            "create_final_review_request": False,
        },
        handlers=default_full_assessment_handlers(),
    )

    by_step = {item["step"]: item for item in result["progress"]}
    assert by_step["reports"]["status"] == "complete"
    assert by_step["approval_request"]["status"] == "skipped"
    assert result["approval"]["status"] == "not_requested"
    assert result["client_ready"] is False
