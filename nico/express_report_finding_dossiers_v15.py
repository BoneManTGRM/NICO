from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable


VERSION = "express_finding_dossiers_v15"


@dataclass(frozen=True)
class FindingDossier:
    finding_id: str
    section_id: str
    title: str
    severity: str
    confidence: str
    evidence: tuple[str, ...]
    business_impact: str
    repair_specification: str
    owner: str
    effort: str
    verification: str
    rollback: str
    residual_risk: str
    disposition: str


def _text(value: Any, fallback: str = "Not provided") -> str:
    text = " ".join(str(value or "").split())
    return text or fallback


def _unique(values: Iterable[Any]) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value, "")
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return tuple(output)


def _finding_id(section_id: str, title: str, evidence: tuple[str, ...]) -> str:
    material = f"{section_id}|{title}|{'|'.join(evidence)}".encode("utf-8")
    return f"FND-{sha256(material).hexdigest()[:12].upper()}"


def build_finding_dossiers(result: dict[str, Any]) -> tuple[FindingDossier, ...]:
    repairs = result.get("repair_intelligence") if isinstance(result.get("repair_intelligence"), dict) else {}
    candidates = [item for item in repairs.get("candidates", []) if isinstance(item, dict)]
    by_title = {_text(item.get("title"), "").casefold(): item for item in candidates if _text(item.get("title"), "")}
    output: list[FindingDossier] = []
    seen: set[str] = set()

    for section in result.get("sections", []):
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("id"), "unknown")
        section_evidence = _unique(section.get("evidence", []))
        for raw in section.get("findings", []):
            title = _text(raw, "")
            key = f"{section_id}:{title.casefold()}"
            if not title or key in seen:
                continue
            seen.add(key)
            repair = by_title.get(title.casefold(), {})
            evidence = section_evidence[:6]
            output.append(FindingDossier(
                finding_id=_finding_id(section_id, title, evidence),
                section_id=section_id,
                title=title,
                severity=_text(repair.get("severity"), "unclassified").lower(),
                confidence=_text(repair.get("confidence"), "review-limited").lower(),
                evidence=evidence,
                business_impact=_text(repair.get("business_impact") or repair.get("impact"), "Business impact requires reviewer confirmation."),
                repair_specification=_text(repair.get("recommended_action") or repair.get("action"), "Define the smallest reversible repair from the exact evidence."),
                owner=_text(repair.get("owner"), "Authorized engineering owner"),
                effort=_text(repair.get("effort"), "Estimate after exact evidence review"),
                verification=_text(repair.get("verification"), "Run focused tests, the full suite, a production build, and a new immutable NICO assessment."),
                rollback=_text(repair.get("rollback"), "Document and test the smallest reversible fallback before implementation."),
                residual_risk=_text(repair.get("residual_risk"), "Residual risk remains until verification and human disposition are complete."),
                disposition=_text(repair.get("disposition"), "open").lower(),
            ))
    return tuple(output)


REPORT_LABELS = {
    "en": {
        "title": "NICO Express Technical Health Assessment",
        "finding_dossier": "Finding Dossier",
        "business_impact": "Business impact",
        "repair_specification": "Repair specification",
        "verification": "Verification",
        "rollback": "Rollback",
        "residual_risk": "Residual risk",
        "human_review": "Human review required",
    },
    "es": {
        "title": "Evaluación Express de Salud Técnica NICO",
        "finding_dossier": "Expediente del Hallazgo",
        "business_impact": "Impacto empresarial",
        "repair_specification": "Especificación de reparación",
        "verification": "Verificación",
        "rollback": "Reversión",
        "residual_risk": "Riesgo residual",
        "human_review": "Se requiere revisión humana",
    },
}


def report_labels(locale: str) -> dict[str, str]:
    normalized = str(locale or "en").lower().replace("_", "-")
    return REPORT_LABELS["es"] if normalized.startswith("es") else REPORT_LABELS["en"]


__all__ = [
    "FindingDossier",
    "REPORT_LABELS",
    "VERSION",
    "build_finding_dossiers",
    "report_labels",
]
