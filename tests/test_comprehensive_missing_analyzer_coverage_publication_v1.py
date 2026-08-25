from __future__ import annotations

import base64
import io

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.comprehensive_client_report_render_v60 import (
    validate_existing_report_accuracy,
)
from nico.comprehensive_report_coverage_synchronization_v63 import (
    synchronize_final_report_coverage,
)


def _pdf_without_coverage() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    document.drawString(72, 740, "NICO COMPREHENSIVE")
    document.drawString(72, 720, "Canonical Technical Scorecard")
    document.drawString(72, 700, "Evidence Appendix")
    document.drawString(72, 680, "Human Review and Acceptance Gate")
    document.drawString(72, 660, "Incomplete applicable analyzers: 0")
    document.save()
    return buffer.getvalue()


def _package_without_coverage() -> dict:
    pdf = _pdf_without_coverage()
    markdown = "\n".join(
        (
            "NICO COMPREHENSIVE",
            "Canonical Technical Scorecard",
            "Maturity Exceptional",
            "Evidence Appendix",
            "Human Review and Acceptance Gate",
            "Incomplete applicable analyzers: 0",
        )
    )
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
        "markdown": markdown,
        "html": f"<html><body><main>{markdown}</main></body></html>",
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _pdf_text(package: dict) -> str:
    pdf = base64.b64decode(package["pdf_base64"])
    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def test_exact_omission_failure_is_repaired_from_canonical_coverage() -> None:
    package = _package_without_coverage()

    with pytest.raises(
        ValueError,
        match="client report omitted analyzer execution coverage",
    ):
        validate_existing_report_accuracy(package)

    repaired = synchronize_final_report_coverage(
        package,
        expected_coverage=100,
    )

    assert "analyzer_execution_coverage: 100" in repaired["markdown"]
    assert "analyzer_execution_coverage: 100" in repaired["html"]
    assert "analyzer_execution_coverage: 100" in _pdf_text(repaired)
    assert repaired["coverage_synchronization"]["total_insertions"] == 3
    assert repaired["coverage_synchronization"]["total_replacements"] == 0
    assert repaired["human_review_required"] is True
    assert repaired["client_delivery_allowed"] is False

    validation = validate_existing_report_accuracy(repaired)
    assert validation["canonical_coverage_value"] == 100
    assert validation["conflicting_coverage_absent"] is True
    assert validation["coverage_synchronization_verified"] is True
    assert validation["production_pdf_validated"] is True


def test_missing_coverage_repair_is_byte_idempotent_after_first_insertion() -> None:
    first = synchronize_final_report_coverage(
        _package_without_coverage(),
        expected_coverage=100,
    )
    second = synchronize_final_report_coverage(first, expected_coverage=100)

    assert second["markdown"] == first["markdown"]
    assert second["html"] == first["html"]
    assert base64.b64decode(second["pdf_base64"]) == base64.b64decode(
        first["pdf_base64"]
    )
    assert second["coverage_synchronization"]["total_insertions"] == 0
    assert second["coverage_synchronization"]["total_replacements"] == 0
