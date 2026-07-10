from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from nico.complexity_engine import build_complexity_profile
from nico.dependency_proof_inventory import build_dependency_proof_inventory
from nico.github_app_auth import build_github_clone_auth_env
from nico.scanner_tool_runners import redact_payload, redact_text, run_scanner_tools
from nico.scanner_worker_orchestration import build_scanner_worker_orchestration_manifest, stable_artifact_hash
from nico.worker_execution import (
    WorkerCommandResult,
    WorkerLimits,
    WorkerWorkspace,
    make_workspace,
    run_command,
    validate_ref,
    validate_repository,
    workspace_from_temp,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def hosted_scanner_autorun_enabled(payload: dict[str, Any]) -> bool:
    """Return whether hosted Express should attempt a scanner worker run.

    The browser still only needs owner/repo plus the authorization checkbox. The
    backend can disable this globally with NICO_ENABLE_HOSTED_SCANNER_AUTORUN=false
    or per request with run_scanner_worker/scanner_worker_autorun=false.
    """
    if os.getenv("NICO_ENABLE_HOSTED_SCANNER_AUTORUN", "true").lower() != "true":
        return False
    if payload.get("run_scanner_worker") is False or payload.get("scanner_worker_autorun") is False:
        return False
    return bool(payload.get("authorized") and payload.get("repository"))


def full_history_secret_scan_enabled(payload: dict[str, Any]) -> bool:
    """Return whether the worker should clone full git history for secret scanners."""
    if os.getenv("NICO_ENABLE_FULL_HISTORY_SECRET_SCAN", "true").lower() != "true":
        return False
    if payload.get("full_history_secret_scan") is False:
        return False
    return bool(payload.get("authorized") and payload.get("repository"))


def _clone_command(repository: str, ref: str | None, workspace: WorkerWorkspace, *, full_history: bool = False) -> tuple[str, ...]:
    repository = validate_repository(repository)
    clone_url = f"https://github.com/{repository}.git"
    command: list[str] = ["git", "clone", "--no-tags"]
    if not full_history:
        command.extend(["--depth", "1"])
    if ref:
        command.extend(["--branch", validate_ref(ref)])
    command.extend([clone_url, str(workspace.repo_dir)])
    return tuple(command)


def checkout_for_hosted_scan(payload: dict[str, Any], workspace: WorkerWorkspace) -> WorkerCommandResult:
    repository = str(payload.get("repository") or "")
    ref = payload.get("ref") or payload.get("branch") or payload.get("default_branch") or ""
    command = _clone_command(
        repository,
        str(ref).strip() or None,
        workspace,
        full_history=full_history_secret_scan_enabled(payload),
    )
    clone_auth = build_github_clone_auth_env()
    return run_command(
        command,
        cwd=workspace.root,
        limits=WorkerLimits(timeout_seconds=240, max_output_chars=12_000),
        extra_env=clone_auth.extra_env,
    )


def _git_commit_count(workspace: WorkerWorkspace) -> int | None:
    if not workspace.repo_dir.exists():
        return None
    result = run_command(("git", "rev-list", "--count", "HEAD"), cwd=workspace.repo_dir, limits=WorkerLimits(timeout_seconds=30, max_output_chars=2_000))
    if not result.ok:
        return None
    try:
        return int((result.stdout or "").strip())
    except ValueError:
        return None


def _git_head_sha(workspace: WorkerWorkspace) -> str | None:
    if not workspace.repo_dir.exists():
        return None
    result = run_command(("git", "rev-parse", "HEAD"), cwd=workspace.repo_dir, limits=WorkerLimits(timeout_seconds=30, max_output_chars=2_000))
    if not result.ok:
        return None
    value = (result.stdout or "").strip()
    return value or None


def _clone_auth_metadata() -> dict[str, Any]:
    clone_auth = build_github_clone_auth_env()
    return {
        "mode": clone_auth.mode,
        "evidence": clone_auth.evidence,
        "unavailable": clone_auth.unavailable,
    }


def _blocked_artifact(payload: dict[str, Any], reason: str) -> dict[str, Any]:
    generated_at = _now_iso()
    repository = payload.get("repository")
    run_id = stable_artifact_hash({"repository": repository, "generated_at": generated_at, "state": "blocked"})[:16]
    artifact = {
        "artifact_schema": "nico.scanner_worker.v1",
        "worker_execution_state": "blocked",
        "repository": repository,
        "generated_at": generated_at,
        "run_id": run_id,
        "tools": {},
        "dependency_proof": build_dependency_proof_inventory(__import__("pathlib").Path("."), {}),
        "unavailable_data_notes": [reason],
        "human_review_required": True,
    }
    artifact["orchestration"] = build_scanner_worker_orchestration_manifest(
        artifact,
        repository=str(repository or ""),
        run_id=run_id,
        started_at=generated_at,
        finished_at=generated_at,
    )
    return artifact


def _checkout_failed_artifact(payload: dict[str, Any], checkout: WorkerCommandResult) -> dict[str, Any]:
    output = redact_text((checkout.stdout or "") + "\n" + (checkout.stderr or ""))
    clone_auth = _clone_auth_metadata()
    generated_at = _now_iso()
    repository = payload.get("repository")
    run_id = stable_artifact_hash({"repository": repository, "generated_at": generated_at, "state": "checkout_failed"})[:16]
    artifact = {
        "artifact_schema": "nico.scanner_worker.v1",
        "worker_execution_state": "checkout_failed",
        "repository": repository,
        "generated_at": generated_at,
        "run_id": run_id,
        "tools": {},
        "dependency_proof": build_dependency_proof_inventory(__import__("pathlib").Path("."), {}),
        "checkout": {
            "returncode": checkout.returncode,
            "timed_out": checkout.timed_out,
            "output_truncated": checkout.output_truncated,
            "safe_output_preview": output[:2000],
            "full_history_secret_scan_requested": full_history_secret_scan_enabled(payload),
            "auth_mode": clone_auth["mode"],
        },
        "unavailable_data_notes": ["Hosted scanner worker could not check out the authorized repository."] + clone_auth["unavailable"],
        "human_review_required": True,
    }
    artifact["orchestration"] = build_scanner_worker_orchestration_manifest(
        artifact,
        repository=str(repository or ""),
        run_id=run_id,
        started_at=generated_at,
        finished_at=generated_at,
    )
    return artifact


def run_hosted_scanner_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Synchronously run scanner tools for an authorized hosted Express assessment.

    This creates a temporary isolated checkout, executes available scanner tools,
    redacts tool output, returns a report-safe artifact, and removes the workspace.
    Missing executables, disabled project-command tools, timeouts, or checkout errors
    remain explicit unavailable evidence instead of being treated as clean results.
    """
    if not hosted_scanner_autorun_enabled(payload):
        return _blocked_artifact(payload, "Hosted scanner worker auto-run is disabled or the request is not explicitly authorized.")

    try:
        validate_repository(str(payload.get("repository") or ""))
    except ValueError as exc:
        return _blocked_artifact(payload, str(exc))

    started = time.monotonic()
    started_at = _now_iso()
    full_history = full_history_secret_scan_enabled(payload)
    clone_auth = _clone_auth_metadata()
    temp_workspace = make_workspace("nico-hosted-scan-")
    try:
        workspace = workspace_from_temp(temp_workspace)
        checkout = checkout_for_hosted_scan(payload, workspace)
        if not checkout.ok:
            return _checkout_failed_artifact(payload, checkout)

        commit_count = _git_commit_count(workspace)
        commit_sha = _git_head_sha(workspace)
        repository = validate_repository(str(payload.get("repository") or ""))
        run_id = stable_artifact_hash({"repository": repository, "started_at": started_at, "commit_sha": commit_sha})[:16]
        scanner_artifact = run_scanner_tools(workspace)
        scanner_artifact["dependency_proof"] = build_dependency_proof_inventory(workspace.repo_dir, scanner_artifact.get("tools") if isinstance(scanner_artifact.get("tools"), dict) else {})
        scanner_artifact["complexity_engine"] = build_complexity_profile(workspace.repo_dir)
        finished_at = _now_iso()
        scanner_artifact.update(
            {
                "worker_execution_state": "completed",
                "repository": repository,
                "generated_at": finished_at,
                "started_at": started_at,
                "finished_at": finished_at,
                "run_id": run_id,
                "duration_seconds": round(time.monotonic() - started, 2),
                "checkout": {
                    "returncode": checkout.returncode,
                    "timed_out": checkout.timed_out,
                    "output_truncated": checkout.output_truncated,
                    "full_history_secret_scan_requested": full_history,
                    "commit_count": commit_count,
                    "commit_sha": commit_sha,
                    "history_depth": "full" if full_history else "shallow",
                    "auth_mode": clone_auth["mode"],
                },
                "private_repo_auth": clone_auth,
                "retention_note": "Temporary hosted scanner workspace was deleted after artifact generation.",
                "human_review_required": True,
            }
        )
        scanner_artifact["orchestration"] = build_scanner_worker_orchestration_manifest(
            scanner_artifact,
            repository=repository,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
        )
        scanner_artifact["artifact_hash"] = stable_artifact_hash({key: value for key, value in scanner_artifact.items() if key != "artifact_hash"})
        return redact_payload(scanner_artifact)
    finally:
        temp_workspace.cleanup()
