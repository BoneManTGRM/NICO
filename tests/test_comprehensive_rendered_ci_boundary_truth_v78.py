from __future__ import annotations

import pytest

from nico import comprehensive_ci_boundary_compat_v74 as ci_v74
from nico import comprehensive_client_truth_final_v1 as final_truth
from nico import comprehensive_rendered_ci_boundary_truth_v78 as truth_v78
from nico import comprehensive_report_language_truth_v77 as language_v77


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
    request_language: str | None = None,
) -> dict[str, object]:
    canonical: dict[str, object] = {
        "report_language": canonical_language,
    }
    if request_language:
        canonical["request_metadata"] = {"report_language": request_language}
    return {
        "json": canonical,
        "markdown": boundary,
        "html": "",
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
    )

    truth = truth_v78.reconcile_rendered_ci_boundary_language(result)

    assert truth["language"] == "es-MX"
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
    )

    truth = truth_v78.reconcile_rendered_ci_boundary_language(result)

    assert truth["language"] == "en"
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
    )

    with pytest.raises(
        ValueError,
        match="complete English and Spanish CI/CD boundaries",
    ):
        truth_v78.reconcile_rendered_ci_boundary_language(result)


def test_incomplete_spanish_boundary_fails_with_spanish_missing_marker() -> None:
    incomplete = "\n".join(_boundary(spanish=True).splitlines()[:3])
    result = _package(
        incomplete,
        canonical_language="en",
    )

    with pytest.raises(
        ValueError,
        match="D. Resultados históricos de los flujos de trabajo",
    ):
        truth_v78.reconcile_rendered_ci_boundary_language(result)


def test_v78_wraps_the_final_publication_validator() -> None:
    installation = truth_v78.install_comprehensive_rendered_ci_boundary_truth_v78()

    assert installation["validator_bound"] is True
    assert getattr(
        final_truth._validate_surfaces,
        "_nico_rendered_ci_boundary_validator_v78",
        False,
    ) is True
