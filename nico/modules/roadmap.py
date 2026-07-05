"""Roadmap Module (Phase 2)

Basic 30/60/90 day roadmap builder for Express tier.
"""

def build_roadmap(result: dict) -> dict:
    phases = {
        "30_days": [],
        "60_days": [],
        "90_days": []
    }

    findings = result.get("findings_count", 0)
    dep = result.get("dependency_audit", {})
    cicd = result.get("cicd_audit", {})
    arch = result.get("architecture_audit", {})

    # 30 days
    if findings > 0:
        phases["30_days"].append("Prioritize top scanner findings by severity and repair confidence.")
    if dep.get("risky_dependencies"):
        phases["30_days"].append("Review and update risky dependencies.")
    if not cicd.get("has_ci"):
        phases["30_days"].append("Add a basic CI workflow for tests and static checks.")

    if not phases["30_days"]:
        phases["30_days"].append("Preserve working scanner, reporting, and assessment regression tests.")

    # 60 days
    if arch.get("debt_signals"):
        phases["60_days"].append("Review large files and TODO/FIXME clusters.")
    phases["60_days"].append("Improve report evidence quality and link each recommendation to source signals.")
    phases["60_days"].append("Add stronger dependency audit support using pip-audit/npm audit when available.")

    # 90 days
    phases["90_days"].append("Add GitHub activity analysis for commits/PRs/checks when token is available.")
    phases["90_days"].append("Add better CI/CD history analysis with workflow pass/fail rates.")
    phases["90_days"].append("Prepare Mid tier expansion without claiming stakeholder/QA/parity data unless provided.")

    return {
        "status": "completed",
        "phases": phases,
        "limitations": ["Heuristic roadmap only. Effort estimates require human review and project context."]
    }
