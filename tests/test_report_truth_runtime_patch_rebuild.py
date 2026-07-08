from nico.report_truth_runtime_patch import apply_dependency_score_consistency, rebuild_reports, refresh_project_trend_score


def _result_with_malformed_dependency_report():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-08T19:23:51Z",
        "maturity_signal": {"level": "Senior", "score": 89},
        "project_trend_evidence": {
            "status": "tracked",
            "prior_run_count": 6,
            "previous_score": 89,
            "average_prior_score": 88,
            "current_score": 85,
            "notes": ["Project trend evidence: 6 prior completed Express run(s); previous score=89; prior average=88; current score=85; delta vs previous=-4."],
        },
        "release_readiness": {"status": "evidence_incomplete", "passed_signals": ["code_audit_green"], "missing_signals": []},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "status": "green", "score": 86, "summary": "Code audit.", "evidence": [], "findings": [], "unavailable": []},
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "status": "green",
                "score": 90,
                "summary": "Dependency review is green from available evidence.",
                "evidence": [
                    "OSV returned 11 vulnerability record(s) for PyPI:PyJWT@[crypto]==2.13.0: GHSA-752w-5fwx-jx9f, GHSA-993g-76c3-p5m4.",
                    "Parsed clean dependency artifacts superseded earlier manifest-only dependency warnings for this run.",
                ],
                "findings": [],
                "unavailable": [],
            },
            {"id": "secrets_review", "label": "Secrets", "status": "green", "score": 90, "summary": "Secrets.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "static_analysis", "label": "Static", "status": "green", "score": 86, "summary": "Static.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "ci_cd", "label": "CI/CD", "status": "green", "score": 95, "summary": "CI.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "architecture_debt", "label": "Architecture", "status": "green", "score": 94, "summary": "Architecture.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "status": "green", "score": 82, "summary": "Velocity.", "evidence": ["Project trend evidence: 6 prior completed Express run(s); previous score=89; prior average=88; current score=85; delta vs previous=-4."], "findings": [], "unavailable": []},
            {"id": "client_acceptance", "label": "Client / Human Acceptance", "status": "gray", "score": 0, "summary": "Acceptance.", "evidence": [], "findings": [], "unavailable": []},
        ],
        "reports": {"markdown": "old markdown GREEN 90 PyJWT@[crypto] current score=85", "html": "", "pdf_base64": ""},
    }


def test_dependency_truth_guard_rebuilds_reports_and_removes_stale_green_claims():
    result = _result_with_malformed_dependency_report()
    result = apply_dependency_score_consistency(result)
    result = refresh_project_trend_score(result)
    result = rebuild_reports(result)

    dependency = next(item for item in result["sections"] if item["id"] == "dependency_health")
    velocity = next(item for item in result["sections"] if item["id"] == "velocity_complexity")
    markdown = result["reports"]["markdown"]

    assert dependency["status"] == "yellow"
    assert dependency["score"] == 74
    assert result["maturity_signal"]["score"] == 87
    assert "PyJWT@[crypto]" not in markdown
    assert "GREEN 90" not in markdown
    assert "superseded earlier manifest-only dependency warnings" not in markdown
    assert "current score=87" in "\n".join(velocity["evidence"])
    assert "current score=85" not in "\n".join(velocity["evidence"])
