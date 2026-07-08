from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests

from nico.scanner_worker_artifacts import normalize_scanner_worker_artifact
from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace, run_command

OSV_API = "https://api.osv.dev/v1/querybatch"

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


ESLINT_CONFIG_NAMES = (
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.cjs",
    ".eslintrc",
    ".eslintrc.json",
    ".eslintrc.js",
    ".eslintrc.cjs",
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
        return [] if result.returncode == 0 else [{"message": redact_text(result.stderr or "tool failed without stdout")}]

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        if tool_name == "trufflehog":
            return _parse_json_lines(text)
        if tool_name in {"eslint", "typescript", "coverage"} and result.returncode != 0:
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


def _normalize_requirement(raw: str) -> dict[str, str] | None:
    line = raw.split("#", 1)[0].strip()
    if not line or line.startswith("-"):
        return None
    match = re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*(==|~=|>=|<=|>|<)\s*([^;\s]+)", line)
    if not match:
        return None
    name, operator, version = match.groups()
    if operator != "==":
        return None
    return {"name": name, "version": version, "ecosystem": "PyPI", "source": "requirements.txt"}


def _package_lock_dependencies(path: Path) -> list[dict[str, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    dependencies: list[dict[str, str]] = []
    packages = payload.get("packages")
    if isinstance(packages, dict):
        for raw_name, item in packages.items():
            if not raw_name or raw_name == "" or not isinstance(item, dict):
                continue
            version = str(item.get("version") or "").strip()
            if not version:
                continue
            name = raw_name.split("node_modules/", 1)[-1]
            if name:
                dependencies.append({"name": name, "version": version, "ecosystem": "npm", "source": str(path)})
    return dependencies


def _osv_query_dependencies(repo_dir: Path) -> list[dict[str, str]]:
    dependencies: list[dict[str, str]] = []
    requirements = repo_dir / "requirements.txt"
    if requirements.exists():
        for line in requirements.read_text(encoding="utf-8", errors="replace").splitlines():
            item = _normalize_requirement(line)
            if item:
                dependencies.append(item)
    for lockfile in repo_dir.glob("**/package-lock.json"):
        if any(part in {"node_modules", ".next", "dist", "build"} for part in lockfile.relative_to(repo_dir).parts):
            continue
        dependencies.extend(_package_lock_dependencies(lockfile))
    return dependencies[:150]


def _osv_api_fallback_tool(spec: ScannerToolSpec, repo_dir: Path) -> dict[str, Any]:
    dependencies = _osv_query_dependencies(repo_dir)
    if not dependencies:
        return _unavailable_tool(spec, "osv-scanner CLI is not installed and no exact dependency versions were available for OSV API fallback evidence.")
    queries = [
        {"package": {"name": item["name"], "ecosystem": item["ecosystem"]}, "version": item["version"]}
        for item in dependencies
    ]
    try:
        response = requests.post(OSV_API, json={"queries": queries}, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return _unavailable_tool(spec, f"osv-scanner CLI is not installed and OSV API fallback was unavailable: {exc}")
    results = payload.get("results") if isinstance(payload, dict) else []
    findings: list[dict[str, Any]] = []
    if isinstance(results, list):
        for dependency, result in zip(dependencies, results):
            vulns = result.get("vulns", []) if isinstance(result, dict) else []
            for vuln in vulns:
                if isinstance(vuln, dict):
                    item = dict(vuln)
                    item.setdefault("package", dependency["name"])
                    item.setdefault("version", dependency["version"])
                    item.setdefault("ecosystem", dependency["ecosystem"])
                    findings.append(item)
    return redact_payload(
        {
            "tool": spec.name,
            "status": "completed",
            "category": spec.category,
            "returncode": 1 if findings else 0,
            "timed_out": False,
            "output_truncated": False,
            "execution_source": "osv_api_fallback",
            "evidence_summary": f"OSV API fallback queried {len(dependencies)} exact dependency version(s) because osv-scanner CLI was not installed.",
            "findings": findings,
            "stderr": "",
            "scans_git_history": spec.scans_git_history,
        }
    )


def _read_package_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _has_eslint_config(path: Path) -> bool:
    return any((path / name).exists() for name in ESLINT_CONFIG_NAMES)


def _package_script(path: Path, script_name: str) -> str | None:
    payload = _read_package_json(path / "package.json")
    scripts = payload.get("scripts")
    if not isinstance(scripts, dict):
        return None
    value = scripts.get(script_name)
    return str(value) if value else None


def _resolve_command_and_cwd(spec: ScannerToolSpec, workspace: WorkerWorkspace) -> tuple[tuple[str, ...] | None, Path, str | None]:
    repo_dir = workspace.repo_dir
    web_dir = repo_dir / "apps" / "web"
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
    if spec.name == "eslint":
        if (web_dir / "package.json").exists():
            if _has_eslint_config(web_dir):
                return spec.command, web_dir, None
            if _package_script(web_dir, "lint"):
                return ("npm", "run", "lint"), web_dir, None
        return None, repo_dir, "No frontend ESLint config or lint script was found for scanner-worker ESLint evidence."
    if spec.name == "typescript":
        if (web_dir / "package.json").exists():
            if _package_script(web_dir, "lint"):
                return ("npm", "run", "lint"), web_dir, None
            return spec.command, web_dir, None
        return None, repo_dir, "apps/web/package.json not found for TypeScript scanner-worker evidence."
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

    if shutil.which(spec.command[0]) is None:
        if spec.name == "osv-scanner":
            return _osv_api_fallback_tool(spec, workspace.repo_dir)
        return _unavailable_tool(spec, f"{spec.command[0]} is not installed in the worker image")

    command, cwd, unavailable_reason = _resolve_command_and_cwd(spec, workspace)
    if command is None:
        return _unavailable_tool(spec, unavailable_reason or f"{spec.name} could not resolve a safe command")
    if shutil.which(command[0]) is None:
        return _unavailable_tool(spec, f"{command[0]} is not installed in the worker image")

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
            "command_intent": " ".join(command[:3]),
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
