from __future__ import annotations

import base64
import io

import pytest
from reportlab.pdfgen import canvas

from nico import comprehensive_report_language_truth_v77 as language_truth
from nico import comprehensive_terminal_report_language_authority_v83 as terminal


def _split_marker(marker: str) -> tuple[str, str]:
    words = marker.split()
    assert len(words) >= 2
    return " ".join(words[:-1]), words[-1]


def _markdown(markers: tuple[str, ...]) -> str:
    lines: list[str] = []
    for marker in markers:
        first, second = _split_marker(marker)
        lines.extend((first, second, "evidence retained", ""))
    return "\n".join(lines)


def _html(markers: tuple[str, ...]) -> str:
    rows: list[str] = []
    for marker in markers:
        first, second = _split_marker(marker)
        rows.append(
            f"<p><span>{first}</span>\n<span>{second}</span> evidence retained</p>"
        )
    return "<html><body>" + "\n".join(rows) + "</body></html>"


def _pdf_base64(markers: tuple[str, ...]) -> str:
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    y = 760
    for marker in markers:
        first, second = _split_marker(marker)
        pdf.drawString(72, y, first)
        y -= 16
        pdf.drawString(72, y, second + " evidence retained")
        y -= 28
    pdf.save()
    return base64.b64encode(output.getvalue()).decode("ascii")


def _result(language: str, *, markdown_markers: tuple[str, ...] | None = None) -> dict:
    markers = (
        language_truth._ES_BOUNDARY_MARKERS
        if language == "es-MX"
        else language_truth._EN_BOUNDARY_MARKERS
    )
    return {
        "json": {
            "report_language": language,
            "locale": language,
            "identity": {
                "run_id": "comprun_terminal_ci_boundary_compat",
                "report_language": language,
            },
            "assessment": {
                "report_language": language,
                "locale": language,
            },
        },
        "markdown": _markdown(markdown_markers if markdown_markers is not None else markers),
        "html": _html(markers),
        "pdf_base64": _pdf_base64(markers),
    }


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_normalized_complete_surfaces_outrank_obsolete_raw_combined_marker_failure(
    language: str,
) -> None:
    result = _result(language)
    markers = (
        language_truth._ES_BOUNDARY_MARKERS
        if language == "es-MX"
        else language_truth._EN_BOUNDARY_MARKERS
    )

    def legacy_raw_validator(_result: dict) -> None:
        raise ValueError(f"client report omitted CI/CD boundary: {markers[0]}")

    validation = terminal._validate_with_legacy_ci_compat(
        legacy_raw_validator,
        result,
    )

    assert validation["authoritative_report_language"] == language
    assert validation["surface_coverage"]["markdown"]["complete"] is True
    assert validation["surface_coverage"]["html"]["complete"] is True
    assert validation["surface_coverage"]["pdf"]["complete"] is True
    assert validation["independent_markdown_html_pdf_validation"] is True
    assert validation["client_delivery_allowed"] is False


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_actual_missing_boundary_still_fails_closed_before_legacy_compat(
    language: str,
) -> None:
    markers = (
        language_truth._ES_BOUNDARY_MARKERS
        if language == "es-MX"
        else language_truth._EN_BOUNDARY_MARKERS
    )
    result = _result(language, markdown_markers=markers[1:])

    with pytest.raises(ValueError, match="CI/CD boundary in Markdown"):
        terminal._validate_with_legacy_ci_compat(lambda _result: None, result)


def test_non_ci_legacy_truth_failure_is_never_suppressed() -> None:
    result = _result("en")

    def legacy_truth_failure(_result: dict) -> None:
        raise ValueError("canonical generated_at does not match rendered surfaces")

    with pytest.raises(
        ValueError,
        match="canonical generated_at does not match rendered surfaces",
    ):
        terminal._validate_with_legacy_ci_compat(legacy_truth_failure, result)
