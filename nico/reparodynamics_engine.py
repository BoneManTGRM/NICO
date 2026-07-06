from __future__ import annotations

from typing import Any


def _sections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in payload.get("sections", []) or [] if isinstance(item, dict)]


def _ratio(done: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(max(0.0, min(1.0, done / total)), 3)


def reparodynamic_loop(payload: dict[str, Any]) -> dict[str, Any]:
    sections = _sections(payload)
    source_total = 0
    source_verified = 0
    unavailable_count = 0
    limited_count = 0
    red_count = 0
    repair_queue: list[dict[str, Any]] = []

    for item in sections:
        required = set(item.get("required_sources") or [])
        evidence = set(item.get("evidence_sources") or [])
        unavailable = set(item.get("unavailable_sources") or [])
        source_total += len(required)
        source_verified += len(required & evidence)
        unavailable_count += len(item.get("unavailable") or []) + len(unavailable)
        limited_count += 1 if item.get("confidence") in {"limited", "unavailable"} else 0
        red_count += 1 if item.get("status") == "red" else 0
        if item.get("status") in {"red", "yellow", "gray"} or item.get("confidence") in {"limited", "unavailable"}:
            repair_queue.append({
                "section": item.get("label") or item.get("id"),
                "status": item.get("status"),
                "confidence": item.get("confidence"),
                "priority": "high" if item.get("status") == "red" else "medium" if item.get("confidence") in {"limited", "unavailable"} else "normal",
                "reason": "Repair or evidence collection needed before stronger claims.",
            })

    detection_strength = _ratio(source_verified, source_total)
    unavailable_burden = _ratio(unavailable_count, max(1, unavailable_count + source_verified))
    repair_pressure = _ratio(red_count + limited_count, max(1, len(sections)))
    stabilization_score = round(max(0.0, min(1.0, 1 - ((unavailable_burden + repair_pressure) / 2))), 3)

    return {
        "loop": ["detect", "classify", "prioritize", "repair_plan", "approval", "verify", "trend", "stabilize"],
        "detection_strength": detection_strength,
        "unavailable_evidence_burden": unavailable_burden,
        "repair_pressure": repair_pressure,
        "stabilization_score": stabilization_score,
        "repair_queue": repair_queue[:12],
        "human_review_required": True,
        "interpretation": "Higher stabilization requires more verified required evidence, fewer unavailable sources, and fewer red or limited-confidence sections.",
    }
