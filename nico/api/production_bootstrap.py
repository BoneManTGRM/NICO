from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

import nico.express_async_api as express
from nico.api.production import app as production_app
from nico.assessment_block_messages import install_assessment_block_messages
from nico.durable_runtime_storage import install_durable_runtime_storage
from nico.express_backend_diagnostics import EXPRESS_BACKEND_DIAGNOSTICS_VERSION
from nico.express_runtime_heartbeat import install_express_runtime_heartbeat
from nico.express_status_liveness_patch import install_express_status_liveness_patch
from nico.lifecycle_status_hardening import install_lifecycle_status_hardening
from nico.mid_live_status_api import MID_LIVE_STATUS_ROUTE, register_mid_live_status_routes
from nico.mid_runtime_diagnostics import register_mid_runtime_diagnostics
from nico.postgres_timeout_patch import install_postgres_timeout_patch
from nico.runtime_heartbeat_atomic_patch import install_runtime_heartbeat_atomic_patch
from nico.runtime_storage_truth_patch import install_runtime_storage_truth
from nico.scanner_redaction_safety import (
    SCANNER_REDACTION_SAFETY_VERSION,
    install_scanner_redaction_safety,
    scanner_redaction_safety_status,
)
from nico.snapshot_scanner_heartbeat_patch import install_snapshot_scanner_heartbeat
from nico.storage import STORE
from nico.storage_serialization_safety import (
    STORAGE_SERIALIZATION_SAFETY_VERSION,
    install_storage_serialization_safety,
)

EXPRESS_RUNTIME_DIAGNOSTICS_ROUTE = "/diagnostics/express-runtime"
EXPRESS_RUNTIME_REQUIRED_ROUTES = {
    ("POST", "/assessment/express-run"),
    ("POST", "/assessment/express-run/{run_id}/status"),
}


def _durable_required() -> bool:
    return (
        bool(os.getenv("DATABASE_URL", "").strip())
        or os.getenv("NICO_REQUIRE_DURABLE_ASSESSMENT_STORAGE", "false").strip().lower() == "true"
        or os.getenv("NICO_ENABLE_SQLITE_DURABLE_STORAGE", "false").strip().lower() == "true"
    )


def _configured_workers() -> int:
    try:
        return max(1, int(os.getenv("NICO_WEB_WORKERS", "1")))
    except (TypeError, ValueError):
        return 1


def _route_count(target: FastAPI, method: str, path: str) -> int:
    expected = method.upper()
    return sum(
        1
        for route in target.routes
        if str(getattr(route, "path", "")) == path
        and expected in {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
    )


def _express_backend_contract() -> dict[str, Any]:
    bootstrap = globals().get("EXPRESS_PRODUCTION_BOOTSTRAP")
    if not isinstance(bootstrap, dict):
        return {}
    value = bootstrap.get("express_backend_diagnostics")
    return value if isinstance(value, dict) else {}


def _serialization_contract() -> dict[str, Any]:
    value = globals().get("STORAGE_SERIALIZATION_SAFETY")
    return value if isinstance(value, dict) else {}


def express_runtime_status(target: FastAPI) -> dict[str, Any]:
    worker = express._execute
    route_counts = {
        f"{method} {path}": _route_count(target, method, path)
        for method, path in sorted(EXPRESS_RUNTIME_REQUIRED_ROUTES)
    }
    diagnostics_installed = bool(getattr(worker, "_nico_express_backend_diagnostics_v1", False))
    heartbeat_installed = bool(getattr(worker, "_nico_express_runtime_heartbeat_v1", False))
    atomic_heartbeat_installed = callable(getattr(STORE, "patch_heartbeat", None))
    serialization = _serialization_contract()
    serialization_installed = bool(
        serialization.get("storage_metadata_boundary_installed")
        and serialization.get("sqlite_metadata_boundary_installed")
        and serialization.get("express_scanner_boundary_installed")
    )
    backend_contract = _express_backend_contract()
    exact_snapshot_scanner_required = bool(backend_contract.get("exact_snapshot_scanner_required"))
    report_artifact_gate = bool(backend_contract.get("report_artifact_gate"))
    same_run_scanner_identity_required = bool(
        backend_contract.get("same_run_scanner_identity_required")
        or (exact_snapshot_scanner_required and report_artifact_gate)
    )
    report_without_scanner_allowed = bool(
        backend_contract.get(
            "report_without_scanner_allowed",
            not (exact_snapshot_scanner_required and report_artifact_gate),
        )
    )
    redaction = scanner_redaction_safety_status()
    storage = STORE.status()
    durable_required = _durable_required()
    persistence_available = bool(storage.get("persistence_available"))
    durability_verified = bool(storage.get("durability_verified", storage.get("adapter") == "postgres"))
    workers = _configured_workers()
    ready = (
        diagnostics_installed
        and heartbeat_installed
        and atomic_heartbeat_installed
        and serialization_installed
        and exact_snapshot_scanner_required
        and same_run_scanner_identity_required
        and report_artifact_gate
        and not report_without_scanner_allowed
        and redaction["cycle_safe_redaction_installed"]
        and (persistence_available or not durable_required)
        and all(count == 1 for count in route_counts.values())
    )
    return {
        "status": "ok" if ready else "blocked",
        "version": EXPRESS_BACKEND_DIAGNOSTICS_VERSION,
        "bounded_backend_diagnostics_installed": diagnostics_installed,
        "durable_lifecycle_heartbeat_installed": heartbeat_installed,
        "atomic_heartbeat_status_guard_installed": atomic_heartbeat_installed,
        "storage_serialization_safety_version": STORAGE_SERIALIZATION_SAFETY_VERSION,
        "cycle_safe_storage_serialization_installed": serialization_installed,
        "circular_scanner_evidence_is_terminal": False,
        "storage_serialization_maximum_depth": serialization.get("maximum_depth"),
        "heartbeat_can_reopen_terminal_state": False,
        "status_read_can_write_terminal_interruption": False,
        "scanner_liveness_corroboration": True,
        "worker_name": str(getattr(worker, "__name__", "unknown"))[:120],
        "configured_web_workers": workers,
        "single_worker_default": workers == 1,
        "route_counts": route_counts,
        "scanner_redaction_safety_version": SCANNER_REDACTION_SAFETY_VERSION,
        "cycle_safe_scanner_redaction_installed": redaction["cycle_safe_redaction_installed"],
        "scanner_redaction_maximum_depth": redaction["maximum_depth"],
        "exact_snapshot_scanner_required": exact_snapshot_scanner_required,
        "same_run_scanner_identity_required": same_run_scanner_identity_required,
        "report_artifact_gate": report_artifact_gate,
        "report_without_scanner_allowed": report_without_scanner_allowed,
        "storage_adapter": storage.get("adapter") or "unknown",
        "storage_recording_available": persistence_available,
        "durable_storage_required": durable_required,
        "durable_storage_ready": persistence_available,
        "durability_verified": durability_verified,
        "survives_container_replacement_verified": durability_verified,
        "durability_warning": storage.get("durability_warning") or "",
        "memory_storage_accepted": not durable_required,
        "request_validation_422_possible": False,
        "single_start_only": True,
        "replacement_run_allowed": False,
        "automatic_retry_allowed": False,
        "human_review_required": True,
        "client_ready": False,
    }


def _register_runtime_diagnostics(target: FastAPI) -> None:
    if _route_count(target, "GET", EXPRESS_RUNTIME_DIAGNOSTICS_ROUTE):
        return

    def runtime_diagnostics() -> dict[str, Any]:
        return express_runtime_status(target)

    target.add_api_route(
        EXPRESS_RUNTIME_DIAGNOSTICS_ROUTE,
        runtime_diagnostics,
        methods=["GET"],
        tags=["diagnostics"],
    )
    target.openapi_schema = None


DURABLE_RUNTIME_STORAGE = install_durable_runtime_storage()
STORAGE_SERIALIZATION_SAFETY = install_storage_serialization_safety()
RUNTIME_HEARTBEAT_ATOMIC = install_runtime_heartbeat_atomic_patch()
RUNTIME_STORAGE_TRUTH = install_runtime_storage_truth()
POSTGRES_TIMEOUTS = install_postgres_timeout_patch()
SCANNER_REDACTION_SAFETY = install_scanner_redaction_safety()
SNAPSHOT_SCANNER_HEARTBEAT = install_snapshot_scanner_heartbeat()
EXPRESS_PRODUCTION_BOOTSTRAP = install_assessment_block_messages()
EXPRESS_RUNTIME_HEARTBEAT = install_express_runtime_heartbeat()
app = production_app
MID_LIVE_STATUS = register_mid_live_status_routes(app)
LIFECYCLE_STATUS_HARDENING = install_lifecycle_status_hardening(app)
EXPRESS_STATUS_LIVENESS = install_express_status_liveness_patch()
MID_RUNTIME = register_mid_runtime_diagnostics(app)
_register_runtime_diagnostics(app)
EXPRESS_PRODUCTION_RUNTIME = express_runtime_status(app)

if _durable_required() and not STORE.status().get("persistence_available"):
    raise RuntimeError(f"Assessment lifecycle storage is unavailable: {STORE.status()}")
if not STORAGE_SERIALIZATION_SAFETY.get("storage_metadata_boundary_installed"):
    raise RuntimeError("Production bootstrap did not install cycle-safe storage serialization")
if not STORAGE_SERIALIZATION_SAFETY.get("sqlite_metadata_boundary_installed"):
    raise RuntimeError("SQLite runtime storage is not bound to cycle-safe serialization")
if not STORAGE_SERIALIZATION_SAFETY.get("express_scanner_boundary_installed"):
    raise RuntimeError("Express scanner projection is not bound to cycle-safe serialization")
if not SCANNER_REDACTION_SAFETY["cycle_safe_redaction_installed"]:
    raise RuntimeError("Express production bootstrap did not install cycle-safe scanner redaction")
if not EXPRESS_PRODUCTION_RUNTIME["bounded_backend_diagnostics_installed"]:
    raise RuntimeError("Express production bootstrap did not install bounded backend diagnostics")
if not EXPRESS_PRODUCTION_RUNTIME["durable_lifecycle_heartbeat_installed"]:
    raise RuntimeError("Express production bootstrap did not install lifecycle heartbeats")
if not EXPRESS_PRODUCTION_RUNTIME["atomic_heartbeat_status_guard_installed"]:
    raise RuntimeError("Express production bootstrap did not install atomic heartbeat status guards")
if not EXPRESS_PRODUCTION_RUNTIME["cycle_safe_storage_serialization_installed"]:
    raise RuntimeError("Express production runtime did not verify cycle-safe storage serialization")
if EXPRESS_PRODUCTION_RUNTIME["status_read_can_write_terminal_interruption"]:
    raise RuntimeError("Express status reads can still write terminal interruption evidence")
if not EXPRESS_PRODUCTION_RUNTIME["exact_snapshot_scanner_required"]:
    raise RuntimeError("Express production bootstrap does not require exact-snapshot scanner execution")
if not EXPRESS_PRODUCTION_RUNTIME["same_run_scanner_identity_required"]:
    raise RuntimeError("Express production bootstrap does not require same-run scanner identity")
if not EXPRESS_PRODUCTION_RUNTIME["report_artifact_gate"]:
    raise RuntimeError("Express production bootstrap does not require complete report artifacts")
if EXPRESS_PRODUCTION_RUNTIME["report_without_scanner_allowed"]:
    raise RuntimeError("Express production bootstrap still permits reports without scanner completion")
if any(count != 1 for count in EXPRESS_PRODUCTION_RUNTIME["route_counts"].values()):
    raise RuntimeError(
        f"Express production routes are missing or duplicated: {EXPRESS_PRODUCTION_RUNTIME['route_counts']}"
    )
if _route_count(app, MID_LIVE_STATUS_ROUTE[0], MID_LIVE_STATUS_ROUTE[1]) != 1:
    raise RuntimeError("Mid live-status route must be registered exactly once")
if not SNAPSHOT_SCANNER_HEARTBEAT.get("source_runner_binding_installed"):
    raise RuntimeError("Scanner heartbeat wrapper is not bound to the source tool runner")
if not SNAPSHOT_SCANNER_HEARTBEAT.get("snapshot_worker_binding_installed"):
    raise RuntimeError("Scanner heartbeat wrapper is not bound to the snapshot worker's scanner-tool module alias")
if LIFECYCLE_STATUS_HARDENING.get("express_request_validation_422_possible"):
    raise RuntimeError("Express status route can still emit framework validation HTTP 422")
if LIFECYCLE_STATUS_HARDENING.get("mid_generic_http_500_possible"):
    raise RuntimeError("Mid live-status route can still emit an unbounded generic HTTP 500")
if MID_RUNTIME.get("status") != "ok":
    raise RuntimeError(f"Mid production runtime diagnostics are blocked: {MID_RUNTIME}")
if EXPRESS_PRODUCTION_RUNTIME.get("status") != "ok":
    raise RuntimeError(f"Express production runtime diagnostics are blocked: {EXPRESS_PRODUCTION_RUNTIME}")

app.state.nico_durable_runtime_storage = DURABLE_RUNTIME_STORAGE
app.state.nico_storage_serialization_safety = STORAGE_SERIALIZATION_SAFETY
app.state.nico_runtime_heartbeat_atomic = RUNTIME_HEARTBEAT_ATOMIC
app.state.nico_runtime_storage_truth = RUNTIME_STORAGE_TRUTH
app.state.nico_postgres_timeouts = POSTGRES_TIMEOUTS
app.state.nico_scanner_redaction_safety = SCANNER_REDACTION_SAFETY
app.state.nico_snapshot_scanner_heartbeat = SNAPSHOT_SCANNER_HEARTBEAT
app.state.nico_express_production_bootstrap = EXPRESS_PRODUCTION_BOOTSTRAP
app.state.nico_express_runtime_heartbeat = EXPRESS_RUNTIME_HEARTBEAT
app.state.nico_lifecycle_status_hardening = LIFECYCLE_STATUS_HARDENING
app.state.nico_express_status_liveness = EXPRESS_STATUS_LIVENESS
app.state.nico_express_production_runtime = EXPRESS_PRODUCTION_RUNTIME
app.state.nico_mid_live_status = MID_LIVE_STATUS
app.state.nico_mid_runtime = MID_RUNTIME

__all__ = [
    "app",
    "DURABLE_RUNTIME_STORAGE",
    "STORAGE_SERIALIZATION_SAFETY",
    "RUNTIME_HEARTBEAT_ATOMIC",
    "RUNTIME_STORAGE_TRUTH",
    "POSTGRES_TIMEOUTS",
    "SCANNER_REDACTION_SAFETY",
    "SNAPSHOT_SCANNER_HEARTBEAT",
    "EXPRESS_PRODUCTION_BOOTSTRAP",
    "EXPRESS_RUNTIME_HEARTBEAT",
    "LIFECYCLE_STATUS_HARDENING",
    "EXPRESS_STATUS_LIVENESS",
    "EXPRESS_PRODUCTION_RUNTIME",
    "MID_LIVE_STATUS",
    "MID_RUNTIME",
    "EXPRESS_RUNTIME_DIAGNOSTICS_ROUTE",
    "EXPRESS_RUNTIME_REQUIRED_ROUTES",
    "express_runtime_status",
]
