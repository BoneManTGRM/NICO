from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "apps/web/app/WorkflowCallout.tsx"
HOSTED_UI = ROOT / "apps/web/app/GenericRepositoryExample.tsx"


def test_canonical_spanish_routes_receive_the_spanish_workflow_callout() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert 'pathname.startsWith("/es")' in source
    assert "inicia Express o Integral" in source
    assert "Mid o Full" not in source
    assert '/es/assessment?tier=express#assessment' in source


def test_hosted_ui_recognizes_es_assessment_and_es_mx_aliases() -> None:
    source = HOSTED_UI.read_text(encoding="utf-8")
    assert 'pathname === "/es"' in source
    assert 'pathname.startsWith("/es/")' in source
    assert 'pathname.startsWith("/es-mx")' in source
    assert 'language === "es-mx"' in source


def test_spanish_hero_uses_complete_spanish_copy() -> None:
    source = HOSTED_UI.read_text(encoding="utf-8")
    required = {
        "Plataforma NICO",
        "Impulsado por Reparodynamics",
        "flujos de análisis",
        "informes preparados para el cliente",
        "planificación de reparaciones",
        "Ejecutar evaluación",
        "Ejecutar analizadores",
    }
    for phrase in required:
        assert phrase in source
    assert "workflows de scanner" not in source
    assert "Worker del scanner" not in source


def test_spanish_commercial_operations_and_trends_are_fully_localized() -> None:
    source = HOSTED_UI.read_text(encoding="utf-8")
    required = {
        "Operaciones comerciales",
        "Configuración de ejecución, historial del proyecto y diagnósticos",
        "Repositorio predeterminado",
        "Escrituras administrativas",
        "Visibilidad de funciones",
        "Conjunto predeterminado de funciones activo",
        "Línea base de tendencias del proyecto",
        "Los datos de tendencias se cargarán cuando exista historial de ejecuciones del proyecto.",
        "Diagnósticos seguros",
    }
    for phrase in required:
        assert phrase in source


def test_diagnostic_payload_is_localized_only_for_display() -> None:
    source = HOSTED_UI.read_text(encoding="utf-8")
    assert "SPANISH_DIAGNOSTIC_KEYS" in source
    assert "localizeDiagnosticValue" in source
    assert '["status", "estado"]' in source
    assert '["reason", "motivo"]' in source
    assert "JSON.stringify(diagnosticDisplay, null, 2)" in source
    assert "diagnostics || diagnosticsFallback" in source
