from __future__ import annotations

import io
from copy import deepcopy
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.comprehensive_commercial_ship_projection_v3 import (
    compact_sparse_limitation_pages,
    project_canonical_for_client_presentation,
)


def _canonical_fixture() -> dict:
    return {
        "identity": {
            "run_id": "comprun_dynamic_fixture",
            "repository": "example/repository",
            "commit_sha": "a" * 40,
        },
        "stage_summaries": [
            {
                "stage_id": "requirements_traceability",
                "title": "Requirements Traceability",
                "status": "complete",
                "summary": "The processing pass completed.",
                "evidence": [],
                "findings": [],
                "unavailable": [
                    "Authoritative stakeholder requirements were not supplied."
                ],
            },
            {
                "stage_id": "historical_trends_and_change_failure",
                "title": "Historical Trends and Change Failure",
                "status": "complete",
                "summary": "Historical processing completed.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Production incident history was unavailable."],
            },
            {
                "stage_id": "decision_report_generation",
                "title": "Core Decision Report",
                "status": "complete",
                "summary": "Core report generation completed.",
                "evidence": ["report_package.pdf_page_count: 37"],
                "findings": [],
                "unavailable": [],
            },
            {
                "stage_id": "deployment_and_infrastructure",
                "title": "Deployment and Infrastructure",
                "status": "complete",
                "summary": "Deployment evidence was collected.",
                "evidence": [
                    "Observed deployments: 17",
                    "Successful deployments: 11",
                    "Non-success deployments: 6",
                    "Non-success deployment classification: 2",
                ],
                "findings": [],
                "unavailable": [],
            },
        ],
    }


def test_projection_changes_only_client_presentation_truth() -> None:
    canonical = _canonical_fixture()
    before = deepcopy(canonical)

    projected = project_canonical_for_client_presentation(canonical)

    assert canonical == before
    stages = {item["stage_id"]: item for item in projected["stage_summaries"]}

    requirements = stages["requirements_traceability"]
    assert requirements["status"] == (
        "processing complete · authoritative requirements not supplied"
    )
    assert canonical["stage_summaries"][0]["status"] == "complete"

    history = stages["historical_trends_and_change_failure"]
    assert history["status"] == "processing complete · evidence limited"

    core = stages["decision_report_generation"]
    assert core["evidence"] == [
        "Core decision-report PDF page count: 37 "
        "(intermediate artifact; not final assembled report length)."
    ]
    assert "pdf_page_count" not in " ".join(core["evidence"])

    deployment = stages["deployment_and_infrastructure"]
    rendered = "\n".join(deployment["evidence"])
    assert "observed=17" in rendered
    assert "successful=11" in rendered
    assert "failed/non-success=2" in rendered
    assert "unresolved=4" in rendered
    assert "Non-success deployments: 6" not in rendered
    assert "Non-success deployment classification: 2" not in rendered


def test_deployment_projection_does_not_guess_failure_split() -> None:
    canonical = {
        "stage_summaries": [
            {
                "stage_id": "deployment_and_infrastructure",
                "title": "Deployment and Infrastructure",
                "status": "complete",
                "summary": "Deployment evidence was collected.",
                "evidence": [
                    "GitHub deployment evidence: observed=23, success=19, non-success=4."
                ],
                "findings": [],
                "unavailable": [],
            }
        ]
    }

    projected = project_canonical_for_client_presentation(canonical)
    text = "\n".join(projected["stage_summaries"][0]["evidence"])
    assert "observed=23" in text
    assert "successful=19" in text
    assert "failed/non-success=not separately evidenced" in text
    assert "unresolved=not separately evidenced" in text
    assert "failed-or-unresolved remainder=4" in text


def _pdf_with_sparse_limitation_pair() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)

    document.drawString(72, 740, "Canonical Technical Scorecard")
    document.drawString(72, 720, "Dense evidence page remains unchanged")
    document.showPage()

    document.drawString(72, 740, "Six-Month Roadmap")
    document.drawString(72, 710, "Unavailable or Limited Evidence")
    document.drawString(72, 690, "Validated roadmap evidence was not supplied.")
    document.showPage()

    document.drawString(72, 740, "Staffing, Sequencing, and Cost")
    document.drawString(72, 710, "Unavailable or Limited Evidence")
    document.drawString(72, 690, "Authoritative staffing assumptions were not supplied.")
    document.showPage()

    document.drawString(72, 740, "Human Review and Acceptance Gate")
    document.drawString(72, 720, "Human approval remains pending.")
    document.save()
    return buffer.getvalue()


def test_sparse_roadmap_staffing_pages_compact_without_losing_text() -> None:
    original = _pdf_with_sparse_limitation_pair()
    compacted, manifest = compact_sparse_limitation_pages(original)

    assert manifest["status"] == "compacted"
    assert manifest["original_pages"] == 4
    assert manifest["final_pages"] == 3
    assert manifest["pages_removed"] == 1
    assert manifest["truth_preserved"] is True

    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(compacted)).pages
    )
    assert "Six-Month Roadmap" in text
    assert "Validated roadmap evidence was not supplied." in text
    assert "Staffing, Sequencing, and Cost" in text
    assert "Authoritative staffing assumptions were not supplied." in text
    assert "Human Review and Acceptance Gate" in text


def _pdf_with_sparse_ordinary_sections() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    header = "NICO Comprehensive · comprun_dynamic_fixture · AUTOMATED DRAFT"
    sections = [
        ("Code audit", "Executable code-risk findings: 0."),
        ("Dependency / Library Ecosystem", "Review-required dependency candidates: 21."),
        ("Secrets Exposure Review", "Review-required secret candidates: 19."),
        ("Static Analysis", "Review-required static candidates: 664."),
        ("CI/CD Analysis", "Workflow configuration exact-SHA match: True."),
        ("Architecture & Technical Debt", "Complexity risk remains pending human review."),
        ("Velocity / Complexity", "Mutable activity volume remains unscored context."),
    ]
    for title, evidence in sections:
        document.drawString(54, 760, header)
        document.drawString(54, 720, title)
        document.drawString(54, 690, evidence)
        document.drawString(54, 670, "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED")
        document.showPage()

    document.drawString(54, 760, header)
    document.drawString(54, 720, "Human Review and Acceptance Gate")
    document.drawString(54, 690, "Only an authorized human reviewer may approve the exact artifact.")
    document.save()
    return buffer.getvalue()


def test_sparse_ordinary_sections_reflow_without_touching_review_gate() -> None:
    original = _pdf_with_sparse_ordinary_sections()
    compacted, manifest = compact_sparse_limitation_pages(original)

    assert manifest["status"] == "compacted"
    assert manifest["original_pages"] == 8
    assert manifest["final_pages"] < 8
    assert manifest["pages_removed"] >= 3
    assert manifest["truth_preserved"] is True
    assert manifest["canonical_truth_mutated"] is False

    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(compacted)).pages
    )
    for marker in (
        "Code audit",
        "Dependency / Library Ecosystem",
        "Secrets Exposure Review",
        "Static Analysis",
        "CI/CD Analysis",
        "Architecture & Technical Debt",
        "Velocity / Complexity",
        "Human Review and Acceptance Gate",
        "Only an authorized human reviewer may approve the exact artifact.",
    ):
        assert marker in text


def test_review_pdf_and_markdown_bridge_never_silently_noops() -> None:
    source = Path("apps/web/app/AssessmentReviewPdfDownload.tsx").read_text(
        encoding="utf-8"
    )

    assert 'window.open(href, "_blank", "noopener,noreferrer")' in source
    assert "window.location.assign(href)" in source
    assert "fetchMarkdown" in source
    assert "navigator.clipboard.writeText" in source
    assert 'document.execCommand("copy")' in source
    assert "Markdown copied." in source
    assert "Markdown could not be copied." in source
    assert "visibleRunId" in source


def test_real_runtime_and_renderer_install_report_metadata_integrity() -> None:
    production = Path("nico/api/same_run_locale_report_bootstrap.py").read_text(
        encoding="utf-8"
    )
    worker = Path("nico/api/final_report_worker_bootstrap.py").read_text(
        encoding="utf-8"
    )

    for source in (production, worker):
        assert "install_comprehensive_report_review_integrity_v1" in source
        assert "REPORT_REVIEW_INTEGRITY" in source
        assert "primary_technical_contact_projected_from_human_evidence" in source
        assert "client_delivery_allowed" in source

    assert "display_metadata_persisted_in_initial_canonical_write" in production
    assert '"report_review_integrity_bound": True' in worker
