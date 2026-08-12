from __future__ import annotations

import pytest
from fastapi import FastAPI

from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.phase3_engagement_intake_v1 import client_delivery_identity_valid, validate_and_enrich_intake
from nico.phase3_evidence_core_v1 import functional_qa_provider, platform_parity_provider, requirements_traceability_provider, stakeholder_alignment_provider
from nico.phase3_planning_synthesis_v1 import resourcing_provider, roadmap_provider
from nico.phase3_professional_assessment_v1 import install_phase3_professional_assessment_v1


def _module(status: str = "complete", **evidence: object) -> dict:
    return {
        "status": status,
        "evidence": evidence,
        "reviewer": "Authorized client source",
        "observed_at": "2026-08-12T12:00:00Z",
        "source_reference": "client://retained-input",
    }


def _context(*, modules: dict | None = None) -> dict:
    repo = {
        "architecture_evidence": {
            "test_path_count": 91,
            "source_file_count": 150,
            "deployment_manifests": ["Dockerfile"],
        },
        "file_evidence": {
            "sampled_paths": [
                "apps/web/app/page.tsx",
                "ios/App.swift",
                "docs/ADR-001.md",
                "docs/requirements.md",
            ]
        },
        "workflow_evidence": {
            "commands_detected": ["pytest", "npm run build"],
            "successful_runs": 18,
            "non_success_runs": 2,
            "workflow_run_count": 20,
        },
        "activity_evidence": {
            "captured_through": "2026-08-12T12:00:00Z",
            "commits_returned": 100,
            "pull_requests_returned": 50,
            "merged_pull_requests": 45,
        },
    }
    scoring = {
        "assessment": {
            "maturity_signal": {"level": "Exceptional", "score": 91, "presented_score": 91},
            "sections": [
                {"id": "architecture_debt", "label": "Architecture & Technical Debt", "presented_score": 72, "summary": "Hotspots require sequencing."},
                {"id": "ci_cd", "label": "CI/CD Analysis", "presented_score": 96, "summary": "Immutable workflow controls are strong."},
                {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "presented_score": 88, "summary": "Dependency evidence requires continuing review."},
            ],
        }
    }
    return {
        "run_id": "comprun_phase3",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_phase3",
        "customer_id": "client_001",
        "project_id": "project_001",
        "human_evidence": {"modules": modules or {}},
        "prior_stage_results": {
            "repository_and_delivery_evidence": {
                "repository_evidence": repo,
                "complexity_evidence": {
                    "hotspots": [{"path": "nico/a.py", "line": 12, "hotspot_score": 88.0}],
                    "top_coupled_files": [{"path": "nico/a.py", "fan_out": 9, "internal_fan_out": 6}],
                    "duplicate_evidence": {"duplicate_line_ratio": 0.05, "duplicate_block_groups": 2},
                },
            },
            "evidence_reconciliation_and_scoring": scoring,
        },
    }


def test_client_intake_requires_real_identity_contact_access_and_scope() -> None:
    with pytest.raises(ValueError, match="project_identity_required"):
        validate_and_enrich_intake(
            {
                "repository": "BoneManTGRM/NICO",
                "client_name": "Acme",
                "project_name": "",
                "authorization_confirmed": True,
                "human_evidence": {},
            }
        )

    with pytest.raises(ValueError, match="client_engagement_context_required"):
        validate_and_enrich_intake(
            {
                "repository": "BoneManTGRM/NICO",
                "client_name": "Acme",
                "project_name": "Platform",
                "authorization_confirmed": True,
                "human_evidence": {"stakeholder_context": {"evidence": {}}},
            }
        )

    enriched = validate_and_enrich_intake(
        {
            "repository": "BoneManTGRM/NICO",
            "client_name": "Acme",
            "project_name": "Platform",
            "authorization_confirmed": True,
            "human_evidence": {
                "stakeholder_context": {
                    "evidence": {
                        "access_method": ["authorized GitHub read access"],
                        "primary_technical_contact": ["CTO"],
                        "authorized_scope": ["repository and supplied evidence"],
                    },
                    "reviewer": "CTO",
                    "observed_at": "2026-08-12T12:00:00Z",
                    "source_reference": "client://intake",
                }
            },
        }
    )
    evidence = enriched["human_evidence"]["stakeholder_context"]["evidence"]
    assert enriched["phase3_engagement_mode"] == "client"
    assert evidence["engagement_mode"] == ["client"]
    assert evidence["client_identity"] == ["Acme"]
    assert evidence["project_identity"] == ["Platform"]


def test_internal_intake_is_explicit_and_placeholder_identity_cannot_deliver() -> None:
    enriched = validate_and_enrich_intake(
        {
            "repository": "BoneManTGRM/NICO",
            "client_name": "",
            "project_name": "",
            "authorization_confirmed": True,
            "human_evidence": {},
        }
    )
    assert enriched["phase3_engagement_mode"] == "internal"
    assert enriched["human_evidence"]["stakeholder_context"]["evidence"]["engagement_mode"] == ["internal"]
    record = {
        "identity": {"customer_id": "default_customer", "project_id": "default_project"},
        "human_evidence": {
            "modules": {
                "stakeholder_context": {
                    "evidence": {"engagement_mode": ["internal"]}
                }
            }
        },
    }
    assert client_delivery_identity_valid(record) is False


def test_repository_tests_never_become_runtime_acceptance_and_supplied_qa_is_retained() -> None:
    context = _context(
        modules={
            "functional_qa": _module(
                test_cases=["Sign in and open dashboard"],
                observed_results=["Dashboard loaded in approved staging environment"],
            )
        }
    )
    result = functional_qa_provider(context)
    qa = result["functional_qa"]
    assert qa["test_path_count"] == 91
    assert qa["supplied_test_cases"] == ["Sign in and open dashboard"]
    assert qa["runtime_evidence_state"] == "supplied_unverified"
    assert qa["repository_tests_are_runtime_acceptance"] is False
    assert qa["runtime_acceptance_established"] is False


def test_missing_runtime_qa_stays_visibly_missing() -> None:
    result = functional_qa_provider(_context())
    assert result["functional_qa"]["runtime_evidence_state"] == "not_assessed"
    assert result["missing_evidence"][0]["evidence_type"] == "runtime_functional_qa"
    assert result["unavailable_data_notes"]


def test_source_indicators_never_become_device_parity() -> None:
    result = platform_parity_provider(_context())
    parity = result["platform_parity"]
    assert parity["ios_paths"] == ["ios/App.swift"]
    assert parity["source_indicators_are_device_parity"] is False
    assert parity["device_runtime_parity_established"] is False
    assert result["missing_evidence"]


def test_stakeholder_notes_never_become_approved_authority_automatically() -> None:
    result = stakeholder_alignment_provider(
        _context(
            modules={
                "stakeholder_context": _module(
                    objectives=["Reduce release risk"],
                    constraints=["No weekend cutovers"],
                )
            }
        )
    )
    alignment = result["stakeholder_alignment"]
    assert alignment["objectives"] == ["Reduce release risk"]
    assert alignment["stakeholder_authority_established"] is False
    assert alignment["model_inference_is_stakeholder_authority"] is False


def test_requirements_keep_authoritative_inferred_and_missing_states_distinct() -> None:
    context = _context(
        modules={
            "compliance_requirements": _module(
                requirements=["ADR-001: preserve one canonical assessment pipeline", "REQ-002: nonexistent-widget contract"],
                authority_status=["authoritative"],
            )
        }
    )
    result = requirements_traceability_provider(context)
    mappings = result["requirements_traceability"]["mappings"]
    assert mappings[0]["authority_classification"] == "authoritative"
    assert mappings[0]["implementation_mapping_classification"] in {"inferred", "missing"}
    assert mappings[1]["authority_classification"] == "authoritative"
    assert result["requirements_traceability"]["contractual_obligations_invented"] is False

    missing = requirements_traceability_provider(_context())
    assert missing["missing_evidence"][0]["evidence_type"] == "authoritative_requirements"


def test_roadmap_remains_nico_proposal_and_staffing_never_invents_commercial_data() -> None:
    context = _context(
        modules={
            "stakeholder_context": _module(constraints=["Release freeze in December"]),
            "compliance_requirements": _module(requirements=["REQ-1: CI controls"], authority_status=["authoritative"]),
        }
    )
    req = requirements_traceability_provider(context)
    context["prior_stage_results"]["requirements_traceability"] = req
    stakeholder = stakeholder_alignment_provider(context)
    context["prior_stage_results"]["stakeholder_and_business_alignment"] = stakeholder
    roadmap = roadmap_provider(context)
    assert [item["window"] for item in roadmap["roadmap"]] == ["0-30 days", "31-90 days", "91-180 days"]
    assert all(item["sequence_state"] == "nico_proposed" for item in roadmap["roadmap"])
    assert all(item["stakeholder_approved"] is False for item in roadmap["roadmap"])
    assert roadmap["roadmap_truth"]["approved_dates_present"] is False

    context["prior_stage_results"]["six_month_roadmap"] = roadmap
    staffing = resourcing_provider(context)
    evidence = staffing["evidence"]
    assert evidence["commercial_values_generated"] is False
    assert evidence["salary_rates_generated"] is False
    assert evidence["vendor_commitments_generated"] is False
    assert evidence["final_budget_generated"] is False


def test_installation_reuses_one_comprehensive_provider_registry_and_preserves_report_providers() -> None:
    app = FastAPI()
    report_provider = object()
    scoring_provider = object()
    registry = {
        "report_generation": report_provider,
        "final_report_generation": report_provider,
        "cross_format_verification": report_provider,
        "canonical_scoring": scoring_provider,
        "technical_analysis": object(),
        "functional_qa": object(),
        "platform_parity": object(),
        "stakeholder_alignment": object(),
        "requirements_traceability": object(),
        "historical_trends": object(),
        "roadmap": object(),
        "resourcing": object(),
        "executive_briefing": object(),
    }
    setattr(app.state, PROVIDER_STATE_KEY, registry)
    status = install_phase3_professional_assessment_v1(app)
    updated = getattr(app.state, PROVIDER_STATE_KEY)
    assert status["one_public_product"] == "NICO Comprehensive"
    assert status["one_client_report"] is True
    assert status["parallel_assessment_pipeline_created"] is False
    assert updated["report_generation"] is report_provider
    assert updated["final_report_generation"] is report_provider
    assert updated["cross_format_verification"] is report_provider
    assert updated["canonical_scoring"] is scoring_provider


def test_installed_review_guard_fails_closed_for_internal_final_approval() -> None:
    app = FastAPI()
    setattr(app.state, PROVIDER_STATE_KEY, {
        "canonical_scoring": object(),
        "report_generation": object(),
        "final_report_generation": object(),
        "cross_format_verification": object(),
    })
    install_phase3_professional_assessment_v1(app)

    class Store:
        def load(self, run_id: str) -> dict:
            assert run_id == "internal-run"
            return {
                "identity": {"customer_id": "default_customer", "project_id": "default_project"},
                "human_evidence": {"modules": {"stakeholder_context": {"evidence": {"engagement_mode": ["internal"]}}}},
            }

    service = ComprehensiveRunService.__new__(ComprehensiveRunService)
    service._store = Store()
    with pytest.raises(ValueError, match="client_delivery_identity_required_for_final_approval"):
        service.review(
            "internal-run",
            reviewer="Alice",
            reviewer_role="Security specialist",
            decision="approved",
            decision_reason="Fixture",
        )
