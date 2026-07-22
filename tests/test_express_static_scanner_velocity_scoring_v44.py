from __future__ import annotations

from nico.express_static_scanner_velocity_scoring_v44 import (
    apply_express_static_scanner_velocity_scoring_v44,
)


def _section(section_id: str, score: int | None, status: str = "verified") -> dict:
    return {
        "id": section_id,
        "label": section_id,
        "score": score,
        "source_score": score,
        "presented_score": score,
        "score_value": score,
        "status": status,
        "presented_status": status,
        "assurance_status": status,
        "directly_scored": score is not None,
        "exclude_from_maturity": score is None,
        "evidence": [],
        "findings": [],
        "unavailable": [],
    }


def _result() -> dict:
    code = _section("code_audit", 86)
    dependency = _section("dependency_health", 86, "review_limited")
    dependency["evidence"] = [
        "Scanner-worker dependency tools completed: pip-audit, npm-audit, osv-scanner."
    ]
    secrets = _section("secrets_review", 88, "review_limited")
    secrets["evidence"] = [
        "Exact-snapshot trufflehog status=completed; findings=1; commit=abc.",
    ]
    secrets["findings"] = [
        "gitleaks ended with status timeout; its output requires human review."
    ]
    static = _section("static_analysis", None, "review_limited")
    static.update(
        {
            "directly_scored": False,
            "exclude_from_maturity": True,
            "evidence": [
                "Exact-snapshot semgrep status=completed; findings=108; commit=abc.",
                "Exact-snapshot typescript status=completed; findings=1; commit=abc.",
                "Bandit triage artifact attached: blocking=0, needs_review=45, approved=0, candidate_false_positive=163.",
                "ESLint is not configured for this snapshot and is treated as not applicable.",
            ],
            "findings": [
                "bandit ended with status failed; its output requires human review before client-facing conclusions.",
                "Semgrep and TypeScript produced 109 unverified candidate(s) requiring triage.",
                "Bandit attached triage records 45 candidate(s) requiring review and 163 candidate false-positive(s); verified blockers=0, approved=0.",
            ],
            "unavailable": [
                "Live Bandit execution failed for this exact snapshot."
            ],
        }
    )
    ci = _section("ci_cd", 92)
    architecture = _section("architecture_debt", 87)
    velocity = _section("velocity_complexity", 73, "review_limited")
    velocity["evidence"] = [
        "Commit velocity: 100 commits over 180 days (3.89/week).",
        "Pull request traceability ratio: 100 PRs / 100 commits = 1.0.",
        "Source-file footprint from recursive tree: 1172 files.",
        "Complexity engine current-run artifact completed: 1181 source file(s), 160867 LOC, risk=medium.",
        "Project trend unavailable: no prior completed Express runs were found for this project in retained storage.",
    ]
    velocity["unavailable"] = [
        "Precise story-point expectation, reviewer seniority, and business-value mapping require stakeholder context and human review."
    ]
    scanner = _section("scanner_worker_evidence", None, "supplemental")
    scanner.update(
        {
            "directly_scored": False,
            "exclude_from_maturity": True,
            "evidence": [
                "Scanner-worker dependency tools completed: pip-audit, npm-audit, osv-scanner.",
                "Exact-snapshot trufflehog status=completed; findings=1.",
                "Exact-snapshot semgrep status=completed; findings=108.",
                "Exact-snapshot typescript status=completed; findings=1.",
                "Scanner-worker static artifacts were observed for: bandit, eslint, typescript.",
            ],
            "findings": [
                "gitleaks ended with status timeout.",
                "bandit ended with status failed.",
            ],
            "unavailable": [
                "No ESLint configuration exists; ESLint is not applicable."
            ],
        }
    )
    acceptance = _section("client_acceptance", None, "human_review_pending")
    return {
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"score": 87, "presented_score": 85, "level": "Strong"},
        "sections": [
            code,
            dependency,
            secrets,
            static,
            ci,
            architecture,
            velocity,
            scanner,
            acceptance,
        ],
    }


def test_static_receives_bounded_strong_score_when_minimum_evidence_is_accepted() -> None:
    result = apply_express_static_scanner_velocity_scoring_v44(_result())
    static = next(item for item in result["sections"] if item["id"] == "static_analysis")
    assert static["score_value"] == 82
    assert static["score_band_label"] == "STRONG"
    assert static["assurance_label"] == "REVIEW LIMITED"
    assert static["analyzer_execution_coverage"] == 83
    assert static["directly_scored"] is True
    assert static["exclude_from_maturity"] is False
    assert "capped below Exceptional" in static["score_rationale"]


def test_scanner_worker_gets_execution_coverage_without_double_counting() -> None:
    result = apply_express_static_scanner_velocity_scoring_v44(_result())
    scanner = next(item for item in result["sections"] if item["id"] == "scanner_worker_evidence")
    assert scanner["score_value"] == 75
    assert scanner["score_kind"] == "execution_coverage"
    assert scanner["score_band_label"] == "EXECUTION COVERAGE"
    assert scanner["directly_scored"] is False
    assert scanner["exclude_from_maturity"] is True
    assert scanner["included_in_maturity"] is False
    assert scanner["scanner_execution_completed"] == [
        "npm-audit",
        "osv-scanner",
        "pip-audit",
        "semgrep",
        "trufflehog",
        "typescript",
    ]


def test_velocity_moves_to_strong_when_objective_signals_pass() -> None:
    result = apply_express_static_scanner_velocity_scoring_v44(_result())
    velocity = next(item for item in result["sections"] if item["id"] == "velocity_complexity")
    assert velocity["score_value"] == 85
    assert velocity["score_band_label"] == "STRONG"
    assert velocity["assurance_label"] == "REVIEW LIMITED"
    assert "3.89/week" in velocity["score_rationale"]
    assert "1.00" in velocity["score_rationale"]


def test_weighted_headline_remains_stable_and_truthful() -> None:
    result = apply_express_static_scanner_velocity_scoring_v44(_result())
    assert result["technical_score"] == 87
    assert result["evidence_adjusted_score"] == 85
    records = result["express_weighted_scoring"]["records"]
    scanner = next(item for item in records if item["section_id"] == "scanner_worker_evidence")
    static = next(item for item in records if item["section_id"] == "static_analysis")
    assert scanner["included"] is False
    assert static["included"] is True
