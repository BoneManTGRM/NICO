from __future__ import annotations

import hashlib
import json
from typing import Any


INVALID_COMPLEXITY_RISKS = {
    "review_required",
    "unavailable",
    "unknown",
    "failed",
    "error",
    "blocked",
    "not_run",
}


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _report_run_id(result: dict[str, Any]) -> str:
    existing = result.get("report_run_id") or result.get("run_id") or result.get("assessment_id")
    if existing:
        return str(existing)
    basis = {
        "repository": result.get("repository") or result.get("repo"),
        "generated_at": result.get("generated_at"),
        "project": result.get("project_name"),
    }
    return "run_" + _hash_payload(basis)[:16]


def _scanner_artifact(result: dict[str, Any]) -> dict[str, Any]:
    value = result.get("scanner_worker_artifact")
    return value if isinstance(value, dict) else {}


def _complexity_profile(result: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(result.get("complexity_engine"), dict):
        return result["complexity_engine"]
    scanner = _scanner_artifact(result)
    profile = scanner.get("complexity_engine")
    if isinstance(profile, dict):
        return profile
    existing = result.get("complexity_artifact")
    if isinstance(existing, dict) and isinstance(existing.get("profile"), dict):
        return existing["profile"]
    return None


def _commit_sha(result: dict[str, Any], profile: dict[str, Any]) -> str:
    scanner = _scanner_artifact(result)
    checkout = scanner.get("checkout") if isinstance(scanner.get("checkout"), dict) else {}
    bundle = result.get("scanner_artifacts") if isinstance(result.get("scanner_artifacts"), dict) else {}
    return str(
        result.get("commit_sha")
        or result.get("head_sha")
        or result.get("deploy_commit")
        or profile.get("commit_sha")
        or bundle.get("commit_sha")
        or checkout.get("commit_sha")
        or "unknown"
    )


def _find_section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    for section in result.get("sections", []) or []:
        if isinstance(section, dict) and section.get("id") == section_id:
            return section
    return None


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def _clear_stale_complexity_lines(section: dict[str, Any]) -> None:
    fragments = (
        "complexity engine",
        "current-run complexity",
        "deeper complexity analysis",
        "missing runtime artifacts",
        "source-footprint",
        "release-readiness lift not applied",
        "complexity proof is incomplete",
    )
    lowered = tuple(item.lower() for item in fragments)
    for key in ("evidence", "findings", "unavailable"):
        values = section.get(key) or []
        if not isinstance(values, list):
            values = [values]
        section[key] = [line for line in values if not any(fragment in str(line).lower() for fragment in lowered)]


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _verified(profile: dict[str, Any]) -> bool:
    analyzed = _positive_int(profile.get("analyzed_file_count") or profile.get("files_analyzed") or profile.get("source_file_count"))
    total_loc = _positive_int(profile.get("total_loc") or profile.get("total_source_loc"))
    functions = _positive_int(profile.get("total_functions") or profile.get("functions_measured"))
    risk = str(profile.get("risk_level") or profile.get("risk") or "unknown").strip().lower()
    return analyzed > 0 and total_loc > 0 and functions > 0 and risk not in INVALID_COMPLEXITY_RISKS


def _artifact(result: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    report_run_id = _report_run_id(result)
    repository = str(result.get("repository") or result.get("repo") or "")
    commit_sha = _commit_sha(result, profile)
    verified = _verified(profile)
    summary = {
        "source_file_count": _positive_int(profile.get("source_file_count") or profile.get("files_considered")),
        "analyzed_file_count": _positive_int(profile.get("analyzed_file_count") or profile.get("files_analyzed")),
        "total_loc": _positive_int(profile.get("total_loc") or profile.get("total_source_loc")),
        "total_functions": _positive_int(profile.get("total_functions") or profile.get("functions_measured")),
        "call_graph_edge_count": _positive_int(profile.get("call_graph_edge_count")),
        "max_file_cyclomatic_complexity": _positive_int(
            profile.get("max_file_cyclomatic_complexity") or profile.get("maximum_cyclomatic_complexity")
        ),
        "manifest_dependency_count": _positive_int(profile.get("manifest_dependency_count")),
        "complexity_score": _positive_int(profile.get("complexity_score")),
        "velocity_score": _positive_int(profile.get("velocity_score")),
        "risk_level": str(profile.get("risk_level") or profile.get("risk") or "unknown"),
    }
    default_guardrail = (
        "Complexity evidence is generated from the exact checked-out repository state and only supports score lifts when bound to this report run."
    )
    payload = {
        "artifact_schema": "nico.complexity_artifact.v1",
        "status": "completed" if verified else "unavailable",
        "report_run_id": report_run_id,
        "repository": repository,
        "commit_sha": commit_sha,
        "generated_at": str(result.get("generated_at") or ""),
        "verified_for_this_report": verified,
        "tool_name": "complexity engine",
        "source": str(profile.get("source") or "checked_out_repository_complexity"),
        "evidence_scope": str(profile.get("evidence_scope") or "Exact checked-out repository state."),
        "summary": summary,
        "profile": profile,
        "evidence": list(profile.get("evidence") or []),
        "findings": list(profile.get("findings") or []),
        "unavailable": list(profile.get("unavailable") or profile.get("unavailable_data_notes") or []),
        "guardrail": str(profile.get("guardrail") or default_guardrail),
    }
    payload["artifact_hash"] = _hash_payload(payload)
    return payload


def _attach_unavailable(section: dict[str, Any], artifact: dict[str, Any]) -> None:
    section.setdefault("unavailable", [])
    if not isinstance(section["unavailable"], list):
        section["unavailable"] = [section["unavailable"]]
    summary = artifact["summary"]
    _append_unique(
        section["unavailable"],
        "Complexity evidence is unavailable for scoring: "
        f"analyzed_files={summary['analyzed_file_count']}, LOC={summary['total_loc']}, "
        f"function_units={summary['total_functions']}, risk={summary['risk_level']}.",
    )


def _attach_to_velocity(section: dict[str, Any], artifact: dict[str, Any]) -> None:
    _clear_stale_complexity_lines(section)
    if artifact.get("status") != "completed":
        _attach_unavailable(section, artifact)
        return
    summary = artifact["summary"]
    section.setdefault("evidence", [])
    if not isinstance(section["evidence"], list):
        section["evidence"] = [section["evidence"]]
    _append_unique(
        section["evidence"],
        "Complexity engine current-run artifact completed: "
        f"{summary['analyzed_file_count']} source file(s), {summary['total_loc']} LOC, "
        f"{summary['total_functions']} function-like units, {summary['call_graph_edge_count']} call-graph edge(s), "
        f"max measured complexity {summary['max_file_cyclomatic_complexity']}, risk={summary['risk_level']}.",
    )
    _append_unique(
        section["evidence"],
        f"Complexity artifact bound to report_run_id={artifact['report_run_id']} commit_sha={artifact['commit_sha']} hash={artifact['artifact_hash'][:16]}.",
    )
    _append_unique(section["evidence"], f"Complexity evidence scope: {artifact['evidence_scope']}")
    for line in artifact.get("evidence", [])[:4]:
        _append_unique(section["evidence"], str(line))

    section.setdefault("findings", [])
    if not isinstance(section["findings"], list):
        section["findings"] = [section["findings"]]
    for line in artifact.get("findings", [])[:6]:
        _append_unique(section["findings"], "Complexity engine finding: " + str(line))

    section.setdefault("unavailable", [])
    if not isinstance(section["unavailable"], list):
        section["unavailable"] = [section["unavailable"]]
    for line in artifact.get("unavailable", [])[:4]:
        _append_unique(section["unavailable"], "Complexity engine unavailable evidence: " + str(line))


def _attach_to_architecture(section: dict[str, Any], artifact: dict[str, Any]) -> None:
    if artifact.get("status") != "completed":
        _attach_unavailable(section, artifact)
        return
    section.setdefault("evidence", [])
    if not isinstance(section["evidence"], list):
        section["evidence"] = [section["evidence"]]
    summary = artifact["summary"]
    _append_unique(
        section["evidence"],
        "Architecture complexity support: current-run complexity artifact reports "
        f"{summary['analyzed_file_count']} analyzed source file(s), complexity_score={summary['complexity_score']}, "
        f"risk={summary['risk_level']}.",
    )


def attach_complexity_artifact_to_report(result: dict[str, Any]) -> dict[str, Any]:
    """Attach current-run complexity/call-graph evidence to report sections."""
    if result.get("status") != "complete":
        return result
    guards = result.setdefault("report_quality_guards", {})
    profile = _complexity_profile(result)
    if not profile:
        guards["complexity_artifact"] = {
            "status": "missing",
            "artifact_attached": False,
            "guardrail": "No complexity profile was attached to this report run.",
        }
        return result

    artifact = _artifact(result, profile)
    result["report_run_id"] = artifact["report_run_id"]
    result["complexity_artifact"] = artifact

    velocity = _find_section(result, "velocity_complexity")
    if velocity:
        _attach_to_velocity(velocity, artifact)
    architecture = _find_section(result, "architecture_debt")
    if architecture:
        _attach_to_architecture(architecture, artifact)

    guards["complexity_artifact"] = {
        "status": artifact["status"],
        "artifact_attached": True,
        "artifact_hash": artifact["artifact_hash"],
        "report_run_id": artifact["report_run_id"],
        "commit_sha": artifact["commit_sha"],
        "verified_for_this_report": artifact["verified_for_this_report"],
        "source_file_count": artifact["summary"]["source_file_count"],
        "analyzed_file_count": artifact["summary"]["analyzed_file_count"],
        "total_loc": artifact["summary"]["total_loc"],
        "total_functions": artifact["summary"]["total_functions"],
        "call_graph_edge_count": artifact["summary"]["call_graph_edge_count"],
        "source": artifact["source"],
        "guardrail": artifact["guardrail"],
    }
    return result
