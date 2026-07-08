from __future__ import annotations

from typing import Any


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _included_in_score(section: dict[str, Any]) -> bool:
    if section.get("supplemental") is True:
        return False
    if _as_int(section.get("scoring_weight", 1)) == 0:
        return False
    if section.get("status") == "gray":
        return False
    return True


def build_score_details(payload: dict[str, Any]) -> dict[str, Any]:
    sections = [item for item in (payload or {}).get("sections", []) if isinstance(item, dict)]
    rows = []
    for item in sections:
        evidence = item.get("evidence") or []
        findings = item.get("findings") or []
        unavailable = item.get("unavailable") or []
        included = _included_in_score(item)
        rows.append(
            {
                "id": item.get("id"),
                "label": item.get("label") or item.get("id"),
                "score": _as_int(item.get("score")),
                "status": item.get("status"),
                "diagnostic_status": item.get("diagnostic_status"),
                "confidence": item.get("confidence"),
                "supplemental": bool(item.get("supplemental")),
                "scoring_weight": _as_int(item.get("scoring_weight", 1)),
                "included_in_maturity_score": included,
                "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
                "finding_count": len(findings) if isinstance(findings, list) else 0,
                "unavailable_count": len(unavailable) if isinstance(unavailable, list) else 0,
                "missing_required_sources": item.get("missing_required_sources") or [],
            }
        )
    scored_rows = [row for row in rows if row["included_in_maturity_score"]]
    score = round(sum(row["score"] for row in scored_rows) / len(scored_rows)) if scored_rows else 0
    limited = [row for row in scored_rows if row.get("confidence") in {"limited", "unavailable"}]
    low = sorted(scored_rows, key=lambda row: row["score"])[:3]
    return {
        "status": "ok" if scored_rows else "unavailable",
        "score": score,
        "section_count": len(scored_rows),
        "display_section_count": len(rows),
        "supplemental_section_count": len(rows) - len(scored_rows),
        "limited_count": len(limited),
        "lowest_sections": low,
        "supplemental_sections": [row for row in rows if not row["included_in_maturity_score"]],
        "sections": rows,
        "explanation": "Overall score is the rounded average of core scored sections only. Supplemental diagnostic sections remain visible but are not averaged into maturity unless explicitly mapped into core evidence.",
    }


def attach_score_details(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload or {})
    result["score_details"] = build_score_details(result)
    return result
