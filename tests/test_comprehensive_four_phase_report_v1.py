from __future__ import annotations

import base64
import hashlib
import io
import json
from copy import deepcopy

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.comprehensive_four_phase_report_v1 import (
    apply_four_phase_pdf,
    apply_four_phase_program,
    build_four_phase_program,
    finalize_four_phase_report_package,
    install_comprehensive_four_phase_report_v1,
    repair_four_phase_markdown,
)


def _canonical(*, language: str = "en") -> dict:
    return {
        "identity": {
            "repository": "example/repository",
            "commit_sha": "a" * 40,
            "run_id": "comprun_test",
            "customer_id": "customer_test",
            "project_id": "project_test",
            "evidence_ledger_id": "ledger_test",
            "report_language": language,
        },
        "locale": language,
        "report_language": language,
        "assessment_state": "review_required",
        "review_package_ready": True,
        "human_review_completed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "completed_applicable_analyzers": 9,
        "incomplete_applicable_analyzers": 0,
        "decision_content_limitations": ["runtime evidence not supplied"],
        "lifecycle": {
            "review_package_ready": True,
            "human_review_status": "pending",
            "client_delivery_allowed": False,
        },
        "assessment": {
            "canonical_scanner_finding_register": {
                "technical_triage": {
                    "technical_triage_coverage_pct": 100.0,
                    "human_review_work_units": 12,
                    "candidates_requiring_individual_human_attention": 7,
                    "grouped_review_eligible_candidates": 5,
                    "grouped_human_review_clusters": 2,
                }
            }
        },
    }


def _pdf() -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    titles = [
        "NICO Comprehensive",
        "Table of Contents",
        "Review-Required Candidate Register",
        "Functional QA",
        "Historical Trends and Change Failure",
        "Human Review and Acceptance Gate",
    ]
    for index, title in enumerate(titles, 1):
        page.setFont("Helvetica-Bold", 18)
        page.drawString(54, 730, title)
        page.setFont("Helvetica", 8)
        page.drawString(54, 40, f"Document page {index} of {len(titles)}")
        page.showPage()
    page.save()
    return buffer.getvalue()


def _package(canonical: dict) -> dict:
    return {
        "json": canonical,
        "markdown": "# NICO Comprehensive\n\n## Executive Decision Brief\n\nBody.\n",
        "html": "<html><body>Body.</body></html>",
        "pdf_base64": base64.b64encode(_pdf()).decode("ascii"),
        "client_report_completion": {},
    }


def _canonical_payload_digest(canonical: dict) -> str:
    payload = deepcopy(canonical)
    payload.pop("artifacts", None)
    payload.pop("artifact_manifest", None)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_four_phase_program_preserves_truth_boundaries() -> None:
    program = build_four_phase_program(_canonical())
    assert program["phase_count"] == 4
    assert [item["phase"] for item in program["phases"]] == [1, 2, 3, 4]
    assert program["phases"][0]["status"] == "complete"
    assert program["phases"][1]["status"] == "ready_pending_human_decision"
    assert program["phases"][2]["status"] == "complete_with_disclosed_limitations"
    assert program["phases"][3]["status"] == (
        "blocked_pending_authorized_human_approval"
    )
    assert program["human_review_required"] is True
    assert program["client_delivery_allowed"] is False


def test_four_phase_markdown_is_bilingual_and_idempotent() -> None:
    english = apply_four_phase_program(_canonical())
    english_markdown = repair_four_phase_markdown(
        "# NICO Comprehensive\n\n## Executive Decision Brief\n\nBody.\n",
        english,
    )
    assert english_markdown.count("## Four-Phase Assessment Program") == 1
    for title in (
        "Automated Technical Triage",
        "Human Review by Exception",
        "Broader Professional Assessment",
        "Approval and Client Delivery",
    ):
        assert title in english_markdown
    assert "CLIENT DELIVERY BLOCKED" in english_markdown
    assert repair_four_phase_markdown(english_markdown, english) == english_markdown

    spanish = apply_four_phase_program(_canonical(language="es-MX"))
    spanish_markdown = repair_four_phase_markdown(
        "# NICO Integral\n\n## Resumen ejecutivo\n\nContenido.\n",
        spanish,
    )
    assert spanish_markdown.count("## Programa de evaluación en cuatro fases") == 1
    for title in (
        "Triaje técnico automatizado",
        "Revisión humana por excepción",
        "Evaluación profesional ampliada",
        "Aprobación y entrega al cliente",
    ):
        assert title in spanish_markdown
    assert "ENTREGA AL CLIENTE BLOQUEADA" in spanish_markdown


def test_four_phase_pdf_updates_toc_without_changing_page_count() -> None:
    canonical = apply_four_phase_program(_canonical())
    original = _pdf()
    rendered = apply_four_phase_pdf(original, canonical)
    original_reader = PdfReader(io.BytesIO(original))
    rendered_reader = PdfReader(io.BytesIO(rendered))
    assert len(rendered_reader.pages) == len(original_reader.pages)
    toc_text = rendered_reader.pages[1].extract_text() or ""
    assert "FOUR-PHASE ASSESSMENT PROGRAM" in toc_text
    assert "Automated Technical Triage" in toc_text
    assert "Human Review by Exception" in toc_text
    assert "Broader Professional Assessment" in toc_text
    assert "Approval and Client Delivery" in toc_text
    outline_titles: list[str] = []

    def collect(items: list) -> None:
        for item in items:
            if isinstance(item, list):
                collect(item)
            else:
                outline_titles.append(str(getattr(item, "title", item)))

    collect(rendered_reader.outline)
    assert "Four-Phase Assessment Program" in outline_titles
    assert "Automated Technical Triage" in outline_titles
    assert apply_four_phase_pdf(rendered, canonical) == rendered


def test_finalizer_publishes_all_four_phases_across_surfaces() -> None:
    result = finalize_four_phase_report_package(_package(_canonical()))
    assert result["json"]["four_phase_program"]["phase_count"] == 4
    assert result["client_report_completion"]["all_four_phases_present"] is True
    assert (
        result["client_report_completion"][
            "phase4_human_approval_boundary_preserved"
        ]
        is True
    )
    assert result["client_delivery_allowed"] is False
    assert result["pdf_page_count"] == 6
    assert result["pdf_sha256"]
    assert result["markdown_sha256"]
    assert result["html_sha256"]

    second = finalize_four_phase_report_package(deepcopy(result))
    assert second["pdf_sha256"] == result["pdf_sha256"]
    assert second["markdown_sha256"] == result["markdown_sha256"]
    assert second["html_sha256"] == result["html_sha256"]


def test_finalizer_rebinds_canonical_json_artifact_digest_after_phase_insertion() -> None:
    canonical = _canonical()
    canonical["artifacts"] = [
        {
            "artifact_type": "canonical_json",
            "sha256": "stale-before-four-phase-publication",
            "digest_scope": (
                "canonical_truth_payload_excluding_artifact_self_reference"
            ),
        }
    ]
    canonical["artifact_manifest"] = {
        "artifact_schema": "nico.comprehensive-artifact-manifest.v1",
        "artifacts": deepcopy(canonical["artifacts"]),
    }

    result = finalize_four_phase_report_package(_package(canonical))
    expected = _canonical_payload_digest(result["json"])

    assert result["json"]["artifacts"][0]["sha256"] == expected
    assert (
        result["json"]["artifact_manifest"]["artifacts"][0]["sha256"]
        == expected
    )
    assert result["json"]["four_phase_program"]["phase_count"] == 4
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False

    second = finalize_four_phase_report_package(deepcopy(result))
    assert second == result


def test_installer_publishes_before_exact_artifact_manifest_binding() -> None:
    from nico import comprehensive_artifact_manifest_approval_v1 as manifest

    state = install_comprehensive_four_phase_report_v1()
    assert state["bound"] is True
    assert state["publication_precedes_exact_artifact_binding"] is True

    result = manifest.attach_artifact_manifest(_package(_canonical()))
    canonical = result["json"]
    assert canonical["four_phase_program"]["phase_count"] == 4
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False

    pdf = base64.b64decode(result["pdf_base64"])
    pdf_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(pdf)).pages
    )
    for title in (
        "Automated Technical Triage",
        "Human Review by Exception",
        "Broader Professional Assessment",
        "Approval and Client Delivery",
    ):
        assert title in result["markdown"]
        assert title in result["html"]
        assert title in pdf_text

    contents = {
        "findings_csv": result["findings_csv"].encode("utf-8"),
        "evidence_csv": result["evidence_csv"].encode("utf-8"),
        "candidate_register_json": result["candidate_register_json"].encode(
            "utf-8"
        ),
        "remediation_backlog_json": result["remediation_backlog_json"].encode(
            "utf-8"
        ),
        "markdown_report": result["markdown"].encode("utf-8"),
        "html_report": result["html"].encode("utf-8"),
        "comprehensive_pdf": pdf,
        "canonical_json": result["canonical_json"].encode("utf-8"),
    }
    for entry in result["artifact_manifest"]["artifacts"]:
        artifact_type = entry["artifact_type"]
        assert artifact_type in contents
        content = contents[artifact_type]
        assert hashlib.sha256(content).hexdigest() == entry["sha256"]
        assert len(content) == entry["size_bytes"]

    manifest_json = result["evidence_manifest_json"].encode("utf-8")
    assert (
        hashlib.sha256(manifest_json).hexdigest()
        == result["evidence_manifest_sha256"]
    )
