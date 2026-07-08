from __future__ import annotations

import json
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


TOOL_SPECS: tuple[ScannerToolSpec, ...] = (
    ScannerToolSpec("bandit", ("bandit", "-r", ".", "-f", "json"), "static", timeout_seconds=180),
    ScannerToolSpec("semgrep", ("semgrep", "scan", "--config", "auto", "--json", "."), "static", timeout_seconds=240),
    ScannerToolSpec("eslint", ("npx", "eslint", ".", "--format", "json"), "static", timeout_seconds=180),
    ScannerToolSpec("typescript", ("npx", "tsc", "--noEmit", "--pretty", "false"), "static", timeout_seconds=180),
    ScannerToolSpec("gitleaks", ("gitleaks", "detect", "--no-banner", "--redact", "--report-format", "json", "--source", "."), "secret", timeout_seconds=180),
    ScannerToolSpec("trufflehog", ("trufflehog", "filesystem", ".", "--json", "--no-update"), "secret", timeout_seconds=180),
)


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


def parse_tool_findings(tool_name: str, result: WorkerCommandResult) -> list[Any]:
    text = redact_text(result.stdout or "")
    if not text.strip():
        return []

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        if tool_name == "trufflehog":
            return _parse_json_lines(text)
        return []

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
    if tool_name == "typescript":
        return [] if result.returncode == 0 else [{"message": redact_text(result.stderr or result.stdout)}]
    if tool_name == "gitleaks" and isinstance(payload, list):
        return payload
    if tool_name == "trufflehog" and isinstance(payload, dict):
        return [payload]
    return []


def run_scanner_tool(
    spec: ScannerToolSpec,
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult] = run_command,
) -> dict[str, Any]:
    executable = spec.command[0]
    if shutil.which(executable) is None:
        return {
            "tool": spec.name,
            "status": "unavailable",
            "reason": f"{executable} is not installed in the worker image",
            "findings": [],
        }

    result = runner(
        spec.command,
        cwd=workspace.repo_dir,
        limits=WorkerLimits(timeout_seconds=spec.timeout_seconds, max_output_chars=spec.max_output_chars),
    )
    status = "completed" if not result.timed_out else "timeout"
    findings = parse_tool_findings(spec.name, result)
    return redact_payload(
        {
            "tool": spec.name,
            "status": status,
            "returncode": result.returncode,
            "timed_out": result.timed_out,
            "output_truncated": result.output_truncated,
            "findings": findings,
            "stderr": result.stderr,
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
    return {
        "artifact_schema": "nico.scanner_worker.v1",
        "tools": {item["tool"]: item for item in tool_results if isinstance(item, dict) and item.get("tool")},
        "normalized": normalized,
    }


def write_scanner_artifact(payload: dict[str, Any], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(redact_payload(payload), indent=2, sort_keys=True), encoding="utf-8")
    return destination
