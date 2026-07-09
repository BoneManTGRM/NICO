from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

from nico.scanner_tool_runners import (
    ScannerToolSpec,
    _osv_api_fallback_tool,
    _package_lock_dependencies,
    parse_tool_findings,
    redact_payload,
    run_command,
)
from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace

DEPENDENCY_TOOL_NAMES = {"pip-audit", "npm-audit", "osv-scanner"}


def _unavailable(spec: ScannerToolSpec, reason: str, *, source: str = "hosted_dependency_scanner_patch") -> dict[str, Any]:
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
        "scans_git_history": spec.scans_git_history,
    }


def _completed(spec: ScannerToolSpec, result: WorkerCommandResult, *, cwd: Path, command: tuple[str, ...], source: str) -> dict[str, Any]:
    findings = parse_tool_findings(spec.name, result)
    if result.returncode != 0 and not findings and (result.stderr or result.stdout):
        findings = [{"message": (result.stderr or result.stdout)[:2000]}]
    status = "timeout" if result.timed_out else "completed"
    reason = "" if status == "completed" else f"{spec.name} timed out."
    return redact_payload(
        {
            "tool": spec.name,
            "status": status,
            "category": spec.category,
            "returncode": result.returncode,
            "timed_out": result.timed_out,
            "output_truncated": result.output_truncated,
            "command_intent": " ".join(command[:4]),
            "command_resolved": command[0],
            "cwd": str(cwd),
            "findings": findings,
            "findings_count": len(findings),
            "stderr": result.stderr,
            "reason": reason,
            "failure_or_unavailable_reason": reason,
            "current_run": True,
            "verified_for_this_report": not result.timed_out,
            "execution_source": source,
            "scans_git_history": spec.scans_git_history,
        }
    )


def _requirements(repo_dir: Path) -> Path | None:
    direct = repo_dir / "requirements.txt"
    if direct.exists():
        return direct
    candidates = [path for path in repo_dir.glob("**/requirements.txt") if "node_modules" not in path.parts and ".venv" not in path.parts]
    return candidates[0] if candidates else None


def _lockfile_dirs(repo_dir: Path) -> list[Path]:
    candidates = [repo_dir / "package-lock.json"]
    candidates.extend(repo_dir.glob("*/package-lock.json"))
    candidates.extend(repo_dir.glob("*/*/package-lock.json"))
    dirs: list[Path] = []
    for lockfile in candidates:
        if not lockfile.exists():
            continue
        if any(part in {"node_modules", ".next", "dist", "build"} for part in lockfile.parts):
            continue
        if (lockfile.parent / "package.json").exists() and lockfile.parent not in dirs:
            dirs.append(lockfile.parent)
    return dirs


def _pip_audit_command(repo_dir: Path) -> tuple[tuple[str, ...] | None, Path, str | None, str]:
    requirements = _requirements(repo_dir)
    if not requirements:
        return None, repo_dir, "requirements.txt not found for pip-audit dependency evidence.", "pip_audit_unavailable"
    cwd = requirements.parent
    relative = requirements.relative_to(cwd)
    if shutil.which("pip-audit"):
        return ("pip-audit", "-r", str(relative), "-f", "json"), cwd, None, "pip_audit_cli"
    return (sys.executable, "-m", "pip_audit", "-r", str(relative), "-f", "json"), cwd, None, "python_module_pip_audit"


def _npm_audit_commands(repo_dir: Path) -> tuple[list[tuple[tuple[str, ...], Path]], str | None]:
    dirs = _lockfile_dirs(repo_dir)
    if not dirs:
        return [], "package-lock.json with adjacent package.json not found for npm audit dependency evidence."
    if shutil.which("npm") is None:
        return [], "npm is not installed in the worker image."
    return [(("npm", "audit", "--json", "--package-lock-only", "--ignore-scripts"), directory) for directory in dirs], None


def _run_first_successful_npm_audit(
    spec: ScannerToolSpec,
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult],
) -> dict[str, Any]:
    commands, reason = _npm_audit_commands(workspace.repo_dir)
    if not commands:
        return _unavailable(spec, reason or "npm audit command could not be resolved.")
    results: list[dict[str, Any]] = []
    for command, cwd in commands:
        result = runner(command, cwd=cwd, limits=WorkerLimits(timeout_seconds=spec.timeout_seconds, max_output_chars=spec.max_output_chars))
        completed = _completed(spec, result, cwd=cwd, command=command, source="npm_audit_lockfile")
        results.append(completed)
        if completed.get("status") == "completed":
            completed["lockfile_count_checked"] = len(commands)
            completed["attempts"] = results
            return completed
    merged_reason = "; ".join(str(item.get("reason") or item.get("stderr") or "npm audit failed")[:400] for item in results)
    return _unavailable(spec, merged_reason or "npm audit did not complete for any lockfile.", source="npm_audit_lockfile")


def _run_pip_audit(
    spec: ScannerToolSpec,
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult],
) -> dict[str, Any]:
    command, cwd, reason, source = _pip_audit_command(workspace.repo_dir)
    if command is None:
        return _unavailable(spec, reason or "pip-audit command could not be resolved.")
    result = runner(command, cwd=cwd, limits=WorkerLimits(timeout_seconds=spec.timeout_seconds, max_output_chars=spec.max_output_chars))
    if command[0] == sys.executable and result.returncode != 0 and "No module named" in (result.stderr or result.stdout):
        return _unavailable(spec, "pip-audit binary is not installed and python -m pip_audit is unavailable in the worker image.", source=source)
    return _completed(spec, result, cwd=cwd, command=command, source=source)


def _run_osv_scanner_or_api(
    spec: ScannerToolSpec,
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult],
) -> dict[str, Any]:
    if shutil.which("osv-scanner") is None:
        payload = _osv_api_fallback_tool(spec, workspace.repo_dir)
        if isinstance(payload, dict):
            payload.setdefault("current_run", True)
            payload.setdefault("verified_for_this_report", payload.get("status") == "completed")
            payload.setdefault("findings_count", len(payload.get("findings") or []))
            payload.setdefault("failure_or_unavailable_reason", payload.get("reason") or "")
        return payload
    command = ("osv-scanner", "--format", "json", ".")
    result = runner(command, cwd=workspace.repo_dir, limits=WorkerLimits(timeout_seconds=spec.timeout_seconds, max_output_chars=spec.max_output_chars))
    return _completed(spec, result, cwd=workspace.repo_dir, command=command, source="osv_scanner_cli")


def _patch_dependency_scanner_tools() -> None:
    from nico import scanner_tool_runners

    original = getattr(scanner_tool_runners, "_nico_original_run_scanner_tool_dependency_execution", None)
    if original is None:
        original = scanner_tool_runners.run_scanner_tool
        scanner_tool_runners._nico_original_run_scanner_tool_dependency_execution = original

    def run_scanner_tool_with_dependency_execution(
        spec: ScannerToolSpec,
        workspace: WorkerWorkspace,
        *,
        runner: Callable[..., WorkerCommandResult] = run_command,
    ) -> dict[str, Any]:
        if spec.name == "pip-audit":
            return _run_pip_audit(spec, workspace, runner=runner)
        if spec.name == "npm-audit":
            return _run_first_successful_npm_audit(spec, workspace, runner=runner)
        if spec.name == "osv-scanner":
            return _run_osv_scanner_or_api(spec, workspace, runner=runner)
        return original(spec, workspace, runner=runner)

    scanner_tool_runners.run_scanner_tool = run_scanner_tool_with_dependency_execution


def _patch_artifact_dependency_summary() -> None:
    from nico import hosted_scanner_worker

    original = getattr(hosted_scanner_worker, "_nico_original_run_hosted_scanner_worker_dependency_summary", None)
    if original is None:
        original = hosted_scanner_worker.run_hosted_scanner_worker
        hosted_scanner_worker._nico_original_run_hosted_scanner_worker_dependency_summary = original

    def run_hosted_scanner_worker_with_dependency_summary(payload: dict[str, Any]) -> dict[str, Any]:
        artifact = original(payload)
        if not isinstance(artifact, dict):
            return artifact
        tools = artifact.get("tools") if isinstance(artifact.get("tools"), dict) else {}
        dependency_tools = {name: tools.get(name) for name in DEPENDENCY_TOOL_NAMES}
        completed = [name for name, item in dependency_tools.items() if isinstance(item, dict) and item.get("status") == "completed"]
        unavailable = [name for name, item in dependency_tools.items() if not isinstance(item, dict) or item.get("status") in {"unavailable", "missing", "timeout", "failed"}]
        findings_count = sum(int(item.get("findings_count") or len(item.get("findings") or [])) for item in dependency_tools.values() if isinstance(item, dict))
        artifact["dependency_scanner_execution"] = {
            "required_tools": sorted(DEPENDENCY_TOOL_NAMES),
            "completed_tools": sorted(completed),
            "unavailable_tools": sorted(unavailable),
            "findings_count": findings_count,
            "current_run": bool(artifact.get("generated_at")),
            "verified_for_this_report": len(completed) == len(DEPENDENCY_TOOL_NAMES),
            "guardrail": "Dependency scanner evidence is only clean when required tools complete and return zero findings or approved triage exists.",
        }
        return artifact

    hosted_scanner_worker.run_hosted_scanner_worker = run_hosted_scanner_worker_with_dependency_summary


def install_hosted_dependency_scanner_execution_patch() -> None:
    _patch_dependency_scanner_tools()
    _patch_artifact_dependency_summary()
