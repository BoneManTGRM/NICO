from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI

from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.phase3_engagement_intake_v1 import install_phase3_engagement_intake_v1
from nico.phase3_evidence_core_v1 import CORE_PROVIDER_REPLACEMENTS
from nico.phase3_planning_synthesis_v1 import PLANNING_PROVIDER_REPLACEMENTS

VERSION = "nico.phase3_professional_assessment.v2"


def install_phase3_professional_assessment_v1(app: FastAPI) -> dict[str, Any]:
    existing = getattr(app.state, "nico_phase3_professional_assessment", None)
    if isinstance(existing, Mapping) and existing.get("status") in {"installed", "already_installed"}:
        return {**dict(existing), "status": "already_installed"}

    engagement = install_phase3_engagement_intake_v1(app)
    registry = getattr(app.state, PROVIDER_STATE_KEY, None)
    if not isinstance(registry, dict):
        raise RuntimeError("phase3_requires_existing_comprehensive_provider_registry")
    preserved = {
        key: registry.get(key)
        for key in (
            "canonical_scoring",
            "report_generation",
            "final_report_generation",
            "cross_format_verification",
        )
    }
    replacements = {**CORE_PROVIDER_REPLACEMENTS, **PLANNING_PROVIDER_REPLACEMENTS}
    registry.update(replacements)
    setattr(app.state, PROVIDER_STATE_KEY, registry)
    if any(registry.get(key) is not value for key, value in preserved.items()):
        raise RuntimeError("phase3_must_not_replace_scoring_or_report_pipeline")

    status = {
        "artifact_schema": VERSION,
        "synthesis_schema": "nico.phase3_professional_synthesis.v1",
        "status": "installed",
        "service_id": "comprehensive",
        "one_public_product": "NICO Comprehensive",
        "one_client_report": True,
        "parallel_assessment_pipeline_created": False,
        "existing_provider_registry_reused": True,
        "provider_replacements": sorted(replacements),
        "canonical_scoring_replaced": False,
        "report_pipeline_replaced": False,
        "missing_evidence_engine_bound": True,
        "functional_qa_real_evidence_supported": True,
        "repository_tests_cannot_be_runtime_acceptance": True,
        "platform_parity_real_evidence_supported": True,
        "source_indicators_cannot_be_device_parity": True,
        "requirements_authority_and_inference_separated": True,
        "stakeholder_inference_cannot_be_authority": True,
        "roadmap_framework_until_approved": True,
        "staffing_commercial_values_not_invented": True,
        "activity_volume_quality_score_effect": "none",
        "technical_score_inputs_changed": False,
        "engagement_intake": engagement,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    app.state.nico_phase3_professional_assessment = dict(status)
    return status


__all__ = ["VERSION", "install_phase3_professional_assessment_v1"]
