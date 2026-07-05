    dep = result.get("dependency_audit", {})
    if dep.get("risky_dependencies"):
        score -= 10
        drivers.append("Risky/outdated dependencies detected")
        quick_wins.append("Review and update risky dependencies.")

    # New: Penalize for real vulnerabilities
    critical = dep.get("critical_count", 0)
    high = dep.get("high_count", 0)
    total_vulns = dep.get("vulnerabilities_found", 0)

    if critical >= 1:
        score -= 25
        drivers.append(f"Critical vulnerabilities detected ({critical})")
        quick_wins.append("Immediately remediate critical dependency vulnerabilities.")
    elif high >= 3:
        score -= 15
        drivers.append(f"Multiple high-severity vulnerabilities ({high})")
        quick_wins.append("Prioritize remediation of high-severity dependency vulnerabilities.")
    elif total_vulns >= 5:
        score -= 10
        drivers.append(f"Multiple dependency vulnerabilities found ({total_vulns})")
