from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import nico.snapshot_scanner_worker as snapshot_worker

_ORIGINAL_CLONE: Callable[..., tuple[Path | None, str, list[str]]] = snapshot_worker.clone_repository_at_snapshot


def _is_shallow(repo_path: Path, env: dict[str, str]) -> bool | None:
    result = snapshot_worker._git(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=repo_path,
        env=env,
        timeout=30,
    )
    if result.returncode != 0:
        return None
    value = (result.stdout or "").strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def clone_repository_with_full_history(
    repository: str,
    commit_sha: str,
    workspace: Path,
    env: dict[str, str],
) -> tuple[Path | None, str, list[str]]:
    """Keep the exact detached snapshot while repairing an accidental shallow checkout.

    Current-tree scanning may continue when full history cannot be obtained. The
    history scanner independently verifies depth before any clean-history claim, so
    an inconclusive depth probe here does not alter the legacy checkout contract.
    """

    repo_path, actual_sha, notes = _ORIGINAL_CLONE(repository, commit_sha, workspace, env)
    notes = list(notes)
    if repo_path is None:
        return None, actual_sha, notes

    shallow = _is_shallow(repo_path, env)
    if shallow is False or shallow is None:
        return repo_path, actual_sha, notes

    unshallow = snapshot_worker._git(
        ["git", "fetch", "--unshallow", "--no-tags", "origin"],
        cwd=repo_path,
        env=env,
        timeout=180,
    )
    if unshallow.returncode != 0:
        preview, _ = snapshot_worker.base.redact((unshallow.stdout or "") + "\n" + (unshallow.stderr or ""))
        notes.append(f"Exact snapshot remained shallow because full history fetch failed: {preview[:800]}")
        return repo_path, actual_sha, notes

    resolved = snapshot_worker._git(["git", "rev-parse", "HEAD"], cwd=repo_path, env=env, timeout=30)
    resolved_sha = (resolved.stdout or "").strip().lower()
    if resolved.returncode != 0 or resolved_sha != str(commit_sha or "").lower():
        notes.append("Full-history fetch changed or obscured the detached snapshot identity; history evidence remains unavailable.")
        return repo_path, actual_sha, notes
    if _is_shallow(repo_path, env) is not False:
        notes.append("Git reported the repository as shallow after the full-history fetch; history evidence remains unavailable.")
        return repo_path, actual_sha, notes

    notes.append("Exact snapshot checkout retained the requested commit and verified full git history for history-aware scanners.")
    return repo_path, actual_sha, notes


def install_exact_snapshot_full_history_checkout() -> dict[str, Any]:
    installed = bool(getattr(snapshot_worker, "_nico_full_history_checkout_installed", False))
    snapshot_worker.clone_repository_at_snapshot = clone_repository_with_full_history
    snapshot_worker._nico_full_history_checkout_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "rule": "The detached snapshot commit must remain exact while a shallow checkout is unshallowed; history scanners independently verify full depth before supporting a clean claim.",
    }


__all__ = ["clone_repository_with_full_history", "install_exact_snapshot_full_history_checkout"]
