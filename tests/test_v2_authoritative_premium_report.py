from __future__ import annotations

import base64

from nico.v2_authoritative_premium_report import (
    project_authoritative_canonical,
    rebuild_authoritative_premium_artifacts,
)

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
                "technical_score": 72,
                "presented_score": 72,
                "score": 72,
                "evidence_adjusted_score": 71,
            },
            "sections": [
                {
                    "id": "security",
                    "label": "Security & Static Analysis",
                    "score": 74,
                    "presented_score": 74,
                    "status": "review_required",
                    "summary": "Bandit failed and Gitleaks missing in the legacy section cache.",
                    "findings": ["ESLint missing despite retained scanner evidence."],
                    "evidence": ["Canonical evidence is available."],
                    "unavailable": [],
                }
            ],
            "unavailable_data_notes": [],
        },
        "canonical_findings": [
            {
                "finding_id": "RISK-P2-TEST-EVAL",
                "priority": "P2",
                "category": "security",
                "finding_family": "python-eval-exec",
                "title": "Dynamic execution pattern",
                "location": "tests/test_express_safe_trace_diagnostics.py:44",
                "status": "open",
                "recommendation": "Confirm the test fixture is intentional.",
            },
            {
                "finding_id": "RISK-P1-OSV-001",
                "priority": "P1",
                "category": "dependencies",
                "finding_family": "osv-advisory",
                "title": "Dependency advisory requires disposition",
                "location": "package-lock.json",
                "status": "open",
                "material": True,
                "package": "example-package",
                "installed_version": "1.0.0",
                "advisory_id": "GHSA-example",
            },
        ],
        "scanner_execution_records": [
            {
                "scanner_name": "bandit",
                "commit_sha": SHA,
                "state": "completed",
                "status": "completed",
                "completed": True,
                "verified": True,
                "exact_commit_match": True,
                "artifact_hash": "b" * 64,
                "findings": [],
            },
            {
                "scanner_name": "eslint",
                "commit_sha": SHA,
                "state": "completed_with_findings",
                "status": "completed_with_findings",
                "completed": True,
                "verified": True,
                "exact_commit_match": True,
                "artifact_hash": "e" * 64,
                "findings": [{"rule_id": "no-unused-vars"}, {"rule_id": "no-explicit-any"}],
            },
            {
                "scanner_name": "gitleaks",
                "commit_sha": SHA,
                "state": "completed",
                "status": "completed",
                "completed": True,
                "verified": True,
                "exact_commit_match": True,
                "artifact_hash": "g" * 64,
                "findings": [],
            },
            {
                "scanner_name": "osv-scanner",
                "commit_sha": SHA,
                "state": "completed_with_findings",
                "status": "completed_with_findings",
                "completed": True,
                "verified": True,
                "exact_commit_match": True,
                "artifact_hash": "o" * 64,
                "findings": [
                    {
                        "id": "GHSA-example",
                        "package": "example-package",
                        "version": "1.0.0",
                        "severity": "high",
                    }
                ],
            },
            {
                "scanner_name": "trufflehog",
                "commit_sha": SHA,
                "state": "failed",
                "status": "failed",
                "completed": False,
                "verified": False,
                "exact_commit_match": True,
                "artifact_hash": "",
                "failure_reason": "temporary workspace clone could not retrieve a lazy Git object",
                "findings": [],
            },
        ],
        "stage_summaries": [
            {
                "stage_id": "dependency_security_static_analysis",
                "title": "Dependency, Security, and Static Analysis",
                "status": "review_required",
                "summary": "Bandit failed in stale pre-v2 data.",
                "evidence": [],
                "findings": [],
                "unavailable": [],
            }
        ],
        "roadmap": [
            {
                "window": "0-30 days",
                "objective": "Triage verified production risks first.",
                "work_packages": [],
            }
        ],
    }


def test_authoritative_projection_synchronizes_truth_and_dispositions():
    result = project_authoritative_canonical(_canonical())
    assessment = result["assessment"]
    maturity = assessment["maturity_signal"]
    assert assessment["technical_score"] == 74
    assert maturity["technical_score"] == 74
    assert maturity["presented_score"] == 74
    assert maturity["score"] == 74
    assert assessment["canonical_evidence_adjusted_score"] == 73
    assert maturity["evidence_adjusted_score"] == 73
    assert "Bandit failed" not in str(assessment)
    assert "Gitleaks missing" not in str(assessment)
    assert "ESLint missing" not in str(assessment)

    test_finding = next(item for item in result["canonical_findings"] if item["finding_id"] == "RISK-P2-TEST-EVAL")
    assert test_finding["production_scope"] is False
    assert test_finding["technical_score_impact"] == "none"

    dependency = next(item for item in result["canonical_findings"] if item["finding_id"] == "RISK-P1-OSV-001")
    assert dependency["material"] is False
    assert dependency["disposition"] == "triage_required"
    assert dependency["technical_score_impact"] == "assurance_only"
    summary = assessment["dependency_disposition_summary"]
    assert summary["verified_material"] == 0
    assert summary["triage_required"] == 1


def test_authoritative_renderer_restores_old_layout_over_new_truth():
    result = rebuild_authoritative_premium_artifacts({"json": _canonical()})
    contract = result["premium_report_renderer"]
    assert contract["old_premium_layout_restored"] is True
    assert contract["new_canonical_system_is_sole_truth"] is True
    assert contract["plain_canonical_score_page_removed"] is True
    assert contract["dark_branded_cover_restored"] is True
    assert result["pdf_page_count"] >= 5
    assert base64.b64decode(result["pdf_base64"]).startswith(b"%PDF")
    assert "Canonical Score Summary" not in result["markdown"]
    assert "PENDING HUMAN APPROVAL" in result["markdown"].upper()
    assert "APPROVED FINAL" not in result["markdown"].upper()
    assert result["approval_status"] == "pending_human_approval"
    assert result["delivery_status"] == "blocked_pending_human_approval"
    assert result["client_delivery_allowed"] is False
    assert "Bandit failed" not in result["markdown"]
    assert "Gitleaks missing" not in result["markdown"]
    assert "ESLint missing" not in result["markdown"]
    assert "bandit: completed" in result["markdown"].casefold()
    assert "trufflehog" in result["markdown"].casefold()
    assert "CLIENT DELIVERY NOT AUTHORIZED" in result["markdown"]


def test_spanish_authoritative_renderer_preserves_pending_approval_boundary():
    result = rebuild_authoritative_premium_artifacts({"json": _canonical("es-MX")})
    assert base64.b64decode(result["pdf_base64"]).startswith(b"%PDF")
    assert "APROBACIÓN" in result["markdown"].upper()
    assert "FINAL APROBADO" not in result["markdown"].upper()
    assert result["approval_status"] == "pending_human_approval"
    assert result["delivery_status"] == "blocked_pending_human_approval"
    assert result["client_delivery_allowed"] is False
    assert "CLIENT DELIVERY NOT AUTHORIZED" in result["markdown"]
