"""Synthesis Module (Phase 3)

Clean split between static CI config and dynamic CI run history.
"""

def synthesize_recommendations(result: dict) -> dict:
    weights = {}
    weights["scanner"] = min(100, result.get("findings_count", 0) * 4)
    weights["architecture"] = 30 if result.get("architecture_audit", {}).get("debt_signals") else 0
    weights["dependency"] = 25 if result.get("dependency_audit", {}).get("risky_dependencies") else 0

    cicd = result.get("cicd_audit", {})

    # Static CI config weight (no CI files found)
    cicd_static = 20 if not cicd.get("has_ci") else 0

    # Dynamic CI run-history weight (failures / low success rate)
    cicd_history = 0
    if cicd.get("workflow_runs_count", 0) > 0:
        failures = cicd.get("failed_runs_recent", 0)
        success_rate = cicd.get("success_rate")

        if failures >= 5:
            cicd_history = max(cicd_history, 40)
        elif failures >= 2:
            cicd_history = max(cicd_history, 25)

        if success_rate is not None and success_rate < 70:
            cicd_history = max(cicd_history, 30)

        if failures > 0:
            cicd_history = max(cicd_history, 15)

    weights["cicd_static"] = cicd_static
    weights["cicd_history"] = cicd_history

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

    total_weight = sum(weights.values())

    recs = []

    if weights["scanner"] > 0:
        recs.append({"title": "Address highest RYE scanner findings", "weight": weights["scanner"], "source": "scanner"})

    if weights["architecture"] > 0:
        recs.append({"title": "Review architecture debt signals", "weight": weights["architecture"], "source": "architecture"})

    if weights["dependency"] > 0:
        recs.append({"title": "Update risky dependencies", "weight": weights["dependency"], "source": "dependency"})

    if weights["cicd_static"] > 0:
        recs.append({"title": "Implement basic CI workflow", "weight": weights["cicd_static"], "source": "cicd"})

    if weights["cicd_history"] > 0:
        recs.append({"title": "Investigate recent CI/CD failures", "weight": weights["cicd_history"], "source": "cicd"})

    if weights["github_activity"] > 0:
        recs.append({"title": "Review delivery velocity and PR hygiene", "weight": weights["github_activity"], "source": "github_activity"})

    # Sort descending by weight and filter zero-weight
    ranked = sorted(recs, key=lambda r: r["weight"], reverse=True)

    return {
        "status": "completed",
        "overall_evidence_weight": total_weight,
        "ranked_recommendations": ranked[:5],
        "limitations": ["Evidence weighting is heuristic. Full weighting requires human context and more modules."]
    }
