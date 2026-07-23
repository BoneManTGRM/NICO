from __future__ import annotations

import base64

from nico.full_assessment_pdf import (
    FULL_ASSESSMENT_PDF_STYLE_VERSION,
    build_full_assessment_pdf_base64,
    full_assessment_pdf_filename,
)
from nico.full_assessment_scorecard import build_full_assessment_scorecard
from nico.full_assessment_trust_pipeline import (
    finalize_full_assessment_exports,
    prepare_full_assessment_trust,
)
from nico.reports import build_report_package
from nico.storage import STORE


def _context(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "cust-pdf",
        "project_id": "proj-pdf",
        "client_name": "PDF Client",
        "project_name": "PDF Project",
    }


def _repository(run_id: str) -> dict:
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
            "deployment_manifests": ["Dockerfile"],
            "top_level_directories": ["nico", "apps", "tests"],
        },
        "dependency_evidence": {
            "manifest_paths": ["requirements.txt", "apps/web/package.json"],
            "lockfile_paths": ["apps/web/package-lock.json"],
            "dependency_entries": 60,
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


def _scanner(run_id: str) -> dict:
    tools = ["pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint"]
    return {
        "status": "attached",
        "run_id": run_id,
        "scan_id": f"scan_{run_id}",
        "tools_requested": tools,
        "tools_run": tools,
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "unavailable_data_notes": [],
    }


def _prepared(run_id: str) -> dict:
    assessment = build_full_assessment_scorecard(_context(run_id), _repository(run_id), _scanner(run_id))
    prepared = prepare_full_assessment_trust(assessment, _scanner(run_id))
    prepared["scorecard"]["ci_runtime_evidence"] = {
        "jobs_observed": 24,
        "runs_with_jobs": 8,
        "job_success_rate": 0.9583,
        "deployments_observed": 4,
        "baseline_score": 80,
        "final_score": 94,
    }
    prepared["scorecard"]["complexity_runtime_evidence"] = {
        "files_analyzed": 30,
        "functions_measured": 100,
        "average_cyclomatic_complexity": 3.2,
        "maximum_cyclomatic_complexity": 9,
        "duplicate_line_ratio": 0.01,
        "baseline_score": 82,
        "final_score": 94,
    }
    return prepared


def test_full_assessment_pdf_is_valid_review_artifact() -> None:
    prepared = _prepared("fullrun_pdf_direct")
    prepared["status"] = "complete"
    prepared["export_truth_gate"] = {
        "status": "review_required",
        "client_delivery_allowed": False,
        "draft_only": True,
    }

    encoded, error = build_full_assessment_pdf_base64(prepared, report_id="report_pdf_direct")

    assert error is None
    assert encoded
    decoded = base64.b64decode(encoded)
    assert decoded.startswith(b"%PDF")
    assert len(decoded) > 5_000
    assert full_assessment_pdf_filename(prepared) == "nico-full-assessment-BoneManTGRM-NICO.pdf"


def test_finalize_full_assessment_exports_persists_pdf_and_updates_truth_snapshot() -> None:
    run_id = "fullrun_pdf_persist"
    prepared = _prepared(run_id)
    package = build_report_package(
        prepared,
        report_id="report_fullrun_pdf_persist",
        idempotency_key="fullrun-pdf-persist",
    )
    package["scan_id"] = f"scan_{run_id}"

    finalized = finalize_full_assessment_exports(prepared, package)
    assessment = finalized["assessment"]
    reports = finalized["reports"]
    guarded_package = finalized["package"]
    stored = STORE.get("reports", "report_fullrun_pdf_persist")

    assert reports["pdf_base64"]
    assert base64.b64decode(reports["pdf_base64"]).startswith(b"%PDF")
    assert reports["pdf_filename"] == "nico-full-assessment-BoneManTGRM-NICO.pdf"
    assert reports["pdf_style"] == FULL_ASSESSMENT_PDF_STYLE_VERSION
    assert reports["pdf_error"] == ""
    assert reports["human_review_required"] is True
    assert reports["client_delivery_allowed"] is False
    assert guarded_package["formats"]["pdf"] == reports["pdf_base64"]
    assert guarded_package["pdf_filename"] == reports["pdf_filename"]
    assert assessment["export_truth_gate"]["artifact_snapshot"]["pdf"] is True
    assert assessment["status"] == "complete"
    assert assessment["report_finality"] == "final"
    assert assessment["review_status"] == "pending_human_approval"
    assert assessment["delivery_status"] == "blocked_pending_human_approval"
    assert assessment["draft_only"] is False
    assert assessment["client_ready"] is False
    assert stored is not None
    assert stored["formats"]["pdf"] == reports["pdf_base64"]
    assert stored["pdf_style"] == FULL_ASSESSMENT_PDF_STYLE_VERSION


def test_pdf_failure_preserves_markdown_html_and_review_block(monkeypatch) -> None:
    run_id = "fullrun_pdf_failure"
    prepared = _prepared(run_id)
    package = build_report_package(
        prepared,
        report_id="report_fullrun_pdf_failure",
        idempotency_key="fullrun-pdf-failure",
    )
    monkeypatch.setattr(
        "nico.full_assessment_trust_pipeline.build_full_assessment_pdf_base64",
        lambda _candidate, report_id="": (None, "Full Assessment PDF export failed integrity validation."),
    )

    finalized = finalize_full_assessment_exports(prepared, package)

    assert finalized["reports"]["markdown"]
    assert finalized["reports"]["html"]
    assert finalized["reports"]["pdf_base64"] == ""
    assert finalized["reports"]["pdf_error"] == "Full Assessment PDF export failed integrity validation."
    assert finalized["reports"]["client_delivery_allowed"] is False
    assert finalized["reports"]["human_review_required"] is True
    assert finalized["assessment"]["client_ready"] is False
