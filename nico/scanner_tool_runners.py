from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from nico.scanner_worker_artifacts import normalize_scanner_worker_artifact
from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace, run_command

SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", re.DOTALL),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)(\s*[:=]\s*)['\"]?[A-Za-z0-9_./+=:-]{16,}"),
)


@dataclass(frozen=True)
class ScannerToolSpec:
    name: str
    command: tuple[str, ...]
    category: str
    timeout_seconds: int = 120
    max_output_chars: int = 80_000
    requires_project_commands: bool = False
    scans_git_history: bool = False


TOOL_SPECS: tuple[ScannerToolSpec, ...] = (
    ScannerToolSpec("pip-audit", ("pip-audit", "-r", "requirements.txt", "-f", "json"), "dependency", timeout_seconds=180),
    ScannerToolSpec("npm-audit", ("npm", "audit", "--json", "--package-lock-only", "--ignore-scripts"), "dependency", timeout_seconds=180),
    ScannerToolSpec("osv-scanner", ("osv-scanner", "--format", "json", "."), "dependency", timeout_seconds=180),
    ScannerToolSpec("bandit", ("bandit", "-r", ".", "-f", "json"), "static", timeout_seconds=180),
    ScannerToolSpec("semgrep", ("semgrep", "scan", "--config", "auto", "--json", "."), "static", timeout_seconds=240),
    ScannerToolSpec("eslint", ("npx", "eslint", ".", "--format", "json"), "static", timeout_seconds=180, requires_project_commands=True),
    ScannerToolSpec("typescript", ("npx", "tsc", "--noEmit", "--pretty", "false"), "static", timeout_seconds=180, requires_project_commands=True),
    ScannerToolSpec("gitleaks", ("gitleaks", "detect", "--no-banner", "--redact", "--report-format", "json", "--source", "."), "secret", timeout_seconds=240, scans_git_history=True),
    ScannerToolSpec("trufflehog", ("trufflehog", "git", "file://{repo_dir}", "--json", "--no-update", "--no-verification"), "secret", timeout_seconds=300, scans_git_history=True),
    ScannerToolSpec("coverage", ("coverage", "run", "-m", "pytest", "-q"), "coverage", timeout_seconds=240, requires_project_commands=True),
)


def project_commands_allowed() -> bool:
    return os.getenv("NICO_ALLOW_PROJECT_COMMANDS", "false").lower() == "true"


def redact_text(value: str) -> str:
    redacted = value or ""
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: _redact_match(match), redacted)
    return redacted


def _redact_match(match: re.Match[str]) -> str:
    if match.lastindex and match.lastindex >= 2:
        return f"{match.group(1)}{match.group(2)}[REDACTED]"
    return "[REDACTED]"


def redact_payload(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact_payload(item) for key, item in value.items()}
    return value


def _parse_json_lines(text: str) -> list[Any]:
    items: list[Any] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            items.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return items


def _npm_audit_findings(payload: dict[str, Any]) -> list[Any]:
    vulnerabilities = payload.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return []
    findings: list[Any] = []
    for package_name, item in vulnerabilities.items():
        if isinstance(item, dict):
            finding = dict(item)
            finding.setdefault("package", package_name)
            findings.append(finding)
    return findings


def _pip_audit_findings(payload: dict[str, Any]) -> list[Any]:
    findings: list[Any] = []
    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, list):
        return findings
    for dep in dependencies:
        if not isinstance(dep, dict):
            continue
        for vuln in dep.get("vulns") or []:
            if isinstance(vuln, dict):
                finding = dict(vuln)
                finding.setdefault("package", dep.get("name"))
                finding.setdefault("installed_version", dep.get("version"))
                findings.append(finding)
    return findings


def _osv_findings(payload: dict[str, Any]) -> list[Any]:
    findings: list[Any] = []
    for key in ("results", "packages"):
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            vulns = item.get("vulnerabilities") or item.get("vulns") or []
            for vuln in vulns:
                if isinstance(vuln, dict):
                    findings.append(vuln)
    return findings


def parse_tool_findings(tool_name: str, result: WorkerCommandResult) -> list[Any]:
    text = redact_text(result.stdout or "")
    if not text.strip():
        return []

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        if tool_name == "trufflehog":
            return _parse_json_lines(text)
        if tool_name in {"typescript", "coverage"} and result.returncode != 0:
            return [{"message": redact_text(result.stderr or result.stdout)}]
        return []

    if tool_name == "pip-audit" and isinstance(payload, dict):
        return _pip_audit_findings(payload)
    if tool_name == "npm-audit" and isinstance(payload, dict):
        return _npm_audit_findings(payload)
    if tool_name == "osv-scanner" and isinstance(payload, dict):
        return _osv_findings(payload)
    if tool_name == "bandit" and isinstance(payload, dict):
        return payload.get("results") or []
    if tool_name == "semgrep" and isinstance(payload, dict):
        return payload.get("results") or []
    if tool_name == "eslint" and isinstance(payload, list):
        findings: list[Any] = []
        for file_result in payload:
            if isinstance(file_result, dict):
                for message in file_result.get("messages") or []:
                    if isinstance(message, dict):
                        item = dict(message)
                        item.setdefault("filePath", file_result.get("filePath"))
                        findings.append(item)
        return findings
    if tool_name in {"typescript", "coverage"}:
        return [] if result.returncode == 0 else [{"message": redact_text(result.stderr or result.stdout)}]
    if tool_name == "gitleaks" and isinstance(payload, list):
        return payload
    if tool_name == "trufflehog" and isinstance(payload, dict):
        return [payload]
    return []


def _unavailable_tool(spec: ScannerToolSpec, reason: str) -> dict[str, Any]:
    return {
        "tool": spec.name,
        "status": "unavailable",
        "category": spec.category,
        "reason": reason,
        "findings": [],
        "scans_git_history": spec.scans_git_history,
    }


def _resolve_command_and_cwd(spec: ScannerToolSpec, workspace: WorkerWorkspace) -> tuple[tuple[str, ...] | None, Path, str | None]:
    repo_dir = workspace.repo_dir
    if spec.name == "pip-audit" and not (repo_dir / "requirements.txt").exists():
        return None, repo_dir, "requirements.txt not found for pip-audit."
    if spec.name == "npm-audit":
        lockfiles = [repo_dir / "package-lock.json"]
        lockfiles.extend(repo_dir.glob("*/package-lock.json"))
        lockfiles.extend(repo_dir.glob("*/*/package-lock.json"))
        existing = [path for path in lockfiles if path.exists()]
        if not existing:
            return None, repo_dir, "package-lock.json not found for npm audit."
        return spec.command, existing[0].parent, None
    if spec.name == "trufflehog":
        return tuple(part.replace("{repo_dir}", str(repo_dir)) for part in spec.command), repo_dir, None
    return spec.command, repo_dir, None


def run_scanner_tool(
    spec: ScannerToolSpec,
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult] = run_command,
) -> dict[str, Any]:
    if spec.requires_project_commands and not project_commands_allowed():
        return _unavailable_tool(
            spec,
            f"{spec.name} requires NICO_ALLOW_PROJECT_COMMANDS=true because it may execute project-local commands.",
        )

    executable = spec.command[0]
    if shutil.which(executable) is None:
        return _unavailable_tool(spec, f"{executable} is not installed in the worker image")

    command, cwd, unavailable_reason = _resolve_command_and_cwd(spec, workspace)
    if command is None:
        return _unavailable_tool(spec, unavailable_reason or f"{spec.name} could not resolve a safe command")

    result = runner(
        command,
        cwd=cwd,
        limits=WorkerLimits(timeout_seconds=spec.timeout_seconds, max_output_chars=spec.max_output_chars),
    )
    status = "completed" if not result.timed_out else "timeout"
    findings = parse_tool_findings(spec.name, result)
    return redact_payload(
        {
            "tool": spec.name,
            "status": status,
            "category": spec.category,
            "returncode": result.returncode,
            "timed_out": result.timed_out,
            "output_truncated": result.output_truncated,
            "findings": findings,
            "stderr": result.stderr,
            "scans_git_history": spec.scans_git_history,
        }
    )


def run_scanner_tools(
    workspace: WorkerWorkspace,
    specs: tuple[ScannerToolSpec, ...] = TOOL_SPECS,
    *,
    runner: Callable[..., WorkerCommandResult] = run_command,
) -> dict[str, Any]:
    if not workspace.repo_dir.exists() or not workspace.repo_dir.is_dir():
        raise ValueError("workspace repo directory must exist before scanner tools run")

    tool_results = [run_scanner_tool(spec, workspace, runner=runner) for spec in specs]
    raw_payload = {"tools": tool_results}
    normalized = normalize_scanner_worker_artifact(raw_payload)
    history_secret_tools = [
        item["tool"]
        for item in tool_results
        if isinstance(item, dict) and item.get("category") == "secret" and item.get("status") == "completed" and item.get("scans_git_history")
    ]
    return {
        "artifact_schema": "nico.scanner_worker.v1",
        "tools": {item["tool"]: item for item in tool_results if isinstance(item, dict) and item.get("tool")},
        "normalized": normalized,
        "secret_history_scan": {
            "completed_tools": history_secret_tools,
            "history_aware": bool(history_secret_tools),
        },
    }


def write_scanner_artifact(payload: dict[str, Any], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(redact_payload(payload), indent=2, sort_keys=True), encoding="utf-8")
    return destination
