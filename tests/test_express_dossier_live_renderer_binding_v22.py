from __future__ import annotations

import base64
import io

from pypdf import PdfReader


def _result() -> dict:
    sections = []
    for section_id, label, score in [
        ("code_audit", "Code Audit", 86),
        ("dependency_health", "Dependency Health", 74),
        ("secrets_review", "Secrets Review", 74),
        ("static_analysis", "Static Analysis", 74),
        ("ci_cd", "CI/CD", 74),
        ("architecture_debt", "Architecture", 74),
        ("velocity_complexity", "Velocity", 74),
        ("scanner_worker_evidence", "Scanner Worker Evidence", 6),
        ("client_acceptance", "Client / Human Acceptance", 0),
    ]:
        sections.append({
            "id": section_id,
            "label": label,
            "score": score,
            "status": "yellow",
            "summary": f"{label} summary",
            "evidence": [f"{label} evidence"],
            "findings": [],
            "unavailable": [],
        })
    return {
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-20T00:00:00Z",
        "maturity_signal": {"score": 90, "level": "Senior"},
        "sections": sections,
        "repair_intelligence": {"candidates": []},
        "executive_summary": "Test assessment.",
        "reports": {"markdown": "", "html": ""},
    }


def test_dossier_export_calls_final_live_vector_renderer() -> None:
    import nico
    from nico import express_report_dossier_export_v15 as dossier
    from nico import express_report_premium_v14 as premium

    assert getattr(premium._premium_pdf, "_nico_express_pdf_renderer_truth_v21", False) is True
    assert getattr(premium._premium_pdf, "_nico_express_pdf_score_assurance_v1", False) is True
    assert dossier._premium_pdf is premium._premium_pdf

    result = _result()
    payload, error = dossier.build_express_dossier_export(result)
    assert error is None
    pdf = base64.b64decode(payload or "")
    text = [" ".join((page.extract_text() or "").split()).casefold() for page in PdfReader(io.BytesIO(pdf)).pages]

    assert sum("score contribution and assurance constraints" in page for page in text) == 1
    assert sum("architecture decision record" in page for page in text) == 1
    assert sum(all(token in page for token in ("velocity", "complexity", "ownership", "decision record")) for page in text) == 1
    assert result["express_pdf_renderer_truth"]["status"] == "complete"
    assert result["express_pdf_bar_geometry"]["render_mode"] == "reportlab_vector_geometry"
    assert result["express_pdf_score_assurance"]["assurance_separate"] is True
    assert result["express_pdf_score_assurance_geometry"]["score_band_coloring"] is True
