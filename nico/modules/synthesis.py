"""Synthesis Module (Phase 3)

Added CI/CD run-history weighting.
"""

def synthesize_recommendations(result: dict) -> dict:
    weights = {}
    weights["scanner"] = min(100, result.get("findings_count", 0) * 4)
    weights["architecture"] = 30 if result.get("architecture_audit", {}).get("debt_signals") else 0
    weights["dependency"] = 25 if result.get("dependency_audit", {}).get("risky_dependencies") else 0
    weights["cicd"] = 20 if not result.get("cicd_audit", {}).get("has_ci") else 0

    # GitHub Activity weighting
    gh = result.get("github_activity", {})
    gh_weight = 0
    if gh.get("is_github_target"):
        if gh.get("consistency_classification") == "stale":
            gh_weight = max(gh_weight, 35)
        if gh.get("velocity_classification") == "low":
            gh_weight = max(gh_weight, 25)
        if gh.get("pr_count", 0) == 0:
            gh_weight = max(gh_weight, 15)

    weights["github_activity"] = gh_weight

    # CI/CD run-history weighting (new)
    cicd = result.get("cicd_audit", {})
    cicd_weight = weights.get("cicd", 0)

    if cicd.get("workflow_runs_count", 0) > 0:
        failures = cicd.get("failed_runs_recent", 0)
        success_rate = cicd.get("success_rate")

        if failures >= 5:
            cicd_weight = max(cicd_weight, 40)
        elif failures >= 2:
            cicd_weight = max(cicd_weight, 25)

        if success_rate is not None and success_rate < 70:
            cicd_weight = max(cicd_weight, 30)

        if failures > 0:
            cicd_weight = max(cicd_weight, 15)

    weights["cicd"] = cicd_weight

    total_weight = sum(weights.values())

    recs = [
        {"title": "Address highest RYE scanner findings", "weight": weights["scanner"], "source": "scanner"},
        {"title": "Review architecture debt signals", "weight": weights["architecture"], "source": "architecture"},
        {"title": "Update risky dependencies", "weight": weights["dependency"], "source": "dependency"},
        {"title": "Investigate recent CI/CD failures", "weight": weights["cicd"], "source": "cicd"},
        {"title": "Implement basic CI workflow", "weight": weights.get("cicd_static", 0), "source": "cicd"},
    ]

    if gh_weight > 0:
        recs.append({
            "title": "Review delivery velocity and PR hygiene",
            "weight": gh_weight,
            "source": "github_activity"
        })

    # Sort descending by weight and filter zero-weight
    ranked = sorted([r for r in recs if r["weight"] > 0], key=lambda r: r["weight"], reverse=True)

    return {
        "status": "completed",
        "overall_evidence_weight": total_weight,
        "ranked_recommendations": ranked[:5],
        "limitations": ["Evidence weighting is heuristic. Full weighting requires human context and more modules."]
    }
