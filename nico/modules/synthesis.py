"""Synthesis Module (Phase 3 Start)

Evidence weighting + recommendation ranking for existing Express output.
"""

def synthesize_recommendations(result: dict) -> dict:
    findings_weight = min(100, result.get("findings_count", 0) * 5)
    debt_weight = 30 if result.get("architecture_audit", {}).get("debt_signals") else 0
    dep_weight = 25 if result.get("dependency_audit", {}).get("risky_dependencies") else 0
    ci_weight = 20 if not result.get("cicd_audit", {}).get("has_ci") else 0

    total_weight = findings_weight + debt_weight + dep_weight + ci_weight

    ranked = [
        {"priority": 1, "recommendation": "Address highest RYE scanner findings", "weight": findings_weight, "evidence": "scanner findings"},
    ]

    if debt_weight > 0:
        ranked.append({"priority": 2, "recommendation": "Review architecture debt signals", "weight": debt_weight, "evidence": "large files + TODO clusters"})
    if dep_weight > 0:
        ranked.append({"priority": 3, "recommendation": "Update risky dependencies", "weight": dep_weight, "evidence": "static dep scan"})
    if ci_weight > 0:
        ranked.append({"priority": 4, "recommendation": "Implement basic CI pipeline", "weight": ci_weight, "evidence": "missing CI files"})

    return {
        "status": "completed",
        "overall_evidence_weight": total_weight,
        "ranked_recommendations": ranked[:5],
        "limitations": ["Evidence weighting is heuristic. Full weighting requires human context and more modules."]
    }
