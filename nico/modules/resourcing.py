"""Resourcing Module (Phase 2)

Basic heuristic resourcing recommendations based on assessment signals.
"""

def recommend_resourcing(result: dict) -> dict:
    findings = result.get("findings_count", 0)
    has_ci = result.get("cicd_audit", {}).get("has_ci", False)
    has_debt = bool(result.get("architecture_audit", {}).get("debt_signals"))
    has_risky_deps = bool(result.get("dependency_audit", {}).get("risky_dependencies"))

    min_team = ["Product Engineer"]
    recommended = ["Product Engineering Architect", "Product Engineer"]
    aggressive = ["Product Engineering Architect", "Product Engineer", "Product Quality Engineer"]

    if has_ci is False or has_debt:
        recommended.append("DevOps/Platform support")
        aggressive.append("DevOps/Platform support")

    if has_risky_deps or findings > 15:
        recommended.append("Security/Compliance review")
        aggressive.append("Security/Compliance review")

    rationale = []
    if findings > 0:
        rationale.append("Scanner findings present — engineering capacity needed for repairs.")
    if not has_ci:
        rationale.append("No CI detected — platform/DevOps help recommended.")
    if has_debt:
        rationale.append("Technical debt signals — architecture ownership recommended.")

    return {
        "status": "completed",
        "minimum_team": min_team,
        "recommended_team": recommended,
        "aggressive_team": aggressive,
        "rationale": rationale,
        "when_retainer_makes_sense": "High findings count or recurring drift suggests retainer is valuable.",
        "limitations": ["Heuristic recommendation only. Final resourcing should consider team skills and roadmap complexity."]
    }
