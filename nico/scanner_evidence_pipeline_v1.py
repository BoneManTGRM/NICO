from __future__ import annotations

import csv
import gzip
import hashlib
import inspect
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable

from nico.scanner_tool_runners import (
    ScannerToolSpec,
    TOOL_SPECS,
    ProjectCommandPreparation,
    _node_env,
    normalize_scanner_worker_artifact,
    prepare_project_commands,
    redact_payload,
    redact_text,
    resolve_node_project_dir,
)
from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace, run_command

VERSION = "nico.scanner_evidence_pipeline.v1"
_PATCH_MARKER = "_nico_scanner_evidence_pipeline_v1"
REQUIRED_EVIDENCE_TOOLS = (
    "pip-audit",
    "npm-audit",
    "osv-scanner",
    "bandit",
    "semgrep",
    "eslint",
    "typescript",
    "gitleaks",
    "trufflehog",
)
GENERATED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "dist",
    "build",
    "coverage_html",
    "__pycache__",
}
MAX_PARSE_BYTES = int(os.getenv("NICO_MAX_SCANNER_PARSE_BYTES", str(256 * 1024 * 1024)))
DEFAULT_RAW_ROOT = os.getenv("NICO_SCANNER_RAW_ARTIFACT_ROOT", str(Path(tempfile.gettempdir()) / "nico-scanner-artifacts"))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _runner_kwargs(runner: Callable[..., WorkerCommandResult], **kwargs: Any) -> dict[str, Any]:
    try:
        parameters = inspect.signature(runner).parameters
    except (TypeError, ValueError):
        return kwargs
    accepts_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
    if accepts_kwargs:
        return kwargs
    return {key: value for key, value in kwargs.items() if key in parameters}


def _run(
    runner: Callable[..., WorkerCommandResult],
    command: tuple[str, ...],
    *,
    cwd: Path,
    limits: WorkerLimits,
    stdout_path: Path,
    extra_env: dict[str, str] | None = None,
) -> WorkerCommandResult:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    kwargs = _runner_kwargs(
        runner,
        cwd=cwd,
        limits=limits,
        stdout_path=stdout_path,
        extra_env=extra_env or {},
    )
    result = runner(command, **kwargs)
    if not stdout_path.exists():
        stdout_path.write_text(result.stdout or "", encoding="utf-8", errors="replace")
    return result


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _read_json(path: Path) -> tuple[Any, str]:
    if not path.exists():
        return None, "scanner output file is missing"
    size = path.stat().st_size
    if size > MAX_PARSE_BYTES:
        return None, f"scanner output exceeded the bounded parse limit of {MAX_PARSE_BYTES} bytes"
    try:
        return json.loads(_read_text(path)), ""
    except json.JSONDecodeError as exc:
        return None, f"scanner JSON output could not be parsed: line {exc.lineno} column {exc.colno}"


def _raw_blob(tool: str, path: Path, raw_format: str) -> dict[str, Any]:
    present = path.exists() and path.is_file()
    raw = path.read_bytes() if present else b""
    redacted = redact_text(raw.decode("utf-8", errors="replace")).encode("utf-8")
    compressed = gzip.compress(redacted, compresslevel=6, mtime=0)
    return {
        "tool": tool,
        "filename": f"{tool}.{raw_format}.gz".replace("/", "_"),
        "raw_format": raw_format,
        "present": present,
        "source_bytes": len(raw),
        "retained_bytes": len(redacted),
        "gzip_bytes": len(compressed),
        "sha256": _sha256(redacted),
        "gzip_sha256": _sha256(compressed),
        # Hex is intentionally used for the short-lived transport object. The
        # package-wide secret redactor cannot mutate hexadecimal text, so the
        # checksum remains stable until the outer worker persists the gzip.
        "gzip_hex": compressed.hex(),
        "redacted": True,
    }


def _normalize_value(value: Any, workspace: WorkerWorkspace) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        ignored_keys = {
            "generated_at", "started_at", "finished_at", "duration_seconds",
            "elapsed", "elapsed_seconds", "run_id", "timestamp", "scan_time",
            "scan_start", "scan_end", "profiling_times",
        }
        volatile_path_keys = {"repository_local_path"}
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            text_key = str(key)
            lower_key = text_key.lower()
            if lower_key in ignored_keys:
                continue
            if lower_key in volatile_path_keys:
                normalized[text_key] = "<scanner-temp>"
            else:
                normalized[text_key] = _normalize_value(item, workspace)
        return normalized
    if isinstance(value, list):
        normalized = [_normalize_value(item, workspace) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    if isinstance(value, str):
        text = value.replace(str(workspace.root), "<workspace>").replace(str(workspace.repo_dir), "<repo>")
        return text
    return value

def _deterministic_fingerprint(payload: dict[str, Any], workspace: WorkerWorkspace) -> str:
    canonical = _normalize_value(
        {
            "tool": payload.get("tool"),
            "status": payload.get("status"),
            "returncode": payload.get("returncode"),
            "findings": payload.get("findings") or [],
            "full_history_verified": payload.get("full_history_verified"),
            "output_capture_complete": payload.get("output_capture_complete"),
        },
        workspace,
    )
    return _sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))


def _scanner_version(tool_name: str, executable: str, cwd: Path) -> str:
    command = (executable, "version") if tool_name == "gitleaks" else (executable, "--version")
    try:
        result = run_command(command, cwd=cwd, limits=WorkerLimits(20, 4_000))
    except Exception:
        return "unavailable"
    text = (result.stdout or result.stderr or "").strip().splitlines()
    return redact_text(text[0])[:500] if text else "unavailable"


def _tool_payload(
    spec: ScannerToolSpec,
    result: WorkerCommandResult,
    *,
    findings: list[Any],
    capture_complete: bool,
    reason: str,
    raw_blob: dict[str, Any],
    execution_source: str,
    workspace: WorkerWorkspace,
    valid_returncodes: Iterable[int] | None = None,
    full_history_verified: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    valid = set(valid_returncodes or spec.valid_returncodes)
    if result.timed_out:
        status = "timeout"
        reason = reason or f"{spec.name} exceeded its {spec.timeout_seconds}-second timeout."
    elif result.returncode not in valid:
        status = "failed"
        reason = reason or redact_text(result.stderr or result.stdout or f"unexpected return code {result.returncode}")[:4000]
    elif not capture_complete:
        status = "failed"
        reason = reason or "scanner output could not be captured and parsed completely"
    elif spec.scans_git_history and not full_history_verified:
        status = "failed"
        reason = reason or "full git history was not verified for the secret scanner"
    else:
        status = "completed"
        reason = ""
    payload: dict[str, Any] = {
        "tool": spec.name,
        "status": status,
        "category": spec.category,
        "returncode": result.returncode,
        "returncode_valid": result.returncode in valid,
        "timed_out": result.timed_out,
        "output_truncated": result.output_truncated,
        "output_capture_complete": capture_complete,
        "stdout_bytes": result.stdout_bytes,
        "stderr_bytes": result.stderr_bytes,
        "command_intent": " ".join(
            Path(part).name if index == 0 else str(part)
            for index, part in enumerate(tuple(result.args)[:10])
        ),
        "scanner_tool_version": _scanner_version(spec.name, str(result.args[0]), workspace.repo_dir),
        "findings": findings,
        "findings_count": len(findings),
        "stderr": redact_text(result.stderr or "")[:4000],
        "reason": reason,
        "failure_or_unavailable_reason": reason,
        "execution_source": execution_source,
        "execution_observed_for_this_report": True,
        "current_run": True,
        "verified_for_this_report": status == "completed",
        "scans_git_history": spec.scans_git_history,
        "full_history_verified": full_history_verified if spec.scans_git_history else False,
        "raw_artifact_capture_complete": bool(raw_blob.get("present")) and bool(raw_blob.get("sha256")),
        "raw_artifact_sha256": raw_blob.get("sha256"),
        "raw_artifact_format": raw_blob.get("raw_format"),
        "raw_artifact_bytes": raw_blob.get("retained_bytes"),
    }
    if extra:
        payload.update(extra)
    payload["deterministic_fingerprint"] = _deterministic_fingerprint(payload, workspace)
    safe_payload = redact_payload(payload)
    safe_payload["artifact_hash"] = _sha256(
        json.dumps(safe_payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    )
    safe_payload["_raw_artifact_blob"] = raw_blob
    return safe_payload


def _unavailable(spec: ScannerToolSpec, reason: str, *, source: str) -> dict[str, Any]:
    return {
        "tool": spec.name,
        "status": "unavailable",
        "category": spec.category,
        "reason": reason,
        "failure_or_unavailable_reason": reason,
        "findings": [],
        "findings_count": 0,
        "execution_source": source,
        "execution_observed_for_this_report": True,
        "current_run": True,
        "verified_for_this_report": False,
        "raw_artifact_capture_complete": False,
        "scans_git_history": spec.scans_git_history,
        "full_history_verified": False,
    }


def _requirements(repo_dir: Path) -> Path | None:
    direct = repo_dir / "requirements.txt"
    if direct.exists():
        return direct
    for path in repo_dir.glob("**/requirements.txt"):
        if not any(part in GENERATED_DIRS for part in path.relative_to(repo_dir).parts):
            return path
    return None


def _lockfile_dirs(repo_dir: Path) -> list[Path]:
    directories: list[Path] = []
    for lockfile in repo_dir.glob("**/package-lock.json"):
        relative = lockfile.relative_to(repo_dir)
        if any(part in GENERATED_DIRS for part in relative.parts):
            continue
        if (lockfile.parent / "package.json").exists() and lockfile.parent not in directories:
            directories.append(lockfile.parent)
    return sorted(directories)


def _npm_findings(payload: Any) -> list[Any]:
    findings: list[Any] = []
    if not isinstance(payload, dict):
        return findings
    vulnerabilities = payload.get("vulnerabilities")
    if isinstance(vulnerabilities, dict):
        for package, value in vulnerabilities.items():
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("package", package)
                findings.append(item)
    return findings


def _pip_findings(payload: Any) -> list[Any]:
    findings: list[Any] = []
    if not isinstance(payload, dict):
        return findings
    for dependency in payload.get("dependencies") or []:
        if not isinstance(dependency, dict):
            continue
        for vulnerability in dependency.get("vulns") or []:
            if isinstance(vulnerability, dict):
                item = dict(vulnerability)
                item.setdefault("package", dependency.get("name"))
                item.setdefault("installed_version", dependency.get("version"))
                findings.append(item)
    return findings


def _walk_vulnerabilities(value: Any, findings: list[dict[str, Any]]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"vulnerabilities", "vulns"} and isinstance(item, list):
                findings.extend(entry for entry in item if isinstance(entry, dict))
            else:
                _walk_vulnerabilities(item, findings)
    elif isinstance(value, list):
        for item in value:
            _walk_vulnerabilities(item, findings)


def _osv_findings(payload: Any) -> list[Any]:
    findings: list[dict[str, Any]] = []
    _walk_vulnerabilities(payload, findings)
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in findings:
        marker = json.dumps(item, sort_keys=True, default=str)
        if marker not in seen:
            seen.add(marker)
            unique.append(item)
    return unique


def _run_pip_audit(spec: ScannerToolSpec, workspace: WorkerWorkspace, runner: Callable[..., WorkerCommandResult]) -> dict[str, Any]:
    requirements = _requirements(workspace.repo_dir)
    binary = shutil.which("pip-audit")
    if requirements is None:
        return _unavailable(spec, "requirements.txt was not found.", source="canonical_pip_audit")
    if binary is None:
        return _unavailable(spec, "pip-audit is not installed in the worker image.", source="canonical_pip_audit")
    raw = workspace.root / "scanner-raw" / "pip-audit.json"
    command = (binary, "-r", str(requirements), "-f", "json")
    result = _run(runner, command, cwd=workspace.repo_dir, limits=WorkerLimits(spec.timeout_seconds, spec.max_output_chars), stdout_path=raw)
    payload, parse_reason = _read_json(raw)
    blob = _raw_blob(spec.name, raw, "json")
    return _tool_payload(spec, result, findings=_pip_findings(payload), capture_complete=payload is not None, reason=parse_reason, raw_blob=blob, execution_source="canonical_pip_audit", workspace=workspace, valid_returncodes={0, 1})


def _run_npm_audit(spec: ScannerToolSpec, workspace: WorkerWorkspace, runner: Callable[..., WorkerCommandResult]) -> dict[str, Any]:
    binary = shutil.which("npm")
    directories = _lockfile_dirs(workspace.repo_dir)
    if binary is None:
        return _unavailable(spec, "npm is not installed in the worker image.", source="canonical_npm_audit")
    if not directories:
        return _unavailable(spec, "No package-lock.json with an adjacent package.json was found.", source="canonical_npm_audit")
    runs: list[dict[str, Any]] = []
    findings: list[Any] = []
    valid = True
    last_result = WorkerCommandResult(args=(binary,), returncode=0, stdout="", stderr="")
    for index, directory in enumerate(directories, start=1):
        raw = workspace.root / "scanner-raw" / f"npm-audit-{index}.json"
        command = (binary, "audit", "--json", "--package-lock-only", "--ignore-scripts")
        result = _run(runner, command, cwd=directory, limits=WorkerLimits(spec.timeout_seconds, spec.max_output_chars), stdout_path=raw)
        last_result = result
        payload, reason = _read_json(raw)
        valid = valid and payload is not None and result.returncode in {0, 1} and not result.timed_out
        findings.extend(_npm_findings(payload))
        runs.append({"directory": str(directory.relative_to(workspace.repo_dir)), "returncode": result.returncode, "payload": payload, "reason": reason})
    combined = workspace.root / "scanner-raw" / "npm-audit.json"
    combined.write_text(json.dumps({"runs": runs}, indent=2, sort_keys=True), encoding="utf-8")
    blob = _raw_blob(spec.name, combined, "json")
    return _tool_payload(spec, last_result, findings=findings, capture_complete=valid, reason="" if valid else "one or more npm audit runs did not return complete JSON", raw_blob=blob, execution_source="canonical_npm_audit", workspace=workspace, valid_returncodes={0, 1}, extra={"lockfile_count_checked": len(directories)})


def _run_osv(spec: ScannerToolSpec, workspace: WorkerWorkspace, runner: Callable[..., WorkerCommandResult]) -> dict[str, Any]:
    binary = shutil.which("osv-scanner")
    if binary is None:
        return _unavailable(spec, "osv-scanner is not installed in the worker image.", source="canonical_osv_scanner")
    attempts = (
        (binary, "scan", "source", "-r", ".", "--format", "json"),
        (binary, "--format", "json", "."),
    )
    failure_reasons: list[str] = []
    last_result = WorkerCommandResult(args=(binary,), returncode=127, stdout="", stderr="")
    last_raw = workspace.root / "scanner-raw" / "osv-scanner.json"
    for index, command in enumerate(attempts, start=1):
        raw = workspace.root / "scanner-raw" / f"osv-scanner-attempt-{index}.json"
        result = _run(runner, command, cwd=workspace.repo_dir, limits=WorkerLimits(spec.timeout_seconds, spec.max_output_chars), stdout_path=raw)
        last_result, last_raw = result, raw
        payload, reason = _read_json(raw)
        if payload is not None and result.returncode in {0, 1} and not result.timed_out:
            canonical = workspace.root / "scanner-raw" / "osv-scanner.json"
            shutil.copyfile(raw, canonical)
            blob = _raw_blob(spec.name, canonical, "json")
            return _tool_payload(spec, result, findings=_osv_findings(payload), capture_complete=True, reason="", raw_blob=blob, execution_source=f"canonical_osv_scanner_v{index}", workspace=workspace, valid_returncodes={0, 1}, extra={"command_variant": index})
        failure_reasons.append(reason or redact_text(result.stderr or result.stdout or f"exit {result.returncode}")[:1000])
    blob = _raw_blob(spec.name, last_raw, "json")
    return _tool_payload(spec, last_result, findings=[], capture_complete=False, reason="; ".join(failure_reasons), raw_blob=blob, execution_source="canonical_osv_scanner", workspace=workspace, valid_returncodes={0, 1})


def _run_bandit(spec: ScannerToolSpec, workspace: WorkerWorkspace, runner: Callable[..., WorkerCommandResult]) -> dict[str, Any]:
    binary = shutil.which("bandit")
    if binary is None:
        return _unavailable(spec, "bandit is not installed in the worker image.", source="canonical_bandit_csv")
    raw = workspace.root / "scanner-raw" / "bandit.csv"
    raw.parent.mkdir(parents=True, exist_ok=True)
    log = workspace.root / "scanner-output" / "bandit.log"
    command = (binary, "-r", ".", "-f", "csv", "-o", str(raw), "-x", ",".join(sorted(GENERATED_DIRS)))
    result = _run(runner, command, cwd=workspace.repo_dir, limits=WorkerLimits(spec.timeout_seconds, max(spec.max_output_chars, 4_000_000)), stdout_path=log)
    findings: list[dict[str, Any]] = []
    reason = ""
    capture_complete = raw.exists()
    if raw.exists():
        try:
            with raw.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                reader = csv.DictReader(handle)
                required_columns = {"filename", "line_number", "issue_severity", "issue_confidence", "test_id"}
                if not required_columns.issubset(set(reader.fieldnames or [])):
                    raise csv.Error("Bandit CSV header is incomplete")
                for row in reader:
                    item = dict(row)
                    if item.get("line_number"):
                        try:
                            item["line_number"] = int(str(item["line_number"]))
                        except ValueError:
                            pass
                    findings.append(item)
        except (OSError, csv.Error) as exc:
            capture_complete = False
            reason = f"Bandit CSV output could not be parsed: {type(exc).__name__}"
    else:
        reason = "Bandit did not create its complete CSV report."
    blob = _raw_blob(spec.name, raw if raw.exists() else log, "csv")
    return _tool_payload(spec, result, findings=findings, capture_complete=capture_complete, reason=reason, raw_blob=blob, execution_source="canonical_bandit_csv", workspace=workspace, valid_returncodes={0, 1}, extra={"compact_complete_result": True})


def _semgrep_config(workspace: WorkerWorkspace) -> Path:
    config = workspace.root / "nico-semgrep-standard.yml"
    config.write_text(
        """rules:
  - id: nico.python.eval
    message: Dynamic eval execution requires security review.
    severity: ERROR
    languages: [python]
    pattern: eval(...)
  - id: nico.python.exec
    message: Dynamic exec execution requires security review.
    severity: ERROR
    languages: [python]
    pattern: exec(...)
  - id: nico.python.subprocess-shell
    message: subprocess with shell=True requires injection review.
    severity: ERROR
    languages: [python]
    pattern: subprocess.$FUNC(..., shell=True, ...)
  - id: nico.python.requests-no-verify
    message: TLS verification is disabled.
    severity: ERROR
    languages: [python]
    pattern: requests.$METHOD(..., verify=False, ...)
  - id: nico.javascript.eval
    message: Dynamic eval execution requires security review.
    severity: ERROR
    languages: [javascript, typescript]
    pattern: eval(...)
  - id: nico.javascript.new-function
    message: Dynamic Function construction requires security review.
    severity: ERROR
    languages: [javascript, typescript]
    pattern: new Function(...)
""",
        encoding="utf-8",
    )
    return config


def _run_semgrep(spec: ScannerToolSpec, workspace: WorkerWorkspace, runner: Callable[..., WorkerCommandResult]) -> dict[str, Any]:
    binary = shutil.which("semgrep")
    if binary is None:
        return _unavailable(spec, "semgrep is not installed in the worker image.", source="canonical_semgrep")
    raw = workspace.root / "scanner-raw" / "semgrep.json"
    config = _semgrep_config(workspace)
    command = (binary, "scan", "--config", str(config), "--json", "--jobs", "1", "--max-memory", "1536", "--timeout", "30", "--timeout-threshold", "5", "--exclude", "node_modules", "--exclude", ".next", "--exclude", "dist", "--exclude", "build", ".")
    result = _run(runner, command, cwd=workspace.repo_dir, limits=WorkerLimits(spec.timeout_seconds, max(spec.max_output_chars, 8_000_000)), stdout_path=raw, extra_env={"SEMGREP_SEND_METRICS": "off", "SEMGREP_ENABLE_VERSION_CHECK": "0"})
    payload, reason = _read_json(raw)
    findings = payload.get("results") if isinstance(payload, dict) and isinstance(payload.get("results"), list) else []
    errors = payload.get("errors") if isinstance(payload, dict) and isinstance(payload.get("errors"), list) else []
    capture_complete = payload is not None and not any(str(item.get("level") or "").lower() == "error" for item in errors if isinstance(item, dict))
    blob = _raw_blob(spec.name, raw, "json")
    return _tool_payload(spec, result, findings=findings, capture_complete=capture_complete, reason=reason or ("Semgrep reported execution errors." if not capture_complete else ""), raw_blob=blob, execution_source="nico_standard_semgrep_profile", workspace=workspace, valid_returncodes={0, 1}, extra={"scanner_error_count": len(errors), "generated_config_sha256": _sha256(config.read_bytes()), "configured_rule_count": 6})


def _supported_web_files(project_dir: Path) -> bool:
    supported = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
    ignored = GENERATED_DIRS | {".turbo", ".cache"}
    for path in project_dir.rglob("*"):
        if any(part in ignored for part in path.relative_to(project_dir).parts):
            continue
        if path.is_file() and path.suffix in supported:
            return True
    return False


def _node_module_path(name: str, web_dir: Path) -> Path | None:
    configured = str(os.getenv("NICO_ESLINT_MODULE_ROOT") or "").strip()
    roots = [Path(configured)] if configured else []
    roots.extend(Path(value) for value in os.getenv("NODE_PATH", "").split(os.pathsep) if value)
    roots.append(web_dir / "node_modules")
    seen: set[str] = set()
    for root in roots:
        marker = str(root)
        if marker in seen:
            continue
        seen.add(marker)
        candidate = root / Path(*name.split("/"))
        if candidate.is_dir() and (candidate / "package.json").is_file():
            return candidate.resolve()
    return None


def _node_module_entry(name: str, web_dir: Path) -> Path | None:
    configured = str(os.getenv("NICO_ESLINT_PARSER_ENTRY") or "").strip()
    if configured:
        entry = Path(configured)
        if entry.is_file():
            return entry.resolve()
    module = _node_module_path(name, web_dir)
    if module is None:
        return None
    try:
        package = json.loads((module / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        package = {}
    for relative in (package.get("main"), "dist/index.js", "index.js"):
        if not relative:
            continue
        candidate = module / str(relative)
        if candidate.is_file():
            return candidate.resolve()
    return None


def _eslint_config(workspace: WorkerWorkspace, web_dir: Path) -> tuple[Path | None, str]:
    parser_entry = _node_module_entry("@typescript-eslint/parser", web_dir)
    if parser_entry is None:
        return None, "The NICO standard ESLint profile requires a resolvable @typescript-eslint/parser entry point."
    config = workspace.root / "nico-eslint.config.cjs"
    config.write_text(
        "const tsParser = require(" + json.dumps(str(parser_entry)) + ");\n"
        "module.exports = [\n"
        "  { ignores: ['**/node_modules/**','**/.next/**','**/dist/**','**/build/**'] },\n"
        "  { files: ['**/*.{js,jsx,mjs,cjs}'], languageOptions: { ecmaVersion: 'latest', sourceType: 'module', parserOptions: { ecmaFeatures: { jsx: true } } }, rules: { 'no-constant-condition': 'error', 'no-dupe-keys': 'error', 'no-func-assign': 'error', 'no-import-assign': 'error', 'no-unreachable': 'error', 'valid-typeof': 'error' } },\n"
        "  { files: ['**/*.{ts,tsx}'], languageOptions: { parser: tsParser, parserOptions: { ecmaVersion: 'latest', sourceType: 'module', ecmaFeatures: { jsx: true } } }, rules: { 'no-constant-condition': 'error', 'no-dupe-class-members': 'error', 'no-fallthrough': 'error', 'no-self-assign': 'error', 'no-unreachable': 'error', 'no-undef': 'off', 'no-unused-vars': 'off' } }\n"
        "];\n",
        encoding="utf-8",
    )
    return config, ""


def _run_eslint(spec: ScannerToolSpec, workspace: WorkerWorkspace, runner: Callable[..., WorkerCommandResult], preparation: ProjectCommandPreparation | None) -> dict[str, Any]:
    project_dir = preparation.project_dir if preparation else resolve_node_project_dir(workspace.repo_dir)
    if not _supported_web_files(project_dir):
        return _unavailable(spec, "No supported JavaScript or TypeScript source files were found in the resolved Node project.", source="canonical_eslint")
    binary = shutil.which("eslint") or str(project_dir / "node_modules" / ".bin" / "eslint")
    if not Path(binary).exists() and shutil.which(binary) is None:
        return _unavailable(spec, "eslint is not installed in the worker image.", source="canonical_eslint")
    config, config_reason = _eslint_config(workspace, project_dir)
    if config is None:
        return _unavailable(spec, config_reason, source="canonical_eslint")
    raw = workspace.root / "scanner-raw" / "eslint.json"
    command = (binary, ".", "--ext", ".js,.jsx,.mjs,.cjs,.ts,.tsx", "--format", "json", "--config", str(config), "--no-config-lookup", "--no-error-on-unmatched-pattern")
    env = _node_env(workspace, project_dir)
    env["NODE_OPTIONS"] = os.getenv("NICO_NODE_OPTIONS", "--max-old-space-size=2048")
    result = _run(runner, command, cwd=project_dir, limits=WorkerLimits(spec.timeout_seconds, max(spec.max_output_chars, 16_000_000)), stdout_path=raw, extra_env=env)
    payload, reason = _read_json(raw)
    findings: list[Any] = []
    if isinstance(payload, list):
        for file_result in payload:
            if not isinstance(file_result, dict):
                continue
            for message in file_result.get("messages") or []:
                if isinstance(message, dict):
                    item = dict(message)
                    item.setdefault("filePath", file_result.get("filePath"))
                    findings.append(item)
    capture_complete = isinstance(payload, list)
    blob = _raw_blob(spec.name, raw, "json")
    return _tool_payload(spec, result, findings=findings, capture_complete=capture_complete, reason=reason, raw_blob=blob, execution_source="nico_standard_eslint_profile", workspace=workspace, valid_returncodes={0, 1}, extra={"project_preparation": {"status": preparation.status, "node_modules_ready": preparation.node_modules_ready} if preparation else {}, "generated_config_sha256": _sha256(config.read_bytes())})


def _typescript_findings(text: str) -> list[dict[str, Any]]:
    import re

    pattern = re.compile(r"^(?P<file>.+?)\((?P<line>\d+),(?P<column>\d+)\):\s+error\s+(?P<code>TS\d+):\s+(?P<message>.+)$")
    findings: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match:
            findings.append({"file_path": match.group("file"), "line": int(match.group("line")), "column": int(match.group("column")), "code": match.group("code"), "message": match.group("message"), "severity": "high"})
    return findings


def _run_typescript(spec: ScannerToolSpec, workspace: WorkerWorkspace, runner: Callable[..., WorkerCommandResult], preparation: ProjectCommandPreparation | None) -> dict[str, Any]:
    project_dir = preparation.project_dir if preparation else resolve_node_project_dir(workspace.repo_dir)
    tsconfig = project_dir / "tsconfig.json"
    binary = project_dir / "node_modules" / ".bin" / "tsc"
    if preparation is None or not preparation.node_modules_ready:
        return _unavailable(spec, preparation.reason if preparation else "Project dependencies were not prepared.", source="canonical_typescript")
    if not tsconfig.exists() or not binary.exists():
        return _unavailable(spec, "tsconfig.json or the exact local TypeScript compiler is missing in the resolved Node project.", source="canonical_typescript")
    raw = workspace.root / "scanner-raw" / "typescript.txt"
    env = _node_env(workspace, project_dir)
    env["NODE_OPTIONS"] = os.getenv("NICO_NODE_OPTIONS", "--max-old-space-size=2048")
    command = (str(binary), "--noEmit", "--pretty", "false", "--incremental", "false", "-p", str(tsconfig))
    result = _run(runner, command, cwd=project_dir, limits=WorkerLimits(spec.timeout_seconds, max(spec.max_output_chars, 8_000_000)), stdout_path=raw, extra_env=env)
    text = _read_text(raw)
    findings = _typescript_findings(text)
    capture_complete = result.returncode == 0 or bool(findings)
    reason = "" if capture_complete else redact_text(result.stderr or text or f"TypeScript returned {result.returncode} without parseable diagnostics")[:4000]
    blob = _raw_blob(spec.name, raw, "txt")
    return _tool_payload(spec, result, findings=findings, capture_complete=capture_complete, reason=reason, raw_blob=blob, execution_source="canonical_typescript_project", workspace=workspace, valid_returncodes={0, 1, 2}, extra={"project_preparation": {"status": preparation.status, "node_modules_ready": preparation.node_modules_ready}})


def _history_metadata(workspace: WorkerWorkspace) -> dict[str, Any]:
    def git(*args: str) -> WorkerCommandResult:
        return run_command(("git", *args), cwd=workspace.repo_dir, limits=WorkerLimits(30, 4_000))

    shallow = git("rev-parse", "--is-shallow-repository")
    head = git("rev-parse", "HEAD")
    count = git("rev-list", "--count", "HEAD")
    text = (shallow.stdout or shallow.stderr or "").strip().lower()
    return {
        "full_history_verified": shallow.ok and text == "false",
        "history_depth": "full" if shallow.ok and text == "false" else "shallow_or_unverified",
        "head_sha": (head.stdout or "").strip() if head.ok else "",
        "commit_count": int((count.stdout or "0").strip()) if count.ok and (count.stdout or "").strip().isdigit() else None,
    }


def _run_gitleaks(spec: ScannerToolSpec, workspace: WorkerWorkspace, runner: Callable[..., WorkerCommandResult]) -> dict[str, Any]:
    binary = shutil.which("gitleaks")
    if binary is None:
        return _unavailable(spec, "gitleaks is not installed in the worker image.", source="canonical_gitleaks")
    history = _history_metadata(workspace)
    raw = workspace.root / "scanner-raw" / "gitleaks.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    log = workspace.root / "scanner-output" / "gitleaks.log"
    command = (binary, "detect", "--source", ".", "--report-format", "json", "--report-path", str(raw), "--no-banner", "--redact")
    result = _run(runner, command, cwd=workspace.repo_dir, limits=WorkerLimits(spec.timeout_seconds, max(spec.max_output_chars, 4_000_000)), stdout_path=log)
    if result.returncode == 0 and not raw.exists():
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text("[]\n", encoding="utf-8")
    payload, reason = _read_json(raw)
    findings = payload if isinstance(payload, list) else []
    blob = _raw_blob(spec.name, raw if raw.exists() else log, "json")
    return _tool_payload(spec, result, findings=findings, capture_complete=isinstance(payload, list), reason=reason, raw_blob=blob, execution_source="canonical_gitleaks_full_history", workspace=workspace, valid_returncodes={0, 1}, full_history_verified=bool(history["full_history_verified"]), extra=history)


def _run_trufflehog(spec: ScannerToolSpec, workspace: WorkerWorkspace, runner: Callable[..., WorkerCommandResult]) -> dict[str, Any]:
    binary = shutil.which("trufflehog")
    if binary is None:
        return _unavailable(spec, "trufflehog is not installed in the worker image.", source="canonical_trufflehog")
    history = _history_metadata(workspace)
    raw = workspace.root / "scanner-raw" / "trufflehog.jsonl"
    command = (binary, "git", f"file://{workspace.repo_dir}", "--json", "--no-update", "--no-verification")
    result = _run(runner, command, cwd=workspace.repo_dir, limits=WorkerLimits(spec.timeout_seconds, max(spec.max_output_chars, 8_000_000)), stdout_path=raw)
    findings: list[Any] = []
    invalid = 0
    for line in _read_text(raw).splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            invalid += 1
            continue
        if isinstance(item, dict):
            findings.append(item)
        else:
            invalid += 1
    blob = _raw_blob(spec.name, raw, "jsonl")
    return _tool_payload(spec, result, findings=findings, capture_complete=invalid == 0, reason="" if invalid == 0 else f"{invalid} TruffleHog output line(s) were not valid JSON", raw_blob=blob, execution_source="canonical_trufflehog_full_history", workspace=workspace, valid_returncodes={0, 183}, full_history_verified=bool(history["full_history_verified"]), extra={**history, "invalid_json_lines": invalid})


def _run_problem_tool(spec: ScannerToolSpec, workspace: WorkerWorkspace, runner: Callable[..., WorkerCommandResult], preparation: ProjectCommandPreparation | None) -> dict[str, Any]:
    handlers = {
        "pip-audit": lambda: _run_pip_audit(spec, workspace, runner),
        "npm-audit": lambda: _run_npm_audit(spec, workspace, runner),
        "osv-scanner": lambda: _run_osv(spec, workspace, runner),
        "bandit": lambda: _run_bandit(spec, workspace, runner),
        "semgrep": lambda: _run_semgrep(spec, workspace, runner),
        "eslint": lambda: _run_eslint(spec, workspace, runner, preparation),
        "typescript": lambda: _run_typescript(spec, workspace, runner, preparation),
        "gitleaks": lambda: _run_gitleaks(spec, workspace, runner),
        "trufflehog": lambda: _run_trufflehog(spec, workspace, runner),
    }
    return handlers[spec.name]()


def _git_text(workspace: WorkerWorkspace, *args: str) -> str:
    try:
        result = run_command(("git", *args), cwd=workspace.repo_dir, limits=WorkerLimits(30, 4_000))
    except Exception:
        return ""
    return (result.stdout or "").strip() if result.ok else ""


def _target_repository(workspace: WorkerWorkspace) -> str:
    remote = _git_text(workspace, "config", "--get", "remote.origin.url")
    value = remote.replace("https://github.com/", "").replace("git@github.com:", "").removesuffix(".git").strip("/")
    return value or "unavailable"


def _application_commit_sha() -> str:
    for name in ("NICO_RELEASE_SHA", "RAILWAY_GIT_COMMIT_SHA", "RENDER_GIT_COMMIT", "GITHUB_SHA", "COMMIT_SHA", "SOURCE_VERSION"):
        value = str(os.getenv(name) or "").strip().lower()
        if len(value) == 40 and all(character in "0123456789abcdef" for character in value):
            return value
    return "unavailable"


def _scanner_provenance(workspace: WorkerWorkspace) -> dict[str, Any]:
    target_commit = _git_text(workspace, "rev-parse", "HEAD").lower() or "unavailable"
    application_commit = _application_commit_sha()
    return {
        "target_repository": _target_repository(workspace),
        "target_commit_sha": target_commit,
        "application_commit_sha": application_commit,
        "target_exact_commit_verified": len(target_commit) == 40,
        "application_and_target_commit_equal": (
            application_commit == target_commit
            if application_commit != "unavailable" and target_commit != "unavailable"
            else None
        ),
        "scanner_pipeline_version": VERSION,
        "worker_image_digest": str(os.getenv("NICO_WORKER_IMAGE_DIGEST") or os.getenv("RAILWAY_IMAGE_DIGEST") or "unavailable"),
        "intentional_frozen_sha_scan_supported": True,
    }


def run_canonical_scanner_tools(
    workspace: WorkerWorkspace,
    specs: tuple[ScannerToolSpec, ...] = TOOL_SPECS,
    *,
    runner: Callable[..., WorkerCommandResult] = run_command,
    fallback_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not workspace.repo_dir.is_dir():
        raise ValueError("workspace repo directory must exist before scanner tools run")
    selected = tuple(specs)
    needs_node = any(spec.name in {"eslint", "typescript"} for spec in selected)
    preparation = prepare_project_commands(workspace, runner=runner) if needs_node else None
    tool_results: list[dict[str, Any]] = []
    raw_blobs: dict[str, Any] = {}
    for spec in selected:
        if spec.name in REQUIRED_EVIDENCE_TOOLS:
            payload = _run_problem_tool(spec, workspace, runner, preparation)
        elif fallback_runner is not None:
            payload = fallback_runner(spec, workspace, runner=runner)
        else:
            continue
        blob = payload.pop("_raw_artifact_blob", None) if isinstance(payload, dict) else None
        if isinstance(blob, dict):
            raw_blobs[spec.name] = blob
        tool_results.append(payload)
    tools = {item["tool"]: item for item in tool_results if isinstance(item, dict) and item.get("tool")}
    normalized = normalize_scanner_worker_artifact({"tools": tools})
    required_statuses = {name: str(tools.get(name, {}).get("status") or "missing") for name in REQUIRED_EVIDENCE_TOOLS}
    evidence_complete = all(status == "completed" for status in required_statuses.values())
    provenance = _scanner_provenance(workspace)
    artifact = {
        "artifact_schema": "nico.scanner_worker.v3",
        "scanner_contract_version": "nico.scanner_worker.v3",
        "scanner_pipeline_version": VERSION,
        "tools": tools,
        "normalized": normalized,
        "project_preparation": {
            "status": preparation.status,
            "node_modules_ready": preparation.node_modules_ready,
            "reason": preparation.reason,
            "returncode": preparation.returncode,
            "timed_out": preparation.timed_out,
            "output_truncated": preparation.output_truncated,
        } if preparation else {"status": "not_required", "node_modules_ready": False},
        "required_scanner_statuses": required_statuses,
        "required_scanner_completion": evidence_complete,
        "raw_artifact_capture_complete": all(
            name in raw_blobs
            and raw_blobs[name].get("present") is True
            and bool(raw_blobs[name].get("sha256"))
            for name in REQUIRED_EVIDENCE_TOOLS
        ),
        "raw_artifact_blobs": raw_blobs,
        "deterministic_fingerprints": {name: tools.get(name, {}).get("deterministic_fingerprint") for name in REQUIRED_EVIDENCE_TOOLS},
        "observed_failure_is_not_verified_evidence": True,
        "missing_evidence_is_not_clean": True,
        "scanner_provenance": provenance,
        "target_commit_sha": provenance["target_commit_sha"],
        "target_repository": provenance["target_repository"],
        "application_commit_sha": provenance["application_commit_sha"],
        "provenance_verified": provenance["target_exact_commit_verified"],
    }
    artifact["artifact_hash"] = _sha256(
        json.dumps(
            {key: value for key, value in artifact.items() if key != "raw_artifact_blobs"},
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return artifact


def materialize_raw_artifacts(
    artifact: dict[str, Any],
    destination_root: Path,
    *,
    repository: str,
    commit_sha: str,
    run_id: str,
) -> dict[str, Any]:
    blobs = artifact.pop("raw_artifact_blobs", {})
    destination = destination_root / hashlib.sha256(repository.encode("utf-8")).hexdigest()[:16] / commit_sha / run_id
    destination.mkdir(parents=True, exist_ok=True)
    retained: dict[str, Any] = {}
    errors: list[str] = []
    for tool, blob in sorted(blobs.items() if isinstance(blobs, dict) else []):
        try:
            compressed = bytes.fromhex(str(blob.get("gzip_hex") or ""))
            if _sha256(compressed) != blob.get("gzip_sha256"):
                raise ValueError("compressed artifact checksum mismatch")
            raw = gzip.decompress(compressed)
            if _sha256(raw) != blob.get("sha256"):
                raise ValueError("raw artifact checksum mismatch")
            filename = str(blob.get("filename") or f"{tool}.raw.gz").replace("/", "_")
            path = destination / filename
            path.write_bytes(compressed)
            path.chmod(0o600)
            retained[tool] = {
                "storage_key": str(path.relative_to(destination_root)),
                "filename": filename,
                "sha256": blob.get("sha256"),
                "gzip_sha256": blob.get("gzip_sha256"),
                "raw_format": blob.get("raw_format"),
                "retained_bytes": blob.get("retained_bytes"),
                "gzip_bytes": blob.get("gzip_bytes"),
                "redacted": True,
            }
        except Exception as exc:
            errors.append(f"{tool}: {type(exc).__name__}: {exc}")
    manifest = {
        "schema": "nico.scanner_raw_artifacts.v1",
        "repository": repository,
        "commit_sha": commit_sha,
        "run_id": run_id,
        "pipeline_version": VERSION,
        "artifacts": retained,
        "errors": errors,
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    manifest_path.chmod(0o600)
    complete = not errors and all(name in retained for name in REQUIRED_EVIDENCE_TOOLS)
    tools = artifact.get("tools") if isinstance(artifact.get("tools"), dict) else {}
    for tool in REQUIRED_EVIDENCE_TOOLS:
        payload = tools.get(tool) if isinstance(tools.get(tool), dict) else None
        if payload is None:
            continue
        payload["raw_artifact_retention_complete"] = tool in retained
        if tool in retained:
            payload["raw_artifact"] = retained[tool]
        else:
            payload["verified_for_this_report"] = False
            if payload.get("status") == "completed":
                payload["status"] = "failed"
            reason = "The complete redacted raw scanner artifact was not retained."
            payload["reason"] = reason
            payload["failure_or_unavailable_reason"] = reason
    artifact["raw_artifacts"] = retained
    artifact["raw_artifact_manifest_storage_key"] = str(manifest_path.relative_to(destination_root))
    artifact["raw_artifact_retention_complete"] = complete
    artifact["raw_artifact_retention_errors"] = errors
    artifact["normalized"] = normalize_scanner_worker_artifact({"tools": tools})
    artifact["required_scanner_statuses"] = {
        name: str((tools.get(name) or {}).get("status") or "missing")
        for name in REQUIRED_EVIDENCE_TOOLS
    }
    artifact["required_scanner_completion"] = all(
        status == "completed" for status in artifact["required_scanner_statuses"].values()
    )
    artifact["scanner_evidence_ready"] = bool(artifact.get("required_scanner_completion")) and complete
    return artifact


def install_scanner_evidence_pipeline_v1() -> dict[str, Any]:
    from nico import hosted_scanner_worker
    from nico import scanner_tool_runners

    if getattr(hosted_scanner_worker, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}
    original_tool = scanner_tool_runners.run_scanner_tool

    def final_run_scanner_tools(
        workspace: WorkerWorkspace,
        specs: tuple[ScannerToolSpec, ...] = TOOL_SPECS,
        *,
        runner: Callable[..., WorkerCommandResult] = run_command,
    ) -> dict[str, Any]:
        return run_canonical_scanner_tools(
            workspace,
            specs,
            runner=runner,
            fallback_runner=original_tool,
        )

    hosted_scanner_worker.run_scanner_tools = final_run_scanner_tools
    original_worker = hosted_scanner_worker.run_hosted_scanner_worker

    def hosted_worker_with_retained_raw_artifacts(payload: dict[str, Any]) -> dict[str, Any]:
        artifact = original_worker(payload)
        if not isinstance(artifact, dict) or not isinstance(artifact.get("raw_artifact_blobs"), dict):
            return artifact
        checkout = artifact.get("checkout") if isinstance(artifact.get("checkout"), dict) else {}
        commit_sha = str(checkout.get("commit_sha") or artifact.get("target_commit_sha") or "unknown")
        repository = str(artifact.get("repository") or payload.get("repository") or "unknown/unknown")
        run_id = str(artifact.get("run_id") or "unknown")
        materialize_raw_artifacts(
            artifact,
            Path(DEFAULT_RAW_ROOT),
            repository=repository,
            commit_sha=commit_sha,
            run_id=run_id,
        )
        previous_state = str(artifact.get("worker_execution_state") or "completed")
        artifact["scanner_evidence_gate"] = {
            "status": "passed" if artifact.get("scanner_evidence_ready") else "blocked",
            "required_tools": list(REQUIRED_EVIDENCE_TOOLS),
            "tool_statuses": artifact.get("required_scanner_statuses") or {},
            "raw_artifact_retention_complete": artifact.get("raw_artifact_retention_complete") is True,
            "target_commit_sha": commit_sha,
            "missing_evidence_is_not_clean": True,
        }
        artifact["worker_execution_state_before_evidence_gate"] = previous_state
        artifact["worker_execution_state"] = "completed" if artifact.get("scanner_evidence_ready") else "partial"
        if not artifact.get("scanner_evidence_ready"):
            artifact["human_review_required"] = True
            notes = artifact.setdefault("unavailable_data_notes", [])
            if isinstance(notes, list):
                note = "Scanner evidence is not client-ready until every required scanner completes and every redacted raw artifact is retained."
                if note not in notes:
                    notes.append(note)
        artifact["retention_note"] = (
            "Complete redacted scanner outputs were retained outside the temporary checkout; "
            "the checkout was deleted after artifact generation."
        )
        artifact["artifact_hash"] = _sha256(
            json.dumps(
                {key: value for key, value in artifact.items() if key != "artifact_hash"},
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        return artifact

    hosted_scanner_worker.run_hosted_scanner_worker = hosted_worker_with_retained_raw_artifacts
    # Several legacy runtime modules imported the worker by value. Rebind every
    # loaded NICO module to the same final worker so no stale execution path can
    # bypass complete capture or durable raw-artifact retention.
    for module in tuple(sys.modules.values()):
        name = str(getattr(module, "__name__", ""))
        if name.startswith("nico.") and hasattr(module, "run_hosted_scanner_worker"):
            setattr(module, "run_hosted_scanner_worker", hosted_worker_with_retained_raw_artifacts)

    setattr(hosted_scanner_worker, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "version": VERSION,
        "required_tools": list(REQUIRED_EVIDENCE_TOOLS),
        "full_output_capture": True,
        "durable_redacted_raw_artifacts": True,
        "frozen_sha_determinism_supported": True,
        "public_scanner_tool_api_unchanged": True,
    }


__all__ = [
    "VERSION",
    "REQUIRED_EVIDENCE_TOOLS",
    "install_scanner_evidence_pipeline_v1",
    "materialize_raw_artifacts",
    "run_canonical_scanner_tools",
]
