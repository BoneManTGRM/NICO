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
MAX_SCANNER_PARSE_BYTES = int(os.getenv("NICO_MAX_SCANNER_PARSE_BYTES", str(20 * 1024 * 1024)))

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
    valid_returncodes: frozenset[int] = frozenset({0, 1})


@dataclass(frozen=True)
class ProjectCommandPreparation:
    status: str
    web_dir: Path
    node_modules_ready: bool
    reason: str = ""
    returncode: int | None = None
    timed_out: bool = False
    output_truncated: bool = False

    @property
    def project_dir(self) -> Path:
        """Layout-neutral alias retained alongside the legacy ``web_dir`` field."""

        return self.web_dir


TOOL_SPECS: tuple[ScannerToolSpec, ...] = (
    ScannerToolSpec("pip-audit", ("pip-audit", "-r", "requirements.txt", "-f", "json"), "dependency", timeout_seconds=240, max_output_chars=500_000),
    ScannerToolSpec("npm-audit", ("npm", "audit", "--json", "--package-lock-only", "--ignore-scripts"), "dependency", timeout_seconds=240, max_output_chars=1_000_000),
    ScannerToolSpec("osv-scanner", ("osv-scanner", "--format", "json", "."), "dependency", timeout_seconds=240, max_output_chars=1_000_000),
    ScannerToolSpec("bandit", ("bandit", "-r", ".", "-f", "json"), "static", timeout_seconds=240, max_output_chars=2_000_000),
    ScannerToolSpec(
        "semgrep",
        (
            "semgrep",
            "scan",
            "--config",
            "auto",
            "--json",
            "--jobs",
            "1",
            "--max-memory",
            "1024",
            "--timeout",
            "30",
            "--timeout-threshold",
            "5",
            "--exclude",
            "node_modules",
            "--exclude",
            ".next",
            "--exclude",
            "dist",
            "--exclude",
            "build",
            ".",
        ),
        "static",
        timeout_seconds=360,
        max_output_chars=4_000_000,
    ),
    ScannerToolSpec("eslint", ("eslint", ".", "--format", "json"), "static", timeout_seconds=300, max_output_chars=4_000_000, requires_project_commands=True, valid_returncodes=frozenset({0, 1})),
    ScannerToolSpec("typescript", ("tsc", "--noEmit", "--pretty", "false", "--incremental", "false"), "static", timeout_seconds=300, max_output_chars=2_000_000, requires_project_commands=True, valid_returncodes=frozenset({0, 1, 2})),
    ScannerToolSpec("gitleaks", ("gitleaks", "detect", "--no-banner", "--redact", "--report-format", "json", "--source", ".", "--log-opts", "HEAD"), "secret", timeout_seconds=600, max_output_chars=2_000_000, scans_git_history=True),
    ScannerToolSpec("trufflehog", ("trufflehog", "git", "file://{repo_dir}", "--json", "--no-update", "--no-verification", "--branch", "HEAD"), "secret", timeout_seconds=600, max_output_chars=4_000_000, scans_git_history=True, valid_returncodes=frozenset({0})),
    ScannerToolSpec("coverage", ("coverage", "run", "-m", "pytest", "-q"), "coverage", timeout_seconds=360, max_output_chars=2_000_000, requires_project_commands=True, valid_returncodes=frozenset({0, 1})),
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


def _complete_stdout(result: WorkerCommandResult) -> tuple[str, bool, str]:
    if result.stdout_path:
        path = Path(result.stdout_path)
        try:
            size = path.stat().st_size
            if size > MAX_SCANNER_PARSE_BYTES:
                return result.stdout, False, f"scanner output exceeded the bounded parse limit of {MAX_SCANNER_PARSE_BYTES} bytes"
            return path.read_text(encoding="utf-8", errors="replace"), True, ""
        except OSError as exc:
            return result.stdout, False, f"scanner output file could not be read: {type(exc).__name__}"
    return result.stdout, not result.output_truncated, "" if not result.output_truncated else "scanner output was truncated before parsing"


def _typescript_findings(text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    pattern = re.compile(r"^(?P<file>.+?)\((?P<line>\d+),(?P<column>\d+)\):\s+error\s+(?P<code>TS\d+):\s+(?P<message>.+)$")
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match:
            findings.append(
                {
                    "file_path": match.group("file"),
                    "line": int(match.group("line")),
                    "column": int(match.group("column")),
                    "code": match.group("code"),
                    "message": match.group("message"),
                    "severity": "high",
                }
            )
    if findings:
        return findings
    return [{"message": redact_text(text[:20_000])}] if text.strip() else []


def parse_tool_findings(tool_name: str, result: WorkerCommandResult) -> tuple[list[Any], bool, str]:
    raw_text, capture_complete, capture_reason = _complete_stdout(result)
    text = redact_text(raw_text or "")
    if not text.strip():
        if result.returncode == 0:
            return [], capture_complete, capture_reason
        fallback = redact_text(result.stderr or "tool failed without stdout")
        return ([{"message": fallback}] if fallback else []), capture_complete, capture_reason

    if tool_name == "typescript":
        return _typescript_findings(text), capture_complete, capture_reason

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        if tool_name == "trufflehog":
            items = _parse_json_lines(text)
            return items, capture_complete and bool(items or not text.strip()), capture_reason or ("" if items else "trufflehog JSON-lines output could not be parsed")
        if tool_name in {"eslint", "coverage"} and result.returncode != 0:
            return [{"message": redact_text(result.stderr or text)}], False, capture_reason or "tool returned non-JSON diagnostic output"
        return [], False, capture_reason or "scanner JSON output could not be parsed"

    if tool_name == "pip-audit" and isinstance(payload, dict):
        return _pip_audit_findings(payload), capture_complete, capture_reason
    if tool_name == "npm-audit" and isinstance(payload, dict):
        return _npm_audit_findings(payload), capture_complete, capture_reason
    if tool_name == "osv-scanner" and isinstance(payload, dict):
        return _osv_findings(payload), capture_complete, capture_reason
    if tool_name == "bandit" and isinstance(payload, dict):
        return payload.get("results") or [], capture_complete, capture_reason
    if tool_name == "semgrep" and isinstance(payload, dict):
        return payload.get("results") or [], capture_complete, capture_reason
    if tool_name == "eslint" and isinstance(payload, list):
        findings: list[Any] = []
        for file_result in payload:
            if isinstance(file_result, dict):
                for message in file_result.get("messages") or []:
                    if isinstance(message, dict):
                        item = dict(message)
                        item.setdefault("filePath", file_result.get("filePath"))
                        findings.append(item)
        return findings, capture_complete, capture_reason
    if tool_name == "coverage":
        return ([] if result.returncode == 0 else [{"message": redact_text(result.stderr or text)}]), capture_complete, capture_reason
    if tool_name == "gitleaks" and isinstance(payload, list):
        return payload, capture_complete, capture_reason
    if tool_name == "trufflehog" and isinstance(payload, dict):
        return [payload], capture_complete, capture_reason
    return [], capture_complete, capture_reason


def _unavailable_tool(spec: ScannerToolSpec, reason: str, *, preparation: ProjectCommandPreparation | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tool": spec.name,
        "status": "unavailable",
        "category": spec.category,
        "reason": reason,
        "findings": [],
        "scans_git_history": spec.scans_git_history,
        "verified_for_this_report": False,
    }
    if preparation is not None:
        payload["project_preparation"] = {
            "status": preparation.status,
            "reason": preparation.reason,
            "returncode": preparation.returncode,
            "timed_out": preparation.timed_out,
            "output_truncated": preparation.output_truncated,
        }
    return payload


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
    except (requests.RequestException, ValueError) as exc:
        return _unavailable_tool(spec, f"OSV API fallback failed: {type(exc).__name__}")
    findings: list[dict[str, Any]] = []
    for dependency, result in zip(dependencies, payload.get("results") or [], strict=False):
        if not isinstance(result, dict):
            continue
        for vulnerability in result.get("vulns") or []:
            if isinstance(vulnerability, dict):
                item = dict(vulnerability)
                item.setdefault("package", dependency["name"])
                item.setdefault("installed_version", dependency["version"])
                findings.append(item)
    return {
        "tool": spec.name,
        "status": "completed",
        "category": spec.category,
        "returncode": 0,
        "returncode_valid": True,
        "timed_out": False,
        "output_truncated": False,
        "output_capture_complete": True,
        "stdout_bytes": 0,
        "stderr_bytes": 0,
        "command_intent": "osv-api querybatch",
        "findings": redact_payload(findings),
        "stderr": "",
        "reason": "",
        "scans_git_history": False,
        "verified_for_this_report": True,
        "fallback": "OSV querybatch API",
        "dependency_count": len(dependencies),
    }


def _has_eslint_config(web_dir: Path) -> bool:
    return any((web_dir / name).exists() for name in ESLINT_CONFIG_NAMES)


def _package_script(web_dir: Path, name: str) -> str:
    package_json = web_dir / "package.json"
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    scripts = payload.get("scripts")
    if not isinstance(scripts, dict):
        return ""
    value = scripts.get(name)
    return str(value).strip() if isinstance(value, str) else ""


def _node_env(workspace: WorkerWorkspace, cwd: Path) -> dict[str, str]:
    node_path = str(cwd / "node_modules")
    current = os.getenv("NODE_PATH", "")
    return {
        "HOME": str(workspace.root / "home"),
        "npm_config_cache": str(workspace.root / "npm-cache"),
        "npm_config_update_notifier": "false",
        "npm_config_fund": "false",
        "npm_config_audit": "false",
        "NODE_PATH": node_path if not current else f"{node_path}{os.pathsep}{current}",
        "PATH": f"{cwd / 'node_modules' / '.bin'}{os.pathsep}{os.getenv('PATH', '')}",
    }


def resolve_node_project_dir(repo_dir: Path) -> Path:
    """Resolve the deterministic Node project assessed by project-local tools.

    NICO itself uses ``apps/web`` while many customer repositories, including
    SARA, keep package.json at the repository root. Prefer the established
    monorepo frontend when present, then support the conventional root layout.
    """

    web_dir = repo_dir / "apps" / "web"
    if (web_dir / "package.json").is_file():
        return web_dir
    if (repo_dir / "package.json").is_file():
        return repo_dir
    return web_dir


def prepare_project_commands(
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult] = run_command,
) -> ProjectCommandPreparation:
    project_dir = resolve_node_project_dir(workspace.repo_dir)
    package_json = project_dir / "package.json"
    lockfile = project_dir / "package-lock.json"
    if not package_json.exists():
        return ProjectCommandPreparation("unavailable", project_dir, False, "No supported package.json was found at apps/web or the repository root.")
    if not lockfile.exists():
        return ProjectCommandPreparation("unavailable", project_dir, False, f"{lockfile.relative_to(workspace.repo_dir)} is required for deterministic project-tool preparation.")
    npm = shutil.which("npm")
    if not npm:
        return ProjectCommandPreparation("unavailable", project_dir, False, "npm is not installed in the worker image.")

    output_path = workspace.root / "scanner-output" / "npm-ci.stdout"
    result = runner(
        (
            npm,
            "ci",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            "--prefer-offline",
        ),
        cwd=project_dir,
        limits=WorkerLimits(timeout_seconds=420, max_output_chars=200_000),
        extra_env=_node_env(workspace, project_dir),
        stdout_path=output_path,
    )
    ready = result.returncode == 0 and not result.timed_out and (project_dir / "node_modules").is_dir()
    reason = "" if ready else redact_text(result.stderr or result.stdout or "npm ci did not establish node_modules")[:2000]
    return ProjectCommandPreparation(
        "completed" if ready else "failed",
        project_dir,
        ready,
        reason,
        returncode=result.returncode,
        timed_out=result.timed_out,
        output_truncated=result.output_truncated,
    )


def _resolve_command_and_cwd(
    spec: ScannerToolSpec,
    workspace: WorkerWorkspace,
    preparation: ProjectCommandPreparation | None,
) -> tuple[tuple[str, ...] | None, Path, str | None]:
    repo_dir = workspace.repo_dir
    web_dir = resolve_node_project_dir(repo_dir)
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
    if spec.name in {"eslint", "typescript"}:
        if preparation is None or not preparation.node_modules_ready:
            return None, web_dir, preparation.reason if preparation else "Project dependencies were not prepared."
        bin_name = "eslint" if spec.name == "eslint" else "tsc"
        binary = web_dir / "node_modules" / ".bin" / bin_name
        if not binary.exists():
            return None, web_dir, f"{bin_name} was not installed by the exact package-lock dependency preparation."
        if spec.name == "eslint":
            if not _has_eslint_config(web_dir) and not _package_script(web_dir, "lint"):
                return None, web_dir, "No ESLint configuration or lint script was found in the resolved Node project."
            return (str(binary), ".", "--format", "json"), web_dir, None
        tsconfig = web_dir / "tsconfig.json"
        if not tsconfig.exists():
            return None, web_dir, "tsconfig.json not found in the resolved Node project for TypeScript evidence."
        return (str(binary), "--noEmit", "--pretty", "false", "--incremental", "false", "-p", str(tsconfig)), web_dir, None
    if spec.name == "trufflehog":
        command = tuple(part.replace("{repo_dir}", str(repo_dir)) for part in spec.command)
        if "--branch" not in command:
            command += ("--branch", "HEAD")
        return command, repo_dir, None
    if spec.name == "gitleaks":
        command = spec.command
        if "--log-opts" not in command:
            command += ("--log-opts", "HEAD")
        return command, repo_dir, None
    return spec.command, repo_dir, None


def _command_available(command: tuple[str, ...]) -> bool:
    executable = command[0]
    if "/" in executable:
        return Path(executable).is_file() and os.access(executable, os.X_OK)
    return shutil.which(executable) is not None


def _tool_env(spec: ScannerToolSpec, workspace: WorkerWorkspace, cwd: Path) -> dict[str, str]:
    env: dict[str, str] = {
        "CI": "true",
        "NO_COLOR": "1",
        "FORCE_COLOR": "0",
    }
    if spec.name in {"eslint", "typescript"}:
        env.update(_node_env(workspace, cwd))
    if spec.name == "semgrep":
        env.update({"SEMGREP_SEND_METRICS": "off", "SEMGREP_ENABLE_VERSION_CHECK": "0"})
    return env


def _invoke_runner(
    runner: Callable[..., WorkerCommandResult],
    command: tuple[str, ...],
    *,
    cwd: Path,
    limits: WorkerLimits,
    extra_env: dict[str, str],
    stdout_path: Path,
) -> WorkerCommandResult:
    """Support production runners and minimal test doubles without weakening production evidence."""
    try:
        return runner(
            command,
            cwd=cwd,
            limits=limits,
            extra_env=extra_env,
            stdout_path=stdout_path,
        )
    except TypeError as exc:
        message = str(exc)
        if "unexpected keyword argument" not in message:
            raise
        return runner(command, cwd=cwd, limits=limits)


def run_scanner_tool(
    spec: ScannerToolSpec,
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult] = run_command,
    preparation: ProjectCommandPreparation | None = None,
) -> dict[str, Any]:
    if spec.requires_project_commands and not project_commands_allowed():
        return _unavailable_tool(
            spec,
            f"{spec.name} requires NICO_ALLOW_PROJECT_COMMANDS=true because it may execute project-local commands.",
        )
    if spec.requires_project_commands and preparation is None:
        preparation = prepare_project_commands(workspace, runner=runner)

    if spec.name == "osv-scanner" and shutil.which(spec.command[0]) is None:
        return _osv_api_fallback_tool(spec, workspace.repo_dir)

    command, cwd, unavailable_reason = _resolve_command_and_cwd(spec, workspace, preparation)
    if command is None:
        return _unavailable_tool(spec, unavailable_reason or f"{spec.name} could not resolve a safe command", preparation=preparation)
    if not _command_available(command):
        return _unavailable_tool(spec, f"{command[0]} is not installed in the worker image", preparation=preparation)

    output_path = workspace.root / "scanner-output" / f"{spec.name}.stdout"
    result = _invoke_runner(
        runner,
        command,
        cwd=cwd,
        limits=WorkerLimits(timeout_seconds=spec.timeout_seconds, max_output_chars=spec.max_output_chars),
        extra_env=_tool_env(spec, workspace, cwd),
        stdout_path=output_path,
    )
    findings, capture_complete, capture_reason = parse_tool_findings(spec.name, result)
    returncode_valid = result.returncode in spec.valid_returncodes
    if result.timed_out:
        status = "timeout"
        execution_error = f"{spec.name} exceeded its {spec.timeout_seconds}-second bounded timeout."
    elif not returncode_valid:
        status = "failed"
        execution_error = redact_text(result.stderr or result.stdout or f"unexpected return code {result.returncode}")[:4000]
    elif not capture_complete:
        status = "failed"
        execution_error = capture_reason or "scanner output could not be parsed completely"
    else:
        status = "completed"
        execution_error = ""

    payload = {
        "tool": spec.name,
        "status": status,
        "category": spec.category,
        "returncode": result.returncode,
        "returncode_valid": returncode_valid,
        "timed_out": result.timed_out,
        "output_truncated": result.output_truncated,
        "output_capture_complete": capture_complete,
        "stdout_bytes": result.stdout_bytes,
        "stderr_bytes": result.stderr_bytes,
        "command_intent": " ".join(Path(part).name if index == 0 else part for index, part in enumerate(command[:5])),
        "findings": findings,
        "stderr": result.stderr,
        "reason": execution_error,
        "scans_git_history": spec.scans_git_history,
        "verified_for_this_report": status == "completed",
    }
    if preparation is not None and spec.requires_project_commands:
        payload["project_preparation"] = {
            "status": preparation.status,
            "node_modules_ready": preparation.node_modules_ready,
            "returncode": preparation.returncode,
            "timed_out": preparation.timed_out,
            "output_truncated": preparation.output_truncated,
        }
    return redact_payload(payload)


def run_scanner_tools(
    workspace: WorkerWorkspace,
    specs: tuple[ScannerToolSpec, ...] = TOOL_SPECS,
    *,
    runner: Callable[..., WorkerCommandResult] = run_command,
) -> dict[str, Any]:
    if not workspace.repo_dir.exists() or not workspace.repo_dir.is_dir():
        raise ValueError("workspace repo directory must exist before scanner tools run")

    needs_project = any(spec.requires_project_commands for spec in specs)
    preparation = prepare_project_commands(workspace, runner=runner) if needs_project and project_commands_allowed() else None
    tool_results = [run_scanner_tool(spec, workspace, runner=runner, preparation=preparation) for spec in specs]
    raw_payload = {"tools": tool_results}
    normalized = normalize_scanner_worker_artifact(raw_payload)
    history_secret_tools = [
        item["tool"]
        for item in tool_results
        if isinstance(item, dict)
        and item.get("category") == "secret"
        and item.get("status") == "completed"
        and item.get("scans_git_history")
        and item.get("full_history_verified") is True
    ]
    return {
        "artifact_schema": "nico.scanner_worker.v2",
        "tools": {item["tool"]: item for item in tool_results if isinstance(item, dict) and item.get("tool")},
        "normalized": normalized,
        "project_preparation": {
            "status": preparation.status,
            "node_modules_ready": preparation.node_modules_ready,
            "reason": preparation.reason,
        } if preparation else {"status": "not_required", "node_modules_ready": False},
        "secret_history_scan": {
            "completed_tools": history_secret_tools,
            "history_aware": bool(history_secret_tools),
        },
    }


def write_scanner_artifact(payload: dict[str, Any], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(redact_payload(payload), indent=2, sort_keys=True), encoding="utf-8")
    return destination
