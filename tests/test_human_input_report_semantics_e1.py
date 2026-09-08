"""E1 regressions through the installed providers and retained report projections.

All human metadata here is synthetic operational test data, never professional approval.
"""
from __future__ import annotations

import base64
import io
from copy import deepcopy

import pytest
from fastapi import FastAPI
from pypdf import PdfReader

from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.comprehensive_report_package import _stage_summary, build_comprehensive_report_package
from nico.comprehensive_human_evidence_report_v2 import build_report_package_with_human_context
from nico.comprehensive_client_review_companion_v5 import substantive_review_sections, merge_substantive_review_markdown
from nico.comprehensive_client_review_companion_v7 import render_paired_substantive_review_pdf
from nico.phase3_professional_assessment_v1 import install_phase3_professional_assessment_v1
from nico.strategic_human_evidence_v1 import normalize_strategic_human_evidence


def _context(modules=None, language="en"):
    return {
        "run_id": "comprun_e1_synthetic",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_e1_synthetic",
        "customer_id": "synthetic_internal_customer",
        "project_id": "synthetic_internal_project",
        "report_language": language,
        "human_evidence": normalize_strategic_human_evidence(modules or {}),
        "prior_stage_results": {
            "repository_and_delivery_evidence": {
                "repository_evidence": {
                    "file_evidence": {"sampled_paths": ["src/auth.py"]},
                    "architecture_evidence": {"test_path_count": 2},
                },
            },
        },
    }


def _module(**evidence):
    return {
        "evidence": evidence,
        "reviewer": "SYNTHETIC operational fixture; no professional attestation",
        "observed_at": "2026-09-08T00:00:00Z",
        "source_reference": "fixture://internal-e1",
    }


def _providers():
    app = FastAPI()
    setattr(app.state, PROVIDER_STATE_KEY, {})
    install_phase3_professional_assessment_v1(app)
    return getattr(app.state, PROVIDER_STATE_KEY)


@pytest.mark.parametrize("authority_only", [False, True])
def test_absent_and_authority_only_do_not_receive_substantive_coverage(authority_only):
    context = _context(
        {"compliance_requirements": _module(authority_status=["authoritative"])}
        if authority_only else {}
    )
    for provider, payload in (
        ("requirements_traceability", "requirements_traceability"),
        ("stakeholder_alignment", "stakeholder_alignment"),
    ):
        result = _providers()[provider](context)
        assert result["status"] == "complete"  # execution completed
        assert result[payload]["evidence_state"] == "not_assessed"
        assert result["assessment_dimensions"]["substantive_coverage"] == "not_assessed"
        assert result["assessment_dimensions"]["full_coverage_claim"] is False
        assert result["human_review_required"] is True
        assert result["client_delivery_allowed"] is False
        assert "not assessed" in result["summary"].casefold()
    requirements = _providers()["requirements_traceability"](context)
    assert requirements["requirements_traceability"]["supplied_requirement_count"] == 0
    assert requirements["requirements_traceability"]["mappings"] == []


@pytest.mark.parametrize("marker", [{"status": "excluded"}, {"excluded": True}])
def test_excluded_populated_inputs_are_not_consumed_or_credited(marker):
    raw = {
        "compliance_requirements": {
            **_module(requirements=["EXCLUDED_SECRET_REQUIREMENT"], authority_status=["authoritative"]),
            **marker,
            "exclusion_rationale": "Synthetic explicit scope exclusion",
        },
        "stakeholder_context": {
            **_module(objectives=["EXCLUDED_SECRET_OBJECTIVE"], constraints=["EXCLUDED_SECRET_CONSTRAINT"]),
            **marker,
            "exclusion_rationale": "Synthetic explicit scope exclusion",
        },
    }
    # All three stakeholder contributors must be excluded to exclude the whole stage.
    # The original one-module case remains separately covered as mixed scope below.
    raw["product_objectives"] = {**_module(objectives=["EXCLUDED_SECRET_PRODUCT"], success_measures=["EXCLUDED_SECRET_MEASURE"]), **marker, "exclusion_rationale": "Synthetic explicit scope exclusion"}
    raw["release_constraints"] = {**_module(constraints=["EXCLUDED_SECRET_RELEASE"]), **marker, "exclusion_rationale": "Synthetic explicit scope exclusion"}
    context = _context(raw)
    frozen = deepcopy(context)
    for provider, payload in (
        ("requirements_traceability", "requirements_traceability"),
        ("stakeholder_alignment", "stakeholder_alignment"),
    ):
        result = _providers()[provider](context)
        assert result["status"] == "complete"
        assert result[payload]["evidence_state"] == "excluded"
        assert result["assessment_dimensions"]["substantive_coverage"] == "excluded"
        assert result["assessment_dimensions"]["full_coverage_claim"] is False
        assert result["missing_evidence"] == []
        assert "excluded" in result["summary"].casefold()
        assert "EXCLUDED_SECRET" not in str(result[payload])
    assert context == frozen  # retained source/history is immutable
    requirements = _providers()["requirements_traceability"](context)["requirements_traceability"]
    assert requirements["authority_status_supplied"] == []
    assert requirements["authoritative_requirement_count"] == 0


def test_supplied_evidence_remains_partial_and_order_independent():
    modules = {
        "compliance_requirements": _module(
            requirements=["REQ-01: auth.py must enforce access"],
            authority_status=["authoritative"],
        ),
        "stakeholder_context": _module(objectives=["Bounded objective"], constraints=["Bounded constraint"]),
        "product_objectives": _module(objectives=["Additional objective"], success_measures=["Observed measure"]),
    }
    first = _context(modules)
    second = _context(dict(reversed(list(modules.items()))))
    registry = _providers()
    forward = {key: registry[key](first) for key in ("requirements_traceability", "stakeholder_alignment")}
    reverse = {key: registry[key](second) for key in ("stakeholder_alignment", "requirements_traceability")}
    assert forward == reverse
    requirements = forward["requirements_traceability"]
    assert requirements["requirements_traceability"]["supplied_requirement_count"] == 1
    assert requirements["requirements_traceability"]["mappings"][0]["implementation_mapping_classification"] == "inferred"
    for result in forward.values():
        assert result["assessment_dimensions"]["substantive_coverage"] == "partial"
        assert result["assessment_dimensions"]["approval_status"] == "not_established"
        assert result["assessment_dimensions"]["full_coverage_claim"] is False


@pytest.mark.parametrize("language", ["en", "es-MX"])
@pytest.mark.parametrize("mode", ["absent", "excluded", "supplied"])
def test_actual_report_and_final_companion_preserve_human_input_state(language, mode):
    modules = {}
    if mode != "absent":
        modules = {
            "compliance_requirements": _module(requirements=["SOURCE_REQUIREMENT_LITERAL"], authority_status=["authoritative"]),
            "stakeholder_context": _module(objectives=["SOURCE_OBJECTIVE_LITERAL"], constraints=["SOURCE_CONSTRAINT_LITERAL"]),
        }
    if mode == "excluded":
        modules["product_objectives"] = _module(objectives=["EXCLUDED_PRODUCT"], success_measures=["EXCLUDED_MEASURE"])
        modules["release_constraints"] = _module(constraints=["EXCLUDED_RELEASE"])
        for module in modules.values():
            module.update(excluded=True, exclusion_rationale="Synthetic scope exclusion")
    context = _context(modules, language)
    registry = _providers()
    results = {
        "requirements_traceability": registry["requirements_traceability"](context),
        "stakeholder_and_business_alignment": registry["stakeholder_alignment"](context),
    }
    frozen = deepcopy(results)
    package = build_report_package_with_human_context(
        build_comprehensive_report_package,
        context=context,
        identity={key: context[key] for key in (
            "run_id", "repository", "commit_sha", "evidence_ledger_id", "customer_id", "project_id", "report_language"
        )},
        stage_results=results,
    )
    assert package["status"] == "complete"
    report = package["report_package"]
    canonical = report["json"]
    expected_state = {"absent": "not_assessed", "excluded": "excluded", "supplied": "partial"}[mode]
    by_stage = {stage["stage_id"]: stage for stage in canonical["stage_summaries"]}
    for stage_id in results:
        assert by_stage[stage_id]["assessment_dimensions"]["substantive_coverage"] == expected_state
    assert results == frozen
    assert canonical["human_review_required"] is True
    assert canonical["client_delivery_allowed"] is False

    spanish = language == "es-MX"
    sections = substantive_review_sections(canonical, spanish=spanish)
    selected = [section for section in sections if section["id"] in results]
    status_word = (
        {"absent": "No evaluado", "excluded": "Excluido", "supplied": "aportada"}
        if spanish else
        {"absent": "Not assessed", "excluded": "Excluded", "supplied": "supplied"}
    )[mode]
    assert len(selected) == 2
    for section in selected:
        assert status_word.casefold() in section["status"].casefold()
        if mode == "excluded":
            assert section["required_input"] == []
    markdown = merge_substantive_review_markdown("# Synthetic E1 review\n", canonical, spanish=spanish)
    pdf = render_paired_substantive_review_pdf(canonical, spanish=spanish)
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    assert status_word.casefold() in markdown.casefold()
    assert status_word.casefold() in pdf_text.casefold()
    if mode == "excluded":
        assert "SOURCE_REQUIREMENT_LITERAL" not in str(canonical["stage_summaries"])
        assert "SOURCE_OBJECTIVE_LITERAL" not in str(canonical["stage_summaries"])
        human_stages = [
            stage for stage in canonical["stage_summaries"]
            if stage["stage_id"].startswith("client_human_evidence_")
        ]
        assert human_stages
        assert all(stage["status"] == "excluded" for stage in human_stages)
    elif mode == "supplied":
        assert "SOURCE_REQUIREMENT_LITERAL" in str(canonical["stage_summaries"])
        assert "SOURCE_OBJECTIVE_LITERAL" in str(canonical["stage_summaries"])


@pytest.mark.parametrize("language", ["en", "es-MX"])
@pytest.mark.parametrize("mode", ["absent", "metadata_only", "test_plan_only", "excluded"])
def test_final_runtime_sections_cannot_credit_metadata_or_exclusions(language, mode):
    modules = {}
    if mode != "absent":
        # Deliberate PASS/device words in metadata are not runtime observations.
        modules = {
            "functional_qa": {**_module(), "reviewer": "SYNTHETIC PASS operator metadata"},
            "platform_parity": {**_module(), "source_reference": "fixture://Desktop-iPhone-WebKit-English-es-MX-PASS"},
        }
    if mode == "test_plan_only":
        modules["functional_qa"]["evidence"]["test_cases"] = ["Planned PASS checkout journey"]
    if mode == "excluded":
        for module in modules.values():
            module.update(excluded=True, exclusion_rationale="Synthetic scope exclusion")
    context = _context(modules, language)
    registry = _providers()
    results = {stage: registry[stage](context) for stage in ("functional_qa", "platform_parity")}
    raw = build_report_package_with_human_context(
        build_comprehensive_report_package,
        context=context,
        identity={key: context[key] for key in (
            "run_id", "repository", "commit_sha", "evidence_ledger_id", "customer_id", "project_id", "report_language"
        )},
        stage_results=results,
    )
    assert raw["status"] == "complete"
    canonical = raw["report_package"]["json"]
    spanish = language == "es-MX"
    sections = {section["id"]: section for section in substantive_review_sections(canonical, spanish=spanish)}
    for stage_id in results:
        section = sections[stage_id]
        if mode == "excluded":
            assert ("Excluido" if spanish else "Excluded") in section["status"]
            assert section["required_input"] == []
        else:
            assert ("no evaluad" if spanish else "not assessed") in section["status"].casefold()
        assert "Observed runtime evidence" not in section["status"]
        assert "Evidencia de ejecución observada" not in section["status"]
        assert "Platform observations supplied" not in section["status"]
        assert "Observaciones de plataforma aportadas" not in section["status"]
    markdown = merge_substantive_review_markdown("# Synthetic runtime semantics\n", canonical, spanish=spanish)
    pdf = render_paired_substantive_review_pdf(canonical, spanish=spanish)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    for surface in (markdown, text):
        assert "Observed runtime evidence: PASS" not in surface
        assert "Evidencia de ejecución observada: PASS" not in surface
        if mode == "excluded":
            assert ("Excluido del alcance" if spanish else "Excluded from scope") in surface
    if mode == "excluded":
        from nico.comprehensive_platform_parity_summary_v1 import install_comprehensive_platform_parity_summary
        from nico import comprehensive_client_ready_projection_v1 as projection

        install_comprehensive_platform_parity_summary()
        gate_pdf = projection.render_evidence_review_gate_pdf(canonical, {}, spanish=spanish)
        gate_text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(gate_pdf)).pages)
        assert ("excluida explícitamente" if spanish else "explicitly excluded") in gate_text
        assert "human input required" not in gate_text.casefold()


@pytest.mark.parametrize("excluded_id", ["stakeholder_context", "product_objectives", "release_constraints"])
def test_one_stakeholder_exclusion_cannot_hide_other_absent_scopes(excluded_id):
    context = _context({excluded_id: {**_module(), "excluded": True, "exclusion_rationale": "Synthetic limited exclusion"}})
    result = _providers()["stakeholder_alignment"](context)
    dimensions = result["assessment_dimensions"]
    assert dimensions["substantive_coverage"] == "not_assessed"
    assert dimensions["input_module_states"][excluded_id] == "excluded"
    assert list(dimensions["input_module_states"].values()).count("not_assessed") == 2
    assert result["missing_evidence"]
    assert result["stakeholder_alignment"]["evidence_state"] == "not_assessed"


def test_supplied_stakeholder_scope_retains_other_excluded_and_absent_scopes():
    context = _context({
        "stakeholder_context": {**_module(objectives=["EXCLUDED_OBJECTIVE"]), "excluded": True, "exclusion_rationale": "Synthetic limited exclusion"},
        "product_objectives": _module(objectives=["Retained product objective"], success_measures=["Retained success measure"]),
    })
    result = _providers()["stakeholder_alignment"](context)
    dimensions = result["assessment_dimensions"]
    assert dimensions["substantive_coverage"] == "partial"
    assert dimensions["input_module_states"] == {
        "product_objectives": "supplied_unverified",
        "release_constraints": "not_assessed",
        "stakeholder_context": "excluded",
    }
    assert "EXCLUDED_OBJECTIVE" not in str(result["stakeholder_alignment"])
    assert dimensions["full_coverage_claim"] is False
