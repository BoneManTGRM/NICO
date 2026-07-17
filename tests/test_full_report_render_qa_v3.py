from nico.full_report_render_qa_v3 import (
    MAX_PAGES,
    MIN_PAGES,
    attach_full_render_qa,
    validate_full_bilingual_parity,
    validate_full_render,
)


ENGLISH_LABELS = [
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
]

SPANISH_LABELS = [
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
]


def _pages(labels: list[str], count: int = 90) -> list[str]:
    prefix = " ".join(labels)
    return [f"{prefix} Page {index}. " + ("Substantive evidence interpretation and decision context. " * 6) for index in range(1, count + 1)]


def test_full_render_passes_only_with_valid_depth_and_human_review() -> None:
    qa = validate_full_render(
        _pages(ENGLISH_LABELS),
        locale="en-US",
        human_review_complete=True,
        score_records=[{"section_id": "architecture", "presented_score": 82, "status": "green", "deductions": []}],
        finding_ids=["ENT-001", "ENT-002"],
    )
    assert qa.status == "pass"
    assert qa.page_count == 90
    assert qa.client_delivery_allowed is True


def test_full_render_blocks_delivery_for_page_placeholder_and_score_failures() -> None:
    pages = _pages(ENGLISH_LABELS, MIN_PAGES - 1)
    pages[0] += " package-name>=<minimum-fixed-version>"
    qa = validate_full_render(
        pages,
        locale="en",
        human_review_complete=True,
        score_records=[{"section_id": "security", "presented_score": 80, "status": "green", "deductions": [{"reason": "scanner failed", "points": 10}]}],
        finding_ids=["ENT-001", "ENT-001"],
    )
    assert qa.status == "fail"
    assert qa.client_delivery_allowed is False
    assert any("page count" in issue for issue in qa.issues)
    assert any("Placeholder" in issue for issue in qa.issues)
    assert any("Duplicate enterprise finding IDs" in issue for issue in qa.issues)
    assert any("Score/status contradiction" in issue for issue in qa.issues)


def test_full_spanish_render_uses_same_depth_contract() -> None:
    qa = validate_full_render(_pages(SPANISH_LABELS, MAX_PAGES), locale="es-MX", human_review_complete=False)
    assert qa.status == "pass"
    assert qa.locale == "es"
    assert qa.page_count == MAX_PAGES
    assert qa.client_delivery_allowed is False


def test_full_bilingual_parity_compares_structure_and_identity() -> None:
    english = {
        "page_count": 90,
        "visual_count": 22,
        "finding_dossier_count": 18,
        "score_record_count": 12,
        "evidence_record_count": 140,
        "roadmap_item_count": 24,
        "section_ids": ["board", "architecture", "roadmap"],
        "finding_ids": ["ENT-001", "ENT-002"],
    }
    spanish = dict(english)
    assert validate_full_bilingual_parity(english, spanish) == ()
    spanish["page_count"] = 89
    spanish["finding_ids"] = ["ENT-001"]
    issues = validate_full_bilingual_parity(english, spanish)
    assert len(issues) == 2


def test_attach_full_render_qa_is_fail_closed() -> None:
    result = {
        "full_score_transparency": {"records": []},
        "full_enterprise_findings": {"records": [{"finding_id": "ENT-001"}]},
        "client_delivery_allowed": True,
    }
    attach_full_render_qa(result, _pages(ENGLISH_LABELS), locale="en", human_review_complete=False)
    assert result["full_render_qa"]["status"] == "pass"
    assert result["client_delivery_allowed"] is False
    assert result["human_review_required"] is True
