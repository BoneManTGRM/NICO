from __future__ import annotations

from pathlib import Path

from nico.comprehensive_authoritative_scanner_truth_v62 import (
    reconcile_authoritative_scanner_truth,
)

ROOT = Path(__file__).resolve().parents[1]
TOOLS = [
    "pip-audit",
    "npm-audit",
    "osv-scanner",
    "bandit",
    "semgrep",
    "eslint",
    "typescript",
    "gitleaks",
    "trufflehog",
]


def _record(name: str, *, completed: bool = True, source: str = "json") -> dict:
    return {
        "scanner_name": name,
        "status": "completed" if completed else "failed",
        "completed": completed,
        "verified": completed,
        "verified_for_this_report": completed,
        "exact_commit_match": True,
        "artifact_hash": name.replace("-", "") * 4,
        "finding_count": 0,
        "execution_source": source,
        "failure_reason": "" if completed else "scanner execution failed",
    }


def test_live_manifest_preserves_failed_bandit_even_if_finalizer_drops_record() -> None:
    records = [_record(name) for name in TOOLS if name != "bandit"]
    canonical = {
        "assessment": {
            "technical_score": 92,
            "maturity_level": "Senior",
            "incomplete_analyzers": ["bandit", "gitleaks"],
            "analyzer_execution_coverage": 78,
            "sections": [
                {
                    "label": "Static Analysis",
                    "summary": "Analyzer execution coverage is 88%.",
                    "analyzer_execution_coverage": 88,
                }
            ],
        },
        "scanner_execution_records": records,
        "live_scanner_evidence": {
            "tools_requested": TOOLS,
            "tools_run": [name for name in TOOLS if name != "bandit"],
            "failed_tools": ["bandit"],
            "unavailable_tools": [],
            "timed_out_tools": [],
        },
        "provenance": {
            "completed_applicable_analyzers": 9,
            "incomplete_applicable_analyzers": 0,
            "analyzer_execution_coverage": 100,
        },
    }

    result = reconcile_authoritative_scanner_truth(canonical)
    contract = result["client_readiness_contract"]

    assert result["analyzer_execution_coverage"] == 89
    assert result["assessment"]["analyzer_execution_coverage"] == 89
    assert result["assessment"]["incomplete_analyzers"] == ["bandit"]
    assert result["provenance"]["analyzer_execution_coverage"] == 89
    assert result["provenance"]["incomplete_applicable_analyzers"] == 1
    assert "coverage is 89%" in result["assessment"]["sections"][0]["summary"]
    assert result["assessment"]["maturity_level"] == "Exceptional"
    assert contract["coverage_numerator"] == 8
    assert contract["coverage_denominator"] == 9
    assert contract["incomplete_analyzers"] == ["bandit"]
    assert contract["recursive_stale_projection_counts_ignored"] is True
    assert contract["authoritative_source"] == (
        "direct_exact_run_records_plus_live_scanner_manifest"
    )


def test_live_manifest_and_exact_records_produce_honest_full_coverage() -> None:
    canonical = {
        "assessment": {
            "technical_score": 92,
            "maturity_level": "Senior",
            "incomplete_analyzers": ["bandit", "gitleaks"],
            "analyzer_execution_coverage": 78,
        },
        "scanner_execution_records": [
            _record(
                name,
                source="canonical_bandit_json_v62" if name == "bandit" else "json",
            )
            for name in TOOLS
        ],
        "live_scanner_evidence": {
            "tools_requested": TOOLS,
            "tools_run": TOOLS,
            "failed_tools": [],
            "unavailable_tools": [],
            "timed_out_tools": [],
        },
    }

    result = reconcile_authoritative_scanner_truth(canonical)
    contract = result["client_readiness_contract"]

    assert result["analyzer_execution_coverage"] == 100
    assert result["completed_applicable_analyzers"] == 9
    assert result["incomplete_applicable_analyzers"] == 0
    assert result["assessment"]["incomplete_analyzers"] == []
    assert contract["coverage_numerator"] == 9
    assert contract["coverage_denominator"] == 9
    assert contract["incomplete_analyzers"] == []
    assert contract["maturity_label"] == "Exceptional"


def test_report_runtime_reconciles_after_authoritative_projection_without_redesign() -> None:
    source = (
        ROOT / "nico" / "comprehensive_client_report_render_v60.py"
    ).read_text(encoding="utf-8")
    mobile = (
        ROOT / "nico" / "comprehensive_mobile_score_projection_v2.py"
    ).read_text(encoding="utf-8")

    assert "single_pass.project_authoritative_canonical = project" in source
    assert "reconcile_authoritative_scanner_truth(current(value))" in source
    assert '"single_pass_projection_bound": projection_bound' in source
    assert '"existing_renderer_preserved": True' in source
    assert '"redesign_performed": False' in source
    assert '"existing_report_renderer_preserved": True' in mobile
    assert '"report_redesign_performed": False' in mobile
