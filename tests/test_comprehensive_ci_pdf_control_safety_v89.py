from __future__ import annotations

import io

from pypdf import PdfReader

from nico import comprehensive_ci_pdf_control_safety_v89 as v89
from nico import comprehensive_rendered_ci_boundary_producer_v79 as producer


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


def _canonical(language: str) -> dict[str, object]:
    return {
        "report_language": language,
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "f14441c866bf26626c3ec00cd5c537f0bce8b63a",
            "run_id": "comprun_pdf_control_fixture",
            "generated_at": "2026-08-19T00:00:00Z",
            "evidence_ledger_id": "ledger_pdf_control_fixture",
            "report_language": language,
        },
        "assessment": {
            "report_language": language,
            "service_id": "comprehensive",
            "sections": [],
        },
        "ci_operational_context": {
            "successful_workflow_runs": 80,
            "failed_workflow_runs": 10,
            "unknown_workflow_runs": 10,
            "workflow_runs_observed": 100,
            "jobs_observed": 37,
            "deployments_observed": 10,
            "successful_deployments": 5,
            "non_successful_deployments": 4,
        },
    }


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def test_v89_binds_exact_ci_boundary_pdf_producer() -> None:
    installation = v89.install_comprehensive_ci_pdf_control_safety_v89()

    assert installation["bound"] is True
    assert installation["del_control_glyph_sanitized"] is True
    assert installation["text_operands_only"] is True
    assert producer._boundary_pdf_page is v89._boundary_pdf_page_v89


def test_exact_production_ci_boundary_del_glyph_is_removed_without_losing_truth() -> None:
    v89.install_comprehensive_ci_pdf_control_safety_v89()
    original = v89._ORIGINAL_BOUNDARY_PDF_PAGE
    assert original is not None

    raw = original(_canonical("en"), spanish=False)
    raw_text = _pdf_text(raw)
    assert "\x7f" in raw_text

    repaired = producer._boundary_pdf_page(_canonical("en"), spanish=False)
    repaired_text = _pdf_text(repaired)

    assert "\x7f" not in repaired_text
    assert all(marker in repaired_text for marker in _EN_MARKERS)
    assert all(marker not in repaired_text for marker in _ES_MARKERS)


def test_spanish_ci_boundary_is_control_safe_and_keeps_spanish_truth() -> None:
    v89.install_comprehensive_ci_pdf_control_safety_v89()

    repaired = producer._boundary_pdf_page(_canonical("es-MX"), spanish=True)
    repaired_text = _pdf_text(repaired)

    assert "\x7f" not in repaired_text
    assert all(marker in repaired_text for marker in _ES_MARKERS)
    assert all(marker not in repaired_text for marker in _EN_MARKERS)


def test_clean_pdf_bytes_are_not_rewritten() -> None:
    original = v89._ORIGINAL_BOUNDARY_PDF_PAGE
    if original is None:
        v89.install_comprehensive_ci_pdf_control_safety_v89()
        original = v89._ORIGINAL_BOUNDARY_PDF_PAGE
    assert original is not None

    raw = original(_canonical("en"), spanish=False)
    clean = v89.sanitize_ci_pdf_control_glyphs(raw)
    clean_again = v89.sanitize_ci_pdf_control_glyphs(clean)

    assert "\x7f" not in _pdf_text(clean)
    assert clean_again == clean
