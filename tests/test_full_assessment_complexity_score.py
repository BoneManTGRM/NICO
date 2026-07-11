from __future__ import annotations

from copy import deepcopy

from nico.evidence_ledger import build_evidence_ledger
from nico.full_assessment_complexity_score import apply_complexity_score
from nico.full_assessment_scorecard import TECHNICAL_SECTION_WEIGHTS, build_full_assessment_scorecard


def _context() -> dict:
    return {
        "run_id": "fullrun_complexity_score",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "cust-complexity-score",
        "project_id": "proj-complexity-score",
    }


def _repository() -> dict:
    return {
        "status": "attached",
        "evidence_id": "repo-complexity-score",
        "run_id": "fullrun_complexity_score",
        "file_evidence": {"files_profiled": 40},
        "architecture_evidence": {
            "source_file_count": 100,
            "test_path_count": 20,
            "documentation_path_count": 10,
            "deployment_manifests": ["Dockerfile"],
            "top_level_directories": ["nico", "apps", "tests"],
        },
        "dependency_evidence": {
            "manifest_paths": ["requirements.txt"],
            "lockfile_paths": ["package-lock.json"],
            "dependency_entries": 50,
        },
        "activity_evidence": {
            "commits_returned": 80,
            "pull_requests_returned": 30,
            "merged_pull_requests": 25,
            "open_pull_requests": 5,
        },
        "workflow_evidence": {
            "workflow_file_count": 3,
            "workflow_run_count": 20,
            "successful_runs": 18,
            "non_success_runs": 2,
            "commands_detected": ["pytest", "npm run lint", "npm run build"],
            "explicit_permissions_present": True,
        },
        "code_signal_evidence": {
            "todo_fixme_security_notes": 0,
            "risk_pattern_hits": 0,
            "potential_secret_pattern_hits": 0,
        },
        "unavailable_data_notes": [],
    }


def _scanner() -> dict:
    tools = ["pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint"]
    return {
        "status": "attached",
        "run_id": "fullrun_complexity_score",
        "scan_id": "scan-complexity-score",
        "tools_requested": tools,
        "tools_run": tools,
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "unavailable_data_notes": [],
    }


def _good_complexity() -> dict:
    return {
        "status": "attached",
        "evidence_id": "complexity-good",
        "run_id": "fullrun_complexity_score",
        "repository": "BoneManTGRM/NICO",
        "analyzer_version": "nico-bounded-complexity-v1",
        "files_analyzed": 30,
        "python_files_analyzed": 30,
        "javascript_typescript_files_analyzed": 0,
        "python_parse_failures": 0,
        "total_source_loc": 3500,
        "functions_measured": 100,
        "average_cyclomatic_complexity": 3.2,
        "maximum_cyclomatic_complexity": 9,
        "high_complexity_functions": 1,
        "very_high_complexity_functions": 0,
        "high_complexity_ratio": 0.01,
        "long_functions": 1,
        "deep_nesting_functions": 1,
        "maximum_nesting": 4,
        "import_edges": 90,
        "internal_import_edges": 40,
        "maximum_fan_out": 8,
        "hotspots": [
            {
                "path": "nico/one.py",
                "line": 10,
                "name": "one",
                "cyclomatic_complexity": 11,
                "loc": 60,
                "max_nesting": 3,
            }
        ],
        "duplicate_evidence": {
            "duplicate_block_groups": 1,
            "duplicate_line_ratio": 0.01,
        },
        "unavailable_data_notes": [],
        "retention_note": "Only bounded numeric and path-level complexity evidence is retained.",
        "guardrail": "Complexity evidence covers the authorized sampled source files only.",
    }


def _assessment() -> dict:
    return build_full_assessment_scorecard(_context(), _repository(), _scanner())


def _velocity(assessment: dict) -> dict:
    return next(item for item in assessment["sections"] if item["id"] == "velocity_complexity")


def test_good_complexity_evidence_raises_only_velocity_and_preserves_weights() -> None:
    baseline = _assessment()
    baseline_velocity = _velocity(baseline)["score"]
    baseline_other = {item["id"]: item["score"] for item in baseline["sections"] if item["id"] != "velocity_complexity"}

    updated = apply_complexity_score(deepcopy(baseline), _good_complexity())
    updated_velocity = _velocity(updated)
    updated_other = {item["id"]: item["score"] for item in updated["sections"] if item["id"] != "velocity_complexity"}

    assert updated_velocity["score"] > baseline_velocity
    assert updated_velocity["score"] <= 95
    assert updated_velocity["confidence"] == "ast-and-sampled-source-bound"
    assert updated_velocity["score_evidence_breakdown"]["weights_changed"] is False
    assert updated_velocity["score_evidence_breakdown"]["thresholds_changed"] is False
    assert updated_other == baseline_other
    assert updated["scorecard"]["weights"] == TECHNICAL_SECTION_WEIGHTS
    assert updated["scorecard"]["complexity_runtime_evidence"]["files_analyzed"] == 30
    assert updated["complexity_artifact"]["status"] == "completed"
    assert updated["complexity_artifact"]["verified_for_this_report"] is True
    assert updated["complexity_artifact"]["report_run_id"] == "fullrun_complexity_score"
    assert any("Complexity engine analyzed" in line for line in updated_velocity["evidence"])

    ledger = build_evidence_ledger({**updated, "status": "complete", "report_run_id": updated["run_id"]})
    coverage = ledger["coverage_by_section"]["velocity_complexity"]
    assert coverage["complete"] is True
    assert coverage["verified_required_tools"] == ["complexity engine"]


def test_missing_complexity_evidence_leaves_score_unchanged() -> None:
    baseline = _assessment()
    updated = apply_complexity_score(deepcopy(baseline), {"status": "unavailable", "files_analyzed": 0})

    assert _velocity(updated)["score"] == _velocity(baseline)["score"]
    assert updated["maturity_signal"]["score"] == baseline["maturity_signal"]["score"]
    assert updated["scorecard"]["complexity_evidence_applied"] is False
    assert "complexity_artifact" not in updated


def test_poor_complexity_evidence_lowers_velocity_instead_of_receiving_credit() -> None:
    complexity = _good_complexity()
    complexity.update(
        {
            "average_cyclomatic_complexity": 15.0,
            "maximum_cyclomatic_complexity": 50,
            "high_complexity_functions": 40,
            "very_high_complexity_functions": 20,
            "high_complexity_ratio": 0.40,
            "long_functions": 30,
            "deep_nesting_functions": 30,
            "maximum_fan_out": 35,
            "duplicate_evidence": {
                "duplicate_block_groups": 20,
                "duplicate_line_ratio": 0.25,
            },
        }
    )
    baseline = _assessment()
    updated = apply_complexity_score(deepcopy(baseline), complexity)
    breakdown = _velocity(updated)["score_evidence_breakdown"]

    assert _velocity(updated)["score"] < _velocity(baseline)["score"]
    assert breakdown["complexity_evidence_increment"] < 0
    assert any("maximum measured complexity" in reason for reason in breakdown["reasons"])
    assert any("duplicate-line ratio" in reason for reason in breakdown["reasons"])
    assert any("Review 40" in finding for finding in _velocity(updated)["findings"])


def test_mismatched_complexity_run_is_not_applied() -> None:
    complexity = _good_complexity()
    complexity["run_id"] = "other-run"
    baseline = _assessment()
    updated = apply_complexity_score(deepcopy(baseline), complexity)

    assert _velocity(updated)["score"] == _velocity(baseline)["score"]
    assert updated["scorecard"]["complexity_evidence_applied"] is False
    assert any("run_id did not match" in note for note in _velocity(updated)["unavailable"])
