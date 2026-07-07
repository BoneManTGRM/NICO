from __future__ import annotations

from typing import Any

CLIENT_READY_TARGET = 85
CLIENT_READY_ITEMS = [
    "persistent_storage",
    "stable_run_id",
    "final_review_link",
    "review_requested",
    "review_approved",
    "rerun_after_approval",
    "acceptance_green",
    "report_exports",
    "delivery_notes",
]


def _has(payload: dict[str, Any], item: str) -> bool:
    storage = payload.get("storage") or {}
    review = payload.get("final_review") or {}
    acceptance = payload.get("client_acceptance") or {}
    reports = payload.get("reports") or payload.get("formats") or {}
    text = str(payload).lower()
    return {
        "persistent_storage": bool(storage.get("persistence_available")),
        "stable_run_id": bool(payload.get("run_id") or review.get("run_id")),
        "final_review_link": bool(review.get("url")),
        "review_requested": payload.get("final_review_status") in {"pending", "approved", "needs_more_evidence", "rejected"},
        "review_approved": payload.get("final_review_status") == "approved" or acceptance.get("status") == "accepted",
        "rerun_after_approval": acceptance.get("status") == "accepted" or bool(payload.get("rerun_after_approval")),
        "acceptance_green": acceptance.get("status") == "accepted",
        "report_exports": bool(reports.get("markdown") or reports.get("html") or reports.get("json") or reports.get("pdf") or reports.get("pdf_base64")),
        "delivery_notes": bool(payload.get("delivery_notes") or payload.get("unavailable_data_notes")) or "delivery" in text,
    }[item]


def build_client_ready_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    complete = [item for item in CLIENT_READY_ITEMS if _has(payload, item)]
    missing = [item for item in CLIENT_READY_ITEMS if item not in complete]
    score = round(len(complete) / len(CLIENT_READY_ITEMS) * CLIENT_READY_TARGET)
    return {
        "status": "green" if score >= CLIENT_READY_TARGET else "yellow" if score >= 55 else "red",
        "target": CLIENT_READY_TARGET,
        "score": score,
        "complete_count": len(complete),
        "total_count": len(CLIENT_READY_ITEMS),
        "complete": complete,
        "missing": missing,
        "delivery_checklist": [
            "Confirm persistent storage is active.",
            "Confirm run_id is stable.",
            "Use the run-scoped final-review link.",
            "Request and complete human review.",
            "Rerun after approval.",
            "Confirm Client / Human Acceptance is green.",
            "Export the final report package.",
            "Attach delivery notes and unavailable-data disclosure.",
        ],
        "next_actions": [
            {"item": item, "action": f"Complete client-ready evidence for {item.replace('_', ' ')}."}
            for item in missing
        ],
        "rule": "Client-ready coverage requires persistence, review, rerun, acceptance, exports, and delivery notes. It does not replace human approval or client acceptance.",
    }
