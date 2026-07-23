from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from types import ModuleType

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "nico" / "final_report_package_v1.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("final_report_package_v1_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_final_language_replaces_cover_footer_and_delivery_draft_terms() -> None:
    module = _load_module()

    assert module._final_language(
        "DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED"
    ) == "FINAL REPORT PACKAGE · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED"
    assert module._final_language(
        "NICO Comprehensive · run_123 · DRAFT"
    ) == "NICO Comprehensive · run_123 · FINAL REPORT"
    assert module._final_language(
        "The automated assessment is complete only as a draft."
    ) == "The automated final report package is complete and ready for human review."


def test_final_report_mapping_preserves_review_gate_and_renames_artifact() -> None:
    module = _load_module()
    report = {
        "markdown": "**DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED**",
        "html": "<span>DRAFT · HUMAN REVIEW REQUIRED</span>",
        "pdf_base64": "placeholder",
        "pdf_filename": "nico-comprehensive-assessment-DRAFT.pdf",
    }

    output = module._finalize_report_mapping(report, service="comprehensive")

    assert output is report
    assert "DRAFT" not in output["markdown"]
    assert "DRAFT" not in output["html"]
    assert output["pdf_filename"].endswith("-FINAL.pdf")
    assert output["report_state"] == "final_report_pending_human_approval"
    assert output["report_finalized"] is True
    assert output["human_review_status"] == "pending"
    assert output["human_review_required"] is True
    assert output["client_delivery_allowed"] is False


def test_reportlab_context_removes_draft_from_paragraphs_and_footers() -> None:
    module = _load_module()
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    buffer = io.BytesIO()

    def footer(canvas, _doc) -> None:
        canvas.drawString(36, 24, "NICO Comprehensive · run_123 · DRAFT")

    with module._final_reportlab_language():
        # Import again while the context is active because production renderers import
        # Paragraph inside the report-building function.
        from reportlab.platypus import Paragraph as ActiveParagraph

        doc = SimpleDocTemplate(buffer, pagesize=letter, invariant=1)
        doc.build(
            [
                ActiveParagraph(
                    "DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED",
                    getSampleStyleSheet()["BodyText"],
                )
            ],
            onFirstPage=footer,
            onLaterPages=footer,
        )

    text = "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(buffer.getvalue())).pages)
    assert "DRAFT" not in text.upper()
    assert "FINAL REPORT PACKAGE" in text.upper()
    assert "NICO COMPREHENSIVE · RUN_123 · FINAL REPORT" in text.upper()


def test_pdf_draft_detection_samples_cover_and_last_page() -> None:
    module = _load_module()
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    SimpleDocTemplate(buffer, pagesize=letter, invariant=1).build(
        [Paragraph("Final report", styles["BodyText"]), PageBreak(), Paragraph("DRAFT", styles["BodyText"])]
    )

    assert module._pdf_contains_draft(buffer.getvalue()) is True
