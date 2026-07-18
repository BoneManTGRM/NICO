from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

import nico.client_acceptance as client_acceptance
from nico.express_final_gate_completion_patch import normalize_assessment_completion

PATCH_VERSION = "nico.express_backend_completion_transport.v1"
_GATE_MARKER = "_nico_express_backend_completion_gate_v1"
_SAFE_MARKER = "_nico_express_backend_completion_safe_payload_v1"
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
    """Make Express completion authoritative before persistence and status transport.

    The async runner reached report generation successfully, but the final response
    could remain ``running`` because the last gate binding and safe-response reducer
    did not preserve the canonical completion contract. This installer normalizes
    the final gate on the live API reference, then carries the resulting completion,
    score, section, and report evidence through the safe response boundary so the
    same run can be persisted as complete pending human review.
    """

    from nico.api import main as api_main

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
        "status": "installed" if "installed" in {gate_status, safe_status} else "already_installed",
        "version": PATCH_VERSION,
        "gate_binding": gate_status,
        "safe_payload_binding": safe_status,
        "same_run_completion_persisted": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["PATCH_VERSION", "install_express_backend_completion_transport"]
