from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

import nico.scanner_tool_runners as tool_runners
from nico.full_assessment_secret_history_confidence_v1 import (
    install_full_assessment_secret_history_confidence_v1,
)
from nico.scanner_determinism_reentry_v2 import install_scanner_determinism_reentry
from nico.scanner_tool_runners import ScannerToolSpec
from nico.snapshot_scanner_heartbeat_patch import install_snapshot_scanner_heartbeat
from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace, run_command


# Patch the public installer before package initialization exposes it to other
# compatibility modules and tests. The terminal bootstrap invokes it again last.
SCANNER_DETERMINISM_REENTRY = install_scanner_determinism_reentry()
FULL_ASSESSMENT_SECRET_HISTORY_CONFIDENCE = (
    install_full_assessment_secret_history_confidence_v1()
)
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
        return True, "All ancestry reachable from the assessed commit was verified as non-shallow git history."
    if value == "true":
        return False, "The scanner workspace is shallow."
    return None, "Git returned an unrecognized history-depth value."


def _head_sha(workspace: WorkerWorkspace) -> str:
    result = _git_result(workspace, ("git", "rev-parse", "HEAD"), 30)
    value = (result.stdout or "").strip().casefold()
    if result.timed_out or result.returncode != 0:
        return ""
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        return ""
    return value


def _ensure_full_history(workspace: WorkerWorkspace) -> tuple[bool, str]:
    state, note = _history_state(workspace)
    if state is True:
        return True, note
    if state is None:
        return False, note

    head_sha = _head_sha(workspace)
    if not head_sha:
        return False, "The immutable HEAD commit could not be resolved before history expansion."
    fetch = _git_result(
        workspace,
        ("git", "fetch", "--unshallow", "--no-tags", "origin", head_sha),
        180,
    )
    if fetch.timed_out:
        return False, "Exact-commit ancestry fetch timed out; history-aware scanner evidence is unavailable."
    if fetch.returncode != 0:
        return False, "Exact-commit ancestry fetch failed; history-aware scanner evidence is unavailable."

    verified, verify_note = _history_state(workspace)
    if verified is not True:
        return False, f"Exact-commit ancestry fetch completed but depth verification failed: {verify_note}"
    observed = _head_sha(workspace)
    if observed != head_sha:
        return False, "History expansion changed the assessed HEAD identity; history-aware scanner evidence is unavailable."
    return True, "The shallow checkout was expanded only for non-shallow git history reachable from immutable assessed HEAD."


def _force_option(command: tuple[str, ...], option: str, value: str) -> tuple[str, ...]:
    parts = list(command)
    if option in parts:
        index = parts.index(option)
        if index + 1 < len(parts):
            parts[index + 1] = value
        else:
            parts.append(value)
    else:
        parts.extend((option, value))
    return tuple(parts)


def _head_scoped_spec(spec: ScannerToolSpec) -> ScannerToolSpec:
    command = tuple(spec.command)
    normalized = str(spec.name or "").casefold()
    if normalized == "gitleaks":
        command = _force_option(command, "--log-opts", "HEAD")
    elif normalized == "trufflehog":
        command = _force_option(command, "--branch", "HEAD")
    return replace(spec, command=command) if command != tuple(spec.command) else spec


def _unavailable_history_tool(spec: ScannerToolSpec, reason: str) -> dict[str, Any]:
    return {
        "tool": spec.name,
        "status": "unavailable",
        "category": spec.category,
        "reason": reason,
        "failure_or_unavailable_reason": reason,
        "findings": [],
        "findings_count": 0,
        "returncode": None,
        "timed_out": False,
        "output_truncated": False,
        "current_run": True,
        "verified_for_this_report": True,
        "execution_source": "scanner_history_truth_guard",
        "scans_git_history": True,
        "history_depth": "shallow_or_unverified",
        "full_history_verified": False,
        "history_depth_verified": False,
        "history_scope": "unavailable",
        "immutable_head_selector": "HEAD",
        "descendant_refs_scanned": False,
        "guardrail": "History-aware scanner completion credit requires verified non-shallow git history reachable from immutable assessed HEAD.",
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

    scoped_spec = _head_scoped_spec(spec)
    result = dict(_ORIGINAL_RUN_SCANNER_TOOL(scoped_spec, workspace, runner=runner))
    result["history_depth_verified"] = True
    result["history_scope"] = "reachable_ancestry_at_assessed_commit"
    result["history_verification_note"] = note
    result["history_depth"] = "full"
    result["full_history_verified"] = True
    result["immutable_head_selector"] = "HEAD"
    result["deterministic_head_selector_applied"] = True
    result["descendant_refs_scanned"] = False
    return result


def _without_heartbeat_wrapper(delegate: Callable[..., Any]) -> Callable[..., Any]:
    """Unwrap a prior heartbeat layer before rebuilding the canonical runner stack."""

    if any(
        bool(getattr(delegate, marker, False))
        for marker in (
            "_nico_snapshot_scanner_heartbeat_tool_v3",
            "_nico_snapshot_scanner_heartbeat_tool_v2",
        )
    ):
        previous = getattr(delegate, "_nico_previous", None)
        if callable(previous):
            return previous
    return delegate


def install_scanner_history_truth() -> dict[str, Any]:
    installed = bool(getattr(tool_runners, "_nico_scanner_history_truth_installed", False))
    if not installed:
        global _ORIGINAL_RUN_SCANNER_TOOL
        _ORIGINAL_RUN_SCANNER_TOOL = _without_heartbeat_wrapper(
            tool_runners.run_scanner_tool
        )
        tool_runners.run_scanner_tool = run_scanner_tool_with_history_truth
        tool_runners._nico_scanner_history_truth_installed = True
    confidence = install_full_assessment_secret_history_confidence_v1()
    heartbeat = install_snapshot_scanner_heartbeat()
    return {
        "status": "already_installed" if installed else "installed",
        "rule": "Gitleaks, TruffleHog, and future history-aware scanners require verified non-shallow git history reachable from immutable HEAD; mutable descendant branches, remotes, and tags have no scan effect.",
        "history_scope": "reachable_ancestry_at_assessed_commit",
        "immutable_head_selector": "HEAD",
        "descendant_refs_scanned": False,
        "full_assessment_secret_history_confidence": confidence,
        "snapshot_scanner_heartbeat": heartbeat,
        "heartbeat_wrapper_restored_after_history_binding": heartbeat.get(
            "source_runner_binding_installed"
        )
        is True,
    }


__all__ = [
    "FULL_ASSESSMENT_SECRET_HISTORY_CONFIDENCE",
    "SCANNER_DETERMINISM_REENTRY",
    "install_scanner_history_truth",
    "run_scanner_tool_with_history_truth",
]
