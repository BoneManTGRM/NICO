from __future__ import annotations

from importlib import import_module
import sys
from typing import Any, Callable

PATCH_VERSION = "nico.express_completion_score_binding.v1"
_RESPONSE_MARKER = "_nico_express_completion_score_response_v1"
_EXECUTE_MARKER = "_nico_express_completion_score_execute_v1"
_BOOTSTRAP_MARKER = "_nico_express_completion_score_bootstrap_v1"


def bind_api_main_response(api_main: Any) -> dict[str, Any]:
    """Bind reconciliation to the final response boundary used by Express routes."""

    current = getattr(api_main, "safe_assessment_response_payload", None)
    if not callable(current):
        return {
            "status": "unavailable",
            "reason": "safe_assessment_response_payload_not_loaded",
        }
    if getattr(current, _RESPONSE_MARKER, False):
        return {
            "status": "already_installed",
            "response_boundary_reconciled": True,
        }
    original: Callable[[Any], dict[str, Any]] = current

    def safe_response_with_final_reconciliation(value: Any) -> dict[str, Any]:
        from nico.post_polish_score_reconciliation_patch import reconcile_after_polish

        reconciled = (
            reconcile_after_polish(value)
            if isinstance(value, dict) and value.get("status") == "complete"
            else value
        )
        return original(reconciled)

    setattr(safe_response_with_final_reconciliation, _RESPONSE_MARKER, True)
    setattr(safe_response_with_final_reconciliation, "_nico_previous", original)
    api_main.safe_assessment_response_payload = safe_response_with_final_reconciliation
    return {
        "status": "installed",
        "response_boundary_reconciled": True,
    }


def _patch_async_execute() -> dict[str, Any]:
    from nico import express_async_api

    current = express_async_api._execute
    if getattr(current, _EXECUTE_MARKER, False):
        return {
            "status": "already_installed",
            "async_execute_bound": True,
        }
    original = current

    def execute_with_final_response_binding(
        run_id: str,
        request_payload: dict[str, Any],
    ) -> None:
        api_main = import_module("nico.api.main")
        bind_api_main_response(api_main)
        original(run_id, request_payload)

    setattr(execute_with_final_response_binding, _EXECUTE_MARKER, True)
    setattr(execute_with_final_response_binding, "_nico_previous", original)
    express_async_api._execute = execute_with_final_response_binding
    return {
        "status": "installed",
        "async_execute_bound": True,
    }


def _patch_production_bootstrap() -> dict[str, Any]:
    from nico import assessment_score_integrity

    current = assessment_score_integrity.install_assessment_score_integrity
    if getattr(current, _BOOTSTRAP_MARKER, False):
        return {
            "status": "already_installed",
            "production_bootstrap_bound": True,
        }
    original = current

    def install_score_integrity_with_response_binding() -> dict[str, Any]:
        result = original()
        api_main = import_module("nico.api.main")
        binding = bind_api_main_response(api_main)
        if isinstance(result, dict):
            enriched = dict(result)
            enriched["express_completion_score_binding"] = binding
            return enriched
        return {
            "status": "installed",
            "score_integrity_result_type": type(result).__name__,
            "express_completion_score_binding": binding,
        }

    setattr(install_score_integrity_with_response_binding, _BOOTSTRAP_MARKER, True)
    setattr(install_score_integrity_with_response_binding, "_nico_previous", original)
    assessment_score_integrity.install_assessment_score_integrity = install_score_integrity_with_response_binding
    return {
        "status": "installed",
        "production_bootstrap_bound": True,
    }


def install_express_completion_score_binding() -> dict[str, Any]:
    bootstrap = _patch_production_bootstrap()
    async_execute = _patch_async_execute()

    immediate = {
        "status": "not_loaded",
        "reason": "nico.api.main_not_loaded_during_package_install",
    }
    api_main = sys.modules.get("nico.api.main")
    if api_main is not None:
        immediate = bind_api_main_response(api_main)

    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "production_bootstrap": bootstrap,
        "async_execute": async_execute,
        "immediate_api_binding": immediate,
        "final_response_boundary": "safe_assessment_response_payload",
        "score_inflation_allowed": False,
        "guardrail": (
            "The response-bound reconciliation can only apply evidence already present in the completed assessment. "
            "It cannot create scanner proof, test evidence, acceptance, human approval, or client-ready state."
        ),
    }


__all__ = [
    "PATCH_VERSION",
    "bind_api_main_response",
    "install_express_completion_score_binding",
]
