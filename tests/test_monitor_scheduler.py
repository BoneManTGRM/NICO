from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from nico.monitor_execute_service import MonitorExecuteService, MonitorExecuteStore
from nico.monitor_scheduler import (
    AlertPolicy,
    MonitorCadence,
    MonitorRunState,
    RepositoryObservation,
    build_alerts,
    create_remediation_work_items,
    detect_changes,
    escalate_alert,
    next_run_state,
    observation_digest,
)


def _observation(
    *,
    sha: str,
    score: float = 90,
    evidence: float = 95,
    deployment: str = "success",
    provider: str = "ready",
    findings: tuple[dict, ...] = (),
    observed_at: str = "2026-07-21T00:00:00Z",
) -> RepositoryObservation:
    return RepositoryObservation(
        repository="BoneManTGRM/NICO",
        immutable_sha=sha,
        observed_at=observed_at,
        canonical_score=score,
        evidence_completeness=evidence,
        deployment_state=deployment,
        provider_state=provider,
        findings=findings,
        artifact_digest="sha256:artifact",
    )


def test_change_detection_captures_regressions_and_new_findings() -> None:
    previous = _observation(sha="a" * 40)
    current = _observation(
        sha="b" * 40,
        score=70,
        evidence=80,
        deployment="failed",
        provider="rate_limited",
        findings=(
            {
                "finding_id": "F-1",
                "severity": "critical",
                "title": "New critical exposure",
                "evidence_id": "E-1",
            },
        ),
        observed_at="2026-07-21T01:00:00Z",
    )
    events = detect_changes(previous, current, policy=AlertPolicy(minimum_severity="medium"))
    kinds = {item.change_type for item in events}

    assert "repository_revision_changed" in kinds
    assert "canonical_score_regressed" in kinds
    assert "evidence_completeness_regressed" in kinds
    assert "provider_collection_degraded" in kinds
    assert "deployment_degraded" in kinds
    assert "new_finding" in kinds
    assert len({item.dedup_key for item in events}) == len(events)


def test_alerts_deduplicate_and_escalate_only_when_unacknowledged() -> None:
    events = detect_changes(
        _observation(sha="a" * 40),
        _observation(
            sha="b" * 40,
            deployment="failed",
            observed_at="2026-07-21T00:00:00Z",
        ),
    )
    policy = AlertPolicy(destinations=("dashboard", "email"), escalation_after_seconds=60)
    alerts = build_alerts(events, policy=policy)
    assert len(alerts) == len(events) * 2

    duplicate = build_alerts(
        events,
        policy=policy,
        existing_dedup_keys=[item.dedup_key for item in events],
    )
    assert duplicate == ()

    escalated = escalate_alert(alerts[0], policy=policy, now="2026-07-21T00:02:00Z")
    assert escalated.status == "escalated"
    assert escalated.escalated_at == "2026-07-21T00:02:00Z"


def test_scheduler_backoff_resets_after_success() -> None:
    state = MonitorRunState(
        monitor_id="monitor-1",
        repository="BoneManTGRM/NICO",
        customer_id="customer-1",
        project_id="project-1",
    )
    cadence = MonitorCadence(interval_seconds=60, stale_after_seconds=600)
    failed = next_run_state(
        state,
        cadence=cadence,
        success=False,
        error="provider_outage",
        now=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    failed_again = next_run_state(
        failed,
        cadence=cadence,
        success=False,
        error="provider_outage",
        now=datetime(2026, 7, 21, 0, 1, tzinfo=timezone.utc),
    )
    recovered = next_run_state(
        failed_again,
        cadence=cadence,
        success=True,
        observed_sha="b" * 40,
        now=datetime(2026, 7, 21, 0, 3, tzinfo=timezone.utc),
    )

    assert failed.consecutive_failures == 1
    assert failed_again.consecutive_failures == 2
    assert recovered.consecutive_failures == 0
    assert recovered.last_error == ""
    assert recovered.last_sha == "b" * 40


def test_high_new_findings_create_observed_work_items_without_approval(tmp_path: Path) -> None:
    store = MonitorExecuteStore(lambda: sqlite3.connect(tmp_path / "monitor.db"), dialect="sqlite")
    store.ensure_schema()
    service = MonitorExecuteService(store)
    previous = _observation(sha="a" * 40)
    current = _observation(
        sha="b" * 40,
        findings=(
            {"finding_id": "F-HIGH", "severity": "high", "title": "High finding"},
            {"finding_id": "F-LOW", "severity": "low", "title": "Low finding"},
        ),
        observed_at="2026-07-21T01:00:00Z",
    )
    events = detect_changes(previous, current, policy=AlertPolicy(minimum_severity="low"))
    created = create_remediation_work_items(
        service=service,
        events=events,
        observation=current,
        customer_id="customer-1",
        project_id="project-1",
    )

    assert len(created) == 1
    assert created[0]["state"] == "observed"
    assert created[0]["finding"]["finding_id"] == "F-HIGH"
    assert created[0]["approval"] is None
    assert created[0]["client_delivery_allowed"] is False


def test_observation_digest_is_deterministic_and_changes_with_truth() -> None:
    first = _observation(sha="a" * 40)
    same = _observation(sha="a" * 40, observed_at="2026-07-22T00:00:00Z")
    changed = _observation(sha="b" * 40)
    assert observation_digest(first) == observation_digest(same)
    assert observation_digest(first) != observation_digest(changed)
