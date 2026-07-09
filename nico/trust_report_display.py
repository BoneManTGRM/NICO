from __future__ import annotations

from typing import Any

CRITICAL_SECTIONS = ("dependency_health", "static_analysis", "secrets_review")
REQUIRED_COVERAGE_SECTIONS = ("dependency_health", "static_analysis", "secrets_review")


def _section_map(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sections: dict[str, dict[str, Any]] = {}
    for section in result.get("sections", []) or []:
        if isinstance(section, dict) and section.get("id"):
            sections[str(section["id"])] = section
    return sections


def _score(result: dict[str, Any]) -> int | None:
    signal = result.get("maturity_signal")
    if not isinstance(signal, dict):
        return None
    try:
        return int(signal.get("score"))
    except (TypeError, ValueError):
        return None


def _coverage(result: dict[str, Any]) -> dict[str, Any]:
    ledger = result.get("evidence_ledger")
    if isinstance(ledger, dict) and isinstance(ledger.get("coverage_by_section"), dict):
        return ledger["coverage_by_section"]
    return {}


def _missing_coverage(result: dict[str, Any]) -> dict[str, list[str]]:
    coverage = _coverage(result)
    missing: dict[str, list[str]] = {}
    for section_id in REQUIRED_COVERAGE_SECTIONS:
        data = coverage.get(section_id)
        if not isinstance(data, dict):
            missing[section_id] = ["coverage ledger unavailable"]
            continue
        missing_tools = data.get("missing_required_tools")
        if isinstance(missing_tools, list) and missing_tools:
            missing[section_id] = [str(item) for item in missing_tools]
    return missing


def _trust_violations(result: dict[str, Any]) -> list[dict[str, Any]]:
    trust_engine = result.get("trust_engine")
    if isinstance(trust_engine, dict) and isinstance(trust_engine.get("violations"), list):
        return [item for item in trust_engine["violations"] if isinstance(item, dict)]
    return []


def _export_blocked(result: dict[str, Any]) -> bool:
    gate = result.get("export_truth_gate")
    if not isinstance(gate, dict):
        return False
    return gate.get("export_allowed") is False or gate.get("status") == "failed"


def _critical_not_green(result: dict[str, Any]) -> dict[str, str]:
    sections = _section_map(result)
    not_green: dict[str, str] = {}
    for section_id in CRITICAL_SECTIONS:
        section = sections.get(section_id)
        status = str(section.get("status") if section else "missing")
        if status != "green":
            not_green[section_id] = status
    return not_green


def _scanner_status(result: dict[str, Any]) -> str:
    guards = result.get("report_quality_guards")
    if not isinstance(guards, dict):
        return "unknown"
    scanner = guards.get("scanner_artifact_integration")
    if not isinstance(scanner, dict):
        return "unknown"
    return str(scanner.get("status") or "unknown")


def _why_not_higher(result: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    missing = _missing_coverage(result)
    for section_id, tools in missing.items():
        label = {
            "dependency_health": "Dependency",
            "static_analysis": "Static Analysis",
            "secrets_review": "Secrets",
        }.get(section_id, section_id)
        reasons.append(f"{label} required proof incomplete: {', '.join(tools)}.")
    for section, status in _critical_not_green(result).items():
        label = {
            "dependency_health": "Dependency",
            "static_analysis": "Static Analysis",
            "secrets_review": "Secrets",
        }.get(section, section)
        reasons.append(f"{label} is {status.upper()}, not client-clean GREEN.")
    for violation in _trust_violations(result):
        section = violation.get("section") or "Report"
        reason = violation.get("reason") or "strict trust rule applied"
        reasons.append(f"{section}: {reason}.")
    if _scanner_status(result) == "missing":
        reasons.append("Scanner artifact integration is missing for this report run.")
    if _export_blocked(result):
        reasons.append("Export Truth Gate blocked client-facing artifacts.")
    return list(dict.fromkeys(reasons))[:8]


def _path_to_verified(result: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    missing = _missing_coverage(result)
    if missing.get("dependency_health"):
        steps.append("Attach current-run clean pip-audit, npm audit, and OSV/OSV Scanner evidence.")
    if missing.get("static_analysis"):
        steps.append("Attach current-run Bandit, Semgrep, ESLint, and TypeScript evidence with zero blockers or approved triage.")
    if missing.get("secrets_review"):
        steps.append("Attach current-run full-history gitleaks and trufflehog evidence with zero high-confidence credentials.")
    if _critical_not_green(result):
        steps.append("Resolve or formally triage every YELLOW/RED critical section before client-clean delivery.")
    if _scanner_status(result) == "missing":
        steps.append("Attach the scanner-worker artifact bundle to the exact report run.")
    if _export_blocked(result):
        steps.append("Rebuild Markdown/HTML/PDF after final QA and pass the Export Truth Gate.")
    if not steps:
        steps.append("Keep evidence ledger, scanner artifact bundle, and export truth gate attached to preserve verified status.")
    return steps


def _computed_trust_level(result: dict[str, Any]) -> str:
    if _export_blocked(result):
        return "Draft only"
    reasons = _why_not_higher(result)
    if _trust_violations(result) or _critical_not_green(result):
        return "Review-limited"
    if _missing_coverage(result):
        return "Evidence-bound"
    if _scanner_status(result) == "attached":
        return "Verified"
    if reasons:
        return "Evidence-bound"
    return str(result.get("trust_level") or "Evidence-bound")


def _client_delivery_status(trust_level: str) -> str:
    if trust_level == "Verified":
        return "Client-ready after human approval"
    if trust_level == "Evidence-bound":
        return "Evidence-bound but not fully verified"
    if trust_level == "Review-limited":
        return "Human Review Required"
    return "Draft only — not client-ready"


def _summary_text(display: dict[str, Any]) -> str:
    return (
        f"Trust Level: {display['trust_level']}. "
        f"Client Delivery: {display['client_delivery_status']}. "
        f"Score: {display.get('score', 'unknown')}/100."
    )


def _attach_display_section(result: dict[str, Any], display: dict[str, Any]) -> None:
    sections = [
        section
        for section in result.get("sections", []) or []
        if not (isinstance(section, dict) and section.get("id") == "trust_readiness")
    ]
    sections.insert(
        0,
        {
            "id": "trust_readiness",
            "label": "Trust & Client Readiness",
            "status": "green" if display["trust_level"] == "Verified" else "yellow" if display["trust_level"] in {"Evidence-bound", "Review-limited"} else "red",
            "score": 0,
            "scoring_weight": 0,
            "supplemental": True,
            "summary": _summary_text(display),
            "evidence": [
                f"Trust Level: {display['trust_level']}",
                f"Client Delivery: {display['client_delivery_status']}",
                f"Evidence Ledger: {display['evidence_ledger_status']}",
                f"Scanner Artifact Integration: {display['scanner_artifact_status']}",
                f"Export Truth Gate: {display['export_truth_gate_status']}",
            ],
            "findings": display["why_not_higher"] or ["No trust display blockers found."],
            "unavailable": [] if display["trust_level"] == "Verified" else ["Verified client-clean status requires all critical evidence to remain attached and clean."],
        },
    )
    result["sections"] = sections


def attach_trust_report_display(result: dict[str, Any]) -> dict[str, Any]:
    """Attach plain-English trust status and next steps to report output."""

    if result.get("status") != "complete":
        return result
    trust_level = _computed_trust_level(result)
    ledger = result.get("evidence_ledger") if isinstance(result.get("evidence_ledger"), dict) else {}
    export_gate = result.get("export_truth_gate") if isinstance(result.get("export_truth_gate"), dict) else {}
    display = {
        "version": "trust-report-display-v1",
        "trust_level": trust_level,
        "client_delivery_status": _client_delivery_status(trust_level),
        "score": _score(result),
        "why_not_higher": _why_not_higher(result),
        "path_to_verified": _path_to_verified(result),
        "evidence_ledger_status": str(ledger.get("status") or "missing"),
        "scanner_artifact_status": _scanner_status(result),
        "export_truth_gate_status": str(export_gate.get("status") or "pending"),
    }
    result["trust_level"] = trust_level
    result["client_delivery_status"] = display["client_delivery_status"]
    result["trust_report_display"] = display
    result.setdefault("report_quality_guards", {})["trust_report_display"] = {
        "status": "attached",
        "trust_level": trust_level,
        "client_delivery_status": display["client_delivery_status"],
    }
    _attach_display_section(result, display)

    quick_wins = list(result.get("quick_wins") or [])
    for item in display["path_to_verified"][:3]:
        if item not in quick_wins:
            quick_wins.append(item)
    result["quick_wins"] = quick_wins
    return result
