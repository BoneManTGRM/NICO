"""Maturity Module (Phase 2)

Basic heuristic maturity semaphore + quick wins for Express tier.
"""

def assess_maturity(result: dict) -> dict:
    score = 80
    drivers = []
    quick_wins = []
    limitations = ["Heuristic maturity score only. Not a substitute for full human architecture review."]

    findings = result.get("findings_count", 0)

    if findings > 20:
        score -= 20
        drivers.append("High number of scanner findings (>20)")
    elif findings > 5:
        score -= 10
        drivers.append("Moderate number of scanner findings (>5)")

    dep = result.get("dependency_audit", {})
    if dep.get("risky_dependencies"):
        score -= 15
        drivers.append("Risky/outdated dependencies detected")
        quick_wins.append("Review and update risky dependencies.")

    cicd = result.get("cicd_audit", {})
    if not cicd.get("has_ci"):
        score -= 10
        drivers.append("No CI configuration detected")
        quick_wins.append("Add a basic CI workflow for tests and static checks.")

    arch = result.get("architecture_audit", {})
    if arch.get("debt_signals"):
        score -= 15
        drivers.append("Technical debt signals (large files or high TODO density)")
        quick_wins.append("Review large files and TODO/FIXME clusters.")

    if findings > 0:
        quick_wins.append("Prioritize top scanner findings by severity and repair confidence.")

    # Clamp
    score = max(0, min(100, score))

    if score >= 75:
        semaphore = "Green"
    elif score >= 50:
        semaphore = "Yellow"
    else:
        semaphore = "Red"

    return {
        "status": "completed",
        "semaphore": semaphore,
        "score": score,
        "drivers": drivers,
        "quick_wins": quick_wins,
        "limitations": limitations
    }
