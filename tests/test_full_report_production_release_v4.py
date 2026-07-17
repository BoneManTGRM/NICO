from __future__ import annotations

from nico.full_report_production_release_v4 import (
    REQUIRED_FORMATS,
    build_bilingual_release_gate,
    build_full_release_manifest,
)


def _pages(locale: str) -> list[str]:
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
    substantive = " Evidence-bound analysis with owner, verification, rollback, acceptance criteria, and residual risk."
    pages = [(label + substantive * 3) for label in labels]
    pages.extend([f"{locale} enterprise analysis page {index}." + substantive * 3 for index in range(12, 70)])
    return pages


def _report() -> dict:
    return {
        "full_score_transparency": {"records": []},
        "full_enterprise_findings": {"records": []},
    }


def _exports() -> dict:
    return {"pdf": b"%PDF-1.7", "html": "<html>report</html>", "markdown": "# report"}


def test_release_manifest_requires_qa_exports_and_human_review() -> None:
    blocked = build_full_release_manifest(
        _report(), pages=_pages("en"), locale="en", exports=_exports(), human_review_complete=False
    )
    assert blocked["full_production_release"]["release_state"] == "blocked"
    assert blocked["client_delivery_allowed"] is False

    approved = build_full_release_manifest(
        _report(), pages=_pages("en"), locale="en", exports=_exports(), human_review_complete=True
    )
    release = approved["full_production_release"]
    assert release["release_state"] == "approved"
    assert approved["client_delivery_allowed"] is True
    assert set(release["exports"]) == set(REQUIRED_FORMATS)


def test_missing_export_fails_closed() -> None:
    result = build_full_release_manifest(
        _report(),
        pages=_pages("en"),
        locale="en",
        exports={"pdf": b"%PDF", "html": "<html />"},
        human_review_complete=True,
    )
    assert result["client_delivery_allowed"] is False
    assert "Required Full export missing: markdown" in result["full_production_release"]["issues"]


def test_bilingual_gate_requires_both_approved_and_structurally_equal() -> None:
    common = {
        "page_count": 70,
        "visual_count": 22,
        "finding_dossier_count": 4,
        "score_record_count": 12,
        "evidence_record_count": 50,
        "roadmap_item_count": 8,
        "section_ids": ["architecture", "security"],
        "finding_ids": ["FULL-001", "FULL-002"],
    }
    english = {**common, "full_production_release": {"release_state": "approved"}}
    spanish = {**common, "full_production_release": {"release_state": "approved"}}
    assert build_bilingual_release_gate(english, spanish)["client_delivery_allowed"] is True

    spanish["visual_count"] = 21
    gate = build_bilingual_release_gate(english, spanish)
    assert gate["client_delivery_allowed"] is False
    assert any("visual_count" in issue for issue in gate["issues"])
