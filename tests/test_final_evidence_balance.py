from nico.final_report_consistency import finalize_express_result_consistency


def _base_sections(ci_evidence=None):
    return [
        {"id": "code_audit", "label": "Code Audit", "score": 86, "status": "green", "summary": "", "evidence": ["actionable TODO/FIXME/security markers=0"], "findings": [], "unavailable": []},
        {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "score": 90, "status": "green", "summary": "", "evidence": ["requirements.txt found", "package.json found", "Lockfile evidence found", "pip-audit", "npm-audit"], "findings": [], "unavailable": []},
        {"id": "secrets_review", "label": "Secrets Exposure Review", "score": 88, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
        {"id": "static_analysis", "label": "Static Analysis", "score": 70, "status": "yellow", "summary": "", "evidence": ["Built-in static risk-pattern hits: 0."], "findings": [], "unavailable": ["External analyzer execution is unavailable."]},
        {"id": "ci_cd", "label": "CI/CD Analysis", "score": 95, "status": "green", "summary": "", "evidence": ci_evidence or ["Workflow text includes test, lint, or build commands.", "npm run lint", "npm run build"], "findings": [], "unavailable": []},
        {"id": "architecture_debt", "label": "Architecture & Technical Debt", "score": 94, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
        {"id": "velocity_complexity", "label": "Velocity / Complexity", "score": 73, "status": "yellow", "summary": "", "evidence": ["Commit velocity: 100 commits over 180 days.", "Pull request traceability ratio: 90 PRs / 100 commits = 0.9."], "findings": [], "unavailable": ["Human review required."]},
    ]


def test_final_scoring_balances_clean_static_and_pr_ratio():
    result = finalize_express_result_consistency(
        {
            "status": "complete",
            "repository": "BoneManTGRM/NICO",
            "sections": _base_sections(),
            "reports": {},
        }
    )

    static = next(item for item in result["sections"] if item["id"] == "static_analysis")
    velocity = next(item for item in result["sections"] if item["id"] == "velocity_complexity")

    assert static["score"] >= 86
    assert static["status"] == "green"
    assert velocity["score"] >= 82
    assert velocity["status"] == "green"
    assert result["maturity_signal"]["score"] > 85


def test_green_ci_lifts_clean_static_without_exact_ci_marker_text():
    result = finalize_express_result_consistency(
        {
            "status": "complete",
            "repository": "BoneManTGRM/NICO",
            "sections": _base_sections(ci_evidence=["GitHub Actions workflow runs returned in assessment window: 100; success=91; non-success=9."]),
            "reports": {},
        }
    )

    static = next(item for item in result["sections"] if item["id"] == "static_analysis")
    velocity = next(item for item in result["sections"] if item["id"] == "velocity_complexity")

    assert static["score"] >= 86
    assert static["status"] == "green"
    assert velocity["score"] >= 82
    assert velocity["status"] == "green"
