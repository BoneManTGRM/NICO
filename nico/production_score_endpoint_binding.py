from __future__ import annotations

from importlib import import_module
from typing import Any, Callable

from nico.post_polish_score_reconciliation_patch import reconcile_after_polish

PATCH_VERSION = "nico.production_score_endpoint_binding.v1"
_MARKER = "_nico_production_score_endpoint_binding_v1"


def install_production_score_endpoint_binding(api_main: Any | None = None) -> dict[str, Any]:
    """Bind reconciliation to the last Express mutation used by sync and async routes.

    `nico.api.main` is imported before production installers execute. Patching its
    module-level `attach_client_acceptance_gate` reference here guarantees both
    the synchronous route and the asynchronous worker reconcile after report
    polishing, finalization, review-target attachment, evidence-bundle
    attachment, and client-acceptance attachment.
    """

    target = api_main if api_main is not None else import_module("nico.api.main")
    current: Callable[[dict[str, Any]], dict[str, Any]] = target.attach_client_acceptance_gate
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": PATCH_VERSION,
            "binding": "nico.api.main.attach_client_acceptance_gate",
            "sync_express_route": True,
            "async_express_route": True,
            "final_mutation_stage": True,
        }

    original = current

    def attach_acceptance_with_final_score(result: dict[str, Any]) -> dict[str, Any]:
        gated = original(result)
        return reconcile_after_polish(gated)

    setattr(attach_acceptance_with_final_score, _MARKER, True)
    setattr(attach_acceptance_with_final_score, "_nico_previous", original)
    target.attach_client_acceptance_gate = attach_acceptance_with_final_score
    setattr(target, "_nico_production_score_endpoint_binding", PATCH_VERSION)

    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "binding": "nico.api.main.attach_client_acceptance_gate",
        "sync_express_route": True,
        "async_express_route": True,
        "final_mutation_stage": True,
        "score_inflation_allowed": False,
        "guardrail": (
            "The binding only invokes existing evidence-bound reconciliation after the acceptance gate. "
            "It cannot create scanner proof, test evidence, approval, or client-ready state."
        ),
    }


__all__ = ["PATCH_VERSION", "install_production_score_endpoint_binding"]
