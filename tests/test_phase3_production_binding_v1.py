from __future__ import annotations

from nico.api.terminal_authority_bootstrap import app
from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.phase3_evidence_core_v1 import CORE_PROVIDER_REPLACEMENTS
from nico.phase3_planning_synthesis_v1 import PLANNING_PROVIDER_REPLACEMENTS


def test_phase3_professional_synthesis_is_installed_on_the_existing_production_comprehensive_app() -> None:
    status = dict(getattr(app.state, "nico_phase3_professional_assessment", {}) or {})
    assert status["status"] in {"installed", "already_installed"}
    assert status["service_id"] == "comprehensive"
    assert status["one_public_product"] == "NICO Comprehensive"
    assert status["one_client_report"] is True
    assert status["parallel_assessment_pipeline_created"] is False
    assert status["canonical_scoring_replaced"] is False
    assert status["report_pipeline_replaced"] is False
    assert status["technical_score_inputs_changed"] is False
    assert status["human_review_required"] is True
    assert status["client_delivery_allowed"] is False
    engagement = status["engagement_intake"]
    assert engagement["runtime_recovery_guard_installed"] is True
    assert engagement["runtime_recovery_reapplies_approval_identity_guard"] is True
    assert engagement["historical_module_definition_contract_mutated"] is False
    controller = getattr(app.state, "comprehensive_api_controller", None)
    if controller is not None:
        assert engagement["approval_identity_guard_installed"] is True


def test_phase3_reuses_the_terminal_provider_registry_instead_of_creating_a_parallel_pipeline() -> None:
    registry = getattr(app.state, PROVIDER_STATE_KEY)
    expected = {**CORE_PROVIDER_REPLACEMENTS, **PLANNING_PROVIDER_REPLACEMENTS}
    for capability, provider in expected.items():
        assert registry[capability] is provider
    assert "canonical_scoring" in registry
    assert "report_generation" in registry
    assert "final_report_generation" in registry
    assert "cross_format_verification" in registry
