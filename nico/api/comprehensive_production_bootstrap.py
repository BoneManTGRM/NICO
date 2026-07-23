from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from nico.api.production_bootstrap import app as production_app
from nico.comprehensive_api_routes import COMPREHENSIVE_API_ROUTES
from nico.comprehensive_decision_grade_v5 import install_decision_grade_binding
from nico.comprehensive_exact_commit_intake_repair import install_comprehensive_exact_commit_intake_repair
from nico.comprehensive_native_providers import install_native_comprehensive_providers
from nico.comprehensive_production_bootstrap import install_comprehensive_production_bootstrap
from nico.comprehensive_production_capabilities import build_production_capability_executors
from nico.comprehensive_report_appendix_v3 import install_native_provider_binding
from nico.final_report_package_v1 import install_final_report_package_v1

VERSION = "nico.api.comprehensive_production_bootstrap.v6"
COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE = "/diagnostics/comprehensive-runtime"


def _route_count(target: FastAPI, method: str, path: str) -> int:
    expected = method.upper()
    return sum(
        1
        for route in target.routes
        if str(getattr(route, "path", "")) == path
        and expected in {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
    )


def _register_runtime_diagnostics(target: FastAPI) -> None:
    if _route_count(target, "GET", COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE):
        return

    def runtime_diagnostics() -> dict[str, Any]:
        status = dict(getattr(target.state, "nico_comprehensive_production_runtime", {}) or {})
        status.setdefault("artifact_schema", VERSION)
        status.setdefault("service_id", "comprehensive")
        status["human_review_required"] = True
        status["client_delivery_allowed"] = False
        return status

    target.add_api_route(
        COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE,
        runtime_diagnostics,
        methods=["GET"],
        tags=["diagnostics"],
    )
    target.openapi_schema = None


def install_comprehensive_on_production_app(target: FastAPI) -> dict[str, Any]:
    """Mount the decision-grade native Comprehensive boundary.

    The compatibility appendix binding and then the decision-grade binding are
    installed before native providers and before the executor map is built. The
    decision-grade layer remains canonical while preserving the established
    appendix bootstrap contract used by prior releases and regression tests.
    Human review remains mandatory and client delivery remains blocked.
    """

    report_binding = install_native_provider_binding()
    legacy_report_binding = report_binding
    report_binding = install_decision_grade_binding()
    exact_commit_intake_repair = install_comprehensive_exact_commit_intake_repair()
    final_report_binding = install_final_report_package_v1()
    native_providers = install_native_comprehensive_providers(target)
    executors = build_production_capability_executors(target)
    controller = install_comprehensive_production_bootstrap(
        target,
        capability_executors=executors,
    )
    route_counts = {
        f"{method} {path}": _route_count(target, method, path)
        for method, path in sorted(COMPREHENSIVE_API_ROUTES)
    }
    runtime = dict(getattr(target.state, "comprehensive_runtime", {}) or {})
    provider_status = dict(
        getattr(target.state, "nico_comprehensive_capability_provider_status", {}) or {}
    )
    native_status = dict(
        getattr(target.state, "nico_native_comprehensive_provider_status", {}) or {}
    )
    missing_capabilities = list(provider_status.get("missing_capabilities") or [])
    final_report_ready = (
        final_report_binding.get("report_finalized") is True
        and final_report_binding.get("human_review_required") is True
        and final_report_binding.get("client_delivery_allowed") is False
    )
    intake_repair_ready = exact_commit_intake_repair.get("status") in {"installed", "already_installed"}
    ready = (
        controller is not None
        and runtime.get("configured") is True
        and runtime.get("status") == "ready"
        and runtime.get("client_delivery_allowed") is False
        and runtime.get("human_review_required") is True
        and legacy_report_binding.get("bound") is True
        and report_binding.get("bound") is True
        and report_binding.get("canonical_scoring_bound") is True
        and report_binding.get("secret_category_isolated") is True
        and report_binding.get("score_band_separated_from_assurance") is True
        and final_report_ready
        and intake_repair_ready
        and len(native_providers) > 0
        and not missing_capabilities
        and all(count == 1 for count in route_counts.values())
    )
    status = {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "status": "ready" if ready else "blocked",
        "configured": bool(runtime.get("configured")),
        "reason": str(runtime.get("reason") or ("comprehensive_native_providers_missing" if missing_capabilities else "")),
        "persistence_adapter": str(runtime.get("persistence_adapter") or "unavailable"),
        "route_counts": route_counts,
        "legacy_report_binding": legacy_report_binding,
        "report_binding": report_binding,
        "final_report_binding": final_report_binding,
        "exact_commit_intake_repair": exact_commit_intake_repair,
        "native_provider_status": native_status,
        "capability_provider_status": provider_status,
        "native_provider_count": len(native_providers),
        "missing_capabilities": missing_capabilities,
        "report_binding_before_provider_install": True,
        "final_report_binding_before_executor_build": True,
        "provider_install_before_executor_build": True,
        "diagnostics_route": COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE,
        "report_state": "final_report_pending_human_approval",
        "report_finalized": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    target.state.nico_comprehensive_production_runtime = status
    _register_runtime_diagnostics(target)
    status["diagnostics_route_count"] = _route_count(
        target,
        "GET",
        COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE,
    )
    target.state.nico_comprehensive_production_runtime = status
    return status


app = production_app
COMPREHENSIVE_PRODUCTION_RUNTIME = install_comprehensive_on_production_app(app)

if any(count != 1 for count in COMPREHENSIVE_PRODUCTION_RUNTIME["route_counts"].values()):
    raise RuntimeError(
        "Comprehensive production routes are missing or duplicated: "
        f"{COMPREHENSIVE_PRODUCTION_RUNTIME['route_counts']}"
    )
if COMPREHENSIVE_PRODUCTION_RUNTIME["diagnostics_route_count"] != 1:
    raise RuntimeError("Comprehensive runtime diagnostics route must be registered exactly once")
if COMPREHENSIVE_PRODUCTION_RUNTIME["legacy_report_binding"].get("bound") is not True:
    raise RuntimeError("Legacy Comprehensive appendix compatibility binding was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["report_binding"].get("bound") is not True:
    raise RuntimeError("Decision-grade Comprehensive report binding was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["report_binding"].get("canonical_scoring_bound") is not True:
    raise RuntimeError("Decision-grade Comprehensive scoring binding was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["final_report_binding"].get("report_finalized") is not True:
    raise RuntimeError("Final report package binding was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["exact_commit_intake_repair"].get("status") not in {"installed", "already_installed"}:
    raise RuntimeError("Comprehensive exact-commit intake repair was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["native_provider_count"] < 1:
    raise RuntimeError("Comprehensive production runtime did not install native providers")
if COMPREHENSIVE_PRODUCTION_RUNTIME["missing_capabilities"]:
    raise RuntimeError(
        "Comprehensive production runtime has missing capabilities: "
        f"{COMPREHENSIVE_PRODUCTION_RUNTIME['missing_capabilities']}"
    )
if COMPREHENSIVE_PRODUCTION_RUNTIME["human_review_required"] is not True:
    raise RuntimeError("Comprehensive production runtime must require human review")
if COMPREHENSIVE_PRODUCTION_RUNTIME["client_delivery_allowed"] is not False:
    raise RuntimeError("Comprehensive production runtime must block client delivery")


__all__ = [
    "app",
    "COMPREHENSIVE_PRODUCTION_RUNTIME",
    "COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE",
    "VERSION",
    "install_comprehensive_on_production_app",
]
