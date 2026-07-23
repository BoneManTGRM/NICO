from __future__ import annotations

from copy import deepcopy

from nico import express_async_api as api
from nico.express_terminal_authority import (
    EXPRESS_TERMINAL_AUTHORITY_VERSION,
    _reports_ready,
    _terminal_candidate,
    _terminal_payload,
)


def _completed_payload(run_id: str = "express_run_terminal_authority") -> dict:
    return {
        "run_id": run_id,
        "status": "running",
        "current_stage": "complete",
        "progress_percent": 100,
        "human_review_required": True,
        "reports": {
            "markdown": "# Report",
            "html": "<h1>Report</h1>",
            "pdf_base64": "JVBERi0xLjQ=",
        },
    }


def test_terminal_candidate_requires_exact_express_run_and_all_report_formats() -> None:
    payload = _completed_payload()
    assert _reports_ready(payload) is True
    assert _terminal_candidate(payload) is True

    missing = deepcopy(payload)
    missing["reports"].pop("pdf_base64")
    assert _reports_ready(missing) is False
    assert _terminal_candidate(missing) is False

    wrong_run = deepcopy(payload)
    wrong_run["run_id"] = "mid_run_not_express"
    assert _terminal_candidate(wrong_run) is False


def test_terminal_payload_is_explicit_complete_and_fail_closed_for_delivery() -> None:
    payload = _terminal_payload(api, _completed_payload()["run_id"], _completed_payload(), source="test")

    assert payload["status"] == "complete"
    assert payload["current_stage"] == "complete"
    assert payload["progress_percent"] == 100
    assert payload["report_generation_status"] == "complete"
    assert payload["terminal"] is True
    assert payload["human_review_required"] is True
    assert payload["client_ready"] is False
    assert payload["client_delivery_allowed"] is False
    assert payload["duplicate_start_allowed"] is False
    assert payload["terminal_persistence"]["version"] == EXPRESS_TERMINAL_AUTHORITY_VERSION
    assert payload["terminal_persistence"]["write_order"] == "compact_terminal_before_rich_record"


def test_production_container_uses_terminal_authority_after_comprehensive_bootstrap() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    bootstrap = (root / "nico" / "api" / "terminal_authority_bootstrap.py").read_text(encoding="utf-8")

    assert "nico.api.terminal_authority_bootstrap:app" in dockerfile
    assert bootstrap.index("from nico.api.comprehensive_production_bootstrap import app") < bootstrap.index(
        "install_express_terminal_authority()"
    )
