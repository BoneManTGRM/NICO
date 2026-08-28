from __future__ import annotations

from nico import comprehensive_human_evidence_report_v1 as human_report
from nico import v2_premium_report_renderer as renderer
from nico.comprehensive_engagement_metadata_v1 import (
    build_comprehensive_engagement_metadata,
)
from nico.strategic_human_evidence_v1 import MODULES, normalize_strategic_human_evidence


def _human_input() -> dict[str, dict]:
    output: dict[str, dict] = {}
    for module_id, definition in MODULES.items():
        evidence = {
            field: [f"human::{module_id}::{field}"]
            for field in definition["required_fields"]
        }
        if module_id == "stakeholder_context":
            evidence.update(
                {
                    "access_method": ["Read-only repository access supplied by client"],
                    "primary_technical_contact": ["Named technical contact supplied by client"],
                    "authorized_scope": ["Exact repository scope supplied by client"],
                }
            )
        output[module_id] = {
            "evidence": evidence,
            "reviewer": f"reviewer::{module_id}",
            "observed_at": "2026-08-27T20:00:00Z",
            "source_reference": f"source::{module_id}",
        }
    return output


def _context(report_language: str = "en") -> dict:
    human_evidence = normalize_strategic_human_evidence(_human_input())
    engagement = build_comprehensive_engagement_metadata(
        client_name="Client Human Name",
        project_name="Client Human Project",
        human_evidence=human_evidence,
    )
    return {
        "run_id": "comprun_human_evidence_report_v1",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_human_evidence_report_v1",
        "customer_id": "customer_human_evidence_report_v1",
        "project_id": "project_human_evidence_report_v1",
        "report_language": report_language,
        "engagement_metadata": engagement,
        "human_evidence": human_evidence,
    }


def _canonical(report_language: str = "en", stages: list[dict] | None = None) -> dict:
    return {
        "report_language": report_language,
        "identity": {
            "run_id": "comprun_human_evidence_report_v1",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_human_evidence_report_v1",
            "customer_id": "customer_human_evidence_report_v1",
            "project_id": "project_human_evidence_report_v1",
            "report_language": report_language,
        },
        "assessment": {
            "technical_score": 93,
            "canonical_evidence_adjusted_score": 93,
            "maturity_signal": {
                "level": "Exceptional",
                "technical_score": 93,
                "canonical_evidence_adjusted_score": 93,
                "presented_score": 93,
            },
            "sections": [],
            "unavailable_data_notes": [],
        },
        "stage_summaries": list(stages or []),
    }


def _rendered_stages(context: dict) -> list[dict]:
    def fake_builder(*, identity, stage_results):
        canonical = _canonical(str(context["report_language"]))
        stages = renderer._canonical_stages(canonical)
        assert renderer._score_pair(canonical["assessment"]) == (93, 93)
        return {
            "status": "complete",
            "identity": identity,
            "stage_results": stage_results,
            "stages": stages,
        }

    result = human_report.build_report_package_with_human_context(
        fake_builder,
        context=context,
        identity=dict(_canonical(str(context["report_language"]))["identity"]),
        stage_results={},
    )
    return list(result["stages"])


def test_all_verified_human_modules_and_five_engagement_fields_reach_report_stages() -> None:
    stages = _rendered_stages(_context("en"))
    by_id = {str(stage.get("stage_id")): stage for stage in stages}

    summary = by_id["client_evidence_summary"]
    joined_summary = "\n".join(summary.get("evidence") or [])
    for expected in (
        "Client Human Name",
        "Client Human Project",
        "Named technical contact supplied by client",
        "Read-only repository access supplied by client",
        "Exact repository scope supplied by client",
    ):
        assert expected in joined_summary

    for module_id, definition in MODULES.items():
        matching = [
            stage
            for stage_id, stage in by_id.items()
            if stage_id == f"client_human_evidence_{module_id}"
            or stage_id.startswith(f"client_human_evidence_{module_id}_")
        ]
        assert matching, module_id
        joined = "\n".join(
            line
            for stage in matching
            for line in stage.get("evidence") or []
        )
        for field in definition["required_fields"]:
            assert f"human::{module_id}::{field}" in joined
        assert f"reviewer::{module_id}" in joined
        assert f"source::{module_id}" in joined

    assert all(
        len(line) < 1000
        for stage in stages
        if str(stage.get("stage_id") or "").startswith("client_")
        for line in stage.get("evidence") or []
    )


def test_spanish_projection_localizes_nico_labels_but_preserves_client_literals() -> None:
    stages = _rendered_stages(_context("es-MX"))
    human_stages = [
        stage
        for stage in stages
        if str(stage.get("stage_id") or "").startswith("client_human_evidence_")
    ]
    assert len(human_stages) >= len(MODULES)
    assert all(
        str(stage.get("title") or "").startswith(
            "Evidencia humana aportada por el cliente"
        )
        for stage in human_stages
    )
    assert all(
        str(line).startswith("Dato aportado por el cliente · ")
        for stage in human_stages
        for line in stage.get("evidence") or []
    )
    summary = next(
        stage for stage in stages if stage.get("stage_id") == "client_evidence_summary"
    )
    assert summary["title"] == "Resumen de evidencia del cliente"
    assert "Client Human Name" in "\n".join(summary.get("evidence") or [])


def test_locale_projection_reuses_frozen_human_evidence_without_assessment_rerun() -> None:
    english = _rendered_stages(_context("en"))
    spanish_canonical = _canonical("es-MX", english)

    # The exact stored canonical population is the source. No report-build human
    # context is present here, which simulates a later locale projection of the same run.
    projected = renderer._canonical_stages(spanish_canonical)
    by_id = {str(stage.get("stage_id")): stage for stage in projected}

    summary = by_id["client_evidence_summary"]
    assert summary["title"] == "Resumen de evidencia del cliente"
    assert all(
        not str(line).startswith("Client-supplied data · ")
        for line in summary.get("evidence") or []
    )
    functional = next(
        stage
        for stage_id, stage in by_id.items()
        if stage_id.startswith("client_human_evidence_functional_qa")
    )
    assert functional["title"].startswith(
        "Evidencia humana aportada por el cliente — QA funcional"
    )
    assert any(
        str(line).startswith("Dato aportado por el cliente · Casos de prueba")
        for line in functional.get("evidence") or []
    )
    assert renderer._score_pair(spanish_canonical["assessment"]) == (93, 93)


def test_tampered_human_evidence_is_not_projected() -> None:
    context = _context("en")
    tampered = dict(context["human_evidence"])
    tampered["status"] = "tampered"
    context["human_evidence"] = tampered

    stages = _rendered_stages(context)
    assert not any(
        str(stage.get("stage_id") or "").startswith("client_human_evidence_")
        for stage in stages
    )
    summary = next(
        stage for stage in stages if stage.get("stage_id") == "client_evidence_summary"
    )
    # Digest-verified engagement metadata remains available, but the tampered module
    # package is rejected instead of being silently rendered as trusted human evidence.
    assert "Client Human Name" in "\n".join(summary.get("evidence") or [])
