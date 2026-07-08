from __future__ import annotations

import hashlib
import json
from typing import Any

from nico.scanner_worker_artifacts import normalize_scanner_worker_artifact, scanner_worker_evidence_notes

CATEGORY_TO_SECTION = {
    "dependency": "dependency_health",
    "static": "static_analysis",
    "secret": "secrets_review",
    "coverage": "coverage",
}

SECTION_TOOL_PREFIXES = {
    "dependency_health": "Scanner-worker dependency tools",
    "static_analysis": "Scanner-worker static tools",
    "secrets_review": "Scanner-worker secret tools",
    "coverage": "Scanner-worker coverage tools",
}


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _artifact_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("scanner_worker_artifact", "scanner_artifacts", "scanner_worker"):
        value = result.get(key)
        if isinstance(value, dict):
            return value
    return None


def _section_id(section: dict[str, Any]) -> str:
    return str(section.get("id") or "")


def _find_section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    for section in result.get("sections", []) or []:
        if isinstance(section, dict) and _section_id(section) == section_id:
            return section
    return None


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def _remove_stale_scanner_lines(section: dict[str, Any], section_id: str) -> None:
    prefix = SECTION_TOOL_PREFIXES.get(section_id)
    if not prefix:
        return
    for key in ("evidence", "findings", "unavailable"):
        values = section.get(key) or []
        if not isinstance(values, list):
            values = [values]
        section[key] = [item for item in values if not str(item).startswith(prefix)]


def _note_for_section(section_id: str, notes: dict[str, list[str]]) -> dict[str, list[str]]:
    prefix = SECTION_TOOL_PREFIXES.get(section_id, "")
    return {
        key: [item for item in notes.get(key, []) if item.startswith(prefix)]
        for key in ("evidence", "findings", "unavailable")
    }


def _attach_section_notes(result: dict[str, Any], notes: dict[str, list[str]]) -> None:
    for section_id in SECTION_TOOL_PREFIXES:
        section = _find_section(result, section_id)
        if not section:
            continue
        _remove_stale_scanner_lines(section, section_id)
        section_notes = _note_for_section(section_id, notes)
        for key in ("evidence", "findings", "unavailable"):
            section.setdefault(key, [])
            if not isinstance(section[key], list):
                section[key] = [section[key]]
            for item in section_notes[key]:
                _append_unique(section[key], item)


def _current_run_summary(normalized: dict[str, Any]) -> dict[str, Any]:
    tools = normalized.get("tools") if isinstance(normalized.get("tools"), dict) else {}
    completed = sorted(tool for tool, payload in tools.items() if isinstance(payload, dict) and payload.get("completed"))
    unavailable = sorted(tool for tool, payload in tools.items() if isinstance(payload, dict) and not payload.get("completed"))
    return {
        "completed_tools": completed,
        "unavailable_tools": unavailable,
        "dependency_evidence_complete": bool(normalized.get("dependency_evidence_complete")),
        "static_evidence_complete": bool(normalized.get("static_evidence_complete")),
        "secret_evidence_complete": bool(normalized.get("secret_evidence_complete")),
        "dependency_finding_count": int(normalized.get("dependency_finding_count") or 0),
        "static_finding_count": int(normalized.get("static_finding_count") or 0),
        "secret_finding_count": int(normalized.get("secret_finding_count") or 0),
    }


def attach_scanner_artifacts_to_report(result: dict[str, Any]) -> dict[str, Any]:
    """Attach current-run scanner artifact proof to report sections.

    This converts raw scanner-worker output into section evidence before final QA,
    trust caps, evidence ledger creation, and export validation. Missing tools stay
    explicit unavailable evidence; completed tools become exact current-run proof.
    """

    if result.get("status") != "complete":
        return result
    artifact = _artifact_payload(result)
    guards = result.setdefault("report_quality_guards", {})
    if not artifact:
        guards["scanner_artifact_integration"] = {
            "status": "missing",
            "artifact_attached": False,
            "guardrail": "No scanner-worker artifact was attached to this report run.",
        }
        return result

    normalized = normalize_scanner_worker_artifact(artifact)
    artifact = dict(artifact)
    artifact["normalized"] = normalized
    artifact["artifact_hash"] = _hash_payload(artifact)
    artifact["verified_for_report_run"] = True
    result["scanner_worker_artifact"] = artifact
    result["scanner_artifact_summary"] = _current_run_summary(normalized)

    notes = scanner_worker_evidence_notes(artifact)
    _attach_section_notes(result, notes)

    guards["scanner_artifact_integration"] = {
        "status": "attached",
        "artifact_attached": True,
        "artifact_hash": artifact["artifact_hash"],
        "completed_tools": result["scanner_artifact_summary"]["completed_tools"],
        "unavailable_tools": result["scanner_artifact_summary"]["unavailable_tools"],
        "guardrail": "Completed scanner tools are current-run proof; unavailable tools remain explicit missing evidence.",
    }
    return result
