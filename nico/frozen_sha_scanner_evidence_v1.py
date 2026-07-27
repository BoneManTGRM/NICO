from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import uuid4

from nico import scanner_tool_runners as legacy_runners
from nico import scanner_worker as base
from nico.storage import STORE
from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace, run_command

VERSION = "nico.frozen_sha_scanner_evidence.v1"
FROZEN_QUALIFICATION_SHA = "8ed545766fb4c5054798a02ea17ece0fe7bcab64"
REQUIRED_TOOLS = (
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
CRITICAL_REPEATABILITY_TOOLS = (
    "bandit",
    "eslint",
    "typescript",
    "gitleaks",
    "osv-scanner",
)
MAX_RETAINED_OUTPUT_BYTES = int(
    os.getenv("NICO_SCANNER_MAX_RETAINED_OUTPUT_BYTES", str(256 * 1024 * 1024))
)
NODE_HEAP_MB = int(os.getenv("NICO_SCANNER_NODE_HEAP_MB", "4096"))
_COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_VOLATILE_KEYS = {
    "created_at",
    "updated_at",
    "completed_at",
    "duration_seconds",
    "stdout_bytes",
    "stderr_bytes",
    "artifact_path",
    "stderr_path",
    "manifest_path",
}
_SECRET_KEYS = {
    "raw",
    "rawv2",
    "secret",
    "token",
    "password",
    "credential",
    "privatekey",
    "private_key",
}


@dataclass(frozen=True)
class StrictToolSpec:
    name: str
    category: str
    timeout_seconds: int
    max_preview_chars: int
    valid_returncodes: frozenset[int]
    requires_node_preparation: bool = False
    requires_full_history: bool = False


TOOL_SPECS: dict[str, StrictToolSpec] = {
    "pip-audit": StrictToolSpec("pip-audit", "dependency", 300, 500_000, frozenset({0, 1})),
    "npm-audit": StrictToolSpec("npm-audit", "dependency", 300, 1_000_000, frozenset({0, 1})),
    "osv-scanner": StrictToolSpec("osv-scanner", "dependency", 420, 4_000_000, frozenset({0, 1})),
    "bandit": StrictToolSpec("bandit", "static", 420, 4_000_000, frozenset({0, 1})),
    "semgrep": StrictToolSpec("semgrep", "static", 600, 8_000_000, frozenset({0, 1})),
    "eslint": StrictToolSpec("eslint", "static", 420, 8_000_000, frozenset({0, 1}), True),
    "typescript": StrictToolSpec("typescript", "static", 420, 4_000_000, frozenset({0, 2}), True),
    "gitleaks": StrictToolSpec("gitleaks", "secret", 900, 4_000_000, frozenset({0, 1}), False, True),
    "trufflehog": StrictToolSpec("trufflehog", "secret", 900, 8_000_000, frozenset({0, 183}), False, True),
}


def _safe_text(value: Any, limit: int = 4000) -> str:
    text = legacy_runners.redact_text(str(value or ""))
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_root(scan_id: str) -> tuple[Path, str]:
    configured = os.getenv("NICO_SCANNER_ARTIFACT_ROOT", "").strip()
    if configured:
        root = Path(configured).expanduser().resolve()
        retention_class = "configured_durable_root"
    else:
        data_root = Path("/data")
        if data_root.exists() and os.access(data_root, os.W_OK):
            root = (data_root / "scanner-evidence").resolve()
            retention_class = "service_data_root"
        else:
            root = (Path.cwd() / "artifacts" / "scanner-evidence").resolve()
            retention_class = "local_artifact_root"
    destination = root / scan_id
    destination.mkdir(parents=True, exist_ok=True)
    return destination, retention_class


def _git(
    command: list[str],
    *,
    cwd: Path | None,
    env: dict[str, str],
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        shell=False,
        check=False,
        start_new_session=True,
    )


def clone_repository_at_exact_history(
    repository: str,
    commit_sha: str,
    workspace: Path,
    env: dict[str, str],
) -> tuple[Path | None, str, dict[str, Any], list[str]]:
    """Fetch one exact commit and every ancestor reachable from that commit.

    No branch tip is checked out and no shallow boundary is allowed. This gives
    history-aware scanners the complete history that existed at the frozen SHA,
    without including later commits.
    """

    expected = str(commit_sha or "").strip().lower()
    if shutil.which("git") is None:
        return None, "", {}, ["git is unavailable in the scanner worker image."]
    if not _COMMIT_SHA_RE.fullmatch(expected):
        return None, "", {}, ["A full 40-character immutable commit SHA is required."]

    repo_path = workspace / "repo"
    repo_path.mkdir(parents=True, exist_ok=False)
    commands: tuple[tuple[list[str], Path | None], ...] = (
        (["git", "init", "--quiet", str(repo_path)], None),
        (["git", "remote", "add", "origin", base.safe_repo_url(repository)], repo_path),
        (
            [
                "git",
                "-c",
                "protocol.version=2",
                "fetch",
                "--filter=blob:none",
                "--no-tags",
                "origin",
                expected,
            ],
            repo_path,
        ),
        (["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"], repo_path),
    )
    for command, cwd in commands:
        completed = _git(command, cwd=cwd, env=env)
        if completed.returncode != 0:
            preview = _safe_text((completed.stdout or "") + "\n" + (completed.stderr or ""), 1200)
            shutil.rmtree(repo_path, ignore_errors=True)
            return None, "", {}, [f"Exact-history checkout failed ({' '.join(command[:3])}): {preview}"]

    head = _git(["git", "rev-parse", "HEAD"], cwd=repo_path, env=env, timeout=30)
    shallow = _git(["git", "rev-parse", "--is-shallow-repository"], cwd=repo_path, env=env, timeout=30)
    count = _git(["git", "rev-list", "--count", "HEAD"], cwd=repo_path, env=env, timeout=180)
    actual = (head.stdout or "").strip().lower()
    try:
        commit_count = max(0, int((count.stdout or "0").strip()))
    except ValueError:
        commit_count = 0
    is_shallow = (shallow.stdout or "").strip().lower() != "false"
    history_verified = bool(
        head.returncode == 0
        and shallow.returncode == 0
        and count.returncode == 0
        and actual == expected
        and not is_shallow
        and commit_count >= 1
    )
    history = {
        "full_history_verified": history_verified,
        "history_head_sha": actual,
        "history_commit_count": commit_count,
        "shallow_repository": is_shallow,
        "history_scope": "all ancestors reachable from the exact immutable commit",
    }
    if not history_verified:
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, actual, history, [
            "The exact checkout was shallow, incomplete, or did not match the requested SHA; history-aware scanning was blocked."
        ]

    working_tree_bytes = 0
    for path in repo_path.rglob("*"):
        if not path.is_file() or ".git" in path.relative_to(repo_path).parts:
            continue
        try:
            working_tree_bytes += path.stat().st_size
        except OSError:
            continue
    history["working_tree_bytes"] = working_tree_bytes
    if working_tree_bytes > base.MAX_REPO_BYTES:
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, actual, history, [
            f"Repository working tree exceeds the bounded scanner limit: {working_tree_bytes} > {base.MAX_REPO_BYTES} bytes."
        ]
    return repo_path, actual, history, []


def _node_environment(workspace: WorkerWorkspace, web_dir: Path) -> dict[str, str]:
    global_root = ""
    try:
        completed = subprocess.run(
            ["npm", "root", "-g"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if completed.returncode == 0:
            global_root = (completed.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        global_root = ""
    paths = [str(web_dir / "node_modules")]
    configured = os.getenv("NODE_PATH", "").strip()
    if configured:
        paths.append(configured)
    if global_root:
        paths.append(global_root)
    return {
        "CI": "true",
        "NO_COLOR": "1",
        "FORCE_COLOR": "0",
        "NODE_PATH": os.pathsep.join(dict.fromkeys(path for path in paths if path)),
        "NPM_CONFIG_CACHE": str(workspace.root / "npm-cache"),
        "npm_config_cache": str(workspace.root / "npm-cache"),
        "NODE_OPTIONS": f"--max-old-space-size={NODE_HEAP_MB}",
    }


def _retain_text(
    source: Path | None,
    destination: Path,
    *,
    fallback: str = "",
    secret_output: bool = False,
) -> dict[str, Any]:
    if source is not None and source.is_file():
        raw = source.read_bytes()
    else:
        raw = fallback.encode("utf-8", errors="replace")
    if len(raw) > MAX_RETAINED_OUTPUT_BYTES:
        raise RuntimeError(
            f"scanner artifact exceeded the retained-output boundary of {MAX_RETAINED_OUTPUT_BYTES} bytes"
        )
    redacted = False
    if secret_output:
        text = raw.decode("utf-8", errors="replace")
        sanitized = _sanitize_secret_payload_text(text)
        raw = sanitized.encode("utf-8")
        redacted = sanitized != text
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    return {
        "path": str(destination),
        "sha256": _sha256_bytes(raw),
        "size_bytes": len(raw),
        "secret_redaction_applied": redacted,
    }


def _sanitize_secret_value(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).replace("-", "").replace("_", "").lower()
            output[str(key)] = "[REDACTED]" if normalized in _SECRET_KEYS else _sanitize_secret_value(item)
        return output
    if isinstance(value, list):
        return [_sanitize_secret_value(item) for item in value]
    if isinstance(value, str):
        return legacy_runners.redact_text(value)
    return value


def _sanitize_secret_payload_text(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        lines: list[str] = []
        all_json = True
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                lines.append(json.dumps(_sanitize_secret_value(json.loads(line)), sort_keys=True))
            except json.JSONDecodeError:
                all_json = False
                break
        if all_json:
            return "\n".join(lines) + ("\n" if lines else "")
        return legacy_runners.redact_text(text)
    return json.dumps(_sanitize_secret_value(value), indent=2, sort_keys=True) + "\n"


def _write_eslint_config(workspace: WorkerWorkspace) -> Path:
    destination = workspace.root / "scanner-eslint.config.cjs"
    destination.write_text(
        """const js = require('@eslint/js');
const tsParser = require('@typescript-eslint/parser');
const tsPlugin = require('@typescript-eslint/eslint-plugin');

module.exports = [
  { ignores: ['**/.git/**', '**/node_modules/**', '**/.next/**', '**/dist/**', '**/build/**', '**/.venv/**', '**/venv/**'] },
  { files: ['**/*.{js,mjs,cjs,jsx}'], ...js.configs.recommended },
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: { ecmaVersion: 'latest', sourceType: 'module', ecmaFeatures: { jsx: true } },
    },
    plugins: { '@typescript-eslint': tsPlugin },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      'no-undef': 'off',
      'no-unused-vars': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
];
""",
        encoding="utf-8",
    )
    return destination


def _prepare_node_project(
    workspace: WorkerWorkspace,
    artifact_dir: Path,
) -> dict[str, Any]:
    web_dir = workspace.repo_dir / "apps" / "web"
    if not (web_dir / "package.json").is_file() or not (web_dir / "package-lock.json").is_file():
        return {
            "status": "unavailable",
            "node_modules_ready": False,
            "reason": "apps/web/package.json and package-lock.json are required for deterministic TypeScript evidence.",
        }
    npm = shutil.which("npm")
    if not npm:
        return {"status": "unavailable", "node_modules_ready": False, "reason": "npm is unavailable."}
    output = workspace.root / "scanner-output" / "npm-ci.stdout"
    result = run_command(
        (npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund", "--prefer-offline"),
        cwd=web_dir,
        limits=WorkerLimits(timeout_seconds=600, max_output_chars=500_000),
        extra_env=_node_environment(workspace, web_dir),
        stdout_path=output,
    )
    retained = _retain_text(output, artifact_dir / "preparation" / "npm-ci.stdout")
    stderr = _retain_text(None, artifact_dir / "preparation" / "npm-ci.stderr", fallback=result.stderr)
    ready = bool(
        result.returncode == 0
        and not result.timed_out
        and (web_dir / "node_modules").is_dir()
        and (web_dir / "node_modules" / ".bin" / "tsc").is_file()
    )
    return {
        "status": "completed" if ready else "failed",
        "node_modules_ready": ready,
        "returncode": result.returncode,
        "timed_out": result.timed_out,
        "reason": "" if ready else _safe_text(result.stderr or result.stdout or "npm ci failed", 2000),
        "artifacts": {"stdout": retained, "stderr": stderr},
    }


def _tool_version(command: str, args: tuple[str, ...] = ("--version",)) -> str:
    executable = shutil.which(command) if "/" not in command else command
    if not executable:
        return "unavailable"
    try:
        completed = subprocess.run(
            [str(executable), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    return _safe_text((completed.stdout or completed.stderr or "").strip(), 300) or "unknown"


def _command_for(
    spec: StrictToolSpec,
    workspace: WorkerWorkspace,
    preparation: dict[str, Any],
) -> tuple[tuple[str, ...] | None, Path, dict[str, str], str]:
    repo = workspace.repo_dir
    web = repo / "apps" / "web"
    env = {"CI": "true", "NO_COLOR": "1", "FORCE_COLOR": "0"}
    if spec.name == "pip-audit":
        requirements = repo / "requirements.txt"
        if not requirements.is_file():
            return None, repo, env, "requirements.txt is unavailable."
        executable = shutil.which("pip-audit")
        return ((executable, "-r", str(requirements), "-f", "json") if executable else None, repo, env, "pip-audit is unavailable.")
    if spec.name == "npm-audit":
        if not (web / "package-lock.json").is_file():
            return None, web, env, "apps/web/package-lock.json is unavailable."
        executable = shutil.which("npm")
        return ((executable, "audit", "--json", "--package-lock-only", "--ignore-scripts") if executable else None, web, _node_environment(workspace, web), "npm is unavailable.")
    if spec.name == "osv-scanner":
        executable = shutil.which("osv-scanner")
        return ((executable, "scan", "source", "-r", ".", "--format", "json") if executable else None, repo, env, "osv-scanner is unavailable; partial API fallback is not accepted.")
    if spec.name == "bandit":
        executable = shutil.which("bandit")
        command = (
            executable,
            "-r",
            ".",
            "-f",
            "json",
            "-x",
            ".git,node_modules,.next,dist,build,.venv,venv",
        ) if executable else None
        return command, repo, env, "bandit is unavailable."
    if spec.name == "semgrep":
        executable = shutil.which("semgrep")
        command = (
            executable,
            "scan",
            "--config",
            "auto",
            "--json",
            "--jobs",
            "1",
            "--max-memory",
            "2048",
            "--timeout",
            "45",
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
        ) if executable else None
        return command, repo, {**env, "SEMGREP_SEND_METRICS": "off", "SEMGREP_ENABLE_VERSION_CHECK": "0"}, "semgrep is unavailable."
    if spec.name == "eslint":
        executable = shutil.which("eslint")
        config = _write_eslint_config(workspace)
        command = (
            executable,
            ".",
            "--config",
            str(config),
            "--format",
            "json",
            "--no-error-on-unmatched-pattern",
        ) if executable else None
        return command, web, _node_environment(workspace, web), "The scanner-owned ESLint runtime is unavailable."
    if spec.name == "typescript":
        if preparation.get("node_modules_ready") is not True:
            return None, web, _node_environment(workspace, web), str(preparation.get("reason") or "Node preparation failed.")
        local = web / "node_modules" / ".bin" / "tsc"
        executable = str(local) if local.is_file() else shutil.which("tsc")
        tsconfig = web / "tsconfig.json"
        if not tsconfig.is_file():
            return None, web, _node_environment(workspace, web), "apps/web/tsconfig.json is unavailable."
        command = (
            executable,
            "--noEmit",
            "--pretty",
            "false",
            "--incremental",
            "false",
            "-p",
            str(tsconfig),
        ) if executable else None
        return command, web, _node_environment(workspace, web), "TypeScript is unavailable."
    if spec.name == "gitleaks":
        executable = shutil.which("gitleaks")
        command = (
            executable,
            "detect",
            "--source",
            ".",
            "--report-format",
            "json",
            "--no-banner",
            "--redact",
        ) if executable else None
        return command, repo, env, "gitleaks is unavailable."
    if spec.name == "trufflehog":
        executable = shutil.which("trufflehog")
        command = (
            executable,
            "git",
            f"file://{repo}",
            "--json",
            "--no-update",
            "--no-verification",
        ) if executable else None
        return command, repo, env, "trufflehog is unavailable."
    return None, repo, env, f"Unsupported scanner: {spec.name}"


def _recursive_vulnerabilities(value: Any) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key in ("vulnerabilities", "vulns"):
            items = value.get(key)
            if isinstance(items, list):
                findings.extend(item for item in items if isinstance(item, dict))
        for item in value.values():
            findings.extend(_recursive_vulnerabilities(item))
    elif isinstance(value, list):
        for item in value:
            findings.extend(_recursive_vulnerabilities(item))
    return findings


def _parse_tool_output(
    tool: str,
    result: WorkerCommandResult,
    output_path: Path,
) -> tuple[list[dict[str, Any]], bool, str]:
    try:
        size = output_path.stat().st_size
    except OSError:
        size = 0
    if size > MAX_RETAINED_OUTPUT_BYTES:
        return [], False, f"{tool} output exceeded {MAX_RETAINED_OUTPUT_BYTES} retained bytes"
    try:
        text = output_path.read_text(encoding="utf-8", errors="replace") if output_path.is_file() else ""
    except OSError as exc:
        return [], False, f"{tool} output could not be read: {type(exc).__name__}"
    stripped = text.strip()
    if tool == "typescript":
        pattern = re.compile(
            r"^(?P<file>.+?)\((?P<line>\d+),(?P<column>\d+)\):\s+error\s+(?P<code>TS\d+):\s+(?P<message>.+)$"
        )
        findings = []
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
                        "severity": "error",
                    }
                )
        if result.returncode == 0:
            return findings, True, ""
        if findings:
            return findings, True, ""
        return [], False, _safe_text(result.stderr or text or "TypeScript returned no parseable diagnostics")
    if tool == "trufflehog":
        findings: list[dict[str, Any]] = []
        invalid = 0
        for line in text.splitlines():
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
        return findings, invalid == 0, "" if invalid == 0 else f"{invalid} TruffleHog lines were not valid JSON"
    if not stripped:
        return ([], True, "") if result.returncode in TOOL_SPECS[tool].valid_returncodes else ([], False, _safe_text(result.stderr))
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return [], False, _safe_text(result.stderr or "Scanner output was not valid JSON")
    if tool == "pip-audit" and isinstance(payload, dict):
        return [item for item in legacy_runners._pip_audit_findings(payload) if isinstance(item, dict)], True, ""
    if tool == "npm-audit" and isinstance(payload, dict):
        return [item for item in legacy_runners._npm_audit_findings(payload) if isinstance(item, dict)], True, ""
    if tool == "osv-scanner" and isinstance(payload, dict):
        return _recursive_vulnerabilities(payload), isinstance(payload.get("results"), list), "" if isinstance(payload.get("results"), list) else "OSV output did not contain a complete results array"
    if tool == "bandit" and isinstance(payload, dict):
        errors = payload.get("errors")
        complete = isinstance(payload.get("results"), list) and (not isinstance(errors, list) or not errors)
        reason = "" if complete else "Bandit reported collection errors or omitted its results array"
        return [item for item in payload.get("results") or [] if isinstance(item, dict)], complete, reason
    if tool == "semgrep" and isinstance(payload, dict):
        errors = payload.get("errors")
        complete = isinstance(payload.get("results"), list) and (not isinstance(errors, list) or not errors)
        return [item for item in payload.get("results") or [] if isinstance(item, dict)], complete, "" if complete else "Semgrep reported execution errors"
    if tool == "eslint" and isinstance(payload, list):
        findings = []
        for file_result in payload:
            if not isinstance(file_result, dict):
                continue
            for message in file_result.get("messages") or []:
                if isinstance(message, dict):
                    item = dict(message)
                    item.setdefault("filePath", file_result.get("filePath"))
                    findings.append(item)
        return findings, True, ""
    if tool == "gitleaks" and isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)], True, ""
    return [], False, f"{tool} emitted an unsupported JSON schema"


def _normalized_tool_version(tool: str, command: tuple[str, ...]) -> str:
    executable = command[0]
    if tool == "gitleaks":
        return _tool_version(executable, ("version",))
    return _tool_version(executable)


def _run_tool(
    spec: StrictToolSpec,
    workspace: WorkerWorkspace,
    preparation: dict[str, Any],
    history: dict[str, Any],
    artifact_dir: Path,
    pass_number: int,
) -> dict[str, Any]:
    command, cwd, env, unavailable_reason = _command_for(spec, workspace, preparation)
    base_payload: dict[str, Any] = {
        "tool": spec.name,
        "category": spec.category,
        "pass": pass_number,
        "required": True,
        "repeatability_critical": spec.name in CRITICAL_REPEATABILITY_TOOLS,
        "findings": [],
        "current_run": True,
        "verified_for_this_report": False,
        "output_capture_complete": False,
        "full_history_verified": history.get("full_history_verified") is True if spec.requires_full_history else None,
    }
    if command is None:
        return {**base_payload, "status": "unavailable", "reason": unavailable_reason}
    output_path = workspace.root / "scanner-output" / f"pass-{pass_number}" / f"{spec.name}.stdout"
    result = run_command(
        command,
        cwd=cwd,
        limits=WorkerLimits(
            timeout_seconds=spec.timeout_seconds,
            max_output_chars=spec.max_preview_chars,
        ),
        extra_env=env,
        stdout_path=output_path,
    )
    findings, capture_complete, capture_reason = _parse_tool_output(spec.name, result, output_path)
    try:
        retained_stdout = _retain_text(
            output_path,
            artifact_dir / f"pass-{pass_number}" / f"{spec.name}.stdout",
            secret_output=spec.category == "secret",
        )
        retained_stderr = _retain_text(
            None,
            artifact_dir / f"pass-{pass_number}" / f"{spec.name}.stderr",
            fallback=result.stderr,
            secret_output=spec.category == "secret",
        )
        retained = True
        retention_reason = ""
    except Exception as exc:
        retained_stdout = {}
        retained_stderr = {}
        retained = False
        retention_reason = f"artifact retention failed: {type(exc).__name__}"
    valid_returncode = result.returncode in spec.valid_returncodes
    history_complete = not spec.requires_full_history or history.get("full_history_verified") is True
    if result.timed_out:
        status = "timeout"
        reason = f"{spec.name} exceeded its {spec.timeout_seconds}-second timeout"
    elif not valid_returncode:
        status = "failed"
        reason = _safe_text(result.stderr or result.stdout or f"unexpected return code {result.returncode}")
    elif not capture_complete:
        status = "failed"
        reason = capture_reason or "scanner output was incomplete"
    elif not history_complete:
        status = "failed"
        reason = "full exact-SHA history was not verified"
    elif not retained:
        status = "failed"
        reason = retention_reason
    else:
        status = "completed"
        reason = ""
    return legacy_runners.redact_payload(
        {
            **base_payload,
            "status": status,
            "reason": reason,
            "returncode": result.returncode,
            "returncode_valid": valid_returncode,
            "timed_out": result.timed_out,
            "output_preview_truncated": result.output_truncated,
            "output_capture_complete": capture_complete,
            "stdout_bytes": result.stdout_bytes,
            "stderr_bytes": result.stderr_bytes,
            "tool_version": _normalized_tool_version(spec.name, command),
            "command_intent": " ".join(Path(part).name if index == 0 else part for index, part in enumerate(command[:8])),
            "findings": findings,
            "findings_count": len(findings),
            "verified_for_this_report": status == "completed",
            "full_history_verified": history.get("full_history_verified") is True if spec.requires_full_history else None,
            "raw_artifacts": {"stdout": retained_stdout, "stderr": retained_stderr},
        }
    )


def _canonical(value: Any, repo_path: Path) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonical(item, repo_path)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _VOLATILE_KEYS and str(key) != "raw_artifacts"
        }
    if isinstance(value, list):
        items = [_canonical(item, repo_path) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    if isinstance(value, str):
        return value.replace(str(repo_path), "<repo>").replace("\\", "/")
    return value


def _fingerprint(results: Iterable[dict[str, Any]], repo_path: Path) -> str:
    payload = [
        _canonical(
            {
                "tool": item.get("tool"),
                "status": item.get("status"),
                "returncode": item.get("returncode"),
                "tool_version": item.get("tool_version"),
                "output_capture_complete": item.get("output_capture_complete"),
                "full_history_verified": item.get("full_history_verified"),
                "findings": item.get("findings") or [],
                "reason": item.get("reason") or "",
            },
            repo_path,
        )
        for item in results
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return _sha256_bytes(encoded)


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_tool: dict[str, dict[str, Any]] = {}
    for item in results:
        by_tool[str(item.get("tool") or "unknown")] = {
            "status": item.get("status"),
            "findings_count": int(item.get("findings_count") or 0),
            "output_capture_complete": item.get("output_capture_complete") is True,
            "verified_for_this_report": item.get("verified_for_this_report") is True,
            "tool_version": item.get("tool_version"),
        }
    return {
        "raw_total": sum(int(item.get("findings_count") or 0) for item in results),
        "material_total": 0,
        "review_required_total": sum(int(item.get("findings_count") or 0) for item in results),
        "excluded_test_only_total": 0,
        "by_tool": by_tool,
        "truth_model": "scanner execution completion is separate from human finding disposition",
    }


def _artifact_manifest(
    artifact_dir: Path,
    *,
    scan_id: str,
    repository: str,
    commit_sha: str,
    history: dict[str, Any],
    passes: list[dict[str, Any]],
) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    for path in sorted(artifact_dir.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        artifacts.append(
            {
                "path": str(path.relative_to(artifact_dir)),
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    manifest = {
        "artifact_schema": "nico.scanner_evidence_manifest.v1",
        "scan_id": scan_id,
        "repository": repository,
        "commit_sha": commit_sha,
        "history": history,
        "passes": passes,
        "artifacts": artifacts,
    }
    manifest_path = artifact_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    manifest["manifest_sha256"] = _sha256_file(manifest_path)
    return manifest


def _new_job(payload: dict[str, Any]) -> dict[str, Any]:
    repository = str(payload.get("repository") or "").strip()
    commit_sha = str(payload.get("snapshot_commit_sha") or "").strip().lower()
    snapshot_id = str(payload.get("snapshot_id") or "").strip()
    if not payload.get("authorized"):
        return {"status": "blocked", "error": "Explicit authorization is required."}
    if not repository:
        return {"status": "blocked", "error": "repository is required."}
    if not snapshot_id or not _COMMIT_SHA_RE.fullmatch(commit_sha):
        return {"status": "blocked", "error": "snapshot_id and a full immutable commit SHA are required."}
    if not str(payload.get("authorized_by") or "").strip():
        return {"status": "blocked", "error": "authorized_by is required."}
    if not str(payload.get("authorization_scope") or "").strip():
        return {"status": "blocked", "error": "authorization_scope is required."}
    try:
        base.safe_repo_url(repository)
    except ValueError as exc:
        return {"status": "blocked", "error": str(exc)}
    scan_id = f"scan_strict_{uuid4().hex[:16]}"
    job = {
        "scan_id": scan_id,
        "run_id": payload.get("run_id") or "",
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "repository": repository,
        "snapshot_id": snapshot_id,
        "snapshot_commit_sha": commit_sha,
        "actual_commit_sha": "",
        "snapshot_match": False,
        "status": "queued",
        "current_stage": "queued",
        "progress_percent": 2,
        "created_at": base.now_iso(),
        "updated_at": base.now_iso(),
        "authorized_by": payload.get("authorized_by"),
        "authorization_scope": payload.get("authorization_scope"),
        "tools_requested": list(REQUIRED_TOOLS),
        "required_tools": list(REQUIRED_TOOLS),
        "repeatability_tools": list(CRITICAL_REPEATABILITY_TOOLS),
        "repeatability_passes_required": 2,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    base.SCAN_JOBS[scan_id] = job
    STORE.put("scanner_runs", scan_id, job)
    return job


def _execute_scan(scan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    customer_id = str(payload.get("customer_id") or "default_customer")
    project_id = str(payload.get("project_id") or "default_project")
    job = base.SCAN_JOBS[scan_id]
    job.update({"status": "running", "current_stage": "exact_history_checkout", "progress_percent": 5, "updated_at": base.now_iso()})
    STORE.put("scanner_runs", scan_id, job)
    artifact_dir, retention_class = _artifact_root(scan_id)
    started = time.monotonic()
    notes: list[str] = []
    actual_sha = ""
    history: dict[str, Any] = {}
    pass_records: list[dict[str, Any]] = []
    all_results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="nico-strict-scan-") as temp_name:
        workspace = WorkerWorkspace(root=Path(temp_name))
        env = base.clean_env(workspace.root)
        repo_path, actual_sha, history, clone_notes = clone_repository_at_exact_history(
            str(payload.get("repository") or ""),
            str(payload.get("snapshot_commit_sha") or ""),
            workspace.root,
            env,
        )
        notes.extend(clone_notes)
        if repo_path is not None:
            job.update({"current_stage": "deterministic_project_preparation", "progress_percent": 12, "updated_at": base.now_iso()})
            STORE.put("scanner_runs", scan_id, job)
            preparation = _prepare_node_project(workspace, artifact_dir)
            if preparation.get("status") != "completed":
                notes.append(str(preparation.get("reason") or "Node project preparation failed."))
            pass_tools = (REQUIRED_TOOLS, CRITICAL_REPEATABILITY_TOOLS)
            for pass_index, tool_names in enumerate(pass_tools, start=1):
                results: list[dict[str, Any]] = []
                for tool_index, tool_name in enumerate(tool_names, start=1):
                    job.update(
                        {
                            "current_stage": f"scanner_pass_{pass_index}",
                            "active_tool": tool_name,
                            "progress_percent": min(
                                95,
                                15
                                + round(
                                    ((pass_index - 1) + tool_index / max(1, len(tool_names)))
                                    / len(pass_tools)
                                    * 78
                                ),
                            ),
                            "updated_at": base.now_iso(),
                        }
                    )
                    STORE.put("scanner_runs", scan_id, job)
                    try:
                        result = _run_tool(
                            TOOL_SPECS[tool_name],
                            workspace,
                            preparation,
                            history,
                            artifact_dir,
                            pass_index,
                        )
                    except Exception as exc:  # pragma: no cover - defensive scanner isolation
                        result = {
                            "tool": tool_name,
                            "category": TOOL_SPECS[tool_name].category,
                            "pass": pass_index,
                            "status": "failed",
                            "reason": f"{tool_name} failed safely inside the strict worker: {type(exc).__name__}",
                            "findings": [],
                            "findings_count": 0,
                            "output_capture_complete": False,
                            "verified_for_this_report": False,
                            "current_run": True,
                        }
                    results.append(result)
                    all_results.append(result)
                fingerprint = _fingerprint(results, repo_path)
                pass_records.append(
                    {
                        "pass": pass_index,
                        "tools": list(tool_names),
                        "fingerprint": fingerprint,
                        "all_completed": all(item.get("status") == "completed" for item in results),
                        "tool_statuses": {str(item.get("tool")): str(item.get("status")) for item in results},
                    }
                )

    first_results = [item for item in all_results if int(item.get("pass") or 0) == 1]
    second_results = [item for item in all_results if int(item.get("pass") or 0) == 2]
    first_by_tool = {str(item.get("tool")): item for item in first_results}
    second_by_tool = {str(item.get("tool")): item for item in second_results}
    required_complete = bool(
        len(first_by_tool) == len(REQUIRED_TOOLS)
        and all(first_by_tool.get(name, {}).get("status") == "completed" for name in REQUIRED_TOOLS)
    )
    critical_complete_twice = bool(
        all(first_by_tool.get(name, {}).get("status") == "completed" for name in CRITICAL_REPEATABILITY_TOOLS)
        and all(second_by_tool.get(name, {}).get("status") == "completed" for name in CRITICAL_REPEATABILITY_TOOLS)
    )
    first_critical_fingerprint = _fingerprint(
        [first_by_tool[name] for name in CRITICAL_REPEATABILITY_TOOLS if name in first_by_tool],
        Path("/tmp/repo-placeholder"),
    )
    second_critical_fingerprint = _fingerprint(
        [second_by_tool[name] for name in CRITICAL_REPEATABILITY_TOOLS if name in second_by_tool],
        Path("/tmp/repo-placeholder"),
    )
    repeatability_verified = bool(
        critical_complete_twice
        and first_critical_fingerprint == second_critical_fingerprint
        and len(first_critical_fingerprint) == 64
    )
    snapshot_match = bool(actual_sha) and actual_sha == str(payload.get("snapshot_commit_sha") or "").lower()
    clean = bool(snapshot_match and history.get("full_history_verified") is True and required_complete and repeatability_verified)
    failed = sorted({str(item.get("tool")) for item in all_results if item.get("status") == "failed"})
    unavailable = sorted({str(item.get("tool")) for item in all_results if item.get("status") == "unavailable"})
    timed_out = sorted({str(item.get("tool")) for item in all_results if item.get("status") == "timeout"})
    completed = sorted({str(item.get("tool")) for item in first_results if item.get("status") == "completed"})
    first_summary = _summary(first_results)
    manifest = _artifact_manifest(
        artifact_dir,
        scan_id=scan_id,
        repository=str(payload.get("repository") or ""),
        commit_sha=str(payload.get("snapshot_commit_sha") or ""),
        history=history,
        passes=pass_records,
    )
    if not required_complete:
        notes.append("One or more required scanners did not complete with fully retained output.")
    if not repeatability_verified:
        notes.append("The five critical scanner results did not complete twice with deterministic equivalence.")
    job.update(
        {
            "status": "complete" if clean else "blocked",
            "current_stage": "complete" if clean else "scanner_evidence_blocked",
            "progress_percent": 100,
            "updated_at": base.now_iso(),
            "completed_at": base.now_iso(),
            "duration_seconds": round(time.monotonic() - started, 2),
            "actual_commit_sha": actual_sha,
            "snapshot_match": snapshot_match,
            "history_evidence": history,
            "tools_run": completed,
            "unavailable_tools": unavailable,
            "failed_tools": failed,
            "timed_out_tools": timed_out,
            "required_tools_complete": required_complete,
            "scanner_results": first_results,
            "scanner_repeatability_results": second_results,
            "scanner_passes": pass_records,
            "repeatability": {
                "status": "verified" if repeatability_verified else "blocked",
                "passes_required": 2,
                "critical_tools": list(CRITICAL_REPEATABILITY_TOOLS),
                "first_fingerprint": first_critical_fingerprint,
                "second_fingerprint": second_critical_fingerprint,
                "equivalent": first_critical_fingerprint == second_critical_fingerprint,
            },
            "finding_summary": first_summary,
            "finding_count": first_summary["raw_total"],
            "material_finding_count": first_summary["material_total"],
            "review_required_finding_count": first_summary["review_required_total"],
            "excluded_test_only_finding_count": first_summary["excluded_test_only_total"],
            "artifact_retention": {
                "class": retention_class,
                "root": str(artifact_dir),
                "manifest_path": manifest.get("manifest_path"),
                "manifest_sha256": manifest.get("manifest_sha256"),
                "artifact_count": len(manifest.get("artifacts") or []),
                "raw_outputs_retained": True,
                "secret_outputs_redacted": True,
            },
            "unavailable_data_notes": sorted(set(note for note in notes if note)),
            "human_review_required": True,
            "client_delivery_allowed": False,
            "qualification_target_sha": FROZEN_QUALIFICATION_SHA if str(payload.get("snapshot_commit_sha") or "").lower() == FROZEN_QUALIFICATION_SHA else "",
        }
    )
    base.SCAN_JOBS[scan_id] = job
    STORE.put("scanner_runs", scan_id, job)
    STORE.audit(
        "scanner.strict_snapshot_completed",
        {
            "scan_id": scan_id,
            "repository": job.get("repository"),
            "snapshot_commit_sha": job.get("snapshot_commit_sha"),
            "actual_commit_sha": actual_sha,
            "status": job.get("status"),
            "required_tools_complete": required_complete,
            "repeatability_verified": repeatability_verified,
            "artifact_manifest_sha256": manifest.get("manifest_sha256"),
        },
        customer_id=customer_id,
        project_id=project_id,
    )
    return job


def start_snapshot_scan(payload: dict[str, Any]) -> dict[str, Any]:
    job = _new_job(payload)
    if job.get("status") == "blocked":
        return job
    scan_id = str(job["scan_id"])
    threading.Thread(target=_execute_scan, args=(scan_id, dict(payload)), daemon=True).start()
    return job


def run_snapshot_scan_sync(payload: dict[str, Any]) -> dict[str, Any]:
    job = _new_job(payload)
    if job.get("status") == "blocked":
        return job
    return _execute_scan(str(job["scan_id"]), dict(payload))


def _strict_provider(provider_module: Any) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def scanner_suite_provider(context: dict[str, Any]) -> dict[str, Any]:
        snapshot = provider_module._snapshot(context)
        if snapshot.get("status") != "attached":
            return provider_module._result(context, "blocked", reason="attached_snapshot_required")
        scan_id = provider_module._scan_id(context)
        scan = base.get_scan(scan_id) if hasattr(base, "get_scan") and scan_id else {}
        if not scan:
            from nico.scanner_worker import get_scan

            scan = get_scan(scan_id) if scan_id else start_snapshot_scan(
                {
                    "repository": context["repository"],
                    "authorized": True,
                    "customer_id": context["customer_id"],
                    "project_id": context["project_id"],
                    "run_id": context["run_id"],
                    "authorized_by": "comprehensive_native_provider",
                    "authorization_scope": "authorized defensive repository assessment",
                    "snapshot_id": snapshot.get("snapshot_id"),
                    "snapshot_commit_sha": snapshot.get("commit_sha"),
                }
            )
        status = _safe_text(scan.get("status"), 40).lower()
        if status in {"queued", "running"}:
            return provider_module._result(
                context,
                "running",
                summary="The fail-closed scanner suite is executing against the exact immutable commit.",
                scan_id=scan.get("scan_id"),
                scanner={
                    "scan_id": scan.get("scan_id"),
                    "status": status,
                    "current_stage": scan.get("current_stage"),
                    "active_tool": scan.get("active_tool"),
                    "progress_percent": scan.get("progress_percent"),
                    "snapshot_commit_sha": scan.get("snapshot_commit_sha"),
                },
            )
        strict_complete = bool(
            status == "complete"
            and scan.get("snapshot_match") is True
            and scan.get("required_tools_complete") is True
            and isinstance(scan.get("repeatability"), dict)
            and scan["repeatability"].get("status") == "verified"
        )
        if not strict_complete:
            return provider_module._result(
                context,
                "blocked",
                reason="required_scanner_evidence_incomplete_or_nonrepeatable",
                scan_id=scan.get("scan_id"),
                scanner_status=status or "unavailable",
                failed_tools=scan.get("failed_tools") or [],
                unavailable_tools=scan.get("unavailable_tools") or [],
                timed_out_tools=scan.get("timed_out_tools") or [],
                repeatability=scan.get("repeatability") or {},
                artifact_retention=scan.get("artifact_retention") or {},
                unavailable_data_notes=scan.get("unavailable_data_notes")
                or ["Required scanner evidence did not complete twice against the immutable SHA."],
            )
        counts = provider_module._counts(scan)
        return provider_module._result(
            context,
            summary="All required scanners completed with retained artifacts, exact-SHA history, and two-pass critical-tool equivalence.",
            scan_id=scan.get("scan_id"),
            scanner={
                "scan_id": scan.get("scan_id"),
                "status": "complete",
                "snapshot_match": True,
                "actual_commit_sha": scan.get("actual_commit_sha"),
                "tools_requested": scan.get("tools_requested") or [],
                "tools_run": scan.get("tools_run") or [],
                "failed_tools": [],
                "unavailable_tools": [],
                "timed_out_tools": [],
                "repeatability": scan.get("repeatability") or {},
                "artifact_retention": scan.get("artifact_retention") or {},
                "finding_summary": scan.get("finding_summary") or {},
            },
            evidence={
                "scan_id": scan.get("scan_id"),
                "snapshot_match": True,
                "actual_commit_sha": scan.get("actual_commit_sha"),
                "required_tools_complete": True,
                "repeatability_verified": True,
                "artifact_manifest_sha256": (scan.get("artifact_retention") or {}).get("manifest_sha256"),
                **counts,
            },
        )

    return scanner_suite_provider


def install_frozen_sha_scanner_evidence_v1(provider_module: Any) -> dict[str, Any]:
    from nico import snapshot_scanner_worker

    marker = "_nico_frozen_sha_scanner_evidence_v1"
    if getattr(snapshot_scanner_worker, marker, False):
        return {"status": "already_installed", "version": VERSION, "bound": True}
    snapshot_scanner_worker.clone_repository_at_snapshot = clone_repository_at_exact_history
    snapshot_scanner_worker._run_snapshot_scan = _execute_scan
    snapshot_scanner_worker.start_snapshot_scan = start_snapshot_scan
    provider_module.start_snapshot_scan = start_snapshot_scan
    provider_module.scanner_suite_provider = _strict_provider(provider_module)
    setattr(snapshot_scanner_worker, marker, True)
    return {
        "status": "installed",
        "version": VERSION,
        "bound": True,
        "exact_sha_non_shallow_checkout": True,
        "required_tools_fail_closed": True,
        "bandit_vendor_exclusions": True,
        "scanner_owned_eslint_config": True,
        "typescript_heap_mb": NODE_HEAP_MB,
        "osv_partial_fallback_allowed": False,
        "critical_tools_run_twice": list(CRITICAL_REPEATABILITY_TOOLS),
        "retained_raw_artifacts": True,
        "secret_artifacts_redacted": True,
        "qualification_sha": FROZEN_QUALIFICATION_SHA,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def qualification_summary(scan: dict[str, Any]) -> dict[str, Any]:
    first = {str(item.get("tool")): item for item in scan.get("scanner_results") or [] if isinstance(item, dict)}
    second = {str(item.get("tool")): item for item in scan.get("scanner_repeatability_results") or [] if isinstance(item, dict)}
    return {
        "artifact_schema": "nico.frozen_sha_scanner_qualification.v1",
        "status": "qualified" if scan.get("status") == "complete" else "blocked",
        "scan_id": scan.get("scan_id"),
        "repository": scan.get("repository"),
        "expected_commit_sha": scan.get("snapshot_commit_sha"),
        "actual_commit_sha": scan.get("actual_commit_sha"),
        "snapshot_match": scan.get("snapshot_match") is True,
        "full_history_verified": (scan.get("history_evidence") or {}).get("full_history_verified") is True,
        "required_tools_complete": scan.get("required_tools_complete") is True,
        "repeatability": scan.get("repeatability") or {},
        "first_pass": {
            name: {
                "status": first.get(name, {}).get("status"),
                "tool_version": first.get(name, {}).get("tool_version"),
                "findings_count": first.get(name, {}).get("findings_count"),
                "output_capture_complete": first.get(name, {}).get("output_capture_complete") is True,
                "artifact_sha256": ((first.get(name, {}).get("raw_artifacts") or {}).get("stdout") or {}).get("sha256"),
            }
            for name in REQUIRED_TOOLS
        },
        "second_pass": {
            name: {
                "status": second.get(name, {}).get("status"),
                "tool_version": second.get(name, {}).get("tool_version"),
                "findings_count": second.get(name, {}).get("findings_count"),
                "output_capture_complete": second.get(name, {}).get("output_capture_complete") is True,
                "artifact_sha256": ((second.get(name, {}).get("raw_artifacts") or {}).get("stdout") or {}).get("sha256"),
            }
            for name in CRITICAL_REPEATABILITY_TOOLS
        },
        "artifact_retention": scan.get("artifact_retention") or {},
        "blocking_notes": scan.get("unavailable_data_notes") or [],
        "client_ready": False,
        "human_review_required": True,
    }


__all__ = [
    "CRITICAL_REPEATABILITY_TOOLS",
    "FROZEN_QUALIFICATION_SHA",
    "REQUIRED_TOOLS",
    "VERSION",
    "clone_repository_at_exact_history",
    "install_frozen_sha_scanner_evidence_v1",
    "qualification_summary",
    "run_snapshot_scan_sync",
    "start_snapshot_scan",
]
