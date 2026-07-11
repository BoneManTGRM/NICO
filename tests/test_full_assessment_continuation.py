from __future__ import annotations

from nico.full_assessment_continuation import (
    apply_full_assessment_continuation,
    plan_full_assessment_continuation,
)
from nico.storage import MemoryAdapter


def _record(**overrides):
    record = {
        "run_id": "fullrun_auto",
        "customer_id": "cust-a",
        "project_id": "proj-a",
        "repository": "BoneManTGRM/NICO",
        "scan_id": "scan-auto",
        "report_id": "",
        "approval_id": "",
        "request": {
            "repository": "BoneManTGRM/NICO",
            "authorization_confirmed": True,
            "authorized": True,
            "authorized_by": "tester",
            "customer_id": "cust-a",
            "project_id": "proj-a",
            "build_reports": True,
            "create_final_review_request": True,
            "auto_continue": True,
        },
    }
    record.update(overrides)
    return record


def _payload():
    return {
        "run_id": "fullrun_auto",
        "scan_id": "scan-auto",
        "repository": "BoneManTGRM/NICO",
        "authorization_confirmed": True,
        "authorized": True,
        "authorized_by": "tester",
        "customer_id": "cust-a",
        "project_id": "proj-a",
    }


def test_completed_scanner_enables_saved_report_and_review_steps() -> None:
    plan = plan_full_assessment_continuation(
        _payload(),
        _record(),
        auto_continue=True,
        scan_loader=lambda scan_id: {"scan_id": scan_id, "run_id": "fullrun_auto", "status": "complete"},
    )

    assert plan["should_continue"] is True
    assert plan["payload"]["build_reports"] is True
    assert plan["payload"]["create_final_review_request"] is True
    assert plan["reuse_report"] is False
    assert plan["reuse_approval"] is False


def test_running_scanner_keeps_downstream_steps_disabled() -> None:
    plan = plan_full_assessment_continuation(
        _payload(),
        _record(),
        auto_continue=True,
        scan_loader=lambda scan_id: {"scan_id": scan_id, "run_id": "fullrun_auto", "status": "running"},
    )

    assert plan["should_continue"] is False
    assert plan["payload"]["build_reports"] is False
    assert plan["payload"]["create_final_review_request"] is False
    assert "still running" in plan["reason"]


def test_scanner_run_mismatch_blocks_continuation() -> None:
    plan = plan_full_assessment_continuation(
        _payload(),
        _record(),
        auto_continue=True,
        scan_loader=lambda scan_id: {"scan_id": scan_id, "run_id": "other-run", "status": "complete"},
    )

    assert plan["should_continue"] is False
    assert plan["same_run"] is False
    assert "does not match" in plan["reason"]


def test_saved_auto_continue_false_is_respected_by_planner() -> None:
    plan = plan_full_assessment_continuation(
        _payload(),
        _record(),
        auto_continue=False,
        scan_loader=lambda scan_id: {"scan_id": scan_id, "run_id": "fullrun_auto", "status": "complete"},
    )

    assert plan["should_continue"] is False
    assert plan["payload"]["build_reports"] is False
    assert plan["payload"]["create_final_review_request"] is False
    assert "explicitly disabled" in plan["reason"]


def test_existing_report_and_approval_are_reused() -> None:
    plan = plan_full_assessment_continuation(
        _payload(),
        _record(report_id="report-existing", approval_id="approval-existing"),
        auto_continue=True,
        scan_loader=lambda scan_id: {"scan_id": scan_id, "run_id": "fullrun_auto", "status": "complete"},
    )

    assert plan["reuse_report"] is True
    assert plan["reuse_approval"] is True
    assert plan["payload"]["build_reports"] is False
    assert plan["payload"]["create_final_review_request"] is False


def test_existing_report_can_create_missing_review_without_duplicate_report() -> None:
    store = MemoryAdapter()
    store.put(
        "reports",
        "report-existing",
        {
            "report_id": "report-existing",
            "run_id": "fullrun_auto",
            "customer_id": "cust-a",
            "project_id": "proj-a",
            "status": "complete",
            "formats": {"markdown": "# Existing", "html": "<h1>Existing</h1>", "json": {}},
        },
    )
    plan = plan_full_assessment_continuation(
        _payload(),
        _record(report_id="report-existing"),
        auto_continue=True,
        scan_loader=lambda scan_id: {"scan_id": scan_id, "run_id": "fullrun_auto", "status": "complete"},
    )
    result = {
        "status": "complete",
        "run_id": "fullrun_auto",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "cust-a",
        "project_id": "proj-a",
        "reports": {},
        "approval": {"status": "not_requested"},
        "progress": [
            {"step": "authorization", "status": "complete"},
            {"step": "repo_evidence", "status": "complete"},
            {"step": "scanner_worker", "status": "complete"},
            {"step": "evidence_attachment", "status": "complete"},
            {"step": "scoring", "status": "complete"},
            {"step": "reports", "status": "skipped"},
            {"step": "approval_request", "status": "skipped"},
        ],
    }

    updated = apply_full_assessment_continuation(
        result,
        plan,
        store=store,
        review_requester=lambda payload: {
            "status": "pending_review",
            "approval": {
                "approval_id": "approval-new",
                "status": "pending",
                "requested_action": "final_report_approval",
                "run_id": payload["run_id"],
                "report_id": payload["report_id"],
            },
        },
    )

    by_step = {item["step"]: item for item in updated["progress"]}
    assert updated["reports"]["report_id"] == "report-existing"
    assert updated["reports"]["markdown"] == "# Existing"
    assert updated["approval"]["approval_id"] == "approval-new"
    assert by_step["reports"]["status"] == "complete"
    assert by_step["reports"]["evidence"]["reused"] is True
    assert by_step["approval_request"]["status"] == "complete"
    assert updated["status"] == "complete"
    assert updated["auto_continuation"]["continued"] is True
