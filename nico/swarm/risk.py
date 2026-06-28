from __future__ import annotations


def score_swarm_risk(events: list[dict]) -> dict:
    score = 0
    reasons = []
    touched = {}
    for event in events:
        for path in event.get("files_accessed", ()):
            touched[path] = touched.get(path, 0) + 1
        if event.get("approval_required"):
            score += 15
        if event.get("risk_level") in {"high", "critical"}:
            score += 25
    if any(count > 2 for count in touched.values()):
        score += 20
        reasons.append("multiple_agents_touching_same_file")
    return {"score": min(score, 100), "reasons": reasons}
