from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

from nico.evidence_pipeline_common_v1 import (
    _call_runner,
    _effective_command,
    _eslint_config_exists,
    _not_applicable,
    _package_script,
    _raw_output_record,
    _script_executes,
)
from nico.evidence_pipeline_osv_v1 import _full_osv_api_fallback


def _resolve_project_command(
    runners: Any,
    spec: Any,
    workspace: Any,
    project: tuple[Path, Path | None],
    preparation: Any,
) -> tuple[tuple[str, ...] | None, Path, str | None]:
    del workspace
    project_dir, lock_root = project
    lint_script = _package_script(project_dir)

    if lock_root is None:
        if spec.name == "eslint":
            if _script_executes(lint_script, "eslint"):
                return ("npm", "run", "lint"), project_dir, None
            if lint_script:
                return None, project_dir, "The configured lint script does not execute ESLint."
            return None, project_dir, "No ESLint configuration or executable lint script was found."
        if _script_executes(lint_script, "tsc"):
            return ("npm", "run", "lint"), project_dir, None
        return None, project_dir, "No exact package-lock or TypeScript lint script was found for this project."

    if preparation is None or not preparation.node_modules_ready:
        return None, project_dir, preparation.reason if preparation else "Project dependencies were not prepared."

    if spec.name == "eslint" and not _eslint_config_exists(project_dir):
        if _script_executes(lint_script, "eslint"):
            return ("npm", "run", "lint"), project_dir, None
        return None, project_dir, "The configured lint script does not execute ESLint."

    bin_name = "eslint" if spec.name == "eslint" else "tsc"
    binary = lock_root / "node_modules" / ".bin" / bin_name
    if not binary.is_file():
        system_binary = shutil.which(bin_name)
        if system_binary:
            binary = Path(system_binary)
        else:
            return None, project_dir, f"{bin_name} was not installed by the exact package-lock dependency preparation."
    if spec.name == "eslint":
        return (str(binary), ".", "--format", "json"), project_dir, None
    tsconfig = project_dir / "tsconfig.json"
    if not tsconfig.is_file() and _script_executes(lint_script, "tsc"):
        return ("npm", "run", "lint"), project_dir, None
    return (
        str(binary),
        "--noEmit",
        "--pretty",
        "false",
        "--incremental",
        "false",
        "-p",
        str(tsconfig),
    ), project_dir, None


def _stamp_and_enrich(payload: dict[str, Any], spec: Any, workspace: Any) -> dict[str, Any]:
    original_status = str(payload.get("status") or "").lower()
    try:
        from nico.hosted_evidence_execution_patch import _enrich_tool_payload

        payload = _enrich_tool_payload(payload, str(spec.name))
    except Exception:
        payload = dict(payload)

    if original_status == "not_applicable":
        payload.update(
            {
                "status": "not_applicable",
                "verified_for_this_report": True,
                "execution_observed_for_this_report": True,
                "current_run": True,
                "evidence_limitation": False,
            }
        )
        payload.pop("failure_or_unavailable_reason", None)
        payload.pop("execution_failure_is_evidence_limitation", None)

    try:
        from nico.scanner_artifact_provenance_v1 import _stamp_tool

        payload = _stamp_tool(payload, spec, workspace)
    except Exception:
        payload = dict(payload)
    return payload


def _parse_findings(runners: Any, tool_name: str, result: Any) -> tuple[list[Any], bool, str]:
    raw_text, capture_complete, capture_reason = runners._complete_stdout(result)
    text = runners.redact_text(raw_text or "")
    if not text.strip():
        if result.returncode == 0:
            return [], capture_complete, capture_reason
        fallback = runners.redact_text(result.stderr or "tool failed without stdout")
        return ([{"message": fallback}] if fallback else []), capture_complete, capture_reason
    if tool_name == "typescript":
        return runners._typescript_findings(text), capture_complete, capture_reason
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        if tool_name == "trufflehog":
            items = runners._parse_json_lines(text)
            return items, capture_complete and bool(items or not text.strip()), capture_reason or ("" if items else "trufflehog JSON-lines output could not be parsed")
        if tool_name in {"eslint", "coverage"} and result.returncode != 0:
            return [{"message": runners.redact_text(result.stderr or text)}], False, capture_reason or "tool returned non-JSON diagnostic output"
        return [], False, capture_reason or "scanner JSON output could not be parsed"
    if tool_name == "pip-audit" and isinstance(payload, dict):
        return runners._pip_audit_findings(payload), capture_complete, capture_reason
    if tool_name == "npm-audit" and isinstance(payload, dict):
        return runners._npm_audit_findings(payload), capture_complete, capture_reason
    if tool_name == "osv-scanner" and isinstance(payload, dict):
        return runners._osv_findings(payload), capture_complete, capture_reason
    if tool_name == "bandit" and isinstance(payload, dict):
        return list(payload.get("results") or []), capture_complete, capture_reason
    if tool_name == "semgrep" and isinstance(payload, dict):
        values = list(payload.get("results") or [])
        try:
            from nico.scanner_complete_output_compat_v3 import _semgrep_finding

            values = [_semgrep_finding(item) for item in values]
        except Exception:
            pass
        return values, capture_complete, capture_reason
    if tool_name == "eslint" and isinstance(payload, list):
        findings: list[Any] = []
        for file_result in payload:
            if not isinstance(file_result, dict):
                continue
            for message in file_result.get("messages") or []:
                if isinstance(message, dict):
                    item = dict(message)
                    item.setdefault("filePath", file_result.get("filePath"))
                    findings.append(item)
        return findings, capture_complete, capture_reason
    if tool_name == "coverage":
        return ([] if result.returncode == 0 else [{"message": runners.redact_text(result.stderr or text)}]), capture_complete, capture_reason
    if tool_name == "gitleaks" and isinstance(payload, list):
        return payload, capture_complete, capture_reason
    if tool_name == "trufflehog" and isinstance(payload, dict):
        return [payload], capture_complete, capture_reason
    return [], False, capture_reason or "scanner output shape was not recognized"


def _run_tool(
    runners: Any,
    spec: Any,
    workspace: Any,
    *,
    runner: Callable[..., Any],
    project: tuple[Path, Path | None] | None = None,
    preparation: Any = None,
) -> dict[str, Any]:
    if spec.name in {"eslint", "typescript"}:
        if not runners.project_commands_allowed():
            payload = runners._unavailable_tool(
                spec,
                f"{spec.name} requires NICO_ALLOW_PROJECT_COMMANDS=true because it executes the snapshot's project toolchain.",
            )
            return _stamp_and_enrich(payload, spec, workspace)
        if project is None:
            reason = (
                "No ESLint configuration or lint script exists in any package root; ESLint is not applicable to this snapshot."
                if spec.name == "eslint"
                else "No TypeScript project or TypeScript lint script was found; TypeScript is not applicable to this snapshot."
            )
            return _stamp_and_enrich(_not_applicable(spec, reason), spec, workspace)

        project_dir, lock_root = project
        lint_script = _package_script(project_dir)
        if (
            spec.name == "eslint"
            and lock_root is not None
            and not _eslint_config_exists(project_dir)
            and not _script_executes(lint_script, "eslint")
        ):
            return _stamp_and_enrich(
                _not_applicable(
                    spec,
                    "No ESLint configuration exists in the locked project and its lint script does not execute ESLint; TypeScript remains independently evaluated.",
                ),
                spec,
                workspace,
            )
        command, cwd, unavailable_reason = _resolve_project_command(runners, spec, workspace, project, preparation)
    elif spec.name == "osv-scanner" and shutil.which(spec.command[0]) is None:
        return _stamp_and_enrich(_full_osv_api_fallback(runners, spec, workspace.repo_dir), spec, workspace)
    else:
        command, cwd, unavailable_reason = runners._resolve_command_and_cwd(spec, workspace, None)

    if command is None:
        payload = runners._unavailable_tool(spec, unavailable_reason or f"{spec.name} could not resolve a safe command")
        return _stamp_and_enrich(payload, spec, workspace)
    command = _effective_command(spec, tuple(command))
    if not runners._command_available(command):
        payload = runners._unavailable_tool(spec, f"{command[0]} is not installed in the worker image")
        return _stamp_and_enrich(payload, spec, workspace)

    output_path = workspace.root / "scanner-output" / f"{spec.name}.stdout"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = _call_runner(
        runner,
        command,
        cwd=cwd,
        limits=runners.WorkerLimits(timeout_seconds=spec.timeout_seconds, max_output_chars=spec.max_output_chars),
        extra_env=runners._tool_env(spec, workspace, cwd),
        stdout_path=output_path,
    )
    findings, capture_complete, capture_reason = _parse_findings(runners, spec.name, result)
    raw_output = _raw_output_record(result)
    returncode_valid = result.returncode in spec.valid_returncodes
    if result.timed_out:
        status = "timeout"
        execution_error = f"{spec.name} exceeded its {spec.timeout_seconds}-second bounded timeout."
    elif not returncode_valid:
        status = "failed"
        execution_error = runners.redact_text(result.stderr or result.stdout or f"unexpected return code {result.returncode}")[:4000]
    elif not capture_complete:
        status = "failed"
        execution_error = capture_reason
    else:
        status = "completed"
        execution_error = ""
    full_history_verified = bool(status == "completed" and spec.scans_git_history and spec.name in {"gitleaks", "trufflehog"})
    payload: dict[str, Any] = {
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
        "command_intent": " ".join(Path(part).name if index == 0 else part for index, part in enumerate(command[:10])),
        "findings": findings,
        "findings_count": len(findings),
        "stderr": result.stderr,
        "reason": execution_error,
        "scans_git_history": spec.scans_git_history,
        "full_history_verified": full_history_verified,
        "verified_for_this_report": status == "completed",
        "execution_observed_for_this_report": True,
        "current_run": True,
    }
    if raw_output is not None:
        payload["raw_output_artifact"] = raw_output
    if preparation is not None:
        payload["project_preparation"] = {
            "status": preparation.status,
            "node_modules_ready": preparation.node_modules_ready,
            "returncode": preparation.returncode,
            "timed_out": preparation.timed_out,
            "output_truncated": preparation.output_truncated,
            "lock_root": str(preparation.web_dir),
        }
    return _stamp_and_enrich(runners.redact_payload(payload), spec, workspace)


__all__ = ["_run_tool"]
