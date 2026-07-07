from __future__ import annotations

from typing import Any

from nico.max_target_status import build_max_target_status

PRIORITY = {
    "client_ready": 1,
    "express": 2,
    "mid": 3,
    "retainer": 4,
}

SERVICE_LABELS = {
    "express": "Express",
    "mid": "Mid",
    "retainer": "Retainer",
    "client_ready": "Client-ready",
}

ACTIONS = {
    "persistent_storage": "Confirm persistent storage is active before relying on run history.",
    "stable_run_id": "Run the assessment and keep the generated run ID for review and export.",
    "final_review_link": "Use the run-scoped final review link.",
    "review_requested": "Request final review for the exact run.",
    "review_approved": "Complete human review before final delivery.",
    "rerun_after_approval": "Rerun after approval so the acceptance evidence can apply.",
    "acceptance_green": "Confirm Client / Human Acceptance is green in the rerun output.",
    "report_exports": "Export the final report package.",
    "delivery_notes": "Attach delivery notes and unavailable-data disclosure.",
    "human_review": "Keep the final package blocked until human review is complete.",
    "stakeholder_inputs": "Collect stakeholder goals, pain points, outcomes, and decision owners.",
    "qa_review": "Collect QA evidence for critical flows and release blockers.",
    "platform_parity": "Compare iOS and Android behavior, UX, and feature availability.",
    "risk_register": "Create a technical and product risk register.",
    "six_month_roadmap": "Build a six-month roadmap with milestones and priorities.",
    "weekly_status": "Generate weekly status with completed work, risks, and next actions.",
}


def build_max_target_action_plan(payload: dict[str, Any]) -> dict[str, Any]:
    status = build_max_target_status(payload or {})
    gates = status.get("next_gates") or []
    ordered = sorted(gates, key=lambda item: (PRIORITY.get(item.get("service"), 99), item.get("gate", "")))
    steps = []
    for index, item in enumerate(ordered, start=1):
        service = item.get("service", "unknown")
        gate = item.get("gate", "unknown")
        steps.append(
            {
                "order": index,
                "service": service,
                "service_label": SERVICE_LABELS.get(service, service.replace("_", " ").title()),
                "gate": gate,
                "action": ACTIONS.get(gate, f"Complete evidence for {gate.replace('_', ' ')}."),
            }
        )
    return {
        "status": status.get("status"),
        "overall_score": status.get("overall_score"),
        "overall_target": status.get("overall_target"),
        "overall_gap": status.get("overall_gap"),
        "ready_for_all_max": status.get("ready_for_all_max"),
        "step_count": len(steps),
        "steps": steps,
        "first_step": steps[0] if steps else None,
        "rule": "Action plan is derived from missing evidence gates. It does not mark review, stakeholder input, or acceptance complete.",
    }
