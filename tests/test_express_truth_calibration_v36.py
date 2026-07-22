from __future__ import annotations

from nico.express_assurance_display_v37 import _pdf_records
from nico.express_truth_calibration_v36 import calibrate_express_truth, calibrated_score_records


def _sample_result():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"level": "Mid", "score": 81, "source_score": 81, "presented_score": 73},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "score": 86, "source_score": 86, "presented_score": 86, "status": "green", "findings": [], "evidence": ["Recursive test evidence present."], "unavailable": []},
            {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "score": 76, "source_score": 76, "presented_score": 69, "status": "yellow", "findings": ["npm-audit returned 2 finding(s) requiring human triage."], "evidence": ["Exact-snapshot pip-audit status=completed; findings=0."], "unavailable": []},
            {"id": "secrets_review", "label": "Secrets Exposure Review", "score": 88, "source_score": 88, "presented_score": 82, "status": "yellow", "findings": ["trufflehog returned 1 finding(s) requiring human triage."], "evidence": ["Exact-snapshot gitleaks status=completed; findings=0."], "unavailable": []},
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 56,
                "source_score": 56,
                "presented_score": 28,
                "status": "yellow",
                "evidence": [
                    "Exact-snapshot semgrep status=completed; findings=108; commit=abc.",
                    "Exact-snapshot typescript status=completed; findings=1; commit=abc.",
                    "Bandit triage artifact attached: blocking=0, needs_review=45, approved=0, candidate_false_positive=160.",
                ],
                "findings": [
                    "Scanner-worker static tools reported 109 finding(s).",
                    "bandit ended with status failed; its output requires human review.",
                    "semgrep returned 108 finding(s) requiring human triage.",
                    "typescript returned 1 finding(s) requiring human triage.",
                    "Parsed Bandit artifact reported 205 finding(s).",
                    "Bandit triage summary: total=205, blocker_count=0, review_required_count=205, candidate_false_positive_count=0.",
                ],
                "unavailable": [
                    "Accepted clean execution evidence unavailable for: bandit, eslint.",
                    "eslint was unavailable in the exact-snapshot scanner: No ESLint configuration exists and the package lint script does not execute ESLint.",
                    "Accepted clean execution evidence unavailable for: semgrep.",
                    "Bandit source distinction: parsed artifact exists but live execution is not verified.",
                ],
            },
            {"id": "ci_cd", "label": "CI/CD Analysis", "score": 95, "source_score": 95, "presented_score": 92, "status": "green", "findings": ["Historical workflow reliability includes 21 non-success run(s)."], "evidence": ["Current release checks are successful."], "unavailable": []},
            {
                "id": "architecture_debt",
                "label": "Architecture & Technical Debt",
                "score": 94,
                "source_score": 94,
                "presented_score": 86,
                "status": "green",
                "evidence": [
                    "Repository root contains nico/.",
                    "Complexity engine analyzed 1160 source files and 157427 LOC.",
                    "Top complexity hotspot: nico/mid_review_enforcement.py hotspot_score=517.65, max_function_cyclomatic=None, density=None, churn=899.",
                ],
                "findings": ["At least one function has very high cyclomatic complexity."],
                "unavailable": [],
            },
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "score": 73, "source_score": 73, "presented_score": 67, "status": "yellow", "findings": [], "evidence": ["Commit velocity: 100 commits over 180 days."], "unavailable": ["Stakeholder expectation data is unavailable."]},
            {"id": "scanner_worker_evidence", "label": "Scanner Worker Evidence", "score": None, "presented_score": None, "directly_scored": False, "status": "supplemental", "evidence": [], "findings": [], "unavailable": []},
            {"id": "client_acceptance", "label": "Client / Human Acceptance", "score": None, "presented_score": None, "directly_scored": False, "status": "gray", "evidence": [], "findings": [], "unavailable": []},
        ],
    }


def test_static_candidate_volume_and_failed_analyzer_do_not_create_critical_score():
    result = calibrate_express_truth(_sample_result())
    static = next(item for item in result["sections"] if item["id"] == "static_analysis")
    assert static["score_value"] is None
    assert static["technical_score_display"] == "NOT SCORED"
    assert static["assurance_label"] == "REVIEW LIMITED"
    assert static["diagnostic_score_before_truth_gate"] == 28
    assert not any("unavailable for: semgrep" in item.lower() for item in static["unavailable"])
    assert any("45 candidate(s) requiring review" in item for item in static["findings"])
    assert any("160 candidate false-positive" in item for item in static["findings"])
    assert not any("review_required_count=205" in item for item in static["findings"])


def test_evidence_constraints_do_not_reduce_technical_scores_and_unscored_is_not_zero():
    result = _sample_result()
    records, adjusted = calibrated_score_records(result)
    by_id = {item.section_id: item for item in records}
    assert by_id["dependency_health"].presented_score == 76
    assert by_id["secrets_review"].presented_score == 88
    assert by_id["velocity_complexity"].presented_score == 73
    assert by_id["ci_cd"].presented_score == 92
    assert by_id["architecture_debt"].presented_score == 86
    assert "static_analysis" not in by_id
    assert result["maturity_signal"]["score"] == 85
    assert result["maturity_signal"]["level"] == "Strong"
    assert adjusted == 83
    assert "static_analysis" in result["maturity_signal"]["unscored_controls_excluded"]


def test_internal_none_metrics_and_legacy_mid_label_are_removed():
    result = calibrate_express_truth(_sample_result())
    architecture = next(item for item in result["sections"] if item["id"] == "architecture_debt")
    visible = " ".join(architecture["evidence"] + architecture["findings"])
    assert "max_function_cyclomatic=None" not in visible
    assert "density=None" not in visible
    assert "Repository root contains" not in visible
    assert result["maturity_signal"]["level"] != "Mid"
    assert " Mid " not in f" {result['executive_summary']} "


def test_client_tables_show_assurance_disposition_not_legacy_yellow_green_status():
    result = _sample_result()
    calibrated_score_records(result)
    records = _pdf_records(result)
    dependency = next(item for item in records if item["section_id"] == "dependency_health")
    ci = next(item for item in records if item["section_id"] == "ci_cd")
    static = next(item for item in records if item["section_id"] == "static_analysis")
    assert dependency["canonical_status"] == "REVIEW LIMITED"
    assert ci["canonical_status"] == "VERIFIED"
    assert static["canonical_status"] == "REVIEW LIMITED"
    assert static["score_label"] == "NOT SCORED"
