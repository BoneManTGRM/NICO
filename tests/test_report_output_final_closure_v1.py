from __future__ import annotations

import base64
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


def _shared_section_page_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    width, height = letter
    pdf.drawString(42, height - 54, "NICO Comprehensive")
    pdf.drawString(42, height - 78, "Comprehensive Technical Assessment")
    pdf.showPage()

    y = height - 54
    for line in (
        "NICO Comprehensive | AUTOMATED DRAFT · PENDING HUMAN APPROVAL",
        "Code audit",
        "STRONG · 96/100",
        "Executable code-risk findings: 0.",
        "Dependency / Library Ecosystem",
        "PROVISIONAL STRONG — HUMAN REVIEW REQUIRED · 96/100",
        "Review-required candidates: 21.",
        "Secrets Exposure Review",
        "PROVISIONAL STRONG — HUMAN REVIEW REQUIRED · 96/100",
        "Review-required candidates: 19.",
    ):
        pdf.drawString(42, y, line)
        y -= 18
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _report_identity() -> dict[str, str]:
    return {
        "run_id": "comprun_metadata_proof",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_metadata_proof",
        "customer_id": "customer_canonical_scope",
        "project_id": "project_canonical_scope",
        "customer_name": "Acme Client",
        "project_name": "Atlas Project",
        "primary_technical_contact": "Alex Reviewer",
    }


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
    import nico.comprehensive_report_review_integrity_v1 as integrity
    from nico.comprehensive_final_worker_pdf_reflow_v1 import (
        _install_display_metadata_fallback,
    )

    _install_display_metadata_fallback()
    record = {
        "identity": {
            "customer_id": "scope-customer",
            "project_id": "scope-project",
        },
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

    values = integrity._display_values(record)
    assert values == {
        "customer_name": "Acme Client",
        "project_name": "Atlas Project",
        "primary_technical_contact": "Alex Reviewer",
    }
    assert record["identity"]["customer_id"] == "scope-customer"
    assert record["identity"]["project_id"] == "scope-project"


def test_report_package_preserves_display_metadata_in_canonical_truth_and_rendered_artifacts():
    from nico.comprehensive_report_package import build_comprehensive_report_package

    built = build_comprehensive_report_package(
        identity=_report_identity(),
        stage_results={},
    )
    assert built["status"] == "complete"
    report = built["report_package"]
    canonical_identity = report["json"]["identity"]

    assert canonical_identity["customer_id"] == "customer_canonical_scope"
    assert canonical_identity["project_id"] == "project_canonical_scope"
    assert canonical_identity["customer_name"] == "Acme Client"
    assert canonical_identity["project_name"] == "Atlas Project"
    assert canonical_identity["primary_technical_contact"] == "Alex Reviewer"

    assert "Client display name: Acme Client" in report["markdown"]
    assert "Project display name: Atlas Project" in report["markdown"]
    assert "Primary technical contact: Alex Reviewer" in report["markdown"]
    assert "Acme Client" in report["html"]
    assert "Atlas Project" in report["html"]
    assert "Alex Reviewer" in report["html"]

    pdf_bytes = base64.b64decode(report["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf_bytes))
    rendered = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Customer Acme Client" in rendered
    assert "Project Atlas Project" in rendered
    assert "customer_canonical_scope" not in rendered
    assert "project_canonical_scope" not in rendered

    executive_page = reader.pages[1].extract_text() or ""
    assert "Executive Decision Brief" in executive_page
    assert "Priority Constraints and Decision Risks" in executive_page


def test_client_evidence_summary_projects_primary_contact_from_preserved_canonical_identity():
    import nico.comprehensive_report_review_integrity_v1 as integrity
    import nico.v2_premium_report_renderer as renderer
    from nico.comprehensive_report_package import _pdf, build_comprehensive_report_package

    integrity._install_required_report_sections()
    built = build_comprehensive_report_package(
        identity=_report_identity(),
        stage_results={},
    )
    canonical = built["report_package"]["json"]
    stages = renderer._canonical_stages(canonical)
    client_summary = next(
        item for item in stages if item.get("stage_id") == "client_evidence_summary"
    )
    evidence = "\n".join(client_summary.get("evidence") or [])
    assert "Client display name: Acme Client" in evidence
    assert "Project display name: Atlas Project" in evidence
    assert "Primary technical contact: Alex Reviewer" in evidence

    pdf_base64, pdf_error, _ = _pdf(
        dict(canonical["identity"]),
        dict(canonical["assessment"]),
        stages,
        built["generated_at"],
    )
    assert pdf_error is None
    rendered = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(base64.b64decode(pdf_base64))).pages
    )
    assert "Alex Reviewer" in rendered


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


def test_compacted_shared_page_keeps_every_semantic_section_in_toc_and_bookmarks():
    from nico.comprehensive_semantic_navigation_v1 import semantic_renumber_and_outline

    rendered = semantic_renumber_and_outline(_shared_section_page_pdf())
    reader = PdfReader(io.BytesIO(rendered))
    assert len(reader.pages) == 3
    toc = reader.pages[1].extract_text() or ""
    for title in (
        "Code Audit",
        "Dependency / Library Ecosystem",
        "Secrets Exposure Review",
    ):
        assert title in toc

    flattened_outline = " ".join(str(item) for item in reader.outline)
    assert "Code Audit" in flattened_outline
    assert "Dependency / Library Ecosystem" in flattened_outline
    assert "Secrets Exposure Review" in flattened_outline
