from __future__ import annotations

import base64
import io

import pytest
from reportlab.pdfgen import canvas

from nico import comprehensive_ci_boundary_compat_v74 as ci_v74
from nico import comprehensive_client_truth_final_v1 as final_truth
from nico import comprehensive_rendered_ci_boundary_truth_v78 as truth_v78
from nico import comprehensive_report_language_truth_v77 as language_v77


def _boundary(*, spanish: bool) -> tuple[str, ...]:
    canonical = {
        "report_language": "es-MX" if spanish else "en",
        "assessment": {"sections": []},
    }
    return ci_v74.ci_cd_boundary_markers(canonical, spanish=spanish)


def _pdf(lines: tuple[str, ...]) -> str:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, invariant=1)
    y = 760
    for line in lines:
        page.drawString(40, y, line)
        y -= 20
    page.save()
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _package(
    *,
    language: str,
    root_language: str | None = None,
    request_language: str | None = None,
    markers: tuple[str, ...] | None = None,
) -> dict[str, object]:
    spanish = language == "es-MX"
    values = markers or _boundary(spanish=spanish)
    canonical: dict[str, object] = {
        "report_language": root_language or language,
        "identity": {"report_language": language},
        "assessment": {"report_language": root_language or language},
    }
    if request_language:
        canonical["request_metadata"] = {"report_language": request_language}
    return {
        "json": canonical,
        "markdown": "\n".join(values),
        "html": "<p>" + "</p><p>".join(values) + "</p>",
        "pdf_base64": _pdf(values),
    }


def test_run_identity_spanish_overrides_synthesized_root_english() -> None:
    canonical = {
        "report_language": "en",
        "identity": {"report_language": "es-MX"},
    }

    assert truth_v78.resolve_report_language(canonical) == "es-MX"
    assert language_v77.resolve_report_language(canonical) == "es-MX"


def test_request_spanish_overrides_synthesized_root_english_without_run_identity() -> None:
    canonical = {
        "report_language": "en",
        "request_metadata": {"report_language": "es-MX"},
    }

    assert truth_v78.resolve_report_language(canonical) == "es-MX"
    assert language_v77.resolve_report_language(canonical) == "es-MX"


def test_exact_production_failure_stale_english_projection_uses_spanish_identity() -> None:
    result = _package(language="es-MX", root_language="en")

    truth = truth_v78.reconcile_rendered_ci_boundary_language(result)

    assert truth["language"] == "es-MX"
    assert truth["authority_source"] == "run_identity:report_language"
    canonical = result["json"]
    assert isinstance(canonical, dict)
    assert canonical["report_language"] == "es-MX"
    contract = canonical["v2_prepublication_contract"]
    assert isinstance(contract, dict)
    assert contract["authoritative_report_language"] == "es-MX"
    assert contract["rendered_artifact_is_language_authority"] is False
    assert contract["rendered_ci_boundary_overrode_canonical_language"] is False


def test_complete_english_boundaries_still_pass() -> None:
    result = _package(language="en")

    truth = truth_v78.reconcile_rendered_ci_boundary_language(result)

    assert truth["language"] == "en"
    assert truth["surface_coverage"]["markdown"]["complete"] is True
    assert truth["surface_coverage"]["html"]["complete"] is True
    assert truth["surface_coverage"]["pdf"]["complete"] is True


def test_rendered_truth_remains_diagnostic_not_authority() -> None:
    spanish = _boundary(spanish=True)
    result = {
        "markdown": "\n".join(spanish),
        "html": "<div>" + "</div><div>".join(spanish) + "</div>",
        "pdf_base64": _pdf(spanish),
    }

    truth = truth_v78.rendered_ci_boundary_truth(result)

    assert truth["language"] == "es-MX"
    assert truth["complete"] is True
    assert truth["per_surface"]["html"]["spanish"]["complete"] is True
    assert truth["rendered_artifact_is_language_authority"] is False


def test_spanish_package_with_english_structural_boundary_fails_closed() -> None:
    result = _package(language="es-MX")
    english = _boundary(spanish=False)
    result["html"] = str(result["html"]) + "<p>" + english[0] + "</p>"

    with pytest.raises(
        ValueError,
        match="contains en CI/CD boundary in HTML for authoritative es-MX report",
    ):
        truth_v78.reconcile_rendered_ci_boundary_language(result)


def test_incomplete_spanish_pdf_fails_with_language_surface_and_marker() -> None:
    spanish = _boundary(spanish=True)
    result = _package(language="es-MX")
    result["pdf_base64"] = _pdf(spanish[:3])

    with pytest.raises(
        ValueError,
        match=(
            r"client report omitted es-MX CI/CD boundary in PDF: "
            r"D\. Resultados históricos de los flujos de trabajo"
        ),
    ):
        truth_v78.reconcile_rendered_ci_boundary_language(result)


def test_rendered_spanish_cannot_override_authoritative_english_identity() -> None:
    spanish = _boundary(spanish=True)
    result = _package(language="en", markers=spanish)

    with pytest.raises(
        ValueError,
        match=r"client report omitted en CI/CD boundary in Markdown: A\. CI/CD configuration maturity:",
    ):
        truth_v78.reconcile_rendered_ci_boundary_language(result)


def test_v78_wraps_the_final_publication_validator() -> None:
    installation = truth_v78.install_comprehensive_rendered_ci_boundary_truth_v78()

    assert installation["validator_bound"] is True
    assert installation["rendered_ci_boundary_is_final_authority"] is False
    assert getattr(
        final_truth._validate_surfaces,
        "_nico_rendered_ci_boundary_validator_v78",
        False,
    ) is True
