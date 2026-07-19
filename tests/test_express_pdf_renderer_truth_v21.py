from __future__ import annotations

import io

from pypdf import PdfReader

from nico.express_pdf_renderer_truth_v21 import proportional_width, replace_renderer_pages
from nico.express_report_premium_v14 import _premium_pdf


def _result() -> dict:
    sections = []
    for section_id, label, score in [
        ("code_audit", "Code Audit", 86),
        ("dependency_health", "Dependency Health", 74),
        ("secrets_review", "Secrets Review", 6),
        ("static_analysis", "Static Analysis", 0),
        ("ci_cd", "CI/CD", 90),
        ("architecture_debt", "Architecture", 74),
        ("velocity_complexity", "Velocity and Complexity", 86),
    ]:
        sections.append({"id": section_id, "label": label, "score": score, "status": "yellow", "summary": f"{label} summary", "evidence": [f"{label} exact evidence"], "findings": [], "unavailable": []})
    return {
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-19T00:00:00Z",
        "maturity_signal": {"score": 90, "level": "Senior"},
        "sections": sections,
        "repair_intelligence": {"candidates": []},
        "executive_summary": "Test assessment.",
    }


def test_proportional_width_exact_geometry() -> None:
    assert proportional_width(0) == 0
    assert proportional_width(6) == 5.76
    assert proportional_width(74) == 71.04
    assert proportional_width(86) == 82.56
    assert proportional_width(90) == 86.4
    assert proportional_width(6) < proportional_width(74) < proportional_width(86) < proportional_width(90)


def test_renderer_replaces_glyph_page_and_splits_architecture_velocity() -> None:
    result = _result()
    original = _premium_pdf(result)
    replaced = replace_renderer_pages(original, result)
    pages = PdfReader(io.BytesIO(replaced)).pages
    text = [page.extract_text() or "" for page in pages]
    assert sum("Score Contribution and Constraints" in page for page in text) == 1
    assert sum("Architecture Decision Record" in page for page in text) == 1
    assert sum("Velocity, Complexity, and Ownership Decision Record" in page for page in text) == 1
    assert all("Architecture, Complexity, and Ownership Decision Record" not in page for page in text)
    geometry = result["express_pdf_bar_geometry"]["records"]
    widths = {item["score"]: item["rendered_width"] for item in geometry}
    assert widths[0] == 0
    assert widths[6] < widths[74] < widths[86] < widths[90]
    truth = result["express_pdf_renderer_truth"]
    assert truth["status"] == "complete"
    assert truth["actual_vector_geometry"] is True
    assert truth["architecture_velocity_split"] is True
