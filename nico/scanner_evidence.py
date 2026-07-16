from __future__ import annotations

from copy import deepcopy
from typing import Any

SCANNER_SOURCE_MAP = {
    "pip-audit": "dependency_intelligence",
    "npm-audit": "dependency_intelligence",
    "osv-scanner": "dependency_intelligence",
    "semgrep": "static_analysis",
    "bandit": "static_analysis",
    "eslint": "static_analysis",
    "typescript": "static_analysis",
    "gitleaks": "secret_scanning",
    "trufflehog": "secret_scanning",
    "coverage": "test_execution",
    "pytest": "test_execution",
    "npm-test": "test_execution",
    "npm-build": "build_execution",
}


def _scanner_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    run = payload.get("scanner_run") or payload.get("scanner") or {}
    direct = payload.get("scanner_results") or []
    if isinstance(run, dict) and isinstance(run.get("scanner_results"), list):
        direct = run["scanner_results"]
    return [item for item in direct if isinstance(item, dict)]


def _score_from_results(items: list[dict[str, Any]]) -> int:
    if not items:
        return 0
    completed = sum(1 for item in items if item.get("status") in {"completed", "passed"})
    failed = sum(1 for item in items if item.get("status") in {"failed", "error", "timeout"})
    unavailable = sum(1 for item in items if item.get("status") == "unavailable")
    findings = sum(len(item.get("findings") or []) for item in items if isinstance(item.get("findings"), list))
    base = 42 + completed * 7 - failed * 14 - unavailable * 5 - min(24, findings * 2)
    return max(25, min(92, base))


def _status(score: int, unavailable: bool) -> str:
    if unavailable and score < 45:
        return "gray"
    if score >= 75:
        return "green"
    if score >= 45:
        return "yellow"
    return "red"


def scanner_section(payload: dict[str, Any]) -> dict[str, Any] | None:
    items = _scanner_items(payload)
    if not items:
        return None
    evidence: list[str] = []
    findings: list[str] = []
    unavailable: list[str] = []
    sources: set[str] = set()
    for item in items:
        name = str(item.get("tool") or item.get("scanner") or "scanner")
        state = str(item.get("status") or "unknown")
        sources.add(SCANNER_SOURCE_MAP.get(name, "scanner_worker"))
        item_findings = item.get("findings") if isinstance(item.get("findings"), list) else []
        summary = str(
            item.get("evidence_summary")
            or item.get("command_intent")
            or item.get("reason")
            or f"findings={len(item_findings)}"
        )[:500]
        evidence.append(f"Scanner worker result: {name} status={state}; findings={len(item_findings)}; {summary}")
        if state in {"failed", "error", "timeout"}:
            findings.append(f"{name} returned {state}; review scanner output before client-final claims.")
        elif state == "completed" and item_findings:
            findings.append(f"{name} returned {len(item_findings)} finding(s) requiring human triage.")
        if state == "unavailable":
            unavailable.append(
                f"{name} was unavailable: "
                f"{'; '.join(map(str, item.get('unavailable_data_notes') or [])) or str(item.get('reason') or 'tool did not run')}"
            )
    score = _score_from_results(items)
    has_unavailable = any(item.get("status") == "unavailable" for item in items)
    diagnostic_status = _status(score, has_unavailable)
    return {
        "id": "scanner_worker_evidence",
        "label": "Exact-Snapshot Scanner Evidence",
        "score": score,
        "status": "gray",
        "diagnostic_status": diagnostic_status,
        "scoring_weight": 0,
        "supplemental": True,
        "score_impact": "diagnostic_only",
        "summary": "The scanner suite executed against the exact commit captured for this Express run. Its output is attached as supplemental diagnostic evidence and mapped into the relevant core evidence sections without silently inflating the overall maturity score.",
        "evidence": evidence,
        "findings": findings,
        "unavailable": unavailable,
        "evidence_sources": sorted(sources | {"scanner_worker"}),
        "unavailable_sources": ["scanner_worker"] if has_unavailable else [],
        "required_sources": ["scanner_worker"],
        "human_review_required": True,
    }


def enrich_payload_with_scanner_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(payload)
    section = scanner_section(output)
    if not section:
        return output
    sections = [item for item in output.get("sections", []) or [] if isinstance(item, dict)]
    sections = [item for item in sections if item.get("id") != section["id"]]
    sections.append(section)
    output["sections"] = sections
    output.setdefault("evidence_readiness", {})["scanner_worker_attached"] = True
    output.setdefault("evidence_readiness", {})["scanner_worker_scoring_mode"] = "supplemental_diagnostic_with_core_source_mapping"
    return output
