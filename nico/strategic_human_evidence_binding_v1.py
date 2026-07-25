from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any

from fastapi import FastAPI

from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.strategic_human_evidence_v1 import human_evidence_module

VERSION = "nico.strategic_human_evidence_binding.v1"
Provider = Callable[[dict[str, Any]], dict[str, Any]]

_CAPABILITY_MODULES: dict[str, tuple[str, ...]] = {
    "functional_qa": ("functional_qa",),
    "platform_parity": ("platform_parity", "accessibility_ux"),
    "stakeholder_alignment": (
        "stakeholder_context",
        "release_goals",
        "incident_history",
        "support_pain_points",
        "budget_staffing_constraints",
        "accepted_risks",
    ),
    "requirements_traceability": (
        "requirements_compliance",
        "architecture_decisions",
        "release_goals",
    ),
    "roadmap": (
        "release_goals",
        "budget_staffing_constraints",
        "accepted_risks",
    ),
    "resourcing": ("budget_staffing_constraints", "release_goals"),
    "executive_briefing": (
        "stakeholder_context",
        "release_goals",
        "accepted_risks",
        "incident_history",
    ),
}


def _provided_modules(context: dict[str, Any], module_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    package = context.get("human_evidence")
    modules: list[dict[str, Any]] = []
    for module_id in module_ids:
        module = human_evidence_module(package, module_id)
        if module.get("status") == "provided":
            modules.append(module)
    return modules


def _human_projection(modules: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "provided" if modules else "not_assessed",
        "module_ids": [str(module["module_id"]) for module in modules],
        "module_count": len(modules),
        "statement_count": sum(len(module.get("statements") or []) for module in modules),
        "record_count": sum(len(module.get("records") or []) for module in modules),
        "attachment_reference_count": sum(
            len(module.get("attachment_refs") or []) for module in modules
        ),
        "modules": [
            {
                "module_id": module["module_id"],
                "label": module["label"],
                "source_type": module["source_type"],
                "statements": deepcopy(module.get("statements") or []),
                "records": deepcopy(module.get("records") or []),
                "attachment_refs": deepcopy(module.get("attachment_refs") or []),
                "supplied_by": module.get("supplied_by") or "",
                "captured_at": module.get("captured_at") or "",
                "module_sha256": module.get("module_sha256") or "",
            }
            for module in modules
        ],
        "directly_scored": False,
        "requires_human_review": True,
        "repository_inference_prohibited": True,
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
        provided = _provided_modules(context, module_ids)
        projection = _human_projection(provided)
        result["human_evidence"] = projection
        evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
        result["evidence"] = {
            **evidence,
            "human_evidence_status": projection["status"],
            "human_evidence_module_ids": projection["module_ids"],
            "human_evidence_statement_count": projection["statement_count"],
            "human_evidence_record_count": projection["record_count"],
            "human_evidence_attachment_reference_count": projection[
                "attachment_reference_count"
            ],
        }
        if provided:
            result["unavailable_data_notes"] = _remove_repository_only_limitations(
                list(result.get("unavailable_data_notes") or []),
                capability=capability,
            )
            result["summary"] = (
                str(result.get("summary") or "").rstrip(". ")
                + f". {len(provided)} explicit human-evidence module(s) were attached; statements remain review-bound and are not automatically scored."
            )
        result["human_review_required"] = True
        result["client_delivery_allowed"] = False
        return result

    setattr(execute, "_nico_strategic_human_evidence_v1", True)
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
        if getattr(provider, "_nico_strategic_human_evidence_v1", False):
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
        "human_evidence_module_count": 11,
        "repository_inference_prohibited": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    app.state.nico_strategic_human_evidence_binding = status
    return status


__all__ = ["VERSION", "install_strategic_human_evidence_binding"]
