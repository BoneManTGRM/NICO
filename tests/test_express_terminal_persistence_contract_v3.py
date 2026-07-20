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
        "express_pdf_bar_geometry": {
            "render_mode": "reportlab_vector_geometry",
            "verification_samples": [{"score": 0, "rendered_width": 0.0}],
        },
        "express_pdf_page_layout": {"status": "complete"},
        "express_visual_qa": {"status": "pass"},
        "express_pdf_pagination": {"status": "complete"},
    }


def test_complete_terminal_record_carries_full_artifact_contract() -> None:
    result = reconcile_record({}, _complete_payload())
    contract = result["express_terminal_contract"]
    assert result["status"] == "complete"
    assert result["progress_percent"] == 100
    assert contract["status"] == "complete"
    assert contract["missing_requirements"] == []
    assert contract["fail_closed"] is True
    assert result["client_delivery_allowed"] is False


def test_missing_artifacts_and_contracts_are_explicitly_degraded() -> None:
    result = reconcile_record({}, {"status": "complete"})
    contract = result["express_terminal_contract"]
    assert result["status"] == "complete"
    assert contract["status"] == "degraded"
    for requirement in (
        "report_generation_complete",
        "pdf_present",
        "markdown_present",
        "html_present",
        "cross_format_contract_present",
        "renderer_contract_present",
        "vector_geometry_present",
        "page_layout_present",
        "visual_qa_present",
        "pagination_present",
    ):
        assert requirement in contract["missing_requirements"]
    assert "client_delivery_block_reason" in result


def test_empty_contract_objects_do_not_count_as_verified() -> None:
    payload = _complete_payload()
    payload["express_cross_format_contract"] = {}
    payload["express_pdf_renderer_truth"] = {}
    payload["express_visual_qa"] = {}
    result = reconcile_record({}, payload)
    missing = result["express_terminal_contract"]["missing_requirements"]
    assert "cross_format_contract_present" in missing
    assert "cross_format_complete" in missing
    assert "renderer_contract_present" in missing
    assert "renderer_complete" in missing
    assert "visual_qa_present" in missing
    assert "visual_qa_passed" in missing


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
