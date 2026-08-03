from __future__ import annotations

import base64
from pathlib import Path

from nico.comprehensive_client_ready_projection_v1 import APPROVAL_SUFFIX
from nico.phase9_comprehensive_report_integration_v1 import finalize_report_package
from nico.v2_scanner_reconciliation import normalize_record


COMMIT = "a" * 40
ROOT = Path(__file__).resolve().parents[1]


def finding(identifier: str, enriched: bool = False) -> dict:
    item = {
        "finding_id": identifier,
        "category": "architecture",
        "title": "High-complexity code hotspot",
        "location": "apps/web/app/operations/page.tsx:177",
        "fact": "cyclomatic_complexity=52; loc=173; method=typescript_compiler_ast",
        "priority": "P1",
        "status": "open",
        "recommendation": "Decompose the hotspot.",
        "acceptance_criteria": ["Target complexity is at most 30."],
    }
    if enriched:
        item.update({
            "business_impact": "Concentrated branch logic increases regression risk.",
            "owner_role": "Product Engineering Architect",
            "effort": "M-L",
            "acceptance_criteria": [
                f"Target complexity is at most 30. [method: metric_comparison; target commit: {COMMIT}]",
                f"Target complexity is at most 30. [method: metric_comparison; target commit: {COMMIT}]",
            ],
        })
    return item


def raw_result() -> dict:
    legacy = finding("RISK-LEGACY")
    prioritized = finding("RISK-P1-CANONICAL", enriched=True)
    canonical = {
        "identity": {"repository": "BoneManTGRM/NICO", "commit_sha": COMMIT, "run_id": "comprun_v2"},
        "assessment": {"technical_score": 82, "canonical_evidence_adjusted_score": 81, "sections": []},
        "canonical_findings": [legacy, prioritized],
        "findings_register": [legacy, prioritized],
        "scanner_execution_records": [
            {"scanner_name": "bandit", "status": "failed", "exit_code": 1, "commit_sha": COMMIT, "findings": [{"id": "B101"}], "stdout": "{}"},
            {"scanner_name": "eslint", "status": "failed", "exit_code": 1, "commit_sha": COMMIT, "findings": [{"ruleId": "complexity"}], "stdout": "[]"},
            {"scanner_name": "gitleaks", "status": "partial", "commit_sha": COMMIT, "failure_reason": "binary unavailable"},
        ],
    }
    duplicated = "FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL"
    return {
        "status": "failed",
        "record": {"status": "failed"},
        "report_package": {
            "json": canonical,
            "pdf_filename": f"nico-report-{duplicated}.pdf",
            "spanish_pdf_filename": f"nico-report-es-{duplicated}.pdf",
            "json_filename": f"nico-report-{duplicated}.json",
            "markdown_filename": f"nico-report-{duplicated}.md",
            "csv_filename": f"nico-report-{duplicated}.csv",
            "pdf_base64": base64.b64encode(b"%PDF stale").decode("ascii"),
        },
    }


def test_production_scanner_runtime_remains_installed_and_durable():
    bootstrap = (ROOT / "nico/api/terminal_authority_bootstrap.py").read_text(encoding="utf-8")
    runtime = (ROOT / "nico/scanner_evidence_pipeline_v1.py").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "install_scanner_evidence_pipeline_v1" in bootstrap
    assert "SCANNER_EVIDENCE_PIPELINE" in bootstrap
    assert "full_output_capture" in bootstrap
    assert "durable_redacted_raw_artifacts" in bootstrap
    assert "frozen_sha_determinism_supported" in bootstrap

    assert "stdout_path" in runtime
    assert "MAX_PARSE_BYTES" in runtime
    assert "raw_artifact_sha256" in runtime
    assert "verified_for_this_report" in runtime
    assert "full_history_verified" in runtime

    assert "NICO_MAX_SCANNER_PARSE_BYTES=268435456" in dockerfile
    assert "NICO_SCANNER_RAW_ARTIFACT_ROOT=/data/scanner-artifacts" in dockerfile
    assert "NICO_ESLINT_PARSER_ENTRY" in dockerfile


def test_findings_exit_code_with_retained_exact_sha_artifact_is_completed():
    normalized = normalize_record({
        "scanner_name": "bandit", "status": "failed", "exit_code": 1,
        "commit_sha": COMMIT, "findings": [{"id": "B101"}], "stdout": "{}",
    }, COMMIT)
    assert normalized["status"] == "completed_with_findings"
    assert normalized["verified_complete"] is True
    assert normalized["artifact_hash"]


def test_finalizer_eliminates_production_contradictions_and_duplicates():
    output = finalize_report_package(raw_result())
    package = output["report_package"]
    canonical = package["json"]
    assert output["assessment_state"] == "review_required"
    assert output["status"] == "review_required"
    assert output["record"]["assessment_state"] == "review_required"
    assert output["record"]["assessment_package_complete"] is True
    assert output["human_review_required"] is True
    assert output["client_delivery_allowed"] is False
    assert len(canonical["canonical_findings"]) == 1
    assert len(canonical["canonical_findings"][0]["acceptance_criteria"]) == 1
    for key in ("pdf_filename", "spanish_pdf_filename", "json_filename", "markdown_filename", "csv_filename"):
        assert package[key].count(APPROVAL_SUFFIX) == 1
        assert "FINAL-PENDING-APPROVAL" not in package[key]
    assert package["report_finality"] == "automated_draft"
    assert package["approval_status"] == "pending_human_approval"
    assert package["delivery_status"] == "blocked_pending_human_approval"
    assert package["markdown"]
    assert base64.b64decode(package["pdf_base64"]).startswith(b"%PDF")
    hashes = {
        package["canonical_truth_sha256"], package["json_canonical_sha256"],
        package["markdown_canonical_sha256"], package["pdf_canonical_sha256"],
        package["csv_canonical_sha256"], package["ui_canonical_sha256"],
    }
    assert len(hashes) == 1


def test_real_scanner_failure_remains_failure():
    normalized = normalize_record({
        "scanner_name": "gitleaks", "status": "failed", "exit_code": 127,
        "commit_sha": COMMIT, "stderr": "binary not found",
    }, COMMIT)
    assert normalized["status"] == "failed"
    assert normalized["verified_complete"] is False
    assert "binary not found" in normalized["failure_reason"]
