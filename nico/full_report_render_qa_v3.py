from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


VERSION = "full_report_render_qa_v3"
MIN_PAGES = 70
MAX_PAGES = 120
MIN_SUBSTANTIVE_CHARACTERS = 180
_PLACEHOLDER_RE = re.compile(r"<[^>]*(?:version|package|minimum|maximum|verified|todo|tbd)[^>]*>", re.I)
_RAW_MARKUP_RE = re.compile(r"(?:<script\b|<style\b|\{\s*['\"]\w+['\"]\s*:|\[object Object\])", re.I)


@dataclass(frozen=True)
class FullRenderQA:
    status: str
    locale: str
    page_count: int
    issues: tuple[str, ...]
    client_delivery_allowed: bool


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _pages(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(_text(value) for value in values)


def validate_full_render(
    pages: Iterable[Any],
    *,
    locale: str = "en",
    human_review_complete: bool = False,
    score_records: Iterable[dict[str, Any]] = (),
    finding_ids: Iterable[str] = (),
) -> FullRenderQA:
    normalized_locale = "es" if str(locale).lower().replace("_", "-").startswith("es") else "en"
    rendered = _pages(pages)
    joined = "\n".join(rendered)
    issues: list[str] = []

    if not MIN_PAGES <= len(rendered) <= MAX_PAGES:
        issues.append(f"Full report page count must be {MIN_PAGES}-{MAX_PAGES}; observed {len(rendered)}.")

    for index, page in enumerate(rendered, 1):
        if len(page) < MIN_SUBSTANTIVE_CHARACTERS:
            issues.append(f"Page {index} is blank or not substantive ({len(page)} extracted characters).")

    if _PLACEHOLDER_RE.search(joined):
        issues.append("Placeholder token detected in rendered Full report.")
    if _RAW_MARKUP_RE.search(joined):
        issues.append("Raw markup or serialized-object leakage detected in rendered Full report.")

    ids = [_text(value) for value in finding_ids if _text(value)]
    if len(ids) != len(set(ids)):
        issues.append("Duplicate enterprise finding IDs detected.")

    for record in score_records:
        deductions = record.get("deductions") or []
        status = _text(record.get("status")).lower()
        presented = int(record.get("presented_score") or 0)
        if deductions and (status == "green" or presented >= 75):
            issues.append(f"Score/status contradiction for {record.get('section_id') or 'unknown control'}.")

    required = {
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
    }[normalized_locale]
    for label in required:
        if label not in joined:
            issues.append(f"Required {normalized_locale} section label missing: {label}")

    allowed = not issues and human_review_complete
    status = "pass" if not issues else "fail"
    return FullRenderQA(status, normalized_locale, len(rendered), tuple(issues), allowed)


def validate_full_bilingual_parity(english: dict[str, Any], spanish: dict[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    comparable_keys = (
        "page_count",
        "visual_count",
        "finding_dossier_count",
        "score_record_count",
        "evidence_record_count",
        "roadmap_item_count",
    )
    for key in comparable_keys:
        if english.get(key) != spanish.get(key):
            issues.append(f"English/Spanish parity mismatch for {key}: {english.get(key)} != {spanish.get(key)}")
    if english.get("section_ids") != spanish.get("section_ids"):
        issues.append("English/Spanish section structure differs.")
    if english.get("finding_ids") != spanish.get("finding_ids"):
        issues.append("English/Spanish finding identity differs.")
    return tuple(issues)


def attach_full_render_qa(
    result: dict[str, Any],
    pages: Iterable[Any],
    *,
    locale: str = "en",
    human_review_complete: bool = False,
) -> dict[str, Any]:
    score_records = ((result.get("full_score_transparency") or {}).get("records") or [])
    finding_ids = [item.get("finding_id") for item in ((result.get("full_enterprise_findings") or {}).get("records") or []) if isinstance(item, dict)]
    qa = validate_full_render(
        pages,
        locale=locale,
        human_review_complete=human_review_complete,
        score_records=score_records,
        finding_ids=finding_ids,
    )
    result["full_render_qa"] = {
        "version": VERSION,
        "status": qa.status,
        "locale": qa.locale,
        "page_count": qa.page_count,
        "issues": list(qa.issues),
        "human_review_complete": human_review_complete,
        "client_delivery_allowed": qa.client_delivery_allowed,
    }
    result["client_delivery_allowed"] = qa.client_delivery_allowed
    result["human_review_required"] = not human_review_complete
    return result


__all__ = [
    "FullRenderQA",
    "MAX_PAGES",
    "MIN_PAGES",
    "VERSION",
    "attach_full_render_qa",
    "validate_full_bilingual_parity",
    "validate_full_render",
]
