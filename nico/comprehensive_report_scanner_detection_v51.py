from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import re
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Iterable

VERSION = "nico.comprehensive_report_finality.v51"
_PATCH_MARKER = "_nico_comprehensive_report_finality_v51"
_LOCALE: ContextVar[str] = ContextVar("nico_comprehensive_report_locale", default="en")
_SCANNER_TRUTH: ContextVar[dict[str, dict[str, Any]]] = ContextVar(
    "nico_comprehensive_scanner_truth", default={}
)

KNOWN_SCANNERS = {
    "bandit",
    "eslint",
    "gitleaks",
    "npm-audit",
    "osv-scanner",
    "pip-audit",
    "semgrep",
    "trufflehog",
    "typescript",
}

TOOL_CONTROLS = {
    "bandit": (["static"], ["static_analysis"]),
    "eslint": (["static"], ["static_analysis"]),
    "semgrep": (["static"], ["static_analysis"]),
    "typescript": (["static"], ["static_analysis"]),
    "gitleaks": (["secret"], ["secrets_review"]),
    "trufflehog": (["secret"], ["secrets_review"]),
    "npm-audit": (["dependency"], ["dependency_health"]),
    "pip-audit": (["dependency"], ["dependency_health"]),
    "osv-scanner": (["dependency"], ["dependency_health"]),
}

_STATUS_PRIORITY = {
    "unobserved": 0,
    "not_applicable": 1,
    "complete": 2,
    "partial": 3,
    "failed": 4,
    "timed_out": 5,
}

SECTION_WEIGHTS = {
    "code_audit": 0.20,
    "dependency_health": 0.15,
    "secrets_review": 0.15,
    "static_analysis": 0.15,
    "ci_cd": 0.15,
    "architecture_debt": 0.15,
    "velocity_complexity": 0.05,
}


def _text(value: Any, limit: int = 5000) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _locale(value: Any) -> str:
    normalized = _text(value, 32).replace("_", "-").casefold()
    return "es-MX" if normalized in {"es", "es-mx", "spanish", "español", "espanol"} else "en"


def _walk_strings(value: Any, depth: int = 0) -> Iterable[str]:
    if depth > 8:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            yield _text(key)
            yield from _walk_strings(item, depth + 1)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _walk_strings(item, depth + 1)
    elif value not in (None, ""):
        yield _text(value)


def _extract_report_language(identity: dict[str, Any], stage_results: dict[str, Any]) -> str:
    for candidate in (
        identity.get("report_language"),
        identity.get("language"),
        identity.get("locale"),
    ):
        if candidate:
            return _locale(candidate)
    for result in stage_results.values():
        if not isinstance(result, dict):
            continue
        for key in ("report_language", "language", "locale"):
            if result.get(key):
                return _locale(result.get(key))
        evidence = result.get("evidence")
        if isinstance(evidence, dict) and evidence.get("report_language"):
            return _locale(evidence.get("report_language"))
    for statement in _walk_strings(stage_results):
        match = re.search(r"report_language\s*[:=]\s*([A-Za-z_-]+)", statement, re.I)
        if match:
            return _locale(match.group(1))
    return "en"


def _canonical_tool(value: Any) -> str:
    normalized = _text(value, 80).casefold().replace("_", "-")
    aliases = {
        "osv": "osv-scanner",
        "osv scanner": "osv-scanner",
        "npm audit": "npm-audit",
        "pip audit": "pip-audit",
        "type-script": "typescript",
        "tsc": "typescript",
        "truffle-hog": "trufflehog",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in KNOWN_SCANNERS else ""


def _new_tool_record(tool: str) -> dict[str, Any]:
    categories, controls = TOOL_CONTROLS.get(tool, (["evidence"], ["evidence_assurance"]))
    return {
        "scanner_name": tool,
        "status": "unobserved",
        "required": tool not in {"eslint"},
        "evidence_categories_affected": list(categories),
        "score_controls_affected": list(controls),
        "confidence_impact": "No current-run structured execution record was retained.",
        "remediation_guidance": "Retain a structured exact-SHA completion record and rerun when required.",
        "source": "comprehensive_stage_reconciliation_v51",
    }


def _set_tool_status(
    records: dict[str, dict[str, Any]],
    tool: Any,
    status: str,
    *,
    message: str = "",
    required: bool | None = None,
) -> None:
    canonical = _canonical_tool(tool)
    if not canonical or status not in _STATUS_PRIORITY:
        return
    record = records.setdefault(canonical, _new_tool_record(canonical))
    current = str(record.get("status") or "unobserved")
    # Explicit not-applicable wins for ESLint configuration absence. Otherwise retain
    # the most conservative current-run status.
    if status == "not_applicable" or _STATUS_PRIORITY[status] >= _STATUS_PRIORITY.get(current, 0):
        record["status"] = status
    if required is not None:
        record["required"] = bool(required)
    if message:
        record["failure_message"] = _text(message, 1200)
    if record["status"] == "complete":
        record["confidence_impact"] = "Structured current-run execution completed against the assessed snapshot."
        record["remediation_guidance"] = None
    elif record["status"] == "not_applicable":
        record["required"] = False
        record["confidence_impact"] = "The analyzer is not applicable to the captured repository configuration."
        record["remediation_guidance"] = None
    elif record["status"] == "partial":
        record["confidence_impact"] = "The analyzer produced incomplete or unverified current-run evidence."
        record["remediation_guidance"] = "Repair structured artifact retention and rerun against the same exact SHA."
    elif record["status"] == "timed_out":
        record["timeout_state"] = True
        record["failure_type"] = "timeout"
        record["confidence_impact"] = "The analyzer timed out before a complete result was retained."
        record["remediation_guidance"] = "Increase the bounded worker budget or split the scan, then retain parseable output."
    elif record["status"] == "failed":
        record["failure_type"] = "execution_failure"
        record["confidence_impact"] = "The analyzer did not retain a complete accepted current-run result."
        record["remediation_guidance"] = "Repair the analyzer execution or artifact boundary and rerun against the same exact SHA."


def _items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,;/]", value) if item.strip()]
    return []


def _collect_structured_tool_fields(value: Any, records: dict[str, dict[str, Any]], depth: int = 0) -> None:
    if depth > 9:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = _text(key, 80).casefold()
            if normalized_key in {"tools_run", "completed_tools", "completed_scanners", "scanner_execution_completed"}:
                for tool in _items(item):
                    _set_tool_status(records, tool, "complete")
            elif normalized_key in {"failed_tools", "failed_scanners", "scanner_execution_failed"}:
                for tool in _items(item):
                    _set_tool_status(records, tool, "failed")
            elif normalized_key in {"timed_out_tools", "timedout_tools", "scanner_execution_timed_out"}:
                for tool in _items(item):
                    _set_tool_status(records, tool, "timed_out")
            elif normalized_key in {"unavailable_tools", "partial_tools", "incomplete_tools"}:
                for tool in _items(item):
                    _set_tool_status(records, tool, "partial")
            elif normalized_key in {"scanner_results", "scanner_executions", "execution_records"}:
                for scanner in _items(item) if not isinstance(item, list) else item:
                    if not isinstance(scanner, dict):
                        continue
                    tool = scanner.get("scanner") or scanner.get("scanner_name") or scanner.get("tool")
                    raw_status = _text(scanner.get("status"), 50).casefold()
                    status = {
                        "passed": "complete",
                        "success": "complete",
                        "completed": "complete",
                        "completed_clean": "complete",
                        "complete": "complete",
                        "partial": "partial",
                        "unavailable": "partial",
                        "failed": "failed",
                        "error": "failed",
                        "timeout": "timed_out",
                        "timed_out": "timed_out",
                        "not_applicable": "not_applicable",
                        "skipped_not_applicable": "not_applicable",
                    }.get(raw_status)
                    if status:
                        _set_tool_status(
                            records,
                            tool,
                            status,
                            message=scanner.get("failure_message") or scanner.get("error") or "",
                            required=scanner.get("required") if isinstance(scanner.get("required"), bool) else None,
                        )
            _collect_structured_tool_fields(item, records, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_structured_tool_fields(item, records, depth + 1)


def _scanner_truth(stage_results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    _collect_structured_tool_fields(stage_results, records)

    statements = list(_walk_strings(stage_results))
    for statement in statements:
        lowered = statement.casefold()
        for match in re.finditer(
            r"exact-snapshot\s+([a-z0-9_-]+)\s+status=(completed|completed_clean|passed|success|partial|failed|timeout|timed_out)",
            statement,
            re.I,
        ):
            status = match.group(2).casefold()
            status = "complete" if status in {"completed", "completed_clean", "passed", "success"} else "timed_out" if status in {"timeout", "timed_out"} else status
            _set_tool_status(records, match.group(1), status, message=statement)

        completed_match = re.search(r"(?:completed static tools|dedicated secret tools completed|tools completed)\s*:\s*([^.;]+)", statement, re.I)
        if completed_match:
            for tool in _items(completed_match.group(1)):
                _set_tool_status(records, tool, "complete")

        failed_match = re.search(r"(?:failed static tools|failed static analyzers|failed analyzers|failed tools)\s*:\s*([^.;]+)", statement, re.I)
        if failed_match:
            for tool in _items(failed_match.group(1)):
                _set_tool_status(records, tool, "failed", message=statement)

        unavailable_match = re.search(r"(?:unavailable tools|incomplete scanners?)\s*:\s*([^.;]+)", statement, re.I)
        if unavailable_match:
            for tool in _items(unavailable_match.group(1)):
                _set_tool_status(records, tool, "partial", message=statement)

        if "bandit evidence unavailable" in lowered or ("bandit" in lowered and "output exceeded the bounded capture limit" in lowered):
            _set_tool_status(records, "bandit", "failed", message=statement, required=True)
        if "osv" in lowered and any(token in lowered for token in ("did not produce a complete result", "partial result", "incomplete osv")):
            _set_tool_status(records, "osv-scanner", "partial", message=statement)
        if "gitleaks" in lowered and any(token in lowered for token in ("incomplete", "unavailable", "did not complete", "failed")):
            _set_tool_status(records, "gitleaks", "partial", message=statement)
        if "eslint" in lowered and any(token in lowered for token in ("no eslint configuration", "not applicable", "not configured")):
            _set_tool_status(records, "eslint", "not_applicable", message=statement, required=False)

    # Only expose observed analyzers. The report must not imply that an unrelated
    # analyzer was required merely because it exists in NICO's global tool catalog.
    return {tool: record for tool, record in sorted(records.items()) if record.get("status") != "unobserved"}



__all__ = ["VERSION", "_extract_report_language", "_locale", "_scanner_truth", "_text", "_walk_strings"]
