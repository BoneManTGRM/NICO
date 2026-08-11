from __future__ import annotations

from collections.abc import Mapping
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import FastAPI

from nico import comprehensive_native_providers_v5 as native_provider_v5
from nico.accepted_edition_report_identity_v1 import install_accepted_edition_report_identity
from nico.api.production_bootstrap import app as production_app
from nico.candidate_lineage_runtime_patch_v1 import (
    install_candidate_lineage_runtime_patch,
)
from nico.comprehensive_api_routes import COMPREHENSIVE_API_ROUTES
from nico.comprehensive_core_report_readiness_v1 import install_comprehensive_core_report_readiness
from nico.comprehensive_decision_grade_v5 import install_decision_grade_binding
from nico.comprehensive_final_artifact_truth_v53 import (
    install_comprehensive_final_artifact_truth_v53,
)
from nico.comprehensive_final_report_execution_v1 import install_comprehensive_final_report_execution
from nico.comprehensive_production_bootstrap import install_comprehensive_production_bootstrap
from nico.comprehensive_production_capabilities import (
    PROVIDER_STATE_KEY,
    build_production_capability_executors,
)
from nico.comprehensive_report_appendix_v3 import install_native_provider_binding
from nico.comprehensive_report_truth_v53 import install_comprehensive_report_truth_v53
from nico.comprehensive_score_truth_scope_v4 import install_score_truth_scope
from nico.decision_grade_scanner_executions_v1 import install_structured_scanner_executions
from nico.strategic_human_evidence_binding_v1 import install_strategic_human_evidence_binding
from nico.v2_production_authority import install_v2_production_authority

VERSION = "nico.api.comprehensive_production_bootstrap.v19"
COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE = "/diagnostics/comprehensive-runtime"
_RUNTIME_RECOVERY_SCHEMA = "nico.comprehensive_runtime_recovery.v1"
_TRANSIENT_DATABASE_REASON = "comprehensive_database_unavailable"
_RUNTIME_RECOVERY_MIN_INTERVAL_SECONDS = 5.0
_RUNTIME_RECOVERY_LOCK_STATE = "_nico_comprehensive_runtime_recovery_lock_v1"
_RUNTIME_RECOVERY_LAST_ATTEMPT_STATE = "_nico_comprehensive_runtime_recovery_last_attempt_v1"


def _route_count(target: FastAPI, method: str, path: str) -> int:
    expected = method.upper()
    return sum(
        1
        for route in target.routes
        if str(getattr(route, "path", "")) == path
        and expected in {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
    )


def _runtime_recovery_lock(target: FastAPI) -> Any:
    lock = getattr(target.state, _RUNTIME_RECOVERY_LOCK_STATE, None)
    if lock is None:
        lock = Lock()
        setattr(target.state, _RUNTIME_RECOVERY_LOCK_STATE, lock)
    return lock


def _safe_live_persistence_probe(target: FastAPI) -> dict[str, Any] | None:
    controller = getattr(target.state, "comprehensive_api_controller", None)
    service = getattr(controller, "_service", None)
    store = getattr(service, "_store", None)
    probe = getattr(store, "live_persistence_probe", None)
    if not callable(probe):
        return None
    try:
        raw = probe()
    except Exception:
        raw = None
    result = raw if isinstance(raw, Mapping) else {}
    available = result.get("available") is True
    return {
        "artifact_schema": _RUNTIME_RECOVERY_SCHEMA,
        "status": "ready" if available else "unavailable",
        "available": available,
        "adapter": str(result.get("adapter") or "unknown"),
        "error_detail_exposed": False,
        "same_canonical_store": True,
        "automatic_cross_store_fallback": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _attempt_transient_database_recovery(
    target: FastAPI,
    base_status: Mapping[str, Any],
) -> tuple[dict[str, Any], bool, bool]:
    runtime = dict(getattr(target.state, "comprehensive_runtime", {}) or {})
    if base_status.get("non_storage_readiness_verified") is not True:
        return runtime, False, False
    if runtime.get("configured") is True and runtime.get("status") == "ready":
        return runtime, False, False
    if str(runtime.get("reason") or "") != _TRANSIENT_DATABASE_REASON:
        return runtime, False, False

    lock = _runtime_recovery_lock(target)
    with lock:
        runtime = dict(getattr(target.state, "comprehensive_runtime", {}) or {})
        if runtime.get("configured") is True and runtime.get("status") == "ready":
            return runtime, False, True
        if str(runtime.get("reason") or "") != _TRANSIENT_DATABASE_REASON:
            return runtime, False, False

        now = monotonic()
        last_attempt = float(
            getattr(target.state, _RUNTIME_RECOVERY_LAST_ATTEMPT_STATE, 0.0) or 0.0
        )
        if now - last_attempt < _RUNTIME_RECOVERY_MIN_INTERVAL_SECONDS:
            return runtime, False, False
        setattr(target.state, _RUNTIME_RECOVERY_LAST_ATTEMPT_STATE, now)

        try:
            executors = build_production_capability_executors(target)
            controller = install_comprehensive_production_bootstrap(
                target,
                capability_executors=executors,
            )
        except Exception:
            controller = None
        runtime = dict(getattr(target.state, "comprehensive_runtime", {}) or {})
        recovered = (
            controller is not None
            and runtime.get("configured") is True
            and runtime.get("status") == "ready"
            and runtime.get("survives_container_replacement_verified") is True
        )
        return runtime, True, recovered


def _refresh_runtime_diagnostics(target: FastAPI) -> dict[str, Any]:
    base = dict(getattr(target.state, "nico_comprehensive_production_runtime", {}) or {})
    runtime, attempted, recovered = _attempt_transient_database_recovery(target, base)
    non_storage_ready = base.get("non_storage_readiness_verified") is True
    replacement_safe = runtime.get("survives_container_replacement_verified") is True
    runtime_ready = (
        runtime.get("configured") is True
        and runtime.get("status") == "ready"
        and runtime.get("client_delivery_allowed") is False
        and runtime.get("human_review_required") is True
        and replacement_safe
    )

    live_probe = _safe_live_persistence_probe(target) if runtime_ready else None
    live_database_available = live_probe is None or live_probe.get("available") is True
    ready = non_storage_ready and runtime_ready and live_database_available
    reason = str(runtime.get("reason") or base.get("reason") or "")
    if runtime_ready and not live_database_available:
        reason = _TRANSIENT_DATABASE_REASON
    elif ready:
        reason = ""
    elif not reason and not replacement_safe:
        reason = "comprehensive_storage_not_container_replacement_safe"

    status = {
        **base,
        "artifact_schema": str(base.get("artifact_schema") or VERSION),
        "service_id": "comprehensive",
        "status": "ready" if ready else "blocked",
        "configured": bool(runtime.get("configured")),
        "reason": reason,
        "persistence_adapter": str(runtime.get("persistence_adapter") or "unavailable"),
        "storage_source": str(runtime.get("storage_source") or "unavailable"),
        "database_url_source": str(runtime.get("database_url_source") or ""),
        "durability_verified": runtime.get("durability_verified") is True,
        "survives_container_replacement_verified": replacement_safe,
        "run_store_shared_across_workers": replacement_safe,
        "runtime_recovery_schema": _RUNTIME_RECOVERY_SCHEMA,
        "runtime_recovery_supported": True,
        "runtime_recovery_attempted": attempted,
        "runtime_recovered": recovered,
        "live_persistence_probe": live_probe,
        "same_canonical_store_recovery_only": True,
        "automatic_cross_store_fallback": False,
        "error_detail_exposed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    # A successful recovery replaces only the stale startup availability projection.
    # Keep the static report/scoring/security bindings from the original installation.
    # Transient live-probe failures are intentionally not persisted so the next
    # diagnostics request can observe the same store returning to service.
    if ready and base.get("status") != "ready":
        target.state.nico_comprehensive_production_runtime = dict(status)
    return status


def _register_runtime_diagnostics(target: FastAPI) -> None:
    if _route_count(target, "GET", COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE):
        return

    def runtime_diagnostics() -> dict[str, Any]:
        return _refresh_runtime_diagnostics(target)

    target.add_api_route(
        COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE,
        runtime_diagnostics,
        methods=["GET"],
        tags=["diagnostics"],
    )
    target.openapi_schema = None


def install_comprehensive_on_production_app(target: FastAPI) -> dict[str, Any]:
    """Mount the production Comprehensive boundary with deterministic exact-SHA scoring."""

    report_binding = install_native_provider_binding()
    legacy_report_binding = report_binding
    report_binding = install_decision_grade_binding()
    accepted_edition_report_identity = install_accepted_edition_report_identity()
    score_truth_scope = install_score_truth_scope()

    # Install the authoritative pre-render truth wrapper after every decision-grade
    # report builder has been composed, but before production providers are registered.
    report_truth = install_comprehensive_report_truth_v53()
    candidate_lineage_runtime = install_candidate_lineage_runtime_patch()
    native_providers = native_provider_v5.install_native_comprehensive_providers(target)
    strategic_human_evidence = install_strategic_human_evidence_binding(target)
    scanner_execution_normalization = install_structured_scanner_executions(
        __import__("nico.comprehensive_native_providers", fromlist=["_scan"])
    )
    core_report_readiness = install_comprehensive_core_report_readiness(target)
    final_report_execution = install_comprehensive_final_report_execution(target)

    # Bind full-package truth verification after the final report provider has
    # replaced the registry's cross-format verifier. Rebind that exact wrapper into
    # the target registry so production cannot retain the earlier verifier by value.
    final_artifact_truth = install_comprehensive_final_artifact_truth_v53()
    provider_module = __import__(
        "nico.comprehensive_native_providers",
        fromlist=["cross_format_verification_provider"],
    )
    provider_registry = getattr(target.state, PROVIDER_STATE_KEY, None)
    if isinstance(provider_registry, dict):
        provider_registry["cross_format_verification"] = (
            provider_module.cross_format_verification_provider
        )
        setattr(target.state, PROVIDER_STATE_KEY, provider_registry)
    final_artifact_registry_bound = (
        isinstance(provider_registry, dict)
        and provider_registry.get("cross_format_verification")
        is provider_module.cross_format_verification_provider
    )

    v2_production_authority = install_v2_production_authority(target)
    executors = build_production_capability_executors(target)
    controller = install_comprehensive_production_bootstrap(target, capability_executors=executors)

    route_counts = {
        f"{method} {path}": _route_count(target, method, path)
        for method, path in sorted(COMPREHENSIVE_API_ROUTES)
    }
    runtime = dict(getattr(target.state, "comprehensive_runtime", {}) or {})
    provider_status = dict(getattr(target.state, "nico_comprehensive_capability_provider_status", {}) or {})
    native_status = dict(getattr(target.state, "nico_native_comprehensive_provider_status", {}) or {})
    missing_capabilities = list(provider_status.get("missing_capabilities") or [])
    replacement_safe = runtime.get("survives_container_replacement_verified") is True
    category_specific_scoring_bound = native_status.get("category_specific_scoring_bound") is True
    same_sha_score_deterministic = native_status.get("same_sha_score_deterministic") is True
    mutable_operational_history_affects_score = native_status.get("mutable_operational_history_affects_score") is True
    score_override_disabled = native_status.get("score_override_allowed") is False
    score_truth_scope_bound = score_truth_scope.get("bound") is True
    candidate_lineage_runtime_bound = (
        candidate_lineage_runtime.get("provider_bound") is True
        and candidate_lineage_runtime.get("provider_install_bound") is True
        and candidate_lineage_runtime.get("report_stage_bound") is True
        and candidate_lineage_runtime.get("human_approval_carried_forward") is False
        and candidate_lineage_runtime.get("client_delivery_allowed") is False
        and native_status.get("candidate_lineage_migration_bound") is True
        and native_status.get("human_approval_may_carry_forward") is False
    )
    non_storage_readiness_verified = (
        legacy_report_binding.get("bound") is True
        and report_binding.get("bound") is True
        and report_binding.get("canonical_scoring_bound") is True
        and report_binding.get("secret_category_isolated") is True
        and report_binding.get("score_band_separated_from_assurance") is True
        and accepted_edition_report_identity.get("bound") is True
        and score_truth_scope_bound
        and report_truth.get("bound") is True
        and candidate_lineage_runtime_bound
        and strategic_human_evidence.get("bound") is True
        and scanner_execution_normalization.get("bound") is True
        and core_report_readiness.get("bound") is True
        and final_report_execution.get("bound") is True
        and final_artifact_truth.get("bound") is True
        and final_artifact_registry_bound
        and v2_production_authority.get("bound") is True
        and v2_production_authority.get("v2_finalizer_invoked_by_real_provider") is True
        and category_specific_scoring_bound
        and same_sha_score_deterministic
        and not mutable_operational_history_affects_score
        and score_override_disabled
        and len(native_providers) > 0
        and not missing_capabilities
        and all(count == 1 for count in route_counts.values())
    )
    ready = (
        controller is not None
        and runtime.get("configured") is True
        and runtime.get("status") == "ready"
        and runtime.get("client_delivery_allowed") is False
        and runtime.get("human_review_required") is True
        and replacement_safe
        and non_storage_readiness_verified
    )
    reason = str(runtime.get("reason") or "")
    if not reason and not replacement_safe:
        reason = "comprehensive_storage_not_container_replacement_safe"
    if not reason and accepted_edition_report_identity.get("bound") is not True:
        reason = "accepted_edition_report_identity_binding_incomplete"
    if not reason and not score_truth_scope_bound:
        reason = "score_truth_scope_binding_incomplete"
    if not reason and report_truth.get("bound") is not True:
        reason = "pre_render_report_truth_binding_incomplete"
    if not reason and not candidate_lineage_runtime_bound:
        reason = "candidate_lineage_runtime_binding_incomplete"
    if not reason and strategic_human_evidence.get("bound") is not True:
        reason = "strategic_human_evidence_binding_incomplete"
    if not reason and final_artifact_truth.get("bound") is not True:
        reason = "final_artifact_truth_binding_incomplete"
    if not reason and not final_artifact_registry_bound:
        reason = "final_artifact_truth_registry_binding_incomplete"
    if not reason and v2_production_authority.get("bound") is not True:
        reason = "v2_production_authority_binding_incomplete"
    if not reason and not category_specific_scoring_bound:
        reason = "category_specific_evidence_scoring_not_bound"
    if not reason and not same_sha_score_deterministic:
        reason = "same_sha_score_determinism_not_bound"
    if not reason and mutable_operational_history_affects_score:
        reason = "mutable_operational_history_still_affects_score"
    if not reason and not score_override_disabled:
        reason = "score_override_boundary_not_enforced"
    if not reason and missing_capabilities:
        reason = "comprehensive_native_providers_missing"

    status = {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "status": "ready" if ready else "blocked",
        "configured": bool(runtime.get("configured")),
        "reason": reason,
        "persistence_adapter": str(runtime.get("persistence_adapter") or "unavailable"),
        "storage_source": str(runtime.get("storage_source") or "unavailable"),
        "database_url_source": str(runtime.get("database_url_source") or ""),
        "durability_verified": runtime.get("durability_verified") is True,
        "survives_container_replacement_verified": replacement_safe,
        "run_store_shared_across_workers": replacement_safe,
        "non_storage_readiness_verified": non_storage_readiness_verified,
        "runtime_recovery_schema": _RUNTIME_RECOVERY_SCHEMA,
        "runtime_recovery_supported": True,
        "same_canonical_store_recovery_only": True,
        "automatic_cross_store_fallback": False,
        "route_counts": route_counts,
        "legacy_report_binding": legacy_report_binding,
        "report_binding": report_binding,
        "accepted_edition_report_identity": accepted_edition_report_identity,
        "score_truth_scope": score_truth_scope,
        "report_truth": report_truth,
        "candidate_lineage_runtime": candidate_lineage_runtime,
        "candidate_lineage_runtime_bound": candidate_lineage_runtime_bound,
        "strategic_human_evidence": strategic_human_evidence,
        "scanner_execution_normalization": scanner_execution_normalization,
        "core_report_readiness": core_report_readiness,
        "final_report_execution": final_report_execution,
        "final_artifact_truth": final_artifact_truth,
        "final_artifact_registry_bound": final_artifact_registry_bound,
        "v2_production_authority": v2_production_authority,
        "native_provider_status": native_status,
        "capability_provider_status": provider_status,
        "native_provider_count": len(native_providers),
        "missing_capabilities": missing_capabilities,
        "category_specific_scoring_bound": category_specific_scoring_bound,
        "same_sha_score_deterministic": same_sha_score_deterministic,
        "mutable_operational_history_affects_score": mutable_operational_history_affects_score,
        "score_truth_scope_bound": score_truth_scope_bound,
        "score_override_allowed": False,
        "report_binding_before_accepted_edition_identity": True,
        "accepted_edition_identity_before_score_truth_scope": True,
        "score_truth_scope_before_report_truth": True,
        "report_truth_before_candidate_lineage_runtime": True,
        "candidate_lineage_runtime_before_provider_install": True,
        "report_truth_before_provider_install": True,
        "score_truth_scope_before_provider_install": True,
        "accepted_edition_identity_before_provider_install": True,
        "report_binding_before_provider_install": True,
        "provider_install_before_human_evidence_binding": True,
        "human_evidence_binding_before_executor_build": True,
        "provider_install_before_scanner_execution_normalization": True,
        "scanner_execution_normalization_before_executor_build": True,
        "provider_install_before_core_report_readiness": True,
        "provider_install_before_final_report_execution": True,
        "final_report_execution_before_final_artifact_truth": True,
        "final_artifact_truth_before_v2_production_authority": True,
        "final_report_execution_before_v2_production_authority": True,
        "v2_production_authority_before_executor_build": True,
        "core_report_readiness_before_executor_build": True,
        "final_report_execution_before_executor_build": True,
        "final_artifact_truth_before_executor_build": True,
        "provider_install_before_executor_build": True,
        "single_final_publication_boundary": True,
        "pre_render_truth_reconciliation": True,
        "full_pdf_text_validation": True,
        "review_route": "/assessment/comprehensive-run/{run_id}/review",
        "review_regenerates_report": False,
        "diagnostics_route": COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    target.state.nico_comprehensive_production_runtime = status
    _register_runtime_diagnostics(target)
    status["diagnostics_route_count"] = _route_count(target, "GET", COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE)
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
if COMPREHENSIVE_PRODUCTION_RUNTIME["accepted_edition_report_identity"].get("bound") is not True:
    raise RuntimeError("Accepted-edition report identity binding was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["score_truth_scope_bound"] is not True:
    raise RuntimeError("Overall score alias synchronization scope was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["report_truth"].get("bound") is not True:
    raise RuntimeError("Pre-render Comprehensive report truth was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["candidate_lineage_runtime_bound"] is not True:
    raise RuntimeError("Cross-SHA candidate lineage runtime was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["strategic_human_evidence"].get("bound") is not True:
    raise RuntimeError("Strategic human-evidence binding was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["scanner_execution_normalization"].get("bound") is not True:
    raise RuntimeError("Structured scanner execution normalization was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["core_report_readiness"].get("bound") is not True:
    raise RuntimeError("Comprehensive core-report artifact readiness was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["final_report_execution"].get("bound") is not True:
    raise RuntimeError("Comprehensive final-report execution readiness was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["final_artifact_truth"].get("bound") is not True:
    raise RuntimeError("Comprehensive final-artifact truth verification was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["final_artifact_registry_bound"] is not True:
    raise RuntimeError("Final-artifact truth verifier was not bound into the production registry")
if COMPREHENSIVE_PRODUCTION_RUNTIME["v2_production_authority"].get("bound") is not True:
    raise RuntimeError("V2 production authority was not installed on the final report provider")
if COMPREHENSIVE_PRODUCTION_RUNTIME["category_specific_scoring_bound"] is not True:
    raise RuntimeError("Category-specific evidence-bound scoring was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["same_sha_score_deterministic"] is not True:
    raise RuntimeError("Same-SHA deterministic scoring was not installed")
if COMPREHENSIVE_PRODUCTION_RUNTIME["mutable_operational_history_affects_score"] is not False:
    raise RuntimeError("Mutable operational history must not affect immutable technical scores")
if COMPREHENSIVE_PRODUCTION_RUNTIME["score_override_allowed"] is not False:
    raise RuntimeError("Comprehensive scoring must not allow score overrides")
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
