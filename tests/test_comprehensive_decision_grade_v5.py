from __future__ import annotations

from pathlib import Path

from nico.comprehensive_decision_grade_assessment_v5 import build_decision_grade_assessment
from nico.comprehensive_decision_grade_model_v5 import _score_band
from nico.comprehensive_decision_grade_report_v5 import build_comprehensive_report_package
from nico.comprehensive_decision_grade_v5 import install_decision_grade_binding

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "nico" / "api" / "comprehensive_production_bootstrap.py"


def _repo() -> dict:
    return {
        "architecture_evidence": {"source_file_count": 100, "test_path_count": 40},
        "dependency_evidence": {
            "dependency_entries": 12,
            "lockfile_paths": ["package-lock.json"],
        },
        "activity_evidence": {
            "commits_returned": 100,
            "pull_requests_returned": 80,
            "merged_pull_requests": 70,
        },
        "workflow_evidence": {
            "workflow_file_count": 10,
            "successful_runs": 90,
            "non_success_runs": 4,
            "explicit_permissions_present": True,
            "jobs_observed": 25,
            "job_success_rate": 0.96,
        },
        "code_signal_evidence": {
            "risk_pattern_hits": 1,
            "risk_pattern_samples": ["nico/example.py:12: unsafe pattern"],
            "potential_secret_pattern_hits": 0,
        },
        "unavailable_data_notes": [],
    }


def _scan() -> dict:
    return {
        "status": "complete",
        "tools_run": ["npm-audit", "osv-scanner", "bandit"],
        "unavailable_tools": ["gitleaks", "trufflehog"],
        "failed_tools": ["semgrep"],
        "timed_out_tools": [],
        "finding_summary": {
            "by_category": {
                "dependency": {"raw": 2, "material": 0, "review_required": 2},
                "static": {"raw": 1, "material": 0, "review_required": 1},
                "secret": {"raw": 0, "material": 0, "review_required": 0},
            }
        },
        "scanner_results": [],
        "unavailable_data_notes": ["Dedicated history scanners were unavailable."],
    }


def _complexity() -> dict:
    return {
        "complexity_score": 78,
        "files_analyzed": 54,
        "functions_measured": 247,
        "high_complexity_functions": 53,
        "high_complexity_ratio": 0.2146,
        "deep_nesting_functions": 18,
        "duplicate_evidence": {"duplicate_line_ratio": 0.0401},
        "hotspots": [
            {
                "path": "apps/web/app/assessment/MidSectionReview.tsx",
                "line": 1,
                "name": "<module-logic>",
                "cyclomatic_complexity": 148,
                "loc": 340,
            }
        ],
    }


def test_score_band_is_separate_from_assurance() -> None:
    assert _score_band(92)["score_band_label"] == "EXCEPTIONAL"
    assert _score_band(82)["score_band_label"] == "STRONG"
    assert _score_band(78)["score_band_label"] == "MODERATE"


def test_secret_section_does_not_inherit_dependency_or_static_candidates() -> None:
    assessment = build_decision_grade_assessment(
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        run_id="comprun_v5_test",
        repo=_repo(),
        complexity=_complexity(),
        scan=_scan(),
    )
    sections = {item["id"]: item for item in assessment["sections"]}
    secret = sections["secrets_review"]
    dependency = sections["dependency_health"]
    static = sections["static_analysis"]

    assert "raw=0" in " ".join(secret["evidence"])
    assert not any("3 scanner candidate" in item for item in secret["findings"])
    assert any("dependency candidate" in item for item in dependency["findings"])
    assert any("static-analysis candidate" in item for item in static["findings"])
    assert any("MidSectionReview.tsx" in item for item in sections["architecture_debt"]["findings"])


def test_decision_grade_binding_is_the_production_bootstrap_path() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")
    assert "install_decision_grade_binding" in source
    assert source.index("report_binding = install_decision_grade_binding()") < source.index(
        "native_providers = install_native_comprehensive_providers(target)"
    )


def test_binding_installs_canonical_scoring_and_report_builder() -> None:
    status = install_decision_grade_binding()
    assert status["bound"] is True
    assert status["canonical_scoring_bound"] is True
    assert status["secret_category_isolated"] is True
    assert status["score_band_separated_from_assurance"] is True
    assert callable(build_comprehensive_report_package)
    assert status["human_review_required"] is True
    assert status["client_delivery_allowed"] is False
