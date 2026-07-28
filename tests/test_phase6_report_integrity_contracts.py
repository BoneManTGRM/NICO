from __future__ import annotations

from pathlib import Path

from nico.phase6_final_remediation_v1 import canonicalize_findings, normalize_report_filename

ROOT = Path(__file__).resolve().parents[1]
PHASE6_SOURCE = ROOT / "nico" / "phase6_final_remediation_v1.py"
HTML_SOURCE = ROOT / "nico" / "comprehensive_decision_grade_html_v6.py"
HTML_COMPAT_SOURCE = ROOT / "nico" / "comprehensive_decision_grade_html_v5.py"
CSV_SOURCE = ROOT / "nico" / "comprehensive_decision_grade_csv_v6.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_phase6_has_canonical_finding_deduplication_boundary() -> None:
    assert callable(canonicalize_findings)
    source = _source(PHASE6_SOURCE)

    assert "finding_key" in source
    assert "source_evidence_fingerprint" in source
    assert "_merge_finding" in source
    assert "roadmap_mappings" in source
    assert "backlog_mappings" in source


def test_phase6_keeps_analyzer_message_separate_from_executive_title() -> None:
    source = _source(PHASE6_SOURCE)

    assert '"analyzer_message"' in source
    assert '"executive_title"' in source
    assert '"technical_summary"' in source


def test_phase6_normalizes_finding_location_once() -> None:
    source = _source(PHASE6_SOURCE)

    assert "_normalize_path" in source
    assert "_canonical_location" in source
    assert '"canonical_path"' in source
    assert '"canonical_line"' in source
    assert '"canonical_location"' in source


def test_phase6_artifact_status_suffix_is_idempotent() -> None:
    once = normalize_report_filename(
        "report-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf",
        complete=True,
        approved=False,
    )
    twice = normalize_report_filename(once, complete=True, approved=False)

    assert once == "report-FINAL-PENDING-APPROVAL.pdf"
    assert twice == once


def test_phase6_complexity_distinguishes_actionable_regions() -> None:
    source = _source(PHASE6_SOURCE)

    assert "_complexity_class" in source
    assert "production_function_or_component" in source
    assert "report_generation" in source
    assert "test_code" in source
    assert "generated_or_vendor" in source
    assert "module_or_synthetic_region" in source
    assert "actionable_hotspots" in source


def test_phase6_cross_format_exports_use_canonical_fields() -> None:
    html_source = _source(HTML_SOURCE)
    csv_source = _source(CSV_SOURCE)

    for token in ("executive_title", "canonical_location", "related_locations", "analyzer_message"):
        assert token in html_source
        assert token in csv_source


def test_phase6_html_compatibility_entry_point_routes_to_decomposed_builder() -> None:
    source = _source(HTML_COMPAT_SOURCE)

    assert "from nico.comprehensive_decision_grade_html_v6 import" in source
    assert "def _build_html" not in source


def test_phase6_customer_report_has_no_phase_or_tier_comparison_heading() -> None:
    sources = "\n".join(
        _source(path)
        for path in (
            ROOT / "nico" / "comprehensive_express_quality_v7.py",
            ROOT / "nico" / "comprehensive_decision_grade_report_v5.py",
            HTML_SOURCE,
            HTML_COMPAT_SOURCE,
        )
    )

    assert "Assessment Coverage" in sources
    assert "Why this is broader than Express" not in sources
    assert "Verified Change Since Phase 5 Baseline" not in sources
