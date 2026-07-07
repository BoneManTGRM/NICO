from __future__ import annotations

from typing import Any

from nico.max_target_action_plan import build_max_target_action_plan
from nico.max_target_status import build_max_target_status

DISCLOSURES = [
    "Max-target readiness is evidence-bound.",
    "Human review, stakeholder input, and client acceptance are not auto-completed.",
    "Unavailable data must stay disclosed in delivery notes.",
    "A rerun is required after approval before acceptance evidence can apply.",
]

DELIVERY_ITEMS = [
    "Persistent storage confirmed",
    "Stable run ID captured",
    "Final review link attached",
    "Human review requested",
    "Human review approved",
    "Assessment rerun after approval",
    "Client / Human Acceptance green",
    "Report exports generated",
    "Delivery notes attached",
]


def build_max_target_readiness_packet(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload or {}
    status = build_max_target_status(source)
    plan = build_max_target_action_plan(source)
    services = status.get("services", {})
    service_cards = []
    for key, value in services.items():
        service_cards.append(
            {
                "service": key,
                "score": value.get("score"),
                "target": value.get("target"),
                "gap": value.get("gap"),
                "ready": value.get("ready_for_max"),
                "missing_count": len(value.get("missing") or []),
            }
        )
    return {
        "status": status.get("status"),
        "overall_score": status.get("overall_score"),
        "overall_target": status.get("overall_target"),
        "overall_gap": status.get("overall_gap"),
        "ready_for_all_max": status.get("ready_for_all_max"),
        "service_cards": service_cards,
        "first_step": plan.get("first_step"),
        "step_count": plan.get("step_count"),
        "steps": plan.get("steps"),
        "delivery_items": DELIVERY_ITEMS,
        "disclosures": DISCLOSURES,
        "client_summary": "Ready for max targets." if status.get("ready_for_all_max") else "Not ready for max targets. Complete the remaining evidence gates first.",
        "rule": "Readiness packet summarizes status and next actions without changing evidence state.",
    }
