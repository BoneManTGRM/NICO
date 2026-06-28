from __future__ import annotations

from .risk import finding_risk


def agent_security_report(findings: list[dict]) -> dict:
    risk = finding_risk(findings)
    return {"finding_count": len(findings), "risk": risk, "findings": findings}
