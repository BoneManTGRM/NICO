from __future__ import annotations

from nico.comprehensive_review_candidate_compat_v76 import _has_exact_h2
from nico.comprehensive_review_candidate_publication_v75 import (
    _EN_HEADING,
    _ES_HEADING,
)
from nico.comprehensive_spanish_review_candidate_truth_v70 import (
    repair_english_review_candidate_markdown,
    repair_spanish_review_candidate_markdown,
)


def _canonical(language: str) -> dict:
    summary = {
        "review_required_total": 636,
        "verified_material_total": 0,
    }
    return {
        "report_language": language,
        "locale": language,
        "identity": {"report_language": language},
        "assessment": {
            "report_language": language,
            "review_candidate_summary": dict(summary),
        },
        "review_candidate_summary": dict(summary),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_legacy_spanish_alias_preserves_summary_and_repairs_truth() -> None:
    source = "\n".join(
        [
            "# Evaluación",
            "## Resumen del paquete de evidencia",
            "",
            "Resumen general conservado.",
            "- Candidatos pendientes de revisión: 12",
            "- Hallazgos materiales confirmados: 4",
            "- Efecto en puntuación: solo aseguramiento hasta completar la revisión.",
            "",
            "## Puerta de revisión humana y aceptación",
        ]
    )

    repaired = repair_spanish_review_candidate_markdown(
        source,
        _canonical("es-MX"),
    )

    assert repaired.count("## Resumen del paquete de evidencia") == 1
    assert "Resumen general conservado." in repaired
    assert repaired.count(_ES_HEADING) == 1
    assert "Candidatos que requieren revisión: 636" in repaired
    assert "Hallazgos materiales confirmados: 0" in repaired
    assert "Candidatos pendientes de revisión" not in repaired
    assert "solo aseguramiento hasta completar la revisión" not in repaired


def test_legacy_spanish_alias_leaves_english_report_unchanged() -> None:
    source = "## Evidence Package Summary\n\nEnglish evidence.\n"
    assert repair_spanish_review_candidate_markdown(
        source,
        _canonical("en"),
    ) == source


def test_legacy_english_alias_preserves_summary_and_repairs_truth() -> None:
    source = "\n".join(
        [
            "# Report",
            "## Evidence Package Summary",
            "",
            "General evidence retained.",
            "- Review-required candidates: 12",
            "- Confirmed material findings: 4",
            "- Score effect: assurance-only until triaged.",
            "",
            "## Human Review and Acceptance Gate",
        ]
    )

    repaired = repair_english_review_candidate_markdown(
        source,
        _canonical("en"),
    )

    assert repaired.count("## Evidence Package Summary") == 1
    assert "General evidence retained." in repaired
    assert repaired.count(_EN_HEADING) == 1
    assert "Review-required candidates: 636" in repaired
    assert "Confirmed material findings: 0" in repaired
    assert "assurance-only until triaged" not in repaired


def test_heading_detection_requires_an_exact_h2_line() -> None:
    source = (
        "This paragraph mentions ## Review-Required Candidate Register inline, "
        "but it is not a section heading."
    )
    assert _has_exact_h2(source, _EN_HEADING) is False
    assert _has_exact_h2(source, _ES_HEADING) is False
    assert _has_exact_h2(f"{_EN_HEADING}\nbody", _EN_HEADING) is True
