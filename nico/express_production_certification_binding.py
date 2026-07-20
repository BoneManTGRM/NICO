from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from nico.express_production_certification import build_express_production_certification

VERSION = "nico.express_production_certification_binding.v1"
_PATCH_MARKER = "_nico_express_production_certification_binding_v1"


def install_express_production_certification_binding() -> dict[str, Any]:
    from nico import express_async_api

    current: Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any]] = express_async_api._record
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def certified_record(run_id: str, request_payload: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
        prior_runs = response.get("prior_same_sha_runs") if isinstance(response.get("prior_same_sha_runs"), list) else []
        build_express_production_certification(response, prior_runs=prior_runs)
        certification = response["express_production_certification"]
        if certification.get("status") != "certified_pending_human_review":
            response["client_ready"] = False
            response["client_delivery_allowed"] = False
            response["delivery_status"] = "blocked_pending_production_certification"
            response["client_delivery_block_reason"] = (
                "Express production certification is incomplete; exact deployment identity, durable restart retrieval, "
                "two same-SHA matching runs, and full artifact inspection are required."
            )
        return current(run_id, request_payload, response)

    setattr(certified_record, _PATCH_MARKER, True)
    setattr(certified_record, "_nico_previous", current)
    express_async_api._record = certified_record
    return {
        "status": "installed",
        "version": VERSION,
        "exact_snapshot_identity_required": True,
        "frontend_backend_deployment_identity_required": True,
        "restart_persistence_required": True,
        "two_same_sha_runs_required": True,
        "full_artifact_inspection_required": True,
        "human_review_required": True,
    }


__all__ = ["VERSION", "install_express_production_certification_binding"]
