from __future__ import annotations

import pytest

from nico.report_path_truth import apply_report_path_truth


def test_report_path_truth_applies_express_labels() -> None:
    result = {
        "reports": {
            "markdown": "# Express report",
            "html": "<html><body><h1>Express report</h1></body></html>",
        }
    }

    updated = apply_report_path_truth(result, "express")

    assert updated["report_path"] == "express"
    assert updated["report_path_label"] == "Express Assessment"
    assert updated["reports"]["markdown"].startswith("> Report path: Express Assessment (`express`).")
    assert 'data-nico-report-path="express"' in updated["reports"]["html"]
    assert "report_path_conflict" not in updated


def test_report_path_truth_applies_full_run_labels() -> None:
    result = {
        "reports": {
            "markdown": "# Full report",
            "html": "<html><body><h1>Full report</h1></body></html>",
        },
        "assessment": {},
    }

    updated = apply_report_path_truth(result, "full_run")

    assert updated["report_path"] == "full_run"
    assert updated["report_path_label"] == "Full Assessment"
    assert updated["assessment"]["report_path"] == "full_run"
    assert updated["reports"]["markdown"].startswith("> Report path: Full Assessment (`full_run`).")
    assert 'data-nico-report-path="full_run"' in updated["reports"]["html"]


def test_report_path_truth_discloses_conflict_and_blocks_client_readiness() -> None:
    result = {
        "report_path": "express",
        "reports": {"report_path": "express", "markdown": "# Wrong path"},
        "assessment": {"report_path": "express"},
        "human_review_required": False,
        "client_ready": True,
    }

    updated = apply_report_path_truth(result, "full_run")

    assert updated["report_path"] == "full_run"
    assert updated["reports"]["report_path"] == "full_run"
    assert updated["assessment"]["report_path"] == "full_run"
    assert updated["report_path_conflict"]["detected"] is True
    assert updated["report_path_conflict"]["expected"] == "full_run"
    assert updated["report_path_conflict"]["observed"] == ["express"]
    assert updated["human_review_required"] is True
    assert updated["client_ready"] is False


def test_report_path_truth_is_idempotent() -> None:
    result = {
        "reports": {
            "markdown": "# Report",
            "html": "<html><body><h1>Report</h1></body></html>",
        }
    }

    once = apply_report_path_truth(result, "express")
    twice = apply_report_path_truth(once, "express")

    assert twice["reports"]["markdown"].count("Report path: Express Assessment") == 1
    assert twice["reports"]["html"].count('data-nico-report-path="express"') == 1


def test_report_path_truth_rejects_unknown_path() -> None:
    with pytest.raises(ValueError, match="unsupported report path"):
        apply_report_path_truth({}, "unknown")
