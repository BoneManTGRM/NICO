from __future__ import annotations

from fastapi import FastAPI

from nico.api.hosted import app
from nico.assessment_network_budget import install_assessment_network_budget
from nico.assessment_recovery import (
    REQUIRED_ASSESSMENT_RECOVERY_ROUTES,
    install_assessment_recovery,
)
from nico.assessment_required_tools import install_required_assessment_tools
from nico.assessment_score_integrity import install_assessment_score_integrity
from nico.assessment_score_integrity_compat import install_score_integrity_compatibility
from nico.backup_restore_readiness import (
    REQUIRED_BACKUP_RESTORE_ROUTES,
    install_backup_restore_readiness,
)
from nico.builtin_static_code_context import install_builtin_static_code_context
from nico.correlation_header_exposure import install_correlation_header_exposure
from nico.dependency_scanner_triage import install_dependency_scanner_triage
from nico.exact_snapshot_full_history_checkout import install_exact_snapshot_full_history_checkout
from nico.exact_snapshot_secret_history import install_exact_snapshot_secret_history
from nico.exact_snapshot_secret_history_compat import install_secret_history_score_compatibility
from nico.exact_snapshot_secret_history_exit_guard import install_secret_history_exit_guard
from nico.exact_snapshot_static_triage import install_exact_snapshot_static_triage
from nico.mid_approval_api import register_mid_approval_routes
from nico.mid_assessment_api import register_mid_assessment_routes
from nico.mid_delivery_api import register_mid_delivery_routes
from nico.mid_legacy_migration import LEGACY_MID_PATH, register_legacy_mid_migration
from nico.mid_optional_evidence_api import register_mid_optional_evidence_routes
from nico.mid_report_api import register_mid_report_routes
from nico.mid_report_presentation import install_mid_report_presentation
from nico.mid_review_api import register_mid_review_routes
from nico.mid_review_enforcement_compat import install_mid_review_enforcement_compat
from nico.operational_alerts import (
    OPERATIONS_ALERT_ROUTES,
    install_operational_alert_routes,
)
from nico.operational_observability import (
    OPERATIONS_OBSERVABILITY_ROUTES,
    install_operational_observability,
)
from nico.operations_readiness_api import register_operations_readiness_routes
from nico.retainer_auto_evidence_api import (
    RETAINER_OPS_ROUTE,
    install_retainer_auto_evidence,
)
from nico.scanner_recovery import (
    REQUIRED_SCANNER_RECOVERY_ROUTES,
    install_scanner_recovery,
)
from nico.scanner_runtime_compat import install_scanner_runtime_compat
from nico.secret_history_triage import install_secret_history_triage
from nico.static_triage_evidence_bridge import install_static_triage_evidence_bridge
from nico.storage_schema_readiness import (
    STORAGE_SCHEMA_READINESS_ROUTE,
    install_storage_schema_readiness,
)
from nico.typescript_complexity_syntax import install_typescript_complexity_syntax
from nico.typescript_validation_bridge import install_typescript_validation_bridge

ASSESSMENT_NETWORK_POLICY = install_assessment_network_budget()
ASSESSMENT_SCORE_INTEGRITY = install_assessment_score_integrity()
ASSESSMENT_TYPESCRIPT_COMPLEXITY_SYNTAX = install_typescript_complexity_syntax()
ASSESSMENT_SCORE_COMPATIBILITY = install_score_integrity_compatibility()
ASSESSMENT_BUILTIN_STATIC_CONTEXT = install_builtin_static_code_context()
ASSESSMENT_STATIC_TRIAGE = install_exact_snapshot_static_triage()
ASSESSMENT_FULL_HISTORY_CHECKOUT = install_exact_snapshot_full_history_checkout()
ASSESSMENT_SECRET_HISTORY = install_exact_snapshot_secret_history()
ASSESSMENT_SECRET_HISTORY_EXIT_GUARD = install_secret_history_exit_guard()
ASSESSMENT_SECRET_HISTORY_COMPATIBILITY = install_secret_history_score_compatibility()
ASSESSMENT_SCANNER_RUNTIME_COMPATIBILITY = install_scanner_runtime_compat()
ASSESSMENT_REQUIRED_TOOLS = install_required_assessment_tools()
ASSESSMENT_STATIC_TRIAGE_EVIDENCE = install_static_triage_evidence_bridge()
ASSESSMENT_DEPENDENCY_TRIAGE = install_dependency_scanner_triage()
ASSESSMENT_SECRET_HISTORY_TRIAGE = install_secret_history_triage()
ASSESSMENT_TYPESCRIPT_VALIDATION = install_typescript_validation_bridge()
ASSESSMENT_MID_REPORT_PRESENTATION = install_mid_report_presentation()
ASSESSMENT_MID_REVIEW_ENFORCEMENT = install_mid_review_enforcement_compat()
RETAINER_AUTO_EVIDENCE = install_retainer_auto_evidence(app)
OPERATIONS_OBSERVABILITY = install_operational_observability(app)
OPERATIONS_ALERTING = install_operational_alert_routes(app)
OPERATIONS_STORAGE_SCHEMA = install_storage_schema_readiness(app)
OPERATIONS_SCANNER_RECOVERY = install_scanner_recovery(app)
OPERATIONS_ASSESSMENT_RECOVERY = install_assessment_recovery(app)
OPERATIONS_BACKUP_RESTORE = install_backup_restore_readiness(app)

OPERATIONS_READINESS_ROUTES = {
    ("GET", "/operations/readiness"),
}
REQUIRED_MID_ASSESSMENT_ROUTES = {
    ("POST", "/assessment/mid-run"),
    ("POST", "/assessment/mid-run/{run_id}/status"),
    ("POST", "/assessment/mid-run/{run_id}/evidence"),
    ("GET", "/assessment/mid-run/{run_id}/review-exceptions"),
    ("POST", "/assessment/mid-run/{run_id}/report/draft"),
    ("GET", "/assessment/mid-run/{run_id}/report/draft/pdf"),
    ("POST", "/assessment/mid-run/{run_id}/approval/request"),
    ("GET", "/assessment/mid-run/{run_id}/approval"),
    ("GET", "/assessment/mid-run/approval/{approval_id}/review-items"),
    ("POST", "/assessment/mid-run/approval/{approval_id}/review-items/{item_id}"),
    ("POST", "/assessment/mid-run/approval/{approval_id}/{state}"),
    ("GET", "/assessment/mid-run/{run_id}/report/approved"),
    ("GET", "/assessment/mid-run/{run_id}/report/approved/pdf"),
    ("POST", "/assessment/mid-run/{run_id}/delivery/access"),
    ("GET", "/assessment/mid-run/{run_id}/delivery/access"),
    ("GET", "/assessment/mid-run/{run_id}/delivery/receipts"),
    ("POST", "/assessment/mid-run/delivery/access/{access_id}/revoke"),
    ("POST", "/assessment/mid-run/delivery/inspect"),
    ("POST", "/assessment/mid-run/delivery/redeem"),
    ("POST", LEGACY_MID_PATH),
}
REQUIRED_PRODUCTION_ROUTES = (
    REQUIRED_MID_ASSESSMENT_ROUTES
    | OPERATIONS_READINESS_ROUTES
    | OPERATIONS_OBSERVABILITY_ROUTES
    | OPERATIONS_ALERT_ROUTES
    | REQUIRED_SCANNER_RECOVERY_ROUTES
    | REQUIRED_ASSESSMENT_RECOVERY_ROUTES
    | REQUIRED_BACKUP_RESTORE_ROUTES
    | {STORAGE_SCHEMA_READINESS_ROUTE, RETAINER_OPS_ROUTE}
)
MID_CORE_ROUTES = {
    ("POST", "/assessment/mid-run"),
    ("POST", "/assessment/mid-run/{run_id}/status"),
}
MID_OPTIONAL_EVIDENCE_ROUTES = {
    ("POST", "/assessment/mid-run/{run_id}/evidence"),
}
MID_REVIEW_ROUTES = {
    ("GET", "/assessment/mid-run/{run_id}/review-exceptions"),
}
MID_REPORT_ROUTES = {
    ("POST", "/assessment/mid-run/{run_id}/report/draft"),
    ("GET", "/assessment/mid-run/{run_id}/report/draft/pdf"),
}
MID_APPROVAL_ROUTES = {
    ("POST", "/assessment/mid-run/{run_id}/approval/request"),
    ("GET", "/assessment/mid-run/{run_id}/approval"),
    ("GET", "/assessment/mid-run/approval/{approval_id}/review-items"),
    ("POST", "/assessment/mid-run/approval/{approval_id}/review-items/{item_id}"),
    ("POST", "/assessment/mid-run/approval/{approval_id}/{state}"),
    ("GET", "/assessment/mid-run/{run_id}/report/approved"),
    ("GET", "/assessment/mid-run/{run_id}/report/approved/pdf"),
}
MID_DELIVERY_ROUTES = {
    ("POST", "/assessment/mid-run/{run_id}/delivery/access"),
    ("GET", "/assessment/mid-run/{run_id}/delivery/access"),
    ("GET", "/assessment/mid-run/{run_id}/delivery/receipts"),
    ("POST", "/assessment/mid-run/delivery/access/{access_id}/revoke"),
    ("POST", "/assessment/mid-run/delivery/inspect"),
    ("POST", "/assessment/mid-run/delivery/redeem"),
}


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in target.routes:
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), path))
    return pairs


def _route_count(target: FastAPI, method: str, path: str) -> int:
    expected_method = method.upper()
    count = 0
    for route in target.routes:
        methods = {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
        if str(getattr(route, "path", "")) == path and expected_method in methods:
            count += 1
    return count


def _validate_group(existing: set[tuple[str, str]], required: set[tuple[str, str]], label: str) -> bool:
    present = existing & required
    if present and present != required:
        raise RuntimeError(f"Partial {label} route registration detected; missing={sorted(required - present)}")
    return bool(present)


def register_production_routes(target: FastAPI) -> FastAPI:
    install_retainer_auto_evidence(target)
    existing = _route_pairs(target)
    operations_present = _validate_group(existing, OPERATIONS_READINESS_ROUTES, "operations readiness")
    observability_present = _validate_group(existing, OPERATIONS_OBSERVABILITY_ROUTES, "operational observability")
    alerts_present = _validate_group(existing, OPERATIONS_ALERT_ROUTES, "operational alerts")
    scanner_recovery_present = _validate_group(existing, REQUIRED_SCANNER_RECOVERY_ROUTES, "scanner recovery")
    assessment_recovery_present = _validate_group(existing, REQUIRED_ASSESSMENT_RECOVERY_ROUTES, "assessment recovery")
    backup_restore_present = _validate_group(existing, REQUIRED_BACKUP_RESTORE_ROUTES, "backup/restore readiness")
    storage_schema_present = STORAGE_SCHEMA_READINESS_ROUTE in existing
    core_present = _validate_group(existing, MID_CORE_ROUTES, "unified Mid")
    optional_present = _validate_group(existing, MID_OPTIONAL_EVIDENCE_ROUTES, "Mid optional-evidence")
    review_present = _validate_group(existing, MID_REVIEW_ROUTES, "Mid review")
    report_present = _validate_group(existing, MID_REPORT_ROUTES, "Mid report")
    approval_present = _validate_group(existing, MID_APPROVAL_ROUTES, "Mid approval")
    delivery_present = _validate_group(existing, MID_DELIVERY_ROUTES, "Mid delivery")
    if not operations_present:
        register_operations_readiness_routes(target)
        target.openapi_schema = None
    if not observability_present:
        install_operational_observability(target)
        target.openapi_schema = None
    if not alerts_present:
        install_operational_alert_routes(target)
        target.openapi_schema = None
    if not scanner_recovery_present:
        install_scanner_recovery(target)
        target.openapi_schema = None
    if not assessment_recovery_present:
        install_assessment_recovery(target)
        target.openapi_schema = None
    if not backup_restore_present:
        install_backup_restore_readiness(target)
        target.openapi_schema = None
    if not storage_schema_present:
        install_storage_schema_readiness(target)
        target.openapi_schema = None
    install_correlation_header_exposure(target)
    if not core_present:
        register_mid_assessment_routes(target)
        target.openapi_schema = None
    if not optional_present:
        register_mid_optional_evidence_routes(target)
        target.openapi_schema = None
    if not review_present:
        register_mid_review_routes(target)
        target.openapi_schema = None
    if not report_present:
        register_mid_report_routes(target)
        target.openapi_schema = None
    if not approval_present:
        register_mid_approval_routes(target)
        target.openapi_schema = None
    if not delivery_present:
        register_mid_delivery_routes(target)
        target.openapi_schema = None

    register_legacy_mid_migration(target)
    if _route_count(target, "POST", LEGACY_MID_PATH) != 1:
        raise RuntimeError("Legacy Mid migration route registration must produce exactly one POST /assessment/mid handler")
    if _route_count(target, RETAINER_OPS_ROUTE[0], RETAINER_OPS_ROUTE[1]) != 1:
        raise RuntimeError("Retainer route registration must produce exactly one truth-bound POST /retainer/ops handler")

    missing = REQUIRED_PRODUCTION_ROUTES - _route_pairs(target)
    if missing:
        raise RuntimeError(f"Production route registration incomplete; missing={sorted(missing)}")
    return target


register_production_routes(app)

__all__ = [
    "app",
    "ASSESSMENT_NETWORK_POLICY",
    "ASSESSMENT_SCORE_INTEGRITY",
    "ASSESSMENT_TYPESCRIPT_COMPLEXITY_SYNTAX",
    "ASSESSMENT_SCORE_COMPATIBILITY",
    "ASSESSMENT_BUILTIN_STATIC_CONTEXT",
    "ASSESSMENT_STATIC_TRIAGE",
    "ASSESSMENT_FULL_HISTORY_CHECKOUT",
    "ASSESSMENT_SECRET_HISTORY",
    "ASSESSMENT_SECRET_HISTORY_EXIT_GUARD",
    "ASSESSMENT_SECRET_HISTORY_COMPATIBILITY",
    "ASSESSMENT_SCANNER_RUNTIME_COMPATIBILITY",
    "ASSESSMENT_REQUIRED_TOOLS",
    "ASSESSMENT_STATIC_TRIAGE_EVIDENCE",
    "ASSESSMENT_DEPENDENCY_TRIAGE",
    "ASSESSMENT_SECRET_HISTORY_TRIAGE",
    "ASSESSMENT_TYPESCRIPT_VALIDATION",
    "ASSESSMENT_MID_REPORT_PRESENTATION",
    "ASSESSMENT_MID_REVIEW_ENFORCEMENT",
    "RETAINER_AUTO_EVIDENCE",
    "OPERATIONS_OBSERVABILITY",
    "OPERATIONS_ALERTING",
    "OPERATIONS_STORAGE_SCHEMA",
    "OPERATIONS_SCANNER_RECOVERY",
    "OPERATIONS_ASSESSMENT_RECOVERY",
    "OPERATIONS_BACKUP_RESTORE",
    "register_production_routes",
    "REQUIRED_PRODUCTION_ROUTES",
    "OPERATIONS_READINESS_ROUTES",
    "OPERATIONS_OBSERVABILITY_ROUTES",
    "OPERATIONS_ALERT_ROUTES",
    "REQUIRED_SCANNER_RECOVERY_ROUTES",
    "REQUIRED_ASSESSMENT_RECOVERY_ROUTES",
    "REQUIRED_BACKUP_RESTORE_ROUTES",
    "RETAINER_OPS_ROUTE",
    "STORAGE_SCHEMA_READINESS_ROUTE",
    "REQUIRED_MID_ASSESSMENT_ROUTES",
    "MID_CORE_ROUTES",
    "MID_OPTIONAL_EVIDENCE_ROUTES",
    "MID_REVIEW_ROUTES",
    "MID_REPORT_ROUTES",
    "MID_APPROVAL_ROUTES",
    "MID_DELIVERY_ROUTES",
]
