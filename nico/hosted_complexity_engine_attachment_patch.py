from __future__ import annotations

import hashlib
import json
from typing import Any

COMPLEXITY_SCHEMA = "nico.complexity_attachment.v1"
REQUIRED_COMPLEXITY_KEYS = (
    "source_file_count",
    "total_loc",
    "total_functions",
    "call_graph_edge_count",
    "max_file_cyclomatic_complexity",
    "complexity_score",
    "architecture_score",
    "velocity_score",
    "risk_level",
    "hotspots",
)


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _complexity_profile_valid(profile: dict[str, Any]) -> bool:
    if not isinstance(profile, dict) or not profile:
        return False
    return all(key in profile for key in REQUIRED_COMPLEXITY_KEYS)


def build_complexity_attachment_summary(profile: dict[str, Any] | None) -> dict[str, Any]:
    profile = profile if isinstance(profile, dict) else {}
    valid = _complexity_profile_valid(profile)
    hotspots = profile.get("hotspots") if isinstance(profile.get("hotspots"), list) else []
    top_hotspots = [item for item in hotspots[:8] if isinstance(item, dict)]
    summary = {
        "artifact_schema": COMPLEXITY_SCHEMA,
        "profile_schema": profile.get("artifact_schema") if isinstance(profile, dict) else None,
        "status": "completed" if valid else "unavailable",
        "current_run": valid,
        "verified_for_this_report": valid,
        "source_file_count": _as_int(profile.get("source_file_count")),
        "total_loc": _as_int(profile.get("total_loc")),
        "total_functions": _as_int(profile.get("total_functions")),
        "call_graph_edge_count": _as_int(profile.get("call_graph_edge_count")),
        "max_file_cyclomatic_complexity": _as_int(profile.get("max_file_cyclomatic_complexity")),
        "complexity_score": _as_int(profile.get("complexity_score")),
        "architecture_score": _as_int(profile.get("architecture_score")),
        "velocity_score": _as_int(profile.get("velocity_score")),
        "risk_level": str(profile.get("risk_level") or "unknown"),
        "hotspot_count": len(hotspots),
        "top_hotspots": [
            {
                "path": item.get("path"),
                "hotspot_score": item.get("hotspot_score"),
                "loc": item.get("loc"),
                "cyclomatic_complexity": item.get("cyclomatic_complexity"),
                "churn": item.get("churn"),
                "primary_owner": item.get("primary_owner"),
                "owner_concentration": item.get("owner_concentration"),
            }
            for item in top_hotspots
        ],
        "evidence_count": len(profile.get("evidence") if isinstance(profile.get("evidence"), list) else []),
        "finding_count": len(profile.get("findings") if isinstance(profile.get("findings"), list) else []),
        "unavailable_reason": "" if valid else "Complexity engine profile is missing or incomplete for this report.",
        "guardrail": "Architecture and Velocity score movement requires a current-run complexity profile with source footprint, cyclomatic, hotspot, churn, ownership, and dependency-surface signals attached.",
    }
    summary["artifact_hash"] = _stable_hash(summary)
    return summary


def _attach_complexity_summary_to_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        return artifact
    profile = artifact.get("complexity_engine") if isinstance(artifact.get("complexity_engine"), dict) else None
    artifact["complexity_engine_summary"] = build_complexity_attachment_summary(profile)
    return artifact


def _patch_hosted_scanner_worker_complexity_summary() -> None:
    from nico import hosted_scanner_worker

    original = getattr(hosted_scanner_worker, "_nico_original_run_hosted_scanner_worker_complexity_attachment", None)
    if original is None:
        original = hosted_scanner_worker.run_hosted_scanner_worker
        hosted_scanner_worker._nico_original_run_hosted_scanner_worker_complexity_attachment = original

    def run_hosted_scanner_worker_with_complexity_summary(payload: dict[str, Any]) -> dict[str, Any]:
        original_func = hosted_scanner_worker._nico_original_run_hosted_scanner_worker_complexity_attachment
        artifact = original_func(payload)
        return _attach_complexity_summary_to_artifact(artifact) if isinstance(artifact, dict) else artifact

    hosted_scanner_worker.run_hosted_scanner_worker = run_hosted_scanner_worker_with_complexity_summary


def _patch_scanner_artifact_attachment_complexity_summary() -> None:
    from nico import hosted_scanner_artifacts

    original = getattr(hosted_scanner_artifacts, "_nico_original_attach_scanner_worker_artifacts_complexity_attachment", None)
    if original is None:
        original = hosted_scanner_artifacts.attach_scanner_worker_artifacts
        hosted_scanner_artifacts._nico_original_attach_scanner_worker_artifacts_complexity_attachment = original

    def attach_scanner_worker_artifacts_with_complexity_summary(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        original_func = hosted_scanner_artifacts._nico_original_attach_scanner_worker_artifacts_complexity_attachment
        output = original_func(result, payload)
        if not isinstance(output, dict):
            return output
        artifact = payload.get("scanner_worker_artifact") or payload.get("scanner_artifact") or payload.get("worker_artifact") or payload.get("scanner_worker")
        if isinstance(artifact, dict) and artifact.get("complexity_engine_summary"):
            output["complexity_engine_summary"] = artifact["complexity_engine_summary"]
        elif isinstance(output.get("complexity_engine"), dict):
            output["complexity_engine_summary"] = build_complexity_attachment_summary(output["complexity_engine"])
        return output

    hosted_scanner_artifacts.attach_scanner_worker_artifacts = attach_scanner_worker_artifacts_with_complexity_summary


def install_hosted_complexity_engine_attachment_patch() -> None:
    _patch_hosted_scanner_worker_complexity_summary()
    _patch_scanner_artifact_attachment_complexity_summary()
