from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.client_pdf_status_sanitizer_v1 import sanitize_client_pdf_status
from nico.client_ready_html_v1 import render_client_html
from nico.comprehensive_client_ready_projection_v1 import (
    APPROVAL_SUFFIX,
    EN_BOUNDARY,
    MAX_CLIENT_PDF_PAGES,
    apply_automated_draft_truth,
    clean_finding_title,
    compact_client_markdown,
    compose_compact_client_pdf,
    render_compact_finding_register_pdf,
    render_evidence_review_gate_pdf,
)
from nico.v2_client_ready_truth_projection_v1 import project_client_ready_truth


ROOT = Path(__file__).resolve().parents[1]
PHASE17 = ROOT / "nico" / "phase17_canonical_artifact_rebuild_v1.py"
COMPLETION = ROOT / "nico" / "client_report_completion_v2.py"
PIPELINE = ROOT / "nico" / "v2_pipeline_adapter.py"


def _pdf_pages(*pages: list[str]) -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter, invariant=1)
    for lines in pages:
        y = 740
        for line in lines:
            pdf.drawString(50, y, line)
            y -= 16
        pdf.showPage()
    pdf.save()
    return output.getvalue()


def _register(count: int = 49) -> dict[str, Any]:
    findings = []
    for index in range(count):
        symbol = "<arrow>" if index == 0 else f"function_{index}"
        findings.append(
            {
                "finding_id": f"NICO-FINDING-{index:012X}",
                "priority": "P1" if index < 7 else "P2",
                "title": f"Reduce complexity in {symbol}",
                "symbol": symbol,
                "location": f"nico/module_{index}.py:{100 + index}",
                "path": f"nico/module_{index}.py",
                "line": 100 + index,
                "observed_evidence": f"cyclomatic_complexity={31 + index}",
                "business_impact": "Concentrated branching increases regression risk.",
                "recommended_correction": "Extract bounded helpers and add characterization tests.",
                "verification": [
                    "The exact-SHA rerun no longer reports the condition.",
                    "The required-check suite passes.",
                ],
                "status": "review_required",
            }
        )
    return {
        "code_findings": findings,
        "operational_findings": [],
        "summary": {
            "finding_population_reconciled": True,
            "semantic_duplicate_code_anchors_absent": True,
            "scanner_configuration_errors_promoted_to_code_findings": False,
            "unverified_tls_candidates_promoted_to_p1": False,
            "stable_alias_projection_idempotent": True,
            "decision_finding_count": count,
            "exact_source_code_finding_count": count,
            "operational_or_context_finding_count": 0,
        },
    }


def _canonical(register: dict[str, Any]) -> dict[str, Any]:
    findings = list(register["code_findings"])
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "comprun_client_ready_test",
        },
        "assessment": {
            "technical_score": 93,
            "evidence_adjusted_score": 90,
            "sections": [
                {"section_id": "dependency", "status": "Strong", "summary": "Dependency evidence."},
                {"section_id": "secrets", "status": "Strong", "summary": "Secret evidence."},
                {"section_id": "static_analysis", "status": "Strong", "summary": "Static evidence."},
            ],
        },
        "canonical_findings": findings,
        "review_candidate_summary": {
            "review_required_total": 614,
            "verified_material_total": 0,
            "by_category": {
                "dependency": {"raw": 59, "material": 0, "review_required": 59},
                "secret": {"raw": 17, "material": 0, "review_required": 17},
                "static": {"raw": 538, "material": 0, "review_required": 538},
            },
        },
    }


def test_unapproved_package_uses_automated_draft_truth() -> None:
    projected = apply_automated_draft_truth({"assessment": {}})

    assert APPROVAL_SUFFIX == "AUTOMATED-DRAFT-PENDING-APPROVAL"
    assert projected["report_finality"] == "automated_draft"
    assert projected["approval_status"] == "pending_human_approval"
    assert projected["delivery_status"] == "blocked_pending_human_approval"
    assert projected["client_delivery_allowed"] is False
    assert projected["assessment"]["client_delivery_status"] == "blocked"


def test_review_candidate_sections_are_provisional_not_unqualified_strong() -> None:
    projected = project_client_ready_truth(_canonical(_register(3)))
    sections = projected["assessment"]["sections"]

    assert all(section["status"] == "Provisional Strong" for section in sections)
    assert sections[0]["review_required_candidates"] == 59
    assert sections[1]["review_required_candidates"] == 17
    assert sections[2]["review_required_candidates"] == 538
    assert all(section["score_effect"] == "assurance-only until triaged" for section in sections)
    assert projected["report_finality"] == "automated_draft"


def test_compact_register_retains_all_exact_locations_without_full_page_duplication() -> None:
    register = _register()
    pdf = render_compact_finding_register_pdf(register, spanish=False)
    reader = PdfReader(io.BytesIO(pdf))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert len(reader.pages) < 20
    assert "Prioritized executive detail" in extracted
    assert "Complete Exact-Source Index" in extracted
    assert "anonymous callback" in extracted
    for finding in register["code_findings"]:
        assert finding["location"] in extracted


def test_compact_client_composition_removes_duplicate_cards_and_raw_appendix() -> None:
    register = _register(12)
    canonical = _canonical(register)
    base = _pdf_pages(
        ["NICO COMPREHENSIVE", EN_BOUNDARY],
        ["Executive Decision Brief", "Technical maturity 93/100"],
        ["NICO-FINDING-DUPLICATE", "Exact source", "Implementation sequence"],
        ["Evidence Appendix", "raw internal stage evidence"],
        ["Analyzer Applicability and Provenance", "raw scanner hashes"],
    )
    register_pdf = render_compact_finding_register_pdf(register, spanish=False)
    gate_pdf = render_evidence_review_gate_pdf(canonical, register, spanish=False)
    result = compose_compact_client_pdf(base, register_pdf, gate_pdf)
    reader = PdfReader(io.BytesIO(result))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert len(reader.pages) <= MAX_CLIENT_PDF_PAGES
    assert "NICO-FINDING-DUPLICATE" not in extracted
    assert "raw internal stage evidence" not in extracted
    assert "raw scanner hashes" not in extracted
    assert "Compact Finding and Remediation Register" in extracted
    assert "Human Review and Acceptance Gate" in extracted
    assert EN_BOUNDARY in extracted


def test_compact_markdown_and_html_remove_finality_and_raw_appendix() -> None:
    register = _register(5)
    canonical = _canonical(register)
    existing = """# NICO Comprehensive

FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED

## Executive Decision Brief
Useful decision content.

## Detailed Canonical Findings
### P1 - duplicate card
- Finding ID: NICO-FINDING-OLD

## Evidence Appendix
raw internal stage dump

## Human Review and Acceptance Gate
The final automated report package is complete.

## Delivery Status
Blocked.
"""
    markdown = compact_client_markdown(existing, canonical, register, spanish=False)
    rendered = render_client_html(markdown, "NICO Comprehensive", spanish=False)

    assert "FINAL REPORT" not in markdown
    assert "raw internal stage dump" not in markdown
    assert "NICO-FINDING-OLD" not in markdown
    assert EN_BOUNDARY in markdown
    assert "Complete exact-source index" in markdown
    assert "FINAL REPORT" not in rendered
    assert EN_BOUNDARY in rendered


def test_pdf_status_sanitizer_removes_legacy_final_headers() -> None:
    original = _pdf_pages(
        [
            "NICO Comprehensive · comprun_test · FINAL Page 1",
            "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED",
        ]
    )
    sanitized = sanitize_client_pdf_status(original)
    extracted = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(sanitized)).pages)

    assert "FINAL REPORT" not in extracted
    assert "· FINAL Page" not in extracted
    assert "AUTOMATED DRAFT" in extracted


def test_phase17_installs_and_enforces_the_client_ready_projection() -> None:
    phase17 = PHASE17.read_text(encoding="utf-8")
    completion = COMPLETION.read_text(encoding="utf-8")
    pipeline = PIPELINE.read_text(encoding="utf-8")

    assert "install_client_ready_truth_projection()" in phase17
    assert "sanitize_client_pdf_status" in phase17
    assert "render_compact_finding_register_pdf" in completion
    assert "compose_compact_client_pdf" in completion
    assert "MAX_CLIENT_PDF_PAGES" in completion
    assert '"full_evidence_appendix_in_client_pdf": False' in completion
    assert '"report_finality": REPORT_FINALITY' in completion
    assert "AUTOMATED-DRAFT-PENDING-APPROVAL" in pipeline
    assert '"report_finality": REPORT_FINALITY' in pipeline


def test_identifier_cleanup_removes_placeholder_and_spacing_corruption() -> None:
    assert clean_finding_title("Reduce complexity in <arrow>") == "Reduce complexity in anonymous callback"
    assert clean_finding_title("Reduce complexity in _r ich_detailed_findings") == "Reduce complexity in _rich_detailed_findings"
