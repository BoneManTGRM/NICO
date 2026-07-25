from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.decision_grade_scanner_execution.v1"
_MARKER = "__nico_decision_grade_scanner_execution_v1__"

_TOOL_CATEGORY = {
    "pip-audit": "dependency",
    "npm-audit": "dependency",
    "osv-scanner": "dependency",
    "bandit": "static",
    "semgrep": "static",
    "eslint": "static",
    "typescript": "static",
    "gitleaks": "secret",
    "trufflehog": "secret",
}


def _text(value: Any, limit: int = 500) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({_text(item, 120).casefold() for item in value if _text(item, 120)})


def _scanner_payload(stage: dict[str, Any]) -> dict[str, Any]:
    scanner = stage.get("scanner")
    if isinstance(scanner, dict):
        return scanner
    evidence = stage.get("evidence")
    if isinstance(evidence, dict):
        nested = evidence.get("scanner")
        if isinstance(nested, dict):
            return nested
    return stage


def _status_for(tool: str, *, run: set[str], failed: set[str], timed_out: set[str], unavailable: set[str]) -> str:
    if tool in timed_out:
        return "timed_out"
    if tool in failed:
        return "failed"
    if tool in unavailable:
        return "partial"
    if tool in run:
        return "complete"
    return "partial"


def scanner_results_from_stage(stage: dict[str, Any]) -> list[dict[str, Any]]:
    payload = _scanner_payload(stage)
    requested = set(_names(payload.get("tools_requested")))
    run = set(_names(payload.get("tools_run")))
    failed = set(_names(payload.get("failed_tools")))
    timed_out = set(_names(payload.get("timed_out_tools")))
    unavailable = set(_names(payload.get("unavailable_tools")))
    tools = sorted(requested | run | failed | timed_out | unavailable)
    if not tools:
        return []
    messages = payload.get("tool_messages") if isinstance(payload.get("tool_messages"), dict) else {}
    required_tools = set(_names(payload.get("required_tools")))
    optional_tools = set(_names(payload.get("optional_tools")))
    output: list[dict[str, Any]] = []
    for tool in tools:
        status = _status_for(tool, run=run, failed=failed, timed_out=timed_out, unavailable=unavailable)
        reason = _text(messages.get(tool), 500)
        if not reason and status == "failed":
            reason = "Scanner execution failed before complete structured evidence was retained."
        elif not reason and status == "timed_out":
            reason = "Scanner execution exceeded the bounded timeout."
        elif not reason and status == "partial":
            reason = "Scanner evidence was unavailable or incomplete for this run."
        output.append(
            {
                "tool": tool,
                "status": status,
                "required": tool in required_tools or tool not in optional_tools,
                "category": _TOOL_CATEGORY.get(tool, "unknown"),
                "failure_type": (
                    "timeout" if status == "timed_out" else "execution_failure" if status == "failed" else "evidence_incomplete" if status == "partial" else None
                ),
                "reason": reason or None,
                "retry_count": int(payload.get("retry_count") or 0),
                "started_at": payload.get("started_at"),
                "finished_at": payload.get("finished_at"),
            }
        )
    return output


def normalize_scanner_stage_summaries(stage_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = deepcopy(stage_summaries)
    for stage in output:
        if not isinstance(stage, dict):
            continue
        existing = [item for item in stage.get("scanner_results") or [] if isinstance(item, dict)]
        generated = scanner_results_from_stage(stage)
        seen = {
            (_text(item.get("tool") or item.get("scanner"), 120).casefold(), _text(item.get("status"), 40).casefold())
            for item in existing
        }
        for item in generated:
            key = (_text(item.get("tool"), 120).casefold(), _text(item.get("status"), 40).casefold())
            if key not in seen:
                existing.append(item)
                seen.add(key)
        if existing:
            stage["scanner_results"] = existing
    return output


def wrap_contract_builder(delegate: Callable[..., Any]) -> Callable[..., Any]:
    if getattr(delegate, _MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        raw = kwargs.get("stage_summaries")
        if isinstance(raw, list):
            kwargs = dict(kwargs)
            kwargs["stage_summaries"] = normalize_scanner_stage_summaries(raw)
        return delegate(*args, **kwargs)

    setattr(wrapped, _MARKER, True)
    return wrapped


def install_decision_grade_scanner_execution(report_module: Any) -> dict[str, Any]:
    current = report_module.build_decision_grade_contract
    wrapped = wrap_contract_builder(current)
    report_module.build_decision_grade_contract = wrapped
    return {
        "status": "installed" if wrapped is not current else "already_installed",
        "version": VERSION,
        "bound": report_module.build_decision_grade_contract is wrapped,
        "scanner_suite_arrays_normalized": True,
        "completed_failed_timed_out_and_partial_states_supported": True,
        "technical_score_change_allowed": False,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "scanner_results_from_stage",
    "normalize_scanner_stage_summaries",
    "wrap_contract_builder",
    "install_decision_grade_scanner_execution",
]
