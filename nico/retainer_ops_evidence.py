from __future__ import annotations

from typing import Any

RETAINER_TARGET = 70
RETAINER_ITEMS = [
    "roadmap_backlog",
    "sprint_cadence",
    "release_status",
    "issue_tracking",
    "review_queue",
    "weekly_status",
    "quality_traceability",
    "client_updates",
]

CADENCE_TEMPLATE = {
    "daily": [
        "Review open issues and aging items.",
        "Check active sprint work against roadmap priorities.",
        "Route review-gated actions before implementation.",
    ],
    "weekly": [
        "Generate weekly status with completed work, risks, and next actions.",
        "Refresh release status and rollback notes.",
        "Review quality traceability from requirements to tickets, QA notes, and releases.",
    ],
    "monthly": [
        "Run strategic sync against roadmap milestones.",
        "Update resourcing needs and delivery assumptions.",
        "Review AI-assisted productivity evidence and remaining human decisions.",
    ],
}


def _lines(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def _has(payload: dict[str, Any], item: str) -> bool:
    text = str(payload).lower()
    return {
        "roadmap_backlog": bool(_lines(payload.get("roadmap_notes")) or _lines(payload.get("issue_summary"))) or "backlog" in text or "roadmap" in text,
        "sprint_cadence": bool(payload.get("sprint_cadence") or payload.get("sprint_summary")) or "sprint" in text,
        "release_status": bool(payload.get("release_status") or _lines(payload.get("release_notes"))) or "release" in text,
        "issue_tracking": bool(_lines(payload.get("issues")) or _lines(payload.get("issue_summary"))) or "issue" in text,
        "review_queue": bool(payload.get("review_queue") or payload.get("human_review_queue")) or "review" in text,
        "weekly_status": bool(payload.get("weekly_status_report")) or "weekly" in text,
        "quality_traceability": bool(payload.get("quality_traceability")) or "traceability" in text or "quality" in text,
        "client_updates": bool(payload.get("client_update") or payload.get("client_updates")) or "client" in text,
    }[item]


def build_retainer_ops_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    complete = [item for item in RETAINER_ITEMS if _has(payload, item)]
    missing = [item for item in RETAINER_ITEMS if item not in complete]
    score = round(len(complete) / len(RETAINER_ITEMS) * RETAINER_TARGET)
    roadmap_notes = _lines(payload.get("roadmap_notes"))
    issue_summary = _lines(payload.get("issue_summary"))
    release_notes = _lines(payload.get("release_notes"))
    issues = _lines(payload.get("issues"))
    return {
        "status": "green" if score >= RETAINER_TARGET else "yellow" if score >= 45 else "red",
        "target": RETAINER_TARGET,
        "score": score,
        "complete_count": len(complete),
        "total_count": len(RETAINER_ITEMS),
        "complete": complete,
        "missing": missing,
        "roadmap_packet": roadmap_notes or issue_summary or ["Pending roadmap/backlog evidence: add active milestones, ticket groups, and priority rationale."],
        "release_packet": release_notes or ["Pending release evidence: add release goal, open risks, rollback notes, and go/no-go status."],
        "issue_packet": issues or issue_summary or ["Pending issue evidence: add owner, age, impact, and next decision."],
        "operating_cadence": CADENCE_TEMPLATE,
        "weekly_status_template": [
            "Completed work",
            "Current sprint focus",
            "Open issues and owners",
            "Release status",
            "Quality and traceability notes",
            "Client decisions needed",
            "Next actions before next sync",
        ],
        "next_actions": [
            {"item": item, "action": f"Collect or generate retainer evidence for {item.replace('_', ' ')}."}
            for item in missing
        ],
        "rule": "Retainer coverage improves only when ongoing operating evidence exists. NICO can prepare status, cadence, issue, release, and quality packets, but final decisions and client-facing communication remain human-controlled.",
    }
