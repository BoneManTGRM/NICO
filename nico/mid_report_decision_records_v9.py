from __future__ import annotations

from hashlib import sha256
from typing import Any


VERSION = "mid_report_decision_records_v9"
REQUIRED_FIELDS = (
    "finding_id", "classification", "severity", "priority", "confidence",
    "verification_state", "business_impact", "technical_impact", "affected_systems",
    "exact_evidence", "root_cause", "failure_scenario", "repair", "owner", "effort",
    "dependencies", "verification", "rollback", "acceptance_criteria", "deferred_risk",
    "target_window", "related_findings", "limitations", "approval_boundary",
)


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, fallback: str = "Not established from retained evidence") -> str:
    text = " ".join(str(value or "").split())
    return text or fallback


def _classification(text: str) -> str:
    lowered = text.lower()
    if "security" in lowered or "secret" in lowered or "vulnerab" in lowered:
        return "security_exposure"
    if "release" in lowered or "deploy" in lowered or "ci" in lowered:
        return "release_blocker"
    if "unavailable" in lowered or "missing evidence" in lowered or "timed out" in lowered:
        return "missing_evidence"
    if "governance" in lowered or "owner" in lowered or "review" in lowered:
        return "governance_weakness"
    return "engineering_risk"


def reconcile_mid_decision_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_roots: set[str] = set()
    for section in _items(payload.get("sections")):
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("id"), "unknown")
        label = _text(section.get("label") or section_id, section_id)
        findings = _items(section.get("findings"))
        evidence = [_text(item) for item in _items(section.get("evidence"))]
        limitations = [_text(item) for item in _items(section.get("unavailable"))]
        action = section.get("action") if isinstance(section.get("action"), dict) else {}
        for index, raw in enumerate(findings, start=1):
            finding = raw if isinstance(raw, dict) else {"summary": raw}
            summary = _text(finding.get("summary") or finding.get("title") or raw)
            root = _text(finding.get("root_cause") or summary).lower()
            root_key = sha256(root.encode("utf-8")).hexdigest()[:16]
            if root_key in seen_roots:
                continue
            seen_roots.add(root_key)
            severity = _text(finding.get("severity"), "medium").lower()
            record = {
                "finding_id": _text(finding.get("id"), f"MID-{section_id.upper()}-{index:03d}"),
                "classification": _classification(" ".join([summary, label, *limitations])),
                "severity": severity,
                "priority": _text(finding.get("priority"), "P1" if severity in {"critical", "high"} else "P2"),
                "confidence": _text(finding.get("confidence"), "review-limited" if limitations else "moderate"),
                "verification_state": _text(finding.get("verification_state"), "requires_human_review"),
                "business_impact": _text(finding.get("business_impact") or action.get("impact")),
                "technical_impact": _text(finding.get("technical_impact") or summary),
                "affected_systems": _items(finding.get("affected_systems")) or [label],
                "exact_evidence": _items(finding.get("evidence")) or evidence or ["No exact retained evidence was attached to this finding."],
                "root_cause": _text(finding.get("root_cause") or summary),
                "failure_scenario": _text(finding.get("failure_scenario")),
                "repair": _text(finding.get("repair") or action.get("action")),
                "owner": _text(finding.get("owner") or action.get("owner"), "Authorized technical owner"),
                "effort": _text(finding.get("effort") or action.get("effort"), "Estimate after evidence verification"),
                "dependencies": _items(finding.get("dependencies")),
                "verification": _text(finding.get("verification") or action.get("verification"), "Run targeted tests and a new immutable NICO rescan."),
                "rollback": _text(finding.get("rollback"), "Revert the smallest repair commit and restore the last verified release artifact."),
                "acceptance_criteria": _items(finding.get("acceptance_criteria")) or ["Targeted tests pass", "New scan retains exact evidence", "Human reviewer approves disposition"],
                "deferred_risk": _text(finding.get("deferred_risk"), "Risk remains open until verification and human approval complete."),
                "target_window": _text(finding.get("target_window"), "30 days"),
                "related_findings": _items(finding.get("related_findings")),
                "limitations": limitations or ["Human review remains required before client delivery."],
                "approval_boundary": "NICO recommendation only; authorized human approval is required.",
                "root_cause_key": root_key,
            }
            records.append(record)
    payload["mid_decision_records"] = {
        "version": VERSION,
        "required_fields": list(REQUIRED_FIELDS),
        "root_cause_deduplicated": True,
        "records": records,
    }
    return records


__all__ = ["REQUIRED_FIELDS", "VERSION", "reconcile_mid_decision_records"]
