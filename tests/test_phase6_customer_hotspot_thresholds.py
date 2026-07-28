from __future__ import annotations

from pathlib import Path

from nico.typescript_ast_complexity_v1 import _build_complexity


ROOT = Path(__file__).resolve().parents[1]
THRESHOLD = 30
TARGETS = (
    "apps/web/app/assessment/MidSectionReview.tsx",
    "nico/comprehensive_decision_grade_html_v5.py",
    "nico/comprehensive_decision_grade_assessment_v5.py",
    "nico/comprehensive_decision_grade_assessment_v6.py",
    "nico/comprehensive_decision_grade_report_v5.py",
)


def test_customer_facing_report_and_review_hotspots_are_below_threshold() -> None:
    files = {
        path: (ROOT / path).read_text(encoding="utf-8")
        for path in TARGETS
    }
    result = _build_complexity(files)
    violations = [
        {
            "path": item.get("path"),
            "name": item.get("name"),
            "line": item.get("line"),
            "cyclomatic_complexity": item.get("cyclomatic_complexity"),
        }
        for item in result.get("hotspots") or []
        if str(item.get("path") or "") in TARGETS
        and int(item.get("cyclomatic_complexity") or 0) >= THRESHOLD
    ]

    assert violations == []


def test_v5_assessment_entry_point_is_a_bounded_compatibility_wrapper() -> None:
    source = (ROOT / "nico" / "comprehensive_decision_grade_assessment_v5.py").read_text(encoding="utf-8")

    assert "from nico.comprehensive_decision_grade_assessment_v6 import" in source
    assert "def build_decision_grade_assessment" not in source
    assert len(source.splitlines()) < 20
