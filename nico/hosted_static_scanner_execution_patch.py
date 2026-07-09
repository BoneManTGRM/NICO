from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

from nico.scanner_tool_runners import ScannerToolSpec, parse_tool_findings, redact_payload, redact_text, run_command
from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace

STATIC_TOOL_NAMES = {"bandit", "semgrep", "eslint", "typescript"}
IGNORED_DIRS = {".git", "node_modules", ".next", "dist", "build", ".venv", "venv", "__pycache__"}


def _project_commands_allowed() -> bool:
    return os.getenv("NICO_ALLOW_PROJECT_COMMANDS", "false").lower() == "true"


def _safe_files(repo_dir: Path, suffixes: tuple[str, ...], *, limit: int = 5000) -> list[Path]:
    files: list[Path] = []
    for path in repo_dir.rglob("*"):
        if len(files) >= limit:
            break
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(repo_dir)
        except ValueError:
            continue
        if any(part in IGNORED_DIRS for part in relative.parts):
            continue
        if path.suffix in suffixes:
            files.append(path)
    return files


def _web_dir(repo_dir: Path) -> Path:
    return repo_dir / "apps" / "web"


def _read_package_json(directory: Path) -> dict[str, Any]:
    try:
        import json

        payload = json.loads((directory / "package.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _script(directory: Path, name: str) -> str | None:
    scripts = _read_package_json(directory).get("scripts")
    if isinstance(scripts, dict) and scripts.get(name):
        return str(scripts[name])
    return None


def _local_bin(directory: Path, binary: str) -> Path | None:
    candidate = directory / "node_modules" / ".bin" / binary
    return candidate if candidate.exists() else None


def _unavailable(spec: ScannerToolSpec, reason: str, *, source: str = "hosted_static_scanner_patch") -> dict[str, Any]:
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


def _completed_without_command(spec: ScannerToolSpec, reason: str, *, source: str) -> dict[str, Any]:
    return {
        "tool": spec.name,
        "status": "completed",
        "category": spec.category,
        "returncode": 0,
        "timed_out": False,
        "output_truncated": False,
        "command_intent": "no matching files",
        "findings": [],
        "findings_count": 0,
        "stderr": "",
        "reason": reason,
        "failure_or_unavailable_reason": "",
        "current_run": True,
        "verified_for_this_report": True,
        "execution_source": source,
        "scans_git_history": spec.scans_git_history,
    }


def _completed(spec: ScannerToolSpec, result: WorkerCommandResult, *, cwd: Path, command: tuple[str, ...], source: str) -> dict[str, Any]:
    findings = parse_tool_findings(spec.name, result)
    status = "timeout" if result.timed_out else "completed"
    reason = ""
    if result.timed_out:
        reason = f"{spec.name} timed out."
    elif result.returncode not in {0, 1} and not findings:
        status = "failed"
        reason = redact_text(result.stderr or result.stdout or f"{spec.name} returned {result.returncode} without parseable findings.")[:1500]
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
            "verified_for_this_report": status == "completed",
            "execution_source": source,
            "scans_git_history": spec.scans_git_history,
            "guardrail": "Static scanner output is verified only when the scanner completes against the current authorized checkout.",
        }
    )


def _bandit_command(workspace: WorkerWorkspace) -> tuple[tuple[str, ...] | None, Path, str | None, str]:
    if not _safe_files(workspace.repo_dir, (".py",)):
        return None, workspace.repo_dir, "No Python files were present for Bandit static analysis.", "bandit_no_python_files"
    if shutil.which("bandit"):
        return ("bandit", "-r", ".", "-f", "json", "-x", "./node_modules,./.venv,./venv,./.git"), workspace.repo_dir, None, "bandit_cli"
    return (sys.executable, "-m", "bandit", "-r", ".", "-f", "json", "-x", "./node_modules,./.venv,./venv,./.git"), workspace.repo_dir, None, "python_module_bandit"


def _semgrep_command(workspace: WorkerWorkspace) -> tuple[tuple[str, ...] | None, Path, str | None, str]:
    if not _safe_files(workspace.repo_dir, (".py", ".ts", ".tsx", ".js", ".jsx")):
        return None, workspace.repo_dir, "No supported source files were present for Semgrep static analysis.", "semgrep_no_source_files"
    if shutil.which("semgrep") is None:
        return None, workspace.repo_dir, "semgrep is not installed in the worker image.", "semgrep_cli"
    return (
        "semgrep",
        "scan",
        "--config",
        "auto",
        "--json",
        "--exclude",
        "node_modules",
        "--exclude",
        ".next",
        "--exclude",
        "dist",
        "--exclude",
        "build",
        ".",
    ), workspace.repo_dir, None, "semgrep_cli"


def _eslint_command(workspace: WorkerWorkspace) -> tuple[tuple[str, ...] | None, Path, str | None, str]:
    directory = _web_dir(workspace.repo_dir)
    if not (directory / "package.json").exists():
        return None, workspace.repo_dir, "apps/web/package.json not found for ESLint evidence.", "eslint_unavailable"
    if not _project_commands_allowed():
        return None, directory, "eslint requires NICO_ALLOW_PROJECT_COMMANDS=true because it may execute project-local JavaScript tooling.", "eslint_project_commands_disabled"
    if _script(directory, "lint"):
        return ("npm", "run", "lint", "--", "--format", "json"), directory, None, "eslint_npm_script"
    local = _local_bin(directory, "eslint")
    if local:
        return (str(local), ".", "--format", "json"), directory, None, "eslint_local_binary"
    if shutil.which("eslint"):
        return ("eslint", ".", "--format", "json"), directory, None, "eslint_global_binary"
    return None, directory, "ESLint is not installed globally and no local node_modules/.bin/eslint exists in the checkout.", "eslint_unavailable"


def _typescript_command(workspace: WorkerWorkspace) -> tuple[tuple[str, ...] | None, Path, str | None, str]:
    directory = _web_dir(workspace.repo_dir)
    if not (directory / "package.json").exists():
        return None, workspace.repo_dir, "apps/web/package.json not found for TypeScript evidence.", "typescript_unavailable"
    if not (directory / "tsconfig.json").exists():
        return None, directory, "apps/web/tsconfig.json not found for TypeScript evidence.", "typescript_unavailable"
    if not _project_commands_allowed():
        return None, directory, "typescript requires NICO_ALLOW_PROJECT_COMMANDS=true because it may execute project-local TypeScript tooling.", "typescript_project_commands_disabled"
    for script_name in ("typecheck", "type-check", "check-types"):
        if _script(directory, script_name):
            return ("npm", "run", script_name), directory, None, "typescript_npm_script"
    local = _local_bin(directory, "tsc")
    if local:
        return (str(local), "--noEmit", "--pretty", "false"), directory, None, "typescript_local_binary"
    if shutil.which("tsc"):
        return ("tsc", "--noEmit", "--pretty", "false"), directory, None, "typescript_global_binary"
    return None, directory, "TypeScript compiler is not installed globally and no local node_modules/.bin/tsc exists in the checkout.", "typescript_unavailable"


def _run_static_tool(
    spec: ScannerToolSpec,
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult],
) -> dict[str, Any]:
    if spec.name == "bandit":
        command, cwd, reason, source = _bandit_command(workspace)
        if command is None and source == "bandit_no_python_files":
            return _completed_without_command(spec, reason or "No Python files to scan.", source=source)
    elif spec.name == "semgrep":
        command, cwd, reason, source = _semgrep_command(workspace)
        if command is None and source == "semgrep_no_source_files":
            return _completed_without_command(spec, reason or "No supported source files to scan.", source=source)
    elif spec.name == "eslint":
        command, cwd, reason, source = _eslint_command(workspace)
    elif spec.name == "typescript":
        command, cwd, reason, source = _typescript_command(workspace)
    else:
        return _unavailable(spec, f"Unsupported static scanner: {spec.name}")
    if command is None:
        return _unavailable(spec, reason or f"{spec.name} command could not be resolved.", source=source)
    result = runner(command, cwd=cwd, limits=WorkerLimits(timeout_seconds=spec.timeout_seconds, max_output_chars=spec.max_output_chars))
    if spec.name == "bandit" and command[0] == sys.executable and result.returncode != 0 and "No module named" in (result.stderr or result.stdout):
        return _unavailable(spec, "bandit binary is not installed and python -m bandit is unavailable in the worker image.", source=source)
    return _completed(spec, result, cwd=cwd, command=command, source=source)


def _patch_static_scanner_tools() -> None:
    from nico import scanner_tool_runners

    original = getattr(scanner_tool_runners, "_nico_original_run_scanner_tool_static_execution", None)
    if original is None:
        original = scanner_tool_runners.run_scanner_tool
        scanner_tool_runners._nico_original_run_scanner_tool_static_execution = original

    def run_scanner_tool_with_static_execution(
        spec: ScannerToolSpec,
        workspace: WorkerWorkspace,
        *,
        runner: Callable[..., WorkerCommandResult] = run_command,
    ) -> dict[str, Any]:
        if spec.name in STATIC_TOOL_NAMES:
            return _run_static_tool(spec, workspace, runner=runner)
        return original(spec, workspace, runner=runner)

    scanner_tool_runners.run_scanner_tool = run_scanner_tool_with_static_execution


def _patch_artifact_static_summary() -> None:
    from nico import hosted_scanner_worker

    original = getattr(hosted_scanner_worker, "_nico_original_run_hosted_scanner_worker_static_summary", None)
    if original is None:
        original = hosted_scanner_worker.run_hosted_scanner_worker
        hosted_scanner_worker._nico_original_run_hosted_scanner_worker_static_summary = original

    def run_hosted_scanner_worker_with_static_summary(payload: dict[str, Any]) -> dict[str, Any]:
        artifact = original(payload)
        if not isinstance(artifact, dict):
            return artifact
        tools = artifact.get("tools") if isinstance(artifact.get("tools"), dict) else {}
        static_tools = {name: tools.get(name) for name in STATIC_TOOL_NAMES}
        completed = [name for name, item in static_tools.items() if isinstance(item, dict) and item.get("status") == "completed"]
        unavailable = [name for name, item in static_tools.items() if not isinstance(item, dict) or item.get("status") in {"unavailable", "missing", "timeout", "failed"}]
        findings_count = sum(int(item.get("findings_count") or len(item.get("findings") or [])) for item in static_tools.values() if isinstance(item, dict))
        artifact["static_scanner_execution"] = {
            "required_tools": sorted(STATIC_TOOL_NAMES),
            "completed_tools": sorted(completed),
            "unavailable_tools": sorted(unavailable),
            "findings_count": findings_count,
            "current_run": bool(artifact.get("generated_at")),
            "verified_for_this_report": len(completed) == len(STATIC_TOOL_NAMES),
            "project_commands_allowed": _project_commands_allowed(),
            "guardrail": "Static evidence is only clean when required static scanners complete and return zero blocking findings or approved triage exists.",
        }
        return artifact

    hosted_scanner_worker.run_hosted_scanner_worker = run_hosted_scanner_worker_with_static_summary


def install_hosted_static_scanner_execution_patch() -> None:
    _patch_static_scanner_tools()
    _patch_artifact_static_summary()
