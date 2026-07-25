from __future__ import annotations

from functools import wraps
from typing import Any, Callable

VERSION = "nico.decision_grade_scanner_executions.v1"
_MARKER = "__nico_decision_grade_scanner_executions_v1__"

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

_STATUS_ALIASES = {
    "complete": "complete",
    "completed": "complete",
    "success": "complete",
    "passed": "complete",
    "failed": "failed",
    "failure": "failed",
    "error": "failed",
    "timed_out": "timeout",
    "timed-out": "timeout",
    "timeout": "timeout",
    "unavailable": "unavailable",
    "missing": "unavailable",
    "not_available": "unavailable",
    "partial": "partial",
    "incomplete": "partial",
}


def _tool(value: Any) -> str:
    return str(value or "").strip().casefold()


def _status(value: Any) -> str:
    normalized = str(value or "").strip().casefold()
    return _STATUS_ALIASES.get(normalized, normalized or "unknown")


def _names(scan: dict[str, Any], key: str) -> list[str]:
    return sorted({_tool(item) for item in scan.get(key) or [] if _tool(item)})


def normalize_scanner_executions(scan: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with one canonical execution record per observed scanner.

    Existing structured records remain authoritative. Legacy arrays are used only to
    fill missing execution records, so reports can reconcile scanner health without
    inventing findings or upgrading incomplete evidence to success.
    """

    if not isinstance(scan, dict):
        return scan

    output = dict(scan)
    existing = scan.get("scanner_results") if isinstance(scan.get("scanner_results"), list) else []
    by_tool: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for raw in existing:
        if not isinstance(raw, dict):
            continue
        tool = _tool(raw.get("tool") or raw.get("scanner"))
        if not tool:
            continue
        item = dict(raw)
        item["tool"] = tool
        item["category"] = str(item.get("category") or _TOOL_CATEGORY.get(tool, "unknown"))
        item["status"] = _status(item.get("status"))
        item.setdefault("findings", [])
        if tool not in by_tool:
            order.append(tool)
        by_tool[tool] = item

    requested = _names(scan, "tools_requested")
    completed = _names(scan, "tools_run")
    failed = _names(scan, "failed_tools")
    timed_out = _names(scan, "timed_out_tools")
    unavailable = _names(scan, "unavailable_tools")
    optional = set(_names(scan, "optional_tools"))

    observed: list[str] = []
    for names in (requested, completed, failed, timed_out, unavailable):
        for tool in names:
            if tool not in observed:
                observed.append(tool)

    # Lowest-confidence state first. More explicit failure states override request or
    # completion arrays when legacy fields disagree.
    inferred_status: dict[str, str] = {tool: "partial" for tool in requested}
    inferred_status.update({tool: "complete" for tool in completed})
    inferred_status.update({tool: "unavailable" for tool in unavailable})
    inferred_status.update({tool: "timeout" for tool in timed_out})
    inferred_status.update({tool: "failed" for tool in failed})

    for tool in observed:
        if tool in by_tool:
            item = by_tool[tool]
            item.setdefault("required", tool not in optional)
            continue
        status = inferred_status.get(tool, "unknown")
        reason = ""
        if status == "failed":
            reason = f"{tool} was listed in failed_tools."
        elif status == "timeout":
            reason = f"{tool} was listed in timed_out_tools."
        elif status == "unavailable":
            reason = f"{tool} was listed in unavailable_tools."
        elif status == "partial":
            reason = f"{tool} was requested but no completed execution record was retained."
        item = {
            "tool": tool,
            "category": _TOOL_CATEGORY.get(tool, "unknown"),
            "status": status,
            "required": tool not in optional,
            "findings": [],
            "reason": reason,
            "source": "legacy_execution_arrays",
        }
        by_tool[tool] = item
        order.append(tool)

    records = [by_tool[tool] for tool in order]
    output["scanner_results"] = records
    output["scanner_execution_summary"] = {
        "artifact_schema": VERSION,
        "requested": len(requested),
        "structured_records": len(records),
        "complete": sum(item.get("status") == "complete" for item in records),
        "failed": sum(item.get("status") == "failed" for item in records),
        "timed_out": sum(item.get("status") == "timeout" for item in records),
        "unavailable": sum(item.get("status") == "unavailable" for item in records),
        "partial": sum(item.get("status") == "partial" for item in records),
        "required_incomplete": sum(
            item.get("required") is True and item.get("status") != "complete"
            for item in records
        ),
        "legacy_arrays_normalized": True,
    }
    return output


def wrap_scan_reader(delegate: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    if getattr(delegate, _MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(context: dict[str, Any]) -> dict[str, Any]:
        return normalize_scanner_executions(delegate(context))

    setattr(wrapped, _MARKER, True)
    return wrapped


def install_structured_scanner_executions(provider_module: Any) -> dict[str, Any]:
    current = provider_module._scan
    wrapped = wrap_scan_reader(current)
    provider_module._scan = wrapped
    return {
        "status": "installed" if wrapped is not current else "already_installed",
        "version": VERSION,
        "bound": provider_module._scan is wrapped,
        "legacy_arrays_normalized": True,
        "existing_structured_records_preserved": True,
        "missing_requested_tools_marked_partial": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_structured_scanner_executions",
    "normalize_scanner_executions",
    "wrap_scan_reader",
]
