from __future__ import annotations

from nico.full_report_release_pipeline_v1 import build_full_release_pipeline


def _pages(locale: str = "en") -> list[str]:
    labels = {
        "en": (
            "Board and Executive Decision Package",
            "Enterprise Architecture and System Boundaries",
            "Trust Boundaries and Threat Model",
            "Service, Dependency, and Data-Flow Topology",
            "Deployment and Environment Topology",
            "Resilience, Disaster Recovery, and Continuity",
            "Observability and Incident Operations",
            "Security Governance and SDLC Controls",
            "Technical-Debt Economics",
            "Multi-Quarter Transformation Roadmap",
            "Enterprise Finding Dossiers",
            "Human review required",
        ),
        "es": (
            "Paquete de Decisión para Junta y Ejecutivos",
            "Arquitectura Empresarial y Límites del Sistema",
            "Límites de Confianza y Modelo de Amenazas",
            "Topología de Servicios, Dependencias y Flujos de Datos",
            "Topología de Despliegue y Entornos",
            "Resiliencia, Recuperación ante Desastres y Continuidad",
            "Observabilidad y Operaciones de Incidentes",
            "Gobernanza de Seguridad y Controles SDLC",
            "Economía de la Deuda Técnica",
            "Hoja de Ruta de Transformación Multitrimestral",
            "Expedientes Empresariales de Hallazgos",
            "Se requiere revisión humana",
        ),
    }[locale]
    detail = " Evidence-bound analysis with owner, verification, rollback, acceptance criteria, and residual risk."
    pages = [label + detail * 3 for label in labels]
    pages.extend([f"{locale} substantive enterprise analysis {index}." + detail * 3 for index in range(12, 70)])
    return pages


def _report() -> dict:
    return {
        "report_version": "full-10.0",
        "full_score_transparency": {"records": []},
        "full_enterprise_findings": {"records": []},
    }


def _exports() -> dict:
    return {
        "pdf": b"%PDF-1.7 full report",
        "html": "<html><body>full report</body></html>",
        "markdown": "# Full report",
    }


def test_pipeline_passes_only_when_every_release_gate_passes() -> None:
    result = build_full_release_pipeline(
        _report(),
        pages=_pages("en"),
        exports=_exports(),
        assessment_id="assessment-10h",
        locale="en",
        human_review_complete=True,
    )
    assert result["full_production_release"]["release_state"] == "approved"
    assert result["full_artifact_manifest"]["persisted_artifacts_complete"] is True
    assert result["full_delivery_contract"]["all_formats_available"] is True
    assert result["full_download_responses"]["all_formats_ready"] is True
    assert result["full_release_pipeline"]["response_validation_issues"] == {}
    assert result["client_delivery_allowed"] is True
    for response in result["full_download_responses"]["formats"].values():
        assert response["headers"]["X-Content-SHA256"]
        assert response["required_headers_present"] is True


def test_pipeline_preserves_human_review_block() -> None:
    result = build_full_release_pipeline(
        _report(),
        pages=_pages("es"),
        exports=_exports(),
        assessment_id="assessment-10h-es",
        locale="es",
        human_review_complete=False,
    )
    assert result["full_release_pipeline"]["all_gates_passed"] is False
    assert result["client_delivery_allowed"] is False


def test_pipeline_fails_closed_when_an_export_is_missing() -> None:
    exports = _exports()
    del exports["markdown"]
    result = build_full_release_pipeline(
        _report(),
        pages=_pages("en"),
        exports=exports,
        assessment_id="assessment-missing",
        locale="en",
        human_review_complete=True,
    )
    assert result["full_artifact_manifest"]["persisted_artifacts_complete"] is False
    assert result["full_delivery_contract"]["all_formats_available"] is False
    assert result["client_delivery_allowed"] is False
