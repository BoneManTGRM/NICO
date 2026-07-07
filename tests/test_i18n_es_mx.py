from nico.i18n_es_mx import localize_result, markdown_report_es_mx, reports_es_mx, wants_es_mx
from nico.report_accuracy import apply_report_accuracy


def _sample_result():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-07T10:00:00Z",
        "client_name": "Cliente Demo",
        "project_name": "NICO",
        "assessment_mode": "express_es_mx",
        "executive_summary": "Human review is required before client-facing delivery.",
        "maturity_signal": {"level": "Senior", "score": 82, "summary": "Evidence suggests mature delivery foundations."},
        "maturity_semaphore": {"Code Audit": "green", "Static Analysis": "yellow"},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "score": 82, "status": "green", "summary": "Code audit uses metadata.", "evidence": ["Evidence item"], "findings": [], "unavailable": []},
            {"id": "static_analysis", "label": "Static Analysis", "score": 74, "status": "yellow", "summary": "Static analysis uses checks.", "evidence": [], "findings": ["Finding item"], "unavailable": ["Unavailable data"]},
        ],
        "quick_wins": ["Review evidence."],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "reports": {"markdown": "english", "html": "english"},
    }


def test_wants_es_mx_accepts_express_mode():
    assert wants_es_mx("express_es_mx")
    assert wants_es_mx("es-MX")
    assert not wants_es_mx("express")


def test_localize_result_changes_labels_and_language():
    result = localize_result(_sample_result())
    assert result["report_language"] == "es-MX"
    assert result["language_label"] == "Español (México)"
    assert result["sections"][0]["label"] == "Auditoría de código"
    assert result["sections"][0]["status_label"] == "verde"


def test_spanish_markdown_contains_mexican_spanish_headers():
    markdown = markdown_report_es_mx(_sample_result())
    assert "# Paquete de reporte NICO" in markdown
    assert "Idioma: Español (México)" in markdown
    assert "## Resumen ejecutivo" in markdown
    assert "## Secciones de evaluación" in markdown


def test_apply_report_accuracy_replaces_reports_for_spanish_mode():
    result = apply_report_accuracy(_sample_result())
    assert result["report_language"] == "es-MX"
    assert "Paquete de reporte NICO" in result["reports"]["markdown"]
    assert "lang=\"es-MX\"" in result["reports"]["html"]
    assert result["sections"][0]["label"] == "Auditoría de código"


def test_reports_es_mx_returns_markdown_and_html():
    formats = reports_es_mx(_sample_result())
    assert set(formats) == {"markdown", "html"}
    assert "Resumen ejecutivo" in formats["markdown"]
    assert "Reporte NICO" in formats["html"]
