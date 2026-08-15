from __future__ import annotations

from nico import client_report_completion_v1 as legacy_report
from nico import comprehensive_ci_boundary_compat_v74 as ci_v74
from nico import comprehensive_ci_operational_truth_v71 as ci_truth
from nico import comprehensive_client_truth_final_v1 as final_truth
from nico import comprehensive_report_language_truth_v77 as language_truth
from nico import comprehensive_review_candidate_publication_v75 as publication
from nico import comprehensive_spanish_review_candidate_truth_v70 as legacy_candidate


def _spanish_canonical() -> dict[str, object]:
    return {
        "assessment": {
            "executive_summary": (
                "Se recomienda formalizar la gobernanza de CI/CD y conservar "
                "la evidencia exacta del repositorio evaluado."
            ),
            "sections": [],
        }
    }


def test_output_language_alias_is_authoritative() -> None:
    canonical = {"output_language": "es-MX"}

    assert language_truth.resolve_report_language(canonical) == "es-MX"
    assert language_truth.normalize_report_language_metadata(canonical)[
        "report_language"
    ] == "es-MX"


def test_nested_artifact_language_alias_is_supported() -> None:
    canonical = {"request_metadata": {"artifact_language": "Spanish"}}

    assert language_truth.resolve_report_language(canonical) == "es-MX"


def test_spanish_canonical_copy_recovers_missing_language_metadata() -> None:
    canonical = _spanish_canonical()

    assert language_truth.resolve_report_language(canonical) == "es-MX"
    assert legacy_report._is_spanish(canonical)
    assert legacy_candidate._is_spanish(canonical)
    assert publication._is_spanish(canonical)
    assert ci_v74._is_spanish(canonical, False)
    assert ci_truth._is_spanish(canonical, False)
    assert final_truth._report_language(canonical) == "es-MX"


def test_explicit_english_overrides_spanish_copy() -> None:
    canonical = _spanish_canonical()
    canonical["report_language"] = "en"

    assert language_truth.resolve_report_language(canonical) == "en"
    assert not legacy_report._is_spanish(canonical)
    assert not publication._is_spanish(canonical)
    assert not ci_v74._is_spanish(canonical, False)


def test_ci_boundary_producers_use_one_spanish_decision() -> None:
    canonical = _spanish_canonical()

    final_lines = final_truth._ci_lines(canonical)
    operational_lines = ci_truth.ci_cd_boundary_lines(canonical, spanish=False)

    assert final_lines[0].startswith("A. Madurez de configuración de CI/CD:")
    assert operational_lines[0].startswith(
        "A. Madurez de configuración de CI/CD:"
    )
    assert not final_lines[0].startswith("A. CI/CD configuration maturity:")


def test_explicit_spanish_override_flag_remains_supported() -> None:
    assert ci_v74._is_spanish({}, True)
    assert publication._is_spanish({}, True)


def test_complete_rendered_spanish_boundary_recovers_language() -> None:
    canonical = _spanish_canonical()
    markdown = "\n".join(
        ci_v74.ci_cd_boundary_lines(canonical, spanish=True)
    )

    assert (
        language_truth.rendered_boundary_language({"markdown": markdown})
        == "es-MX"
    )


def test_conflicting_complete_boundaries_are_detected() -> None:
    spanish = "\n".join(
        ci_v74.ci_cd_boundary_lines(_spanish_canonical(), spanish=True)
    )
    english = "\n".join(
        ci_v74.ci_cd_boundary_lines({"report_language": "en"}, spanish=False)
    )

    assert language_truth.rendered_boundary_language(
        {"markdown": f"{spanish}\n{english}"}
    ) == "conflict"
