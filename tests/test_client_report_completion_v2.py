from __future__ import annotations

import base64
import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

from nico.client_report_completion_v2 import (
    finalize_client_report_package,
    prepare_client_report_package,
)


SHA = "e" * 40
GENERATED_AT = "2026-08-04T16:15:00Z"


def _base_pdf() -> bytes:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    SimpleDocTemplate(buffer, pagesize=letter, invariant=1).build(
        [
            Paragraph("NICO Comprehensive", styles["Title"]),
            Paragraph("Repository: example/product", styles["BodyText"]),
            Paragraph(f"Exact commit: {SHA}", styles["BodyText"]),
            Paragraph(f"Generated: {GENERATED_AT}", styles["BodyText"]),
            Paragraph("Technical maturity: 78/100", styles["BodyText"]),
            Paragraph("Evidence-adjusted readiness: 78/100", styles["BodyText"]),
            Paragraph("7 client-review section(s) remain limited", styles["BodyText"]),
            Paragraph("Executive decision report", styles["BodyText"]),
            PageBreak(),
            Paragraph("Executive Risk Register and Decision Briefing", styles["Heading1"]),
            Paragraph("No structured item was retained.", styles["BodyText"]),
            PageBreak(),
            Paragraph("Evidence Appendix", styles["Heading1"]),
            Paragraph("Bounded stage evidence", styles["BodyText"]),
            PageBreak(),
            Paragraph("Human Review and Acceptance Gate", styles["Heading1"]),
            Paragraph("CLIENT DELIVERY BLOCKED", styles["BodyText"]),
        ]
    )
    return buffer.getvalue()


def _empty_scanner_register() -> dict:
    zero = {
        "raw": 0,
        "material": 0,
        "review_required": 0,
        "approved_or_nonblocking": 0,
        "excluded_test_only": 0,
        "exact_source": 0,
        "source_path": 0,
        "payload_without_source": 0,
        "count_only": 0,
    }
    return {
        "artifact_schema": "nico.canonical-scanner-findings.v1",
        "findings": [],
        "totals": dict(zero),
        "summary_by_category": {
            "dependency": dict(zero),
            "secret": dict(zero),
            "static": dict(zero),
        },
        "candidate_record_count": 0,
        "candidate_record_count_matches_raw": True,
        "count_parity_verified": True,
        "candidate_evidence_quality_totals_match_source": True,
    }


def _package() -> dict:
    canonical = {
        "identity": {
            "repository": "example/product",
            "commit_sha": SHA,
            "run_id": "comprun_completion_v2",
            "evidence_ledger_id": "ledger_completion_v2",
            "generated_at": GENERATED_AT,
        },
        "generated_at": GENERATED_AT,
        "repository_evidence": {
            "file_evidence": {
                "sampled_paths": [
                    "package.json",
                    "package-lock.json",
                    "apps/web/app/operations/page.tsx",
                ]
            }
        },
        "canonical_findings": [
            {
                "finding_id": "RISK-OLD",
                "priority": "P1",
                "category": "architecture",
                "status": "open",
                "title": "operations page has concentrated branching and elevated change risk",
                "location": "apps/web/app/operations/page.tsx:177",
                "fact": "cyclomatic_complexity=52; loc=173; grade=F",
                "interpretation": "High-complexity code hotspot",
                "business_impact": "Concentrated branching increases regression risk.",
                "recommendation": "Decompose the hotspot.",
                "acceptance_criteria": ["Complexity is at or below 30."],
                "exact_commit_match": True,
                "production_scope": True,
            }
        ],
        "complexity_evidence": {
            "hotspots": [
                {
                    "path": "apps/web/app/operations/page.tsx",
                    "line": 177,
                    "name": "OperationsPage",
                    "cyclomatic_complexity": 52,
                    "loc": 173,
                    "grade": "F",
                    "source_excerpt": "export default function OperationsPage() { return null; }",
                }
            ]
        },
        "scanner_execution_records": [
            {
                "scanner_name": "eslint",
                "state": "completed_with_findings",
                "status": "completed_with_findings",
                "completed": True,
                "verified": True,
                "verified_complete": True,
                "exact_commit_match": True,
                "artifact_hash": "a" * 64,
                "findings": [
                    {
                        "path": (
                            "/tmp/nico-snapshot-scan-xyz/repo/"
                            "apps/web/app/operations/AssessmentRecoveryPanel.tsx"
                        ),
                        "line": 110,
                        "message": (
                            "Definition for rule 'react-hooks/exhaustive-deps' was not found."
                        ),
                    }
                ],
            },
            {
                "scanner_name": "typescript",
                "state": "completed",
                "status": "completed",
                "completed": True,
                "verified": True,
                "verified_complete": True,
                "exact_commit_match": True,
                "artifact_hash": "b" * 64,
                "findings": [],
            },
        ],
        "assessment": {
            "sections": [
                {
                    "id": "architecture",
                    "label": "Architecture & Technical Debt",
                    "score": 78,
                    "status": "moderate",
                }
            ],
            "technical_score": 78,
            "canonical_evidence_adjusted_score": 78,
            "canonical_scanner_finding_register": _empty_scanner_register(),
            "final_report_input_scores_synchronized": True,
            "report_contract_status": "blocked",
            "report_contract_reason": "canonical_score_truth_mismatch",
        },
    }
    markdown = f"""# NICO Comprehensive Technical Assessment

Repository: example/product
Exact commit: {SHA}
Generated: {GENERATED_AT}
Technical maturity: 78/100
Evidence-adjusted readiness: 78/100
7 client-review section(s) remain limited

## Detailed Canonical Findings

No canonical actionable finding was retained.

## Evidence Appendix

Bounded evidence.

## Human Review and Acceptance Gate

Client delivery remains blocked.
"""
    return {
        "json": canonical,
        "generated_at": GENERATED_AT,
        "markdown": markdown,
        "html": (
            "<html><body>"
            "<p>Repository: example/product</p>"
            f"<p>Exact commit: {SHA}</p>"
            f"<p>Generated: {GENERATED_AT}</p>"
            "<p>Technical maturity: 78/100</p>"
            "<p>Evidence-adjusted readiness: 78/100</p>"
            "<p>7 client-review section(s) remain limited</p>legacy"
            "</body></html>"
        ),
        "pdf_base64": base64.b64encode(_base_pdf()).decode("ascii"),
        "premium_report_renderer": {},
        "phase17_artifact_rebuild": {},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_prepare_reconciles_population_before_premium_render() -> None:
    result = prepare_client_report_package(_package())
    canonical = result["json"]
    register = canonical["client_finding_remediation_register"]
    summary = register["summary"]

    assert canonical["assessment"]["report_contract_status"] == "reconciled"
    assert canonical["assessment"]["finding_register_count"] == summary["decision_finding_count"]
    assert len(canonical["canonical_findings"]) == summary["decision_finding_count"]
    assert summary["exact_source_code_finding_count"] == 1
    assert summary["scanner_configuration_issue_count"] == 1
    assert canonical["scanner_execution_records"][0]["state"] == "configuration_failed"
    assert canonical["scanner_execution_records"][0]["findings"] == []


def test_final_report_has_one_source_aware_register_and_no_worker_paths() -> None:
    result = finalize_client_report_package(_package())
    register = result["client_finding_remediation_register"]
    summary = register["summary"]
    markdown = result["markdown"]
    html = result["html"]
    pdf = base64.b64decode(result["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    combined = "\n".join((markdown, html, extracted))

    assert pdf.startswith(b"%PDF")
    assert GENERATED_AT in extracted
    assert markdown.count("## Compact Finding and Remediation Register") == 1
    assert "Decision findings: 1" in markdown
    assert "Complete exact-source index" in markdown
    assert "apps/web/app/operations/page.tsx:177" in combined
    assert "OperationsPage" in combined
    assert "typed hooks or services" in combined
    assert "/tmp/nico-snapshot-scan-" not in combined
    assert "/home/runner/work/" not in combined
    assert "unknown · unknown" not in combined
    assert "No structured item was retained." not in combined
    assert "react-hooks/exhaustive-deps" not in result["client_finding_remediation_register"]["code_findings"].__repr__()
    assert summary["semantic_duplicate_code_anchors_absent"] is True
    assert summary["finding_population_reconciled"] is True
    assert result["client_report_completion"]["temporary_worker_paths_absent"] is True
    assert result["client_report_completion"]["unverified_tls_candidates_not_promoted"] is True
    assert result["client_report_completion"]["duplicate_full_page_finding_cards_absent"] is True
    assert result["client_report_completion"]["raw_stage_dump_excluded_from_client_pdf"] is True
    assert len(reader.pages) <= result["client_report_completion"]["client_pdf_page_boundary"]
    assert result["json"]["identity"]["generated_at"] == GENERATED_AT
    assert result["report_finality"] == "automated_draft"
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_python_only_live_manifest_renders_six_of_six_applicable_scanners() -> None:
    package = _package()
    canonical = package["json"]
    canonical["repository_evidence"] = {
        "file_evidence": {"sampled_paths": ["requirements.txt", "app.py", "src/service.py"]},
        "dependency_evidence": {"manifest_paths": ["requirements.txt"]},
    }
    canonical["canonical_findings"][0].update(
        {
            "title": "service function has concentrated branching and elevated change risk",
            "location": "src/service.py:27",
        }
    )
    canonical["complexity_evidence"]["hotspots"][0].update(
        {
            "path": "src/service.py",
            "line": 27,
            "name": "process_request",
            "source_excerpt": "def process_request(payload): return payload",
        }
    )
    reasons = {
        "npm-audit": "No package-lock.json with an adjacent package.json was found.",
        "eslint": "No supported JavaScript or TypeScript source files were found in apps/web/app.",
        "typescript": "Project dependencies were not prepared.",
    }
    tools = [
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
    records = []
    for scanner in tools:
        completed = scanner not in reasons
        records.append(
            {
                "scanner_name": scanner,
                "state": "completed" if completed else "failed",
                "status": "completed" if completed else "failed",
                "completed": completed,
                "verified": completed,
                "verified_complete": completed,
                "exact_commit_match": True,
                "artifact_hash": scanner.replace("-", "") * 8 if completed else "",
                "failure_reason": reasons.get(scanner, ""),
                "findings": [],
            }
        )
    canonical["scanner_execution_records"] = records
    canonical["live_scanner_evidence"] = {
        "tools_requested": tools,
        "tools_run": [scanner for scanner in tools if scanner not in reasons],
        "failed_tools": [],
        "unavailable_tools": list(reasons),
        "timed_out_tools": [],
    }

    result = finalize_client_report_package(package)
    finalized = result["json"]
    extracted = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(base64.b64decode(result["pdf_base64"]))).pages
    )

    assert finalized["analyzer_execution_coverage"] == 100
    assert finalized["completed_applicable_analyzers"] == 6
    assert finalized["incomplete_applicable_analyzers"] == 0
    assert len(finalized["scanner_execution_records"]) == 6
    assert len(finalized["not_applicable_scanner_records"]) == 3
    assert "6 of 6 applicable scanner executions completed" in extracted
    assert "6 of 9 applicable scanner executions completed" not in extracted
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
