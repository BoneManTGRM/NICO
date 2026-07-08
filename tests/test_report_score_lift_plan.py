from nico.report_score_lift_plan import build_score_lift_plan


def test_score_lift_plan_identifies_dependency_and_static_paths():
    result = {
        "status": "complete",
        "maturity_signal": {"score": 82},
        "sections": [
            {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "status": "yellow", "score": 74, "summary": "Dependency review is not scanner-clean.", "evidence": [], "findings": [], "unavailable": ["dependency scanner proof missing"]},
            {"id": "static_analysis", "label": "Static Analysis", "status": "yellow", "score": 74, "summary": "Static is review-limited.", "evidence": [], "findings": ["Parsed Bandit artifact reported 50 finding(s)."], "unavailable": ["static triage missing"]},
            {"id": "ci_cd", "label": "CI/CD Analysis", "status": "green", "score": 80, "summary": "CI.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "status": "yellow", "score": 73, "summary": "Velocity.", "evidence": [], "findings": [], "unavailable": []},
        ],
    }

    plan = build_score_lift_plan(result)

    assert plan["current_score"] == 82
    assert plan["target_score"] == 90
    assert plan["status"] == "target_reachable_with_evidence"
    assert "Dependency / Library Ecosystem" in plan["primary_blockers"]
    assert "Static Analysis" in plan["primary_blockers"]
    assert any("Do not raise scores" in item for item in plan["not_allowed"])
    dependency = next(item for item in plan["opportunities"] if item["area"] == "Dependency / Library Ecosystem")
    assert "Attach current-run pip-audit JSON artifact." in dependency["required_evidence"]
