from __future__ import annotations

from nico.express_review_target import attach_express_review_target


def test_attach_express_review_target_labels_express_report_path() -> None:
    result = {
        "generated_at": "2026-07-11T00:00:00Z",
        "reports": {
            "markdown": "# Express",
            "html": "<html><body><h1>Express</h1></body></html>",
        },
    }

    updated = attach_express_review_target(result, {"customer_id": "cust-a", "project_id": "proj-a"})

    assert updated["report_path"] == "express"
    assert updated["report_path_label"] == "Express Assessment"
    assert updated["reports"]["report_path"] == "express"
    assert updated["reports"]["report_path_label"] == "Express Assessment"
    assert updated["reports"]["markdown"].startswith("> Report path: Express Assessment (`express`).")
    assert 'data-nico-report-path="express"' in updated["reports"]["html"]
    assert updated["final_review"]["customer_id"] == "cust-a"
    assert updated["final_review"]["project_id"] == "proj-a"


def test_attach_express_review_target_is_idempotent_for_visible_labels() -> None:
    result = {
        "run_id": "express_123",
        "reports": {
            "markdown": "# Express",
            "html": "<html><body><h1>Express</h1></body></html>",
        },
    }

    once = attach_express_review_target(result, {})
    twice = attach_express_review_target(once, {})

    assert twice["reports"]["markdown"].count("Report path: Express Assessment") == 1
    assert twice["reports"]["html"].count('data-nico-report-path="express"') == 1


def test_attach_express_review_target_does_not_create_reports_object() -> None:
    result = {"run_id": "express_123"}

    updated = attach_express_review_target(result, {})

    assert updated["report_path"] == "express"
    assert updated["report_path_label"] == "Express Assessment"
    assert "reports" not in updated
