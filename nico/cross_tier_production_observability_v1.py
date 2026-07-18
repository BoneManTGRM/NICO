"""Fail-closed production observability checks for Express, Mid, and Full."""

from __future__ import annotations

from typing import Any, Mapping

TIERS = ("express", "mid", "full")
REQUIRED_SIGNALS = (
    "request_success_rate",
    "status_lookup_success_rate",
    "artifact_delivery_success_rate",
    "p95_status_latency_ms",
    "stuck_runs",
    "orphaned_runs",
    "cross_tier_mismatches",
    "unhandled_errors",
)


def evaluate_production_observability(
    evidence: Mapping[str, Mapping[str, Any]],
    *,
    exact_sha: str,
    min_success_rate: float = 0.995,
    max_p95_status_latency_ms: float = 1500.0,
    prior_release_allowed: bool = True,
) -> dict[str, Any]:
    """Return a release decision; missing, stale, or unhealthy telemetry blocks."""
    failures: list[str] = []
    if not prior_release_allowed:
        failures.append("prior_release_block")
    if not exact_sha:
        failures.append("missing_exact_sha")

    for tier in TIERS:
        record = evidence.get(tier)
        if not isinstance(record, Mapping):
            failures.append(f"{tier}:missing_observability")
            continue
        if record.get("commit_sha") != exact_sha:
            failures.append(f"{tier}:sha_mismatch")
        missing = [signal for signal in REQUIRED_SIGNALS if signal not in record]
        failures.extend(f"{tier}:missing:{signal}" for signal in missing)
        if missing:
            continue
        for signal in (
            "request_success_rate",
            "status_lookup_success_rate",
            "artifact_delivery_success_rate",
        ):
            value = float(record[signal])
            if value < min_success_rate or value > 1.0:
                failures.append(f"{tier}:{signal}:unhealthy")
        if float(record["p95_status_latency_ms"]) > max_p95_status_latency_ms:
            failures.append(f"{tier}:p95_status_latency_ms:limit_exceeded")
        for signal in ("stuck_runs", "orphaned_runs", "cross_tier_mismatches", "unhandled_errors"):
            if int(record[signal]) != 0:
                failures.append(f"{tier}:{signal}:nonzero")
        if record.get("alerting_enabled") is not True:
            failures.append(f"{tier}:alerting_disabled")
        if record.get("dashboard_healthy") is not True:
            failures.append(f"{tier}:dashboard_unhealthy")

    return {
        "status": "healthy" if not failures else "blocked",
        "release_allowed": not failures,
        "failures": sorted(set(failures)),
        "tiers_checked": list(TIERS),
        "commit_sha": exact_sha,
    }
