from __future__ import annotations

from importlib import import_module
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nico.retainer_evidence_ingestion import build_retainer_evidence_payload
from nico.retainer_truth_workflow import build_truth_bound_retainer_ops

RETAINER_AUTO_EVIDENCE_VERSION = "nico.retainer_auto_evidence_api.v1"
RETAINER_OPS_ROUTE = ("POST", "/retainer/ops")


class RetainerAutoOpsRequest(BaseModel):
    repository: str = ""
    authorized: bool = False
    authorized_by: str = "unspecified"
    authorization_scope: str = "repository assessment and retainer evidence review only"
    client_name: str = ""
    project_name: str = ""
    customer_id: str = "default_customer"
    project_id: str = "default_project"
    baseline_run_id: str = ""
    timeframe_days: int = Field(default=30, ge=1, le=365)
    refresh_evidence: bool = True
    roadmap_notes: str = ""
    client_update: str = ""
    retainer_metrics: str = ""
    success_metrics: str = ""
    budget_priorities: str = ""
    # Legacy technical fields remain accepted for request compatibility, but the
    # production path replaces them with GitHub-derived evidence when a repository
    # source is bound.
    commit_summary: str = ""
    pr_summary: str = ""
    issue_summary: str = ""
    blockers: str = ""
    release_notes: str = ""


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in target.routes:
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), path))
    return pairs


def _remove_existing_retainer_route(target: FastAPI) -> int:
    retained = []
    removed = 0
    for route in target.router.routes:
        path = str(getattr(route, "path", ""))
        methods = {
            str(method).upper()
            for method in (getattr(route, "methods", set()) or set())
        }
        if path == RETAINER_OPS_ROUTE[1] and RETAINER_OPS_ROUTE[0] in methods:
            removed += 1
            continue
        retained.append(route)
    target.router.routes[:] = retained
    return removed


def _bounded_storage_record(
    request_payload: dict[str, Any],
    result: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    customer_id = str(request_payload.get("customer_id") or "default_customer")
    project_id = str(request_payload.get("project_id") or "default_project")
    repository = str(result.get("repository") or request_payload.get("repository") or "")
    source_binding = result.get("source_binding") if isinstance(result.get("source_binding"), dict) else {}
    baseline = source_binding.get("baseline") if isinstance(source_binding.get("baseline"), dict) else {}
    record_id = f"retainer_{customer_id}_{project_id}"
    return record_id, {
        "workflow": "retainer",
        "customer_id": customer_id,
        "project_id": project_id,
        "repository": repository,
        "status": str(result.get("status") or "needs_more_retainer_evidence"),
        "request": {
            "repository": repository,
            "customer_id": customer_id,
            "project_id": project_id,
            "authorized_by": str(request_payload.get("authorized_by") or "unspecified")[:120],
            "authorization_scope": str(request_payload.get("authorization_scope") or "")[:240],
            "baseline_run_id": str(request_payload.get("baseline_run_id") or ""),
            "timeframe_days": int(request_payload.get("timeframe_days") or 30),
        },
        "source_binding": {
            "status": source_binding.get("status"),
            "repository": source_binding.get("repository"),
            "observed_commit_sha": source_binding.get("observed_commit_sha"),
            "checked_at": source_binding.get("checked_at"),
            "baseline_run_id": baseline.get("run_id"),
            "snapshot_id": baseline.get("snapshot_id"),
            "snapshot_commit_sha": baseline.get("snapshot_commit_sha"),
            "scanner_id": baseline.get("scanner_id"),
        },
        "summary": {
            "maturity_signal": result.get("maturity_signal"),
            "evidence_readiness": result.get("evidence_readiness"),
            "section_statuses": {
                str(item.get("id") or "unknown"): {
                    "status": item.get("status"),
                    "score": item.get("score"),
                    "score_calculated": item.get("score_calculated"),
                }
                for item in result.get("sections") or []
                if isinstance(item, dict)
            },
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    }


def install_retainer_auto_evidence(target: FastAPI) -> dict[str, Any]:
    existing_pairs = _route_pairs(target)
    already_installed = bool(
        getattr(target.state, "retainer_auto_evidence_version", "")
        == RETAINER_AUTO_EVIDENCE_VERSION
        and RETAINER_OPS_ROUTE in existing_pairs
    )
    if already_installed:
        return {
            "installed": True,
            "idempotent_reuse": True,
            "version": RETAINER_AUTO_EVIDENCE_VERSION,
            "route": "POST /retainer/ops",
        }

    removed = _remove_existing_retainer_route(target)
    main = import_module("nico.api.main")

    @target.post("/retainer/ops", tags=["retainer"])
    def hosted_retainer_ops(req: RetainerAutoOpsRequest):
        request_payload = req.model_dump()
        if not bool(request_payload.get("authorized")):
            result = build_truth_bound_retainer_ops(request_payload)
            raise main.safe_blocked_exception(result)

        enriched = build_retainer_evidence_payload(
            request_payload,
            latest_express=getattr(main, "_LAST_HOSTED_ASSESSMENT", {}) or {},
            latest_mid=getattr(main, "_LAST_MID_ASSESSMENT", {}) or {},
            store=main.STORE,
        )
        result = build_truth_bound_retainer_ops(enriched)
        if result.get("status") == "blocked":
            raise main.safe_blocked_exception(result)
        response_payload = main.safe_assessment_response_payload(result)
        main._LAST_RETAINER_OPS = response_payload
        record_id, storage_record = _bounded_storage_record(enriched, response_payload)
        main.STORE.put("assessment_runs", record_id, storage_record)
        return JSONResponse(content=response_payload)

    target.state.retainer_auto_evidence_version = RETAINER_AUTO_EVIDENCE_VERSION
    target.openapi_schema = None
    route_count = sum(
        1
        for route in target.routes
        if str(getattr(route, "path", "")) == RETAINER_OPS_ROUTE[1]
        and RETAINER_OPS_ROUTE[0]
        in {
            str(method).upper()
            for method in (getattr(route, "methods", set()) or set())
        }
    )
    if route_count != 1:
        raise RuntimeError(
            "Retainer auto-evidence installation must produce exactly one POST /retainer/ops route"
        )
    return {
        "installed": True,
        "idempotent_reuse": False,
        "version": RETAINER_AUTO_EVIDENCE_VERSION,
        "route": "POST /retainer/ops",
        "legacy_routes_removed": removed,
        "technical_evidence_mode": "automatic_github_ingestion",
        "manual_context_fields": [
            "roadmap_notes",
            "client_update",
            "retainer_metrics",
            "success_metrics",
            "budget_priorities",
        ],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "RETAINER_AUTO_EVIDENCE_VERSION",
    "RETAINER_OPS_ROUTE",
    "RetainerAutoOpsRequest",
    "install_retainer_auto_evidence",
]
