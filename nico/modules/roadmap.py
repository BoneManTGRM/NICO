    dep = result.get("dependency_audit", {})
    critical = dep.get("critical_count", 0)
    high = dep.get("high_count", 0)
    total_vulns = dep.get("vulnerabilities_found", 0)

    # 30 days
    if findings > 0:
        phases["30_days"].append("Prioritize top scanner findings by severity and repair confidence.")
    if critical >= 1:
        phases["30_days"].append("Immediately remediate critical dependency vulnerabilities (security risk).")
    elif high >= 2:
        phases["30_days"].append("Prioritize remediation of high-severity dependency vulnerabilities.")
    elif dep.get("risky_dependencies"):
        phases["30_days"].append("Review and update risky/outdated dependencies.")
    if not cicd.get("has_ci"):
        phases["30_days"].append("Add a basic CI workflow for tests and static checks.")

    if not phases["30_days"]:
        phases["30_days"].append("Preserve working scanner, reporting, and assessment regression tests.")

    # 60 days
    if total_vulns > 0 and critical == 0 and high < 2:
        phases["60_days"].append("Complete remediation of remaining medium/low dependency vulnerabilities.")
    if arch.get("debt_signals"):
        phases["60_days"].append("Review large files and TODO/FIXME clusters.")
    phases["60_days"].append("Improve report evidence quality and link each recommendation to source signals.")
    if total_vulns == 0:
        phases["60_days"].append("Add stronger dependency audit support using pip-audit/npm audit when available.")
