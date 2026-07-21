from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Callable, Iterable, Mapping

from nico.monitor_execute_service import MonitorExecuteService


class MonitorSchedulerError(RuntimeError):
    pass


@dataclass(frozen=True)
class MonitorCadence:
    interval_seconds: int = 3600
    stale_after_seconds: int = 7200
    max_consecutive_failures: int = 5

    def validate(self) -> None:
        if self.interval_seconds < 60:
            raise MonitorSchedulerError("monitor_interval_too_short")
        if self.stale_after_seconds < self.interval_seconds:
            raise MonitorSchedulerError("monitor_stale_window_too_short")
        if self.max_consecutive_failures < 1:
            raise MonitorSchedulerError("monitor_failure_limit_invalid")


@dataclass(frozen=True)
class RepositoryObservation:
    repository: str
    immutable_sha: str
    observed_at: str
    canonical_score: float
    evidence_completeness: float
    deployment_state: str
    provider_state: str
    findings: tuple[Mapping[str, Any], ...]
    artifact_digest: str
    human_review_required: bool = True
    client_delivery_allowed: bool = False


@dataclass(frozen=True)
class ChangeEvent:
    event_id: str
    repository: str
    before_sha: str
    after_sha: str
    change_type: str
    severity: str
    summary: str
    evidence_ids: tuple[str, ...]
    dedup_key: str
    detected_at: str


@dataclass(frozen=True)
class AlertPolicy:
    minimum_severity: str = "medium"
    score_drop_threshold: float = 5.0
    evidence_drop_threshold: float = 10.0
    escalation_after_seconds: int = 3600
    destinations: tuple[str, ...] = ("dashboard",)


@dataclass(frozen=True)
class AlertRecord:
    alert_id: str
    event_id: str
    destination: str
    status: str
    created_at: str
    acknowledged_at: str = ""
    escalated_at: str = ""


@dataclass(frozen=True)
class MonitorRunState:
    monitor_id: str
    repository: str
    customer_id: str
    project_id: str
    last_sha: str = ""
    last_observed_at: str = ""
    next_run_at: str = ""
    consecutive_failures: int = 0
    last_error: str = ""
    revision: int = 1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    token = str(value or "").strip()
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    parsed = datetime.fromisoformat(token)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _digest(parts: Iterable[str]) -> str:
    return f"sha256:{sha256('|'.join(parts).encode('utf-8')).hexdigest()}"


def _severity_rank(value: str) -> int:
    return {
        "info": 0,
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4,
    }.get(str(value or "").lower(), 0)


def _finding_id(finding: Mapping[str, Any]) -> str:
    return str(
        finding.get("finding_id")
        or finding.get("id")
        or _digest(
            (
                str(finding.get("rule") or ""),
                str(finding.get("path") or ""),
                str(finding.get("line") or ""),
                str(finding.get("title") or ""),
            )
        )
    )


def validate_observation(observation: RepositoryObservation) -> list[str]:
    issues: list[str] = []
    if not observation.repository:
        issues.append("monitor_observation_repository_required")
    if not observation.immutable_sha:
        issues.append("monitor_observation_sha_required")
    if not observation.observed_at:
        issues.append("monitor_observation_time_required")
    if not observation.artifact_digest.startswith("sha256:"):
        issues.append("monitor_observation_artifact_digest_required")
    if not (0 <= observation.canonical_score <= 100):
        issues.append("monitor_observation_score_invalid")
    if not (0 <= observation.evidence_completeness <= 100):
        issues.append("monitor_observation_evidence_invalid")
    if not observation.human_review_required:
        issues.append("monitor_observation_human_review_required")
    if observation.client_delivery_allowed:
        issues.append("monitor_observation_delivery_must_be_blocked")
    return issues


def _event(
    *,
    previous: RepositoryObservation,
    current: RepositoryObservation,
    change_type: str,
    severity: str,
    summary: str,
    evidence_ids: Iterable[str] = (),
) -> ChangeEvent:
    evidence = tuple(dict.fromkeys(str(item) for item in evidence_ids if str(item)))
    dedup = _digest((current.repository, change_type, ",".join(evidence), current.immutable_sha))
    return ChangeEvent(
        event_id=_digest((dedup, current.observed_at)),
        repository=current.repository,
        before_sha=previous.immutable_sha,
        after_sha=current.immutable_sha,
        change_type=change_type,
        severity=severity,
        summary=summary,
        evidence_ids=evidence,
        dedup_key=dedup,
        detected_at=current.observed_at,
    )


def detect_changes(
    previous: RepositoryObservation,
    current: RepositoryObservation,
    *,
    policy: AlertPolicy | None = None,
) -> tuple[ChangeEvent, ...]:
    selected = policy or AlertPolicy()
    issues = validate_observation(previous) + validate_observation(current)
    if issues:
        raise MonitorSchedulerError(",".join(issues))
    if previous.repository != current.repository:
        raise MonitorSchedulerError("monitor_repository_identity_drift")
    events: list[ChangeEvent] = []

    if previous.immutable_sha != current.immutable_sha:
        events.append(
            _event(
                previous=previous,
                current=current,
                change_type="repository_revision_changed",
                severity="info",
                summary="The monitored repository advanced to a new immutable revision.",
            )
        )

    score_drop = previous.canonical_score - current.canonical_score
    if score_drop >= selected.score_drop_threshold:
        severity = "high" if score_drop >= 15 else "medium"
        events.append(
            _event(
                previous=previous,
                current=current,
                change_type="canonical_score_regressed",
                severity=severity,
                summary=f"Canonical score decreased by {score_drop:.1f} points.",
            )
        )

    evidence_drop = previous.evidence_completeness - current.evidence_completeness
    if evidence_drop >= selected.evidence_drop_threshold:
        events.append(
            _event(
                previous=previous,
                current=current,
                change_type="evidence_completeness_regressed",
                severity="medium",
                summary=f"Evidence completeness decreased by {evidence_drop:.1f} points.",
            )
        )

    if previous.provider_state == "ready" and current.provider_state != "ready":
        events.append(
            _event(
                previous=previous,
                current=current,
                change_type="provider_collection_degraded",
                severity="high",
                summary=f"Provider collection changed from ready to {current.provider_state}.",
            )
        )

    if previous.deployment_state == "success" and current.deployment_state != "success":
        events.append(
            _event(
                previous=previous,
                current=current,
                change_type="deployment_degraded",
                severity="critical",
                summary=f"Deployment state changed from success to {current.deployment_state}.",
            )
        )

    previous_findings = {_finding_id(item): item for item in previous.findings}
    current_findings = {_finding_id(item): item for item in current.findings}
    for finding_id in sorted(set(current_findings) - set(previous_findings)):
        finding = current_findings[finding_id]
        severity = str(finding.get("severity") or "medium").lower()
        events.append(
            _event(
                previous=previous,
                current=current,
                change_type="new_finding",
                severity=severity,
                summary=str(finding.get("title") or f"New finding {finding_id}"),
                evidence_ids=(finding_id, str(finding.get("evidence_id") or "")),
            )
        )

    minimum = _severity_rank(selected.minimum_severity)
    unique: dict[str, ChangeEvent] = {}
    for event in events:
        if event.change_type == "repository_revision_changed" or _severity_rank(event.severity) >= minimum:
            unique.setdefault(event.dedup_key, event)
    return tuple(unique.values())


def build_alerts(
    events: Iterable[ChangeEvent],
    *,
    policy: AlertPolicy,
    existing_dedup_keys: Iterable[str] = (),
) -> tuple[AlertRecord, ...]:
    seen = set(existing_dedup_keys)
    alerts: list[AlertRecord] = []
    for event in events:
        if event.dedup_key in seen:
            continue
        seen.add(event.dedup_key)
        for destination in policy.destinations:
            alerts.append(
                AlertRecord(
                    alert_id=_digest((event.event_id, destination)),
                    event_id=event.event_id,
                    destination=destination,
                    status="pending",
                    created_at=event.detected_at,
                )
            )
    return tuple(alerts)


def escalate_alert(
    alert: AlertRecord,
    *,
    policy: AlertPolicy,
    now: str,
) -> AlertRecord:
    if alert.status not in {"pending", "sent"} or alert.acknowledged_at:
        return alert
    elapsed = (_parse(now) - _parse(alert.created_at)).total_seconds()
    if elapsed < policy.escalation_after_seconds:
        return alert
    return replace(alert, status="escalated", escalated_at=now)


def next_run_state(
    state: MonitorRunState,
    *,
    cadence: MonitorCadence,
    success: bool,
    observed_sha: str = "",
    error: str = "",
    now: datetime | None = None,
) -> MonitorRunState:
    cadence.validate()
    current = now or _utc_now()
    failures = 0 if success else state.consecutive_failures + 1
    delay = cadence.interval_seconds
    if failures:
        delay = min(cadence.stale_after_seconds, delay * (2 ** min(failures, 8)))
    return replace(
        state,
        last_sha=observed_sha or state.last_sha,
        last_observed_at=_iso(current) if success else state.last_observed_at,
        next_run_at=_iso(current + timedelta(seconds=delay)),
        consecutive_failures=failures,
        last_error="" if success else str(error or "monitor_run_failed"),
        revision=state.revision + 1,
    )


def create_remediation_work_items(
    *,
    service: MonitorExecuteService,
    events: Iterable[ChangeEvent],
    observation: RepositoryObservation,
    customer_id: str,
    project_id: str,
) -> tuple[dict[str, Any], ...]:
    created: list[dict[str, Any]] = []
    for event in events:
        if event.change_type != "new_finding" or _severity_rank(event.severity) < _severity_rank("high"):
            continue
        work_item_id = _digest((observation.repository, event.dedup_key))
        created.append(
            service.create(
                {
                    "work_item_id": work_item_id,
                    "repository": observation.repository,
                    "immutable_sha": observation.immutable_sha,
                    "customer_id": customer_id,
                    "project_id": project_id,
                    "evidence_id": event.evidence_ids[0] if event.evidence_ids else event.event_id,
                    "finding": {
                        "finding_id": event.evidence_ids[0] if event.evidence_ids else event.event_id,
                        "severity": event.severity,
                        "title": event.summary,
                        "change_event_id": event.event_id,
                    },
                }
            )
        )
    return tuple(created)


def observation_digest(observation: RepositoryObservation) -> str:
    payload = {
        "repository": observation.repository,
        "immutable_sha": observation.immutable_sha,
        "canonical_score": observation.canonical_score,
        "evidence_completeness": observation.evidence_completeness,
        "deployment_state": observation.deployment_state,
        "provider_state": observation.provider_state,
        "finding_ids": sorted(_finding_id(item) for item in observation.findings),
        "artifact_digest": observation.artifact_digest,
    }
    return f"sha256:{sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()}"


__all__ = [
    "AlertPolicy",
    "AlertRecord",
    "ChangeEvent",
    "MonitorCadence",
    "MonitorRunState",
    "MonitorSchedulerError",
    "RepositoryObservation",
    "build_alerts",
    "create_remediation_work_items",
    "detect_changes",
    "escalate_alert",
    "next_run_state",
    "observation_digest",
    "validate_observation",
]
