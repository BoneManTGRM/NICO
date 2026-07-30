from __future__ import annotations

from copy import deepcopy

from nico.dependency_materiality import classify_dependency_finding
from nico.mid_static_score_accuracy import apply_verified_control_reconciliation
from nico.snapshot_scanner_worker import _finding_summary


def _assessment() -> dict:
    return {
        "sections": [
            {"id": "code_audit", "score": 72, "status": "yellow", "evidence": [], "findings": []},
            {"id": "dependency_health", "score": 31, "status": "red", "evidence": [], "findings": []},
            {"id": "secrets_review", "score": 80, "status": "green", "evidence": [], "findings": []},
            {"id": "static_analysis", "score": 80, "status": "green", "evidence": [], "findings": []},
            {"id": "ci_cd", "score": 80, "status": "green", "evidence": [], "findings": []},
            {"id": "architecture_debt", "score": 78, "status": "yellow", "evidence": [], "findings": []},
            {"id": "velocity_complexity", "score": 74, "status": "yellow", "evidence": [], "findings": []},
        ],
        "maturity_signal": {"score": 70, "level": "Mid"},
        "scorecard": {"technical_score": 70},
    }


def _repository() -> dict:
    return {
        "status": "attached",
        "file_evidence": {"files_profiled": 100},
        "architecture_evidence": {
            "source_file_count": 300,
            "test_path_count": 100,
            "documentation_path_count": 20,
        },
        "activity_evidence": {"commits_returned": 50, "pull_requests_returned": 20},
        "dependency_evidence": {
            "manifest_paths": ["requirements.txt", "apps/web/package.json"],
            "lockfile_paths": ["apps/web/package-lock.json"],
            "dependency_entries": 200,
        },
        "code_signal_evidence": {"risk_pattern_hits": 0, "todo_fixme_security_notes": 0},
    }


def _osv_review_candidate() -> dict:
    return {
        "id": "GHSA-review-only",
        "aliases": ["CVE-2099-0001"],
        "package": "example-package",
        "installed_version": "1.0.0",
        "fixed_versions": ["1.0.1"],
        "dependency_path": "apps/web/package-lock.json",
        "severity": "high",
        # Production scope and reachability are deliberately not verified.
    }


def _verified_material_candidate() -> dict:
    return {
        **_osv_review_candidate(),
        "scope": "production",
        "reachability": "reachable",
    }


def test_high_severity_without_scope_and_reachability_is_review_only() -> None:
    result = classify_dependency_finding(_osv_review_candidate())

    assert result["disposition"] == "triage_required"
    assert result["material"] is False
    assert result["technical_score_impact"] == "assurance_only"
    assert set(result["missing_disposition_fields"]) == {"production_scope", "reachability"}
    assert result["package"] == "example-package"
    assert result["fixed_version"] == "1.0.1"


def test_complete_production_reachable_advisory_is_material() -> None:
    result = classify_dependency_finding(_verified_material_candidate())

    assert result["disposition"] == "verified_material"
    assert result["material"] is True
    assert result["technical_score_impact"] == "material"
    assert result["missing_disposition_fields"] == []


def test_explicit_unreachable_advisory_is_retained_as_verified_non_material() -> None:
    candidate = {**_verified_material_candidate(), "reachability": "unreachable"}
    result = classify_dependency_finding(candidate)

    assert result["disposition"] == "verified_non_material"
    assert result["material"] is False
    assert result["technical_score_impact"] == "none"


def test_snapshot_summary_does_not_convert_osv_severity_into_materiality() -> None:
    results = [
        {
            "tool": "pip-audit",
            "category": "dependency",
            "status": "completed",
            "findings": [],
        },
        {
            "tool": "npm-audit",
            "category": "dependency",
            "status": "completed",
            "findings": [],
        },
        {
            "tool": "osv-scanner",
            "category": "dependency",
            "status": "completed",
            "findings": [_osv_review_candidate()],
        },
    ]

    summary = _finding_summary(results)

    assert summary["by_category"]["dependency"]["raw"] == 1
    assert summary["by_category"]["dependency"]["material"] == 0
    assert summary["by_category"]["dependency"]["review_required"] == 1
    assert results[2]["findings"][0]["disposition"] == "triage_required"
    assert "reachability" in results[2]["findings"][0]["missing_disposition_fields"]


def test_verified_material_dependency_still_caps_score() -> None:
    results = [
        {
            "tool": "osv-scanner",
            "category": "dependency",
            "status": "completed",
            "findings": [_verified_material_candidate()],
        }
    ]
    summary = _finding_summary(results)

    assert summary["by_category"]["dependency"]["material"] == 1
    assert summary["material_total"] == 1


def test_clean_exact_audits_and_review_only_osv_can_recover_dependency_score() -> None:
    results = [
        {
            "tool": tool,
            "category": "dependency",
            "status": "completed",
            "verified_for_this_report": True,
            "current_run": True,
            "findings": [] if tool != "osv-scanner" else [_osv_review_candidate()],
        }
        for tool in ("pip-audit", "npm-audit", "osv-scanner")
    ]
    summary = _finding_summary(results)
    scanner = {
        "status": "attached",
        "snapshot_match": True,
        "tools_requested": ["pip-audit", "npm-audit", "osv-scanner"],
        "tools_run": ["pip-audit", "npm-audit", "osv-scanner"],
        "failed_tools": [],
        "timed_out_tools": [],
        "unavailable_tools": [],
        "scanner_results": results,
        "finding_summary": summary,
    }

    original = _assessment()
    reconciled = apply_verified_control_reconciliation(
        deepcopy(original),
        _repository(),
        scanner,
    )
    dependency = next(
        section for section in reconciled["sections"] if section["id"] == "dependency_health"
    )

    assert summary["by_category"]["dependency"]["material"] == 0
    assert summary["by_category"]["dependency"]["review_required"] == 1
    assert dependency["score"] == 88
    assert dependency["status"] == "green"
    assert reconciled["scorecard"]["technical_score"] > original["scorecard"]["technical_score"]
    assert dependency["findings"] == original["sections"][1]["findings"]
