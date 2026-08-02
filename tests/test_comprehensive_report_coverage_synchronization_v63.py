from __future__ import annotations

import base64
import io

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.comprehensive_client_report_render_v60 import (
    validate_existing_report_accuracy,
)
from nico.comprehensive_report_coverage_synchronization_v63 import (
    synchronize_final_report_coverage,
    synchronize_pdf_coverage,
)


def _pdf() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer)
    document.drawString(72, 740, "NICO COMPREHENSIVE")
    document.drawString(72, 720, "Canonical Technical Scorecard")
    document.drawString(72, 700, "Evidence Appendix")
    document.drawString(72, 680, "Human Review and Acceptance Gate")
    document.drawString(72, 640, "Analyzer execution coverage: 89%")
    document.drawString(72, 620, "Analyzer execution coverage:")
    document.drawString(260, 620, "89%")
    document.drawString(72, 600, "Unrelated observed value: 89")
    document.drawString(72, 580, "Incomplete applicable analyzers: 0")
    document.save()
    return buffer.getvalue()


def _package() -> dict:
    pdf = _pdf()
    return {
        "json": {
            "analyzer_execution_coverage": 100,
            "scanner_execution_coverage": 100,
            "incomplete_applicable_analyzers": 0,
            "client_readiness_contract": {
                "analyzer_execution_coverage": 100,
                "coverage_numerator": 9,
                "coverage_denominator": 9,
                "maturity_label": "Exceptional",
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        },
        "markdown": "\n".join(
            (
                "NICO COMPREHENSIVE",
                "Canonical Technical Scorecard",
                "Evidence Appendix",
                "Human Review and Acceptance Gate",
                "Analyzer execution coverage: 89%",
                "analyzer_execution_coverage: 100",
                "Incomplete applicable analyzers: 0",
                "Unrelated observed value: 89",
            )
        ),
        "html": "<html><body><p>Analyzer execution coverage is 89%</p></body></html>",
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def test_pdf_synchronizes_full_and_split_coverage_without_touching_unrelated_values() -> None:
    repaired, count = synchronize_pdf_coverage(_pdf(), 100)
    text = _pdf_text(repaired)
    assert count == 2
    assert "Analyzer execution coverage: 100%" in text
    assert "Analyzer execution coverage:\n100%" in text
    assert "Unrelated observed value: 89" in text
    assert "Analyzer execution coverage: 89%" not in text


def test_final_package_binds_one_canonical_value_in_markdown_html_and_pdf() -> None:
    repaired = synchronize_final_report_coverage(
        _package(), expected_coverage=100
    )
    pdf = base64.b64decode(repaired["pdf_base64"])
    combined = "\n".join((repaired["markdown"], repaired["html"], _pdf_text(pdf)))
    assert "Analyzer execution coverage: 89%" not in combined
    assert "Analyzer execution coverage is 89%" not in combined
    assert "Analyzer execution coverage: 100%" in combined
    assert "Analyzer execution coverage is 100%" in combined
    assert "Unrelated observed value: 89" in combined
    assert repaired["coverage_synchronization"]["canonical_coverage_value"] == 100
    assert repaired["coverage_synchronization"]["scores_changed"] is False
    assert repaired["coverage_synchronization"]["scanner_results_changed"] is False
    assert repaired["human_review_required"] is True
    assert repaired["client_delivery_allowed"] is False
    assert repaired["pdf_sha256"]
    assert repaired["markdown_sha256"]
    assert repaired["html_sha256"]
    validation = validate_existing_report_accuracy(repaired)
    assert validation["conflicting_coverage_absent"] is True
    assert validation["coverage_synchronization_verified"] is True
    assert validation["production_pdf_validated"] is True


def test_synchronization_is_idempotent() -> None:
    first = synchronize_final_report_coverage(_package(), expected_coverage=100)
    second = synchronize_final_report_coverage(first, expected_coverage=100)
    assert second["markdown"] == first["markdown"]
    assert second["html"] == first["html"]
    assert base64.b64decode(second["pdf_base64"]) == base64.b64decode(first["pdf_base64"])
    assert second["coverage_synchronization"]["total_replacements"] == 0
