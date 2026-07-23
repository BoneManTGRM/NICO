from __future__ import annotations

from pathlib import Path

from nico.final_report_delivery_package import finalize_report_payload


ROOT = Path(__file__).resolve().parents[1]
PRESENTATION_GUARD = ROOT / "apps" / "web" / "app" / "AssessmentFinalPresentationGuard.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def test_final_report_payload_removes_draft_terminology_without_approving_delivery() -> None:
    result = finalize_report_payload(
        {
            "title": "DRAFT REPORT",
            "subtitle": "Prepared for human review before delivery",
            "delivery_status": "Draft only",
            "decision_summary": {},
            "canonical_report_truth": {},
        }
    )

    assert result["title"] == "FINAL REPORT"
    assert "Complete report package" in result["subtitle"]
    assert "Final report package" in result["delivery_status"]
    assert result["report_is_complete"] is True
    assert result["report_recreation_required"] is False
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    assert result["decision_summary"]["report_recreation_required"] is False
    assert result["canonical_report_truth"]["report_recreation_required"] is False


def test_terminal_ui_removes_old_presentation_strings() -> None:
    source = PRESENTATION_GUARD.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'card.querySelector("b")!.textContent = "Assessment record"' in source
    assert 'value.textContent = "Recorded"' in source
    assert 'if (raw === "unavailable") node.textContent = "Unavailable"' in source
    assert 'button.textContent = "Download final PDF"' in source
    assert "complete final report package" in source
    assert "AssessmentFinalPresentationGuard" in layout
    assert "reviewers do not need to recreate the report" in layout
