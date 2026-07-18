"""Fail-closed performance qualification for Express, Mid, and Full releases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

TIERS = ("express", "mid", "full")
REQUIRED_METRICS = (
    "repository_files",
    "evidence_items",
    "runtime_seconds",
    "peak_memory_mb",
    "renderer_seconds",
    "worker_recoveries",
    "artifact_success_rate",
)


@dataclass(frozen=True)
class PerformanceLimits:
    max_runtime_seconds: float
    max_peak_memory_mb: float
    max_renderer_seconds: float
    max_worker_recoveries: int
    min_artifact_success_rate: float = 1.0


DEFAULT_LIMITS: Mapping[str, PerformanceLimits] = {
    "express": PerformanceLimits(900.0, 2048.0, 120.0, 2),
    "mid": PerformanceLimits(3600.0, 4096.0, 300.0, 3),
    "full": PerformanceLimits(10800.0, 8192.0, 900.0, 5),
}


def qualify_cross_tier_performance(
    evidence: Mapping[str, Mapping[str, Any]],
    *,
    limits: Mapping[str, PerformanceLimits] = DEFAULT_LIMITS,
    prior_delivery_allowed: bool = True,
) -> dict[str, Any]:
    """Return a release decision that fails closed on missing or excessive metrics."""

    failures: list[str] = []
    if not prior_delivery_allowed:
        failures.append("prior_delivery_block")

    for tier in TIERS:
        record = evidence.get(tier)
        if not isinstance(record, Mapping):
            failures.append(f"{tier}:missing_evidence")
            continue

        missing = [name for name in REQUIRED_METRICS if name not in record]
        failures.extend(f"{tier}:missing:{name}" for name in missing)
        if missing:
            continue

        limit = limits[tier]
        numeric_checks: Sequence[tuple[str, float, float, str]] = (
            ("runtime_seconds", float(record["runtime_seconds"]), limit.max_runtime_seconds, "max"),
            ("peak_memory_mb", float(record["peak_memory_mb"]), limit.max_peak_memory_mb, "max"),
            ("renderer_seconds", float(record["renderer_seconds"]), limit.max_renderer_seconds, "max"),
            ("worker_recoveries", float(record["worker_recoveries"]), float(limit.max_worker_recoveries), "max"),
            (
                "artifact_success_rate",
                float(record["artifact_success_rate"]),
                limit.min_artifact_success_rate,
                "min",
            ),
        )
        for name, value, threshold, direction in numeric_checks:
            if value < 0:
                failures.append(f"{tier}:{name}:negative")
            elif direction == "max" and value > threshold:
                failures.append(f"{tier}:{name}:limit_exceeded")
            elif direction == "min" and value < threshold:
                failures.append(f"{tier}:{name}:below_required")

        if int(record["repository_files"]) <= 0:
            failures.append(f"{tier}:repository_files:invalid")
        if int(record["evidence_items"]) <= 0:
            failures.append(f"{tier}:evidence_items:invalid")
        if record.get("snapshot_sha") in (None, ""):
            failures.append(f"{tier}:missing_snapshot_sha")
        if record.get("completed") is not True:
            failures.append(f"{tier}:not_completed")

    return {
        "status": "qualified" if not failures else "blocked",
        "delivery_allowed": not failures,
        "failures": sorted(set(failures)),
        "tiers_checked": list(TIERS),
    }
