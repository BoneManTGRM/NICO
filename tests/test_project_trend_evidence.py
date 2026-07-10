from nico.final_report_consistency import finalize_express_result_consistency
from nico.project_trend_evidence import STORE


def _section(section_id, label, score, evidence=None, findings=None):
    return {
        "id": section_id,
        "label": label,
        "status": "green",
        "score": score,
        "summary": f"{label} summary",
        "evidence": evidence or [],
        "findings": findings or [],
        "unavailable": [],
    }


def _release_ready_result(score=91):
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "project_id": "default_project",
        "generated_at": "2026-07-07T14:00:00Z",
        "maturity_signal": {"level": "Senior", "score": score},
        "executive_summary": "old",
        "complexity_engine": {"status": "complete", "hotspot_risk": "low"},
        "sections": [
            _section("code_audit", "Code Audit", 86, ["Text files inspected for code-risk markers: actionable TODO/FIXME/security markers=0, risky pattern hits=2, test-path signals=2."]),
            _section("dependency_health", "Dependency / Library Ecosystem", 90, ["Parsed GitHub Actions pip-audit and npm-audit artifacts reported zero dependency vulnerabilities."]),
            _section("secrets_review", "Secrets Exposure Review", 93, ["Parsed credential-scan, gitleaks, and trufflehog full-history artifacts reported zero credential findings.", "Scanner-worker secret tools completed: gitleaks, trufflehog."]),
            _section("static_analysis", "Static Analysis", 86, ["Parsed Bandit and Semgrep artifacts reported zero scanner findings."]),
            _section("ci_cd", "CI/CD Analysis", 95, ["Current GitHub Actions scanner artifact sets were fetched and parsed successfully."]),
            _section("architecture_debt", "Architecture & Technical Debt", 94, ["Repository root contains nico/."]),
            _section(
                "velocity_complexity",
                "Velocity / Complexity",
                90,
                [
                    "Commit velocity: 100 commits over 180 days (3.89/week).",
                    "Pull request traceability ratio: 52 PRs / 100 commits = 0.52.",
                    "Source-file footprint from recursive tree: 101 files.",
                ],
            ),
        ],
        "reports": {},
    }


def test_retained_non_regressing_project_history_lifts_velocity(monkeypatch):
    rows = [
        {"workflow": "express", "project_id": "default_project", "payload": {"status": "complete", "generated_at": "2026-07-07T10:00:00Z", "maturity_signal": {"score": 88}}},
        {"workflow": "express", "project_id": "default_project", "payload": {"status": "complete", "generated_at": "2026-07-07T12:00:00Z", "maturity_signal": {"score": 89}}},
    ]
    monkeypatch.setattr(STORE, "list", lambda table, **kwargs: rows if table == "assessment_runs" else [])
    monkeypatch.setattr(STORE, "status", lambda: {"adapter": "memory"})

    finalized = finalize_express_result_consistency(_release_ready_result(score=91))
    velocity = next(section for section in finalized["sections"] if section["id"] == "velocity_complexity")

    assert finalized["project_trend_evidence"]["status"] == "tracked"
    assert finalized["project_trend_evidence"]["non_regressing"] is True
    assert velocity["score"] == 94
    assert any("Retained project history supports Work-vs-Expected" in item for item in velocity["evidence"])


def test_project_history_does_not_lift_without_tracked_prior_runs(monkeypatch):
    rows = [
        {"workflow": "express", "project_id": "default_project", "payload": {"status": "complete", "generated_at": "2026-07-07T12:00:00Z", "maturity_signal": {"score": 89}}},
    ]
    monkeypatch.setattr(STORE, "list", lambda table, **kwargs: rows if table == "assessment_runs" else [])
    monkeypatch.setattr(STORE, "status", lambda: {"adapter": "memory"})

    finalized = finalize_express_result_consistency(_release_ready_result(score=91))
    velocity = next(section for section in finalized["sections"] if section["id"] == "velocity_complexity")

    assert finalized["project_trend_evidence"]["status"] == "baseline"
    assert velocity["score"] == 90
    assert not any("Retained project history supports Work-vs-Expected" in item for item in velocity["evidence"])


def test_project_history_does_not_lift_regression(monkeypatch):
    rows = [
        {"workflow": "express", "project_id": "default_project", "payload": {"status": "complete", "generated_at": "2026-07-07T10:00:00Z", "maturity_signal": {"score": 92}}},
        {"workflow": "express", "project_id": "default_project", "payload": {"status": "complete", "generated_at": "2026-07-07T12:00:00Z", "maturity_signal": {"score": 93}}},
    ]
    monkeypatch.setattr(STORE, "list", lambda table, **kwargs: rows if table == "assessment_runs" else [])
    monkeypatch.setattr(STORE, "status", lambda: {"adapter": "memory"})

    finalized = finalize_express_result_consistency(_release_ready_result(score=91))
    velocity = next(section for section in finalized["sections"] if section["id"] == "velocity_complexity")

    assert finalized["project_trend_evidence"]["status"] == "tracked"
    assert finalized["project_trend_evidence"]["non_regressing"] is False
    assert velocity["score"] == 90
