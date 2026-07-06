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
    passed = sum(1 for item in items if item.get("status") == "passed")
    failed = sum(1 for item in items if item.get("status") in {"failed", "error", "timeout"})
    unavailable = sum(1 for item in items if item.get("status") == "unavailable")
    base = 40 + passed * 9 - failed * 14 - unavailable * 5
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
        name = str(item.get("scanner") or "scanner")
        state = str(item.get("status") or "unknown")
        sources.add(SCANNER_SOURCE_MAP.get(name, "scanner_worker"))
        summary = str(item.get("evidence_summary") or item.get("command_intent") or "No scanner summary returned.")[:500]
        evidence.append(f"Scanner worker result: {name} status={state}; {summary}")
        if state in {"failed", "error", "timeout"}:
            findings.append(f"{name} returned {state}; review scanner output before client-final claims.")
        if state == "unavailable":
            unavailable.append(f"{name} was unavailable: {'; '.join(map(str, item.get('unavailable_data_notes') or [])) or 'tool did not run'}")
    score = _score_from_results(items)
    has_unavailable = any(item.get("status") == "unavailable" for item in items)
    return {
        "id": "scanner_worker_evidence",
        "label": "Scanner Worker Evidence",
        "score": score,
        "status": _status(score, has_unavailable),
        "summary": "Controlled scanner-worker output is folded into report evidence when a scanner run is attached to the report payload.",
        "evidence": evidence,
        "findings": findings,
        "unavailable": unavailable,
        "evidence_sources": sorted(sources),
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
    return output
