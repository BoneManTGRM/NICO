from __future__ import annotations

from pathlib import Path
import hashlib

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
        "artifact_hash": hashlib.sha256(name.encode("utf-8")).hexdigest(),
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


def test_python_only_exact_run_excludes_node_tools_from_applicable_denominator() -> None:
    records = [_record(name) for name in TOOLS[:]]
    reasons = {
        "npm-audit": "No package-lock.json with an adjacent package.json was found.",
        "eslint": "No supported JavaScript or TypeScript source files were found in apps/web/app.",
        "typescript": "Project dependencies were not prepared.",
    }
    for record in records:
        name = record["scanner_name"]
        if name in reasons:
            record.update(
                {
                    "status": "unavailable",
                    "state": "unavailable",
                    "completed": False,
                    "verified": False,
                    "verified_for_this_report": False,
                    "failure_reason": reasons[name],
                }
            )

    canonical = {
        "identity": {"commit_sha": "a" * 40},
        "repository_evidence": {
            "file_evidence": {
                "sampled_paths": ["requirements.txt", "app.py", "src/service.py"]
            },
            "dependency_evidence": {"manifest_paths": ["requirements.txt"]},
        },
        "assessment": {
            "technical_score": 76,
            "sections": [
                {
                    "id": "dependency_library_ecosystem",
                    "unavailable": [
                        "Incomplete applicable analyzers: npm-audit."
                    ],
                },
                {
                    "id": "static_analysis",
                    "unavailable": [
                        "Incomplete applicable analyzers: eslint, typescript."
                    ],
                },
            ],
        },
        "requested_scanner_records": records,
        "scanner_execution_records": [
            record for record in records if record["scanner_name"] not in reasons
        ],
        "live_scanner_evidence": {
            "tools_requested": TOOLS,
            "tools_run": [name for name in TOOLS if name not in reasons],
            "failed_tools": [],
            "unavailable_tools": list(reasons),
            "timed_out_tools": [],
        },
    }

    result = reconcile_authoritative_scanner_truth(canonical)
    contract = result["client_readiness_contract"]

    assert result["analyzer_execution_coverage"] == 100
    assert result["completed_applicable_analyzers"] == 6
    assert result["incomplete_applicable_analyzers"] == 0
    assert len(result["requested_scanner_records"]) == 9
    assert len(result["scanner_execution_records"]) == 6
    assert {
        item["scanner_name"] for item in result["not_applicable_scanner_records"]
    } == set(reasons)
    assert contract["coverage_numerator"] == 6
    assert contract["coverage_denominator"] == 6
    assert contract["incomplete_analyzers"] == []
    assert contract["not_applicable_exact_run_scanners"] == list(reasons)
    assert contract["not_applicable_scanners_receive_completion_credit"] is False
    assert all(
        not section.get("unavailable")
        for section in result["assessment"]["sections"]
    )


def test_node_only_run_rebuilds_phase14_without_inapplicable_or_contract_blockers() -> None:
    records = [_record(name) for name in TOOLS]
    bandit_record = next(item for item in records if item["scanner_name"] == "bandit")
    bandit_record["status"] = "completed_with_findings"
    bandit_record["state"] = "completed_with_findings"
    bandit_record["exit_code"] = 1
    pip_record = next(item for item in records if item["scanner_name"] == "pip-audit")
    pip_record.update(
        {
            "state": "unavailable",
            "status": "unavailable",
            "completed": False,
            "verified": False,
            "verified_complete": False,
            "verified_for_this_report": False,
            "failure_reason": "requirements.txt was not found.",
        }
    )
    canonical = {
        "identity": {"commit_sha": "a" * 40},
        "repository_evidence": {
            "file_evidence": {"sampled_paths": ["package.json", "src/index.ts"]},
            "dependency_evidence": {"manifest_paths": ["package.json"]},
        },
        "requested_scanner_records": records,
        "scanner_execution_records": records,
        "live_scanner_evidence": {
            "tools_requested": TOOLS,
            "tools_run": [name for name in TOOLS if name != "pip-audit"],
            "failed_tools": [],
            "unavailable_tools": ["pip-audit"],
            "timed_out_tools": [],
        },
    }

    result = reconcile_authoritative_scanner_truth(canonical)
    phase14 = result["evidence_health_summary"]["phase14_analyzer_evidence"]
    pip_summary = next(
        item for item in phase14["analyzers"] if item["scanner"] == "pip-audit"
    )

    assert pip_summary["status"] == "not_applicable"
    assert pip_summary["required"] is False
    assert phase14["rejected_records"] == []
    assert not any(item["scanner"] == "pip-audit" for item in phase14["blockers"])
    assert not any(item["scanner"] == "evidence-contract" for item in phase14["blockers"])
    assert set(phase14["required_scanners"]) == set(TOOLS) - {"pip-audit"}
    assert result["evidence_health_summary"]["incomplete_analyzers"] == []
    assert result["evidence_health_summary"]["incomplete_scanner_records"] == []
    assert set(result["evidence_health_summary"]["completed_scanners"]) == set(TOOLS) - {
        "pip-audit"
    }


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
