from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from nico.scanner_tool_runners import ESLINT_CONFIG_NAMES, ScannerToolSpec, redact_text
from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace

SCANNER_OUTPUT_TRUTH_VERSION = "nico.scanner_output_truth.v1"
_STATIC_COMPLETE_MARKER = "_nico_static_output_truth_v1"
_STATIC_RUN_MARKER = "_nico_static_output_limits_v1"
_ESLINT_MARKER = "_nico_eslint_script_truth_v1"
_TYPESCRIPT_MARKER = "_nico_typescript_script_truth_v1"
_SECRET_COMPLETE_MARKER = "_nico_secret_output_truth_v1"
_GITLEAKS_MARKER = "_nico_gitleaks_report_path_v1"
_SECRET_RUN_MARKER = "_nico_secret_timeout_truth_v1"


def _read_package(directory: Path) -> dict[str, Any]:
    try:
        payload = json.loads((directory / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _script(directory: Path, name: str) -> str:
    scripts = _read_package(directory).get("scripts")
    return str(scripts.get(name) or "") if isinstance(scripts, dict) else ""


def _contains_command(script: str, command: str) -> bool:
    return bool(re.search(rf"(?:^|[\s;&|])(?:npx\s+)?{re.escape(command)}(?:[\s;&|]|$)", script))


def _has_eslint_config(directory: Path) -> bool:
    return any((directory / name).exists() for name in ESLINT_CONFIG_NAMES)


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _json_shape(tool: str, text: str) -> tuple[bool, str]:
    if not text.strip():
        return False, "empty_output"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return False, "invalid_json"
    if tool in {"bandit", "semgrep"} and not isinstance(payload, dict):
        return False, "unexpected_json_shape"
    if tool in {"eslint", "gitleaks"} and not isinstance(payload, list):
        return False, "unexpected_json_shape"
    return True, "parseable_json"


def _json_lines_parseable(text: str) -> tuple[bool, str]:
    if not text.strip():
        return True, "empty_clean_json_lines"
    parsed = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            return False, "invalid_json_line"
        if not isinstance(value, dict):
            return False, "unexpected_json_line_shape"
        parsed += 1
    return True, "parseable_json_lines" if parsed else "empty_clean_json_lines"


def _set_unverified(payload: dict[str, Any], reason: str, parser_status: str) -> dict[str, Any]:
    output = dict(payload)
    output["status"] = "failed"
    output["verified_for_this_report"] = False
    output["output_parseable"] = False
    output["parser_status"] = parser_status
    output["reason"] = reason
    output["failure_or_unavailable_reason"] = reason
    return output


def install_scanner_output_truth_patch() -> dict[str, Any]:
    from nico import hosted_secret_scanner_execution_patch as secret
    from nico import hosted_static_scanner_execution_patch as static

    installed: dict[str, bool] = {}

    current_eslint = static._eslint_command
    if not getattr(current_eslint, _ESLINT_MARKER, False):
        @wraps(current_eslint)
        def truthful_eslint(workspace: WorkerWorkspace):
            directory = workspace.repo_dir / "apps" / "web"
            if not (directory / "package.json").exists():
                return current_eslint(workspace)
            if not static._project_commands_allowed():
                return current_eslint(workspace)
            lint_script = _script(directory, "lint")
            if lint_script and _contains_command(lint_script, "eslint"):
                return ("npm", "run", "lint"), directory, None, "eslint_npm_script"
            if not _has_eslint_config(directory):
                return (
                    None,
                    directory,
                    "No ESLint configuration exists and the package lint script does not execute ESLint; TypeScript compilation must not be relabeled as ESLint evidence.",
                    "eslint_contract_unavailable",
                )
            local = static._local_bin(directory, "eslint")
            if local:
                return (str(local), ".", "--format", "json"), directory, None, "eslint_local_binary"
            if static._which("eslint"):
                return ("eslint", ".", "--format", "json"), directory, None, "eslint_global_binary"
            return None, directory, "ESLint is not installed.", "eslint_unavailable"

        setattr(truthful_eslint, _ESLINT_MARKER, True)
        setattr(truthful_eslint, "_nico_previous", current_eslint)
        static._eslint_command = truthful_eslint
        installed["eslint_contract"] = True

    current_typescript = static._typescript_command
    if not getattr(current_typescript, _TYPESCRIPT_MARKER, False):
        @wraps(current_typescript)
        def truthful_typescript(workspace: WorkerWorkspace):
            directory = workspace.repo_dir / "apps" / "web"
            if not (directory / "package.json").exists() or not static._project_commands_allowed():
                return current_typescript(workspace)
            if not (directory / "tsconfig.json").exists():
                return current_typescript(workspace)
            for script_name in ("typecheck", "type-check", "check-types"):
                if _contains_command(_script(directory, script_name), "tsc"):
                    return ("npm", "run", script_name), directory, None, "typescript_npm_script"
            if _contains_command(_script(directory, "lint"), "tsc"):
                return ("npm", "run", "lint"), directory, None, "typescript_npm_script"
            local = static._local_bin(directory, "tsc")
            if local:
                return (str(local), "--noEmit", "--pretty", "false"), directory, None, "typescript_local_binary"
            if static._which("tsc"):
                return ("tsc", "--noEmit", "--pretty", "false"), directory, None, "typescript_global_binary"
            return None, directory, "TypeScript compiler is not installed.", "typescript_unavailable"

        setattr(truthful_typescript, _TYPESCRIPT_MARKER, True)
        setattr(truthful_typescript, "_nico_previous", current_typescript)
        static._typescript_command = truthful_typescript
        installed["typescript_contract"] = True

    current_static_complete = static._completed
    if not getattr(current_static_complete, _STATIC_COMPLETE_MARKER, False):
        @wraps(current_static_complete)
        def truthful_static_complete(
            spec: ScannerToolSpec,
            result: WorkerCommandResult,
            *,
            cwd: Path,
            command: tuple[str, ...],
            source: str,
        ) -> dict[str, Any]:
            payload = current_static_complete(spec, result, cwd=cwd, command=command, source=source)
            if result.timed_out:
                payload["output_parseable"] = False
                payload["parser_status"] = "timeout"
                return payload
            if result.output_truncated:
                return _set_unverified(
                    payload,
                    f"{spec.name} output was truncated before the complete scanner result could be verified.",
                    "output_truncated",
                )
            if spec.name in {"bandit", "semgrep", "eslint"}:
                parseable, parser_status = _json_shape(spec.name, result.stdout or "")
                if not parseable:
                    return _set_unverified(
                        payload,
                        redact_text(result.stderr or f"{spec.name} did not return complete parseable JSON evidence."),
                        parser_status,
                    )
                payload["output_parseable"] = True
                payload["parser_status"] = parser_status
            else:
                payload["output_parseable"] = True
                payload["parser_status"] = "exit_status_contract"
            if result.returncode not in {0, 1}:
                return _set_unverified(
                    payload,
                    redact_text(result.stderr or f"{spec.name} returned unsupported exit code {result.returncode}."),
                    "unsupported_exit_code",
                )
            payload["verified_for_this_report"] = payload.get("status") == "completed"
            return payload

        setattr(truthful_static_complete, _STATIC_COMPLETE_MARKER, True)
        setattr(truthful_static_complete, "_nico_previous", current_static_complete)
        static._completed = truthful_static_complete
        installed["static_parseability"] = True

    current_static_run = static._run_static_tool
    if not getattr(current_static_run, _STATIC_RUN_MARKER, False):
        @wraps(current_static_run)
        def static_with_bounded_output(spec: ScannerToolSpec, workspace: WorkerWorkspace, *, runner: Callable[..., WorkerCommandResult]):
            minimum = _bounded_int("NICO_STATIC_SCANNER_MAX_OUTPUT_CHARS", 500_000, 80_000, 2_000_000)
            return current_static_run(replace(spec, max_output_chars=max(spec.max_output_chars, minimum)), workspace, runner=runner)

        setattr(static_with_bounded_output, _STATIC_RUN_MARKER, True)
        setattr(static_with_bounded_output, "_nico_previous", current_static_run)
        static._run_static_tool = static_with_bounded_output
        installed["static_output_limit"] = True

    current_gitleaks = secret._gitleaks_command
    if not getattr(current_gitleaks, _GITLEAKS_MARKER, False):
        @wraps(current_gitleaks)
        def gitleaks_with_report(workspace: WorkerWorkspace):
            command, cwd, reason = current_gitleaks(workspace)
            if command is None:
                return command, cwd, reason
            report_path = workspace.root / "gitleaks-report.json"
            augmented = tuple(command) + ("--report-path", str(report_path))
            return augmented, cwd, reason

        setattr(gitleaks_with_report, _GITLEAKS_MARKER, True)
        setattr(gitleaks_with_report, "_nico_previous", current_gitleaks)
        secret._gitleaks_command = gitleaks_with_report
        installed["gitleaks_report_path"] = True

    current_secret_complete = secret._completed
    if not getattr(current_secret_complete, _SECRET_COMPLETE_MARKER, False):
        @wraps(current_secret_complete)
        def truthful_secret_complete(
            spec: ScannerToolSpec,
            result: WorkerCommandResult,
            *,
            cwd: Path,
            command: tuple[str, ...],
            history: dict[str, Any],
            source: str,
        ) -> dict[str, Any]:
            normalized_result = result
            if spec.name == "gitleaks" and "--report-path" in command:
                index = command.index("--report-path")
                report_path = Path(command[index + 1]) if index + 1 < len(command) else Path("")
                try:
                    report_text = report_path.read_text(encoding="utf-8") if report_path.is_file() else ""
                except OSError:
                    report_text = ""
                if report_text:
                    normalized_result = WorkerCommandResult(
                        args=result.args,
                        returncode=result.returncode,
                        stdout=report_text,
                        stderr=result.stderr,
                        timed_out=result.timed_out,
                        output_truncated=result.output_truncated,
                    )
            payload = current_secret_complete(
                spec,
                normalized_result,
                cwd=cwd,
                command=command,
                history=history,
                source=source,
            )
            if result.timed_out:
                payload["output_parseable"] = False
                payload["parser_status"] = "timeout"
                return payload
            if normalized_result.output_truncated:
                return _set_unverified(
                    payload,
                    f"{spec.name} output was truncated before the complete secret-scanner result could be verified.",
                    "output_truncated",
                )
            if spec.name == "gitleaks":
                parseable, parser_status = _json_shape("gitleaks", normalized_result.stdout or "")
            else:
                parseable, parser_status = _json_lines_parseable(normalized_result.stdout or "")
            if not parseable:
                return _set_unverified(
                    payload,
                    redact_text(normalized_result.stderr or f"{spec.name} did not return complete parseable evidence."),
                    parser_status,
                )
            payload["output_parseable"] = True
            payload["parser_status"] = parser_status
            if result.returncode not in {0, 1}:
                return _set_unverified(
                    payload,
                    redact_text(result.stderr or f"{spec.name} returned unsupported exit code {result.returncode}."),
                    "unsupported_exit_code",
                )
            payload["verified_for_this_report"] = bool(
                payload.get("status") == "completed" and history.get("full_history_verified")
            )
            return payload

        setattr(truthful_secret_complete, _SECRET_COMPLETE_MARKER, True)
        setattr(truthful_secret_complete, "_nico_previous", current_secret_complete)
        secret._completed = truthful_secret_complete
        installed["secret_parseability"] = True

    current_secret_run = secret._run_secret_tool
    if not getattr(current_secret_run, _SECRET_RUN_MARKER, False):
        @wraps(current_secret_run)
        def secret_with_history_limits(spec: ScannerToolSpec, workspace: WorkerWorkspace, *, runner: Callable[..., WorkerCommandResult]):
            timeout = _bounded_int("NICO_HISTORY_TOOL_TIMEOUT_SECONDS", 420, 120, 1800)
            output = _bounded_int("NICO_SECRET_SCANNER_MAX_OUTPUT_CHARS", 500_000, 80_000, 2_000_000)
            return current_secret_run(
                replace(spec, timeout_seconds=max(spec.timeout_seconds, timeout), max_output_chars=max(spec.max_output_chars, output)),
                workspace,
                runner=runner,
            )

        setattr(secret_with_history_limits, _SECRET_RUN_MARKER, True)
        setattr(secret_with_history_limits, "_nico_previous", current_secret_run)
        secret._run_secret_tool = secret_with_history_limits
        installed["secret_limits"] = True

    return {
        "status": "installed" if installed else "already_installed",
        "version": SCANNER_OUTPUT_TRUTH_VERSION,
        "installed": installed,
        "typescript_mislabeled_as_eslint": False,
        "invalid_json_treated_as_clean": False,
        "truncated_output_treated_as_verified": False,
        "history_timeout_seconds": _bounded_int("NICO_HISTORY_TOOL_TIMEOUT_SECONDS", 420, 120, 1800),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["SCANNER_OUTPUT_TRUTH_VERSION", "install_scanner_output_truth_patch"]
