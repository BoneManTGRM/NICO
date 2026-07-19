from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

import nico.client_acceptance as client_acceptance
from nico.express_final_gate_completion_patch import normalize_assessment_completion

PATCH_VERSION = "nico.express_backend_completion_transport.v2"
_GATE_MARKER = "_nico_express_backend_completion_gate_v1"
_SAFE_MARKER = "_nico_express_backend_completion_safe_payload_v1"
_BUNDLE_MARKER = "_nico_express_backend_completion_bundle_v1"
_COMPLETION_FIELDS = (
    "status",
    "current_stage",
    "progress_percent",
    "report_generation_status",
    "human_review_required",
    "client_ready",
    "client_delivery_allowed",
    "delivery_status",
    "assessment_completion",
    "express_completion",
    "reports",
    "sections",
    "maturity_signal",
    "technical_score",
)


def _copy_completion_fields(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(target)
    for field in _COMPLETION_FIELDS:
        if field in source:
            output[field] = deepcopy(source[field])
    return output


def install_express_backend_completion_transport() -> dict[str, Any]:
    """Bind the final Express bundle, completion, and safe-response transport.

    This installer runs after every renderer, quality gate, and compatibility
    installer. Exact Express runs must therefore be rebound here so a later
    installer cannot replace the bounded evidence-bundle path and send the
    backend back into the recursive shared bundle at 94-96 percent.
    """

    from nico.api import main as api_main
    from nico.express_evidence_bundle_fast_path import attach_express_evidence_bundle

    current_bundle: Callable[[dict[str, Any]], dict[str, Any]] = api_main.attach_evidence_artifact_bundle
    bundle_status = "already_installed"
    if not getattr(current_bundle, _BUNDLE_MARKER, False):
        @wraps(current_bundle)
        def final_exact_run_bundle(result: dict[str, Any]) -> dict[str, Any]:
            run_id = str(result.get("run_id") or "").strip().lower()
            tier = str(
                result.get("assessment_type")
                or result.get("service_tier")
                or result.get("assessment_mode")
                or ""
            ).strip().lower()
            if tier == "express" or run_id.startswith("express_run_"):
                output = dict(result)
                output.setdefault("assessment_type", "express")
                output.setdefault("service_tier", "express")
                return attach_express_evidence_bundle(output)
            return current_bundle(result)

        setattr(final_exact_run_bundle, _BUNDLE_MARKER, True)
        setattr(final_exact_run_bundle, "_nico_previous", current_bundle)
        api_main.attach_evidence_artifact_bundle = final_exact_run_bundle
        bundle_status = "installed"

    current_gate: Callable[[dict[str, Any]], dict[str, Any]] = api_main.attach_client_acceptance_gate
    gate_status = "already_installed"
    if not getattr(current_gate, _GATE_MARKER, False):
        @wraps(current_gate)
        def authoritative_gate(result: dict[str, Any]) -> dict[str, Any]:
            before = deepcopy(result)
            after = current_gate(result)
            return normalize_assessment_completion(before, after)

        setattr(authoritative_gate, _GATE_MARKER, True)
        setattr(authoritative_gate, "_nico_previous", current_gate)
        api_main.attach_client_acceptance_gate = authoritative_gate
        client_acceptance.attach_client_acceptance_gate = authoritative_gate
        gate_status = "installed"

    current_safe: Callable[[dict[str, Any]], dict[str, Any]] = api_main.safe_assessment_response_payload
    safe_status = "already_installed"
    if not getattr(current_safe, _SAFE_MARKER, False):
        @wraps(current_safe)
        def preserve_completion_payload(result: dict[str, Any]) -> dict[str, Any]:
            normalized = normalize_assessment_completion(result, result)
            safe = current_safe(normalized)
            output = _copy_completion_fields(normalized, safe)
            completion = output.get("assessment_completion")
            if isinstance(completion, dict) and completion.get("status") == "complete_pending_human_review":
                output["status"] = "complete"
                output["current_stage"] = "complete"
                output["progress_percent"] = 100
                output["report_generation_status"] = "complete"
                output["human_review_required"] = True
                output["client_ready"] = False
                output["client_delivery_allowed"] = False
                output["delivery_status"] = "blocked_pending_human_review"
            return output

        setattr(preserve_completion_payload, _SAFE_MARKER, True)
        setattr(preserve_completion_payload, "_nico_previous", current_safe)
        api_main.safe_assessment_response_payload = preserve_completion_payload
        safe_status = "installed"

    return {
        "status": "installed" if "installed" in {bundle_status, gate_status, safe_status} else "already_installed",
        "version": PATCH_VERSION,
        "bundle_binding": bundle_status,
        "gate_binding": gate_status,
        "safe_payload_binding": safe_status,
        "exact_run_identity_bound_last": True,
        "same_run_completion_persisted": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["PATCH_VERSION", "install_express_backend_completion_transport"]
