from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from nico import scanner_worker as base
from nico.storage import STORE

_COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")


def _git(command: list[str], *, cwd: Path | None, env: dict[str, str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        shell=False,
        check=False,
    )


def clone_repository_at_snapshot(
    repository: str,
    commit_sha: str,
    workspace: Path,
    env: dict[str, str],
) -> tuple[Path | None, str, list[str]]:
    """Clone and verify the exact commit selected by the assessment snapshot."""

    if shutil.which("git") is None:
        return None, "", ["git is unavailable in this worker image; snapshot-bound repository clone was skipped."]
    if not _COMMIT_SHA_RE.fullmatch(str(commit_sha or "")):
        return None, "", ["A valid full repository snapshot commit SHA is required before scanner execution."]

    repo_path = workspace / "repo"
    clone = _git(
        ["git", "clone", "--filter=blob:none", "--no-checkout", base.safe_repo_url(repository), str(repo_path)],
        cwd=None,
        env=env,
    )
    clone_preview, _ = base.redact((clone.stdout or "") + "\n" + (clone.stderr or ""))
    if clone.returncode != 0:
        return None, "", [f"snapshot-bound git clone failed: {clone_preview[:1000]}"]

    fetch = _git(["git", "fetch", "--depth", "1", "origin", commit_sha], cwd=repo_path, env=env)
    fetch_preview, _ = base.redact((fetch.stdout or "") + "\n" + (fetch.stderr or ""))
    if fetch.returncode != 0:
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, "", [f"exact snapshot commit could not be fetched: {fetch_preview[:1000]}"]

    checkout = _git(["git", "checkout", "--detach", commit_sha], cwd=repo_path, env=env)
    checkout_preview, _ = base.redact((checkout.stdout or "") + "\n" + (checkout.stderr or ""))
    if checkout.returncode != 0:
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, "", [f"exact snapshot commit could not be checked out: {checkout_preview[:1000]}"]

    resolved = _git(["git", "rev-parse", "HEAD"], cwd=repo_path, env=env, timeout=30)
    actual_sha = (resolved.stdout or "").strip().lower()
    if resolved.returncode != 0 or actual_sha != commit_sha.lower():
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, actual_sha, ["Scanner checkout did not match the assessment snapshot commit; scanner execution was blocked."]

    size = base.directory_size(repo_path)
    if size > base.MAX_REPO_BYTES:
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, actual_sha, [f"repository exceeds max size limit: {size} bytes > {base.MAX_REPO_BYTES} bytes"]
    return repo_path, actual_sha, []


def _run_snapshot_scan(scan_id: str, payload: dict[str, Any]) -> None:
    customer_id = payload.get("customer_id") or "default_customer"
    project_id = payload.get("project_id") or "default_project"
    base.SCAN_JOBS[scan_id]["status"] = "running"
    base.SCAN_JOBS[scan_id]["updated_at"] = base.now_iso()
    STORE.put("scanner_runs", scan_id, base.SCAN_JOBS[scan_id])

    results: list[dict[str, Any]] = []
    unavailable_notes: list[str] = []
    redaction_applied = False
    repo_size = 0
    actual_commit_sha = ""
    deadline = time.monotonic() + base.TOTAL_SCAN_TIMEOUT_SECONDS

    with tempfile.TemporaryDirectory(prefix="nico-snapshot-scan-") as workspace_name:
        workspace = Path(workspace_name)
        env = base.clean_env(workspace)
        try:
            repo_path, actual_commit_sha, clone_notes = clone_repository_at_snapshot(
                str(payload.get("repository") or ""),
                str(payload.get("snapshot_commit_sha") or ""),
                workspace,
                env,
            )
            unavailable_notes.extend(clone_notes)
            if repo_path:
                repo_size = base.directory_size(repo_path)
                for name, cfg in base.selected_tools(payload.get("tools") or []).items():
                    if time.monotonic() >= deadline:
                        results.append(base.unavailable_result(name, cfg, ["Total scan timeout reached before this scanner ran."]))
                        continue
                    result = base.run_tool(name, cfg, repo_path, env, deadline)
                    redaction_applied = redaction_applied or bool(result.get("secret_redaction_applied"))
                    results.append(result)
        except Exception as exc:
            unavailable_notes.append(f"Snapshot-bound worker failed safely: {exc}")

    unavailable = [item["scanner"] for item in results if item.get("status") == "unavailable"]
    failed = [item["scanner"] for item in results if item.get("status") in {"failed", "error"}]
    timed_out = [item["scanner"] for item in results if item.get("status") == "timeout"]
    snapshot_match = bool(actual_commit_sha) and actual_commit_sha == str(payload.get("snapshot_commit_sha") or "").lower()
    base.SCAN_JOBS[scan_id].update(
        {
            "status": "complete" if snapshot_match else "unavailable",
            "updated_at": base.now_iso(),
            "completed_at": base.now_iso(),
            "run_id": payload.get("run_id") or base.SCAN_JOBS[scan_id].get("run_id") or "",
            "snapshot_id": payload.get("snapshot_id") or "",
            "snapshot_commit_sha": payload.get("snapshot_commit_sha") or "",
            "actual_commit_sha": actual_commit_sha,
            "snapshot_match": snapshot_match,
            "tools_requested": list(base.selected_tools(payload.get("tools") or []).keys()),
            "tools_run": [item["scanner"] for item in results if item.get("status") in {"passed", "failed", "timeout", "error"}],
            "unavailable_tools": unavailable,
            "failed_tools": failed,
            "timed_out_tools": timed_out,
            "scanner_results": results,
            "evidence_summary": {
                "mode": "snapshot_bound_scanner_worker",
                "repository": payload.get("repository"),
                "run_id": payload.get("run_id") or base.SCAN_JOBS[scan_id].get("run_id") or "",
                "snapshot_id": payload.get("snapshot_id") or "",
                "snapshot_commit_sha": payload.get("snapshot_commit_sha") or "",
                "actual_commit_sha": actual_commit_sha,
                "snapshot_match": snapshot_match,
                "repo_size_bytes": repo_size,
                "tools_requested": len(base.selected_tools(payload.get("tools") or [])),
                "tools_run": len([item for item in results if item.get("status") in {"passed", "failed", "timeout", "error"}]),
                "unavailable_tools": len(unavailable),
                "failed_tools": len(failed),
                "timed_out_tools": len(timed_out),
            },
            "unavailable_data_notes": unavailable_notes,
            "secret_redaction_applied": redaction_applied,
            "retention_note": "Temporary snapshot-bound scan workspace was deleted after completion.",
            "human_review_required": True,
        }
    )
    STORE.put("scanner_runs", scan_id, base.SCAN_JOBS[scan_id])
    STORE.audit(
        "scanner.snapshot_completed",
        {
            "scan_id": scan_id,
            "status": base.SCAN_JOBS[scan_id]["status"],
            "snapshot_id": payload.get("snapshot_id") or "",
            "snapshot_commit_sha": payload.get("snapshot_commit_sha") or "",
            "actual_commit_sha": actual_commit_sha,
            "snapshot_match": snapshot_match,
        },
        customer_id=customer_id,
        project_id=project_id,
    )


def start_snapshot_scan(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("authorized"):
        return {"status": "blocked", "error": "Explicit authorization is required before snapshot-bound scanner execution."}
    repository = str(payload.get("repository") or "")
    commit_sha = str(payload.get("snapshot_commit_sha") or "").lower()
    snapshot_id = str(payload.get("snapshot_id") or "")
    if not repository:
        return {"status": "blocked", "error": "repository is required."}
    if not snapshot_id or not _COMMIT_SHA_RE.fullmatch(commit_sha):
        return {"status": "blocked", "error": "A captured repository snapshot ID and full commit SHA are required."}
    if not str(payload.get("authorized_by") or "").strip() or str(payload.get("authorized_by")).strip().lower() == "unspecified":
        return {"status": "blocked", "error": "authorized_by is required."}
    if not str(payload.get("authorization_scope") or "").strip():
        return {"status": "blocked", "error": "authorization_scope is required."}
    try:
        base.safe_repo_url(repository)
    except ValueError as exc:
        return {"status": "blocked", "error": str(exc)}

    scan_id = f"scan_snapshot_{uuid4().hex[:16]}"
    job = {
        "scan_id": scan_id,
        "run_id": payload.get("run_id") or "",
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "repository": repository,
        "snapshot_id": snapshot_id,
        "snapshot_commit_sha": commit_sha,
        "actual_commit_sha": "",
        "snapshot_match": False,
        "status": "queued",
        "created_at": base.now_iso(),
        "updated_at": base.now_iso(),
        "authorized_by": payload.get("authorized_by"),
        "authorization_scope": payload.get("authorization_scope"),
        "code_modification_allowed": False,
        "draft_pr_creation_allowed": False,
        "tools_requested": list(base.selected_tools(payload.get("tools") or []).keys()),
        "tools_run": [],
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "max_repo_bytes": base.MAX_REPO_BYTES,
        "tool_timeout_seconds": base.DEFAULT_TOOL_TIMEOUT_SECONDS,
        "total_scan_timeout_seconds": base.TOTAL_SCAN_TIMEOUT_SECONDS,
        "max_output_chars": base.MAX_OUTPUT_CHARS,
        "human_review_required": True,
    }
    base.SCAN_JOBS[scan_id] = job
    STORE.put("scanner_runs", scan_id, job)
    STORE.audit(
        "scanner.snapshot_queued",
        {
            "scan_id": scan_id,
            "run_id": job.get("run_id"),
            "repository": repository,
            "snapshot_id": snapshot_id,
            "snapshot_commit_sha": commit_sha,
        },
        customer_id=job["customer_id"],
        project_id=job["project_id"],
    )
    threading.Thread(target=_run_snapshot_scan, args=(scan_id, dict(payload)), daemon=True).start()
    return job
