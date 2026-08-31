from __future__ import annotations

import io

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.comprehensive_client_truth_final_v1 import (
    normalize_client_truth,
    replace_cover_text,
)


def _summary(
    *,
    raw: int,
    approved: int = 0,
    excluded: int = 0,
    material: int = 0,
    review: int,
    exact_source: int = 0,
    source_path: int = 0,
    payload_without_source: int = 0,
    count_only: int = 0,
) -> dict:
    return {
        "raw": raw,
        "approved_or_nonblocking": approved,
        "excluded_test_only": excluded,
        "material": material,
        "review_required": review,
        "exact_source": exact_source,
        "source_path": source_path,
        "payload_without_source": payload_without_source,
        "count_only": count_only,
    }


def _canonical() -> dict:
    dependency = _summary(raw=59, review=59, source_path=59)
    secret = _summary(raw=17, review=17, payload_without_source=17)
    static = _summary(raw=583, review=583, exact_source=583)
    total = _summary(
        raw=659,
        review=659,
        exact_source=583,
        source_path=59,
        payload_without_source=17,
    )
    ci_contract = {
        "exact_configuration_match": True,
        "score_inputs": {
            "explicit_permissions_present": True,
            "configuration_controls": {
                "build": True,
                "test": True,
                "security": True,
            },
        },
    }
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "comprun_truth_v1",
            "customer_id": "customer_truth",
            "project_id": "project_truth",
            "evidence_ledger_id": "ledger_truth",
        },
        "client_readiness_contract": {"maturity_label": "Exceptional"},
        "completed_applicable_analyzers": 9,
        "incomplete_applicable_analyzers": 0,
        "maturity_label_truth": {"canonical_label": "Senior"},
        "assessment": {
            "technical_score": 93,
            "evidence_adjusted_score": 89,
            "maturity_signal": {"level": "Senior", "score": 93},
            "canonical_scanner_finding_register": {
                "totals": total,
                "summary_by_category": {
                    "dependency": dependency,
                    "secret": secret,
                    "static": static,
                },
                "findings": [],
            },
            "sections": [
                {
                    "id": "dependency_health",
                    "evidence": ["Raw candidates: 59.", "Approved/nonblocking: 0."],
                },
                {
                    "id": "secrets_review",
                    "evidence": [
                        "Raw candidates: 17.",
                        "Approved/nonblocking: 1.",
                        "Review-required candidates: 17.",
                    ],
                },
                {
                    "id": "static_analysis",
                    "evidence": ["Raw candidates: 583."],
                },
                {
                    "id": "ci_cd",
                    "score": 100,
                    "presented_score": 100,
                    "score_contract": ci_contract,
                    "operational_health": {
                        "workflow_run_count": 100,
                        "outcome_taxonomy": {
                            "success": 86,
                            "failure": 5,
                            "cancelled": 0,
                            "skipped": 0,
                            "timed_out": 0,
                            "unknown": 9,
                        },
                    },
                },
            ],
        },
        "stage_summaries": [
            {
                "stage_id": "dependency_security_static_analysis",
                "title": "Dependency, Security, and Static Analysis",
                "status": "complete",
                "summary": "9 scanner records completed and 0 remain incomplete or review-limited.",
                "evidence": ["report_language: en", "stage_execution.elapsed_seconds: 1"],
            },
            {
                "stage_id": "evidence_reconciliation_and_scoring",
                "title": "Evidence Reconciliation and Scoring",
                "status": "complete",
                "evidence": [
                    "candidate_disposition.count_only:",
                    "candidate_disposition.confirmed_material:",
                    "candidate_disposition.review_required: 659",
                ],
            },
            {
                "stage_id": "ci_cd_architecture_complexity_velocity",
                "title": "CI/CD, Architecture, Complexity, and Velocity",
                "status": "complete",
                "evidence": ["source_loc:", "files_analyzed: 887"],
            },
        ],
    }


def test_current_production_secret_contradiction_is_rebuilt_from_register() -> None:
    result = normalize_client_truth(_canonical())
    sections = {item["id"]: item for item in result["assessment"]["sections"]}

    assert sections["secrets_review"]["evidence"] == [
        "Applicable analyzers: gitleaks, trufflehog.",
        "Raw candidates: 17.",
        "Approved/nonblocking: 0.",
        "Excluded non-production/test-only: 0.",
        "Confirmed material findings: 0.",
        "Review-required candidates: 17.",
        "Score effect: assurance-only until triaged.",
    ]
    assert result["assessment"]["candidate_disposition"] == {
        "total_raw": 659,
        "approved_nonblocking": 0,
        "excluded_nonproduction": 0,
        "confirmed_material": 0,
        "review_required": 659,
        "exact_source": 583,
        "source_path": 59,
        "payload_without_source": 17,
        "count_only": 0,
        "model_version": "mutually-exclusive-candidate-dispositions.v1",
        "mutually_exclusive": True,
        "disposition_arithmetic_verified": True,
        "evidence_quality_arithmetic_verified": True,
    }


def test_candidate_arithmetic_mismatch_blocks_before_render() -> None:
    canonical = _canonical()
    canonical["assessment"]["canonical_scanner_finding_register"][
        "summary_by_category"
    ]["secret"]["approved_or_nonblocking"] = 1

    with pytest.raises(ValueError, match="disposition totals do not reconcile for secret"):
        normalize_client_truth(canonical)


def test_zero_candidate_category_is_materialized_without_blocking_publication() -> None:
    canonical = _canonical()
    register = canonical["assessment"]["canonical_scanner_finding_register"]
    register["summary_by_category"].pop("secret")
    register["totals"] = _summary(
        raw=642,
        review=642,
        exact_source=583,
        source_path=59,
    )

    result = normalize_client_truth(canonical)

    secret = result["assessment"]["canonical_scanner_finding_register"][
        "summary_by_category"
    ]["secret"]
    assert secret == _summary(raw=0, review=0)
    section = next(
        item for item in result["assessment"]["sections"]
        if item["id"] == "secrets_review"
    )
    assert "Raw candidates: 0." in section["evidence"]


def test_missing_summary_with_retained_category_findings_still_blocks() -> None:
    canonical = _canonical()
    register = canonical["assessment"]["canonical_scanner_finding_register"]
    register["summary_by_category"].pop("secret")
    register["findings"] = [{"candidate_id": "SECRET-1", "category": "secret"}]

    with pytest.raises(ValueError, match="missing canonical scanner category summary: secret"):
        normalize_client_truth(canonical)


def test_executive_maturity_limit_count_and_stage_boundaries_reconcile() -> None:
    result = normalize_client_truth(_canonical())
    assessment = result["assessment"]
    stages = {item["stage_id"]: item for item in result["stage_summaries"]}

    assert assessment["maturity_signal"]["level"] == "Exceptional"
    assert assessment["limited_review_section_count"] == 7
    assert "Exceptional (93/100)" in assessment["executive_summary"]
    assert "7 client-review section(s)" in assessment["executive_summary"]
    assert stages["dependency_security_static_analysis"]["summary"] == (
        "9 of 9 applicable analyzers completed; 0 are incomplete. Candidate triage is "
        "separate: 659 review-required candidates and 0 confirmed material findings are retained."
    )
    assert stages["evidence_reconciliation_and_scoring"]["evidence"] == [
        "candidate_disposition.review_required: 659"
    ]
    ci_evidence = stages["ci_cd_architecture_complexity_velocity"]["evidence"]
    assert len(ci_evidence) == 4
    assert ci_evidence[0].startswith("A. CI/CD configuration maturity: 100/100")
    assert ci_evidence[1].startswith("B. Current operational readiness:")
    assert ci_evidence[2].startswith("C. Required-check health:")
    assert ci_evidence[3].startswith("D. Historical workflow outcomes")


def test_cover_claim_is_bounded_to_evidence_review() -> None:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, invariant=1)
    pdf.drawString(40, 760, "Decision-Grade Technical Assessment")
    pdf.drawString(40, 740, "READ-ONLY · IMMUTABLE SNAPSHOT · INTERNAL REVIEW REQUIRED")
    pdf.showPage()
    pdf.save()

    repaired = replace_cover_text(buffer.getvalue())
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(repaired)).pages)
    assert "Decision-Grade Technical Assessment" not in text
    assert "Evidence-Bound Technical Review Package" in text
    assert "HUMAN REVIEW REQUIRED" in text
