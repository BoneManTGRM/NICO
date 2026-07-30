from __future__ import annotations

import inspect
import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from nico import scanner_tool_runners
from nico.scanner_evidence_pipeline_v1 import (
    _history_metadata,
    _raw_blob,
    _read_json,
    _run,
    _run_bandit,
    _run_eslint,
    _tool_payload,
    _unavailable,
)
from nico.scanner_tool_runners import (
    ProjectCommandPreparation,
    ScannerToolSpec,
    prepare_project_commands,
    project_commands_allowed,
)
from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace, run_command

VERSION = "nico.authoritative_scanner_execution.v3"
_PATCH_MARKER = "_nico_authoritative_scanner_execution_v3"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _head_sha(workspace: WorkerWorkspace) -> str:
    if not workspace.repo_dir.exists():
        return ""
    result = run_command(
        ("git", "rev-parse", "HEAD"),
        cwd=workspace.repo_dir,
        limits=WorkerLimits(timeout_seconds=30, max_output_chars=2_000),
    )
    return (result.stdout or "").strip() if result.ok else ""


def _normalize_record(record: dict[str, Any], workspace: WorkerWorkspace) -> dict[str, Any]:
    """Project one scanner result into the exact-SHA v2 record contract."""
    output = deepcopy(record)
    name = _text(output.get("scanner_name") or output.get("scanner") or output.get("tool")).casefold().replace("_", "-")
    status = _text(output.get("status") or output.get("state")).casefold().replace("-", "_")
    findings = [item for item in output.get("findings") or [] if isinstance(item, dict)]
    artifact_hash = _text(
        output.get("artifact_hash")
        or output.get("raw_artifact_sha256")
        or output.get("deterministic_fingerprint")
    )
    head_sha = _text(output.get("commit_sha") or output.get("head_sha") or _head_sha(workspace))
    capture_complete = bool(
        output.get("output_capture_complete") is True
        or output.get("raw_artifact_capture_complete") is True
    )
    history_ok = True
    if output.get("scans_git_history"):
        history_ok = output.get("full_history_verified") is True
    completed = bool(status == "completed" and artifact_hash and head_sha and capture_complete and history_ok)
    verified = bool(completed and output.get("verified_for_this_report", True) is not False)

    output.update(
        {
            "scanner_name": name,
            "commit_sha": head_sha,
            "exact_commit_match": bool(head_sha),
            "findings": findings,
            "findings_count": len(findings),
            "completed": completed,
            "verified": verified,
            "verified_complete": verified,
            "raw_artifact_retention_complete": bool(artifact_hash and capture_complete),
            "state": (
                "completed_with_findings"
                if completed and findings
                else "completed"
                if completed
                else status or "failed"
            ),
            "failure_reason": "" if completed else _text(
                output.get("failure_reason")
                or output.get("failure_or_unavailable_reason")
                or output.get("reason")
            ),
            "execution_contract_version": VERSION,
        }
    )
    return output


def _run_gitleaks(
    spec: ScannerToolSpec,
    workspace: WorkerWorkspace,
    runner: Callable[..., WorkerCommandResult],
) -> dict[str, Any]:
    binary = shutil.which("gitleaks")
    if binary is None:
        return _unavailable(
            spec,
            "gitleaks is not installed in the worker image.",
            source="authoritative_gitleaks_v3",
        )

    history = _history_metadata(workspace)
    full_history_verified = history.get("full_history_verified") is True
    if not full_history_verified:
        return _unavailable(
            spec,
            "A verified non-shallow Git checkout is required before Gitleaks can receive completion credit.",
            source="authoritative_gitleaks_v3",
        )

    raw = workspace.root / "scanner-raw" / "gitleaks.json"
    log = workspace.root / "scanner-output" / "gitleaks.log"
    raw.parent.mkdir(parents=True, exist_ok=True)
    command = (
        binary,
        "detect",
        "--no-banner",
        "--redact",
        "--report-format",
        "json",
        "--report-path",
        str(raw),
        "--source",
        ".",
        "--log-opts=--all",
    )
    result = _run(
        runner,
        command,
        cwd=workspace.repo_dir,
        limits=WorkerLimits(
            timeout_seconds=max(spec.timeout_seconds, 240),
            max_output_chars=max(spec.max_output_chars, 4_000_000),
        ),
        stdout_path=log,
    )

    # Gitleaks may omit or leave an empty report on a clean exit. Convert only a
    # successful, complete run into an explicit empty JSON result; every other
    # missing/empty case remains failed.
    if result.returncode == 0 and not result.timed_out:
        if not raw.exists() or not raw.read_text(encoding="utf-8", errors="replace").strip():
            raw.write_text("[]\n", encoding="utf-8")

    payload, parse_reason = _read_json(raw)
    findings = payload if isinstance(payload, list) else []
    capture_complete = isinstance(payload, list)
    blob = _raw_blob(spec.name, raw if raw.exists() else log, "json")
    record = _tool_payload(
        spec,
        result,
        findings=findings,
        capture_complete=capture_complete,
        reason=parse_reason,
        raw_blob=blob,
        execution_source="authoritative_gitleaks_v3",
        workspace=workspace,
        valid_returncodes={0, 1},
        full_history_verified=full_history_verified,
        extra={
            "history_depth": history.get("history_depth"),
            "history_commit_count": history.get("commit_count"),
            "head_sha": history.get("head_sha"),
            "clean_exit_zero_materialized_as_empty_json": result.returncode == 0 and not findings,
        },
    )
    return _normalize_record(record, workspace)


def _invoke_previous(
    previous: Callable[..., dict[str, Any]],
    spec: ScannerToolSpec,
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult],
    preparation: ProjectCommandPreparation | None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"runner": runner}
    try:
        parameters = inspect.signature(previous).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    if accepts_kwargs or "preparation" in parameters:
        kwargs["preparation"] = preparation
    return previous(spec, workspace, **kwargs)


def install_authoritative_scanner_execution_v3() -> dict[str, Any]:
    current = scanner_tool_runners.run_scanner_tool
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    def authoritative_run_scanner_tool(
        spec: ScannerToolSpec,
        workspace: WorkerWorkspace,
        *,
        runner: Callable[..., WorkerCommandResult] = scanner_tool_runners.run_command,
        preparation: ProjectCommandPreparation | None = None,
    ) -> dict[str, Any]:
        if spec.name == "bandit":
            return _normalize_record(_run_bandit(spec, workspace, runner), workspace)
        if spec.name == "gitleaks":
            return _run_gitleaks(spec, workspace, runner)
        if spec.name == "eslint":
            prepared = preparation
            if prepared is None and project_commands_allowed():
                prepared = prepare_project_commands(workspace, runner=runner)
            return _normalize_record(_run_eslint(spec, workspace, runner, prepared), workspace)
        record = _invoke_previous(
            current,
            spec,
            workspace,
            runner=runner,
            preparation=preparation,
        )
        return _normalize_record(record, workspace) if isinstance(record, dict) else record

    setattr(authoritative_run_scanner_tool, _PATCH_MARKER, True)
    setattr(authoritative_run_scanner_tool, "_nico_previous", current)
    scanner_tool_runners.run_scanner_tool = authoritative_run_scanner_tool
    return {
        "status": "installed",
        "version": VERSION,
        "bandit_output": "bounded CSV artifact",
        "gitleaks_output": "explicit JSON report with verified full history",
        "eslint_output": "generated TypeScript-aware flat config",
        "wrapper_accepts_project_preparation": True,
        "clean_scans_require_retained_artifact_hash": True,
        "failed_or_truncated_scans_treated_as_clean": False,
    }


__all__ = [
    "VERSION",
    "_normalize_record",
    "install_authoritative_scanner_execution_v3",
]
