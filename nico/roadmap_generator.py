from __future__ import annotations

from typing import Any

from nico.qa_parity_intake import build_qa_parity_intake
from nico.stakeholder_discovery import build_stakeholder_discovery


def _lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [line.strip() for line in str(value).splitlines() if line.strip()]


def _first(values: list[str], fallback: str) -> str:
    return values[0] if values else fallback


def _category(discovery: dict[str, Any], key: str) -> list[str]:
    categories = discovery.get("categories") if isinstance(discovery.get("categories"), dict) else {}
    value = categories.get(key)
    return value if isinstance(value, list) else []


def _roadmap_notes(payload: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    for key in ("roadmap_notes", "roadmap_inputs", "milestones", "planned_work"):
        notes.extend(_lines(payload.get(key)))
    return notes


def build_six_month_roadmap(
    payload: dict[str, Any],
    stakeholder_discovery: dict[str, Any] | None = None,
    qa_parity_intake: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an evidence-bound six-month roadmap from supplied assessment context."""
    discovery = stakeholder_discovery if isinstance(stakeholder_discovery, dict) else build_stakeholder_discovery(payload)
    qa_parity = qa_parity_intake if isinstance(qa_parity_intake, dict) else build_qa_parity_intake(payload)
    notes = _roadmap_notes(payload)
    risks = _lines(payload.get("known_risks")) + _lines(payload.get("blockers")) + _lines(payload.get("release_blockers"))

    goals = _category(discovery, "goals")
    users = _category(discovery, "users")
    pains = _category(discovery, "pain_points")
    constraints = _category(discovery, "constraints")
    metrics = _category(discovery, "success_metrics")
    questions = _category(discovery, "open_questions")

    critical_blockers = qa_parity.get("blockers") if isinstance(qa_parity.get("blockers"), list) else []
    unavailable: list[str] = []
    if discovery.get("missing_categories"):
        unavailable.append("Stakeholder discovery is incomplete, so roadmap sequencing needs human validation.")
    if qa_parity.get("status") in {"incomplete_intake", "partial_intake_needs_more_evidence"}:
        unavailable.append("QA and parity intake is incomplete, so release-readiness milestones need more evidence.")
    if not notes:
        unavailable.append("No explicit roadmap notes were supplied. Generated roadmap uses available discovery and QA signals only.")

    month_plan = [
        {
            "month": 1,
            "theme": "Stabilize evidence and critical risk",
            "goals": [
                "Close missing evidence categories before client-facing delivery.",
                f"Resolve top blocker: {_first(critical_blockers + risks, 'No explicit blocker supplied; confirm current blocker list with client.')}"
            ],
            "evidence_basis": [
                f"QA/parity status: {qa_parity.get('status', 'unknown')}.",
                f"Stakeholder discovery status: {discovery.get('status', 'unknown')}.",
            ],
            "acceptance_gate": "Human reviewer confirms blocker list, unavailable-data inventory, and Month 1 release constraints.",
        },
        {
            "month": 2,
            "theme": "Repair highest-value user workflows",
            "goals": [
                f"Prioritize user group: {_first(users, 'primary user group not supplied')}.",
                f"Reduce pain point: {_first(pains, 'primary pain point not supplied')}"
            ],
            "evidence_basis": [
                f"Flows covered by QA intake: {qa_parity.get('flows_covered', 0)}.",
                f"Platforms covered by parity intake: {qa_parity.get('platforms_covered', 0)}.",
            ],
            "acceptance_gate": "Client or authorized representative approves user-workflow priority before implementation commitment.",
        },
        {
            "month": 3,
            "theme": "Strengthen QA automation and parity coverage",
            "goals": [
                "Convert recurring QA and parity checks into repeatable release evidence.",
                "Add explicit pass/fail coverage for authentication, payment or core workflow, and error recovery if applicable."
            ],
            "evidence_basis": [
                f"QA items supplied: {qa_parity.get('qa_item_count', 0)}.",
                f"Parity items supplied: {qa_parity.get('parity_item_count', 0)}.",
            ],
            "acceptance_gate": "Technical reviewer confirms QA evidence is repeatable and tied to release criteria.",
        },
        {
            "month": 4,
            "theme": "Execute roadmap milestones under constraints",
            "goals": [
                f"Work inside constraint: {_first(constraints, 'constraint not supplied')}.",
                f"Advance supplied roadmap note: {_first(notes, 'roadmap note not supplied')}"
            ],
            "evidence_basis": [
                f"Roadmap note count: {len(notes)}.",
                f"Known risk count: {len(risks)}.",
            ],
            "acceptance_gate": "Client approves scope, budget, timeline, and any tradeoff that changes delivery expectations.",
        },
        {
            "month": 5,
            "theme": "Measure outcomes and reduce residual risk",
            "goals": [
                f"Measure success metric: {_first(metrics, 'success metric not supplied')}.",
                "Update risk register and evidence bundle after each major repair or release milestone."
            ],
            "evidence_basis": [
                f"Success metrics supplied: {len(metrics)}.",
                f"Open questions supplied: {len(questions)}.",
            ],
            "acceptance_gate": "Human reviewer confirms metrics are measurable and not invented by automation.",
        },
        {
            "month": 6,
            "theme": "Client-ready strategy and retainer transition",
            "goals": [
                f"Validate primary goal: {_first(goals, 'primary goal not supplied')}.",
                "Prepare retainer or next-phase plan from verified evidence, completed repairs, and client-approved priorities."
            ],
            "evidence_basis": [
                f"Discovery readiness score: {discovery.get('readiness_score', 0)}/100.",
                f"QA/parity readiness score: {qa_parity.get('readiness_score', 0)}/100.",
            ],
            "acceptance_gate": "Client signs off on final roadmap results, unresolved risks, and next-phase operating model.",
        },
    ]

    readiness_score = min(100, max(0, round((int(discovery.get("readiness_score") or 0) + int(qa_parity.get("readiness_score") or 0)) / 2)))
    if unavailable:
        readiness_score = min(readiness_score, 82)
    if critical_blockers:
        readiness_score = min(readiness_score, 70)

    return {
        "artifact_schema": "nico.six_month_roadmap.v1",
        "status": "blocked_by_qa_or_delivery_risk" if critical_blockers else "ready_for_human_roadmap_review" if readiness_score >= 70 else "needs_more_evidence",
        "readiness_score": readiness_score,
        "month_plan": month_plan,
        "roadmap_summary": [f"Month {item['month']}: {item['theme']}" for item in month_plan],
        "source_counts": {
            "roadmap_notes": len(notes),
            "known_risks": len(risks),
            "stakeholder_evidence_items": discovery.get("evidence_item_count", 0),
            "qa_items": qa_parity.get("qa_item_count", 0),
            "parity_items": qa_parity.get("parity_item_count", 0),
        },
        "unavailable": unavailable,
        "human_review_required": True,
        "summary": "Six-month roadmap is generated from stakeholder discovery, QA/parity intake, risks, and roadmap notes. Human review is required before client commitments.",
    }
