from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from math import ceil
from typing import Any

from nico import comprehensive_review_work_v1 as legacy

VERSION = "nico.comprehensive_review_work.v2"
PROJECTION_SCHEMA = "nico.comprehensive_review_work_projection.v2"
QC_SAMPLING_VERSION = "nico.phase2.qc_sampling.v2"
_ALLOWED_SAMPLING_STRATEGIES = {"deterministic", "risk_weighted"}
_QC_OUTCOMES = {"agree", "disagree"}
_SCOPE_FIELDS = (
    "run_id",
    "repository",
    "commit_sha",
    "evidence_ledger_id",
    "customer_id",
    "project_id",
    "client_id",
    "workspace_id",
    "organization_id",
    "tenant_id",
)
_SEVERITY_RANK = {
    "critical": 5,
    "material": 5,
    "high": 4,
    "medium": 3,
    "moderate": 3,
    "low": 2,
    "informational": 1,
    "info": 1,
    "unknown": 0,
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now(value: datetime | None = None) -> datetime:
    return (value or datetime.now(UTC)).astimezone(UTC)


def _iso(value: datetime | None = None) -> str:
    return _now(value).isoformat()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _scope_binding(record: Mapping[str, Any]) -> dict[str, str]:
    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    scope: dict[str, str] = {}
    for field in _SCOPE_FIELDS:
        value = identity.get(field)
        if value in (None, ""):
            value = record.get(field)
        normalized = _text(value)
        if normalized:
            scope[field] = normalized
    return scope


def _source_fingerprint(record: Mapping[str, Any]) -> str:
    return _canonical_hash(
        {
            "scope": _scope_binding(record),
            "canonical_scanner_finding_register": legacy.canonical_candidate_register(record),
        }
    )


def _catalog(record: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    register = legacy.canonical_candidate_register(record)
    rows = register.get("findings") if isinstance(register, Mapping) else []
    candidates = {
        _text(row.get("candidate_id")): deepcopy(dict(row))
        for row in rows or []
        if isinstance(row, Mapping) and _text(row.get("candidate_id"))
    }
    raw_clusters = register.get("review_workload_clusters") if isinstance(register, Mapping) else []
    clusters = [deepcopy(dict(row)) for row in raw_clusters or [] if isinstance(row, Mapping)]
    return candidates, clusters


def _triage(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    value = candidate.get("technical_triage")
    return value if isinstance(value, Mapping) else {}


def _verdict(candidate: Mapping[str, Any]) -> str:
    triage = _triage(candidate)
    return _text(
        triage.get("verdict")
        or candidate.get("technical_triage_verdict")
        or candidate.get("triage_verdict")
        or candidate.get("verdict")
    ).casefold()


def _confidence(candidate: Mapping[str, Any]) -> float:
    triage = _triage(candidate)
    value = triage.get(
        "confidence",
        candidate.get("technical_triage_confidence", candidate.get("triage_confidence", 0.0)),
    )
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _severity(candidate: Mapping[str, Any]) -> str:
    return _text(candidate.get("severity") or "unknown").casefold()


def _evidence_change(candidate: Mapping[str, Any]) -> str:
    lineage = candidate.get("lineage") if isinstance(candidate.get("lineage"), Mapping) else {}
    return _text(
        candidate.get("evidence_change_state")
        or candidate.get("lineage_status")
        or lineage.get("evidence_change_state")
        or lineage.get("status")
    ).casefold()


def _proof_gaps(candidate: Mapping[str, Any]) -> list[Any]:
    value = candidate.get("proof_gaps")
    if isinstance(value, list):
        return value
    triage = _triage(candidate)
    value = triage.get("proof_gaps")
    return value if isinstance(value, list) else []


def _conflicting(candidate: Mapping[str, Any]) -> bool:
    triage = _triage(candidate)
    return bool(
        candidate.get("conflicting_evidence")
        or candidate.get("counterevidence_conflict")
        or triage.get("conflicting_evidence")
    )


def _is_material(candidate: Mapping[str, Any]) -> bool:
    return (
        _severity(candidate) in {"critical", "material", "high"}
        or _verdict(candidate) == "confirmed"
        or _text(candidate.get("review_routing_class")).upper() == "CRITICAL_ATTENTION"
    )


def _needs_individual_attention(candidate: Mapping[str, Any]) -> bool:
    if candidate.get("review_requires_individual_attention") is True:
        return True
    changed = _evidence_change(candidate) in {
        "changed",
        "materially_changed",
        "significant_change",
    }
    verdict = _verdict(candidate)
    low_confidence = bool(verdict) and _confidence(candidate) < 0.85
    return bool(
        _is_material(candidate)
        or verdict == "needs_review"
        or low_confidence
        or _proof_gaps(candidate)
        or _conflicting(candidate)
        or changed
    )


def _grouped_eligible(candidate: Mapping[str, Any]) -> bool:
    return bool(
        candidate.get("grouped_review_eligible") is True
        and candidate.get("homogeneous_evidence") is not False
        and candidate.get("homogeneous_verdict") is not False
        and not _needs_individual_attention(candidate)
    )


def _qc_population(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates, _ = _catalog(record)
    population: list[dict[str, Any]] = []
    for candidate_id, candidate in candidates.items():
        if _verdict(candidate) != "not_actionable":
            continue
        if _confidence(candidate) < 0.85 or _is_material(candidate):
            continue
        if _proof_gaps(candidate) or _conflicting(candidate):
            continue
        if _evidence_change(candidate) in {
            "changed",
            "materially_changed",
            "significant_change",
        }:
            continue
        population.append({"candidate_id": candidate_id, "candidate": candidate})
    return population


def _risk_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
    candidate = item["candidate"]
    return (
        -_SEVERITY_RANK.get(_severity(candidate), 0),
        _confidence(candidate),
        _text(item["candidate_id"]),
    )


def _default_sampling_configuration(
    record: Mapping[str, Any],
    ledger: Mapping[str, Any],
) -> dict[str, Any]:
    population = _qc_population(record)
    population_ids = sorted(_text(item["candidate_id"]) for item in population)
    population_set = set(population_ids)
    selected = sorted(
        _text(value)
        for value in ledger.get("qc_required_candidate_ids") or []
        if _text(value) in population_set
    )
    return {
        "sampling_strategy": "deterministic",
        "sampling_version": QC_SAMPLING_VERSION,
        "population_candidate_ids": population_ids,
        "population_size": len(population_ids),
        "sample_size": len(selected),
        "selected_candidate_ids": selected,
        "risk_reason_basis": {
            candidate_id: "retained deterministic cluster representative"
            for candidate_id in selected
        },
        "configured_by": "canonical_default",
        "configured_by_role": "canonical_default",
        "configured_at": _text(ledger.get("updated_at")),
        "sampling_does_not_approve_unsampled_candidates": True,
    }


def _prepare_ledger(record: Mapping[str, Any]) -> dict[str, Any]:
    ledger = legacy.ledger_for_record(record)
    source_sha = _source_fingerprint(record)
    existing_source = _text(ledger.get("review_source_sha256"))
    if existing_source and existing_source != source_sha:
        raise ValueError("review_work_source_evidence_changed")
    scope = _scope_binding(record)
    existing_scope = ledger.get("scope_binding")
    if isinstance(existing_scope, Mapping) and dict(existing_scope) != scope:
        raise ValueError("review_work_scope_binding_changed")
    ledger["review_source_sha256"] = source_sha
    ledger["scope_binding"] = scope
    if not isinstance(ledger.get("quality_control_sampling"), Mapping):
        ledger["quality_control_sampling"] = _default_sampling_configuration(record, ledger)
    return ledger


def _record_with_ledger(record: Mapping[str, Any], ledger: Mapping[str, Any]) -> dict[str, Any]:
    updated = deepcopy(dict(record))
    updated["review_work_ledger"] = deepcopy(dict(ledger))
    return updated


def _require_human(payload: Mapping[str, Any]) -> tuple[str, str]:
    if payload.get("review_authorized") is not True or payload.get("authorization_confirmed") is not True:
        raise ValueError("explicit_review_authorization_required")
    reviewer = _text(payload.get("reviewer"))
    role = _text(payload.get("reviewer_role"))
    if not reviewer:
        raise ValueError("reviewer_required")
    if not role:
        raise ValueError("reviewer_role_required")
    return reviewer, role


def _record_reviewer_identity(
    ledger: dict[str, Any], reviewer: str, reviewer_role: str, timestamp: datetime
) -> None:
    identities = dict(ledger.get("reviewer_identities") or {})
    key = reviewer.casefold()
    previous = identities.get(key) if isinstance(identities.get(key), Mapping) else {}
    identities[key] = {
        "reviewer": reviewer,
        "reviewer_role": reviewer_role,
        "first_seen_at": _text(previous.get("first_seen_at")) or _iso(timestamp),
        "last_seen_at": _iso(timestamp),
        "explicit_authorization_confirmed": True,
    }
    ledger["reviewer_identities"] = identities


def _append_event(
    ledger: dict[str, Any],
    *,
    action: str,
    reviewer: str,
    reviewer_role: str,
    payload: Mapping[str, Any],
    timestamp: datetime,
) -> None:
    events = [dict(item) for item in ledger.get("audit_events") or [] if isinstance(item, Mapping)]
    sequence = len(events) + 1
    previous_hash = _text(events[-1].get("event_sha256")) if events else ""
    event = {
        "sequence": sequence,
        "action": action,
        "reviewer": reviewer,
        "reviewer_role": reviewer_role,
        "recorded_at": _iso(timestamp),
        "previous_event_sha256": previous_hash,
        "payload": {
            key: deepcopy(value)
            for key, value in payload.items()
            if key not in {"operator_token"}
        },
    }
    event["event_sha256"] = _canonical_hash(event)
    events.append(event)
    ledger["audit_events"] = events
    ledger["updated_at"] = _iso(timestamp)
    ledger["human_review_required"] = True
    ledger["client_delivery_allowed"] = False


def _configure_sampling(
    record: Mapping[str, Any],
    ledger: dict[str, Any],
    payload: Mapping[str, Any],
    *,
    now: datetime | None,
) -> dict[str, Any]:
    reviewer, reviewer_role = _require_human(payload)
    timestamp = _now(now)
    strategy = _text(payload.get("sampling_strategy") or "deterministic").casefold()
    if strategy not in _ALLOWED_SAMPLING_STRATEGIES:
        raise ValueError("review_work_qc_sampling_strategy_invalid")
    population = _qc_population(record)
    population_ids = sorted(_text(item["candidate_id"]) for item in population)
    requested = payload.get("sample_size")
    if requested in (None, ""):
        sample_size = (
            min(len(population_ids), max(1, ceil(len(population_ids) * 0.05)))
            if population_ids
            else 0
        )
    else:
        try:
            sample_size = int(requested)
        except (TypeError, ValueError) as exc:
            raise ValueError("review_work_qc_sample_size_must_be_integer") from exc
        if sample_size < 0 or sample_size > len(population_ids):
            raise ValueError("review_work_qc_sample_size_out_of_range")
    ordered = (
        sorted(population, key=_risk_key)
        if strategy == "risk_weighted"
        else sorted(population, key=lambda item: _text(item["candidate_id"]))
    )
    selected = [_text(item["candidate_id"]) for item in ordered[:sample_size]]
    candidates, _ = _catalog(record)
    reason_basis = {
        candidate_id: (
            f"{strategy}; severity={_severity(candidates[candidate_id])}; "
            f"technical_verdict={_verdict(candidates[candidate_id])}; "
            f"confidence={_confidence(candidates[candidate_id]):.3f}"
        )
        for candidate_id in selected
    }
    ledger["quality_control_sampling"] = {
        "sampling_strategy": strategy,
        "sampling_version": QC_SAMPLING_VERSION,
        "population_candidate_ids": population_ids,
        "population_size": len(population_ids),
        "sample_size": len(selected),
        "selected_candidate_ids": selected,
        "risk_reason_basis": reason_basis,
        "configured_by": reviewer,
        "configured_by_role": reviewer_role,
        "configured_at": _iso(timestamp),
        "sampling_does_not_approve_unsampled_candidates": True,
    }
    _record_reviewer_identity(ledger, reviewer, reviewer_role, timestamp)
    _append_event(
        ledger,
        action="configure_qc_sampling",
        reviewer=reviewer,
        reviewer_role=reviewer_role,
        payload={
            "sampling_strategy": strategy,
            "sampling_version": QC_SAMPLING_VERSION,
            "population_size": len(population_ids),
            "sample_size": len(selected),
            "selected_candidate_ids": selected,
        },
        timestamp=timestamp,
    )
    return ledger


def _configured_qc_ids(ledger: Mapping[str, Any]) -> list[str]:
    config = ledger.get("quality_control_sampling")
    if not isinstance(config, Mapping):
        return []
    return sorted({_text(value) for value in config.get("selected_candidate_ids") or [] if _text(value)})


def _effective_qc_ids(ledger: Mapping[str, Any]) -> list[str]:
    required = {_text(value) for value in ledger.get("qc_required_candidate_ids") or [] if _text(value)}
    required.update(_configured_qc_ids(ledger))
    return sorted(required)


def _additional_quality_control(
    record: Mapping[str, Any],
    ledger: dict[str, Any],
    payload: Mapping[str, Any],
    *,
    now: datetime | None,
) -> dict[str, Any]:
    reviewer, reviewer_role = _require_human(payload)
    timestamp = _now(now)
    candidate_id = _text(payload.get("candidate_id"))
    configured = set(_configured_qc_ids(ledger))
    if candidate_id not in configured:
        raise ValueError("review_work_qc_candidate_not_required")
    candidates, _ = _catalog(record)
    if candidate_id not in candidates:
        raise ValueError("review_work_qc_candidate_not_required")
    dispositions = ledger.get("dispositions") if isinstance(ledger.get("dispositions"), Mapping) else {}
    disposition = dispositions.get(candidate_id) if isinstance(dispositions, Mapping) else None
    if not isinstance(disposition, Mapping):
        raise ValueError("review_work_qc_requires_candidate_disposition")
    if _text(disposition.get("reviewer")).casefold() == reviewer.casefold():
        raise ValueError("review_work_qc_requires_independent_reviewer")
    outcome = _text(payload.get("qc_outcome")).casefold()
    note = _text(payload.get("qc_note"))
    if outcome not in _QC_OUTCOMES or not note:
        raise ValueError("review_work_qc_outcome_and_note_required")
    quality_control = dict(ledger.get("quality_control") or {})
    quality_control[candidate_id] = {
        "candidate_id": candidate_id,
        "qc_outcome": outcome,
        "qc_note": note,
        "reviewer": reviewer,
        "reviewer_role": reviewer_role,
        "reviewed_at": _iso(timestamp),
        "independent_reviewer_verified": True,
    }
    ledger["quality_control"] = quality_control
    _record_reviewer_identity(ledger, reviewer, reviewer_role, timestamp)
    _append_event(
        ledger,
        action="quality_control",
        reviewer=reviewer,
        reviewer_role=reviewer_role,
        payload={"candidate_id": candidate_id, "qc_outcome": outcome, "qc_note": note},
        timestamp=timestamp,
    )
    return ledger


def apply_review_work_action(
    record: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    ledger = _prepare_ledger(record)
    prepared_record = _record_with_ledger(record, ledger)
    action = _text(payload.get("action")).casefold()
    if action == "configure_qc_sampling":
        return _configure_sampling(prepared_record, ledger, payload, now=now)
    if action == "quality_control":
        candidate_id = _text(payload.get("candidate_id"))
        legacy_required = {
            _text(value) for value in ledger.get("qc_required_candidate_ids") or [] if _text(value)
        }
        if candidate_id in set(_configured_qc_ids(ledger)) and candidate_id not in legacy_required:
            return _additional_quality_control(prepared_record, ledger, payload, now=now)
    updated = legacy.apply_review_work_action(prepared_record, payload, now=now)
    updated["review_source_sha256"] = _source_fingerprint(record)
    updated["scope_binding"] = _scope_binding(record)
    if not isinstance(updated.get("quality_control_sampling"), Mapping):
        updated["quality_control_sampling"] = _default_sampling_configuration(record, updated)
    return updated


def _primary_queue(candidate: Mapping[str, Any], disposition: Mapping[str, Any] | None) -> str:
    if isinstance(disposition, Mapping):
        return "human_disposition_completed"
    if _is_material(candidate):
        return "critical_material"
    if _needs_individual_attention(candidate):
        return "human_technical_review"
    lineage = _evidence_change(candidate)
    if lineage in {"stable", "carried", "carried_forward", "unchanged"}:
        return "stable_carry_forward"
    return "new_automated_triage_complete"


def review_work_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    ledger = _prepare_ledger(record)
    prepared_record = _record_with_ledger(record, ledger)
    base = legacy.review_work_projection(prepared_record)
    candidates, clusters = _catalog(record)
    dispositions = ledger.get("dispositions") if isinstance(ledger.get("dispositions"), Mapping) else {}
    quality_control = ledger.get("quality_control") if isinstance(ledger.get("quality_control"), Mapping) else {}
    effective_qc = _effective_qc_ids(ledger)
    configured_qc = set(_configured_qc_ids(ledger))
    baseline_qc = {_text(value) for value in ledger.get("qc_required_candidate_ids") or []}

    candidate_rows: list[dict[str, Any]] = []
    queue_counts = {
        "critical_material": 0,
        "human_technical_review": 0,
        "new_automated_triage_complete": 0,
        "stable_carry_forward": 0,
        "quality_control_sample": len(effective_qc),
        "human_disposition_completed": 0,
    }
    for candidate_id, candidate in sorted(candidates.items()):
        disposition = dispositions.get(candidate_id) if isinstance(dispositions, Mapping) else None
        queue = _primary_queue(candidate, disposition if isinstance(disposition, Mapping) else None)
        queue_counts[queue] += 1
        row = deepcopy(candidate)
        row.update(
            {
                "candidate_id": candidate_id,
                "primary_review_queue": queue,
                "quality_control_sample": candidate_id in set(effective_qc),
                "quality_control_source": (
                    "configured"
                    if candidate_id in configured_qc
                    else "canonical_cluster_representative"
                    if candidate_id in baseline_qc
                    else ""
                ),
                "human_disposition": deepcopy(disposition) if isinstance(disposition, Mapping) else None,
                "human_disposition_state": "completed" if isinstance(disposition, Mapping) else "pending",
                "individual_attention_required": _needs_individual_attention(candidate),
                "grouped_review_eligible": _grouped_eligible(candidate),
                "technical_triage_verdict": _verdict(candidate),
                "technical_triage_confidence": _confidence(candidate),
                "evidence_change_state": _evidence_change(candidate),
            }
        )
        candidate_rows.append(row)

    pending_ids = sorted(candidate_id for candidate_id in candidates if candidate_id not in dispositions)
    missing_qc = sorted(
        candidate_id
        for candidate_id in effective_qc
        if not (
            isinstance(quality_control.get(candidate_id), Mapping)
            and quality_control[candidate_id].get("independent_reviewer_verified") is True
        )
    )
    open_requests = [
        dict(item)
        for item in ledger.get("evidence_requests") or []
        if isinstance(item, Mapping) and _text(item.get("status")) == "open"
    ]
    high_impact = {_text(value) for value in ledger.get("high_impact_candidate_ids") or []}
    unresolved_high = sorted(
        candidate_id
        for candidate_id in high_impact
        if not isinstance(dispositions.get(candidate_id), Mapping)
        or not _text(dispositions[candidate_id].get("escalation_resolution"))
        or not _text(dispositions[candidate_id].get("escalation_owner"))
    )
    review_ready = not (pending_ids or missing_qc or open_requests or unresolved_high)

    pending_grouped = {
        candidate_id
        for candidate_id, candidate in candidates.items()
        if candidate_id not in dispositions and _grouped_eligible(candidate)
    }
    clusters_remaining = sum(
        1
        for cluster in clusters
        if any(_text(candidate_id) in pending_grouped for candidate_id in cluster.get("candidate_ids") or [])
    )
    completed_sessions = [
        item
        for item in ledger.get("review_sessions") or []
        if isinstance(item, Mapping) and _text(item.get("status")) == "completed"
    ]
    measured_seconds = sum(max(0, int(item.get("duration_seconds") or 0)) for item in completed_sessions)
    workload = {
        "individual_attention_count": sum(
            1
            for candidate_id, candidate in candidates.items()
            if candidate_id not in dispositions and _needs_individual_attention(candidate)
        ),
        "grouped_review_eligible_count": len(pending_grouped),
        "quality_control_sample_size": len(effective_qc),
        "human_dispositions_pending": len(pending_ids),
        "human_dispositions_completed": len(candidates) - len(pending_ids),
        "clusters_remaining": clusters_remaining,
        "reviewer_interactions": len(ledger.get("audit_events") or []),
        "measured_specialist_seconds": measured_seconds,
        "measured_specialist_hours": round(measured_seconds / 3600.0, 3),
        "four_hour_engineering_target_seconds": 4 * 60 * 60,
        "four_hour_target_is_safety_gate": False,
    }
    return {
        **base,
        "artifact_schema": PROJECTION_SCHEMA,
        "candidates": candidate_rows,
        "clusters": clusters,
        "queue_counts": queue_counts,
        "quality_control_sampling": deepcopy(ledger.get("quality_control_sampling") or {}),
        "quality_control_required_candidate_ids": effective_qc,
        "quality_control_required_count": len(effective_qc),
        "quality_control_completed_count": len(effective_qc) - len(missing_qc),
        "missing_quality_control_candidate_ids": missing_qc,
        "dispositioned_candidate_count": len(candidates) - len(pending_ids),
        "remaining_candidate_count": len(pending_ids),
        "open_evidence_request_count": len(open_requests),
        "open_evidence_requests": open_requests,
        "unresolved_high_impact_candidate_ids": unresolved_high,
        "ready_for_final_approval": review_ready,
        "workload_metrics": workload,
        "review_source_sha256": _text(ledger.get("review_source_sha256")),
        "scope_binding": deepcopy(ledger.get("scope_binding") or {}),
        "ledger": ledger,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def assert_ready_for_approval(record: Mapping[str, Any]) -> dict[str, Any]:
    projection = review_work_projection(record)
    if projection.get("ready_for_final_approval") is not True:
        blockers = {
            "remaining_candidate_count": projection.get("remaining_candidate_count"),
            "quality_control_remaining_count": int(projection.get("quality_control_required_count") or 0)
            - int(projection.get("quality_control_completed_count") or 0),
            "open_evidence_request_count": projection.get("open_evidence_request_count"),
            "unresolved_high_impact_candidate_ids": projection.get("unresolved_high_impact_candidate_ids"),
        }
        raise ValueError(
            "review_work_not_ready_for_approval:"
            + json.dumps(blockers, sort_keys=True, separators=(",", ":"))
        )
    return projection


canonical_candidate_register = legacy.canonical_candidate_register
ledger_for_record = _prepare_ledger
LEDGER_SCHEMA = legacy.LEDGER_SCHEMA


__all__ = [
    "LEDGER_SCHEMA",
    "PROJECTION_SCHEMA",
    "QC_SAMPLING_VERSION",
    "VERSION",
    "apply_review_work_action",
    "assert_ready_for_approval",
    "canonical_candidate_register",
    "ledger_for_record",
    "review_work_projection",
]
