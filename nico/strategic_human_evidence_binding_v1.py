from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any

from fastapi import FastAPI

from nico.comprehensive_intake_display_metadata_v2 import (
    install_comprehensive_intake_display_metadata_v2,
)
from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.strategic_human_evidence_v1 import (
    decision_grade_stage_payload,
    human_evidence_module,
)

VERSION = "nico.strategic_human_evidence_binding.v2.1"
Provider = Callable[[dict[str, Any]], dict[str, Any]]

_CAPABILITY_MODULES: dict[str, tuple[str, ...]] = {
    "functional_qa": ("functional_qa", "accessibility_ux"),
    "platform_parity": ("platform_parity", "accessibility_ux"),
    "stakeholder_alignment": (
        "stakeholder_context",
        "incident_history",
        "product_objectives",
        "release_constraints",
        "compliance_requirements",
        "budget_staffing",
        "accepted_risks",
    ),
    "requirements_traceability": (
        "product_objectives",
        "release_constraints",
        "compliance_requirements",
        "accepted_risks",
    ),
    "roadmap": (
        "product_objectives",
        "release_constraints",
        "budget_staffing",
        "accepted_risks",
    ),
    "resourcing": ("budget_staffing", "release_constraints"),
    "executive_briefing": (
        "stakeholder_context",
        "incident_history",
        "product_objectives",
        "release_constraints",
        "accepted_risks",
    ),
}


def _active_modules(context: dict[str, Any], module_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    package = context.get("human_evidence")
    modules: list[dict[str, Any]] = []
    for module_id in module_ids:
        module = human_evidence_module(package, module_id)
        if module.get("status") != "not_assessed":
            modules.append(module)
    return modules


def _summary(modules: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "not_assessed" if not modules else (
            "complete" if all(module.get("status") in {"complete", "excluded"} for module in modules) else "review_limited"
        ),
        "module_ids": [str(module["module_id"]) for module in modules],
        "module_count": len(modules),
        "complete_count": sum(module.get("status") == "complete" for module in modules),
        "partial_count": sum(module.get("status") == "partial" for module in modules),
        "excluded_count": sum(module.get("status") == "excluded" for module in modules),
        "directly_scored": False,
        "requires_human_review": True,
        "repository_inference_allowed": False,
    }


def _remove_repository_only_limitations(
    notes: list[Any],
    *,
    capability: str,
) -> list[str]:
    patterns = {
        "functional_qa": (
            "runtime user-journey execution",
            "stakeholder acceptance testing",
        ),
        "platform_parity": (
            "cross-platform parity cannot be scored",
            "runnable builds",
        ),
        "stakeholder_alignment": (
            "stakeholder interviews",
            "business priorities",
        ),
        "requirements_traceability": (
            "authoritative requirements register",
            "stakeholder-approved acceptance matrix",
        ),
    }.get(capability, ())
    output: list[str] = []
    for item in notes:
        text = str(item or "").strip()
        lowered = text.casefold()
        if text and not any(pattern in lowered for pattern in patterns):
            output.append(text)
    return output


def _wrap(capability: str, original: Provider) -> Provider:
    module_ids = _CAPABILITY_MODULES[capability]

    def execute(context: dict[str, Any]) -> dict[str, Any]:
        raw = original(context)
        if not isinstance(raw, dict):
            raise TypeError(f"human_evidence_provider_result_must_be_dict:{capability}")
        result = deepcopy(raw)
        active = _active_modules(context, module_ids)
        payload = decision_grade_stage_payload(context.get("human_evidence"), module_ids)
        summary = _summary(active)

        # This direct module mapping is the existing decision-grade report input
        # contract. It permits one canonical ledger instead of a competing schema.
        result["human_evidence"] = payload
        result["human_evidence_summary"] = summary
        evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
        result["evidence"] = {
            **evidence,
            "human_evidence_status": summary["status"],
            "human_evidence_module_ids": summary["module_ids"],
            "human_evidence_complete_count": summary["complete_count"],
            "human_evidence_partial_count": summary["partial_count"],
            "human_evidence_excluded_count": summary["excluded_count"],
        }
        completed_or_excluded = [
            module for module in active if module.get("status") in {"complete", "excluded"}
        ]
        if completed_or_excluded:
            result["unavailable_data_notes"] = _remove_repository_only_limitations(
                list(result.get("unavailable_data_notes") or []),
                capability=capability,
            )
        if active:
            result["summary"] = (
                str(result.get("summary") or "").rstrip(". ")
                + f". {len(active)} explicit human-evidence module(s) were retained; they remain review-bound and do not automatically alter technical scores."
            )
        result["human_review_required"] = True
        result["client_delivery_allowed"] = False
        return result

    setattr(execute, "_nico_strategic_human_evidence_v2", True)
    setattr(execute, "_nico_original_provider", original)
    return execute


def install_strategic_human_evidence_binding(app: FastAPI) -> dict[str, Any]:
    # The production Comprehensive bootstrap always installs this binding. Make the
    # commercial intake metadata persistence part of the same fail-closed boundary so
    # client/project display names cannot depend on a separate, optional installer or
    # process-order side effect. The route function resolves its module-level _intake at
    # request time, so this remains authoritative even when routes are registered later.
    intake_display_metadata = install_comprehensive_intake_display_metadata_v2()
    intake_display_metadata_bound = (
        intake_display_metadata.get("bound") is True
        and intake_display_metadata.get("direct_controller_payload") is True
        and intake_display_metadata.get("durable_report_display_metadata_fallback") is True
        and intake_display_metadata.get("contextvar_required_for_display_metadata") is False
    )

    source = getattr(app.state, PROVIDER_STATE_KEY, None)
    providers = dict(source) if isinstance(source, Mapping) else {}
    bound: list[str] = []
    missing: list[str] = []
    for capability in _CAPABILITY_MODULES:
        provider = providers.get(capability)
        if not callable(provider):
            missing.append(capability)
            continue
        if getattr(provider, "_nico_strategic_human_evidence_v2", False):
            bound.append(capability)
            continue
        providers[capability] = _wrap(capability, provider)
        bound.append(capability)
    setattr(app.state, PROVIDER_STATE_KEY, providers)
    status = {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "bound": not missing and intake_display_metadata_bound,
        "bound_capabilities": sorted(bound),
        "missing_capabilities": sorted(missing),
        "intake_display_metadata": intake_display_metadata,
        "intake_display_metadata_bound": intake_display_metadata_bound,
        "commercial_display_metadata_durable": intake_display_metadata_bound,
        "human_evidence_module_count": 10,
        "existing_decision_grade_ledger_reused": True,
        "repository_inference_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    app.state.nico_strategic_human_evidence_binding = status
    return status


__all__ = ["VERSION", "install_strategic_human_evidence_binding"]
