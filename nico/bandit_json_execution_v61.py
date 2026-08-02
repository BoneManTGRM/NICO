from __future__ import annotations

import shutil
from functools import wraps
from typing import Any, Callable

from nico import scanner_evidence_pipeline_v1 as pipeline
from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace

VERSION = "nico.bandit_json_execution.v62"
_MARKER = "_nico_bandit_json_execution_v61"
_PROBLEM_MARKER = "_nico_bandit_json_problem_dispatch_v62"
_EXCLUDES = (
    ".git",
    ".next",
    ".venv",
    "__pycache__",
    "audit-results",
    "build",
    "coverage",
    "coverage_html",
    "dist",
    "example",
    "examples",
    "fixture",
    "fixtures",
    "generated",
    "node_modules",
    "sample",
    "samples",
    "test",
    "tests",
    "vendor",
    "vendors",
    "venv",
)


def _findings(payload: Any) -> tuple[list[dict[str, Any]], str]:
    if not isinstance(payload, dict):
        return [], "Bandit JSON output is not an object."
    results = payload.get("results")
    if not isinstance(results, list):
        return [], "Bandit JSON output did not retain a results list."
    findings = [dict(item) for item in results if isinstance(item, dict)]
    if len(findings) != len(results):
        return [], "Bandit JSON results contained a non-object finding."
    return findings, ""


def run_bandit_json(
    spec: ScannerToolSpec,
    workspace: WorkerWorkspace,
    runner: Callable[..., WorkerCommandResult],
) -> dict[str, Any]:
    """Run Bandit with a bounded parseable JSON artifact on the exact snapshot."""

    binary = shutil.which("bandit")
    if binary is None:
        return pipeline._unavailable(
            spec,
            "bandit is not installed in the worker image.",
            source="canonical_bandit_json_v62",
        )

    raw = workspace.root / "scanner-raw" / "bandit.json"
    log = workspace.root / "scanner-output" / "bandit.log"
    raw.parent.mkdir(parents=True, exist_ok=True)
    command = (
        binary,
        "-r",
        ".",
        "-f",
        "json",
        "-o",
        str(raw),
        "-x",
        ",".join(_EXCLUDES),
    )
    result = pipeline._run(
        runner,
        command,
        cwd=workspace.repo_dir,
        limits=WorkerLimits(
            timeout_seconds=max(spec.timeout_seconds, 360),
            max_output_chars=max(spec.max_output_chars, 4_000_000),
        ),
        stdout_path=log,
    )
    payload, parse_reason = pipeline._read_json(raw)
    findings, shape_reason = _findings(payload)
    reason = parse_reason or shape_reason
    capture_complete = not reason
    blob = pipeline._raw_blob(
        spec.name,
        raw if raw.exists() else log,
        "json",
    )
    return pipeline._tool_payload(
        spec,
        result,
        findings=findings,
        capture_complete=capture_complete,
        reason=reason,
        raw_blob=blob,
        execution_source="canonical_bandit_json_v62",
        workspace=workspace,
        valid_returncodes={0, 1},
        extra={
            "bandit_json_contract": True,
            "bandit_csv_parser_used": False,
            "explicit_exclusion_count": len(_EXCLUDES),
            "production_source_scope": True,
            "compact_complete_result": True,
        },
    )


def _bind_problem_dispatch() -> bool:
    """Bind JSON execution at the function imported by scanner authority modules.

    The production snapshot authority imports ``_run_problem_tool`` by value after the
    NICO package installers run. Patching only ``_run_bandit`` was vulnerable to a
    later compatibility installer restoring the CSV delegate. Binding the dispatch
    function itself makes Bandit JSON authoritative even if a stale named delegate is
    subsequently assigned.
    """

    current = pipeline._run_problem_tool
    if getattr(current, _PROBLEM_MARKER, False):
        return True

    @wraps(current)
    def dispatch(
        spec: ScannerToolSpec,
        workspace: WorkerWorkspace,
        runner: Callable[..., WorkerCommandResult],
        preparation: Any,
    ) -> dict[str, Any]:
        if spec.name == "bandit":
            return run_bandit_json(spec, workspace, runner)
        return current(spec, workspace, runner, preparation)

    setattr(dispatch, _PROBLEM_MARKER, True)
    setattr(dispatch, "_nico_previous", current)
    pipeline._run_problem_tool = dispatch
    return pipeline._run_problem_tool is dispatch


def install_bandit_json_execution_v61() -> dict[str, Any]:
    current = pipeline._run_bandit
    if not getattr(current, _MARKER, False):
        setattr(run_bandit_json, _MARKER, True)
        setattr(run_bandit_json, "_nico_previous", current)
        pipeline._run_bandit = run_bandit_json

    named_delegate_bound = pipeline._run_bandit is run_bandit_json or bool(
        getattr(pipeline._run_bandit, _MARKER, False)
    )
    problem_dispatch_bound = _bind_problem_dispatch()
    bound = named_delegate_bound and problem_dispatch_bound
    return {
        "status": "installed" if bound else "blocked",
        "version": VERSION,
        "bound": bound,
        "named_bandit_delegate_bound": named_delegate_bound,
        "problem_dispatch_bound": problem_dispatch_bound,
        "output_format": "json",
        "csv_field_limit_dependency_removed": True,
        "full_report_artifact_retained": True,
        "findings_preserved": True,
        "rules_skipped": False,
        "authoritative_snapshot_import_path_bound": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_bandit_json_execution_v61",
    "run_bandit_json",
]
