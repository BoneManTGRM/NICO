from __future__ import annotations

from collections import Counter
from typing import Any

DEPENDENCY_TOOLS = ("pip-audit", "npm-audit", "osv-scanner")
STATIC_TOOLS = ("bandit", "semgrep", "eslint", "typescript")
SECRET_TOOLS = ("gitleaks", "trufflehog")
COVERAGE_TOOLS = ("coverage",)
ALL_TOOLS = DEPENDENCY_TOOLS + STATIC_TOOLS + SECRET_TOOLS + COVERAGE_TOOLS
COMPLETED_STATUSES = {"completed", "success", "ok", "passed", "completed_clean", "clean", "no_findings"}


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
            name = str(item.get("tool") or item.get("scanner") or item.get("name") or "").lower().strip()
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


def _finding_count_from_payload(tool_data: dict[str, Any], fallback_items: list[Any]) -> int:
    for key in ("finding_count", "findings_count", "issue_count", "vulnerability_count"):
        value = tool_data.get(key)
        if isinstance(value, int):
            return max(0, value)
    return len(fallback_items)


def _severity_counts(findings: list[Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for finding in findings:
        severity = "unknown"
        if isinstance(finding, dict):
            severity = str(
                finding.get("severity")
                or finding.get("level")
                or finding.get("issue_severity")
                or finding.get("confidence")
                or "unknown"
            ).lower()
        counts[severity] += 1
    return dict(counts)


def _completed_tools(normalized_tools: dict[str, dict[str, Any]], tools: tuple[str, ...]) -> list[str]:
    return [tool for tool in tools if normalized_tools[tool]["completed"]]


def _finding_count(normalized_tools: dict[str, dict[str, Any]], tools: tuple[str, ...]) -> int:
    return sum(normalized_tools[tool]["finding_count"] for tool in tools)


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
            "completed": status in COMPLETED_STATUSES,
            "finding_count": _finding_count_from_payload(tool_data, findings),
            "severity_counts": _severity_counts(findings),
            "artifact_hash": tool_data.get("artifact_hash"),
            "execution_source": tool_data.get("execution_source"),
            "run_id": tool_data.get("run_id"),
            "generated_at": tool_data.get("generated_at") or tool_data.get("timestamp"),
        }

    dependency_completed = _completed_tools(normalized_tools, DEPENDENCY_TOOLS)
    static_completed = _completed_tools(normalized_tools, STATIC_TOOLS)
    secret_completed = _completed_tools(normalized_tools, SECRET_TOOLS)
    coverage_completed = _completed_tools(normalized_tools, COVERAGE_TOOLS)

    return {
        "artifact_schema": "nico.scanner_worker.v1",
        "dependency_tools_completed": dependency_completed,
        "static_tools_completed": static_completed,
        "secret_tools_completed": secret_completed,
        "coverage_tools_completed": coverage_completed,
        "missing_dependency_tools": [tool for tool in DEPENDENCY_TOOLS if tool not in dependency_completed],
        "missing_static_tools": [tool for tool in STATIC_TOOLS if tool not in static_completed],
        "missing_secret_tools": [tool for tool in SECRET_TOOLS if tool not in secret_completed],
        "missing_coverage_tools": [tool for tool in COVERAGE_TOOLS if tool not in coverage_completed],
        "dependency_finding_count": _finding_count(normalized_tools, DEPENDENCY_TOOLS),
        "static_finding_count": _finding_count(normalized_tools, STATIC_TOOLS),
        "secret_finding_count": _finding_count(normalized_tools, SECRET_TOOLS),
        "coverage_finding_count": _finding_count(normalized_tools, COVERAGE_TOOLS),
        "tools": normalized_tools,
        "dependency_evidence_complete": len(dependency_completed) == len(DEPENDENCY_TOOLS),
        "static_evidence_complete": len(static_completed) == len(STATIC_TOOLS),
        "secret_evidence_complete": len(secret_completed) == len(SECRET_TOOLS),
        "coverage_evidence_complete": len(coverage_completed) == len(COVERAGE_TOOLS),
    }


def scanner_worker_evidence_notes(payload: dict[str, Any]) -> dict[str, list[str]]:
    normalized = normalize_scanner_worker_artifact(payload)
    evidence: list[str] = []
    findings: list[str] = []
    unavailable: list[str] = []

    if normalized["dependency_tools_completed"]:
        evidence.append("Scanner-worker dependency tools completed: " + ", ".join(normalized["dependency_tools_completed"]) + ".")
    if normalized["static_tools_completed"]:
        evidence.append("Scanner-worker static tools completed: " + ", ".join(normalized["static_tools_completed"]) + ".")
    if normalized["secret_tools_completed"]:
        evidence.append("Scanner-worker secret tools completed: " + ", ".join(normalized["secret_tools_completed"]) + ".")
    if normalized["coverage_tools_completed"]:
        evidence.append("Scanner-worker coverage tools completed: " + ", ".join(normalized["coverage_tools_completed"]) + ".")

    if normalized["dependency_finding_count"]:
        findings.append(f"Scanner-worker dependency tools reported {normalized['dependency_finding_count']} finding(s).")
    if normalized["static_finding_count"]:
        findings.append(f"Scanner-worker static tools reported {normalized['static_finding_count']} finding(s).")
    if normalized["secret_finding_count"]:
        findings.append(f"Scanner-worker secret tools reported {normalized['secret_finding_count']} finding(s).")
    if normalized["coverage_finding_count"]:
        findings.append(f"Scanner-worker coverage tools reported {normalized['coverage_finding_count']} finding(s).")

    if normalized["missing_dependency_tools"]:
        unavailable.append("Scanner-worker dependency tools unavailable: " + ", ".join(normalized["missing_dependency_tools"]) + ".")
    if normalized["missing_static_tools"]:
        unavailable.append("Scanner-worker static tools unavailable: " + ", ".join(normalized["missing_static_tools"]) + ".")
    if normalized["missing_secret_tools"]:
        unavailable.append("Scanner-worker secret tools unavailable: " + ", ".join(normalized["missing_secret_tools"]) + ".")
    if normalized["missing_coverage_tools"]:
        unavailable.append("Scanner-worker coverage tools unavailable: " + ", ".join(normalized["missing_coverage_tools"]) + ".")

    return {"evidence": evidence, "findings": findings, "unavailable": unavailable}
