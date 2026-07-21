from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Iterable, Mapping


_AUTHORIZATION_PATTERN = re.compile(
    r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+|basic\s+)?([^\s,;]+)"
)
_PRIVATE_TOKEN_PATTERN = re.compile(r"(?i)(private-token\s*[:=]\s*)([^\s,;]+)")
_SECRET_PATTERN = re.compile(
    r"(?i)(token|secret|password|database_url)(\s*[:=]\s*)([^\s,;]+)"
)


@dataclass(frozen=True)
class MetricPoint:
    name: str
    value: float
    timestamp: str
    labels: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class HealthSnapshot:
    exact_sha: str
    captured_at: str
    storage_available: bool
    storage_latency_ms: float
    queue_depth: int
    provider_failures: int
    report_failures: int
    delivery_gate_blocks: int
    delivery_failures: int
    active_runs: int
    stale_runs: int
    log_redaction_verified: bool
    metrics_digest: str
    status: str
    issues: tuple[str, ...]


@dataclass(frozen=True)
class OperationalThresholds:
    max_storage_latency_ms: float = 500.0
    max_queue_depth: int = 100
    max_provider_failures: int = 5
    max_report_failures: int = 1
    max_delivery_failures: int = 1
    max_stale_runs: int = 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def redact_log_text(value: str) -> str:
    output = str(value or "")
    output = _AUTHORIZATION_PATTERN.sub(lambda match: f"{match.group(1)}<redacted>", output)
    output = _PRIVATE_TOKEN_PATTERN.sub(lambda match: f"{match.group(1)}<redacted>", output)
    output = _SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}<redacted>",
        output,
    )
    return output


def verify_log_redaction(samples: Iterable[str], forbidden_values: Iterable[str] = ()) -> bool:
    forbidden = [str(item) for item in forbidden_values if str(item)]
    for sample in samples:
        redacted = redact_log_text(sample)
        if any(value in redacted for value in forbidden):
            return False
        lowered = redacted.lower()
        if re.search(r"authorization\s*[:=]\s*(?!<redacted>)\S+", lowered):
            return False
        if re.search(r"private-token\s*[:=]\s*(?!<redacted>)\S+", lowered):
            return False
        if re.search(r"(?:token|secret|password|database_url)\s*[:=]\s*(?!<redacted>)\S+", lowered):
            return False
    return True


def _digest(points: Iterable[MetricPoint]) -> str:
    canonical = "\n".join(
        f"{point.name}|{point.value}|{point.timestamp}|"
        + ",".join(f"{key}={value}" for key, value in sorted(point.labels.items()))
        for point in sorted(points, key=lambda item: (item.name, item.timestamp, sorted(item.labels.items())))
    )
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"


def build_health_snapshot(
    *,
    exact_sha: str,
    points: Iterable[MetricPoint],
    log_samples: Iterable[str],
    forbidden_log_values: Iterable[str] = (),
    thresholds: OperationalThresholds | None = None,
    captured_at: str = "",
) -> HealthSnapshot:
    selected = thresholds or OperationalThresholds()
    items = tuple(points)
    latest: dict[str, float] = {}
    for point in items:
        latest[point.name] = point.value
    required = {
        "storage_available",
        "storage_latency_ms",
        "queue_depth",
        "provider_collection_failures",
        "report_generation_failures",
        "delivery_gate_blocks",
        "delivery_failures",
        "active_runs",
        "stale_runs",
    }
    missing = sorted(required - set(latest))
    issues = [f"metric_missing:{name}" for name in missing]
    storage_available = bool(latest.get("storage_available", 0))
    storage_latency = float(latest.get("storage_latency_ms", 0))
    queue_depth = int(latest.get("queue_depth", 0))
    provider_failures = int(latest.get("provider_collection_failures", 0))
    report_failures = int(latest.get("report_generation_failures", 0))
    delivery_gate_blocks = int(latest.get("delivery_gate_blocks", 0))
    delivery_failures = int(latest.get("delivery_failures", 0))
    active_runs = int(latest.get("active_runs", 0))
    stale_runs = int(latest.get("stale_runs", 0))
    redaction = verify_log_redaction(log_samples, forbidden_log_values)

    if not exact_sha:
        issues.append("health_exact_sha_required")
    if not storage_available:
        issues.append("storage_unavailable")
    if storage_latency > selected.max_storage_latency_ms:
        issues.append("storage_latency_exceeded")
    if queue_depth > selected.max_queue_depth:
        issues.append("queue_depth_exceeded")
    if provider_failures > selected.max_provider_failures:
        issues.append("provider_failures_exceeded")
    if report_failures > selected.max_report_failures:
        issues.append("report_failures_exceeded")
    if delivery_failures > selected.max_delivery_failures:
        issues.append("delivery_failures_exceeded")
    if stale_runs > selected.max_stale_runs:
        issues.append("stale_runs_detected")
    if not redaction:
        issues.append("log_redaction_failed")

    return HealthSnapshot(
        exact_sha=exact_sha,
        captured_at=captured_at or _utc_now(),
        storage_available=storage_available,
        storage_latency_ms=storage_latency,
        queue_depth=queue_depth,
        provider_failures=provider_failures,
        report_failures=report_failures,
        delivery_gate_blocks=delivery_gate_blocks,
        delivery_failures=delivery_failures,
        active_runs=active_runs,
        stale_runs=stale_runs,
        log_redaction_verified=redaction,
        metrics_digest=_digest(items),
        status="healthy" if not issues else "degraded",
        issues=tuple(issues),
    )


def alert_conditions(snapshot: HealthSnapshot) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "alert_key": f"operational:{issue}",
            "severity": "critical" if issue in {"storage_unavailable", "log_redaction_failed", "stale_runs_detected"} else "high",
            "summary": issue.replace("_", " "),
            "exact_sha": snapshot.exact_sha,
            "metrics_digest": snapshot.metrics_digest,
            "captured_at": snapshot.captured_at,
        }
        for issue in snapshot.issues
    )


__all__ = [
    "HealthSnapshot",
    "MetricPoint",
    "OperationalThresholds",
    "alert_conditions",
    "build_health_snapshot",
    "redact_log_text",
    "verify_log_redaction",
]
