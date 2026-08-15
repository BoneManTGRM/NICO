from __future__ import annotations

import base64
import html
import io
import re

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico import comprehensive_rendered_ci_boundary_producer_v79 as producer
from nico import comprehensive_rendered_ci_boundary_truth_v78 as truth_v78
from nico import v2_premium_evidence_appendix as appendix
from nico import v2_premium_report_renderer as renderer

_EN_MARKERS = (
    "A. CI/CD configuration maturity:",
    "B. Current operational readiness:",
    "C. Required-check health:",
    "D. Historical workflow outcomes",
)
_ES_MARKERS = (
    "A. Madurez de configuración de CI/CD:",
    "B. Preparación operativa actual:",
    "C. Estado de las verificaciones requeridas:",
    "D. Resultados históricos de los flujos de trabajo",
)


def _pdf_bytes(lines: tuple[str, ...] = ("Base report",)) -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    y = 740
    for line in lines:
        document.drawString(54, y, line)
        y -= 18
    document.save()
    return buffer.getvalue()


def _canonical(
    *,
    language: str = "en",
    request_language: str | None = None,
    spanish_content: bool = False,
) -> dict[str, object]:
    canonical: dict[str, object] = {
        "report_language": language,
        "identity": {
            "repository": "acme/api",
            "commit_sha": "abc123",
            "run_id": "comprun_fixture",
            "generated_at": "2026-01-01T00:00:00Z",
            "evidence_ledger_id": "ledger_fixture",
        },
        "assessment": {
            "report_language": language,
            "sections": [],
            "executive_summary": (
                "La evaluación técnica conserva los hallazgos y requiere "
                "aprobación humana antes de la entrega al cliente."
                if spanish_content
                else "The technical assessment requires human review."
            ),
        },
        "stage_summaries": [],
        "canonical_findings": [],
        "findings_register": [],
        "roadmap": [],
        "staffing_plan": [],
        "scanner_execution_records": [],
        "workflow_health": {},
    }
    if request_language:
        canonical["request_metadata"] = {
            "report_language": request_language,
        }
    return canonical


def _package(
    *,
    canonical: dict[str, object],
    spanish: bool,
    pdf_lines: tuple[str, ...] = ("Base report",),
) -> dict[str, object]:
    markdown = (
        "# Evaluación Técnica Integral NICO\n\n"
        "## Resumen ejecutivo\n\n"
        "La evaluación técnica conserva la evidencia y requiere revisión.\n"
        if spanish
        else "# NICO Comprehensive Technical Assessment\n\n"
        "## Executive Decision Brief\n\n"
        "The assessment retains evidence and requires review.\n"
    )
    return {
        "json": canonical,
        "markdown": markdown,
        "html": f"<html><body><p>{html.escape(markdown)}</p></body></html>",
        "pdf_base64": base64.b64encode(_pdf_bytes(pdf_lines)).decode("ascii"),
    }


def _html_text(value: object) -> str:
    return " ".join(
        html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).split()
    )


def _pdf_text(encoded: object) -> str:
    pdf = base64.b64decode(str(encoded), validate=True)
    return " ".join(
        "\n".join(
            page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
        ).split()
    )


def _assert_markers_on_every_surface(
    result: dict[str, object],
    *,
    desired: tuple[str, ...],
    opposite: tuple[str, ...],
) -> None:
    surfaces = (
        str(result["markdown"]),
        _html_text(result["html"]),
        _pdf_text(result["pdf_base64"]),
    )
    for surface in surfaces:
        assert all(marker in surface for marker in desired)
        assert not all(marker in surface for marker in opposite)


def test_repairs_english_markdown_html_and_pdf_before_final_gate() -> None:
    result = producer.repair_rendered_ci_boundary(
        _package(canonical=_canonical(), spanish=False)
    )

    _assert_markers_on_every_surface(
        result,
        desired=_EN_MARKERS,
        opposite=_ES_MARKERS,
    )
    truth = truth_v78.rendered_ci_boundary_truth(result)
    assert truth["language"] == "en"
    assert all(
        truth["per_surface"][surface]["english"]["complete"] is True
        for surface in ("markdown", "html", "pdf")
    )
    assert result["pdf_page_count"] == 2


def test_request_spanish_is_promoted_before_render_and_repaired_everywhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_v78.install_comprehensive_rendered_ci_boundary_truth_v78()
    observed: dict[str, object] = {}

    def fake_renderer(package: dict[str, object]) -> dict[str, object]:
        canonical = package["json"]
        assert isinstance(canonical, dict)
        observed["language"] = canonical.get("report_language")
        return _package(canonical=canonical, spanish=True)

    monkeypatch.setattr(renderer, "rebuild_premium_client_artifacts", fake_renderer)
    monkeypatch.setattr(appendix, "rebuild_premium_client_artifacts", fake_renderer)

    installation = producer.install_comprehensive_rendered_ci_boundary_producer_v79()
    result = renderer.rebuild_premium_client_artifacts(
        {
            "json": _canonical(
                language="en",
                request_language="es-MX",
                spanish_content=True,
            )
        }
    )

    assert installation["bound"] is True
    assert (
        renderer.rebuild_premium_client_artifacts
        is appendix.rebuild_premium_client_artifacts
    )
    assert observed["language"] == "es-MX"
    canonical = result["json"]
    assert isinstance(canonical, dict)
    assert canonical["report_language"] == "es-MX"
    _assert_markers_on_every_surface(
        result,
        desired=_ES_MARKERS,
        opposite=_EN_MARKERS,
    )


def test_rendered_spanish_overrides_a_synthesized_root_english_default() -> None:
    result = producer.repair_rendered_ci_boundary(
        _package(
            canonical=_canonical(language="en", spanish_content=True),
            spanish=True,
        )
    )

    canonical = result["json"]
    assert isinstance(canonical, dict)
    assert canonical["report_language"] == "es-MX"
    _assert_markers_on_every_surface(
        result,
        desired=_ES_MARKERS,
        opposite=_EN_MARKERS,
    )


def test_complete_opposite_language_pdf_fails_closed() -> None:
    package = _package(
        canonical=_canonical(
            language="en",
            request_language="es-MX",
            spanish_content=True,
        ),
        spanish=True,
        pdf_lines=_EN_MARKERS,
    )
    truth_v78.install_comprehensive_rendered_ci_boundary_truth_v78()

    with pytest.raises(
        ValueError,
        match="opposite-language CI/CD boundary",
    ):
        producer.repair_rendered_ci_boundary(package)
