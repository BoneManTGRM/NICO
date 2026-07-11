from __future__ import annotations

from nico.express_review_target import attach_express_review_target


def test_attach_express_review_target_labels_express_report_path() -> None:
    result = {"generated_at": "2026-07-11T00:00:00Z", "reports": {"markdown": "# Express"}}

    updated = attach_express_review_target(result, {"customer_id": "cust-a", "project_id": "proj-a"})

    assert updated["report_path"] == "express"
    assert updated["reports"]["report_path"] == "express"
    assert updated["final_review"]["customer_id"] == "cust-a"
    assert updated["final_review"]["project_id"] == "proj-a"


def test_attach_express_review_target_does_not_create_reports_object() -> None:
    result = {"run_id": "express_123"}

    updated = attach_express_review_target(result, {})

    assert updated["report_path"] == "express"
    assert "reports" not in updated
