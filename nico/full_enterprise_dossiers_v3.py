from __future__ import annotations

from hashlib import sha256
from typing import Any

VERSION = "full_enterprise_dossiers_v3"


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, fallback: str = "Not provided") -> str:
    text = " ".join(str(value or "").split())
    return text or fallback


def build_enterprise_dossiers(result: dict[str, Any]) -> list[dict[str, Any]]:
    repairs = result.get("repair_intelligence") if isinstance(result.get("repair_intelligence"), dict) else {}
    candidates = [dict(item) for item in _items(repairs.get("candidates")) if isinstance(item, dict)]
    by_title = {_text(item.get("title"), "").casefold(): item for item in candidates if _text(item.get("title"), "")}
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for section in _items(result.get("sections")):
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("id"), "unknown")
        evidence = [_text(item, "") for item in _items(section.get("evidence")) if _text(item, "")][:10]
        for raw in _items(section.get("findings")):
            title = _text(raw, "")
            key = (section_id, title.casefold())
            if not title or key in seen:
                continue
            seen.add(key)
            repair = by_title.get(title.casefold(), {})
            digest = sha256(f"{section_id}|{title}|{'|'.join(evidence)}".encode()).hexdigest()[:14].upper()
            records.append({
                "finding_id": f"ENT-{digest}",
                "section_id": section_id,
                "title": title,
                "classification": _text(repair.get("classification") or repair.get("category"), "engineering risk").lower(),
                "severity": _text(repair.get("severity"), "unclassified").lower(),
                "priority": _text(repair.get("priority") or repair.get("rank"), "unranked"),
                "confidence": _text(repair.get("confidence"), "review-limited").lower(),
                "business_impact": _text(repair.get("business_impact") or repair.get("impact"), "Business impact requires authorized review."),
                "technical_impact": _text(repair.get("technical_impact"), "Technical impact requires exact-context confirmation."),
                "evidence": evidence,
                "root_cause": _text(repair.get("root_cause"), "Root cause not yet proven."),
                "repair": _text(repair.get("recommended_action") or repair.get("action"), "Define the smallest reversible repair from exact evidence."),
                "owner": _text(repair.get("owner"), "Authorized engineering owner"),
                "effort": _text(repair.get("effort"), "Estimate after exact evidence review"),
                "verification": _text(repair.get("verification"), "Run focused tests, full suite, production build, deployment smoke test, and immutable reassessment."),
                "rollback": _text(repair.get("rollback"), "Document and validate a reversible fallback before implementation."),
                "acceptance_criteria": _text(repair.get("acceptance_criteria"), "Objective evidence closes the finding and an authorized reviewer approves disposition."),
                "deferred_risk": _text(repair.get("deferred_risk") or repair.get("residual_risk"), "Residual risk remains until verification and approval are complete."),
                "target_window": _text(repair.get("target_window"), "quarter 1"),
                "approval_required": True,
            })
    result["full_enterprise_dossiers"] = {
        "version": VERSION,
        "count": len(records),
        "stable_ids": True,
        "duplicate_suppression": True,
        "human_review_required": True,
        "records": records,
    }
    return records


def build_enterprise_visual_data(result: dict[str, Any]) -> dict[str, Any]:
    records = build_enterprise_dossiers(result)
    def counts(field: str) -> dict[str, int]:
        output: dict[str, int] = {}
        for item in records:
            key = str(item.get(field) or "unknown")
            output[key] = output.get(key, 0) + 1
        return output
    visuals = {
        "severity_distribution": counts("severity"),
        "confidence_distribution": counts("confidence"),
        "classification_distribution": counts("classification"),
        "ownership_distribution": counts("owner"),
        "roadmap_distribution": counts("target_window"),
        "finding_density_by_section": counts("section_id"),
        "risk_heatmap": [{key: item.get(key) for key in ("finding_id", "severity", "confidence", "classification", "target_window")} for item in records],
        "repair_impact_matrix": [{key: item.get(key) for key in ("finding_id", "business_impact", "effort", "owner")} for item in records],
        "evidence_funnel": {
            "retained_sections": len([item for item in _items(result.get("sections")) if isinstance(item, dict)]),
            "enterprise_findings": len(records),
            "human_dispositions_complete": 0,
        },
        "visual_count": 22,
    }
    result["full_enterprise_visual_data"] = visuals
    return visuals


__all__ = ["VERSION", "build_enterprise_dossiers", "build_enterprise_visual_data"]
