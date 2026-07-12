from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "apps" / "web" / "app" / "full-run" / "page.tsx"


def test_status_refresh_does_not_explicitly_downgrade_report_or_review_intent() -> None:
    source = PAGE.read_text(encoding="utf-8")
    refresh = source.split("async function refreshFullRun", 1)[1].split("async function recoverApprovedDelivery", 1)[0]

    assert "auto_continue: true" in refresh
    assert "body.build_reports = true" in refresh
    assert "body.create_final_review_request = true" in refresh
    assert "build_reports: false" not in refresh
    assert "create_final_review_request: false" not in refresh


def test_full_run_ui_can_repair_missing_report_and_approval_without_rescanning() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "downstreamMissing" in source
    assert "Continue to report and human review" in source
    assert "the existing same-run scanner evidence will be reused" in source
    assert "refreshFullRun(true)" in source


def test_overall_run_badge_is_not_overwritten_by_missing_approved_delivery() -> None:
    source = PAGE.read_text(encoding="utf-8")
    result_section = source.split('className="section panel"><div className="section-head"><div><p className="eyebrow">Full-run result', 1)[1]

    assert "statusClass(runStatus)" in result_section
    assert "approved_delivery_recovery?.status || result?.status" not in source


def test_full_run_page_explicitly_distinguishes_full_assessment_from_mid() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "This is the Full Assessment path" in source
    assert "It creates <code>fullrun_*</code> records" in source
    assert "Command Center Mid Assessment" in source
