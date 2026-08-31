from __future__ import annotations

import base64
import io

import pytest
from pypdf import PdfReader

from nico import comprehensive_report_package as report_package
from nico import comprehensive_report_review_integrity_v1 as report_integrity
from nico import v2_premium_report_renderer as renderer
from nico.canonical_state_rendering_v1 import render_canonical_state
from nico.comprehensive_client_ready_projection_v1 import (
    render_evidence_review_gate_pdf,
)
from nico.comprehensive_decision_grade_csv_v6 import _evidence_csv
from nico.comprehensive_engagement_metadata_v1 import (
    build_comprehensive_engagement_metadata,
    render_engagement_field,
    verify_comprehensive_engagement_metadata,
)


def test_explicit_stakeholder_exclusion_is_not_collapsed_to_not_supplied() -> None:
    metadata = build_comprehensive_engagement_metadata(
        client_name="Cody Jenkins",
        project_name="NICO Audit",
        human_evidence={
            "stakeholder_context": {
                "evidence": {},
                "excluded": True,
                "exclusion_rationale": "Excluded from this engagement by the requester.",
            }
        },
        field_states={
            "client_name": {"state": "supplied_unverified"},
            "project_name": {"state": "supplied_unverified"},
            "primary_technical_contact": {
                "state": "excluded_from_scope",
                "source": "user_action",
            },
            "access_method": {
                "state": "excluded_from_scope",
                "source": "user_action",
            },
            "authorized_scope": {
                "state": "excluded_from_scope",
                "source": "user_action",
            },
        },
    )

    states = metadata["field_states"]
    assert states["client_name"] == {
        "state": "supplied_unverified",
        "value": "Cody Jenkins",
        "source": "client_supplied_intake",
    }
    assert states["project_name"] == {
        "state": "supplied_unverified",
        "value": "NICO Audit",
        "source": "client_supplied_intake",
    }
    for field in (
        "primary_technical_contact",
        "access_method",
        "authorized_scope",
    ):
        assert states[field] == {
            "state": "excluded_from_scope",
            "value": None,
            "source": "user_action",
            "reason": "Excluded from this engagement by the requester.",
        }
        assert metadata[field] == ""


def test_explicit_exclusion_defaults_to_user_action_without_fabricated_metadata() -> None:
    metadata = build_comprehensive_engagement_metadata(
        client_name="",
        project_name="NICO Audit",
        human_evidence={},
        field_states={
            "client_name": {"state": "excluded_from_scope"},
            "project_name": {"state": "supplied_unverified"},
        },
    )
    assert metadata["field_states"]["client_name"] == {
        "state": "excluded_from_scope",
        "value": None,
        "source": "user_action",
    }
    assert "excluded_by" not in metadata["field_states"]["client_name"]
    assert "excluded_at" not in metadata["field_states"]["client_name"]
    assert "reason" not in metadata["field_states"]["client_name"]


@pytest.mark.parametrize(
    ("state", "english", "spanish"),
    [
        ("supplied_verified", "Verified", "Verificado"),
        (
            "supplied_unverified",
            "Supplied — independent verification pending",
            "Proporcionado — verificación independiente pendiente",
        ),
        ("not_supplied", "Not supplied", "No proporcionado"),
        ("excluded_from_scope", "Excluded from scope", "Excluido del alcance"),
        ("not_applicable", "Not applicable", "No aplica"),
        (
            "framework_only",
            "Framework only — stakeholder validation pending",
            "Solo marco de trabajo — pendiente de validación de las partes interesadas",
        ),
        ("review_required", "Human review required", "Revisión humana requerida"),
        (
            "pending_human_approval",
            "Pending human approval",
            "Pendiente de aprobación humana",
        ),
    ],
)
def test_one_canonical_state_mapper_drives_english_and_mexican_spanish(
    state: str,
    english: str,
    spanish: str,
) -> None:
    assert render_canonical_state(state, "en") == english
    assert render_canonical_state(state, "es-MX") == spanish


def _mixed_state_metadata() -> dict:
    return build_comprehensive_engagement_metadata(
        client_name="Cody Jenkins",
        project_name="NICO Audit",
        human_evidence={"stakeholder_context": {"evidence": {}}},
        field_states={
            "client_name": {"state": "supplied_unverified"},
            "project_name": {"state": "supplied_verified"},
            "primary_technical_contact": {
                "state": "excluded_from_scope",
                "source": "user_action",
            },
            "access_method": {"state": "not_supplied"},
            "authorized_scope": {
                "state": "not_applicable",
                "source": "user_action",
            },
        },
    )


def _canonical(language: str) -> dict:
    metadata = _mixed_state_metadata()
    return {
        "report_language": language,
        "locale": language,
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "comprun_field_state_truth_v1",
            "report_language": language,
            "customer_name": "Cody Jenkins",
            "project_name": "NICO Audit",
            "engagement_field_states": metadata["field_states"],
        },
        "engagement_metadata": metadata,
        "assessment": {
            "technical_score": 93,
            "canonical_evidence_adjusted_score": 93,
            "maturity_signal": {"score": 93, "presented_score": 93},
            "sections": [],
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "scanner_execution_records": [],
        "review_candidate_summary": {},
        "technical_triage": {"workload_metrics": {}},
        "stage_summaries": [],
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


@pytest.mark.parametrize(
    ("language", "expected_rows"),
    [
        (
            "en",
            (
                "Client name: Cody Jenkins",
                "Project name: NICO Audit",
                "Primary technical contact: Excluded from scope",
                "Access method: Not supplied",
                "Authorized scope: Not applicable",
            ),
        ),
        (
            "es-MX",
            (
                "Nombre del cliente: Cody Jenkins",
                "Nombre del proyecto: NICO Audit",
                "Contacto técnico principal: Excluido del alcance",
                "Método de acceso: No proporcionado",
                "Alcance autorizado: No aplica",
            ),
        ),
    ],
)
def test_client_evidence_summary_and_all_report_formats_render_canonical_states(
    language: str,
    expected_rows: tuple[str, ...],
) -> None:
    report_integrity._install_required_report_sections()
    canonical = _canonical(language)
    assert verify_comprehensive_engagement_metadata(canonical["engagement_metadata"])
    stages = renderer._canonical_stages(canonical)
    summary = next(
        stage for stage in stages if stage.get("stage_id") == "client_evidence_summary"
    )
    assert tuple(summary["evidence"][:5]) == expected_rows
    expected_completeness = (
        "Integridad de la evidencia del cliente: Parcial"
        if language == "es-MX"
        else "Client Evidence Completeness: Partial"
    )
    expected_runtime = (
        "Aceptación en ejecución: No establecida"
        if language == "es-MX"
        else "Runtime Acceptance: Not established"
    )
    assert expected_completeness in summary["evidence"]
    assert expected_runtime in summary["evidence"]

    markdown = report_package._markdown(
        canonical["identity"],
        canonical["assessment"],
        stages,
        "2026-08-30T00:00:00Z",
    )
    rendered_html = report_package._semantic_html(markdown, "NICO Comprehensive")
    evidence_csv = _evidence_csv(stages)
    encoded_pdf, error, page_count = report_package._pdf(
        canonical["identity"],
        canonical["assessment"],
        stages,
        "2026-08-30T00:00:00Z",
    )
    assert error is None
    assert page_count > 0
    pdf_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(base64.b64decode(encoded_pdf))).pages
    )
    for expected in expected_rows:
        assert expected in markdown
        assert expected in rendered_html
        assert expected in evidence_csv
        assert expected in pdf_text.replace("\n", " ")


def test_structured_json_and_client_pdf_preserve_state_truth() -> None:
    canonical = _canonical("es-MX")
    metadata = canonical["engagement_metadata"]
    assert metadata["field_states"]["primary_technical_contact"]["state"] == (
        "excluded_from_scope"
    )
    assert render_engagement_field(
        metadata,
        "primary_technical_contact",
        "es-MX",
    ) == "Excluido del alcance"
    assert render_engagement_field(metadata, "access_method", "es-MX") == (
        "No proporcionado"
    )
    assert render_engagement_field(metadata, "authorized_scope", "es-MX") == (
        "No aplica"
    )

    pdf = render_evidence_review_gate_pdf(
        canonical,
        {"summary": {}},
        spanish=True,
    )
    pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    for expected in ("Excluido del alcance", "No proporcionado", "No aplica"):
        assert expected in pdf_text


@pytest.mark.parametrize(
    ("state", "value"),
    [
        ("supplied_unverified", ""),
        ("excluded_from_scope", "literal that contradicts exclusion"),
        ("not_applicable", "literal that contradicts not-applicable"),
    ],
)
def test_contradictory_field_state_and_value_fails_closed(
    state: str,
    value: str,
) -> None:
    with pytest.raises(ValueError, match="engagement_field_state_"):
        build_comprehensive_engagement_metadata(
            client_name=value,
            project_name="NICO Audit",
            human_evidence={},
            field_states={
                "client_name": {"state": state},
                "project_name": {"state": "supplied_unverified"},
            },
        )
