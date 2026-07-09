from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

from nico.scanner_tool_runners import ScannerToolSpec, parse_tool_findings, redact_payload, redact_text, run_command
from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace

SECRET_TOOL_NAMES = {"gitleaks", "trufflehog"}


def _git_result(workspace: WorkerWorkspace, *args: str) -> WorkerCommandResult:
    return run_command(("git", *args), cwd=workspace.repo_dir, limits=WorkerLimits(timeout_seconds=30, max_output_chars=2_000))


def _history_metadata(workspace: WorkerWorkspace) -> dict[str, Any]:
    if not workspace.repo_dir.exists():
        return {
            "history_depth": "missing_checkout",
            "full_history_verified": False,
            "commit_count": None,
            "head_sha": None,
            "reason": "Repository checkout directory does not exist.",
        }
    shallow_result = _git_result(workspace, "rev-parse", "--is-shallow-repository")
    count_result = _git_result(workspace, "rev-list", "--count", "HEAD")
    head_result = _git_result(workspace, "rev-parse", "HEAD")
    shallow_text = (shallow_result.stdout or shallow_result.stderr or "").strip().lower()
    is_shallow = shallow_text == "true"
    full_verified = shallow_result.ok and shallow_text == "false"
    commit_count: int | None = None
    try:
        commit_count = int((count_result.stdout or "").strip()) if count_result.ok else None
    except ValueError:
        commit_count = None
    reason = ""
    if not shallow_result.ok:
        reason = "Could not verify whether checkout is shallow."
    elif is_shallow:
        reason = "Checkout is shallow, so full-history secret scanner proof is not verified."
    return {
        "history_depth": "full" if full_verified else "shallow_or_unverified",
        "full_history_verified": full_verified,
        "commit_count": commit_count,
        "head_sha": (head_result.stdout or "").strip() if head_result.ok else None,
        "reason": reason,
    }


def _unavailable(spec: ScannerToolSpec, reason: str, *, history: dict[str, Any] | None = None, source: str = "hosted_secret_scanner_patch") -> dict[str, Any]:
    history = history or {}
    return {
        "tool": spec.name,
        "status": "unavailable",
        "category": spec.category,
        "reason": reason,
        "failure_or_unavailable_reason": reason,
        "findings": [],
        "findings_count": 0,
        "current_run": True,
        "verified_for_this_report": False,
        "execution_source": source,
        "scans_git_history": True,
        "history_depth": history.get("history_depth") or "unknown",
        "full_history_verified": bool(history.get("full_history_verified")),
        "commit_count": history.get("commit_count"),
        "head_sha": history.get("head_sha"),
    }


def _completed(
    spec: ScannerToolSpec,
    result: WorkerCommandResult,
    *,
    cwd: Path,
    command: tuple[str, ...],
    history: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    findings = parse_tool_findings(spec.name, result)
    status = "timeout" if result.timed_out else "completed"
    reason = ""
    if result.timed_out:
        reason = f"{spec.name} timed out."
    elif history.get("reason"):
        reason = str(history.get("reason") or "")
    elif result.returncode not in {0, 1} and not findings:
        status = "failed"
        reason = redact_text(result.stderr or result.stdout or f"{spec.name} returned {result.returncode} without parseable findings.")[:1500]
    verified = status == "completed" and bool(history.get("full_history_verified"))
    return redact_payload(
        {
            "tool": spec.name,
            "status": status,
            "category": spec.category,
            "returncode": result.returncode,
            "timed_out": result.timed_out,
            "output_truncated": result.output_truncated,
            "command_intent": " ".join(command[:5]),
            "command_resolved": command[0],
            "cwd": str(cwd),
            "findings": findings,
            "findings_count": len(findings),
            "stderr": result.stderr,
            "reason": reason,
            "failure_or_unavailable_reason": reason,
            "current_run": True,
            "verified_for_this_report": verified,
            "execution_source": source,
            "scans_git_history": True,
            "history_depth": history.get("history_depth"),
            "full_history_verified": bool(history.get("full_history_verified")),
            "commit_count": history.get("commit_count"),
            "head_sha": history.get("head_sha"),
            "guardrail": "Secret scanner output is verified only when the scanner completes against a verified full-history checkout.",
        }
    )


def _gitleaks_command(workspace: WorkerWorkspace) -> tuple[tuple[str, ...] | None, Path, str | None]:
    if shutil.which("gitleaks") is None:
        return None, workspace.repo_dir, "gitleaks is not installed in the worker image."
    return (
        "gitleaks",
        "detect",
        "--no-banner",
        "--redact",
        "--report-format",
        "json",
        "--source",
        ".",
    ), workspace.repo_dir, None


def _trufflehog_command(workspace: WorkerWorkspace) -> tuple[tuple[str, ...] | None, Path, str | None]:
    if shutil.which("trufflehog") is None:
        return None, workspace.repo_dir, "trufflehog is not installed in the worker image."
    return (
        "trufflehog",
        "git",
        f"file://{workspace.repo_dir}",
        "--json",
        "--no-update",
        "--no-verification",
    ), workspace.repo_dir, None


def _run_secret_tool(
    spec: ScannerToolSpec,
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult],
) -> dict[str, Any]:
    history = _history_metadata(workspace)
    if spec.name == "gitleaks":
        command, cwd, reason = _gitleaks_command(workspace)
        source = "gitleaks_full_history"
    elif spec.name == "trufflehog":
        command, cwd, reason = _trufflehog_command(workspace)
        source = "trufflehog_full_history"
    else:
        return _unavailable(spec, f"Unsupported secret scanner: {spec.name}", history=history)
    if command is None:
        return _unavailable(spec, reason or f"{spec.name} command could not be resolved.", history=history, source=source)
    result = runner(command, cwd=cwd, limits=WorkerLimits(timeout_seconds=spec.timeout_seconds, max_output_chars=spec.max_output_chars))
    return _completed(spec, result, cwd=cwd, command=command, history=history, source=source)


def _patch_secret_scanner_tools() -> None:
    from nico import scanner_tool_runners

    original = getattr(scanner_tool_runners, "_nico_original_run_scanner_tool_secret_execution", None)
    if original is None:
        original = scanner_tool_runners.run_scanner_tool
        scanner_tool_runners._nico_original_run_scanner_tool_secret_execution = original

    def run_scanner_tool_with_secret_execution(
        spec: ScannerToolSpec,
        workspace: WorkerWorkspace,
        *,
        runner: Callable[..., WorkerCommandResult] = run_command,
    ) -> dict[str, Any]:
        if spec.name in SECRET_TOOL_NAMES:
            return _run_secret_tool(spec, workspace, runner=runner)
        return original(spec, workspace, runner=runner)

    scanner_tool_runners.run_scanner_tool = run_scanner_tool_with_secret_execution


def _patch_artifact_secret_summary() -> None:
    from nico import hosted_scanner_worker

    original = getattr(hosted_scanner_worker, "_nico_original_run_hosted_scanner_worker_secret_summary", None)
    if original is None:
        original = hosted_scanner_worker.run_hosted_scanner_worker
        hosted_scanner_worker._nico_original_run_hosted_scanner_worker_secret_summary = original

    def run_hosted_scanner_worker_with_secret_summary(payload: dict[str, Any]) -> dict[str, Any]:
        artifact = original(payload)
        if not isinstance(artifact, dict):
            return artifact
        tools = artifact.get("tools") if isinstance(artifact.get("tools"), dict) else {}
        secret_tools = {name: tools.get(name) for name in SECRET_TOOL_NAMES}
        completed = [name for name, item in secret_tools.items() if isinstance(item, dict) and item.get("status") == "completed"]
        unavailable = [name for name, item in secret_tools.items() if not isinstance(item, dict) or item.get("status") in {"unavailable", "missing", "timeout", "failed"}]
        findings_count = sum(int(item.get("findings_count") or len(item.get("findings") or [])) for item in secret_tools.values() if isinstance(item, dict))
        full_history_verified = bool(completed) and all(bool(item.get("full_history_verified")) for item in secret_tools.values() if isinstance(item, dict) and item.get("status") == "completed")
        artifact["secret_scanner_execution"] = {
            "required_tools": sorted(SECRET_TOOL_NAMES),
            "completed_tools": sorted(completed),
            "unavailable_tools": sorted(unavailable),
            "findings_count": findings_count,
            "current_run": bool(artifact.get("generated_at")),
            "full_history_verified": full_history_verified,
            "verified_for_this_report": len(completed) == len(SECRET_TOOL_NAMES) and full_history_verified,
            "guardrail": "Secrets evidence is only clean when full-history secret scanners complete and return zero high-confidence findings or approved triage exists.",
        }
        artifact["secret_history_scan"] = {
            "completed_tools": sorted(completed),
            "history_aware": full_history_verified,
            "full_history_verified": full_history_verified,
        }
        return artifact

    hosted_scanner_worker.run_hosted_scanner_worker = run_hosted_scanner_worker_with_secret_summary


def install_hosted_secret_scanner_execution_patch() -> None:
    _patch_secret_scanner_tools()
    _patch_artifact_secret_summary()
