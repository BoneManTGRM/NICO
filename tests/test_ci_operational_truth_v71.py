from __future__ import annotations

from nico import client_report_completion_v2 as completion
from nico.comprehensive_ci_operational_truth_v71 import (
    install_ci_operational_truth_v71,
    repair_ci_operational_markdown,
)
from nico.comprehensive_report_semantic_content_gate_v66 import (
    validate_retained_decision_content,
)
from nico.comprehensive_spanish_review_candidate_truth_v70 import (
    install_spanish_review_candidate_truth_v70,
)


def _canonical(*, language: str) -> dict:
    ci_context = {
        "successful_workflow_runs": 86,
        "non_successful_workflow_runs": 4,
        "jobs_observed": 22,
        "observed_job_success_rate": 1.0,
        "deployments_observed": 10,
        "successful_deployments": 5,
        "non_successful_deployments": 3,
    }
    review_summary = {
        "review_required_total": 636,
        "verified_material_total": 0,
    }
    return {
        "report_language": language,
        "locale": language,
        "identity": {"report_language": language},
        "assessment": {
            "report_language": language,
            "review_candidate_summary": dict(review_summary),
            "ci_operational_context": dict(ci_context),
        },
        "review_candidate_summary": dict(review_summary),
        "ci_operational_context": dict(ci_context),
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


def _install_producer_repairs() -> None:
    install_spanish_review_candidate_truth_v70()
    install_ci_operational_truth_v71()


def test_spanish_compact_report_renders_candidate_and_ci_operational_truth() -> None:
    _install_producer_repairs()
    canonical = _canonical(language="es-MX")

    markdown = completion.compact_client_markdown(
        "# Evaluación Técnica Integral NICO\n\n## Estado de entrega\n",
        canonical,
        _empty_register(),
        spanish=True,
    )

    assert markdown.count("## Registro de candidatos que requieren revisión") == 1
    assert "Candidatos que requieren revisión: 636" in markdown
    assert "Hallazgos materiales confirmados: 0" in markdown
    assert markdown.count("## Preparación operativa y salud histórica de CI/CD") == 1
    assert "Ejecuciones de flujo exitosas: 86" in markdown
    assert "Ejecuciones de flujo no exitosas: 4" in markdown
    assert "Trabajos observados: 22" in markdown
    assert "Tasa de éxito observada de trabajos: 100.0%" in markdown
    assert "Despliegues observados: 10" in markdown
    assert "permanece separada de la madurez de configuración" in markdown

    validation = validate_retained_decision_content(
        {
            "report_language": "es-MX",
            "json": canonical,
            "markdown": markdown,
            "html": f"<html lang='es-MX'><body>{markdown}</body></html>",
        }
    )
    assert validation["review_candidate_truth_present"] is True
    assert validation["ci_operational_context_rendered"] is True
    assert validation["ci_configuration_separation_rendered"] is True


def test_english_compact_report_renders_current_candidate_and_ci_operational_truth() -> None:
    _install_producer_repairs()
    canonical = _canonical(language="en")

    markdown = completion.compact_client_markdown(
        "# NICO Comprehensive Technical Assessment\n\n## Delivery Status\n",
        canonical,
        _empty_register(),
        spanish=False,
    )

    assert markdown.count("## Review-Required Candidate Register") == 1
    assert "Review-required candidates: 636" in markdown
    assert "Confirmed material findings: 0" in markdown
    assert (
        "Score effect: assurance-only while authorized human disposition remains "
        "pending; NICO automated technical triage is complete."
    ) in markdown
    assert "assurance-only until triaged" not in markdown
    assert markdown.count("## CI/CD Operational Readiness and Historical Health") == 1
    assert "Successful workflow runs: 86" in markdown
    assert "Non-success workflow runs: 4" in markdown
    assert "Observed job success rate: 100.0%" in markdown
    assert "remains separate from configuration maturity" in markdown

    validation = validate_retained_decision_content(
        {
            "report_language": "en",
            "json": canonical,
            "markdown": markdown,
            "html": f"<html lang='en'><body>{markdown}</body></html>",
        }
    )
    assert validation["review_candidate_truth_present"] is True
    assert validation["superseded_review_candidate_score_effect_absent"] is True
    assert validation["ci_operational_context_rendered"] is True
    assert validation["ci_configuration_separation_rendered"] is True


def test_ci_operational_repair_replaces_stale_section_once() -> None:
    canonical = _canonical(language="es-MX")
    stale = "\n".join(
        [
            "# Evaluación",
            "## Preparación operativa y salud histórica de CI/CD",
            "- valor obsoleto: 1",
            "## Puerta de revisión humana y aceptación",
        ]
    )

    repaired = repair_ci_operational_markdown(stale, canonical, spanish=True)
    repaired_twice = repair_ci_operational_markdown(repaired, canonical, spanish=True)

    assert repaired_twice.count("## Preparación operativa y salud histórica de CI/CD") == 1
    assert "valor obsoleto" not in repaired_twice
    assert "Ejecuciones de flujo exitosas: 86" in repaired_twice


def test_ci_operational_repair_leaves_report_unchanged_without_context() -> None:
    source = "# Report\n\n## Delivery Status\n"
    canonical = {
        "report_language": "en",
        "assessment": {},
    }
    assert repair_ci_operational_markdown(
        source,
        canonical,
        spanish=False,
    ) == source
