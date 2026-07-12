from __future__ import annotations

from typing import Any

from nico.diagnostics import deployment_diagnostics, feature_diagnostics, storage_diagnostics
from nico.report_truth_status import build_report_truth_status
from nico.runtime_config import runtime_config

OPERATIONS_READINESS_SCHEMA = "nico.operations_readiness.v1"
REQUIRED_OPERATION_ROUTES = {
    "GET /health",
    "GET /diagnostics",
    "GET /operations/readiness",
    "GET /operations/events",
    "GET /operations/observability",
    "POST /assessment/github",
    "POST /assessment/mid-run",
    "POST /assessment/full-run",
    "POST /worker/scan",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _runtime_status() -> dict[str, Any]:
    try:
        config = runtime_config()
    except Exception:  # pragma: no cover - defensive runtime boundary
        return {"status": "unavailable", "source": "unavailable", "version": "unavailable"}
    source = str(config.get("source") or "").strip()
    version = str(config.get("version") or "").strip()
    return {
        "status": "ok" if source and version and source != "unavailable" and version != "unavailable" else "unavailable",
        "source": source or "unavailable",
        "version": version or "unavailable",
    }


def _check(
    check_id: str,
    label: str,
    *,
    passed: bool,
    required: bool,
    observed: Any,
    expected: Any,
    remediation: str,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "label": label,
        "required": required,
        "passed": bool(passed),
        "status": "passed" if passed else "failed",
        "observed": observed,
        "expected": expected,
        "remediation": "" if passed else remediation,
    }


def build_operations_readiness(
    route_inventory: list[str] | set[str] | tuple[str, ...],
    *,
    deployment: dict[str, Any] | None = None,
    storage: dict[str, Any] | None = None,
    features: dict[str, Any] | None = None,
    report_truth: dict[str, Any] | None = None,
    runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a fail-closed hosted operations-readiness decision.

    This contract evaluates semantic production prerequisites. It does not evaluate
    repository findings and cannot authorize client delivery.
    """

    deployment_payload = _dict(deployment if deployment is not None else deployment_diagnostics())
    storage_payload = _dict(storage if storage is not None else storage_diagnostics())
    features_payload = _dict(features if features is not None else feature_diagnostics())
    truth_payload = _dict(report_truth if report_truth is not None else build_report_truth_status())
    runtime_payload = _dict(runtime if runtime is not None else _runtime_status())
    routes = {str(item).strip() for item in route_inventory if str(item).strip()}
    missing_routes = sorted(REQUIRED_OPERATION_ROUTES - routes)

    deployed_commit = str(deployment_payload.get("deployed_commit") or "unavailable")
    deployment_commit_available = deployed_commit != "unavailable"
    deployment_matches = bool(deployment_payload.get("matches_expected_build"))
    persistence_available = bool(storage_payload.get("persistence_available"))
    scanner_execution_enabled = bool(features_payload.get("scanner_execution_enabled"))
    report_truth_active = truth_payload.get("status") == "ok" and bool(truth_payload.get("guard_active"))
    runtime_loaded = runtime_payload.get("status") == "ok"
    admin = _dict(features_payload.get("admin"))
    admin_configured = bool(admin.get("admin_writes_configured"))
    project_commands_disabled = not bool(features_payload.get("project_commands_allowed"))

    checks = [
        _check(
            "deployment_commit_available",
            "Deployed commit identity",
            passed=deployment_commit_available,
            required=True,
            observed=deployed_commit,
            expected="A non-empty deployed commit identity",
            remediation="Expose the deployment commit through a supported runtime commit environment variable and redeploy latest main.",
        ),
        _check(
            "deployment_matches_expected",
            "Deployment matches expected build",
            passed=deployment_commit_available and deployment_matches,
            required=True,
            observed=deployment_payload.get("matches_expected_build"),
            expected=True,
            remediation="Redeploy the expected main build and verify the runtime commit identity before trusting hosted output.",
        ),
        _check(
            "report_truth_guard_active",
            "Report truth guard",
            passed=report_truth_active,
            required=True,
            observed=truth_payload.get("status") or "unavailable",
            expected="ok",
            remediation="Load the current report-truth guard and redeploy before generating score-change or client-facing reports.",
        ),
        _check(
            "durable_storage",
            "Durable hosted storage",
            passed=persistence_available,
            required=True,
            observed=storage_payload.get("storage", {}).get("adapter") if isinstance(storage_payload.get("storage"), dict) else storage_payload.get("adapter"),
            expected="Persistent hosted storage available",
            remediation="Configure and verify durable Postgres storage; process-memory storage is not production-ready.",
        ),
        _check(
            "scanner_execution_enabled",
            "Scanner execution",
            passed=scanner_execution_enabled,
            required=True,
            observed=scanner_execution_enabled,
            expected=True,
            remediation="Enable scanner execution in the hosted runtime and verify required scanner binaries separately.",
        ),
        _check(
            "runtime_config_loaded",
            "Runtime configuration",
            passed=runtime_loaded,
            required=True,
            observed={"source": runtime_payload.get("source"), "version": runtime_payload.get("version")},
            expected="Loaded source and version",
            remediation="Restore a valid runtime configuration source and version before accepting assessment traffic.",
        ),
        _check(
            "required_routes_registered",
            "Required workflow routes",
            passed=not missing_routes,
            required=True,
            observed={"registered": len(routes), "missing": missing_routes},
            expected=sorted(REQUIRED_OPERATION_ROUTES),
            remediation="Register every required operations, assessment, scanner, and observability route in the production application.",
        ),
        _check(
            "operator_admin_configured",
            "Operator admin authentication",
            passed=admin_configured,
            required=False,
            observed=admin.get("admin_write_mode") or "read_only",
            expected="Server-side operator admin authentication configured",
            remediation="Configure NICO_ADMIN_TOKEN before relying on public operator write workflows.",
        ),
        _check(
            "project_commands_disabled",
            "Project command execution default",
            passed=project_commands_disabled,
            required=False,
            observed=features_payload.get("project_commands_allowed"),
            expected=False,
            remediation="Disable project command execution unless a separately reviewed authorized workflow requires it.",
        ),
    ]

    required_failures = [item for item in checks if item["required"] and not item["passed"]]
    advisory_failures = [item for item in checks if not item["required"] and not item["passed"]]
    if required_failures:
        status = "blocked"
    elif advisory_failures:
        status = "degraded"
    else:
        status = "ready"

    return {
        "artifact_schema": OPERATIONS_READINESS_SCHEMA,
        "status": status,
        "operational_ready": status == "ready",
        "required_checks": sum(1 for item in checks if item["required"]),
        "required_passed": sum(1 for item in checks if item["required"] and item["passed"]),
        "advisory_checks": sum(1 for item in checks if not item["required"]),
        "advisory_passed": sum(1 for item in checks if not item["required"] and item["passed"]),
        "checks": checks,
        "blockers": [item["id"] for item in required_failures],
        "warnings": [item["id"] for item in advisory_failures],
        "missing_routes": missing_routes,
        "deployment": {
            "build_marker": deployment_payload.get("build_marker"),
            "expected_build_commit": deployment_payload.get("expected_build_commit"),
            "deployed_commit": deployed_commit,
            "matches_expected_build": deployment_matches,
        },
        "storage": {
            "persistence_available": persistence_available,
            "database_configured": bool(storage_payload.get("database_configured")),
            "warnings": storage_payload.get("warnings") if isinstance(storage_payload.get("warnings"), list) else [],
        },
        "report_truth": {
            "status": truth_payload.get("status") or "unavailable",
            "version": truth_payload.get("version") or "unavailable",
            "guard_active": bool(truth_payload.get("guard_active")),
        },
        "runtime_config": runtime_payload,
        "next_action": _next_action(status, required_failures, advisory_failures),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "guardrail": "Operational readiness proves production prerequisites only. It does not prove a repository is clean or authorize client delivery.",
    }


def _next_action(status: str, blockers: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> str:
    if status == "blocked":
        labels = ", ".join(str(item.get("label") or item.get("id")) for item in blockers)
        return f"Fix required operational blockers before accepting trusted production work: {labels}."
    if status == "degraded":
        labels = ", ".join(str(item.get("label") or item.get("id")) for item in warnings)
        return f"Core operation is available, but resolve advisory warnings before full operator use: {labels}."
    return "Run the post-deployment smoke check, then perform fresh Mid and Full acceptance runs before client delivery."
