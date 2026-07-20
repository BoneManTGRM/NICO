from __future__ import annotations

from nico.express_run_record_integrity import reconcile_record


def _complete_payload() -> dict:
    return {
        "status": "complete",
        "current_stage": "complete",
        "progress_percent": 100,
        "report_generation_status": "complete",
        "reports": {
            "pdf_base64": "JVBERi0xLjQ=",
            "markdown": "# Express",
            "html": "<h1>Express</h1>",
        },
        "express_cross_format_contract": {"status": "complete"},
        "express_pdf_renderer_truth": {"status": "complete"},
        "express_visual_qa": {"status": "pass"},
    }


def test_complete_terminal_record_carries_full_artifact_contract() -> None:
    result = reconcile_record({}, _complete_payload())
    contract = result["express_terminal_contract"]
    assert result["status"] == "complete"
    assert result["progress_percent"] == 100
    assert contract["status"] == "complete"
    assert contract["missing_requirements"] == []
    assert result["client_delivery_allowed"] is False


def test_missing_artifacts_are_explicitly_degraded_not_silently_complete() -> None:
    result = reconcile_record({}, {"status": "complete"})
    contract = result["express_terminal_contract"]
    assert result["status"] == "complete"
    assert contract["status"] == "degraded"
    assert "pdf_present" in contract["missing_requirements"]
    assert "markdown_present" in contract["missing_requirements"]
    assert "html_present" in contract["missing_requirements"]
    assert "client_delivery_block_reason" in result


def test_late_heartbeat_cannot_erase_rich_terminal_artifacts() -> None:
    existing = {"response": _complete_payload()}
    incoming = {"status": "running", "current_stage": "scanner", "progress_percent": 70}
    result = reconcile_record(existing, incoming)
    assert result["status"] == "complete"
    assert result["current_stage"] == "complete"
    assert result["progress_percent"] == 100
    assert result["reports"]["markdown"] == "# Express"
    assert result["status_regression_prevented"] is True
    assert result["express_terminal_contract"]["status"] == "complete"
