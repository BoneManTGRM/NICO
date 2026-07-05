"""Synthesis Module (Phase 3)

Evidence weighting + GitHub activity integration.
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

    total_weight = sum(weights.values())

    recs = [
        {"title": "Address highest RYE scanner findings", "weight": weights["scanner"], "source": "scanner"},
        {"title": "Review architecture debt signals", "weight": weights["architecture"], "source": "architecture"},
        {"title": "Update risky dependencies", "weight": weights["dependency"], "source": "dependency"},
        {"title": "Implement basic CI workflow", "weight": weights["cicd"], "source": "cicd"},
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
