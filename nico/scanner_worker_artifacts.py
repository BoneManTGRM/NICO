from __future__ import annotations

from collections import Counter
from typing import Any

STATIC_TOOLS = ("bandit", "semgrep", "eslint", "typescript")
SECRET_TOOLS = ("gitleaks", "trufflehog")
ALL_TOOLS = STATIC_TOOLS + SECRET_TOOLS


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _tool_payloads(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_tools = payload.get("tools") or payload.get("results") or {}
    if isinstance(raw_tools, dict):
        return {str(name).lower(): data if isinstance(data, dict) else {"raw": data} for name, data in raw_tools.items()}
    if isinstance(raw_tools, list):
        parsed: dict[str, dict[str, Any]] = {}
        for item in raw_tools:
            if not isinstance(item, dict):
                continue
            name = str(item.get("tool") or item.get("name") or "").lower().strip()
            if name:
                parsed[name] = item
        return parsed
    return {}


def _finding_items(tool_data: dict[str, Any]) -> list[Any]:
    for key in ("findings", "issues", "results", "vulnerabilities"):
        value = tool_data.get(key)
        if isinstance(value, list):
            return value
    count = tool_data.get("finding_count") or tool_data.get("findings_count") or tool_data.get("issue_count")
    if isinstance(count, int) and count > 0:
        return [{} for _ in range(count)]
    return []


def _severity_counts(findings: list[Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for finding in findings:
        severity = "unknown"
        if isinstance(finding, dict):
            severity = str(
                finding.get("severity")
                or finding.get("level")
                or finding.get("issue_severity")
                or "unknown"
            ).lower()
        counts[severity] += 1
    return dict(counts)


def normalize_scanner_worker_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize sandboxed scanner output into evidence NICO can score safely.

    The worker is allowed to evolve its raw tool output, but hosted scoring should only
    consume this small normalized shape. Missing tools stay explicit instead of being
    treated as clean evidence.
    """
    tools = _tool_payloads(payload)
    normalized_tools: dict[str, dict[str, Any]] = {}
    for tool in ALL_TOOLS:
        tool_data = tools.get(tool) or {}
        findings = _finding_items(tool_data)
        status = str(tool_data.get("status") or ("completed" if tool_data else "unavailable")).lower()
        normalized_tools[tool] = {
            "status": status,
            "completed": status in {"completed", "success", "ok", "passed"},
            "finding_count": len(findings),
            "severity_counts": _severity_counts(findings),
        }

    static_completed = [tool for tool in STATIC_TOOLS if normalized_tools[tool]["completed"]]
    secret_completed = [tool for tool in SECRET_TOOLS if normalized_tools[tool]["completed"]]
    static_findings = sum(normalized_tools[tool]["finding_count"] for tool in STATIC_TOOLS)
    secret_findings = sum(normalized_tools[tool]["finding_count"] for tool in SECRET_TOOLS)

    return {
        "artifact_schema": "nico.scanner_worker.v1",
        "static_tools_completed": static_completed,
        "secret_tools_completed": secret_completed,
        "missing_static_tools": [tool for tool in STATIC_TOOLS if tool not in static_completed],
        "missing_secret_tools": [tool for tool in SECRET_TOOLS if tool not in secret_completed],
        "static_finding_count": static_findings,
        "secret_finding_count": secret_findings,
        "tools": normalized_tools,
        "static_evidence_complete": len(static_completed) == len(STATIC_TOOLS),
        "secret_evidence_complete": len(secret_completed) == len(SECRET_TOOLS),
    }


def scanner_worker_evidence_notes(payload: dict[str, Any]) -> dict[str, list[str]]:
    normalized = normalize_scanner_worker_artifact(payload)
    evidence: list[str] = []
    findings: list[str] = []
    unavailable: list[str] = []

    if normalized["static_tools_completed"]:
        evidence.append("Scanner-worker static tools completed: " + ", ".join(normalized["static_tools_completed"]) + ".")
    if normalized["secret_tools_completed"]:
        evidence.append("Scanner-worker secret tools completed: " + ", ".join(normalized["secret_tools_completed"]) + ".")

    if normalized["static_finding_count"]:
        findings.append(f"Scanner-worker static tools reported {normalized['static_finding_count']} finding(s).")
    if normalized["secret_finding_count"]:
        findings.append(f"Scanner-worker secret tools reported {normalized['secret_finding_count']} finding(s).")

    if normalized["missing_static_tools"]:
        unavailable.append("Scanner-worker static tools unavailable: " + ", ".join(normalized["missing_static_tools"]) + ".")
    if normalized["missing_secret_tools"]:
        unavailable.append("Scanner-worker secret tools unavailable: " + ", ".join(normalized["missing_secret_tools"]) + ".")

    return {"evidence": evidence, "findings": findings, "unavailable": unavailable}
