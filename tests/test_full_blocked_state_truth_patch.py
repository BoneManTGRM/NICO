from __future__ import annotations

import nico.full_assessment_orchestrator as orchestrator


def _context(**overrides):
    context = {
        "run_id": "fullrun_truth",
        "build_reports": True,
        "create_final_review_request": True,
    }
    context.update(overrides)
    return context


def test_unavailable_scanner_evidence_blocks_downstream_stages() -> None:
    scoring = orchestrator._scoring_handler(
        _context(),
        {
            "evidence_attachment": {
                "status": "unavailable",
                "evidence": {"status": "unavailable"},
            }
        },
    )
    reports = orchestrator._reports_handler(_context(), {"scoring": scoring})
    approval = orchestrator._approval_request_handler(_context(), {"reports": reports})

    assert scoring["status"] == "blocked"
    assert reports["status"] == "blocked"
    assert approval["status"] == "blocked"
    assert "not skipped by request" in scoring["message"]
    assert "not skipped by request" in reports["message"]
    assert "not skipped by request" in approval["message"]
    assert scoring["evidence"]["blocked_by_upstream"] is True
    assert reports["evidence"]["upstream_status"] == "blocked"
    assert approval["evidence"]["upstream_status"] == "blocked"


def test_pending_scanner_evidence_remains_pending_not_blocked() -> None:
    result = orchestrator._scoring_handler(
        _context(),
        {
            "evidence_attachment": {
                "status": "pending",
                "evidence": {"status": "pending"},
            }
        },
    )

    assert result["status"] == "planned"
    assert "waits for completed same-run scanner evidence" in result["message"]


def test_explicitly_disabled_report_and_review_stages_remain_skipped() -> None:
    reports = orchestrator._reports_handler(
        _context(build_reports=False),
        {"scoring": {"status": "blocked"}},
    )
    approval = orchestrator._approval_request_handler(
        _context(create_final_review_request=False),
        {"reports": {"status": "blocked"}},
    )

    assert reports["status"] == "skipped"
    assert reports["message"] == "Report generation was skipped by request."
    assert approval["status"] == "skipped"
    assert approval["message"] == "Final review request was skipped by request."


def test_full_orchestration_reports_blockers_as_failed_run() -> None:
    handlers = orchestrator.default_full_assessment_handlers()
    handlers["repo_evidence"] = lambda context, outputs: {
        "status": "complete",
        "message": "repository evidence attached",
    }
    handlers["scanner_worker"] = lambda context, outputs: {
        "status": "unavailable",
        "message": "scanner unavailable",
        "scan": {"scan_id": "scan_missing", "status": "not_found"},
        "evidence": {"run_id": context["run_id"], "scan_id": "scan_missing"},
    }

    result = orchestrator.run_full_assessment_orchestration(
        {
            "repository": "example/repository",
            "authorization_confirmed": True,
            "authorized_by": "authorized_operator",
            "build_reports": True,
            "create_final_review_request": True,
        },
        handlers=handlers,
    )

    statuses = {item["step"]: item["status"] for item in result["progress"]}
    assert statuses["scanner_worker"] == "unavailable"
    assert statuses["evidence_attachment"] == "unavailable"
    assert statuses["scoring"] == "blocked"
    assert statuses["reports"] == "blocked"
    assert statuses["approval_request"] == "blocked"
    assert result["status"] == "failed"
    assert result["human_review_required"] is True
    assert result["client_ready"] is False
