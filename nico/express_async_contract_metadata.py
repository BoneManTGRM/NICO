from __future__ import annotations

from functools import wraps
from typing import Any, Callable

_MARKER = "_nico_express_async_contract_metadata_v6"
_EXACT_RUN_BUNDLE_MARKER = "_nico_express_exact_run_bundle_dispatch_v1"


def install_express_async_contract_metadata() -> dict[str, Any]:
    from nico import express_async_api
    from nico.api import main as api_main
    from nico.express_report_generation_recovery import install_express_report_generation_recovery
    from nico.express_final_gate_checkpoint_patch import install_express_final_gate_checkpoint_patch
    from nico.express_backend_final_gate_truth import install_express_backend_final_gate_truth
    from nico.express_evidence_bundle_fast_path import (
        attach_express_evidence_bundle,
        install_express_evidence_bundle_fast_path,
    )

    report_recovery = install_express_report_generation_recovery()
    final_gate_checkpoint = install_express_final_gate_checkpoint_patch()
    evidence_bundle_fast_path = install_express_evidence_bundle_fast_path()

    current_bundle: Callable[[dict[str, Any]], dict[str, Any]] = api_main.attach_evidence_artifact_bundle
    if not getattr(current_bundle, _EXACT_RUN_BUNDLE_MARKER, False):
        @wraps(current_bundle)
        def attach_exact_run_bundle(result: dict[str, Any]) -> dict[str, Any]:
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

        setattr(attach_exact_run_bundle, _EXACT_RUN_BUNDLE_MARKER, True)
        setattr(attach_exact_run_bundle, "_nico_previous", current_bundle)
        api_main.attach_evidence_artifact_bundle = attach_exact_run_bundle
        exact_run_bundle_dispatch = {
            "status": "installed",
            "exact_run_identity": True,
            "tier_metadata_stamped_before_bundle": True,
        }
    else:
        exact_run_bundle_dispatch = {
            "status": "already_installed",
            "exact_run_identity": True,
            "tier_metadata_stamped_before_bundle": True,
        }

    backend_final_gate = install_express_backend_final_gate_truth()
    current = express_async_api.register_express_async_routes
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "report_generation_recovery": report_recovery,
            "final_gate_checkpoint": final_gate_checkpoint,
            "evidence_bundle_fast_path": evidence_bundle_fast_path,
            "exact_run_bundle_dispatch": exact_run_bundle_dispatch,
            "backend_final_gate": backend_final_gate,
        }

    def register_with_contract_metadata(app):
        result = dict(current(app))
        result.update(
            {
                "single_long_browser_connection_required": False,
                "exact_run_polling": True,
                "duplicate_active_scope_start_prevented": True,
                "max_active_runs": express_async_api.MAX_ACTIVE_EXPRESS_RUNS,
                "staged_progress_available": True,
                "progress_source": "backend_stage_records",
                "report_generation_recovery": report_recovery,
                "final_gate_checkpoint": final_gate_checkpoint,
                "evidence_bundle_fast_path": evidence_bundle_fast_path,
                "exact_run_bundle_dispatch": exact_run_bundle_dispatch,
                "backend_final_gate": backend_final_gate,
            }
        )
        return result

    setattr(register_with_contract_metadata, _MARKER, True)
    setattr(register_with_contract_metadata, "_nico_previous", current)
    express_async_api.register_express_async_routes = register_with_contract_metadata
    return {
        "status": "installed",
        "staged_progress_available": True,
        "report_generation_recovery": report_recovery,
        "final_gate_checkpoint": final_gate_checkpoint,
        "evidence_bundle_fast_path": evidence_bundle_fast_path,
        "exact_run_bundle_dispatch": exact_run_bundle_dispatch,
        "backend_final_gate": backend_final_gate,
    }


__all__ = ["install_express_async_contract_metadata"]
