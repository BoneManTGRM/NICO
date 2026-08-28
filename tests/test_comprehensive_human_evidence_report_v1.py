from __future__ import annotations

import base64
import io
from copy import deepcopy

from pypdf import PdfReader

from nico import comprehensive_human_evidence_report_v2 as human_report
from nico import v2_premium_report_renderer as renderer
from nico.comprehensive_engagement_metadata_v1 import (
    build_comprehensive_engagement_metadata,
)
from nico.comprehensive_report_package import build_comprehensive_report_package
from nico.comprehensive_report_worker_runtime_v90 import _report_identity
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


def _compact_context(report_language: str = "en") -> dict:
    source = {
        "functional_qa": {
            "evidence": {
                "test_cases": ["Human checkout smoke test"],
                "observed_results": ["Human observed checkout success"],
            },
            "reviewer": "Human QA Reviewer",
            "observed_at": "2026-08-27T20:00:00Z",
            "source_reference": "Client QA record",
        },
        "stakeholder_context": {
            "evidence": {
                "objectives": ["Human supplied product objective"],
                "constraints": ["Human supplied delivery constraint"],
                "access_method": ["Client supplied read-only HTTPS access"],
                "primary_technical_contact": ["Client supplied technical contact"],
                "authorized_scope": ["Client supplied exact repository scope"],
            },
            "reviewer": "Human Stakeholder Reviewer",
            "observed_at": "2026-08-27T20:00:00Z",
            "source_reference": "Client stakeholder record",
        },
    }
    human_evidence = normalize_strategic_human_evidence(source)
    engagement = build_comprehensive_engagement_metadata(
        client_name="Client Artifact Name",
        project_name="Client Artifact Project",
        human_evidence=human_evidence,
    )
    return {
        "run_id": "comprun_human_evidence_artifact_v1",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "b" * 40,
        "evidence_ledger_id": "ledger_human_evidence_artifact_v1",
        "customer_id": "customer_human_evidence_artifact_v1",
        "project_id": "project_human_evidence_artifact_v1",
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


def _full_package(context: dict) -> dict:
    raw = human_report.build_report_package_with_human_context(
        build_comprehensive_report_package,
        context=context,
        identity=_report_identity(context),
        stage_results={},
    )
    assert raw["status"] == "complete"

    report = deepcopy(raw["report_package"])
    canonical = deepcopy(report["json"])
    identity = deepcopy(canonical.get("identity") or {})
    generated_at = str(raw["generated_at"])
    language = str(context["report_language"])
    canonical["generated_at"] = generated_at
    canonical["generation_timestamp"] = generated_at
    canonical["report_language"] = language
    identity["generated_at"] = generated_at
    identity["generation_timestamp"] = generated_at
    identity["report_language"] = language
    canonical["identity"] = identity
    report["json"] = canonical

    # This is the same premium final-artifact population used by the production report
    # repair chain after the base canonical package exists. It proves the retained human
    # stages survive into the actual EN/es-MX Markdown, HTML, JSON and PDF surfaces.
    rebuilt = renderer.rebuild_premium_client_artifacts(report)
    raw["report_package"] = rebuilt
    return raw


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


def test_base_canonical_population_retains_human_stages_before_locale_rebuild() -> None:
    context = _compact_context("en")
    raw = human_report.build_report_package_with_human_context(
        build_comprehensive_report_package,
        context=context,
        identity=_report_identity(context),
        stage_results={},
    )
    assert raw["status"] == "complete"
    stages = raw["report_package"]["json"].get("stage_summaries") or []
    by_id = {str(stage.get("stage_id") or ""): stage for stage in stages}
    assert "client_evidence_summary" in by_id
    assert "client_human_evidence_functional_qa" in by_id
    assert "client_human_evidence_stakeholder_context" in by_id
    joined = "\n".join(
        line
        for stage in stages
        if str(stage.get("stage_id") or "").startswith("client_")
        for line in stage.get("evidence") or []
    )
    for expected in (
        "Client Artifact Name",
        "Client Artifact Project",
        "Client supplied technical contact",
        "Client supplied read-only HTTPS access",
        "Client supplied exact repository scope",
        "Human checkout smoke test",
        "Human observed checkout success",
    ):
        assert expected in joined


def test_english_final_artifacts_carry_verified_human_input_end_to_end() -> None:
    package = _full_package(_compact_context("en"))
    report = package["report_package"]

    canonical = report["json"]
    stages = canonical.get("stage_summaries") or []
    stage_ids = {str(stage.get("stage_id") or "") for stage in stages}
    assert "client_evidence_summary" in stage_ids
    assert "client_human_evidence_functional_qa" in stage_ids
    assert "client_human_evidence_stakeholder_context" in stage_ids

    expected = (
        "Client Artifact Name",
        "Client Artifact Project",
        "Client supplied technical contact",
        "Client supplied read-only HTTPS access",
        "Client supplied exact repository scope",
        "Human checkout smoke test",
        "Human observed checkout success",
        "Human supplied product objective",
        "Human supplied delivery constraint",
    )
    markdown = str(report["markdown"])
    html = str(report["html"])
    pdf = base64.b64decode(report["pdf_base64"])
    pdf_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(pdf)).pages
    )
    for value in expected:
        assert value in markdown
        assert value in html
        assert value in pdf_text

    assert "Client Evidence Summary" in markdown
    assert "Client Human Evidence" in markdown
    assert report["human_review_required"] is True
    assert report["client_delivery_allowed"] is False


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


def test_spanish_final_artifacts_localize_nico_human_labels_end_to_end() -> None:
    package = _full_package(_compact_context("es-MX"))
    report = package["report_package"]
    canonical = report["json"]
    assert str(canonical.get("report_language") or "").lower().startswith("es")

    markdown = str(report["markdown"])
    html = str(report["html"])
    pdf = base64.b64decode(report["pdf_base64"])
    pdf_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(pdf)).pages
    )

    for label in (
        "Resumen de evidencia del cliente",
        "Evidencia humana aportada por el cliente",
        "Dato aportado por el cliente",
        "Método de acceso",
        "Contacto técnico principal",
        "Alcance autorizado",
    ):
        assert label in markdown
        assert label in html
        assert label in pdf_text

    # Client-entered values are factual literals, not NICO-authored prose. They remain
    # unchanged while NICO-owned headings/labels are es-MX.
    for value in (
        "Client Artifact Name",
        "Client Artifact Project",
        "Human checkout smoke test",
        "Human observed checkout success",
        "Human supplied product objective",
    ):
        assert value in markdown
        assert value in html
        assert value in pdf_text

    assert report["human_review_required"] is True
    assert report["client_delivery_allowed"] is False


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
