from __future__ import annotations

from nico import express_truth_calibration_v36 as v36
from nico.express_truth_calibration_v38_compat import (
    _selective_score_records,
    _selective_truth,
    _uses_v36_truth_model,
    install_express_truth_calibration_v38_compat,
)


def _target_result() -> dict:
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"level": "Mid", "score": 81},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "score": 86, "status": "green", "evidence": [], "findings": [], "unavailable": []},
            {"id": "dependency_health", "label": "Dependency", "score": 76, "status": "yellow", "evidence": [], "findings": ["npm-audit returned 2 finding(s) requiring human triage."], "unavailable": []},
            {"id": "secrets_review", "label": "Secrets", "score": 88, "status": "yellow", "evidence": [], "findings": ["trufflehog returned 1 finding(s) requiring human triage."], "unavailable": []},
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 56,
                "presented_score": 28,
                "status": "yellow",
                "evidence": [
                    "Exact-snapshot semgrep status=completed; findings=108.",
                    "Exact-snapshot typescript status=completed; findings=1.",
                    "Bandit triage artifact attached: blocking=0, needs_review=45, approved=0, candidate_false_positive=160.",
                ],
                "findings": ["bandit ended with status failed; its output requires human review."],
                "unavailable": [
                    "Accepted clean execution evidence unavailable for: bandit, eslint.",
                    "eslint was unavailable in the exact-snapshot scanner: No ESLint configuration exists and the package lint script does not execute ESLint.",
                    "Accepted clean execution evidence unavailable for: semgrep.",
                ],
            },
            {"id": "ci_cd", "label": "CI/CD", "score": 95, "status": "green", "evidence": [], "findings": ["Historical workflow reliability includes 21 non-success run(s)."], "unavailable": []},
            {"id": "architecture_debt", "label": "Architecture", "score": 94, "status": "green", "evidence": [], "findings": ["At least one function has very high cyclomatic complexity."], "unavailable": []},
            {"id": "velocity_complexity", "label": "Velocity", "score": 73, "status": "yellow", "evidence": [], "findings": [], "unavailable": ["Stakeholder context unavailable."]},
        ],
    }


def test_calibration_signature_is_narrow_and_explicit() -> None:
    target = _target_result()
    assert _uses_v36_truth_model(target) is True
    target["sections"][3]["evidence"] = ["Semgrep artifact attached."]
    assert _uses_v36_truth_model(target) is False


def test_target_signature_removes_contradictory_eslint_and_semgrep_limitations() -> None:
    install_express_truth_calibration_v38_compat()
    result = _selective_truth(_target_result())
    static = next(item for item in result["sections"] if item["id"] == "static_analysis")
    limitations = " ".join(static["unavailable"]).casefold()
    assert "semgrep" not in limitations
    assert "eslint" not in limitations
    assert "bandit" in limitations
    assert static["score_value"] is None
    assert static["status"] == "yellow"
    assert static["assurance_label"] == "REVIEW LIMITED"


def test_non_target_scoring_retains_v33_evidence_deduction_contract() -> None:
    result = {
        "maturity_signal": {"level": "Mid", "score": 88},
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency",
                "score": 90,
                "status": "green",
                "evidence": [],
                "findings": ["OSV candidate requires human triage."],
                "unavailable": [],
            }
        ],
    }
    records, overall = _selective_score_records(result)
    assert records[0].presented_score == 85
    assert records[0].status == "yellow"
    assert overall == 85


def test_metric_cleanup_does_not_relabel_unrelated_score_evidence() -> None:
    install_express_truth_calibration_v38_compat()
    trend = "Project trend evidence: previous score=89; current score=87."
    hotspot = "Complexity hotspot: module.py score=517.65, max_function_cyclomatic=None, density=None."
    assert v36._clean_metric_text(trend) == trend
    cleaned = v36._clean_metric_text(hotspot)
    assert "hotspot_index=517.65" in cleaned
    assert "max_function_cyclomatic=None" not in cleaned
    assert "density=None" not in cleaned
