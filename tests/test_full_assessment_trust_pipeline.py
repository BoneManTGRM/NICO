from __future__ import annotations

from copy import deepcopy

from nico.full_assessment_api import _attach_assessment_truth_summary
from nico.full_assessment_scorecard import build_full_assessment_scorecard
from nico.full_assessment_trust_pipeline import (
    finalize_full_assessment_exports,
    prepare_full_assessment_trust,
)
from nico.reports import build_report_package
from nico.storage import STORE


def _context(run_id: str = "fullrun_trust") -> dict:
    return {
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "cust-trust",
        "project_id": "proj-trust",
        "client_name": "Client Trust",
        "project_name": "Project Trust",
    }


def _repository(run_id: str = "fullrun_trust") -> dict:
    return {
        "status": "attached",
        "evidence_id": f"repo_{run_id}",
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "file_evidence": {"files_profiled": 40, "tree_paths_seen": 300},
        "architecture_evidence": {
            "source_file_count": 120,
            "test_path_count": 25,
            "documentation_path_count": 12,
            "deployment_manifests": ["Dockerfile", "render.yaml"],
            "top_level_directories": ["nico", "apps", "tests", "docs", ".github"],
        },
        "dependency_evidence": {
            "manifest_paths": ["requirements.txt", "apps/web/package.json"],
            "lockfile_paths": ["apps/web/package-lock.json"],
            "dependency_entries": 60,
            "ecosystems": ["PyPI", "npm"],
        },
        "activity_evidence": {
            "commits_returned": 100,
            "pull_requests_returned": 40,
            "merged_pull_requests": 35,
            "open_pull_requests": 5,
        },
        "workflow_evidence": {
            "workflow_file_count": 4,
            "workflow_run_count": 50,
            "successful_runs": 46,
            "non_success_runs": 4,
            "commands_detected": ["pytest", "npm run lint", "npm run build", "semgrep"],
            "explicit_permissions_present": True,
        },
        "code_signal_evidence": {
            "todo_fixme_security_notes": 0,
            "risk_pattern_hits": 0,
            "potential_secret_pattern_hits": 0,
        },
        "unavailable_data_notes": [],
    }


def _scanner(run_id: str = "fullrun_trust") -> dict:
    return {
        "status": "attached",
        "run_id": run_id,
        "scan_id": f"scan_{run_id}",
        "tools_requested": ["pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint"],
        "tools_run": ["pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint"],
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "unavailable_data_notes": [],
    }


def _assessment(run_id: str = "fullrun_trust") -> dict:
    return build_full_assessment_scorecard(_context(run_id), _repository(run_id), _scanner(run_id))


def test_prepare_trust_attaches_real_ledger_and_preserves_weighted_score() -> None:
    original = _assessment()
    original_dependency = next(item for item in original["sections"] if item["id"] == "dependency_health")["score"]
    original_static = next(item for item in original["sections"] if item["id"] == "static_analysis")["score"]

    prepared = prepare_full_assessment_trust(original, _scanner())
    by_id = {item["id"]: item for item in prepared["sections"]}
    coverage = prepared["evidence_ledger"]["coverage_by_section"]

    assert prepared["status"] == "complete"
    assert prepared["report_finality"] == "final"
    assert prepared["review_status"] == "pending_human_approval"
    assert prepared["delivery_status"] == "blocked_pending_human_approval"
    assert prepared["draft_only"] is False
    assert prepared["report_path"] == "full_run"
    assert prepared["report_path_label"] == "Full Assessment"
    assert prepared["trust_engine"]["status"] == "applied"
    assert prepared["trust_report_display"]["version"] == "trust-report-display-v1"
    assert prepared["evidence_ledger"]["entry_count"] > 0
    assert coverage["dependency_health"]["complete"] is True
    assert coverage["static_analysis"]["verified_required_tools"] == ["bandit", "semgrep", "eslint"]
    assert coverage["static_analysis"]["missing_required_tools"] == ["typescript"]
    assert coverage["secrets_review"]["missing_required_tools"] == ["gitleaks", "trufflehog"]
    assert by_id["dependency_health"]["score"] == original_dependency
    assert by_id["static_analysis"]["score"] == original_static
    assert prepared["scorecard"]["technical_score"] == prepared["maturity_signal"]["score"]
    assert prepared["scorecard"]["post_trust_caps"] is True
    assert prepared["human_review_required"] is True
    assert prepared["client_ready"] is False
    assert "authorized Full Assessment" in prepared["executive_summary"]
    assert "authorized hosted Express Technical Health Assessment" not in prepared["executive_summary"]


def test_finalize_exports_applies_export_gate_and_preserves_report_artifacts() -> None:
    run_id = "fullrun_export_pass"
    prepared = prepare_full_assessment_trust(_assessment(run_id), _scanner(run_id))
    package = build_report_package(
        prepared,
        report_id="report_fullrun_export_pass",
        idempotency_key="fullrun-export-pass",
    )
    package["scan_id"] = f"scan_{run_id}"

    finalized = finalize_full_assessment_exports(prepared, package)
    assessment = finalized["assessment"]
    reports = finalized["reports"]
    stored = STORE.get("reports", "report_fullrun_export_pass")

    assert assessment["export_truth_gate"]["status"] in {"passed", "review_required"}
    assert assessment["export_truth_gate"]["client_delivery_allowed"] is False
    assert reports["client_delivery_allowed"] is False
    assert reports["human_review_required"] is True
    assert reports["markdown"]
    assert reports["html"]
    assert "Full Assessment" in reports["markdown"]
    assert "Trust Level:" in reports["markdown"]
    assert "authorized hosted Express Technical Health Assessment" not in reports["markdown"]
    assert stored is not None
    assert stored["export_truth_gate"]["status"] == assessment["export_truth_gate"]["status"]
    assert stored["formats"]["markdown"] == reports["markdown"]
    assert assessment["status"] == "complete"
    assert assessment["report_finality"] == "final"
    assert assessment["review_status"] == "pending_human_approval"
    assert assessment["delivery_status"] == "blocked_pending_human_approval"
    assert assessment["draft_only"] is False
    assert reports["report_finality"] == "final"
    assert reports["review_status"] == "pending_human_approval"
    assert reports["delivery_status"] == "blocked_pending_human_approval"
    assert reports["draft_only"] is False
    assert assessment["client_ready"] is False


def test_export_contradiction_becomes_review_required_without_destroying_artifacts() -> None:
    run_id = "fullrun_export_review"
    prepared = prepare_full_assessment_trust(_assessment(run_id), _scanner(run_id))
    contradictory = deepcopy(prepared)
    dependency = next(item for item in contradictory["sections"] if item["id"] == "dependency_health")
    dependency["status"] = "green"
    dependency["unavailable"].append("pip-audit is unavailable and missing for this report run.")
    package = {
        "status": "complete",
        "report_id": "report_fullrun_export_review",
        "customer_id": "cust-trust",
        "project_id": "proj-trust",
        "run_id": run_id,
        "idempotency_key": "fullrun-export-review",
        "idempotent_reuse": False,
        "formats": {
            "markdown": "# Full Assessment draft\n\nDependency / Library Ecosystem — GREEN\n",
            "html": "<html><body>Full Assessment draft</body></html>",
            "json": contradictory,
            "pdf": None,
        },
    }

    finalized = finalize_full_assessment_exports(contradictory, package)
    gate = finalized["assessment"]["export_truth_gate"]

    assert gate["status"] == "review_required"
    assert gate["draft_only"] is True
    assert gate["export_allowed"] is True
    assert gate["client_delivery_allowed"] is False
    assert finalized["reports"]["markdown"]
    assert finalized["reports"]["html"]
    assert finalized["reports"]["report_finality"] == "final"
    assert finalized["reports"]["review_status"] == "pending_human_approval"
    assert finalized["reports"]["delivery_status"] == "blocked_pending_human_approval"
    assert finalized["reports"]["draft_only"] is False


def test_api_truth_summary_surfaces_nested_gate_state_without_changing_delivery_rule() -> None:
    run_id = "fullrun_truth_summary"
    prepared = prepare_full_assessment_trust(_assessment(run_id), _scanner(run_id))
    prepared["export_truth_gate"] = {
        "status": "review_required",
        "client_delivery_allowed": False,
        "draft_only": True,
    }
    result = {
        "status": "complete",
        "run_id": run_id,
        "assessment": prepared,
        "reports": {"markdown": "# report"},
        "human_review_required": False,
        "client_ready": True,
    }

    updated = _attach_assessment_truth_summary(result)

    assert updated["trust_level"] == prepared["trust_level"]
    assert updated["evidence_ledger"]["report_run_id"] == run_id
    assert updated["export_truth_gate"]["status"] == "review_required"
    assert updated["delivery_verdict"] == "human_review_required"
    assert updated["human_review_required"] is True
    assert updated["client_ready"] is False
    assert updated["reports"]["client_delivery_allowed"] is False
