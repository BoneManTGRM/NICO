from __future__ import annotations

import base64
import hashlib
import json

from nico import comprehensive_final_artifact_truth_v53 as artifact_truth


COMMIT = "a" * 40


def _finding() -> dict:
    return {
        "finding_id": "NICO-FINDING-ONE",
        "title": "Reduce complexity in _spanish_pdf",
        "exact_source": "nico/spanish.py:50-223:50",
        "function": "_spanish_pdf",
        "rule_id": "complexity_hotspot",
    }


def _operational() -> dict:
    return {
        "finding_id": "NICO-FINDING-TWO",
        "title": "GHSA-example",
        "priority": "P2",
        "recommendation": "Triage the dependency candidate.",
    }


def _scanner_record() -> dict:
    return {
        "finding_id": "NICO-SCAN-0000000000000001",
        "raw_fingerprint": "1" * 64,
        "scanner": "semgrep",
        "category": "static",
        "rule_id": "typescript.review",
        "severity": "low",
        "confidence": "unknown",
        "source_path": "src/module.ts",
        "line": 10,
        "column": 1,
        "evidence": "Review candidate",
        "disposition": "review_required",
        "evidence_quality": "exact_source",
        "occurrence_count": 1,
        "source_record_count": 1,
        "exact_commit_sha": COMMIT,
        "human_review_required": True,
    }


def _scanner_register() -> dict:
    findings = [_scanner_record()]
    digest = hashlib.sha256(
        json.dumps(findings, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    summary = {
        "static": {
            "raw": 1,
            "material": 0,
            "review_required": 1,
            "approved_or_nonblocking": 0,
            "excluded_test_only": 0,
            "exact_source": 1,
            "source_path": 0,
            "payload_without_source": 0,
            "count_only": 0,
        }
    }
    return {
        "artifact_schema": "nico.canonical-scanner-findings.v1",
        "status": "complete",
        "exact_commit_sha": COMMIT,
        "findings": findings,
        "summary_by_category": summary,
        "totals": dict(summary["static"]),
        "count_parity_verified": True,
        "discrepancies": [],
        "canonical_digest_sha256": digest,
        "raw_payload_retention_complete": True,
    }


def _package(*, include_v5_truth: bool = False) -> dict:
    rows = [
        {"technical_score": 96, "weight": 0.20, "assurance_factor": 1.00, "included": True},
        {"technical_score": 96, "weight": 0.15, "assurance_factor": 0.98, "included": True},
        {"technical_score": 96, "weight": 0.15, "assurance_factor": 0.98, "included": True},
        {"technical_score": 85, "weight": 0.15, "assurance_factor": 1.00, "included": True},
        {"technical_score": 100, "weight": 0.15, "assurance_factor": 1.00, "included": True},
        {"technical_score": 78, "weight": 0.15, "assurance_factor": 1.00, "included": True},
        {"technical_score": 87, "weight": 0.05, "assurance_factor": 1.00, "included": True},
    ]
    assessment = {
        "technical_score": 92,
        "evidence_adjusted_score": 91,
        "canonical_evidence_adjusted_score": 91,
        "maturity_signal": {
            "score": 92,
            "source_score": 92,
            "technical_score": 92,
            "evidence_adjusted_score": 91,
            "canonical_evidence_adjusted_score": 91,
        },
        "scoring_weights": rows,
        "decision_grade_findings_register": [_finding(), _operational()],
        "scanner_execution_records": [
            {
                "scanner_name": "bandit",
                "status": "completed",
                "exact_commit_match": True,
                "artifact_hash": "abc",
            }
        ],
        "incomplete_analyzers": [],
        "analyzer_execution_coverage": 100,
    }
    canonical = {
        "assessment": assessment,
        "findings_register": [_finding(), _operational()],
        "unique_finding_count": 2,
        "stage_summaries": [
            {
                "stage_id": "evidence_reconciliation_and_scoring",
                "evidence": [
                    "technical_score: 92",
                    "canonical_technical_score: 92",
                    "evidence_adjusted_score: 91",
                    "canonical_evidence_adjusted_score: 91",
                    "analyzer_execution_coverage: 100",
                ],
            }
        ],
    }
    package = {
        "json": canonical,
        "markdown": "Technical maturity 92/100. Evidence-Adjusted 91/100. _spanish_pdf",
        "html": "<html>Technical maturity 92/100. Evidence-Adjusted 91/100. _spanish_pdf</html>",
        "pdf_base64": base64.b64encode(b"not-a-real-pdf").decode("ascii"),
    }
    if include_v5_truth:
        register = _scanner_register()
        operational = {
            "status": "strong",
            "score": 96,
            "successful_runs": 24,
            "non_success_runs": 1,
            "observed_run_count": 25,
            "score_effect": "operational_context_only",
            "technical_configuration_score_affected": False,
        }
        assessment.update(
            {
                "commit_sha": COMMIT,
                "human_review_required": True,
                "client_delivery_allowed": False,
                "canonical_scanner_finding_register": register,
                "scanner_finding_summary": register["summary_by_category"],
                "evidence_coverage": {
                    "canonical_finding_register_status": "complete",
                    "canonical_finding_count": 1,
                    "canonical_finding_digest_sha256": register["canonical_digest_sha256"],
                    "candidate_volume_affects_technical_score": False,
                    "candidate_volume_affects_evidence_adjusted_score": True,
                },
                "score_contract": {
                    "technical_score": 92,
                    "evidence_adjusted_score": 91,
                    "candidate_volume_affects_technical_score": False,
                    "candidate_volume_affects_evidence_adjusted_score": True,
                    "candidate_volume_penalty": 1,
                    "missing_raw_payload_penalty": 0,
                    "incomplete_analyzer_penalty": 0,
                    "assurance_penalty": 1,
                    "canonical_finding_register_required": True,
                    "canonical_finding_count_parity_required": True,
                    "canonical_finding_count_parity_verified": True,
                },
                "ci_cd_operational_health": operational,
                "sections": [
                    {
                        "id": "ci_cd",
                        "presented_score": 100,
                        "configuration_maturity_score": 100,
                        "operational_health": operational,
                    }
                ],
            }
        )
        canonical.update(
            {
                "identity": {"commit_sha": COMMIT},
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        )
        package.update(
            {
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        )
    return package


def test_final_artifact_validation_accepts_one_recomputable_truth(monkeypatch) -> None:
    monkeypatch.setattr(
        artifact_truth,
        "_pdf_text",
        lambda _pdf: "Technical maturity 92/100 Evidence-Adjusted 91/100 _spanish_pdf",
    )

    result = artifact_truth.validate_final_report_package(_package())

    assert result["status"] == "verified"
    assert result["failed_checks"] == []
    assert result["calculated_unique_finding_count"] == 2


def test_final_artifact_validation_accepts_complete_v5_truth(monkeypatch) -> None:
    monkeypatch.setattr(
        artifact_truth,
        "_pdf_text",
        lambda _pdf: "Technical maturity 92/100 Evidence-Adjusted 91/100 _spanish_pdf",
    )

    result = artifact_truth.validate_final_report_package(_package(include_v5_truth=True))

    assert result["status"] == "verified"
    assert result["checks"]["canonical_scanner_totals_recompute"] is True
    assert result["checks"]["evidence_adjusted_penalty_recomputes"] is True
    assert result["checks"]["ci_configuration_and_operational_health_separated"] is True
    assert result["checks"]["automated_package_remains_human_review_gated"] is True


def test_final_artifact_validation_blocks_stale_scanner_duplicate_and_identifier(monkeypatch) -> None:
    package = _package()
    canonical = package["json"]
    canonical["assessment"]["incomplete_analyzers"] = ["bandit"]
    canonical["assessment"]["analyzer_execution_coverage"] = 89
    canonical["findings_register"].append(_finding())
    package["markdown"] += " span ish_pdf"
    monkeypatch.setattr(
        artifact_truth,
        "_pdf_text",
        lambda _pdf: "Technical maturity 92/100 Evidence-Adjusted 91/100 span ish_pdf",
    )

    result = artifact_truth.validate_final_report_package(package)

    assert result["status"] == "blocked"
    assert "completed_scanners_not_incomplete" in result["failed_checks"]
    assert "finding_register_has_no_equivalent_duplicates" in result["failed_checks"]
    assert "markdown_identifier_integrity" in result["failed_checks"]
    assert "pdf_identifier_integrity" in result["failed_checks"]


def test_v5_truth_blocks_count_score_ci_and_delivery_drift(monkeypatch) -> None:
    package = _package(include_v5_truth=True)
    assessment = package["json"]["assessment"]
    assessment["canonical_scanner_finding_register"]["totals"]["raw"] = 2
    assessment["ci_cd_operational_health"]["score_effect"] = "technical_score"
    assessment["sections"][0]["operational_health"] = assessment["ci_cd_operational_health"]
    assessment["evidence_adjusted_score"] = 92
    assessment["canonical_evidence_adjusted_score"] = 92
    assessment["maturity_signal"]["evidence_adjusted_score"] = 92
    assessment["maturity_signal"]["canonical_evidence_adjusted_score"] = 92
    assessment["score_contract"]["evidence_adjusted_score"] = 92
    package["client_delivery_allowed"] = True
    package["json"]["client_delivery_allowed"] = True
    assessment["client_delivery_allowed"] = True
    monkeypatch.setattr(
        artifact_truth,
        "_pdf_text",
        lambda _pdf: "Technical maturity 92/100 Evidence-Adjusted 92/100 _spanish_pdf",
    )

    result = artifact_truth.validate_final_report_package(package)

    assert result["status"] == "blocked"
    assert "canonical_scanner_totals_recompute" in result["failed_checks"]
    assert "evidence_adjusted_penalty_recomputes" in result["failed_checks"]
    assert "ci_configuration_and_operational_health_separated" in result["failed_checks"]
    assert "automated_package_remains_human_review_gated" in result["failed_checks"]
