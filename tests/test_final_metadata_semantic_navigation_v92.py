from __future__ import annotations

import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _report_pdf(pages: list[list[str]]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    _, height = letter
    for lines in pages:
        y = height - 54
        for line in lines:
            pdf.drawString(42, y, line)
            y -= 18
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _outline_titles(value):
    output: list[str] = []
    if isinstance(value, list):
        for item in value:
            output.extend(_outline_titles(item))
        return output
    title = getattr(value, "title", None)
    if title:
        output.append(str(title))
    return output


def test_final_base_report_canonical_identity_retains_supplied_display_metadata():
    from nico import comprehensive_report_package as base_report
    from nico.comprehensive_final_display_metadata_v92 import (
        install_comprehensive_final_display_metadata_v92,
    )

    installed = install_comprehensive_final_display_metadata_v92()
    assert installed["bound"] is True
    assert installed["canonical_scope_ids_unchanged"] is True
    assert installed["canonical_scores_unchanged"] is True

    result = base_report.build_comprehensive_report_package(
        identity={
            "run_id": "comprun_metadata_regression",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_metadata_regression",
            "customer_id": "customer_scope_regression",
            "project_id": "project_scope_regression",
            "customer_name": "NICO Production Metadata Proof 2026-08-26",
            "project_name": "Comprehensive Metadata E2E Proof",
            "primary_technical_contact": "NICO Metadata Proof Contact",
        },
        stage_results={},
    )

    assert result["status"] == "complete"
    canonical = result["report_package"]["json"]
    identity = canonical["identity"]
    assert identity["customer_id"] == "customer_scope_regression"
    assert identity["project_id"] == "project_scope_regression"
    assert identity["customer_name"] == "NICO Production Metadata Proof 2026-08-26"
    assert identity["project_name"] == "Comprehensive Metadata E2E Proof"
    assert identity["primary_technical_contact"] == "NICO Metadata Proof Contact"
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_semantic_toc_keeps_every_heading_when_compaction_puts_three_sections_on_one_page():
    from nico.comprehensive_semantic_navigation_v2 import semantic_renumber_and_outline

    source = _report_pdf(
        [
            ["NICO Comprehensive", "AUTOMATED DRAFT | PENDING HUMAN APPROVAL"],
            [
                "NICO Comprehensive · AUTOMATED DRAFT",
                "Code audit",
                "Evidence for code audit.",
                "Dependency / Library Ecosystem",
                "Evidence for dependencies.",
                "Secrets Exposure Review",
                "Evidence for secrets.",
            ],
            [
                "NICO Comprehensive · AUTOMATED DRAFT",
                "Static Analysis",
                "Evidence for static analysis.",
            ],
            [
                "NICO Comprehensive · AUTOMATED DRAFT",
                "Human Review and Acceptance Gate",
                "Authorized human review remains required.",
            ],
        ]
    )

    revised = semantic_renumber_and_outline(source)
    reader = PdfReader(io.BytesIO(revised))
    assert len(reader.pages) == 5

    toc = reader.pages[1].extract_text() or ""
    for title in (
        "Code audit",
        "Dependency / Library Ecosystem",
        "Secrets Exposure Review",
        "Static Analysis",
        "Human Review and Acceptance Gate",
    ):
        assert title in toc

    # All three compacted technical sections intentionally map to the same physical
    # page after the TOC is inserted. The old one-title-per-page navigation lost two.
    lines = [" ".join(line.split()) for line in toc.splitlines() if line.strip()]
    positions = {title: lines.index(title) for title in (
        "Code audit",
        "Dependency / Library Ecosystem",
        "Secrets Exposure Review",
    )}
    for title, index in positions.items():
        assert lines[index + 1] == "3", title

    static_index = lines.index("Static Analysis")
    assert lines[static_index + 1] == "4"
    gate_index = lines.index("Human Review and Acceptance Gate")
    assert lines[gate_index + 1] == "5"

    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Evidence for code audit." in full_text
    assert "Evidence for dependencies." in full_text
    assert "Evidence for secrets." in full_text
    assert "Evidence for static analysis." in full_text

    outline_titles = _outline_titles(reader.outline)
    for title in (
        "Code audit",
        "Dependency / Library Ecosystem",
        "Secrets Exposure Review",
        "Static Analysis",
        "Human Review and Acceptance Gate",
    ):
        assert title in outline_titles


def test_spanish_semantic_navigation_adds_no_english_toc_or_document_page_label():
    from nico.comprehensive_semantic_navigation_v2 import semantic_renumber_and_outline

    source = _report_pdf(
        [
            ["NICO", "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE"],
            [
                "NICO Comprehensive · BORRADOR AUTOMATIZADO",
                "Auditoría de código",
                "Evidencia conservada.",
                "Ecosistema de dependencias y bibliotecas",
                "Evidencia conservada.",
            ],
            [
                "NICO Comprehensive · BORRADOR AUTOMATIZADO",
                "Puerta de revisión y aceptación humana",
                "La aprobación humana autorizada sigue pendiente.",
            ],
        ]
    )

    revised = semantic_renumber_and_outline(source)
    reader = PdfReader(io.BytesIO(revised))
    toc = reader.pages[1].extract_text() or ""
    assert "Tabla de contenido" in toc
    assert "Table of Contents" not in toc
    assert "Auditoría de código" in toc
    assert "Ecosistema de dependencias y bibliotecas" in toc
    assert "Puerta de revisión y aceptación humana" in toc

    document_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Página del documento 3 de 4" in document_text
    assert "Document page 3 of 4" not in document_text
