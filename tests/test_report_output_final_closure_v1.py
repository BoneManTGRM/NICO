from __future__ import annotations

import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _sparse_report_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    width, height = letter
    sections = (
        ("Architecture and data flow", "ARCH-EVIDENCE-ALPHA"),
        ("Developer delivery process", "DELIVERY-EVIDENCE-BRAVO"),
        ("Requirements traceability", "REQUIREMENTS-EVIDENCE-CHARLIE"),
        ("Historical trends and change failure", "HISTORY-EVIDENCE-DELTA"),
    )
    for index, (title, marker) in enumerate(sections, start=1):
        y = height - 54
        for line in (
            "NICO Comprehensive | AUTOMATED DRAFT · PENDING HUMAN APPROVAL",
            title,
            "This section reports retained evidence for the exact assessed repository state and does not infer unavailable client evidence.",
            f"- {marker}: retained source evidence remains bound to the exact assessed commit and report snapshot.",
            "- Human review remains required before any final approval or client delivery authorization.",
            f"Document page {index} of {len(sections)}",
        ):
            pdf.drawString(42, y, line)
            y -= 18
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_intake_mirrors_display_names_into_retained_report_evidence_without_mutation():
    from nico.comprehensive_intake_display_metadata_v2 import (
        _human_evidence_with_display_metadata,
    )

    original = {
        "modules": {
            "stakeholder_context": {
                "evidence": {
                    "primary_technical_contact": "Alex Reviewer",
                    "access_method": "read-only API",
                }
            }
        }
    }
    projected = _human_evidence_with_display_metadata(
        original,
        client_name="Acme Client",
        project_name="Atlas Project",
    )

    evidence = projected["modules"]["stakeholder_context"]["evidence"]
    assert evidence["customer_name"] == "Acme Client"
    assert evidence["project_name"] == "Atlas Project"
    assert evidence["primary_technical_contact"] == "Alex Reviewer"
    assert "customer_name" not in original["modules"]["stakeholder_context"]["evidence"]
    assert "project_name" not in original["modules"]["stakeholder_context"]["evidence"]


def test_isolated_report_worker_recovers_missing_identity_display_names_from_retained_evidence():
    from nico.comprehensive_report_worker_runtime_v90 import _report_identity

    context = {
        "run_id": "comprun_worker_metadata_fixture",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger-worker-metadata-fixture",
        "customer_id": "scope-customer",
        "project_id": "scope-project",
        "human_evidence": {
            "modules": {
                "stakeholder_context": {
                    "evidence": {
                        "customer_name": "Acme Client",
                        "project_name": "Atlas Project",
                        "primary_technical_contact": "Alex Reviewer",
                    }
                }
            }
        },
    }

    identity = _report_identity(context)
    assert identity["customer_name"] == "Acme Client"
    assert identity["project_name"] == "Atlas Project"
    assert identity["primary_technical_contact"] == "Alex Reviewer"
    assert identity["customer_id"] == "scope-customer"
    assert identity["project_id"] == "scope-project"


def test_sparse_report_reflow_compacts_literal_hyphen_bullets_without_dropping_text():
    from nico.comprehensive_pdf_reflow_v1 import compact_sparse_stage_pages

    source = _sparse_report_pdf()
    source_pages = len(PdfReader(io.BytesIO(source)).pages)
    compacted, manifest = compact_sparse_stage_pages(source)
    reader = PdfReader(io.BytesIO(compacted))
    rendered = "\n".join(str(page.extract_text() or "") for page in reader.pages)

    assert source_pages == 4
    assert manifest["status"] == "compacted"
    assert manifest["truth_preserved"] is True
    assert manifest["canonical_truth_mutated"] is False
    assert manifest["final_pages"] < source_pages
    assert len(reader.pages) == manifest["final_pages"]
    for marker in (
        "- ARCH-EVIDENCE-ALPHA",
        "- DELIVERY-EVIDENCE-BRAVO",
        "- REQUIREMENTS-EVIDENCE-CHARLIE",
        "- HISTORY-EVIDENCE-DELTA",
    ):
        assert marker in rendered


def test_report_reflow_removes_footer_only_spill_pages() -> None:
    from nico.comprehensive_pdf_reflow_v1 import compact_sparse_stage_pages

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    header = "NICO Comprehensive · comprun_footer_fixture · AUTOMATED DRAFT"
    pdf.drawString(42, 760, header)
    pdf.drawString(42, 720, "Repository and Delivery Evidence")
    pdf.drawString(42, 690, "Exact-SHA repository evidence retained.")
    pdf.drawString(42, 36, "Document page 1 of 3")
    pdf.showPage()
    pdf.drawString(42, 760, header)
    pdf.drawString(42, 36, "Document page 2 of 3")
    pdf.showPage()
    pdf.drawString(42, 760, header)
    pdf.drawString(42, 720, "Human Review and Acceptance Gate")
    pdf.drawString(42, 690, "Human approval remains pending.")
    pdf.drawString(42, 36, "Document page 3 of 3")
    pdf.save()

    compacted, manifest = compact_sparse_stage_pages(buffer.getvalue())
    reader = PdfReader(io.BytesIO(compacted))
    rendered = "\n".join(str(page.extract_text() or "") for page in reader.pages)

    assert len(reader.pages) == 2
    assert manifest["status"] == "compacted"
    assert manifest["pages_removed"] == 1
    assert manifest["footer_only_pages_removed"] == 1
    assert manifest["truth_preserved"] is True
    assert "Repository and Delivery Evidence" in rendered
    assert "Human Review and Acceptance Gate" in rendered
