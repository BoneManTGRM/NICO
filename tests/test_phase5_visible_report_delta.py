from __future__ import annotations

from nico.phase5_report_truth_v2 import install_phase5_report_truth_v2


TARGET = "b" * 40


def _completed(tool: str, category: str) -> dict:
    return {
        "tool": tool,
        "category": category,
        "status": "completed",
        "target_commit_sha": TARGET,
        "verified_for_this_report": True,
        "output_capture_complete": True,
        "raw_artifact_capture_complete": True,
        "returncode_valid": True,
        "timed_out": False,
        "scans_git_history": tool in {"gitleaks", "trufflehog"},
        "full_history_verified": True if tool in {"gitleaks", "trufflehog"} else False,
        "findings": [],
        "findings_count": 0,
        "artifact_hash": f"artifact-{tool}",
        "raw_artifact_sha256": f"raw-{tool}",
        "deterministic_fingerprint": f"fingerprint-{tool}",
    }


def test_markdown_contains_real_scanner_ci_and_complexity_delta() -> None:
    install_phase5_report_truth_v2()
    from nico import comprehensive_report_package as base_report
    from nico.comprehensive_decision_grade_markdown_v5 import (
        _build_markdown,
        _decorate_assessment,
        _limitation_metrics,
        _stage_summaries,
    )

    assessment = {
        "maturity_signal": {"score": 85, "presented_score": 85},
        "canonical_evidence_adjusted_score": 83,
        "sections": [
            {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "score": 92, "evidence": [], "findings": [], "unavailable": []},
            {"id": "secrets_review", "label": "Secrets Exposure Review", "score": 93, "evidence": [], "findings": [], "unavailable": []},
            {"id": "static_analysis", "label": "Static Analysis", "score": 79, "evidence": [], "findings": [], "unavailable": []},
            {"id": "ci_cd", "label": "CI/CD Analysis", "score": 78, "evidence": [], "findings": ["14 historical workflow runs were non-successful"], "unavailable": []},
        ],
        "findings_register": [
            {"finding_id": "old-bandit", "category": "evidence", "title": "bandit evidence unavailable"},
            {
                "finding_id": "old-complexity",
                "category": "architecture",
                "title": "Complexity hotspot: _build_complexity",
                "evidence": "cyclomatic_complexity=94; loc=144",
            },
        ],
        "decision_postures": {},
        "how_to_use_report": [],
        "scope_boundaries": [],
        "assumption_register": [],
        "human_review_required": True,
        "client_ready": False,
    }
    tools = {
        "bandit": _completed("bandit", "static"),
        "eslint": _completed("eslint", "static"),
        "gitleaks": _completed("gitleaks", "secret"),
        "osv-scanner": _completed("osv-scanner", "dependency"),
    }
    ci_summary = {
        "schema": "nico.ci_history_summary.v1",
        "current_branch_health": {"green": True, "required_checks": 4, "successful_required_checks": 4},
        "historical_reliability": {
            "classified_counts": {
                "success": 8,
                "genuine_failure": 1,
                "superseded_cancellation": 2,
                "manual_cancellation": 0,
                "expected_or_unclassified_cancellation": 0,
                "infrastructure_fault": 0,
                "unknown_review_required": 0,
            },
            "genuine_failure_rate": 0.1111,
        },
        "cancellations_counted_as_failures": False,
    }
    stages = {
        "evidence_reconciliation_and_scoring": {"commit_sha": TARGET, "assessment": assessment},
        "deep_scanner_triage": {"target_commit_sha": TARGET, "tools": tools},
        "ci_cd_architecture_complexity_velocity": {
            "commit_sha": TARGET,
            "workflow_evidence": {"classified_history": ci_summary},
            "complexity_evidence": {
                "tracked_function_metrics_are_exact_sha": True,
                "tracked_function_metrics": {
                    "_build_complexity": {
                        "name": "_build_complexity",
                        "path": "nico/typescript_ast_complexity_v1.py",
                        "line": 226,
                        "cyclomatic_complexity": 12,
                        "cognitive_complexity": 10,
                        "loc": 55,
                        "max_nesting": 2,
                        "grade": "B",
                        "method": "python_ast",
                    }
                },
            },
        },
    }

    reconciled = _decorate_assessment(base_report._assessment(stages))
    summaries = _stage_summaries(stages)
    limitations = _limitation_metrics(reconciled, summaries)
    markdown = _build_markdown(
        {
            "repository": "BoneManTGRM/NICO",
            "run_id": "phase5-proof",
            "commit_sha": TARGET,
            "evidence_ledger_id": "ledger-phase5-proof",
            "customer_id": "internal",
            "project_id": "nico",
        },
        reconciled,
        summaries,
        [],
        [],
        limitations,
        "2026-07-27T00:00:00Z",
    )

    complexity_change = reconciled["phase5_verified_outcomes"]["complexity_changes"]["_build_complexity"]
    assert complexity_change["before"] == 94
    assert complexity_change["after"] == 12
    assert complexity_change["delta"] == -82
    assert complexity_change["evidence"]["method"] == "python_ast"
    assert "Verified Change Since Phase 5 Baseline" in markdown
    assert "bandit, eslint, gitleaks, osv-scanner" in markdown
    assert "Workflow outcome classes:" in markdown
    assert "_build_complexity" in markdown and "'after': 12" in markdown
    assert "old-bandit" not in markdown
    assert "Technical maturity" in markdown and "85/100" in markdown
    assert reconciled["maturity_signal"]["presented_score"] == 85
