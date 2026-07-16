from __future__ import annotations

from nico.mid_live_progress_patch import attach_mid_live_progress


def test_mid_scanner_progress_never_regresses_below_retained_run_percent() -> None:
    result = {
        "status": "running",
        "current_stage": "scanner_worker",
        "progress_percent": 47,
        "scanner_progress_percent": 68,
        "scanner": {
            "status": "running",
            "progress_percent": 10,
            "active_tool": "semgrep",
        },
        "progress": [
            {
                "step": "scanner_worker",
                "status": "running",
                "evidence": {"scanner_progress_percent": 10},
            }
        ],
    }

    output = attach_mid_live_progress(result)

    assert output["current_stage"] == "scanner_worker"
    assert output["progress_percent"] == 47
    assert output["scanner_progress_percent"] == 68
    assert output["progress_monotonic"] is True


def test_mid_scanner_progress_advances_when_new_scan_evidence_is_higher() -> None:
    result = {
        "status": "running",
        "current_stage": "scanner_worker",
        "progress_percent": 22,
        "scanner_progress_percent": 10,
        "scanner": {
            "status": "running",
            "progress_percent": 70,
            "active_tool": "trufflehog",
        },
        "progress": [
            {
                "step": "scanner_worker",
                "status": "running",
                "evidence": {"scanner_progress_percent": 70},
            }
        ],
    }

    output = attach_mid_live_progress(result)

    assert output["progress_percent"] == 48
    assert output["scanner_progress_percent"] == 70


def test_mid_stage_handoff_cannot_regress_below_scanner_reconciliation_boundary() -> None:
    result = {
        "status": "running",
        "current_stage": "scanner_reconciliation",
        "progress_percent": 47,
        "progress": [
            {
                "step": "scanner_reconciliation",
                "status": "running",
                "evidence": {},
            }
        ],
    }

    output = attach_mid_live_progress(result)

    assert output["current_stage"] == "scanner_reconciliation"
    assert output["progress_percent"] == 62
    assert output["progress_monotonic"] is True


def test_mid_complete_result_remains_exactly_one_hundred_percent() -> None:
    result = {
        "status": "complete",
        "current_stage": "reports",
        "progress_percent": 94,
        "report_generation_status": "complete",
        "approval_request": {"approval_id": "approval_mid_1"},
    }

    output = attach_mid_live_progress(result)

    assert output["current_stage"] == "complete"
    assert output["progress_percent"] == 100
    assert output["scanner_progress_percent"] == 100
