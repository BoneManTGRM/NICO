from __future__ import annotations

from typing import Any, Callable

import nico.scanner_tool_runners as tool_runners
from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace, run_command


_ORIGINAL_RUN_SCANNER_TOOL: Callable[..., dict[str, Any]] = tool_runners.run_scanner_tool


def _git_result(workspace: WorkerWorkspace, args: tuple[str, ...], timeout: int) -> WorkerCommandResult:
    return run_command(
        args,
        cwd=workspace.repo_dir,
        limits=WorkerLimits(timeout_seconds=timeout, max_output_chars=12_000),
    )


def _history_state(workspace: WorkerWorkspace) -> tuple[bool | None, str]:
    probe = _git_result(workspace, ("git", "rev-parse", "--is-shallow-repository"), 30)
    if probe.timed_out or probe.returncode != 0:
        return None, "Git history depth could not be verified for the scanner workspace."
    value = (probe.stdout or "").strip().lower()
    if value == "false":
        return True, "Full git history was verified."
    if value == "true":
        return False, "The scanner workspace is shallow."
    return None, "Git returned an unrecognized history-depth value."


def _ensure_full_history(workspace: WorkerWorkspace) -> tuple[bool, str]:
    state, note = _history_state(workspace)
    if state is True:
        return True, note
    if state is None:
        return False, note

    fetch = _git_result(workspace, ("git", "fetch", "--unshallow", "--no-tags", "origin"), 180)
    if fetch.timed_out:
        return False, "Full-history fetch timed out; history-aware scanner evidence is unavailable."
    if fetch.returncode != 0:
        return False, "Full-history fetch failed; history-aware scanner evidence is unavailable."

    verified, verify_note = _history_state(workspace)
    if verified is not True:
        return False, f"Full-history fetch completed but depth verification failed: {verify_note}"
    return True, "The shallow checkout was expanded and full git history was verified before history-aware scanning."


def _unavailable_history_tool(spec: ScannerToolSpec, reason: str) -> dict[str, Any]:
    return {
        "tool": spec.name,
        "status": "unavailable",
        "category": spec.category,
        "reason": reason,
        "findings": [],
        "returncode": None,
        "timed_out": False,
        "output_truncated": False,
        "scans_git_history": True,
        "history_depth_verified": False,
        "history_scope": "unavailable",
    }


def run_scanner_tool_with_history_truth(
    spec: ScannerToolSpec,
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult] = tool_runners.run_command,
) -> dict[str, Any]:
    if not spec.scans_git_history:
        return _ORIGINAL_RUN_SCANNER_TOOL(spec, workspace, runner=runner)

    verified, note = _ensure_full_history(workspace)
    if not verified:
        return _unavailable_history_tool(spec, note)

    result = dict(_ORIGINAL_RUN_SCANNER_TOOL(spec, workspace, runner=runner))
    result["history_depth_verified"] = True
    result["history_scope"] = "full_git_history"
    result["history_verification_note"] = note
    return result


def install_scanner_history_truth() -> dict[str, Any]:
    installed = bool(getattr(tool_runners, "_nico_scanner_history_truth_installed", False))
    tool_runners.run_scanner_tool = run_scanner_tool_with_history_truth
    tool_runners._nico_scanner_history_truth_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "rule": "Gitleaks, TruffleHog, and any future history-aware scanner may run only after NICO verifies a non-shallow git history; otherwise the tool remains explicitly unavailable.",
    }


__all__ = [
    "install_scanner_history_truth",
    "run_scanner_tool_with_history_truth",
]
