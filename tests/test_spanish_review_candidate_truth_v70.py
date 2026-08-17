from __future__ import annotations

from pathlib import Path

from nico import client_report_completion_v2 as completion
from nico.comprehensive_report_semantic_content_gate_v66 import (
    validate_retained_decision_content,
)
from nico.comprehensive_spanish_review_candidate_truth_v70 import (
    install_spanish_review_candidate_truth_v70,
    repair_spanish_review_candidate_markdown,
)

ROOT = Path(__file__).resolve().parents[1]


def _canonical(*, language: str = "es-MX") -> dict:
    return {
        "report_language": language,
        "locale": language,
        "identity": {"report_language": language},
        "assessment": {
            "report_language": language,
            "review_candidate_summary": {
                "review_required_total": 636,
                "verified_material_total": 0,
            },
        },
        "review_candidate_summary": {
            "review_required_total": 636,
            "verified_material_total": 0,
        },
        "canonical_findings": [],
        "architecture_hotspots": [],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _empty_register() -> dict:
    return {
        "code_findings": [],
        "operational_findings": [],
        "summary": {
            "exact_source_code_finding_count": 0,
            "operational_or_context_finding_count": 0,
        },
    }


def test_real_compact_spanish_producer_emits_required_candidate_truth() -> None:
    installation = install_spanish_review_candidate_truth_v70()
    canonical = _canonical()

    markdown = completion.compact_client_markdown(
        "# Evaluación Técnica Integral NICO\n\n## Estado de entrega\n",
        canonical,
        _empty_register(),
        spanish=True,
    )

    assert installation["bound"] is True
    assert "## Registro de candidatos que requieren revisión" in markdown
    assert "Candidatos que requieren revisión: 636" in markdown
    assert "Hallazgos materiales confirmados: 0" in markdown
    assert (
        "Efecto en puntuación: solo aseguramiento mientras la disposición humana "
        "siga pendiente; el triaje técnico de NICO está completo."
    ) in markdown
    assert "Candidatos pendientes de revisión" not in markdown
    assert "solo aseguramiento hasta completar la revisión" not in markdown

    validation = validate_retained_decision_content(
        {
            "report_language": "es-MX",
            "json": canonical,
            "markdown": markdown,
            "html": f"<html lang='es-MX'><body>{markdown}</body></html>",
        }
    )
    assert validation["review_required_candidate_count_rendered"] == 636
    assert validation["confirmed_material_candidate_count_rendered"] == 0
    assert validation["review_candidate_truth_present"] is True
    assert validation["superseded_review_candidate_score_effect_absent"] is True


def test_repair_replaces_stale_spanish_section_deterministically() -> None:
    stale = "\n".join(
        [
            "# Evaluación",
            "## Resumen del paquete de evidencia",
            "",
            "- Candidatos pendientes de revisión: 12",
            "- Hallazgos materiales confirmados: 4",
            "- Efecto en puntuación: solo aseguramiento hasta completar la revisión.",
            "",
            "## Puerta de revisión humana y aceptación",
        ]
    )

    repaired = repair_spanish_review_candidate_markdown(stale, _canonical())

    assert repaired.count("## Registro de candidatos que requieren revisión") == 1
    assert "Candidatos que requieren revisión: 636" in repaired
    assert "Hallazgos materiales confirmados: 0" in repaired
    assert "Candidatos pendientes de revisión" not in repaired
    assert "solo aseguramiento hasta completar la revisión" not in repaired


def test_english_markdown_is_unchanged() -> None:
    source = "## Evidence Package Summary\n\n- Review-required candidates: 636\n"
    assert repair_spanish_review_candidate_markdown(
        source,
        _canonical(language="en"),
    ) == source


def test_failure_stage_badge_is_compact_and_never_wraps_on_mobile() -> None:
    css = (ROOT / "apps/web/styles/assessment-failure-terminal.css").read_text()

    assert ".nico-failure-evidence__stages .result-head > .status" in css
    assert "white-space: nowrap" in css
    assert "word-break: normal" in css
    assert "overflow-wrap: normal" in css
    assert "max-width: none" in css
    assert "font-size: 10px" in css
    assert "padding: 5px 8px" in css
