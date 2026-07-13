from __future__ import annotations

from nico.full_assessment_orchestrator import (
    FULL_ASSESSMENT_STEPS,
    default_full_assessment_handlers,
    normalize_repository_target,
    run_full_assessment_orchestration,
)


def test_normalize_repository_target_accepts_owner_repo_and_github_url() -> None:
    assert normalize_repository_target({"repository": "BoneManTGRM/NICO"}) == "BoneManTGRM/NICO"
    assert normalize_repository_target({"target": "https://github.com/BoneManTGRM/NICO"}) == "BoneManTGRM/NICO"
    assert normalize_repository_target({"target": "https://example.com/BoneManTGRM/NICO"}) == ""


def test_full_assessment_blocks_without_authorization() -> None:
    called: list[str] = []

    result = run_full_assessment_orchestration(
        {"repository": "BoneManTGRM/NICO", "authorization_confirmed": False},
        handlers={"repo_evidence": lambda _context, _outputs: called.append("repo_evidence") or {"status": "complete"}},
    )

    assert result["status"] == "blocked"
    assert result["human_review_required"] is True
    assert result["client_ready"] is False
    assert result["progress"] == [
        {"step": "authorization", "status": "blocked", "message": "Authorization confirmation is required before assessment."}
    ]
    assert called == []


def test_full_assessment_blocks_invalid_repository_target() -> None:
    result = run_full_assessment_orchestration({"repository": "https://example.com/nope", "authorization_confirmed": True})

    assert result["status"] == "blocked"
    assert result["repository"] == ""
    assert result["progress"][0]["step"] == "authorization"
    assert result["progress"][0]["status"] == "blocked"


def test_full_assessment_skeleton_preserves_step_order_and_response_shape() -> None:
    called: list[str] = []

    def handler(step: str):
        def _run(_context: dict, _outputs: dict) -> dict:
            called.append(step)
            if step == "scoring":
                return {"status": "complete", "assessment": {"maturity_signal": {"level": "Senior", "score": 91}}}
            if step == "reports":
                return {"status": "complete", "reports": {"markdown": "# NICO", "html": "<h1>NICO</h1>", "pdf_base64": "abc"}}
            if step == "approval_request":
                return {"status": "complete", "approval": {"approval_id": "approval_123", "status": "pending"}}
            return {"status": "complete"}

        return _run

    handlers = {step: handler(step) for step in FULL_ASSESSMENT_STEPS if step != "authorization"}
    result = run_full_assessment_orchestration(
        {
            "repository": "https://github.com/BoneManTGRM/NICO",
            "authorization_confirmed": True,
            "authorized_by": "frontend_reviewer",
            "customer_id": "cust-a",
            "project_id": "proj-a",
        },
        handlers=handlers,
    )

    assert result["status"] == "complete"
    assert result["repository"] == "BoneManTGRM/NICO"
    assert result["customer_id"] == "cust-a"
    assert result["project_id"] == "proj-a"
    assert result["human_review_required"] is True
    assert result["client_ready"] is False
    assert [item["step"] for item in result["progress"]] == FULL_ASSESSMENT_STEPS
    assert [item["status"] for item in result["progress"]] == ["complete"] * len(FULL_ASSESSMENT_STEPS)
    assert called == FULL_ASSESSMENT_STEPS[1:]
    assert result["assessment"]["maturity_signal"]["score"] == 91
    assert result["reports"]["pdf_base64"] == "abc"
    assert result["approval"]["approval_id"] == "approval_123"


def test_missing_handlers_are_planned_not_faked_complete() -> None:
    result = run_full_assessment_orchestration({"repository": "BoneManTGRM/NICO", "authorization_confirmed": True})

    assert result["status"] == "planned"
    assert result["progress"][0]["status"] == "complete"
    assert all(item["status"] == "planned" for item in result["progress"][1:])
    assert result["assessment"] == {}
    assert result["reports"]["pdf_base64"] == ""
    assert result["approval"]["status"] == "not_requested"


def test_default_handlers_bind_repo_and_skipped_scanner_to_run_id() -> None:
    result = run_full_assessment_orchestration(
        {
            "repository": "BoneManTGRM/NICO",
            "authorization_confirmed": True,
            "authorized_by": "tester",
            "customer_id": "cust-a",
            "project_id": "proj-a",
            "run_id": "fullrun_123",
            "run_scanners": False,
        },
        handlers=default_full_assessment_handlers(),
    )

    by_step = {item["step"]: item for item in result["progress"]}
    assert by_step["repo_evidence"]["status"] == "complete"
    assert by_step["repo_evidence"]["evidence"]["run_id"] == "fullrun_123"
    assert by_step["scanner_worker"]["status"] == "skipped"
    assert by_step["scanner_worker"]["evidence"]["run_id"] == "fullrun_123"
    assert by_step["evidence_attachment"]["status"] == "skipped"
    assert by_step["scoring"]["status"] == "blocked"
    assert by_step["reports"]["status"] == "blocked"


def test_default_handlers_queue_scanner_with_same_run_id(monkeypatch) -> None:
    seen: dict = {}

    def fake_start_scan(payload: dict) -> dict:
        seen.update(payload)
        return {
            "status": "queued",
            "scan_id": "scan_123",
            "run_id": payload["run_id"],
            "customer_id": payload["customer_id"],
            "project_id": payload["project_id"],
            "tools_requested": payload["tools"],
        }

    monkeypatch.setattr("nico.scanner_worker.start_scan", fake_start_scan)
    result = run_full_assessment_orchestration(
        {
            "repository": "BoneManTGRM/NICO",
            "authorization_confirmed": True,
            "authorized_by": "tester",
            "customer_id": "cust-a",
            "project_id": "proj-a",
            "run_id": "fullrun_456",
            "tools": ["bandit"],
        },
        handlers=default_full_assessment_handlers(),
    )

    by_step = {item["step"]: item for item in result["progress"]}
    assert result["status"] == "running"
    assert seen["run_id"] == "fullrun_456"
    assert seen["customer_id"] == "cust-a"
    assert seen["project_id"] == "proj-a"
    assert by_step["scanner_worker"]["status"] == "queued"
    assert by_step["scanner_worker"]["evidence"]["scan_id"] == "scan_123"
    assert by_step["evidence_attachment"]["status"] == "pending"
    assert by_step["scoring"]["status"] == "planned"
    assert by_step["reports"]["status"] == "planned"
    assert result["scanner"]["scan_id"] == "scan_123"


def test_completed_scanner_record_attaches_evidence_and_builds_report(monkeypatch) -> None:
    def fake_get_scan(scan_id: str) -> dict:
        return {
            "status": "complete",
            "scan_id": scan_id,
            "run_id": "fullrun_done",
            "customer_id": "cust-a",
            "project_id": "proj-a",
            "tools_requested": ["bandit", "semgrep"],
            "tools_run": ["bandit", "semgrep"],
            "unavailable_tools": [],
            "failed_tools": [],
            "timed_out_tools": [],
            "scanner_results": [
                {"scanner": "bandit", "status": "passed"},
                {"scanner": "semgrep", "status": "passed"},
            ],
            "evidence_summary": {"mode": "controlled_scanner_worker", "tools_run": 2},
            "unavailable_data_notes": [],
            "secret_redaction_applied": False,
            "retention_note": "Temporary scan workspace was deleted after completion.",
        }

    monkeypatch.setattr("nico.scanner_worker.get_scan", fake_get_scan)
    result = run_full_assessment_orchestration(
        {
            "repository": "BoneManTGRM/NICO",
            "authorization_confirmed": True,
            "authorized_by": "tester",
            "customer_id": "cust-a",
            "project_id": "proj-a",
            "run_id": "fullrun_done",
            "scan_id": "scan_done",
        },
        handlers=default_full_assessment_handlers(),
    )

    by_step = {item["step"]: item for item in result["progress"]}
    assert by_step["scanner_worker"]["status"] == "complete"
    assert by_step["evidence_attachment"]["status"] == "complete"
    assert by_step["scoring"]["status"] == "complete"
    assert by_step["reports"]["status"] == "complete"
    assert result["scanner_evidence"]["status"] == "attached"
    assert result["scanner_evidence"]["scan_id"] == "scan_done"
    assert result["scanner_evidence"]["scanner_results_count"] == 2
    assert result["assessment"]["maturity_signal"]["score"] == 90
    assert result["assessment"]["client_delivery_verdict"]["status"] == "human_review_required"
    assert result["reports"]["report_id"].startswith("report_")
    assert "NICO Client-Ready Report Package" in result["reports"]["markdown"]
    assert result["reports"]["pdf_error"]
    assert result["human_review_required"] is True
    assert result["client_ready"] is False


def test_scanner_run_id_mismatch_blocks_attachment(monkeypatch) -> None:
    monkeypatch.setattr(
        "nico.scanner_worker.get_scan",
        lambda scan_id: {"status": "complete", "scan_id": scan_id, "run_id": "other_run"},
    )

    result = run_full_assessment_orchestration(
        {
            "repository": "BoneManTGRM/NICO",
            "authorization_confirmed": True,
            "authorized_by": "tester",
            "run_id": "fullrun_expected",
            "scan_id": "scan_other",
        },
        handlers=default_full_assessment_handlers(),
    )

    by_step = {item["step"]: item for item in result["progress"]}
    assert result["status"] == "failed"
    assert by_step["scanner_worker"]["status"] == "blocked"
    assert by_step["evidence_attachment"]["status"] == "blocked"
    assert by_step["scoring"]["status"] == "blocked"
    assert by_step["reports"]["status"] == "blocked"
    assert result["scanner_evidence"]["scanner_status"] == "blocked"
