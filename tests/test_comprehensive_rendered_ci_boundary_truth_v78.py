from __future__ import annotations

import base64
import io

import pytest
from pypdf import PdfWriter

from nico import comprehensive_ci_boundary_compat_v74 as ci_v74
from nico import comprehensive_client_truth_final_v1 as final_truth
from nico import comprehensive_rendered_ci_boundary_truth_v78 as truth_v78
from nico import comprehensive_report_language_truth_v77 as language_v77

_TIMESTAMP = "2026-08-15T18:30:00Z"
_SPANISH_SUMMARY = (
    "Se recomienda conservar la evidencia exacta y formalizar la gobernanza de CI/CD."
)
_ENGLISH_SUMMARY = (
    "Preserve exact evidence and formalize CI/CD governance before client delivery."
)


def _blank_pdf_base64() -> str:
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return base64.b64encode(output.getvalue()).decode("ascii")


def _boundary(*, spanish: bool) -> str:
    canonical = {
        "report_language": "es-MX" if spanish else "en",
        "assessment": {"sections": []},
    }
    return "\n".join(
        ci_v74.ci_cd_boundary_lines(canonical, spanish=spanish)
    )


def _package(
    boundary: str,
    *,
    canonical_language: str,
    summary: str,
    request_language: str | None = None,
) -> dict[str, object]:
    canonical: dict[str, object] = {
        "report_language": canonical_language,
        "identity": {"generated_at": _TIMESTAMP},
        "assessment": {
            "executive_summary": summary,
            "sections": [],
        },
    }
    if request_language:
        canonical["request_metadata"] = {"report_language": request_language}
    markdown = f"{_TIMESTAMP}\n\n{summary}\n\n{boundary}\n"
    rendered_html = (
        f"<article><time>{_TIMESTAMP}</time><p>{summary}</p>"
        f"<pre>{boundary}</pre></article>"
    )
    return {
        "json": canonical,
        "markdown": markdown,
        "html": rendered_html,
        "pdf_base64": _blank_pdf_base64(),
    }


def test_request_spanish_overrides_synthesized_root_english() -> None:
    canonical = {
        "report_language": "en",
        "request_metadata": {"report_language": "es-MX"},
    }

    assert truth_v78.resolve_report_language(canonical) == "es-MX"
    assert language_v77.resolve_report_language(canonical) == "es-MX"


def test_exact_production_failure_stale_english_with_spanish_boundary_passes() -> None:
    result = _package(
        _boundary(spanish=True),
        canonical_language="en",
        summary=_SPANISH_SUMMARY,
    )

    final_truth._validate_surfaces(result)

    canonical = result["json"]
    assert isinstance(canonical, dict)
    assert canonical["report_language"] == "es-MX"
    contract = canonical["v2_prepublication_contract"]
    assert isinstance(contract, dict)
    assert contract["rendered_ci_boundary_language"] == "es-MX"
    assert contract["rendered_ci_boundary_overrode_canonical_language"] is True


def test_complete_english_boundary_still_passes() -> None:
    result = _package(
        _boundary(spanish=False),
        canonical_language="en",
        summary=_ENGLISH_SUMMARY,
    )

    final_truth._validate_surfaces(result)

    canonical = result["json"]
    assert isinstance(canonical, dict)
    assert canonical["report_language"] == "en"


def test_complete_spanish_boundary_is_detected_from_html_text() -> None:
    boundary = _boundary(spanish=True)
    result = {
        "markdown": "",
        "html": "<div>" + boundary.replace("\n", "</div><div>") + "</div>",
    }

    truth = truth_v78.rendered_ci_boundary_truth(result)

    assert truth["language"] == "es-MX"
    assert truth["complete"] is True
    assert truth["per_surface"]["html"]["spanish"]["complete"] is True


def test_complete_bilingual_boundaries_fail_closed() -> None:
    result = _package(
        _boundary(spanish=True) + "\n" + _boundary(spanish=False),
        canonical_language="en",
        summary=_SPANISH_SUMMARY,
    )

    with pytest.raises(
        ValueError,
        match="complete English and Spanish CI/CD boundaries",
    ):
        final_truth._validate_surfaces(result)


def test_incomplete_spanish_boundary_fails_with_spanish_missing_marker() -> None:
    incomplete = "\n".join(_boundary(spanish=True).splitlines()[:3])
    result = _package(
        incomplete,
        canonical_language="en",
        summary=_SPANISH_SUMMARY,
    )

    with pytest.raises(
        ValueError,
        match="D. Resultados históricos de los flujos de trabajo",
    ):
        final_truth._validate_surfaces(result)
