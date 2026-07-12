from __future__ import annotations

from copy import deepcopy
from typing import Any

import nico.operational_alerts as operational_alerts

OPERATIONAL_ALERT_NORMALIZATION_VERSION = "nico.operational_alert_normalization.v1"
_INSTALLED = False
_ORIGINAL_EVALUATE = operational_alerts.evaluate_operational_alerts


def evaluate_operational_alerts(
    observability: dict[str, Any],
    *,
    frontend_commit: str = "",
) -> dict[str, Any]:
    normalized = deepcopy(observability) if isinstance(observability, dict) else {}
    request_metrics = normalized.get("request_metrics")
    if isinstance(request_metrics, dict):
        severity_counts = request_metrics.get("severity_counts")
        if isinstance(severity_counts, dict):
            for severity in ("p0", "p1", "p2", "p3", "info"):
                severity_counts.setdefault(severity, 0)
    return _ORIGINAL_EVALUATE(normalized, frontend_commit=frontend_commit)


def install_operational_alert_normalization() -> dict[str, Any]:
    global _INSTALLED
    from nico.operations_readiness import REQUIRED_OPERATION_ROUTES

    REQUIRED_OPERATION_ROUTES.add(operational_alerts.REQUIRED_OPERATION_ALERT_ROUTE)
    if _INSTALLED:
        return {
            "installed": True,
            "idempotent_reuse": True,
            "version": OPERATIONAL_ALERT_NORMALIZATION_VERSION,
        }
    operational_alerts.evaluate_operational_alerts = evaluate_operational_alerts
    _INSTALLED = True
    return {
        "installed": True,
        "idempotent_reuse": False,
        "version": OPERATIONAL_ALERT_NORMALIZATION_VERSION,
        "zero_default_severities": ["p0", "p1", "p2", "p3", "info"],
        "required_readiness_route": operational_alerts.REQUIRED_OPERATION_ALERT_ROUTE,
    }


__all__ = [
    "OPERATIONAL_ALERT_NORMALIZATION_VERSION",
    "evaluate_operational_alerts",
    "install_operational_alert_normalization",
]
