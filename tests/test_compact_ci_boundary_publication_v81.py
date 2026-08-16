from __future__ import annotations

import base64
import inspect
import io
from collections.abc import Iterable

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

from nico import client_report_completion_v2 as completion
from nico.client_pdf_compose_v2 import compose_compact_client_pdf
from nico.comprehensive_ci_boundary_compat_v74 import ci_cd_boundary_markers
from nico.comprehensive_client_ready_projection_v1 import MAX_CLIENT_PDF_PAGES
from nico.comprehensive_rendered_ci_boundary_producer_v79 import _boundary_pdf_page


_EN_REVIEW_TITLES = (
    "Functional QA",
    "Platform Parity",
    "Historical Trends and Change Failure",
    "Requirements Traceability",
    "Stakeholder and Business Alignment",
    "Risk Reduction and Executive Briefing",
    "Six-Month Roadmap",
    "Staffing, Sequencing, and Cost",
)
_ES_REVIEW_TITLES = (
    "QA funcional",
    "Paridad de plataformas",
    "Tendencias históricas y fallos de cambio",
    "Trazabilidad de requisitos",
    "Alineación comercial y de partes interesadas",
    "Reducción de riesgo y resumen ejecutivo",
    "Hoja de ruta de seis meses",
    "Personal, secuencia y costo",
)


def _pdf_pages(lines: Iterable[str]) -> bytes:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    story = []
    values = list(lines)
    for index, line in enumerate(values):
        story.append(Paragraph(line, styles["BodyText"]))
        if index < len(values) - 1:
            story.append(PageBreak())
    SimpleDocTemplate(buffer, pagesize=letter, invariant=1).build(story)
    return buffer.getvalue()


def _register() -> dict:
    return {
        "summary": {
            "finding_population_reconciled": True,
            "semantic_duplicate_code_anchors_absent": True,
            "scanner_configuration_errors_promoted_to_code_findings": False,
            "unverified_tls_candidates_promoted_to_p1": False,
            "stable_alias_projection_idempotent": True,
            "decision_finding_count": 0,
            "scanner_configuration_issue_count": 0,
        },
        "code_findings": [],
    }


@pytest.mark.parametrize(
    ("spanish", "language", "status", "review_titles"),
    (
        (False, "en", "AUTOMATED DRAFT", _EN_REVIEW_TITLES),
        (True, "es-MX", "BORRADOR AUTOMATIZADO", _ES_REVIEW_TITLES),
    ),
)
def test_direct_compact_finalizer_binds_ci_boundary_after_review_rebuild(
    monkeypatch: pytest.MonkeyPatch,
    spanish: bool,
    language: str,
    status: str,
    review_titles: tuple[str, ...],
) -> None:
    canonical = {
        "report_language": language,
        "identity": {
            "repository": "example/product",
            "run_id": f"comprun_compact_ci_{language}",
            "report_language": language,
        },
        "assessment": {
            "report_language": language,
            "sections": [],
        },
        "canonical_findings": [],
        "client_finding_remediation_register": _register(),
    }
    rebuilt_markdown = "\n\n".join(
        (
            "# Evaluación Técnica Integral NICO"
            if spanish
            else "# NICO Comprehensive Technical Assessment",
            status,
            *(f"## {title}\n\nEvidence retained." for title in review_titles),
        )
    ) + "\n"
    base_pdf = _pdf_pages(("Core report body",))
    package = {
        "json": canonical,
        "markdown": "legacy markdown",
        "html": "legacy html",
        "pdf_base64": base64.b64encode(base_pdf).decode("ascii"),
        "premium_report_renderer": {},
        "phase17_artifact_rebuild": {},
        "client_report_completion": {},
    }

    monkeypatch.setattr(completion, "prepare_client_report_package", lambda value: dict(value))
    monkeypatch.setattr(
        completion.legacy,
        "finalize_client_report_package",
        lambda value: dict(value),
    )
    monkeypatch.setattr(completion, "normalize_client_assessment_truth", lambda value: dict(value))
    monkeypatch.setattr(completion, "_install_register", lambda value: value)
    monkeypatch.setattr(completion, "reconcile_authoritative_scanner_truth", lambda value: value)
    monkeypatch.setattr(completion, "apply_automated_draft_truth", lambda value: value)
    monkeypatch.setattr(completion.legacy, "_is_spanish", lambda value: spanish)
    monkeypatch.setattr(
        completion,
        "compact_client_markdown",
        lambda markdown, canonical, register, *, spanish: "compact body without CI/CD\n",
    )
    monkeypatch.setattr(
        completion,
        "merge_review_companion_markdown",
        lambda markdown, canonical, *, spanish: rebuilt_markdown,
    )
    monkeypatch.setattr(
        completion,
        "render_client_html",
        lambda markdown, title, *, spanish: f"<html><body>{markdown}</body></html>",
    )
    monkeypatch.setattr(
        completion,
        "render_comprehensive_review_companion_pdf",
        lambda canonical, *, spanish: _pdf_pages(("Review companion",)),
    )
    monkeypatch.setattr(
        completion,
        "render_compact_finding_register_pdf",
        lambda register, *, spanish: _pdf_pages(("Finding register",)),
    )
    monkeypatch.setattr(
        completion,
        "render_evidence_review_gate_pdf",
        lambda canonical, register, *, spanish: _pdf_pages(("Human review gate",)),
    )
    monkeypatch.setattr(completion, "sanitize_client_pdf_status", lambda value: value)

    core_finalize = inspect.unwrap(completion.finalize_client_report_package)
    result = core_finalize(package)
    pdf = base64.b64decode(result["pdf_base64"])
    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    markers = ci_cd_boundary_markers(result["json"], spanish=spanish)

    for marker in markers:
        assert marker in result["markdown"]
        assert marker in result["html"]
        assert marker in extracted
    assert result["client_report_completion"]["ci_cd_boundary_bound_after_review_companion"] is True
    assert result["client_report_completion"]["ci_cd_boundary_reserved_in_pdf_budget"] is True
    assert result["client_report_completion"]["four_part_ci_cd_boundary_in_markdown"] is True
    assert result["client_report_completion"]["four_part_ci_cd_boundary_in_html"] is True
    assert result["client_report_completion"]["four_part_ci_cd_boundary_in_pdf"] is True
    assert len(PdfReader(io.BytesIO(pdf)).pages) <= MAX_CLIENT_PDF_PAGES


def test_compact_pdf_reserves_ci_boundary_when_base_body_fills_page_budget() -> None:
    canonical = {
        "report_language": "en",
        "identity": {
            "repository": "example/product",
            "run_id": "comprun_compact_ci_budget",
            "report_language": "en",
        },
        "assessment": {"report_language": "en", "sections": []},
    }
    base_pdf = _pdf_pages(
        f"Primary decision body {index}"
        for index in range(1, MAX_CLIENT_PDF_PAGES + 1)
    )
    review_pdf = _pdf_pages(f"Review page {index}" for index in range(1, 9))
    register_pdf = _pdf_pages(("Finding register",))
    gate_pdf = _pdf_pages(("Human review gate",))
    ci_boundary_pdf = _boundary_pdf_page(canonical, spanish=False)

    pdf = compose_compact_client_pdf(
        base_pdf,
        register_pdf,
        gate_pdf,
        review_pdf=review_pdf,
        ci_boundary_pdf=ci_boundary_pdf,
    )
    reader = PdfReader(io.BytesIO(pdf))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert len(reader.pages) == MAX_CLIENT_PDF_PAGES
    assert "A. CI/CD configuration maturity:" in extracted
    assert "D. Historical workflow outcomes" in extracted
    assert "Review page 8" in extracted
    assert "Finding register" in extracted
    assert "Human review gate" in extracted
