from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VERSION = "mid_report_premium_contract_v8"
MIN_PAGES = 35
TARGET_PAGES = 42
MAX_PAGES = 50


@dataclass(frozen=True)
class MidScoreRecord:
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


def reconcile_mid_scores(result: dict[str, Any]) -> tuple[MidScoreRecord, ...]:
    records: list[MidScoreRecord] = []
    for raw in _items(result.get("sections")):
        if not isinstance(raw, dict):
            continue
        source = max(0, min(100, int(raw.get("score") or 0)))
        combined = _combined(raw)
        deductions: list[tuple[str, int]] = []
        unavailable = _items(raw.get("unavailable"))
        findings = _items(raw.get("findings"))
        if "timed out" in combined or "timeout" in combined:
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
        records.append(MidScoreRecord(
            section_id=_text(raw.get("id")) or "unknown",
            label=_text(raw.get("label") or raw.get("id")) or "Unknown",
            source_score=source,
            presented_score=presented,
            status=status,
            confidence=confidence,
            deductions=tuple(deductions),
        ))

    result["mid_score_transparency"] = {
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


def mid_report_contract(result: dict[str, Any], locale: str = "en") -> dict[str, Any]:
    normalized = "es" if str(locale).lower().replace("_", "-").startswith("es") else "en"
    records = reconcile_mid_scores(result)
    labels = {
        "en": {
            "title": "NICO Mid Technical Diligence Assessment",
            "executive": "Executive Decision Package",
            "architecture": "Architecture and System Design",
            "ownership": "Ownership and Delivery Concentration",
            "roadmap": "30/60/90-Day Repair Roadmap",
            "review": "Human review required",
        },
        "es": {
            "title": "Evaluación Media de Diligencia Técnica NICO",
            "executive": "Paquete Ejecutivo de Decisión",
            "architecture": "Arquitectura y Diseño del Sistema",
            "ownership": "Concentración de Propiedad y Entrega",
            "roadmap": "Hoja de Ruta de Reparación de 30/60/90 Días",
            "review": "Se requiere revisión humana",
        },
    }[normalized]
    contract = {
        "version": VERSION,
        "locale": normalized,
        "page_contract": {"minimum": MIN_PAGES, "target": TARGET_PAGES, "maximum": MAX_PAGES},
        "required_sections": [
            labels["executive"],
            "Transparent Technical Score" if normalized == "en" else "Puntuación Técnica Transparente",
            labels["architecture"],
            "Dependency and Supply-Chain Topology" if normalized == "en" else "Topología de Dependencias y Cadena de Suministro",
            "Complexity and Churn Hotspots" if normalized == "en" else "Puntos Críticos de Complejidad y Cambio",
            labels["ownership"],
            "CI/CD Reliability and Release Controls" if normalized == "en" else "Confiabilidad CI/CD y Controles de Lanzamiento",
            "Test Maturity and Quality Gates" if normalized == "en" else "Madurez de Pruebas y Puertas de Calidad",
            "Finding Dossiers" if normalized == "en" else "Expedientes de Hallazgos",
            labels["roadmap"],
            labels["review"],
        ],
        "score_record_count": len(records),
        "minimum_visuals": 10,
        "maximum_visuals": 15,
        "full_finding_dossiers_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "labels": labels,
    }
    result["mid_premium_contract"] = contract
    return contract


__all__ = [
    "MAX_PAGES",
    "MIN_PAGES",
    "TARGET_PAGES",
    "VERSION",
    "MidScoreRecord",
    "mid_report_contract",
    "reconcile_mid_scores",
]
