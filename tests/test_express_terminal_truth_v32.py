from nico import express_client_report_postprocessor_v27 as target
from nico.express_client_report_postprocessor_v31_compat import (
    _normalize_not_scored_sections,
    _reconcile_terminal_progress,
    install_express_client_report_postprocessor_v31_compat,
)


def _result() -> dict:
    return {
        "status": "complete",
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 86,
                "status": "green",
            },
            {
                "id": "scanner_worker_evidence",
                "label": "Scanner Worker Evidence",
                "score": None,
                "presented_score": 0,
                "status": "supplemental",
                "directly_scored": False,
            },
            {
                "id": "client_acceptance",
                "label": "Client / Human Acceptance",
                "score": 0,
                "presented_score": 0,
                "status": "gray",
                "directly_scored": False,
            },
        ],
        "reports": {"markdown": "report", "html": "<p>report</p>", "pdf_base64": "JVBERi0="},
        "progress": [
            {
                "step": "truth_and_review_gates",
                "status": "running",
                "message": "Applying final gates.",
            },
            {
                "step": "complete",
                "status": "complete",
                "message": "Assessment completed.",
            },
        ],
        "human_review_required": True,
        "client_ready": False,
    }


def test_not_scored_controls_have_no_numeric_payload_score() -> None:
    result = _result()
    _normalize_not_scored_sections(result)

    scanner = result["sections"][1]
    acceptance = result["sections"][2]
    for section in (scanner, acceptance):
        assert section["score"] is None
        assert section["presented_score"] is None
        assert section["score_label"] == "NOT SCORED"
        assert section["directly_scored"] is False
        assert section["exclude_from_maturity"] is True


def test_terminal_progress_cannot_show_running_after_complete() -> None:
    result = _result()
    _reconcile_terminal_progress(result)

    assert result["terminal_state"] == "human_review_pending"
    assert result["automated_stages_complete"] is True
    assert result["human_review_status"] == "pending"
    assert result["client_delivery_allowed"] is False
    assert result["client_ready"] is False
    assert result["progress"][0]["status"] == "complete"
    assert result["progress"][1]["step"] == "automated_complete"
    assert "human review" in result["progress"][1]["message"].lower()


def test_incomplete_run_is_not_promoted() -> None:
    result = _result()
    result["status"] = "running"
    result["progress"][-1]["status"] = "running"
    _reconcile_terminal_progress(result)

    assert "terminal_state" not in result
    assert result["progress"][0]["status"] == "running"


def test_installer_wraps_live_postprocessor_and_excludes_pdf_controls() -> None:
    installed = install_express_client_report_postprocessor_v31_compat()
    assert installed["terminal_truth_reconciled"] is True
    assert installed["not_scored_payload_normalized"] is True

    result = _result()
    prepared = target.prepare_express_client_report(result)
    assert prepared["sections"][2]["score"] is None
    assert prepared["terminal_state"] == "human_review_pending"
