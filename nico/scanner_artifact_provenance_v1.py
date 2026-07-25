from __future__ import annotations

import hashlib
import json
import os
import re
from functools import wraps
from pathlib import Path
from typing import Any, Callable

VERSION = "nico.scanner_artifact_provenance.v1"
SCANNER_CONTRACT_VERSION = "nico.scanner_worker.v3"
_PATCH_MARKER = "_nico_scanner_artifact_provenance_v1"


def _first_env(*names: str) -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _git_head(repo_dir: Path) -> str:
    git_dir = repo_dir / ".git"
    head_path = git_dir / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if re.fullmatch(r"[0-9a-fA-F]{40}", head):
        return head.lower()
    if not head.startswith("ref:"):
        return ""
    ref = head.split(":", 1)[1].strip()
    try:
        value = (git_dir / ref).read_text(encoding="utf-8").strip()
        if re.fullmatch(r"[0-9a-fA-F]{40}", value):
            return value.lower()
    except OSError:
        pass
    try:
        packed = (git_dir / "packed-refs").read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in packed.splitlines():
        if line.startswith("#") or line.startswith("^"):
            continue
        parts = line.split()
        if len(parts) == 2 and parts[1] == ref and re.fullmatch(r"[0-9a-fA-F]{40}", parts[0]):
            return parts[0].lower()
    return ""


def _remote_repository(repo_dir: Path) -> str:
    try:
        config = (repo_dir / ".git" / "config").read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(r"url\s*=\s*(?:https://github\.com/|git@github\.com:)([^\s]+?)(?:\.git)?\s*$", config, re.I | re.M)
    return match.group(1).strip("/").casefold() if match else ""


def _application_commit_sha() -> str:
    return _first_env(
        "NICO_RELEASE_SHA",
        "RENDER_GIT_COMMIT",
        "GITHUB_SHA",
        "COMMIT_SHA",
        "SOURCE_VERSION",
    ).lower()


def _worker_image_digest() -> str:
    return _first_env(
        "NICO_WORKER_IMAGE_DIGEST",
        "RENDER_IMAGE_DIGEST",
        "CONTAINER_IMAGE_DIGEST",
    ) or "unavailable"


def _artifact_hash(payload: dict[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in payload.items()
        if key not in {"artifact_hash", "stdout", "stderr"}
    }
    encoded = json.dumps(canonical, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _provenance(workspace: Any) -> dict[str, Any]:
    repo_dir = Path(getattr(workspace, "repo_dir", "") or ".")
    target_commit = _git_head(repo_dir)
    application_commit = _application_commit_sha()
    repository = _remote_repository(repo_dir)
    self_assessment = repository == "bonemantgrm/nico"
    comparable = self_assessment and bool(target_commit and application_commit)
    matches = target_commit == application_commit if comparable else None
    return {
        "application_commit_sha": application_commit or "unavailable",
        "target_commit_sha": target_commit or "unavailable",
        "target_repository": repository or "unavailable",
        "worker_image_digest": _worker_image_digest(),
        "worker_code_version": VERSION,
        "scanner_contract_version": SCANNER_CONTRACT_VERSION,
        "self_assessment": self_assessment,
        "self_assessment_commit_match": matches,
        "provenance_complete": bool(application_commit and target_commit),
    }


def _stamp_tool(payload: dict[str, Any], spec: Any, workspace: Any) -> dict[str, Any]:
    output = dict(payload)
    provenance = _provenance(workspace)
    output.update(
        {
            "application_commit_sha": provenance["application_commit_sha"],
            "worker_image_digest": provenance["worker_image_digest"],
            "worker_code_version": provenance["worker_code_version"],
            "scanner_tool_version": str(output.get("scanner_tool_version") or getattr(spec, "version", "") or getattr(spec, "name", "unknown")),
            "scanner_contract_version": provenance["scanner_contract_version"],
            "target_commit_sha": provenance["target_commit_sha"],
            "target_repository": provenance["target_repository"],
            "self_assessment_commit_match": provenance["self_assessment_commit_match"],
        }
    )
    output["artifact_hash"] = _artifact_hash(output)
    return output


def install_scanner_artifact_provenance_v1() -> dict[str, Any]:
    from nico import scanner_tool_runners as runners

    current_tool: Callable[..., Any] = runners.run_scanner_tool
    if getattr(current_tool, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "scanner_contract_version": SCANNER_CONTRACT_VERSION,
        }

    @wraps(current_tool)
    def run_scanner_tool(spec: Any, workspace: Any, *, runner: Any = None) -> dict[str, Any]:
        payload = current_tool(spec, workspace) if runner is None else current_tool(spec, workspace, runner=runner)
        return _stamp_tool(payload, spec, workspace) if isinstance(payload, dict) else payload

    setattr(run_scanner_tool, _PATCH_MARKER, True)
    runners.run_scanner_tool = run_scanner_tool

    current_tools: Callable[..., Any] = runners.run_scanner_tools

    @wraps(current_tools)
    def run_scanner_tools(workspace: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        artifact = current_tools(workspace, *args, **kwargs)
        if not isinstance(artifact, dict):
            return artifact
        provenance = _provenance(workspace)
        artifact["artifact_schema"] = SCANNER_CONTRACT_VERSION
        artifact["scanner_provenance"] = provenance
        artifact["application_commit_sha"] = provenance["application_commit_sha"]
        artifact["worker_image_digest"] = provenance["worker_image_digest"]
        artifact["worker_code_version"] = provenance["worker_code_version"]
        artifact["scanner_contract_version"] = provenance["scanner_contract_version"]
        artifact["target_commit_sha"] = provenance["target_commit_sha"]
        artifact["provenance_verified"] = provenance["self_assessment_commit_match"] is not False
        if provenance["self_assessment_commit_match"] is False:
            artifact["status"] = "blocked"
            artifact["reason"] = "scanner_worker_application_commit_mismatch"
        artifact["artifact_hash"] = _artifact_hash(artifact)
        return artifact

    setattr(run_scanner_tools, _PATCH_MARKER, True)
    runners.run_scanner_tools = run_scanner_tools
    return {
        "status": "installed",
        "version": VERSION,
        "scanner_contract_version": SCANNER_CONTRACT_VERSION,
        "application_commit_recorded": True,
        "worker_image_digest_recorded": True,
        "worker_code_version_recorded": True,
        "scanner_tool_version_recorded": True,
        "artifact_hash_recorded": True,
        "self_assessment_commit_mismatch_blocks": True,
    }


__all__ = [
    "SCANNER_CONTRACT_VERSION",
    "VERSION",
    "install_scanner_artifact_provenance_v1",
]
