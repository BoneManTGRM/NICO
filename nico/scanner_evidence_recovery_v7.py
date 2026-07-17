from __future__ import annotations

import json
from dataclasses import replace
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace


SCANNER_EVIDENCE_RECOVERY_V7 = "nico.scanner_evidence_recovery.v7"
_PATCH_MARKER = "_nico_scanner_evidence_recovery_v7"


def _parseable_json(text: str) -> bool:
    if not str(text or "").strip():
        return False
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return False
    return True


def _semgrep_rules_path() -> Path:
    return Path(__file__).resolve().parent / "scanner_rules" / "nico-semgrep.yml"


def _prepare_web_dependencies(
    workspace: WorkerWorkspace,
    runner: Callable[..., WorkerCommandResult],
) -> dict[str, Any]:
    web = workspace.repo_dir / "apps" / "web"
    lockfile = web / "package-lock.json"
    package = web / "package.json"
    marker = workspace.root / ".nico-web-dependencies-ready"
    if marker.exists():
        return {"status": "ready", "source": "same-workspace-cache"}
    if not package.exists() or not lockfile.exists():
        return {"status": "unavailable", "reason": "apps/web package.json and package-lock.json are required for controlled frontend analyzer installation."}
    result = runner(
        ("npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"),
        cwd=web,
        limits=WorkerLimits(timeout_seconds=300, max_output_chars=20_000),
    )
    if result.timed_out:
        return {"status": "timeout", "reason": "Controlled npm dependency installation timed out before frontend analyzers could run."}
    if result.returncode != 0:
        preview = (result.stderr or result.stdout or "npm ci failed")[:1500]
        return {"status": "failed", "reason": preview}
    marker.write_text("ready", encoding="utf-8")
    return {"status": "ready", "source": "npm-ci-ignore-scripts", "returncode": result.returncode}


def install_scanner_evidence_recovery_v7() -> dict[str, Any]:
    from nico import hosted_dependency_scanner_execution_patch as dependency
    from nico import hosted_static_scanner_execution_patch as static
    from nico import scanner_tool_runners

    if getattr(scanner_tool_runners, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": SCANNER_EVIDENCE_RECOVERY_V7}

    current_dependency_complete = dependency._completed

    @wraps(current_dependency_complete)
    def dependency_complete_with_parseability(
        spec,
        result: WorkerCommandResult,
        *,
        cwd: Path,
        command: tuple[str, ...],
        source: str,
    ) -> dict[str, Any]:
        payload = current_dependency_complete(spec, result, cwd=cwd, command=command, source=source)
        parseable = _parseable_json(result.stdout or "")
        if result.timed_out:
            payload.update({"output_parseable": False, "parser_status": "timeout", "verified_for_this_report": False})
        elif parseable:
            payload.update({"output_parseable": True, "parser_status": "parseable_json", "verified_for_this_report": payload.get("status") == "completed"})
        elif result.returncode == 0 and not (result.stdout or "").strip():
            payload.update({"output_parseable": True, "parser_status": "empty_clean_output", "verified_for_this_report": payload.get("status") == "completed"})
        else:
            payload.update({"output_parseable": False, "parser_status": "non_parseable_output", "verified_for_this_report": False})
            if payload.get("status") == "completed" and not payload.get("findings"):
                payload["status"] = "failed"
                payload["reason"] = f"{spec.name} did not return complete parseable dependency evidence."
                payload["failure_or_unavailable_reason"] = payload["reason"]
        payload["evidence_recovery_version"] = SCANNER_EVIDENCE_RECOVERY_V7
        return payload

    dependency._completed = dependency_complete_with_parseability

    current_osv = dependency._run_osv_scanner_or_api

    @wraps(current_osv)
    def osv_with_verification(spec, workspace: WorkerWorkspace, *, runner):
        payload = current_osv(spec, workspace, runner=runner)
        if isinstance(payload, dict) and payload.get("status") == "completed":
            payload.setdefault("output_parseable", True)
            payload.setdefault("parser_status", "structured_osv_evidence")
            payload.setdefault("verified_for_this_report", True)
            payload.setdefault("current_run", True)
            payload["evidence_recovery_version"] = SCANNER_EVIDENCE_RECOVERY_V7
        return payload

    dependency._run_osv_scanner_or_api = osv_with_verification

    current_semgrep = static._semgrep_command

    @wraps(current_semgrep)
    def semgrep_with_local_rules(workspace: WorkerWorkspace):
        rules = _semgrep_rules_path()
        if rules.exists() and static._which("semgrep") is not None:
            return (
                "semgrep",
                "scan",
                "--config",
                str(rules),
                "--json",
                "--metrics",
                "off",
                "--exclude",
                "node_modules",
                "--exclude",
                ".next",
                "--exclude",
                "dist",
                "--exclude",
                "build",
                ".",
            ), workspace.repo_dir, None, "nico_local_semgrep_rules"
        return current_semgrep(workspace)

    static._semgrep_command = semgrep_with_local_rules

    current_eslint = static._eslint_command

    @wraps(current_eslint)
    def eslint_prefer_local_binary(workspace: WorkerWorkspace):
        web = workspace.repo_dir / "apps" / "web"
        local = static._local_bin(web, "eslint")
        if local:
            return (str(local), ".", "--format", "json"), web, None, "eslint_local_binary_after_controlled_install"
        return current_eslint(workspace)

    static._eslint_command = eslint_prefer_local_binary

    current_typescript = static._typescript_command

    @wraps(current_typescript)
    def typescript_prefer_local_binary(workspace: WorkerWorkspace):
        web = workspace.repo_dir / "apps" / "web"
        local = static._local_bin(web, "tsc")
        if local and (web / "tsconfig.json").exists():
            return (str(local), "--noEmit", "--pretty", "false"), web, None, "typescript_local_binary_after_controlled_install"
        return current_typescript(workspace)

    static._typescript_command = typescript_prefer_local_binary

    current_static_run = static._run_static_tool

    @wraps(current_static_run)
    def static_with_controlled_preparation(spec, workspace: WorkerWorkspace, *, runner):
        preparation: dict[str, Any] | None = None
        effective_spec = spec
        if spec.name in {"eslint", "typescript"}:
            preparation = _prepare_web_dependencies(workspace, runner)
        elif spec.name == "bandit":
            effective_spec = replace(
                spec,
                command=(
                    "bandit",
                    "-r",
                    ".",
                    "-f",
                    "json",
                    "-x",
                    ".git,node_modules,.next,dist,build,.venv,venv,__pycache__",
                ),
            )
        payload = current_static_run(effective_spec, workspace, runner=runner)
        if isinstance(payload, dict):
            payload["evidence_recovery_version"] = SCANNER_EVIDENCE_RECOVERY_V7
            if preparation is not None:
                payload["frontend_dependency_preparation"] = preparation
                if preparation.get("status") != "ready" and payload.get("status") != "completed":
                    payload["reason"] = str(preparation.get("reason") or payload.get("reason") or "Frontend analyzer preparation was unavailable.")
                    payload["failure_or_unavailable_reason"] = payload["reason"]
        return payload

    static._run_static_tool = static_with_controlled_preparation
    setattr(scanner_tool_runners, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "version": SCANNER_EVIDENCE_RECOVERY_V7,
        "dependency_parseability_required": True,
        "local_semgrep_rules": True,
        "controlled_frontend_install": "npm ci --ignore-scripts",
        "score_inflation_allowed": False,
        "human_review_required": True,
    }


__all__ = ["SCANNER_EVIDENCE_RECOVERY_V7", "install_scanner_evidence_recovery_v7"]
