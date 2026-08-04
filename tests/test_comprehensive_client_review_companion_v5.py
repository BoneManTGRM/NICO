from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.client_pdf_status_sanitizer_v1 import sanitize_client_pdf_status
from nico.client_pdf_status_sanitizer_v7 import install_client_pdf_status_sanitizer_v7
from nico.comprehensive_client_review_companion_v5 import (
    COMPANION_PAGE_COUNT,
    SECTION_COUNT,
    merge_substantive_review_markdown,
    render_substantive_review_pdf,
    substantive_review_sections,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_BINDING = ROOT / "nico" / "comprehensive_mobile_score_projection_v2.py"
COMMIT = "3c4352ae1873c547dd01406da833d2faedb5039b"


def _canonical() -> dict:
    section_ids = (
        "functional_qa",
        "platform_parity",
        "historical_trends_and_change_failure",
        "requirements_traceability",
        "stakeholder_and_business_alignment",
        "risk_reduction_and_executive_briefing",
        "six_month_roadmap",
        "staffing_sequencing_and_cost",
    )
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": COMMIT,
            "run_id": "comprun_review_v5",
            "report_language": "en",
        },
        "assessment": {
            "technical_score": 93,
            "evidence_adjusted_score": 89,
            "ci_cd_operational_health": {
                "workflow_run_count": 100,
                "outcome_taxonomy": {
                    "success": 85,
                    "failure": 11,
                    "cancelled": 0,
                    "skipped": 0,
                    "neutral": 0,
                    "timed_out": 0,
                    "action_required": 0,
                    "queued_or_in_progress": 0,
                    "unknown": 4,
                },
            },
            "canonical_scanner_finding_register": {
                "totals": {
                    "raw": 657,
                    "material": 0,
                    "review_required": 656,
                    "approved_or_nonblocking": 1,
                    "excluded_test_only": 0,
                }
            },
            "stage_summaries": [
                {
                    "stage_id": section_id,
                    "status": "unavailable" if section_id != "risk_reduction_and_executive_briefing" else "complete",
                    "summary": "Repository evidence retained for bounded review.",
                    "evidence": [],
                    "findings": [],
                    "unavailable": [],
                }
                for section_id in section_ids
            ],
        },
        "stage_summaries": [],
        "client_finding_remediation_register": {
            "summary": {
                "decision_finding_count": 50,
                "exact_source_code_finding_count": 50,
            },
            "code_findings": [
                {
                    "priority": "P2",
                    "finding_id": "NICO-FINDING-EXAMPLE",
                    "title": "Reduce complexity in example function",
                    "location": "apps/web/app/example.tsx:10",
                    "business_impact": "Concentrated branch logic increases review cost.",
                }
            ],
        },
        "roadmap": [],
        "staffing_plan": [],
    }


def _pdf_with_pages(pages: list[list[str]]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for page_lines in pages:
        y = 780
        for line in page_lines:
            pdf.drawString(40, y, line)
            y -= 18
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_all_eight_sections_are_substantive_and_truthful() -> None:
    sections = substantive_review_sections(_canonical(), spanish=False)

    assert len(sections) == SECTION_COUNT == 8
    assert [section["section_number"] for section in sections] == list(range(1, 9))
    assert all(section["section_count"] == 8 for section in sections)
    assert all(section["summary"] for section in sections)
    assert all(section["evidence"] for section in sections)
    assert all(section["can_conclude"] for section in sections)
    assert all(section["cannot_conclude"] for section in sections)
    assert all(section["required_input"] for section in sections)
    assert all(section["recommended_decision"] for section in sections)

    combined = "\n".join(
        "\n".join(
            [
                section["status"],
                section["summary"],
                *section["evidence"],
                *section["can_conclude"],
                *section["cannot_conclude"],
                *section["required_input"],
                section["recommended_decision"],
            ]
        )
        for section in sections
    )
    assert "No additional structured observation was retained" not in combined
    assert "No additional limitation was retained" not in combined

    by_id = {section["id"]: section for section in sections}
    assert by_id["platform_parity"]["status"] == (
        "Repository indicators assessed — runtime parity not assessed"
    )
    assert "Device and human-context evidence" not in combined or "device" in combined.casefold()
    assert by_id["six_month_roadmap"]["status"] == (
        "Framework only — pending stakeholder validation"
    )
    assert "framework" in by_id["six_month_roadmap"]["recommended_decision"].casefold()


def test_companion_pdf_has_continuous_section_numbering_without_skipped_review_labels() -> None:
    pdf = render_substantive_review_pdf(_canonical(), spanish=False)
    reader = PdfReader(io.BytesIO(pdf))
    extracted_pages = [page.extract_text() or "" for page in reader.pages]
    extracted = "\n".join(extracted_pages)

    assert len(reader.pages) == COMPANION_PAGE_COUNT == 16
    for section_number in range(1, 9):
        first = f"Section {section_number} of 8 | Page 1 of 2"
        second = f"Section {section_number} of 8 | Page 2 of 2"
        assert first in extracted
        assert second in extracted
    assert "Review 2" not in extracted
    assert "Review 5" not in extracted
    assert "Review 8" not in extracted
    assert "No additional structured observation was retained" not in extracted
    assert "AUTOMATED DRAFT | HUMAN REVIEW REQUIRED" in extracted
    assert "HUMAN DECISION PENDING | DELIVERY BLOCKED" in extracted
    assert all(page.strip() for page in extracted_pages)


def test_markdown_uses_specific_limitations_and_not_filler() -> None:
    markdown = merge_substantive_review_markdown(
        "# NICO Comprehensive\n\nAUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED\n\n## Evidence Package Summary\nExisting summary.\n",
        _canonical(),
        spanish=False,
    )

    assert "## Functional QA" in markdown
    assert "## Platform Parity" in markdown
    assert "## Six-Month Roadmap" in markdown
    assert "Repository indicators assessed — runtime parity not assessed" in markdown
    assert "Framework only — pending stakeholder validation" in markdown
    assert "What can be concluded" in markdown
    assert "What cannot be concluded" in markdown
    assert "Required client input" in markdown
    assert "Recommended decision" in markdown
    assert "No additional structured observation was retained" not in markdown
    assert "No additional limitation was retained" not in markdown
    assert "CLIENT DELIVERY BLOCKED" in markdown


def test_status_sanitizer_preserves_client_review_pages_but_drops_raw_internal_pages() -> None:
    install_client_pdf_status_sanitizer_v7()
    source = _pdf_with_pages(
        [
            [
                "NICO | Comprehensive client review | automated draft",
                "Section 1 of 8 | Page 1 of 2",
                "Retained evidence",
                "artifact_schema",
                "stage_execution.internal",
            ],
            [
                "Raw evidence appendix",
                "Retained evidence",
                "artifact_schema",
                "stage_execution.internal",
            ],
            ["Safe client page", "AUTOMATED DRAFT"],
        ]
    )

    sanitized = sanitize_client_pdf_status(source)
    reader = PdfReader(io.BytesIO(sanitized))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert len(reader.pages) == 2
    assert "Section 1 of 8 | Page 1 of 2" in text
    assert "Raw evidence appendix" not in text
    assert "Safe client page" in text


def test_runtime_binds_v5_after_legacy_v4_and_preserves_sanitized_pages() -> None:
    source = RUNTIME_BINDING.read_text(encoding="utf-8")

    legacy = source.index("install_comprehensive_review_companion_v4()")
    substantive = source.index("install_comprehensive_review_companion_v5()")
    sanitizer = source.index("install_client_pdf_status_sanitizer_v7()")
    assert legacy < substantive < sanitizer
    assert 'RUNTIME_REVISION = "v72-exact-digest-approved-delivery"' in source
    assert '"decision_useful_review_companion_pages": 16' in source
    assert '"continuous_review_section_numbering": True' in source
    assert '"filler_only_review_pages_allowed": False' in source
    assert '"roadmap_claim_is_framework_only": True' in source
    assert '"runtime_platform_parity_not_assessed_without_device_evidence": True' in source
