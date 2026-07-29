from __future__ import annotations

import base64
import io
from pathlib import Path

from pypdf import PdfReader

from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from nico.v2_authoritative_report_truth import repair_canonical_truth_in_place

SHA = "a" * 40


def _canonical(language: str = "en") -> dict:
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": SHA,
            "run_id": "comprun_authoritative",
            "evidence_ledger_id": "ledger-authoritative",
            "customer_id": "customer-authoritative",
            "project_id": "project-authoritative",
            "report_language": language,
        },
        "report_language": language,
        "assessment": {
            "report_language": language,
            "technical_score": 74,
            "canonical_evidence_adjusted_score": 73,
            "maturity_signal": {
                "level": "Moderate",
                "score": 72,
                "presented_score": 72,
            },
            "executive_summary": "Canonical evidence is complete enough for internal review.",
            "sections": [
                {
                    "id": "dependencies",
                    "label": "Dependencies",
                    "status": "review_required",
                    "score": 31,
                    "summary": "Gitleaks missing and Bandit failed.",
                    "evidence": ["ESLint missing"],
                }
            ],
            "unavailable_data_notes": [],
        },
        "canonical_findings": [
            {
                "finding_id": "RISK-P2-TEST",
                "priority": "P2",
                "category": "security",
                "title": "Review dynamic execution pattern",
                "location": "tests/test_express_safe_trace_diagnostics.py:42",
                "recommendation": "Confirm the test remains intentionally isolated.",
                "status": "open",
            }
        ],
        "scanner_execution_records": [
            {
                "scanner_name": "bandit",
                "state": "completed",
                "status": "completed",
                "completed": True,
                "verified": True,
                "commit_sha": SHA,
                "artifact_hash": "b" * 64,
                "findings": [],
            },
            {
                "scanner_name": "eslint",
                "state": "completed_with_findings",
                "status": "completed_with_findings",
                "completed": True,
                "verified": True,
                "commit_sha": SHA,
                "artifact_hash": "c" * 64,
                "findings": [{"rule_id": "no-unused-vars"}, {"rule_id": "no-explicit-any"}],
            },
            {
                "scanner_name": "gitleaks",
                "state": "completed",
                "status": "completed",
                "completed": True,
                "verified": True,
                "commit_sha": SHA,
                "artifact_hash": "d" * 64,
                "findings": [],
            },
            {
                "scanner_name": "osv-scanner",
                "state": "completed_with_findings",
                "status": "completed_with_findings",
                "completed": True,
                "verified": True,
                "commit_sha": SHA,
                "artifact_hash": "e" * 64,
                "findings": [
                    {
                        "id": "GHSA-UNTRIAGED",
                        "package": "example-package",
                        "version": "1.0.0",
                        "severity": "high",
                    }
                ],
            },
            {
                "scanner_name": "trufflehog",
                "state": "failed",
                "status": "failed",
                "completed": False,
                "verified": False,
                "commit_sha": SHA,
                "artifact_hash": "",
                "findings": [],
                "failure_reason": "partial Git object store could not satisfy internal clone",
            },
        ],
        "stage_summaries": [
            {
                "stage_id": "evidence_reconciliation_and_scoring",
                "title": "Evidence Reconciliation and Scoring",
                "status": "blocked",
                "summary": "Scoring stage technical score: 72.",
                "score": 72,
                "evidence": [],
                "findings": [],
                "unavailable": [],
            },
            {
                "stage_id": "dependency_security_static_analysis",
                "title": "Dependency, Security, and Static Analysis",
                "status": "failed",
                "summary": "Gitleaks missing and Bandit failed.",
                "evidence": ["ESLint missing"],
                "findings": [],
                "unavailable": ["Gitleaks missing"],
            },
        ],
        "report_contract": {
            "status": "blocked",
            "blocked": True,
            "reason": "canonical_score_truth_mismatch",
        },
        "roadmap": [],
    }


def _pdf_text(encoded: str) -> str:
    pdf = base64.b64decode(encoded)
    assert pdf.startswith(b"%PDF")
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)


def test_authoritative_truth_repairs_scores_scanners_dependencies_and_test_scope():
    canonical = _canonical()
    repair_canonical_truth_in_place(canonical)

    maturity = canonical["assessment"]["maturity_signal"]
    assert maturity["score"] == 74
    assert maturity["presented_score"] == 74
    assert maturity["technical_score"] == 74
    assert maturity["canonical_evidence_adjusted_score"] == 73
    assert canonical["report_contract"]["status"] == "passed"
    assert canonical["report_contract"]["blocked"] is False

    rendered_truth = str(canonical)
    assert "Gitleaks missing" not in rendered_truth
    assert "Bandit failed" not in rendered_truth
    assert "ESLint missing" not in rendered_truth
    assert canonical["assessment"]["evidence_health_summary"]["completed_scanner_count"] == 4
    assert canonical["assessment"]["evidence_health_summary"]["incomplete_scanner_count"] == 1

    finding = canonical["canonical_findings"][0]
    assert finding["production_scope"] == "non_production"
    assert finding["technical_score_impact"] is False

    disposition = canonical["dependency_disposition"][0]
    assert disposition["disposition"] == "untriaged_assurance_gap"
    assert disposition["technical_score_impact"] is False
    summary = canonical["assessment"]["dependency_disposition_summary"]
    assert summary["verified_material_count"] == 0
    assert summary["untriaged_assurance_gap_count"] == 1


def test_premium_renderer_uses_old_visual_shell_with_new_authoritative_engine():
    canonical = _canonical()
    repair_canonical_truth_in_place(canonical)
    result = rebuild_client_artifacts({"json": canonical})
    contract = result["premium_report_renderer"]

    assert contract["old_system_visual_shell"] is True
    assert contract["new_canonical_system_engine"] is True
    assert contract["dark_branded_cover"] is True
    assert contract["executive_dashboard"] is True
    assert contract["canonical_score_summary"] is False
    assert contract["canonical_scanner_truth_only"] is True
    assert contract["dependency_disposition"] is True

    markdown = result["markdown"]
    assert "Canonical Score Summary" not in markdown
    assert "Gitleaks missing" not in markdown
    assert "Bandit failed" not in markdown
    assert "ESLint missing" not in markdown
    assert "74/100" in markdown
    assert "73/100" in markdown
    assert "untriaged_assurance_gap" in markdown
    assert "CLIENT DELIVERY NOT AUTHORIZED" in markdown
    assert "DRAFT" not in markdown.upper()

    pdf_text = _pdf_text(result["pdf_base64"])
    upper_pdf = pdf_text.upper()
    assert "TECHNICAL MATURITY" in upper_pdf
    assert "EVIDENCE-ADJUSTED" in upper_pdf
    assert "74/100" in pdf_text
    assert "73/100" in pdf_text
    assert "DRAFT" not in upper_pdf
    assert result["pdf_page_count"] >= 5


def test_spanish_renderer_preserves_layout_and_finality_without_draft_language():
    canonical = _canonical("es-MX")
    repair_canonical_truth_in_place(canonical)
    result = rebuild_client_artifacts({"json": canonical})

    assert result["premium_report_renderer"]["bilingual_premium_output"] is True
    assert "Evaluación Técnica Integral NICO" in result["markdown"]
    assert "Clasificación de dependencias" in result["markdown"]
    assert "BORRADOR" not in result["markdown"].upper()
    assert "CLIENT DELIVERY NOT AUTHORIZED" in result["markdown"]
    assert "BORRADOR" not in _pdf_text(result["pdf_base64"]).upper()


def test_live_acceptance_reader_retains_collapsed_identity_fallbacks():
    source = Path("scripts/two_service_live_acceptance_v3.py").read_text(encoding="utf-8")
    assert "two_service_live_acceptance_v3_legacy" in source
    assert "url.searchParams.get('run_id')" in source
    assert "url.searchParams.get('expected_commit_sha')" in source
    assert "section.querySelectorAll('code')" in source
    assert "Internal review" in source
    assert "scannerFromDetails" in source
