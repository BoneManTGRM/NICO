from nico.express_decision_quality_v17 import normalize_express_decision_quality


def test_normalization_removes_language_false_positive_and_reconciles_ci_counts():
    result = {
        "repository": "owner/repo",
        "maturity_signal": {"score": 91, "level": "Senior"},
        "sections": [
            {
                "id": "code_audit",
                "evidence": ["apps/web/app/page.tsx:12: python_eval_exec — review"],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "ci_cd",
                "evidence": ["GitHub Actions workflow runs returned: 100; success=94; non-success=2."],
                "findings": [],
                "unavailable": [],
            },
        ],
    }
    output = normalize_express_decision_quality(result)
    assert output["sections"][0]["evidence"] == []
    assert "other/unknown=4" in output["sections"][1]["evidence"][0]
    assert "Senior (91/100)" in output["executive_summary"]


def test_unverified_secret_candidates_are_grouped_and_not_critical():
    result = {
        "maturity_signal": {"score": 80, "level": "Mid"},
        "sections": [],
        "repair_intelligence": {
            "candidates": [
                {
                    "candidate_id": "a",
                    "category": "secret_exposure",
                    "title": "Potential secret exposure in a.py:1",
                    "status": "report_only_unverified_candidate",
                    "severity": "critical",
                    "affected_files": ["a.py"],
                    "verified_fix": False,
                },
                {
                    "candidate_id": "b",
                    "category": "secret_exposure",
                    "title": "Potential secret exposure in b.py:2",
                    "status": "report_only_unverified_candidate",
                    "severity": "critical",
                    "affected_files": ["b.py"],
                    "verified_fix": False,
                },
            ]
        },
    }
    output = normalize_express_decision_quality(result)
    candidates = output["repair_intelligence"]["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["severity"] == "review"
    assert candidates[0]["status"] == "candidate_pending_human_triage"
    assert set(candidates[0]["affected_files"]) == {"a.py", "b.py"}


def test_cross_section_duplicate_findings_are_removed():
    finding = "Complexity and high churn overlap in 51 delivery hotspot file(s)."
    result = {
        "maturity_signal": {"score": 70, "level": "Mid"},
        "sections": [
            {"id": "architecture_debt", "findings": [finding], "evidence": [], "unavailable": []},
            {"id": "velocity_complexity", "findings": [finding], "evidence": [], "unavailable": []},
        ],
    }
    output = normalize_express_decision_quality(result)
    findings = [item for section in output["sections"] for item in section["findings"]]
    assert findings == [finding]
