from __future__ import annotations

import hashlib
import json
from typing import Any

from nico.scanner_tool_runners import TOOL_SPECS

ORCHESTRATION_SCHEMA = "nico.scanner_worker_orchestration.v1"


def stable_artifact_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _tool_payload_hash(payload: dict[str, Any]) -> str:
    safe_payload = {key: value for key, value in payload.items() if key not in {"stdout", "stderr"}}
    return stable_artifact_hash(safe_payload)


def _tool_entry(
    *,
    name: str,
    category: str,
    payload: dict[str, Any] | None,
    run_id: str,
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    payload = payload or {}
    findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    status = str(payload.get("status") or "missing")
    entry = {
        "run_id": run_id,
        "tool": name,
        "category": str(payload.get("category") or category),
        "status": status,
        "exit_code": payload.get("returncode"),
        "timed_out": bool(payload.get("timed_out")),
        "started_at": started_at,
        "finished_at": finished_at,
        "finding_count": len(findings),
        "has_findings": bool(findings),
        "scans_git_history": bool(payload.get("scans_git_history")),
        "execution_source": payload.get("execution_source") or "worker_command",
        "version": payload.get("version"),
        "artifact_hash": _tool_payload_hash(payload) if payload else None,
    }
    if payload.get("reason"):
        entry["reason"] = payload.get("reason")
    return entry


def build_scanner_worker_orchestration_manifest(
    artifact: dict[str, Any],
    *,
    repository: str,
    run_id: str,
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    """Build a report-safe orchestration manifest for every expected scanner tool."""
    raw_tools = artifact.get("tools") if isinstance(artifact.get("tools"), dict) else {}
    entries = []
    required_names = []
    for spec in TOOL_SPECS:
        required_names.append(spec.name)
        payload = raw_tools.get(spec.name) if isinstance(raw_tools, dict) else None
        entries.append(
            _tool_entry(
                name=spec.name,
                category=spec.category,
                payload=payload if isinstance(payload, dict) else None,
                run_id=run_id,
                started_at=started_at,
                finished_at=finished_at,
            )
        )

    completed = [item["tool"] for item in entries if item["status"] == "completed"]
    unavailable = [item["tool"] for item in entries if item["status"] in {"unavailable", "missing"}]
    timed_out = [item["tool"] for item in entries if item["timed_out"]]
    with_findings = [item["tool"] for item in entries if item["has_findings"]]

    manifest = {
        "artifact_schema": ORCHESTRATION_SCHEMA,
        "run_id": run_id,
        "repository": repository,
        "started_at": started_at,
        "finished_at": finished_at,
        "required_tool_count": len(required_names),
        "tools": entries,
        "completed_tools": completed,
        "unavailable_tools": unavailable,
        "timed_out_tools": timed_out,
        "finding_tools": with_findings,
        "guardrail": "Scanner orchestration is evidence-only. Unavailable tools, timeouts, and findings remain visible and cannot be counted as clean proof.",
    }
    manifest["manifest_hash"] = stable_artifact_hash({key: value for key, value in manifest.items() if key != "manifest_hash"})
    return manifest
