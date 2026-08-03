from __future__ import annotations

import base64
import io
from typing import Any, Mapping

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico import v2_localized_report_quality_repairs as localized
from nico import v2_report_quality_repairs as quality
from nico import v2_report_quality_runtime_compat as runtime_compat
from nico.comprehensive_client_ready_projection_v1 import EN_BOUNDARY
from nico.v2_automated_draft_quality_compat_v3 import (
    install_automated_draft_quality_compat,
    repair_rendered_report,
    validate_final_pdf,
)

RUN_ID = "comprun_multipage_scorecard"
COMMIT = "a" * 40


def _sections() -> list[dict]:
    labels = [
        "Code Audit",
        "Dependency / Library Ecosystem",
        "Secrets and Credential Exposure",
        "Static Analysis",
        "CI/CD Configuration Maturity",
        "Architecture and Data Flow",
        "Developer Delivery Process",
        "Deployment and Infrastructure",
        "Requirements Traceability",
        "Functional QA",
        "Platform Parity",
        "Historical Trends and Change Failure",
        "Stakeholder and Business Alignment",
        "Roadmap and Sequencing",
        "Staffing and Cost",
        "Risk Reduction",
        "Operational Readiness",
        "Evidence Reconciliation",
        *[
            f"Supplemental Verified Control {index:02d}"
            for index in range(1, 41)
        ],
    ]
    return [
        {
            "id": f"control_{index}",
            "label": label,
            "presented_status": "STRONG" if index % 2 == 0 else "MODERATE",
            "presented_score": 90 - (index % 7),
            "summary": (
                "Canonical exact-SHA evidence was retained and reconciled. "
                "This deliberately long summary forces the authoritative scorecard "
                "to continue across multiple PDF pages without dropping any row."
            ),
        }
        for index, label in enumerate(labels)
    ]


def _package() -> dict:
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter, invariant=1)
    pdf.drawString(54, 740, "NICO Comprehensive Technical Assessment")
    pdf.drawString(54, 720, "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED")
    pdf.drawString(54, 700, RUN_ID)
    pdf.drawString(54, 680, COMMIT)
    pdf.showPage()
    pdf.drawString(54, 740, "Canonical Technical Scorecard")
    pdf.drawString(54, 720, "stale single-page scorecard")
    pdf.showPage()
    pdf.save()
    return {
        "json": {
            "identity": {"run_id": RUN_ID, "commit_sha": COMMIT},
            "assessment": {
                "technical_score": 90,
                "evidence_adjusted_score": 88,
                "sections": _sections(),
            },
            "report_finality": "automated_draft",
            "approval_status": "pending_human_approval",
            "delivery_status": "blocked_pending_human_approval",
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "pdf_base64": base64.b64encode(output.getvalue()).decode("ascii"),
        "markdown": f"# NICO\n\n{EN_BOUNDARY}\n",
        "html": f"<html><body><article><p>{EN_BOUNDARY}</p></article></body></html>",
    }


def _forced_multipage_scorecard(canonical: Mapping[str, Any]) -> bytes:
    """Render a deterministic two-page scorecard for continuation validation.

    ReportLab pagination can vary across pinned renderer versions. The production
    contract under test is that the validator derives the exact page range from the
    active renderer and accepts wrapped rows on continuation pages. This fixture
    supplies that renderer output directly without weakening any row or score check.
    """

    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    sections = [
        item
        for item in assessment.get("sections") or []
        if isinstance(item, Mapping)
    ]
    midpoint = (len(sections) + 1) // 2
    pages = (sections[:midpoint], sections[midpoint:])

    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter, invariant=1)
    for page_index, page_sections in enumerate(pages):
        y = 742
        if page_index == 0:
            pdf.setFont("Helvetica-Bold", 15)
            pdf.drawString(42, y, "Canonical Technical Scorecard")
            y -= 28
        else:
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(42, y, "Technical Scorecard Continuation")
            y -= 22

        pdf.setFont("Helvetica", 7.2)
        for section in page_sections:
            label = quality._text(section.get("label") or section.get("id"))
            score = section.get("presented_score", section.get("score"))
            score_label = (
                f"{int(round(score))}/100"
                if isinstance(score, (int, float)) and not isinstance(score, bool)
                else "NOT SCORED"
            )
            if label == "Dependency / Library Ecosystem":
                pdf.drawString(42, y, "Dependency / Library")
                pdf.drawString(165, y - 9, "Ecosystem")
                pdf.drawRightString(560, y, score_label)
                y -= 21
            else:
                pdf.drawString(42, y, label)
                pdf.drawRightString(560, y, score_label)
                y -= 18
        pdf.showPage()
    pdf.save()
    return output.getvalue()


def test_compatibility_binds_combined_validator_last() -> None:
    installation = install_automated_draft_quality_compat()

    assert quality._validate_final_pdf is validate_final_pdf
    assert runtime_compat._validate_final_pdf is validate_final_pdf
    assert localized._validate_final_pdf is validate_final_pdf
    assert installation["combined_lifecycle_and_scorecard_validator_bound"] is True
    assert installation["scorecard_extraction_validation_reasserted_last"] is True
    assert installation["wrapped_label_normalization_enabled"] is True
    assert installation["multi_page_scorecard_supported"] is True
    assert installation["all_canonical_rows_and_scores_required"] is True
    assert installation["legacy_raw_substring_scorecard_validator_bypassed"] is True
    assert installation["automated_draft_lifecycle_validator_preserved"] is True


def test_multipage_scorecard_retains_wrapped_dependency_row(monkeypatch) -> None:
    monkeypatch.setattr(quality, "_scorecard_page", _forced_multipage_scorecard)
    monkeypatch.setattr(
        runtime_compat,
        "_scorecard_page",
        _forced_multipage_scorecard,
    )

    repaired = repair_rendered_report(_package())
    pdf = base64.b64decode(repaired["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf))
    texts = [page.extract_text() or "" for page in reader.pages]
    extracted = "\n".join(texts)
    scorecard_index = next(
        index for index, text in enumerate(texts) if "Canonical Technical Scorecard" in text
    )
    expected_scorecard_pages = len(
        PdfReader(io.BytesIO(quality._scorecard_page(repaired["json"]))).pages
    )

    assert expected_scorecard_pages == 2
    assert scorecard_index + expected_scorecard_pages <= len(reader.pages)
    normalized = " ".join(extracted.split())
    assert "Dependency / Library Ecosystem" in normalized
    assert "Supplemental Verified Control 40" in normalized
    assert EN_BOUNDARY in extracted
    assert "FINAL REPORT" not in extracted.upper()
    assert repaired["report_finality"] == "automated_draft"
    assert repaired["approval_status"] == "pending_human_approval"
    assert repaired["client_delivery_allowed"] is False
    contract = repaired["premium_report_renderer"]
    assert contract["combined_lifecycle_and_scorecard_validator_bound"] is True
    assert contract["scorecard_extraction_validation_reasserted_last"] is True
    assert contract["multi_page_scorecard_supported"] is True
    assert contract["all_canonical_rows_and_scores_required"] is True
    assert contract["legacy_raw_substring_scorecard_validator_bypassed"] is True
    assert contract["automated_draft_lifecycle_validator_preserved"] is True
