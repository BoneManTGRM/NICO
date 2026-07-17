from __future__ import annotations

import io

from pypdf import PdfReader

from nico.mid_report_v9_production_binding import enrich_mid_v9, wrap_mid_v9_pdf


def _payload(locale: str = "en") -> dict:
    return {
        "locale": locale,
        "repository": "example/nico",
        "snapshot_commit_sha": "a" * 40,
        "sections": [
            {
                "id": "architecture_debt",
                "label": "Architecture",
                "score": 88,
                "evidence": ["Module graph retained.", "Dependency direction retained."],
                "findings": ["Compatibility surface requires review."],
                "unavailable": [],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 62,
                "evidence": ["Semgrep artifact retained."],
                "findings": ["Bandit failed during exact-snapshot execution."],
                "unavailable": ["Bandit output unavailable."],
            },
        ],
        "mid_score_transparency": {
            "records": [
                {
                    "section_id": "architecture_debt",
                    "label": "Architecture",
                    "source_score": 88,
                    "presented_score": 74,
                    "status": "yellow",
                    "confidence": "review-limited",
                    "deductions": [{"reason": "Open finding", "points": 6}],
                },
                {
                    "section_id": "static_analysis",
                    "label": "Static Analysis",
                    "source_score": 62,
                    "presented_score": 44,
                    "status": "red",
                    "confidence": "review-limited",
                    "deductions": [{"reason": "Analyzer failed", "points": 10}],
                },
            ]
        },
        "repair_intelligence": {
            "candidates": [
                {
                    "title": "Compatibility surface requires review.",
                    "category": "architecture risk",
                    "severity": "high",
                    "confidence": "medium",
                    "business_impact": "Regression probability and maintenance cost increase.",
                    "technical_impact": "Import order can change runtime behavior.",
                    "root_cause": "Multiple compatibility installers mutate shared module state.",
                    "recommended_action": "Move installer registration behind one explicit bootstrap registry.",
                    "owner": "Platform engineering",
                    "effort": "3-5 engineer-days",
                    "verification": "Run import-order matrix, full suite, and production smoke tests.",
                    "rollback": "Restore prior bootstrap registry and redeploy the last verified image.",
                    "deferred_risk": "Additional compatibility patches can create hidden recursion.",
                    "target_window": "Days 0-30",
                }
            ]
        },
    }


def _base_pdf(payload: dict) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate
    from reportlab.lib.styles import getSampleStyleSheet

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, invariant=1)
    styles = getSampleStyleSheet()
    story = []
    for index in range(35):
        story.append(Paragraph(f"Base Mid page {index + 1}. Human review required. " * 20, styles["BodyText"]))
        if index < 34:
            story.append(PageBreak())
    doc.build(story)
    return buffer.getvalue()


def test_mid_v9_enrichment_materializes_merged_records_and_visuals() -> None:
    result = enrich_mid_v9(_payload())
    assert result["mid_decision_records"]["records"]
    assert result["mid_finding_dossiers"]["records"]
    assert result["mid_visual_data"]["visual_count"] == 12
    assert result["mid_v9_production_binding"]["client_delivery_allowed"] is False


def test_mid_v9_pdf_stays_within_contract_and_contains_visual_analysis() -> None:
    wrapped = wrap_mid_v9_pdf(_base_pdf)
    reader = PdfReader(io.BytesIO(wrapped(_payload())))
    assert 35 <= len(reader.pages) <= 50
    text = "\n".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)
    for required in (
        "Evidence-Derived Visual Analysis",
        "Score Contribution",
        "Evidence Funnel",
        "Risk Heatmap",
        "Repair Impact Matrix",
        "Ownership and Accountability",
        "Decision-Ready Finding Dossiers",
    ):
        assert required in text
    assert "Human review required before client delivery" in text


def test_mid_v9_spanish_uses_same_structure_with_translated_labels() -> None:
    wrapped = wrap_mid_v9_pdf(_base_pdf)
    reader = PdfReader(io.BytesIO(wrapped(_payload("es-MX"))))
    text = "\n".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)
    assert "Análisis Visual Derivado de Evidencia" in text
    assert "Embudo de Evidencia" in text
    assert "Matriz de Impacto de Reparación" in text
    assert "Se requiere revisión humana antes de la entrega al cliente" in text


def test_production_init_installs_v9_after_v8_runtime_renderer() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "nico" / "__init__.py").read_text(encoding="utf-8")
    assert source.rindex("install_mid_report_v9_production_binding()") > source.rindex("install_mid_report_professional_v7_runtime_fix()")
