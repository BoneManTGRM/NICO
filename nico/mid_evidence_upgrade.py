from __future__ import annotations

from typing import Any

MID_MAX_TARGET = 85
MID_GATES = [
    "technical_audit",
    "qa_review",
    "platform_parity",
    "stakeholder_inputs",
    "risk_register",
    "six_month_roadmap",
    "resourcing_plan",
    "executive_review",
]

QUESTION_BANK = {
    "qa_review": [
        "What critical user flows must be tested on iOS and Android?",
        "Which bugs block release or client acceptance?",
        "Which flows have the highest user friction or support impact?",
    ],
    "platform_parity": [
        "Which features should behave identically across iOS and Android?",
        "Which differences are intentional product choices?",
        "Which differences are bugs, regressions, or missing implementation?",
    ],
    "stakeholder_inputs": [
        "What are the top business goals for the next six months?",
        "What pain points are slowing delivery or adoption?",
        "What outcomes would make the assessment successful?",
    ],
    "risk_register": [
        "Which technical risks could block the roadmap?",
        "Which product risks could create rework?",
        "Which dependencies or staffing gaps need executive attention?",
    ],
}


def _lines(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def _has(payload: dict[str, Any], key: str) -> bool:
    text = str(payload).lower()
    return {
        "technical_audit": bool(payload.get("technical_audit") or payload.get("sections") or payload.get("maturity_signal")),
        "qa_review": bool(_lines(payload.get("qa_evidence")) or payload.get("qa_checklist")) or "qa" in text,
        "platform_parity": bool(_lines(payload.get("parity_notes")) or payload.get("parity_checklist")) or "parity" in text,
        "stakeholder_inputs": bool(_lines(payload.get("stakeholder_notes"))) or "stakeholder" in text,
        "risk_register": bool(_lines(payload.get("known_risks")) or payload.get("risk_register")) or "risk" in text,
        "six_month_roadmap": bool(_lines(payload.get("roadmap_notes")) or payload.get("six_month_roadmap")) or "roadmap" in text,
        "resourcing_plan": bool(payload.get("resourcing_plan")) or "resourcing" in text or "product engineering" in text,
        "executive_review": bool(payload.get("executive_review")) or "executive" in text or "strategy review" in text,
    }[key]


def build_mid_evidence_upgrade(payload: dict[str, Any]) -> dict[str, Any]:
    complete = [gate for gate in MID_GATES if _has(payload, gate)]
    missing = [gate for gate in MID_GATES if gate not in complete]
    score = round(len(complete) / len(MID_GATES) * MID_MAX_TARGET)
    qa_notes = _lines(payload.get("qa_evidence")) or _lines(payload.get("qa_checklist"))
    parity_notes = _lines(payload.get("parity_notes")) or _lines(payload.get("parity_checklist"))
    stakeholder_notes = _lines(payload.get("stakeholder_notes"))
    risks = _lines(payload.get("known_risks")) or _lines(payload.get("risk_register"))
    roadmap = _lines(payload.get("roadmap_notes")) or _lines(payload.get("six_month_roadmap"))
    return {
        "status": "green" if score >= MID_MAX_TARGET else "yellow" if score >= 60 else "red",
        "target": MID_MAX_TARGET,
        "score": score,
        "complete_count": len(complete),
        "total_count": len(MID_GATES),
        "complete": complete,
        "missing": missing,
        "qa_review_packet": qa_notes or ["Pending QA evidence: add iOS/Android critical flows, friction points, and release-blocking bugs."],
        "platform_parity_packet": parity_notes or ["Pending parity evidence: compare iOS/Android behavior, UX, and feature availability."],
        "stakeholder_packet": stakeholder_notes or ["Pending stakeholder evidence: add product goals, pain points, desired outcomes, and decision owners."],
        "risk_register": risks or ["Pending risk evidence: add technical, product, staffing, dependency, and delivery risks."],
        "six_month_roadmap": roadmap or [
            "Month 1: stabilize critical technical and QA findings.",
            "Months 2-3: close parity and release-readiness gaps.",
            "Months 4-6: execute roadmap milestones with resourcing and quality traceability.",
        ],
        "question_bank": {gate: QUESTION_BANK[gate] for gate in QUESTION_BANK if gate in missing},
        "next_actions": [
            {"gate": gate, "action": f"Collect or generate evidence for {gate.replace('_', ' ')}."}
            for gate in missing
        ],
        "rule": "Mid coverage improves only when QA, parity, stakeholder, risk, roadmap, resourcing, and executive-review evidence are present. Human interviews and final roadmap judgment remain human-controlled.",
    }
