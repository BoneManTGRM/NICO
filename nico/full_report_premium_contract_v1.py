from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VERSION = "full_report_premium_contract_v1"
MIN_PAGES = 70
TARGET_PAGES = 90
MAX_PAGES = 120
MIN_VISUALS = 20
MAX_VISUALS = 30


@dataclass(frozen=True)
class FullScoreRecord:
    section_id: str
    label: str
    source_score: int
    presented_score: int
    status: str
    confidence: str
    deductions: tuple[tuple[str, int], ...]


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _combined(section: dict[str, Any]) -> str:
    values = [section.get("summary")]
    values.extend(_items(section.get("evidence")))
    values.extend(_items(section.get("findings")))
    values.extend(_items(section.get("unavailable")))
    return " ".join(_text(value).lower() for value in values if value)


def reconcile_full_scores(result: dict[str, Any]) -> tuple[FullScoreRecord, ...]:
    records: list[FullScoreRecord] = []
    for raw in _items(result.get("sections")):
        if not isinstance(raw, dict):
            continue
        source = max(0, min(100, int(raw.get("score") or 0)))
        combined = _combined(raw)
        findings = _items(raw.get("findings"))
        unavailable = _items(raw.get("unavailable"))
        deductions: list[tuple[str, int]] = []
        if "timeout" in combined or "timed out" in combined:
            deductions.append(("Required analyzer did not complete", 8))
        if "failed" in combined:
            deductions.append(("Required analyzer failed", 10))
        if "requires review" in combined or "requires human triage" in combined:
            deductions.append(("Unresolved evidence requires disposition", min(12, 4 + len(findings))))
        if unavailable:
            deductions.append(("Material evidence is unavailable or limited", min(10, 2 + len(unavailable))))
        if findings and not deductions:
            deductions.append(("Open findings remain unresolved", min(8, 2 + len(findings))))
        presented = max(0, source - sum(points for _, points in deductions))
        if deductions and presented >= 75:
            presented = 74
        status = "green" if presented >= 75 and not deductions else "yellow" if presented >= 45 else "red"
        confidence = "high" if not deductions else "review-limited"
        records.append(FullScoreRecord(
            section_id=_text(raw.get("id")) or "unknown",
            label=_text(raw.get("label") or raw.get("id")) or "Unknown",
            source_score=source,
            presented_score=presented,
            status=status,
            confidence=confidence,
            deductions=tuple(deductions),
        ))

    result["full_score_transparency"] = {
        "version": VERSION,
        "method": "Source score minus explicit evidence deductions; unresolved controls are capped below GREEN.",
        "records": [
            {
                "section_id": record.section_id,
                "label": record.label,
                "source_score": record.source_score,
                "presented_score": record.presented_score,
                "status": record.status,
                "confidence": record.confidence,
                "deductions": [{"reason": reason, "points": points} for reason, points in record.deductions],
            }
            for record in records
        ],
    }
    return tuple(records)


def full_report_contract(result: dict[str, Any], locale: str = "en") -> dict[str, Any]:
    normalized = "es" if str(locale).lower().replace("_", "-").startswith("es") else "en"
    records = reconcile_full_scores(result)
    labels = {
        "en": {
            "title": "NICO Full Enterprise Technical Diligence Assessment",
            "executive": "Board and Executive Decision Package",
            "architecture": "Enterprise Architecture and Trust Boundaries",
            "resilience": "Resilience, Recovery, and Operational Readiness",
            "governance": "Security Governance and SDLC Controls",
            "economics": "Technical Debt Economics and Resource Plan",
            "roadmap": "Multi-Quarter Transformation Roadmap",
            "review": "Human review required",
        },
        "es": {
            "title": "Evaluación Completa de Diligencia Técnica Empresarial NICO",
            "executive": "Paquete de Decisión para Dirección y Consejo",
            "architecture": "Arquitectura Empresarial y Límites de Confianza",
            "resilience": "Resiliencia, Recuperación y Preparación Operativa",
            "governance": "Gobernanza de Seguridad y Controles SDLC",
            "economics": "Economía de Deuda Técnica y Plan de Recursos",
            "roadmap": "Hoja de Ruta de Transformación Multitrimestral",
            "review": "Se requiere revisión humana",
        },
    }[normalized]
    contract = {
        "version": VERSION,
        "locale": normalized,
        "page_contract": {"minimum": MIN_PAGES, "target": TARGET_PAGES, "maximum": MAX_PAGES},
        "visual_contract": {"minimum": MIN_VISUALS, "maximum": MAX_VISUALS},
        "required_sections": [
            labels["executive"],
            "Transparent Enterprise Technical Score" if normalized == "en" else "Puntuación Técnica Empresarial Transparente",
            labels["architecture"],
            "Service, Dependency, and Data-Flow Topology" if normalized == "en" else "Topología de Servicios, Dependencias y Flujo de Datos",
            "Deployment and Environment Topology" if normalized == "en" else "Topología de Despliegue y Entornos",
            labels["resilience"],
            "Observability and Incident Operations" if normalized == "en" else "Observabilidad y Operaciones de Incidentes",
            labels["governance"],
            "Ownership, Organization, and Delivery Dependencies" if normalized == "en" else "Propiedad, Organización y Dependencias de Entrega",
            "Stakeholder and Business Alignment" if normalized == "en" else "Alineación de Interesados y Negocio",
            labels["economics"],
            "Enterprise Finding Dossiers" if normalized == "en" else "Expedientes Empresariales de Hallazgos",
            labels["roadmap"],
            "Board-Level Conclusion and Sign-Off" if normalized == "en" else "Conclusión y Aprobación a Nivel de Consejo",
            labels["review"],
        ],
        "score_record_count": len(records),
        "full_finding_dossiers_required": True,
        "budget_and_resource_plan_required": True,
        "stakeholder_interview_layer_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "labels": labels,
    }
    result["full_premium_contract"] = contract
    return contract


__all__ = [
    "MAX_PAGES",
    "MAX_VISUALS",
    "MIN_PAGES",
    "MIN_VISUALS",
    "TARGET_PAGES",
    "VERSION",
    "FullScoreRecord",
    "full_report_contract",
    "reconcile_full_scores",
]
