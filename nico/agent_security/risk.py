from __future__ import annotations


def finding_risk(findings: list[dict]) -> dict:
    weights = {"low": 1, "medium": 3, "high": 7, "critical": 10}
    score = min(100, sum(weights.get(finding.get("severity", "low"), 1) for finding in findings) * 10)
    return {"score": score, "level": "critical" if score >= 80 else "high" if score >= 50 else "medium" if score >= 20 else "low"}
