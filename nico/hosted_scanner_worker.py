from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from nico.scanner_tool_runners import redact_payload, redact_text, run_scanner_tools
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
    return run_command(command, cwd=workspace.root, limits=WorkerLimits(timeout_seconds=240, max_output_chars=12_000))


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


def _blocked_artifact(payload: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "artifact_schema": "nico.scanner_worker.v1",
        "worker_execution_state": "blocked",
        "repository": payload.get("repository"),
        "generated_at": _now_iso(),
        "tools": {},
        "unavailable_data_notes": [reason],
        "human_review_required": True,
    }


def _checkout_failed_artifact(payload: dict[str, Any], checkout: WorkerCommandResult) -> dict[str, Any]:
    output = redact_text((checkout.stdout or "") + "\n" + (checkout.stderr or ""))
    return {
        "artifact_schema": "nico.scanner_worker.v1",
        "worker_execution_state": "checkout_failed",
        "repository": payload.get("repository"),
        "generated_at": _now_iso(),
        "tools": {},
        "checkout": {
            "returncode": checkout.returncode,
            "timed_out": checkout.timed_out,
            "output_truncated": checkout.output_truncated,
            "safe_output_preview": output[:2000],
            "full_history_secret_scan_requested": full_history_secret_scan_enabled(payload),
        },
        "unavailable_data_notes": ["Hosted scanner worker could not check out the authorized repository."],
        "human_review_required": True,
    }


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
    full_history = full_history_secret_scan_enabled(payload)
    temp_workspace = make_workspace("nico-hosted-scan-")
    try:
        workspace = workspace_from_temp(temp_workspace)
        checkout = checkout_for_hosted_scan(payload, workspace)
        if not checkout.ok:
            return _checkout_failed_artifact(payload, checkout)

        commit_count = _git_commit_count(workspace)
        scanner_artifact = run_scanner_tools(workspace)
        scanner_artifact.update(
            {
                "worker_execution_state": "completed",
                "repository": validate_repository(str(payload.get("repository") or "")),
                "generated_at": _now_iso(),
                "duration_seconds": round(time.monotonic() - started, 2),
                "checkout": {
                    "returncode": checkout.returncode,
                    "timed_out": checkout.timed_out,
                    "output_truncated": checkout.output_truncated,
                    "full_history_secret_scan_requested": full_history,
                    "commit_count": commit_count,
                    "history_depth": "full" if full_history else "shallow",
                },
                "retention_note": "Temporary hosted scanner workspace was deleted after artifact generation.",
                "human_review_required": True,
            }
        )
        return redact_payload(scanner_artifact)
    finally:
        temp_workspace.cleanup()
