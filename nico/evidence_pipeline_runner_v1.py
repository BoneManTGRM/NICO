from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

from nico.evidence_pipeline_common_v1 import (
    VERSION,
    _exact_sha,
    _prepare_node_project,
    _select_node_project,
)
from nico.evidence_pipeline_tool_v1 import _run_tool


def _tool_record(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool": name,
        "category": payload.get("category"),
        "status": payload.get("status"),
        "returncode": payload.get("returncode"),
        "findings_count": payload.get("findings_count", len(payload.get("findings") or [])),
        "current_run": payload.get("current_run", True),
        "execution_observed_for_this_report": payload.get("execution_observed_for_this_report", True),
        "verified_for_this_report": payload.get("verified_for_this_report", False),
        "full_history_verified": payload.get("full_history_verified", False),
        "artifact_hash": payload.get("artifact_hash"),
        "application_commit_sha": payload.get("application_commit_sha"),
        "target_commit_sha": payload.get("target_commit_sha"),
        "worker_image_digest": payload.get("worker_image_digest"),
        "worker_code_version": payload.get("worker_code_version"),
        "scanner_tool_version": payload.get("scanner_tool_version"),
        "scanner_contract_version": payload.get("scanner_contract_version"),
        "raw_output_artifact": payload.get("raw_output_artifact"),
        "reason": payload.get("reason") or payload.get("failure_or_unavailable_reason") or "",
    }


def _repeatability_fingerprint(tools: dict[str, dict[str, Any]], target_commit_sha: str) -> str:
    canonical_tools: dict[str, Any] = {}
    for name, payload in sorted(tools.items()):
        findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
        finding_hashes = sorted(
            hashlib.sha256(json.dumps(item, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()
            for item in findings
        )
        canonical_tools[name] = {
            "status": payload.get("status"),
            "returncode": payload.get("returncode"),
            "findings_count": payload.get("findings_count", len(findings)),
            "finding_hashes": finding_hashes,
            "full_history_verified": payload.get("full_history_verified", False),
        }
    encoded = json.dumps(
        {"target_commit_sha": target_commit_sha, "tools": canonical_tools},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _artifact_hash(payload: dict[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in payload.items()
        if key not in {"artifact_hash", "generated_at", "started_at", "finished_at", "duration_seconds", "run_id"}
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()


def _build_scanner_runner() -> tuple[Callable[..., dict[str, Any]], Callable[..., dict[str, Any]]]:
    from nico import scanner_tool_runners as runners
    from nico.scanner_artifact_provenance_v1 import SCANNER_CONTRACT_VERSION, _provenance

    runners.MAX_SCANNER_PARSE_BYTES = max(
        int(getattr(runners, "MAX_SCANNER_PARSE_BYTES", 0) or 0),
        int(os.getenv("NICO_MAX_SCANNER_PARSE_BYTES", str(256 * 1024 * 1024))),
    )

    def run_scanner_tool(
        spec: Any,
        workspace: Any,
        *,
        runner: Callable[..., Any] = runners.run_command,
        preparation: Any = None,
    ) -> dict[str, Any]:
        project = _select_node_project(workspace.repo_dir, spec.name) if spec.name in {"eslint", "typescript"} else None
        if project is not None and preparation is None:
            preparation = _prepare_node_project(runners, workspace, project[1], runner=runner)
        return _run_tool(runners, spec, workspace, runner=runner, project=project, preparation=preparation)

    def run_scanner_tools(
        workspace: Any,
        specs: Any = runners.TOOL_SPECS,
        *,
        runner: Callable[..., Any] = runners.run_command,
    ) -> dict[str, Any]:
        if not workspace.repo_dir.exists() or not workspace.repo_dir.is_dir():
            raise ValueError("workspace repo directory must exist before scanner tools run")
        preparation_cache: dict[Path, Any] = {}
        tool_results: list[dict[str, Any]] = []
        for spec in specs:
            project = _select_node_project(workspace.repo_dir, spec.name) if spec.name in {"eslint", "typescript"} else None
            preparation = None
            if project is not None:
                lock_root = project[1]
                if lock_root not in preparation_cache:
                    preparation_cache[lock_root] = _prepare_node_project(runners, workspace, lock_root, runner=runner)
                preparation = preparation_cache[lock_root]
            tool_results.append(_run_tool(runners, spec, workspace, runner=runner, project=project, preparation=preparation))
        tools = {item["tool"]: item for item in tool_results if isinstance(item, dict) and item.get("tool")}
        normalized = runners.normalize_scanner_worker_artifact({"tools": tools})
        provenance = _provenance(workspace)
        target_commit_sha = str(provenance.get("target_commit_sha") or "")
        history_secret_tools = [
            name
            for name, item in tools.items()
            if item.get("category") == "secret"
            and item.get("status") == "completed"
            and item.get("scans_git_history")
            and item.get("full_history_verified") is True
        ]
        artifact: dict[str, Any] = {
            "artifact_schema": SCANNER_CONTRACT_VERSION,
            "tools": tools,
            "normalized": normalized,
            "tool_records": [_tool_record(name, item) for name, item in sorted(tools.items())],
            "raw_output_artifacts": {
                name: item["raw_output_artifact"]
                for name, item in tools.items()
                if isinstance(item.get("raw_output_artifact"), dict)
            },
            "project_preparations": [
                {
                    "lock_root": str(path),
                    "status": prep.status,
                    "node_modules_ready": prep.node_modules_ready,
                    "reason": prep.reason,
                    "returncode": prep.returncode,
                    "timed_out": prep.timed_out,
                    "output_truncated": prep.output_truncated,
                }
                for path, prep in sorted(preparation_cache.items(), key=lambda item: str(item[0]))
            ],
            "secret_history_scan": {
                "completed_tools": history_secret_tools,
                "history_aware": len(history_secret_tools) == 2,
            },
            "scanner_provenance": provenance,
            "application_commit_sha": provenance.get("application_commit_sha"),
            "worker_image_digest": provenance.get("worker_image_digest"),
            "worker_code_version": VERSION,
            "scanner_contract_version": SCANNER_CONTRACT_VERSION,
            "target_commit_sha": target_commit_sha,
            "provenance_verified": bool(provenance.get("provenance_complete") and _exact_sha(target_commit_sha)),
            "retrospective_exact_sha_scan": bool(
                provenance.get("self_assessment") and provenance.get("self_assessment_commit_match") is False
            ),
        }
        artifact["repeatability_fingerprint"] = _repeatability_fingerprint(tools, target_commit_sha)
        artifact["artifact_hash"] = _artifact_hash(artifact)
        return runners.redact_payload(artifact)

    return run_scanner_tool, run_scanner_tools


__all__ = ["_artifact_hash", "_build_scanner_runner"]
