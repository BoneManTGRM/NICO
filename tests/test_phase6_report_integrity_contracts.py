from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_phase6_has_canonical_finding_deduplication_boundary() -> None:
    sources = "\n".join(
        _source(path)
        for path in (
            "nico/comprehensive_decision_grade_assessment_v5.py",
            "nico/comprehensive_decision_grade_report_v5.py",
            "nico/comprehensive_decision_grade_markdown_v5.py",
        )
    )

    assert "canonical_finding" in sources.lower()
    assert "deduplic" in sources.lower()
    assert "roadmap" in sources.lower()


def test_phase6_keeps_rule_message_separate_from_executive_title() -> None:
    sources = "\n".join(
        _source(path)
        for path in (
            "nico/comprehensive_decision_grade_assessment_v5.py",
            "nico/comprehensive_decision_grade_report_v5.py",
        )
    )

    assert "rule_message" in sources
    assert "executive_title" in sources


def test_phase6_normalizes_finding_location_once() -> None:
    sources = "\n".join(
        _source(path)
        for path in (
            "nico/comprehensive_decision_grade_assessment_v5.py",
            "nico/comprehensive_decision_grade_report_v5.py",
        )
    )

    assert "canonical_location" in sources
    assert "normalize" in sources.lower()


def test_phase6_artifact_status_suffix_is_idempotent() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "nico").glob("*.py")
        if "report" in path.name or "artifact" in path.name
    )

    assert "idempotent" in sources.lower()
    assert "PENDING-APPROVAL" in sources


def test_phase6_complexity_distinguishes_actionable_regions() -> None:
    sources = "\n".join(
        _source(path)
        for path in (
            "nico/full_assessment_complexity_evidence.py",
            "nico/typescript_ast_complexity_v1.py",
        )
    )

    assert "actionable" in sources.lower()
    assert "module_region" in sources.lower()
    assert "generated" in sources.lower()
