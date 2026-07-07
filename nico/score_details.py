from __future__ import annotations

from typing import Any


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def build_score_details(payload: dict[str, Any]) -> dict[str, Any]:
    sections = [item for item in (payload or {}).get("sections", []) if isinstance(item, dict)]
    rows = []
    for item in sections:
        evidence = item.get("evidence") or []
        findings = item.get("findings") or []
        unavailable = item.get("unavailable") or []
        rows.append(
            {
                "id": item.get("id"),
                "label": item.get("label") or item.get("id"),
                "score": _as_int(item.get("score")),
                "status": item.get("status"),
                "confidence": item.get("confidence"),
                "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
                "finding_count": len(findings) if isinstance(findings, list) else 0,
                "unavailable_count": len(unavailable) if isinstance(unavailable, list) else 0,
                "missing_required_sources": item.get("missing_required_sources") or [],
            }
        )
    score = round(sum(row["score"] for row in rows) / len(rows)) if rows else 0
    limited = [row for row in rows if row.get("confidence") in {"limited", "unavailable"}]
    low = sorted(rows, key=lambda row: row["score"])[:3]
    return {
        "status": "ok" if rows else "unavailable",
        "score": score,
        "section_count": len(rows),
        "limited_count": len(limited),
        "lowest_sections": low,
        "sections": rows,
        "explanation": "Overall score is the rounded average of section scores. Drops should be reviewed by comparing lowest sections, unavailable evidence, and missing required sources.",
    }


def attach_score_details(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload or {})
    result["score_details"] = build_score_details(result)
    return result
