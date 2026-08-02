from __future__ import annotations

import time

from nico.comprehensive_pre_render_scanner_truth_v65 import (
    canonicalize_stage_results_before_render,
)

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


def _stages() -> dict:
    huge = [
        {
            "path": f"src/file_{index}.py",
            "nested": {"values": list(range(30))},
        }
        for index in range(20_000)
    ]
    return {
        "repository_and_delivery_evidence": {
            "status": "complete",
            "huge_file_inventory": huge,
        },
        "dependency_security_static_analysis": {
            "status": "complete",
            "scanner": {
                "tools_requested": list(TOOLS),
                "tools_run": list(TOOLS),
                "failed_tools": [],
                "unavailable_tools": [],
                "timed_out_tools": [],
            },
            "evidence": {
                "incomplete_analyzers": ["pip-audit"],
                "incomplete_applicable_analyzers": 1,
                "analyzer_execution_coverage": 89,
                "flattened": [
                    "contract.incomplete_analyzers[0]: pip-audit"
                ],
            },
        },
        "evidence_reconciliation_and_scoring": {
            "status": "complete",
            "client_readiness_contract": {
                "authoritative_source": "exact-run",
                "requested_exact_run_scanners": list(TOOLS),
                "completed_exact_commit_scanners": list(TOOLS),
                "incomplete_analyzers": ["pip-audit"],
                "coverage_denominator": 9,
            },
            "assessment": {"sections": []},
            "evidence": {},
        },
    }


def test_large_unrelated_evidence_is_not_copied_or_traversed() -> None:
    stages = _stages()
    huge = stages["repository_and_delivery_evidence"]["huge_file_inventory"]
    started = time.perf_counter()

    cleaned, manifest = canonicalize_stage_results_before_render(stages)

    elapsed = time.perf_counter() - started
    assert elapsed < 5.0
    assert cleaned["repository_and_delivery_evidence"]["huge_file_inventory"] is huge
    evidence = cleaned["dependency_security_static_analysis"]["evidence"]
    assert evidence["incomplete_analyzers"] == []
    assert evidence["incomplete_applicable_analyzers"] == 0
    assert evidence["analyzer_execution_coverage"] == 100
    assert evidence["flattened"] == []
    assert manifest["copy_on_write"] is True
    assert manifest["nodes_visited"] < 5_000
    assert manifest["raw_stage_evidence_mutated"] is False


def test_second_report_builder_pass_skips_duplicate_canonicalization() -> None:
    cleaned, first = canonicalize_stage_results_before_render(_stages())
    started = time.perf_counter()

    second_cleaned, second = canonicalize_stage_results_before_render(cleaned)

    assert time.perf_counter() - started < 0.25
    assert second["status"] == "already_applied"
    assert second["duplicate_canonicalization_skipped"] is True
    assert (
        second_cleaned["dependency_security_static_analysis"]
        is cleaned["dependency_security_static_analysis"]
    )
    assert first["coverage"] == second["coverage"] == 100


def test_unknown_and_genuine_incomplete_evidence_remains_fail_closed() -> None:
    stages = _stages()
    scanner = stages["dependency_security_static_analysis"]["scanner"]
    scanner["tools_run"].remove("semgrep")
    scanner["failed_tools"] = ["semgrep"]
    evidence = stages["dependency_security_static_analysis"]["evidence"]
    evidence["incomplete_analyzers"] = [
        "pip-audit",
        "semgrep",
        "custom analyzer",
    ]

    cleaned, manifest = canonicalize_stage_results_before_render(stages)

    assert manifest["incomplete"] == ["semgrep"]
    assert cleaned["dependency_security_static_analysis"]["evidence"][
        "incomplete_analyzers"
    ] == ["semgrep", "custom analyzer"]
    assert manifest["unknown_evidence_preserved_fail_closed"] is True
