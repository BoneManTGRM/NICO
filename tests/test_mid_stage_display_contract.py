from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "apps" / "web" / "app" / "assessment" / "page.tsx"
MID_API = ROOT / "nico" / "mid_assessment_api.py"


def test_mid_ui_does_not_describe_dedicated_mid_artifacts_as_skipped_by_request() -> None:
    page = PAGE.read_text(encoding="utf-8")
    api = MID_API.read_text(encoding="utf-8")

    assert "dedicated Mid draft" in api
    assert "human-review request" in api
    assert "Full Assessment scorecard" not in api
    assert "Report generation was skipped by request." not in api
    assert "Final review request was skipped by request." not in api
    assert "Mid Assessment multi-section scorecard" in api
    assert "Dedicated Mid draft generation is planned" in api
    assert "Dedicated Mid human-review request is planned" in api
    assert "build_reports: true" in page
    assert "create_final_review_request: true" in page
