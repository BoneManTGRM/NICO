from __future__ import annotations

import pytest

from nico import client_report_completion_v2 as completion
from nico.comprehensive_review_candidate_publication_v75 import (
    repair_review_candidate_publication,
    validate_review_candidate_surfaces,
)
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts


SHA = "6" * 40
GENERATED_AT = "2026-08-15T19:55:00Z"


def _canonical(language: str = "es-MX") -> dict:
    review_summary = {
        "review_required_total": 636,
        "verified_material_total": 0,
        "by_category": {
            "static": {
                "raw": 636,
                "material": 0,
                "review_required": 636,
            }
        },
    }
    return {
        "service_id": "comprehensive",
        "report_language": language,
        "locale": language,
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": SHA,
            "run_id": "comprun_review_candidate_v75",
            "evidence_ledger_id": "ledger-review-candidate-v75",
            "customer_id": "customer-review-candidate-v75",
            "project_id": "project-review-candidate-v75",
            "generated_at": GENERATED_AT,
            "report_language": language,
        },
        "generated_at": GENERATED_AT,
        "review_candidate_summary": dict(review_summary),
        "assessment": {
            "report_language": language,
            "technical_score": 84,
            "canonical_evidence_adjusted_score": 82,
            "review_candidate_summary": dict(review_summary),
            "maturity_signal": {
                "level": "Strong",
                "score": 84,
                "presented_score": 84,
            },
            "sections": [
                {
                    "id": "architecture",
                    "label": "Architecture & Technical Debt",
                    "status": "verified",
                    "presented_status": "verified",
                    "score": 82,
                    "presented_score": 82,
                    "summary": "Architecture evidence is decision ready.",
                    "evidence": [
                        "Module boundaries and complexity were measured."
                    ],
                }
            ],
            "unavailable_data_notes": [],
        },
        "canonical_findings": [
            {
                "finding_id": "RISK-P1-REVIEW-CANDIDATE",
                "priority": "P1",
                "category": "architecture",
                "title": "Reduce complexity in page.tsx",
                "location": "apps/web/app/page.tsx:100",
                "business_impact": "Regression risk is concentrated.",
                "recommendation": "Split the module into bounded components.",
                "status": "open",
            }
        ],
        "scanner_execution_records": [
            {
                "scanner_name": "bandit",
                "state": "completed_with_findings",
                "status": "completed_with_findings",
                "completed": True,
                "verified": True,
                "exact_commit_match": True,
                "artifact_hash": "b" * 64,
                "findings": [{"test_id": "B101"}],
            }
        ],
        "roadmap": [
            {
                "window": "0-30 days",
                "objective": "Remove the highest-risk delivery constraints.",
                "work_packages": [
                    {
                        "work_package_id": "WP-001",
                        "title": "Decompose page.tsx",
                        "owner_role": "Product Engineer",
                        "effort": "M",
                    }
                ],
            }
        ],
        "stage_summaries": [],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _package(language: str = "es-MX") -> dict:
    return {"json": _canonical(language)}


def _empty_register() -> dict:
    return {
        "code_findings": [],
        "operational_findings": [],
        "summary": {
            "exact_source_code_finding_count": 0,
            "operational_or_context_finding_count": 0,
        },
    }


def test_spanish_repair_preserves_evidence_summary_and_adds_dedicated_truth() -> None:
    source = "\n".join(
        [
            "# Evaluación Técnica Integral NICO",
            "",
            "## Resumen del paquete de evidencia",
            "",
            "El PDF conserva decisiones y evidencia estructurada.",
            "- Candidatos pendientes de revisión: 636",
            "- Hallazgos materiales confirmados: 0",
            "- Efecto en puntuación: solo aseguramiento hasta completar la revisión.",
            "",
            "## Puerta de revisión humana y aceptación",
        ]
    )

    repaired = repair_review_candidate_publication(
        source,
        _canonical("es-MX"),
        spanish=True,
    )

    assert repaired.count("## Resumen del paquete de evidencia") == 1
    assert repaired.count("## Registro de candidatos que requieren revisión") == 1
    assert "Candidatos que requieren revisión: 636" in repaired
    assert "Hallazgos materiales confirmados: 0" in repaired
    assert (
        "Efecto en puntuación: solo aseguramiento mientras la disposición humana "
        "siga pendiente; el triaje técnico de NICO está completo."
    ) in repaired
    assert "Candidatos pendientes de revisión" not in repaired
    assert "solo aseguramiento hasta completar la revisión" not in repaired


def test_late_bound_spanish_compact_producer_is_self_sufficient() -> None:
    markdown = completion.compact_client_markdown(
        "# Evaluación Técnica Integral NICO\n\n## Estado de entrega\n",
        _canonical("es-MX"),
        _empty_register(),
        spanish=True,
    )

    assert "## Resumen del paquete de evidencia" in markdown
    assert "## Registro de candidatos que requieren revisión" in markdown
    assert "Candidatos que requieren revisión: 636" in markdown
    assert "Candidatos pendientes de revisión" not in markdown
    assert "solo aseguramiento hasta completar la revisión" not in markdown


def test_late_bound_english_compact_producer_uses_current_truth() -> None:
    markdown = completion.compact_client_markdown(
        "# NICO Comprehensive Technical Assessment\n\n## Delivery Status\n",
        _canonical("en"),
        _empty_register(),
        spanish=False,
    )

    assert "## Evidence Package Summary" in markdown
    assert "## Review-Required Candidate Register" in markdown
    assert "Review-required candidates: 636" in markdown
    assert (
        "Score effect: assurance-only while authorized human disposition remains "
        "pending; NICO automated technical triage is complete."
    ) in markdown
    assert "assurance-only until triaged" not in markdown


def test_spanish_full_artifact_pipeline_retains_candidate_truth() -> None:
    result = rebuild_client_artifacts(_package("es-MX"))

    assert result["status"] == "review_required"
    assert "## Resumen del paquete de evidencia" in result["markdown"]
    assert "## Registro de candidatos que requieren revisión" in result["markdown"]
    assert "Candidatos que requieren revisión: 636" in result["markdown"]
    assert "Hallazgos materiales confirmados: 0" in result["markdown"]
    assert "Registro de candidatos que requieren revisión" in result["html"]
    assert "Candidatos que requieren revisión: 636" in result["html"]
    assert "Candidatos pendientes de revisión" not in result["markdown"]
    assert "solo aseguramiento hasta completar la revisión" not in result["markdown"]
    contract = result["client_report_completion"]
    assert contract["review_candidate_truth_in_markdown"] is True
    assert contract["review_candidate_truth_in_html"] is True
    assert contract["stale_review_candidate_copy_absent"] is True


def test_final_surface_validator_checks_markdown_and_html_independently() -> None:
    canonical = _canonical("es-MX")
    markdown = repair_review_candidate_publication(
        "# Evaluación\n\n## Estado de entrega\n",
        canonical,
        spanish=True,
    )
    result = {
        "json": canonical,
        "markdown": markdown,
        "html": "<html><body>" + markdown.replace("\n", "<br>") + "</body></html>",
    }
    validation = validate_review_candidate_surfaces(result)
    assert validation["review_candidate_truth_in_markdown"] is True
    assert validation["review_candidate_truth_in_html"] is True

    broken = {
        **result,
        "html": "<html><body>missing candidate section</body></html>",
    }
    with pytest.raises(
        ValueError,
        match="review-candidate truth in html",
    ):
        validate_review_candidate_surfaces(broken)
