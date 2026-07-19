from nico import express_decision_quality_v17 as decision_quality
from nico.express_terminal_truth_patch import install_express_terminal_truth_patch

install_express_terminal_truth_patch()


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
    output = decision_quality.normalize_express_decision_quality(result)
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
    output = decision_quality.normalize_express_decision_quality(result)
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
    output = decision_quality.normalize_express_decision_quality(result)
    findings = [item for section in output["sections"] for item in section["findings"]]
    assert findings == [finding]


def test_clean_osv_evidence_is_retained_as_evidence_but_never_as_finding_or_repair():
    clean = "OSV returned no vulnerability records for 12 pinned dependency query/queries."
    result = {
        "maturity_signal": {"score": 90, "level": "Senior"},
        "sections": [
            {
                "id": "dependency_health",
                "evidence": [clean],
                "findings": [clean, "osv-scanner returned 1 finding requiring human triage."],
                "unavailable": [],
            }
        ],
        "repair_intelligence": {
            "candidates": [
                {
                    "candidate_id": "clean-osv",
                    "category": "dependency_health",
                    "title": clean,
                    "severity": "review",
                    "evidence": [clean],
                },
                {
                    "candidate_id": "real-review",
                    "category": "dependency_health",
                    "title": "osv-scanner returned 1 finding requiring human triage.",
                    "severity": "review",
                    "evidence": ["scanner status=completed; findings=1"],
                },
            ]
        },
    }
    output = decision_quality.normalize_express_decision_quality(result)
    assert output["sections"][0]["evidence"] == [clean]
    assert output["sections"][0]["findings"] == ["osv-scanner returned 1 finding requiring human triage."]
    assert [item["candidate_id"] for item in output["repair_intelligence"]["candidates"]] == ["real-review"]


def test_clean_scanner_polarity_patterns_are_not_adverse_findings():
    clean_statements = [
        "pip-audit returned no vulnerabilities found.",
        "npm audit reported 0 vulnerabilities.",
        "gitleaks found no secrets.",
        "trufflehog findings=0.",
        "credential scan passed with no findings.",
        "Bandit triage artifact: blocking=0.",
    ]
    for statement in clean_statements:
        assert decision_quality._is_clean_evidence(statement), statement


def test_clean_business_impact_prose_cannot_promote_clean_evidence():
    result = {
        "maturity_signal": {"score": 90, "level": "Senior"},
        "sections": [],
        "repair_intelligence": {
            "candidates": [
                {
                    "candidate_id": "bad-promotion",
                    "category": "dependency_health",
                    "title": "Review dependency scanner status",
                    "severity": "high",
                    "business_impact": "OSV returned no vulnerability records for 12 pinned dependency queries.",
                    "verified_finding": True,
                }
            ]
        },
    }
    output = decision_quality.normalize_express_decision_quality(result)
    assert output["repair_intelligence"]["candidates"] == []
    assert output["express_decision_quality"]["clean_evidence_excluded_from_repair_priority"] is True
