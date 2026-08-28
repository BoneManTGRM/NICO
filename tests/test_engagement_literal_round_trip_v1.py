from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
from copy import deepcopy

import pytest
from pypdf import PdfReader

from nico import comprehensive_client_ready_projection_v1 as client_projection
from nico import comprehensive_report_package as report_package
from nico import comprehensive_canonical_report_source_v1 as canonical_source
from nico import comprehensive_spanish_canonical_report_v87 as spanish_report
from nico import comprehensive_report_review_integrity_v1 as report_integrity
from nico import comprehensive_same_run_locale_report_v1 as locale_report
from nico import v2_premium_report_renderer as renderer
from nico.comprehensive_engagement_metadata_v1 import (
    build_comprehensive_engagement_metadata,
    verify_comprehensive_engagement_metadata,
)
from nico.comprehensive_report_worker_runtime_v90 import _report_identity
from nico.comprehensive_spanish_current_copy_worker_v98 import (
    install_comprehensive_spanish_current_copy_worker_v98,
)
from nico.strategic_human_evidence_v1 import normalize_strategic_human_evidence
from nico.v2_authoritative_premium_report import _ORIGINAL_HASH


PRIMARY = {
    "client_name": "Cody Jenkins",
    "project_name": "NICO Audit",
    "primary_technical_contact": "Cody — Repository owner / project lead",
    "access_method": "Public GitHub repository via HTTPS/API — read-only access",
    "authorized_scope": (
        "BoneManTGRM/NICO — entire repository, current main branch, including source "
        "code, configuration, CI/CD workflows, dependency manifests, documentation, "
        "and repository metadata. Read-only technical and security assessment."
    ),
}

UNICODE = {
    "client_name": "Compañía Águila, S.A. de C.V.",
    "project_name": "Proyecto Ñandú / Release 2.0",
    "primary_technical_contact": "María-José Pérez - CTO / Ingeniería",
    "access_method": "GitHub Enterprise - acceso de solo lectura",
    "authorized_scope": (
        "organizacion/proyecto - rama release/2026.08; código, configuración y CI/CD."
    ),
}


def _raw_human_evidence(fixture: dict[str, str]) -> dict:
    return {
        "stakeholder_context": {
            "evidence": {
                "primary_technical_contact": [fixture["primary_technical_contact"]],
                "access_method": [fixture["access_method"]],
                "authorized_scope": [fixture["authorized_scope"]],
            }
        }
    }


def _canonical(fixture: dict[str, str], language: str) -> dict:
    human_evidence = normalize_strategic_human_evidence(
        _raw_human_evidence(fixture)
    )
    engagement = build_comprehensive_engagement_metadata(
        client_name=fixture["client_name"],
        project_name=fixture["project_name"],
        human_evidence=_raw_human_evidence(fixture),
    )
    context = {
        "run_id": "comprun_literal_round_trip_v1",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_literal_round_trip_v1",
        "customer_id": "customer_literal_round_trip_v1",
        "project_id": "project_literal_round_trip_v1",
        "report_language": language,
        "engagement_metadata": engagement,
        "human_evidence": human_evidence,
    }
    identity = _report_identity(context)
    return {
        "report_language": language,
        "identity": identity,
        "engagement_metadata": engagement,
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
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


@pytest.mark.parametrize("fixture", [PRIMARY, UNICODE])
def test_five_literals_survive_canonical_report_and_both_locales(
    fixture: dict[str, str],
) -> None:
    report_integrity._install_required_report_sections()
    canonical = _canonical(fixture, "en")
    engagement = canonical["engagement_metadata"]
    assert verify_comprehensive_engagement_metadata(engagement) is True
    assert engagement == {
        **engagement,
        **fixture,
    }

    identity = canonical["identity"]
    expected_identity = {
        "customer_name": fixture["client_name"],
        "project_name": fixture["project_name"],
        "primary_technical_contact": fixture["primary_technical_contact"],
        "access_method": fixture["access_method"],
        "authorized_scope": fixture["authorized_scope"],
    }
    for key, expected in expected_identity.items():
        assert identity[key] == expected

    normalized_human = normalize_strategic_human_evidence(
        _raw_human_evidence(fixture)
    )
    retained = normalized_human["modules"]["stakeholder_context"]["evidence"]
    for key in ("primary_technical_contact", "access_method", "authorized_scope"):
        assert retained[key] == [fixture[key]]

    for language, spanish in (("en", False), ("es-MX", True)):
        localized = deepcopy(canonical)
        localized["report_language"] = language
        localized["identity"]["report_language"] = language
        stages = renderer._canonical_stages(localized)
        summary = next(
            stage
            for stage in stages
            if stage.get("stage_id") == "client_evidence_summary"
        )
        joined = "\n".join(summary.get("evidence") or [])
        for expected in fixture.values():
            assert expected in joined

        pdf = client_projection.render_evidence_review_gate_pdf(
            localized,
            {"summary": {}},
            spanish=spanish,
        )
        pdf_text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(io.BytesIO(pdf)).pages
        )
        visible = " ".join(pdf_text.split())
        for expected in fixture.values():
            assert " ".join(expected.split()) in visible

    assert fixture["project_name"] in identity.values()
    if fixture is PRIMARY:
        assert "NICO Audit" in identity.values()
        assert "NICO audit" not in identity.values()
    assert identity["primary_technical_contact"] != (
        f"{fixture['client_name']} — Repository owner / project lead"
    )


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_client_evidence_summary_keeps_five_literals_and_canonical_system_evidence(
    language: str,
) -> None:
    report_integrity._install_required_report_sections()
    canonical = _canonical(PRIMARY, language)
    canonical.update(
        {
            "scanner_execution_records": [
                {"scanner_name": "scanner-a", "completed": True},
                {"scanner_name": "scanner-b", "completed": False},
            ],
            "review_candidate_summary": {
                "raw_total": 12,
                "review_required_total": 9,
                "verified_material_total": 1,
            },
            "approval_status": "pending_human_approval",
            "delivery_status": "blocked_pending_human_approval",
            "lifecycle": {
                "human_review_status": "pending",
                "client_delivery_status": "blocked",
            },
        }
    )
    canonical["assessment"].update(
        {
            "scanner_execution_summary": {
                "record_count": 2,
                "completed_count": 1,
                "incomplete_count": 1,
            },
            "stage_summaries": [
                {
                    "stage_id": "review_required_candidate_register",
                    "technical_triage": {
                        "status": "complete",
                        "human_review_work_units": 4,
                        "workload_metrics": {
                            "technical_triage_completed": 12,
                            "technical_triage_pending": 0,
                        },
                    },
                }
            ],
        }
    )
    stale_label = "Nombre del cliente" if language == "es-MX" else "Client name"
    canonical["stage_summaries"] = [
        {
            "stage_id": "client_evidence_summary",
            "title": "existing summary",
            "summary": "existing summary",
            "status": "complete",
            "evidence": [
                f"{stale_label}: STALE VALUE",
                "retained-source-id=custom-evidence",
            ],
            "findings": ["retained client evidence finding"],
            "unavailable": ["retained client evidence limitation"],
        }
    ]

    summary = next(
        stage
        for stage in renderer._canonical_stages(canonical)
        if stage.get("stage_id") == "client_evidence_summary"
    )
    evidence = list(summary["evidence"])
    expected_client_lines = (
        (
            f"Client name: {PRIMARY['client_name']}",
            f"Project name: {PRIMARY['project_name']}",
            f"Primary technical contact: {PRIMARY['primary_technical_contact']}",
            f"Access method: {PRIMARY['access_method']}",
            f"Authorized scope: {PRIMARY['authorized_scope']}",
        )
        if language == "en"
        else (
            f"Nombre del cliente: {PRIMARY['client_name']}",
            f"Nombre del proyecto: {PRIMARY['project_name']}",
            f"Contacto técnico principal: {PRIMARY['primary_technical_contact']}",
            f"Método de acceso: {PRIMARY['access_method']}",
            f"Alcance autorizado: {PRIMARY['authorized_scope']}",
        )
    )
    assert tuple(evidence[:5]) == expected_client_lines
    assert all("STALE VALUE" not in line for line in evidence)
    assert "retained-source-id=custom-evidence" in evidence
    assert summary["findings"] == ["retained client evidence finding"]
    assert "retained client evidence limitation" in summary["unavailable"]
    expected_prefixes = (
        (
            "Repository identity:",
            "Exact commit:",
            "Run ID:",
            "Technical maturity:",
            "Evidence-adjusted maturity:",
            "Scanner execution:",
            "Technical-triage status:",
            "Candidate state:",
            "Human-review workload:",
            "Review state:",
            "Approval state:",
            "Client-delivery state:",
        )
        if language == "en"
        else (
            "Identidad del repositorio:",
            "Commit exacto:",
            "ID de ejecución:",
            "Madurez técnica:",
            "Madurez ajustada por evidencia:",
            "Ejecución de analizadores:",
            "Estado del triaje técnico:",
            "Estado de candidatos:",
            "Carga de revisión humana:",
            "Estado de revisión:",
            "Estado de aprobación:",
            "Estado de entrega al cliente:",
        )
    )
    assert all(any(line.startswith(prefix) for line in evidence) for prefix in expected_prefixes)


def test_verified_empty_field_never_borrows_stale_identity_or_evidence() -> None:
    engagement = build_comprehensive_engagement_metadata(
        client_name="Independent Client",
        project_name="Independent Project",
        human_evidence={
            "stakeholder_context": {
                "evidence": {"access_method": ["Read-only"]}
            }
        },
    )
    values = report_integrity._display_values(
        {
            "engagement_metadata": engagement,
            "identity": {"primary_technical_contact": "Stale borrowed contact"},
            "human_evidence": {
                "primary_technical_contact": "Another stale borrowed contact"
            },
        }
    )
    assert values["primary_technical_contact"] == ""
    assert values["access_method"] == "Read-only"
    assert values["authorized_scope"] == ""


def test_engagement_fields_are_read_only_from_stakeholder_context_namespace() -> None:
    metadata = build_comprehensive_engagement_metadata(
        client_name="Independent Client",
        project_name="Independent Project",
        human_evidence={
            "functional_qa": {
                "evidence": {
                    "primary_technical_contact": ["Wrong QA contact"],
                    "access_method": ["Wrong QA access"],
                    "authorized_scope": ["Wrong QA scope"],
                }
            },
            "stakeholder_context": {
                "evidence": {
                    "primary_technical_contact": ["Exact stakeholder contact"],
                    "access_method": ["Exact stakeholder access"],
                    "authorized_scope": ["Exact stakeholder scope"],
                }
            },
        },
    )

    assert metadata["primary_technical_contact"] == "Exact stakeholder contact"
    assert metadata["access_method"] == "Exact stakeholder access"
    assert metadata["authorized_scope"] == "Exact stakeholder scope"


def test_meaningful_internal_spacing_is_not_rewritten_or_truncated() -> None:
    literal = "Proyecto  Ñandú /  Release 2.0"
    engagement = build_comprehensive_engagement_metadata(
        client_name="Compañía  Águila",
        project_name=literal,
        human_evidence={
            "stakeholder_context": {
                "evidence": {
                    "primary_technical_contact": ["María-José  Pérez"],
                    "access_method": ["GitHub  Enterprise"],
                    "authorized_scope": ["rama  release/2026.08"],
                }
            }
        },
    )
    assert engagement["client_name"] == "Compañía  Águila"
    assert engagement["project_name"] == literal
    assert engagement["primary_technical_contact"] == "María-José  Pérez"
    assert engagement["access_method"] == "GitHub  Enterprise"
    assert engagement["authorized_scope"] == "rama  release/2026.08"


def test_meaningful_internal_spacing_survives_stage_markdown_html_and_pdf() -> None:
    fixture = {
        "client_name": "Compañía  Águila",
        "project_name": "Proyecto  Ñandú /  Release 2.0",
        "primary_technical_contact": "María-José  Pérez - CTO /  Ingeniería",
        "access_method": "GitHub  Enterprise - acceso de  solo lectura",
        "authorized_scope": "organizacion/proyecto - rama  release/2026.08; código y  CI/CD.",
    }
    report_integrity._install_required_report_sections()
    canonical = _canonical(fixture, "en")
    stages = renderer._canonical_stages(canonical)
    summary = next(
        stage
        for stage in stages
        if stage.get("stage_id") == "client_evidence_summary"
    )
    stage_text = "\n".join(summary.get("evidence") or [])
    for expected in fixture.values():
        assert expected in stage_text

    identity = canonical["identity"]
    assessment = canonical["assessment"]
    markdown = report_package._markdown(
        identity,
        assessment,
        stages,
        "2026-08-28T00:00:00Z",
    )
    for expected in fixture.values():
        assert expected in markdown

    rendered_html = report_package._semantic_html(markdown, "NICO Comprehensive")
    for expected in fixture.values():
        assert expected in rendered_html
    assert "white-space:break-spaces" in rendered_html

    pdf = client_projection.render_evidence_review_gate_pdf(
        canonical,
        {"summary": {}},
        spanish=False,
    )
    pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    for expected in fixture.values():
        assert expected in pdf_text


@pytest.mark.parametrize("fixture", [PRIMARY, UNICODE])
def test_core_stage_summary_keeps_exact_five_fields_in_markdown_html_and_pdf(
    fixture: dict[str, str],
) -> None:
    report_integrity._install_required_report_sections()
    canonical = _canonical(fixture, "en")
    source_summary = next(
        stage
        for stage in renderer._canonical_stages(canonical)
        if stage.get("stage_id") == "client_evidence_summary"
    )
    summary = report_package._stage_summary(
        "client_evidence_summary",
        {
            "status": source_summary["status"],
            "summary": source_summary["summary"],
            "evidence": source_summary["evidence"],
            "findings": source_summary["findings"],
            "unavailable": source_summary["unavailable"],
        },
    )
    expected_lines = (
        f"Client name: {fixture['client_name']}",
        f"Project name: {fixture['project_name']}",
        f"Primary technical contact: {fixture['primary_technical_contact']}",
        f"Access method: {fixture['access_method']}",
        f"Authorized scope: {fixture['authorized_scope']}",
    )
    assert tuple(summary["evidence"][:5]) == expected_lines

    identity = canonical["identity"]
    assessment = canonical["assessment"]
    markdown = report_package._markdown(
        identity,
        assessment,
        [summary],
        "2026-08-28T00:00:00Z",
    )
    rendered_html = report_package._semantic_html(
        markdown, "NICO Comprehensive"
    )
    encoded, error, page_count = report_package._pdf(
        identity,
        assessment,
        [summary],
        "2026-08-28T00:00:00Z",
    )
    assert error is None
    assert page_count > 0
    pdf_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(base64.b64decode(encoded))).pages
    )
    pdf_logical_text = pdf_text.replace("\n", " ")
    for expected in fixture.values():
        assert expected in markdown
        assert expected in rendered_html
        assert expected in pdf_logical_text
    assert "NICO audit" not in markdown
    assert (
        f"{fixture['client_name']} — Repository owner / project lead"
        not in markdown
    )


def test_canonical_source_identity_preserves_verified_literal_spacing() -> None:
    fixture = {
        "client_name": "Compañía  Águila",
        "project_name": "Proyecto  Ñandú",
        "primary_technical_contact": "María-José  Pérez",
        "access_method": "GitHub  Enterprise",
        "authorized_scope": "rama  release/2026.08",
    }
    engagement = build_comprehensive_engagement_metadata(
        client_name=fixture["client_name"],
        project_name=fixture["project_name"],
        human_evidence=_raw_human_evidence(fixture),
    )
    identity: dict[str, str] = {}

    canonical_source._attach_engagement_identity(
        identity,
        {"engagement_metadata": engagement},
    )

    assert identity == {
        "customer_name": fixture["client_name"],
        "project_name": fixture["project_name"],
        "primary_technical_contact": fixture["primary_technical_contact"],
        "access_method": fixture["access_method"],
        "authorized_scope": fixture["authorized_scope"],
        "engagement_metadata_sha256": engagement["engagement_metadata_sha256"],
    }


def test_spanish_projection_never_translates_user_values_matching_authored_copy() -> None:
    fixture = {
        "client_name": "NICO Comprehensive Technical Assessment",
        "project_name": "Code Audit",
        "primary_technical_contact": "Human Review Checklist",
        "access_method": "Not supplied",
        "authorized_scope": "Priority Constraints and Decision Risks",
    }
    installed = install_comprehensive_spanish_current_copy_worker_v98()
    assert installed["bound"] is True
    report_integrity._install_required_report_sections()
    canonical = _canonical(fixture, "es-MX")
    canonical["stage_summaries"] = renderer._canonical_stages(canonical)

    localized_identity, _, localized_stages, _ = spanish_report._render_inputs(canonical)
    for key, expected in (
        ("customer_name", fixture["client_name"]),
        ("project_name", fixture["project_name"]),
        ("primary_technical_contact", fixture["primary_technical_contact"]),
        ("access_method", fixture["access_method"]),
        ("authorized_scope", fixture["authorized_scope"]),
    ):
        assert localized_identity[key] == expected

    client_summary = next(
        stage
        for stage in localized_stages
        if stage.get("stage_id") == "client_evidence_summary"
    )
    expected_summary_lines = (
        f"Nombre del cliente: {fixture['client_name']}",
        f"Nombre del proyecto: {fixture['project_name']}",
        f"Contacto técnico principal: {fixture['primary_technical_contact']}",
        f"Método de acceso: {fixture['access_method']}",
        f"Alcance autorizado: {fixture['authorized_scope']}",
    )
    assert tuple(client_summary["evidence"][:5]) == expected_summary_lines

    markdown = spanish_report.render_spanish_markdown(canonical)
    for expected in fixture.values():
        assert expected in markdown
        # Each supplied literal is shown once in the identity block and again in the
        # canonical Client Evidence Summary. Neither occurrence may be retransformed.
        assert markdown.count(expected) >= 2
    for localized_label in (
        "Nombre del cliente",
        "Nombre del proyecto",
        "Contacto técnico principal",
        "Método de acceso",
        "Alcance autorizado",
    ):
        assert localized_label in markdown

    pdf, _ = spanish_report.render_spanish_pdf(canonical)
    pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    for expected in fixture.values():
        assert expected in pdf_text


@pytest.mark.parametrize("fixture", [PRIMARY, UNICODE])
def test_spanish_projection_protects_both_client_summary_copies(
    fixture: dict[str, str],
) -> None:
    report_integrity._install_required_report_sections()
    canonical = _canonical(fixture, "es-MX")
    canonical["stage_summaries"] = renderer._canonical_stages(canonical)
    canonical["assessment"]["stage_summaries"] = deepcopy(
        canonical["stage_summaries"]
    )

    _, localized_assessment, localized_stages, _ = spanish_report._render_inputs(
        canonical
    )
    top_summary = next(
        stage
        for stage in localized_stages
        if stage.get("stage_id") == "client_evidence_summary"
    )
    assessment_summary = next(
        stage
        for stage in localized_assessment["stage_summaries"]
        if stage.get("stage_id") == "client_evidence_summary"
    )
    expected_lines = (
        f"Nombre del cliente: {fixture['client_name']}",
        f"Nombre del proyecto: {fixture['project_name']}",
        f"Contacto técnico principal: {fixture['primary_technical_contact']}",
        f"Método de acceso: {fixture['access_method']}",
        f"Alcance autorizado: {fixture['authorized_scope']}",
    )
    assert tuple(top_summary["evidence"][:5]) == expected_lines
    assert tuple(assessment_summary["evidence"][:5]) == expected_lines


def test_multiline_engagement_literals_round_trip_without_report_structure_injection() -> None:
    fixture = {
        "client_name": "Acme\n\n## APPROVED FINAL",
        "project_name": "Safe\r\nProject",
        "primary_technical_contact": "Casey\nSecurity lead",
        "access_method": "Read-only\u2028GitHub API",
        "authorized_scope": "repository/main\u2029source and CI",
    }
    report_integrity._install_required_report_sections()
    canonical = _canonical(fixture, "en")
    canonical["stage_summaries"] = renderer._canonical_stages(canonical)

    for key, expected in fixture.items():
        assert canonical["engagement_metadata"][key] == expected
    assert canonical["identity"]["customer_name"] == fixture["client_name"]
    assert canonical["identity"]["project_name"] == fixture["project_name"]

    markdown = report_package._markdown(
        canonical["identity"],
        canonical["assessment"],
        canonical["stage_summaries"],
        "2026-08-28T00:00:00Z",
    )
    assert "Acme<br/><br/>## APPROVED FINAL" in markdown
    assert "\n## APPROVED FINAL" not in markdown

    rendered_html = report_package._semantic_html(markdown, "NICO Comprehensive")
    assert "<h2>APPROVED FINAL</h2>" not in rendered_html
    assert (
        '<span data-nico-client-literal="true">Acme<br/><br/>## APPROVED FINAL</span>'
        in rendered_html
    )

    pdf = client_projection.render_evidence_review_gate_pdf(
        canonical,
        {"summary": {}},
        spanish=False,
    )
    pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    for visible_line in (
        "Acme",
        "## APPROVED FINAL",
        "Safe",
        "Project",
        "Casey",
        "Security lead",
        "Read-only",
        "GitHub API",
        "repository/main",
        "source and CI",
    ):
        assert visible_line in pdf_text


def test_production_v2_hash_binds_exact_stored_json_and_allows_same_run_locale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = _canonical(PRIMARY, "es-MX")
    expected = _ORIGINAL_HASH(canonical)
    script = """
import json, sys
import nico.api.same_run_locale_report_bootstrap  # noqa: F401
from nico import v2_pipeline_adapter
from nico.v2_authoritative_premium_report import _ORIGINAL_HASH
canonical = json.loads(sys.stdin.read())
print(json.dumps({
    'pipeline': v2_pipeline_adapter.canonical_truth_sha256(canonical),
    'stored': _ORIGINAL_HASH(canonical),
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(canonical, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=True,
    )
    subprocess_hashes = json.loads(completed.stdout)
    assert subprocess_hashes == {"pipeline": expected, "stored": expected}

    status = {
        "run_id": canonical["identity"]["run_id"],
        "repository": canonical["identity"]["repository"],
        "commit_sha": canonical["identity"]["commit_sha"],
        "report_language": "es-MX",
        "terminal": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "reports": {
            "report_id": "comprehensive_report_literal_round_trip_v1",
            "canonical_truth_sha256": expected,
            "json": canonical,
            "markdown": "# informe",
            "html": "<article>informe</article>",
            "pdf_base64": base64.b64encode(b"%PDF-1.4\nsource").decode("ascii"),
        },
    }
    monkeypatch.setattr(
        locale_report,
        "_render_target",
        lambda canonical, report_language: {
            "markdown": "# report",
            "html": "<article>report</article>",
            "pdf_base64": base64.b64encode(b"%PDF-1.4\nlocalized").decode("ascii"),
            "pdf_sha256": "localized-sha",
            "pdf_page_count": 1,
        },
    )
    localized = locale_report.build_same_run_locale_report(status, "en")
    assert localized["canonical_truth_sha256"] == expected
    assert localized["report"]["json"] == canonical
    assert localized["same_canonical_run"] is True
    assert localized["assessment_rerun"] is False
