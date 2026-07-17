from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


SNAPSHOT_FULL_HISTORY_RECOVERY_V7 = "nico.snapshot_full_history_recovery.v7"
_PATCH_MARKER = "_nico_snapshot_full_history_recovery_v7"


def install_snapshot_full_history_recovery_v7() -> dict[str, Any]:
    from nico import snapshot_scanner_worker as worker
    from nico import scanner_worker as base

    current = worker.clone_repository_at_snapshot
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": SNAPSHOT_FULL_HISTORY_RECOVERY_V7}

    def clone_repository_with_verified_history(
        repository: str,
        commit_sha: str,
        workspace: Path,
        env: dict[str, str],
    ) -> tuple[Path | None, str, list[str]]:
        if shutil.which("git") is None:
            return None, "", ["git is unavailable in this worker image; snapshot-bound repository clone was skipped."]
        if not worker._COMMIT_SHA_RE.fullmatch(str(commit_sha or "")):
            return None, "", ["A valid full repository snapshot commit SHA is required before scanner execution."]

        repo_path = workspace / "repo"
        clone = worker._git(
            ["git", "clone", "--filter=blob:none", "--no-checkout", base.safe_repo_url(repository), str(repo_path)],
            cwd=None,
            env=env,
            timeout=240,
        )
        clone_preview, _ = base.redact((clone.stdout or "") + "\n" + (clone.stderr or ""))
        if clone.returncode != 0:
            return None, "", [f"snapshot-bound full-history git clone failed: {clone_preview[:1000]}"]

        fetch = worker._git(["git", "fetch", "--no-tags", "origin", commit_sha], cwd=repo_path, env=env, timeout=180)
        fetch_preview, _ = base.redact((fetch.stdout or "") + "\n" + (fetch.stderr or ""))
        if fetch.returncode != 0:
            shutil.rmtree(repo_path, ignore_errors=True)
            return None, "", [f"exact snapshot commit could not be fetched with history: {fetch_preview[:1000]}"]

        checkout = worker._git(["git", "checkout", "--detach", commit_sha], cwd=repo_path, env=env)
        checkout_preview, _ = base.redact((checkout.stdout or "") + "\n" + (checkout.stderr or ""))
        if checkout.returncode != 0:
            shutil.rmtree(repo_path, ignore_errors=True)
            return None, "", [f"exact snapshot commit could not be checked out: {checkout_preview[:1000]}"]

        shallow = worker._git(["git", "rev-parse", "--is-shallow-repository"], cwd=repo_path, env=env, timeout=30)
        if (shallow.stdout or "").strip().lower() == "true":
            unshallow = worker._git(["git", "fetch", "--unshallow", "--no-tags", "origin"], cwd=repo_path, env=env, timeout=300)
            if unshallow.returncode != 0:
                preview, _ = base.redact((unshallow.stdout or "") + "\n" + (unshallow.stderr or ""))
                shutil.rmtree(repo_path, ignore_errors=True)
                return None, "", [f"full-history verification required by secret scanners could not be completed: {preview[:1000]}"]

        resolved = worker._git(["git", "rev-parse", "HEAD"], cwd=repo_path, env=env, timeout=30)
        actual_sha = (resolved.stdout or "").strip().lower()
        if resolved.returncode != 0 or actual_sha != commit_sha.lower():
            shutil.rmtree(repo_path, ignore_errors=True)
            return None, actual_sha, ["Scanner checkout did not match the assessment snapshot commit; scanner execution was blocked."]

        history = worker._git(["git", "rev-parse", "--is-shallow-repository"], cwd=repo_path, env=env, timeout=30)
        if history.returncode != 0 or (history.stdout or "").strip().lower() != "false":
            shutil.rmtree(repo_path, ignore_errors=True)
            return None, actual_sha, ["Full repository history could not be verified for same-run secret scanning."]

        size = base.directory_size(repo_path)
        if size > base.MAX_REPO_BYTES:
            shutil.rmtree(repo_path, ignore_errors=True)
            return None, actual_sha, [f"repository exceeds max size limit: {size} bytes > {base.MAX_REPO_BYTES} bytes"]
        return repo_path, actual_sha, []

    setattr(clone_repository_with_verified_history, _PATCH_MARKER, True)
    setattr(clone_repository_with_verified_history, "_nico_previous", current)
    worker.clone_repository_at_snapshot = clone_repository_with_verified_history
    return {
        "status": "installed",
        "version": SNAPSHOT_FULL_HISTORY_RECOVERY_V7,
        "exact_snapshot_required": True,
        "full_history_required": True,
        "secret_scan_credit_without_history": False,
        "human_review_required": True,
    }


__all__ = ["SNAPSHOT_FULL_HISTORY_RECOVERY_V7", "install_snapshot_full_history_recovery_v7"]
