from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any

from fastapi import FastAPI

from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.strategic_human_evidence_v1 import (
    decision_grade_stage_payload,
    human_evidence_module,
)

VERSION = "nico.strategic_human_evidence_binding.v3"
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


def _project_descriptive_engagement_identity(
    result: dict[str, Any],
    context: dict[str, Any],
) -> None:
    """Carry persisted display identity into stakeholder evidence without authority.

    Customer/project display names are descriptive run metadata. They must not disappear
    merely because the stakeholder module contains only lightweight mobile context. This
    projection never creates stakeholder authority, approval, residual-risk acceptance,
    or client delivery authorization.
    """

    customer_name = str(
        context.get("customer_name") or context.get("client_name") or ""
    ).strip()
    project_name = str(context.get("project_name") or "").strip()
    if not customer_name and not project_name:
        return

    evidence = result.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
        result["evidence"] = evidence
    engagement = evidence.get("engagement")
    if not isinstance(engagement, dict):
        engagement = {}
        evidence["engagement"] = engagement

    if customer_name:
        engagement["client_identity"] = customer_name
    if project_name:
        engagement["project_identity"] = project_name
    if customer_name or project_name:
        engagement["mode"] = "client"

    primary_contact = str(engagement.get("primary_technical_contact") or "").strip()
    engagement["client_delivery_identity_valid"] = bool(
        customer_name and project_name and primary_contact
    )
    # Identity validity is descriptive only. Delivery authority remains explicitly
    # blocked until an authorized human reviewer acts.
    result["human_review_required"] = True
    result["client_delivery_allowed"] = False


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
        if capability == "stakeholder_alignment":
            _project_descriptive_engagement_identity(result, context)
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

    setattr(execute, "_nico_strategic_human_evidence_v3", True)
    setattr(execute, "_nico_strategic_human_evidence_v2", True)
    setattr(execute, "_nico_original_provider", original)
    return execute


def install_strategic_human_evidence_binding(app: FastAPI) -> dict[str, Any]:
    source = getattr(app.state, PROVIDER_STATE_KEY, None)
    providers = dict(source) if isinstance(source, Mapping) else {}
    bound: list[str] = []
    missing: list[str] = []
    for capability in _CAPABILITY_MODULES:
        provider = providers.get(capability)
        if not callable(provider):
            missing.append(capability)
            continue
        if getattr(provider, "_nico_strategic_human_evidence_v3", False):
            bound.append(capability)
            continue
        providers[capability] = _wrap(capability, provider)
        bound.append(capability)
    setattr(app.state, PROVIDER_STATE_KEY, providers)
    status = {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "bound": not missing,
        "bound_capabilities": sorted(bound),
        "missing_capabilities": sorted(missing),
        "human_evidence_module_count": 10,
        "existing_decision_grade_ledger_reused": True,
        "descriptive_engagement_identity_preserved": True,
        "repository_inference_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    app.state.nico_strategic_human_evidence_binding = status
    return status


__all__ = ["VERSION", "install_strategic_human_evidence_binding"]
