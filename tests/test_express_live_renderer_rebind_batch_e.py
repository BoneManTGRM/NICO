from __future__ import annotations

import io

from pypdf import PdfReader

import nico  # noqa: F401 - importing the package executes production installer order
from nico import express_report_premium_v14 as premium
from nico.express_pdf_renderer_truth_v21 import _PATCH_MARKER, proportional_width


def _result() -> dict:
    sections = []
    for section_id, label, score in [
        ("code_audit", "Code Audit", 86),
        ("dependency_health", "Dependency Health", 74),
        ("secrets_review", "Secrets Review", 6),
        ("static_analysis", "Static Analysis", 0),
        ("ci_cd", "CI/CD", 90),
        ("architecture_debt", "Architecture", 74),
        ("velocity_complexity", "Velocity", 86),
    ]:
        sections.append(
            {
                "id": section_id,
                "label": label,
                "score": score,
                "status": "yellow",
                "summary": f"{label} summary",
                "evidence": [f"{label} exact evidence"],
                "findings": [],
                "unavailable": [],
            }
        )
    return {
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-19T00:00:00Z",
        "maturity_signal": {"score": 90, "level": "Senior"},
        "sections": sections,
        "repair_intelligence": {"candidates": []},
        "executive_summary": "Test assessment.",
    }


def test_final_production_premium_renderer_remains_vector_truth_wrapper() -> None:
    assert getattr(premium._premium_pdf, _PATCH_MARKER, False) is True
    assert getattr(premium._premium_pdf, "_nico_express_pdf_score_assurance_v1", False) is True


def test_live_bound_renderer_replaces_glyph_page_and_splits_decision_records() -> None:
    result = _result()
    payload = premium._premium_pdf(result)
    pages = [" ".join((page.extract_text() or "").split()).casefold() for page in PdfReader(io.BytesIO(payload)).pages]

    assert sum("score contribution and assurance constraints" in page for page in pages) == 1
    assert sum("architecture decision record" in page for page in pages) == 1
    assert sum(
        all(token in page for token in ("velocity", "complexity", "ownership", "decision record"))
        for page in pages
    ) == 1
    assert result["express_pdf_renderer_truth"]["status"] == "complete"
    assert result["express_pdf_bar_geometry"]["render_mode"] == "reportlab_vector_geometry"
    assert result["express_pdf_score_assurance"]["assurance_separate"] is True
    assert result["express_pdf_score_assurance_geometry"]["score_band_coloring"] is True


def test_release_geometry_remains_exact() -> None:
    assert proportional_width(0) == 0.0
    assert proportional_width(6) == 5.76
    assert proportional_width(74) == 71.04
    assert proportional_width(86) == 82.56
    assert proportional_width(90) == 86.4
