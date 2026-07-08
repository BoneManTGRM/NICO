from __future__ import annotations

from typing import Any

CATEGORY_KEYWORDS = {
    "goals": ("goal", "want", "need", "objective", "outcome", "launch", "grow", "reduce", "increase"),
    "users": ("user", "customer", "client", "admin", "operator", "team", "buyer", "audience"),
    "pain_points": ("pain", "problem", "broken", "slow", "confusing", "friction", "complaint", "risk"),
    "constraints": ("constraint", "budget", "deadline", "timeline", "limited", "must", "cannot", "compliance"),
    "success_metrics": ("metric", "kpi", "measure", "success", "conversion", "retention", "revenue", "uptime"),
    "decision_makers": ("owner", "ceo", "cto", "manager", "stakeholder", "approver", "decision", "signoff"),
    "open_questions": ("question", "unknown", "unclear", "confirm", "decide", "pending", "ask"),
}

REQUIRED_CATEGORIES = ("goals", "users", "pain_points", "constraints", "success_metrics", "decision_makers")


def _lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [line.strip() for line in str(value).splitlines() if line.strip()]


def _collect(payload: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    rows: list[str] = []
    for key in keys:
        rows.extend(_lines(payload.get(key)))
    return rows


def _matches(row: str, words: tuple[str, ...]) -> bool:
    lowered = row.lower()
    return any(word in lowered for word in words)


def _bucket_rows(rows: list[str]) -> dict[str, list[str]]:
    buckets = {key: [] for key in CATEGORY_KEYWORDS}
    uncategorized: list[str] = []
    for row in rows:
        matched = False
        for key, words in CATEGORY_KEYWORDS.items():
            if _matches(row, words):
                buckets[key].append(row)
                matched = True
        if not matched:
            uncategorized.append(row)
    buckets["uncategorized"] = uncategorized
    return buckets


def _explicit_or_bucket(payload: dict[str, Any], explicit_keys: tuple[str, ...], fallback: list[str]) -> list[str]:
    explicit = _collect(payload, explicit_keys)
    return explicit if explicit else fallback


def build_stakeholder_discovery(payload: dict[str, Any]) -> dict[str, Any]:
    notes = _collect(payload, ("stakeholder_notes", "discovery_notes", "client_notes", "interview_notes"))
    buckets = _bucket_rows(notes)

    goals = _explicit_or_bucket(payload, ("stakeholder_goals", "business_goals", "goals"), buckets["goals"])
    users = _explicit_or_bucket(payload, ("target_users", "users", "audience"), buckets["users"])
    pain_points = _explicit_or_bucket(payload, ("pain_points", "problems", "frictions"), buckets["pain_points"])
    constraints = _explicit_or_bucket(payload, ("constraints", "budget_constraints", "timeline_constraints"), buckets["constraints"])
    success_metrics = _explicit_or_bucket(payload, ("success_metrics", "kpis", "metrics"), buckets["success_metrics"])
    decision_makers = _explicit_or_bucket(payload, ("decision_makers", "approvers", "stakeholders"), buckets["decision_makers"])
    open_questions = _explicit_or_bucket(payload, ("open_questions", "questions", "unknowns"), buckets["open_questions"])

    categories = {
        "goals": goals,
        "users": users,
        "pain_points": pain_points,
        "constraints": constraints,
        "success_metrics": success_metrics,
        "decision_makers": decision_makers,
        "open_questions": open_questions,
        "uncategorized": buckets["uncategorized"],
    }
    complete_required = sum(1 for key in REQUIRED_CATEGORIES if categories[key])
    total_evidence = sum(len(value) for value in categories.values())

    score = 20 + complete_required * 10 + min(20, total_evidence * 2)
    if not open_questions:
        score -= 5
    readiness_score = max(0, min(100, score))

    missing = [key for key in REQUIRED_CATEGORIES if not categories[key]]
    unavailable = [f"Missing stakeholder discovery category: {key.replace('_', ' ')}." for key in missing]
    if not notes and total_evidence == 0:
        unavailable.append("No stakeholder discovery notes or structured discovery fields were supplied.")

    if missing:
        status = "needs_more_discovery"
    elif open_questions:
        status = "ready_for_human_review_with_open_questions"
    else:
        status = "ready_for_human_review"

    roadmap_inputs = []
    if goals:
        roadmap_inputs.append(f"Primary goal: {goals[0]}")
    if pain_points:
        roadmap_inputs.append(f"Primary pain point: {pain_points[0]}")
    if constraints:
        roadmap_inputs.append(f"Primary constraint: {constraints[0]}")
    if success_metrics:
        roadmap_inputs.append(f"Primary success metric: {success_metrics[0]}")

    return {
        "artifact_schema": "nico.stakeholder_discovery.v1",
        "status": status,
        "readiness_score": readiness_score,
        "evidence_item_count": total_evidence,
        "complete_required_categories": complete_required,
        "required_category_count": len(REQUIRED_CATEGORIES),
        "categories": {key: value[:30] for key, value in categories.items()},
        "missing_categories": missing,
        "roadmap_inputs": roadmap_inputs,
        "unavailable": unavailable,
        "summary": "Structured stakeholder discovery turns supplied client context into goals, users, pain points, constraints, success metrics, decision makers, and open questions. Final interpretation requires human review.",
        "human_review_required": True,
    }
