from __future__ import annotations

import base64
import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

from nico.client_report_completion_v1 import finalize_client_report_package


SHA = "e" * 40


def _base_pdf() -> bytes:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    story = [
        Paragraph("NICO Comprehensive", styles["Title"]),
        Paragraph("Executive report body", styles["BodyText"]),
        PageBreak(),
        Paragraph("Executive Risk Register and Decision Briefing", styles["Heading1"]),
        Paragraph("No structured item was retained.", styles["BodyText"]),
        PageBreak(),
        Paragraph("Evidence Appendix", styles["Heading1"]),
        Paragraph("Bounded stage evidence", styles["BodyText"]),
        PageBreak(),
        Paragraph("Human Review and Acceptance Gate", styles["Heading1"]),
        Paragraph("CLIENT DELIVERY BLOCKED", styles["BodyText"]),
        PageBreak(),
        Paragraph("Evidence Appendix", styles["Heading1"]),
        Paragraph("Scanner provenance", styles["Heading2"]),
        Paragraph("eslint: unavailable", styles["BodyText"]),
    ]
    SimpleDocTemplate(buffer, pagesize=letter, invariant=1).build(story)
    return buffer.getvalue()


def _package() -> dict:
    canonical = {
        "identity": {
            "repository": "example/python-service",
            "commit_sha": SHA,
            "run_id": "comprun_completion",
            "evidence_ledger_id": "ledger_completion",
        },
        "repository_evidence": {
            "file_evidence": {"sampled_paths": ["requirements.txt", "src/service.py"]},
            "dependency_evidence": {"manifest_paths": ["requirements.txt"]},
        },
        "canonical_findings": [
            {
                "finding_id": "RISK-P1-TLS",
                "priority": "P1",
                "category": "security",
                "status": "review_required",
                "title": "TLS certificate verification disabled",
                "location": "src/http_client.py:27",
                "rule_id": "tls_verify_disabled",
                "fact": "risk_pattern=tls_verify_disabled",
                "interpretation": "Disabled certificate verification bypasses transport authenticity checks.",
                "business_impact": "A confirmed production path could expose requests to interception.",
                "recommendation": "Restore certificate verification and add a regression test.",
                "acceptance_criteria": [
                    "The exact-SHA rerun no longer reports verify=False at src/http_client.py:27."
                ],
                "production_scope": True,
            }
        ],
        "scanner_execution_records": [
            {
                "scanner_name": "bandit",
                "category": "static",
                "state": "completed",
                "status": "completed",
                "completed": True,
                "verified": True,
                "exact_commit_match": True,
                "artifact_hash": "b" * 64,
                "findings": [],
            },
            {
                "scanner_name": "npm-audit",
                "category": "dependency",
                "state": "unavailable",
                "status": "unavailable",
                "completed": False,
                "verified": False,
                "exact_commit_match": True,
                "artifact_hash": "",
                "failure_reason": "package-lock.json not found for npm audit.",
                "findings": [],
            },
            {
                "scanner_name": "eslint",
                "category": "static",
                "state": "unavailable",
                "status": "unavailable",
                "completed": False,
                "verified": False,
                "exact_commit_match": True,
                "artifact_hash": "",
                "failure_reason": "apps/web/package.json not found.",
                "findings": [],
            },
            {
                "scanner_name": "typescript",
                "category": "static",
                "state": "unavailable",
                "status": "unavailable",
                "completed": False,
                "verified": False,
                "exact_commit_match": True,
                "artifact_hash": "",
                "failure_reason": "apps/web/package.json not found.",
                "findings": [],
            },
        ],
        "assessment": {
            "sections": [],
            "maturity_signal": {"technical_score": 72, "evidence_adjusted_score": 72},
            "technical_score": 72,
            "canonical_evidence_adjusted_score": 72,
        },
    }
    markdown = """# NICO Comprehensive Technical Assessment

## Detailed Canonical Findings

No canonical actionable finding was retained.

## Human Review and Acceptance Gate

Client delivery remains blocked.

## Evidence Appendix

- Repository: example/python-service

### Scanner provenance

- eslint: state=unavailable
"""
    return {
        "json": canonical,
        "markdown": markdown,
        "html": "<html><body>legacy</body></html>",
        "pdf_base64": base64.b64encode(_base_pdf()).decode("ascii"),
        "premium_report_renderer": {},
        "phase17_artifact_rebuild": {},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_final_report_replaces_old_findings_and_scanner_only_appendix() -> None:
    result = finalize_client_report_package(_package())
    canonical = result["json"]
    register = canonical["client_finding_remediation_register"]
    summary = canonical["assessment"]["scanner_applicability_summary"]

    assert result["pdf_base64"]
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    assert summary["requested_scanners"] == 4
    assert summary["applicable_scanners"] == 1
    assert summary["not_applicable_scanners"] == 3
    assert {item["scanner_name"] for item in canonical["not_applicable_scanner_records"]} == {
        "npm-audit",
        "eslint",
        "typescript",
    }
    assert register["summary"]["exact_source_code_finding_count"] >= 1
    assert "## Finding and Remediation Register" in result["markdown"]
    assert "## Detailed Canonical Findings" not in result["markdown"]
    assert "Analyzer Applicability and Provenance" in result["markdown"]
    assert "No structured item was retained." not in result["markdown"]
    assert "No completion credit was awarded." in result["markdown"]

    pdf = base64.b64decode(result["pdf_base64"])
    extracted = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    compact = "".join(extracted.split())
    assert pdf.startswith(b"%PDF")
    assert "Finding and Remediation Register" in extracted
    assert "src/http_client.py:27".replace(" ", "") in compact
    assert "tls_verify_disabled" in extracted
    assert extracted.count("Analyzer Applicability and Provenance") == 1
    assert "npm-audit" in extracted
    assert "not applicable" in extracted.casefold() or "not-applicable" in extracted.casefold()
    assert "No structured item was retained." not in extracted
    assert "eslint: unavailable" not in extracted


def test_final_report_is_idempotent_for_register_and_provenance() -> None:
    first = finalize_client_report_package(_package())
    second = finalize_client_report_package(first)

    assert second["markdown"].count("## Finding and Remediation Register") == 1
    assert second["markdown"].count("## Analyzer Applicability and Provenance") == 1
    extracted = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(base64.b64decode(second["pdf_base64"]))).pages
    )
    assert extracted.count("Finding and Remediation Register") == 1
    assert extracted.count("Analyzer Applicability and Provenance") == 1
