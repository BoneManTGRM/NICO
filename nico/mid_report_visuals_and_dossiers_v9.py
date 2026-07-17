from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any


VERSION = "mid_report_visuals_and_dossiers_v9"


@dataclass(frozen=True)
class MidFindingDossier:
    finding_id: str
    section_id: str
    title: str
    category: str
    severity: str
    confidence: str
    evidence: tuple[str, ...]
    business_impact: str
    technical_impact: str
    root_cause: str
    repair: str
    owner: str
    effort: str
    dependencies: tuple[str, ...]
    verification: str
    rollback: str
    acceptance_criteria: str
    deferred_risk: str
    target_window: str
    disposition: str


def _text(value: Any, fallback: str = "Not provided") -> str:
    text = " ".join(str(value or "").split())
    return text or fallback


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _unique(values: Any) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for value in _items(values):
        text = _text(value, "")
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return tuple(output)


def _finding_id(section_id: str, title: str, evidence: tuple[str, ...]) -> str:
    payload = f"{section_id}|{title}|{'|'.join(evidence)}".encode("utf-8")
    return f"MID-{sha256(payload).hexdigest()[:12].upper()}"


def build_mid_finding_dossiers(result: dict[str, Any]) -> tuple[MidFindingDossier, ...]:
    intelligence = result.get("repair_intelligence") if isinstance(result.get("repair_intelligence"), dict) else {}
    candidates = [item for item in _items(intelligence.get("candidates")) if isinstance(item, dict)]
    candidate_by_title = {_text(item.get("title"), "").casefold(): item for item in candidates if _text(item.get("title"), "")}
    dossiers: list[MidFindingDossier] = []
    seen: set[str] = set()

    for section in _items(result.get("sections")):
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("id"), "unknown")
        evidence = _unique(section.get("evidence"))[:8]
        for raw_finding in _items(section.get("findings")):
            title = _text(raw_finding, "")
            normalized = " ".join(title.casefold().split())
            key = f"{section_id}:{normalized}"
            if not title or key in seen:
                continue
            seen.add(key)
            candidate = candidate_by_title.get(normalized, {})
            category = _text(candidate.get("category"), "engineering risk").lower()
            dossiers.append(MidFindingDossier(
                finding_id=_finding_id(section_id, title, evidence),
                section_id=section_id,
                title=title,
                category=category,
                severity=_text(candidate.get("severity"), "unclassified").lower(),
                confidence=_text(candidate.get("confidence"), "review-limited").lower(),
                evidence=evidence,
                business_impact=_text(candidate.get("business_impact") or candidate.get("impact"), "Business impact requires reviewer confirmation."),
                technical_impact=_text(candidate.get("technical_impact"), "Technical impact requires exact evidence review."),
                root_cause=_text(candidate.get("root_cause"), "Root cause is not verified."),
                repair=_text(candidate.get("recommended_action") or candidate.get("action"), "Define the smallest reversible repair from the exact evidence."),
                owner=_text(candidate.get("owner"), "Authorized engineering owner"),
                effort=_text(candidate.get("effort"), "Estimate after exact evidence review"),
                dependencies=_unique(candidate.get("dependencies")),
                verification=_text(candidate.get("verification"), "Run focused tests, full suite, production build, and immutable reassessment."),
                rollback=_text(candidate.get("rollback"), "Document and test a reversible fallback before implementation."),
                acceptance_criteria=_text(candidate.get("acceptance_criteria"), "Exact evidence is resolved, verification is green, and reviewer disposition is recorded."),
                deferred_risk=_text(candidate.get("deferred_risk"), "Risk remains until verified repair or explicit acceptance."),
                target_window=_text(candidate.get("target_window"), "30-day roadmap"),
                disposition=_text(candidate.get("disposition"), "open").lower(),
            ))

    result["mid_finding_dossiers"] = {
        "version": VERSION,
        "count": len(dossiers),
        "stable_ids": True,
        "deduplicated": True,
        "records": [asdict(item) for item in dossiers],
    }
    return tuple(dossiers)


def build_mid_visual_data(result: dict[str, Any]) -> dict[str, Any]:
    sections = [item for item in _items(result.get("sections")) if isinstance(item, dict)]
    score_records = result.get("mid_score_transparency") if isinstance(result.get("mid_score_transparency"), dict) else {}
    records = [item for item in _items(score_records.get("records")) if isinstance(item, dict)]
    dossiers = build_mid_finding_dossiers(result)

    severity = Counter(item.severity for item in dossiers)
    category = Counter(item.category for item in dossiers)
    status = Counter(str(item.get("status") or "unknown").lower() for item in records)
    confidence = Counter(str(item.get("confidence") or "unknown").lower() for item in records)
    section_scores = [
        {
            "section_id": str(item.get("section_id") or "unknown"),
            "label": str(item.get("label") or item.get("section_id") or "Unknown"),
            "source_score": int(item.get("source_score") or 0),
            "presented_score": int(item.get("presented_score") or 0),
            "deduction_total": sum(int(d.get("points") or 0) for d in _items(item.get("deductions")) if isinstance(d, dict)),
        }
        for item in records
    ]
    evidence_funnel = {
        "sections": len(sections),
        "evidence_statements": sum(len(_unique(item.get("evidence"))) for item in sections),
        "finding_statements": sum(len(_unique(item.get("findings"))) for item in sections),
        "limitations": sum(len(_unique(item.get("unavailable"))) for item in sections),
        "dossiers": len(dossiers),
        "human_dispositions": sum(1 for item in dossiers if item.disposition not in {"", "open", "pending"}),
    }

    visuals = {
        "version": VERSION,
        "visual_count": 12,
        "score_contribution": section_scores,
        "status_distribution": dict(status),
        "confidence_distribution": dict(confidence),
        "severity_distribution": dict(severity),
        "finding_category_distribution": dict(category),
        "evidence_funnel": evidence_funnel,
        "risk_heatmap": [
            {
                "finding_id": item.finding_id,
                "severity": item.severity,
                "confidence": item.confidence,
                "category": item.category,
                "effort": item.effort,
                "target_window": item.target_window,
            }
            for item in dossiers
        ],
        "repair_impact_matrix": [
            {
                "finding_id": item.finding_id,
                "business_impact": item.business_impact,
                "effort": item.effort,
                "owner": item.owner,
                "target_window": item.target_window,
            }
            for item in dossiers
        ],
        "roadmap_windows": dict(Counter(item.target_window for item in dossiers)),
        "ownership_assignments": dict(Counter(item.owner for item in dossiers)),
        "section_finding_density": {
            str(item.get("id") or "unknown"): len(_unique(item.get("findings"))) for item in sections
        },
        "section_evidence_density": {
            str(item.get("id") or "unknown"): len(_unique(item.get("evidence"))) for item in sections
        },
        "client_delivery_allowed": False,
        "human_review_required": True,
    }
    result["mid_visual_data"] = visuals
    return visuals


__all__ = [
    "MidFindingDossier",
    "VERSION",
    "build_mid_finding_dossiers",
    "build_mid_visual_data",
]
