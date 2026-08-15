from __future__ import annotations

import base64
import io

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.comprehensive_ci_operational_truth_v71 import (
    ci_cd_boundary_lines,
    ci_cd_boundary_markers,
    inject_ci_boundaries_into_review_sections,
    repair_ci_operational_markdown,
    validate_ci_boundary_surfaces,
)


def _canonical(language: str = "en") -> dict:
    return {
        "report_language": language,
        "locale": language,
        "identity": {"report_language": language},
        "assessment": {
            "report_language": language,
            "sections": [
                {
                    "id": "ci_cd",
                    "score": 93,
                    "presented_score": 93,
                    "score_contract": {
                        "exact_configuration_match": True,
                        "score_inputs": {
                            "explicit_permissions_present": True,
                            "configuration_controls": {
                                "build": True,
                                "test": True,
                                "security": True,
                            },
                        },
                    },
                    "operational_health": {
                        "workflow_run_count": 100,
                        "outcome_taxonomy": {
                            "success": 86,
                            "failure": 5,
                            "cancelled": 0,
                            "skipped": 0,
                            "timed_out": 0,
                            "unknown": 9,
                        },
                    },
                }
            ],
        },
        "ci_operational_context": {
            "workflow_run_count": 100,
            "outcome_taxonomy": {
                "success": 86,
                "failure": 5,
                "cancelled": 0,
                "skipped": 0,
                "timed_out": 0,
                "unknown": 9,
            },
        },
    }


def _pdf_base64(lines: list[str]) -> str:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, invariant=1)
    y = 760
    for line in lines:
        pdf.drawString(36, y, line)
        y -= 18
    pdf.showPage()
    pdf.save()
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_english_four_part_ci_boundary_is_complete() -> None:
    lines = ci_cd_boundary_lines(_canonical(), spanish=False)
    assert len(lines) == 4
    assert lines[0].startswith("A. CI/CD configuration maturity:")
    assert lines[1].startswith("B. Current operational readiness:")
    assert lines[2].startswith("C. Required-check health:")
    assert lines[3].startswith("D. Historical workflow outcomes")
    assert "success=86" in lines[3]
    assert "cancelled=0" in lines[3]
    assert "observed=100" in lines[3]


def test_spanish_four_part_ci_boundary_is_complete() -> None:
    lines = ci_cd_boundary_lines(_canonical("es-MX"), spanish=True)
    assert len(lines) == 4
    assert lines[0].startswith("A. Madurez de configuración de CI/CD:")
    assert lines[1].startswith("B. Preparación operativa actual:")
    assert lines[2].startswith("C. Estado de las verificaciones requeridas:")
    assert lines[3].startswith("D. Resultados históricos de los flujos de trabajo")
    assert "correctas=86" in lines[3]
    assert "canceladas=0" in lines[3]
    assert "observadas=100" in lines[3]


def test_compact_markdown_repair_replaces_generic_ci_section_with_four_boundaries() -> None:
    source = """# Report\n\n## CI/CD Operational Readiness and Historical Health\n\nold text\n\n## Human Review and Acceptance Gate\n"""
    repaired = repair_ci_operational_markdown(source, _canonical(), spanish=False)
    for marker in ci_cd_boundary_markers(_canonical(), spanish=False):
        assert marker in repaired
    assert "old text" not in repaired


def test_review_companion_historical_section_retains_four_boundaries() -> None:
    sections = [
        {
            "id": "historical_trends_and_change_failure",
            "evidence": ["Existing evidence"],
        }
    ]
    repaired = inject_ci_boundaries_into_review_sections(
        sections, _canonical(), spanish=False
    )
    evidence = repaired[0]["evidence"]
    assert evidence[:4] == ci_cd_boundary_lines(_canonical(), spanish=False)
    assert evidence[-1] == "Existing evidence"


def test_final_surface_validation_requires_boundary_d_independently() -> None:
    canonical = _canonical()
    lines = ci_cd_boundary_lines(canonical, spanish=False)
    result = {
        "json": canonical,
        "markdown": "\n".join(lines),
        "html": "<html><body>" + "<br>".join(lines) + "</body></html>",
        "pdf_base64": _pdf_base64(lines),
    }
    validation = validate_ci_boundary_surfaces(result)
    assert validation["four_part_ci_cd_boundary_in_markdown"] is True
    assert validation["four_part_ci_cd_boundary_in_html"] is True
    assert validation["four_part_ci_cd_boundary_in_pdf"] is True

    missing_d = lines[:3]
    broken = {
        **result,
        "markdown": "\n".join(missing_d),
        "html": "<html><body>" + "<br>".join(missing_d) + "</body></html>",
        "pdf_base64": _pdf_base64(missing_d),
    }
    with pytest.raises(ValueError, match="Historical workflow outcomes"):
        validate_ci_boundary_surfaces(broken)


def test_spanish_surface_validator_uses_spanish_markers() -> None:
    canonical = _canonical("es-MX")
    lines = ci_cd_boundary_lines(canonical, spanish=True)
    result = {
        "json": canonical,
        "markdown": "\n".join(lines),
        "html": "<html lang='es-MX'><body>" + "<br>".join(lines) + "</body></html>",
        "pdf_base64": _pdf_base64(lines),
    }
    validation = validate_ci_boundary_surfaces(result)
    assert validation["report_language"] == "es-MX"
    extracted = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(base64.b64decode(result["pdf_base64"]))).pages
    )
    assert "D. Resultados históricos de los flujos de trabajo" in extracted
