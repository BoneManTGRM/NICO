from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

VERSION = "nico.scanner_complete_output_compat.v4"
_PATCH_MARKER = "_nico_scanner_complete_output_compat_v4"

_GENERATED_EXCLUSIONS = (
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "dist",
    "build",
    "coverage_html",
)


def _semgrep_finding(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return raw
    item = dict(raw)
    extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    metadata = extra.get("metadata") if isinstance(extra.get("metadata"), dict) else {}
    start = item.get("start") if isinstance(item.get("start"), dict) else {}
    end = item.get("end") if isinstance(item.get("end"), dict) else {}
    severity = (
        item.get("severity")
        or extra.get("severity")
        or metadata.get("severity")
        or metadata.get("impact")
        or "unknown"
    )
    item.setdefault("severity", str(severity).lower())
    item.setdefault("rule_id", item.get("check_id") or metadata.get("id") or "unknown")
    item.setdefault("message", extra.get("message") or metadata.get("message") or "Semgrep candidate requires review")
    item.setdefault("file_path", item.get("path") or "")
    item.setdefault("line", start.get("line"))
    item.setdefault("column", start.get("col"))
    item.setdefault("end_line", end.get("line"))
    item.setdefault("end_column", end.get("col"))
    item.setdefault("verified", False)
    return item


def _normalize_findings(tool_name: str, findings: Any) -> list[Any]:
    values = findings if isinstance(findings, list) else list(findings or [])
    if tool_name == "semgrep":
        return [_semgrep_finding(item) for item in values]
    return values


def _without_gitleaks_head_scope(command: tuple[str, ...]) -> tuple[str, ...]:
    output: list[str] = []
    skip_next = False
    for part in command:
        if skip_next:
            skip_next = False
            continue
        if part == "--log-opts":
            skip_next = True
            continue
        output.append(part)
    return tuple(output)


def _effective_command(spec: Any, command: tuple[str, ...]) -> tuple[str, ...]:
    if spec.name == "gitleaks":
        # Default gitleaks detect behavior scans repository history. The previous
        # compatibility command forced HEAD-only scope while still advertising
        # history coverage, which incorrectly reduced secret assurance.
        return _without_gitleaks_head_scope(command)
    if spec.name == "bandit" and "-x" not in command and "--exclude" not in command:
        return command + ("-x", ",".join(_GENERATED_EXCLUSIONS))
    return command


def install_scanner_complete_output_compat_v3() -> dict[str, Any]:
    from nico import scanner_tool_runners as runners

    if getattr(runners, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    complete_parser: Callable[..., Any] = runners.parse_tool_findings
    original_unavailable = runners._unavailable_tool

    def compatible_parse_tool_findings(tool_name: str, result: Any) -> list[Any]:
        parsed = complete_parser(tool_name, result)
        if isinstance(parsed, tuple) and len(parsed) == 3:
            findings = parsed[0]
            return _normalize_findings(tool_name, findings)
        return _normalize_findings(tool_name, parsed)

    def observed_unavailable(*args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = original_unavailable(*args, **kwargs)
        if isinstance(payload, dict):
            payload["current_run"] = True
            payload["execution_observed_for_this_report"] = True
            payload["verified_for_this_report"] = False
            payload.setdefault("findings_count", 0)
        return payload

    def compatible_run_scanner_tool(
        spec: Any,
        workspace: Any,
        *,
        runner: Callable[..., Any] = runners.run_command,
    ) -> dict[str, Any]:
        if spec.requires_project_commands and not runners.project_commands_allowed():
            return observed_unavailable(
                spec,
                f"{spec.name} requires NICO_ALLOW_PROJECT_COMMANDS=true because it may execute project-local commands.",
            )

        if spec.name == "eslint":
            web_dir = workspace.repo_dir / "apps" / "web"
            if not runners._has_eslint_config(web_dir):
                return observed_unavailable(
                    spec,
                    "No ESLint configuration exists in apps/web; ESLint is not applicable to this snapshot and TypeScript remains independently evaluated.",
                )

        preparation = runners.prepare_project_commands(workspace, runner=runner) if spec.requires_project_commands else None
        if spec.name == "osv-scanner" and shutil.which(spec.command[0]) is None:
            payload = runners._osv_api_fallback_tool(spec, workspace.repo_dir)
            if isinstance(payload, dict):
                payload.setdefault("current_run", True)
                payload.setdefault("execution_observed_for_this_report", True)
                payload["verified_for_this_report"] = payload.get("status") == "completed"
            return payload

        command, cwd, unavailable_reason = runners._resolve_command_and_cwd(spec, workspace, preparation)
        if command is None:
            return observed_unavailable(
                spec,
                unavailable_reason or f"{spec.name} could not resolve a safe command",
                preparation=preparation,
            )
        command = _effective_command(spec, tuple(command))
        if not runners._command_available(command):
            return observed_unavailable(spec, f"{command[0]} is not installed in the worker image", preparation=preparation)

        output_path = workspace.root / "scanner-output" / f"{spec.name}.stdout"
        result = runner(
            command,
            cwd=cwd,
            limits=runners.WorkerLimits(timeout_seconds=spec.timeout_seconds, max_output_chars=spec.max_output_chars),
            extra_env=runners._tool_env(spec, workspace, cwd),
            stdout_path=output_path,
        )
        parsed = complete_parser(spec.name, result)
        if isinstance(parsed, tuple) and len(parsed) == 3:
            findings, capture_complete, capture_reason = parsed
        else:
            findings = parsed if isinstance(parsed, list) else list(parsed or [])
            capture_complete = not bool(getattr(result, "output_truncated", False))
            capture_reason = "" if capture_complete else "scanner output was truncated before parsing"
        findings = _normalize_findings(spec.name, findings)

        returncode_valid = result.returncode in spec.valid_returncodes
        if result.timed_out:
            status = "timeout"
            execution_error = f"{spec.name} exceeded its {spec.timeout_seconds}-second bounded timeout."
        elif not returncode_valid:
            status = "failed"
            execution_error = runners.redact_text(result.stderr or result.stdout or f"unexpected return code {result.returncode}")[:4000]
        elif not capture_complete:
            status = "failed"
            execution_error = capture_reason or "scanner output could not be parsed completely"
        else:
            status = "completed"
            execution_error = ""

        full_history_verified = bool(
            status == "completed"
            and spec.scans_git_history
            and spec.name in {"gitleaks", "trufflehog"}
        )
        payload: dict[str, Any] = {
            "tool": spec.name,
            "status": status,
            "category": spec.category,
            "returncode": result.returncode,
            "returncode_valid": returncode_valid,
            "timed_out": result.timed_out,
            "output_truncated": result.output_truncated,
            "output_capture_complete": bool(capture_complete),
            "stdout_bytes": result.stdout_bytes,
            "stderr_bytes": result.stderr_bytes,
            "command_intent": " ".join(Path(part).name if index == 0 else part for index, part in enumerate(command[:8])),
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
        if preparation is not None:
            payload["project_preparation"] = {
                "status": preparation.status,
                "node_modules_ready": preparation.node_modules_ready,
                "returncode": preparation.returncode,
                "timed_out": preparation.timed_out,
                "output_truncated": preparation.output_truncated,
            }
        return runners.redact_payload(payload)

    def compatible_run_scanner_tools(
        workspace: Any,
        specs: Any = runners.TOOL_SPECS,
        *,
        runner: Callable[..., Any] = runners.run_command,
    ) -> dict[str, Any]:
        if not workspace.repo_dir.exists() or not workspace.repo_dir.is_dir():
            raise ValueError("workspace repo directory must exist before scanner tools run")

        tool_results = [runners.run_scanner_tool(spec, workspace, runner=runner) for spec in specs]
        raw_payload = {"tools": tool_results}
        normalized = runners.normalize_scanner_worker_artifact(raw_payload)
        history_secret_tools = [
            item["tool"]
            for item in tool_results
            if isinstance(item, dict)
            and item.get("category") == "secret"
            and item.get("status") == "completed"
            and item.get("scans_git_history")
            and item.get("full_history_verified") is True
        ]
        preparation = next(
            (
                item.get("project_preparation")
                for item in tool_results
                if isinstance(item, dict) and isinstance(item.get("project_preparation"), dict)
            ),
            None,
        )
        return {
            "artifact_schema": "nico.scanner_worker.v2",
            "tools": {item["tool"]: item for item in tool_results if isinstance(item, dict) and item.get("tool")},
            "normalized": normalized,
            "project_preparation": preparation or {"status": "not_required", "node_modules_ready": False},
            "secret_history_scan": {
                "completed_tools": history_secret_tools,
                "history_aware": bool(history_secret_tools),
            },
        }

    runners.parse_tool_findings = compatible_parse_tool_findings
    runners._unavailable_tool = observed_unavailable
    runners.run_scanner_tool = compatible_run_scanner_tool
    runners.run_scanner_tools = compatible_run_scanner_tools
    setattr(runners, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "version": VERSION,
        "legacy_findings_list_contract": True,
        "complete_capture_metadata_preserved": True,
        "wrapper_keyword_compatibility": True,
        "unavailable_state_observed_not_verified": True,
        "semgrep_nested_severity_normalized": True,
        "gitleaks_full_history_restored": True,
        "bandit_generated_paths_excluded": True,
        "eslint_without_configuration_inapplicable": True,
    }


__all__ = ["VERSION", "install_scanner_complete_output_compat_v3"]
