from __future__ import annotations

from typing import Any


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def attach_report_readiness_gate(report: dict[str, Any], gate: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach readiness gate evidence to a report payload without hiding blockers."""
    result = dict(report or {})
    readiness_gate = _dict(gate)
    result["report_readiness_gate"] = readiness_gate or {
        "artifact_schema": "nico.report_readiness_gate.v1",
        "status": "missing_report_readiness_gate",
        "report_delivery_allowed": False,
        "missing": ["report_readiness_gate"],
        "blockers": ["Report readiness gate artifact was not supplied."],
        "human_review_required": True,
    }

    gate_status = result["report_readiness_gate"].get("status", "unknown")
    delivery_allowed = bool(result["report_readiness_gate"].get("report_delivery_allowed"))
    missing = [str(item) for item in _list(result["report_readiness_gate"].get("missing"))]
    blockers = [str(item) for item in _list(result["report_readiness_gate"].get("blockers"))]

    result["delivery_readiness"] = {
        "status": "delivery_ready" if delivery_allowed else "delivery_blocked",
        "gate_status": gate_status,
        "delivery_allowed": delivery_allowed,
        "missing": missing,
        "blockers": blockers,
        "human_review_required": True,
    }

    unavailable = [str(item) for item in _list(result.get("unavailable_data_notes"))]
    if not delivery_allowed:
        note = f"Report delivery blocked by readiness gate: {gate_status}."
        if note not in unavailable:
            unavailable.append(note)
    for item in missing:
        note = f"Missing readiness evidence: {item}."
        if note not in unavailable:
            unavailable.append(note)
    for item in blockers:
        note = f"Readiness blocker: {item}."
        if note not in unavailable:
            unavailable.append(note)
    result["unavailable_data_notes"] = unavailable

    evidence_bundle = _dict(result.get("evidence_artifact_bundle"))
    artifacts = [dict(item) for item in _list(evidence_bundle.get("artifacts")) if isinstance(item, dict)]
    artifacts.append(
        {
            "artifact_schema": "nico.report_readiness_attachment.v1",
            "type": "report_readiness_gate",
            "status": gate_status,
            "delivery_allowed": delivery_allowed,
        }
    )
    evidence_bundle["artifacts"] = artifacts
    result["evidence_artifact_bundle"] = evidence_bundle
    return result
