from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from math import ceil
from typing import Any, Mapping

from nico import comprehensive_review_work_v1 as legacy

VERSION = "nico.review_work_ledger.v2"
QC_SAMPLING_VERSION = "nico.phase2.qc_sampling.v2"
_ALLOWED_SAMPLING_STRATEGIES = {"deterministic", "risk_weighted"}
_SCOPE_FIELDS = (
    "run_id",
    "repository",
    "commit_sha",
    "canonical_evidence_ledger_id",
    "project_id",
    "workspace_id",
    "organization_id",
    "tenant_id",
    "client_id",
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


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ledger_hash(ledger: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(ledger))
    payload.pop("state_hash", None)
    return _canonical_hash(payload)


def _scope_binding(record: Mapping[str, Any]) -> dict[str, str]:
    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    scope: dict[str, str] = {}
    for field in _SCOPE_FIELDS:
        value = identity.get(field)
        if value in (None, ""):
            value = record.get(field)
        normalized = str(value or "").strip()
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


def _candidate_rows(record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    register = legacy.canonical_candidate_register(record)
    rows = register.get("candidates") if isinstance(register, Mapping) else []
    result: dict[str, dict[str, Any]] = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            candidate_id = str(row.get("candidate_id") or row.get("finding_id") or "").strip()
            if candidate_id:
                result[candidate_id] = deepcopy(dict(row))
    return result


def _triage(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    value = candidate.get("technical_triage")
    return value if isinstance(value, Mapping) else {}


def _routing(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    value = candidate.get("review_routing")
    return value if isinstance(value, Mapping) else {}


def _lineage(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    value = candidate.get("lineage")
    return value if isinstance(value, Mapping) else {}


def _severity(candidate: Mapping[str, Any]) -> str:
    return str(candidate.get("severity") or "unknown").strip().casefold()


def _verdict(candidate: Mapping[str, Any]) -> str:
    triage = _triage(candidate)
    return str(
        triage.get("verdict")
        or candidate.get("technical_triage_verdict")
        or candidate.get("verdict")
        or ""
    ).strip().casefold()


def _confidence(candidate: Mapping[str, Any]) -> float:
    triage = _triage(candidate)
    value = triage.get("confidence", candidate.get("technical_triage_confidence", 0.0))
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _evidence_change(candidate: Mapping[str, Any]) -> str:
    lineage = _lineage(candidate)
    return str(
        candidate.get("evidence_change_state")
        or lineage.get("evidence_change_state")
        or lineage.get("change_state")
        or ""
    ).strip().casefold()


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
        or triage.get("conflicting_evidence")
        or candidate.get("counterevidence_conflict")
    )


def _is_material(candidate: Mapping[str, Any]) -> bool:
    return _severity(candidate) in {"critical", "material", "high"} or _verdict(candidate) == "confirmed"


def _needs_individual_attention(candidate: Mapping[str, Any]) -> bool:
    changed = _evidence_change(candidate) in {"changed", "materially_changed", "significant_change"}
    return bool(
        _is_material(candidate)
        or _verdict(candidate) == "needs_review"
        or _confidence(candidate) < 0.85
        or _proof_gaps(candidate)
        or _conflicting(candidate)
        or changed
        or _routing(candidate).get("individual_attention_required") is True
    )


def _qc_population(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    population: list[dict[str, Any]] = []
    for candidate_id, candidate in _candidate_rows(record).items():
        routing = _routing(candidate)
        if _verdict(candidate) != "not_actionable":
            continue
        if _confidence(candidate) < 0.85 or _is_material(candidate):
            continue
        if _proof_gaps(candidate) or _conflicting(candidate):
            continue
        if _evidence_change(candidate) in {"changed", "materially_changed", "significant_change"}:
            continue
        if routing.get("individual_attention_required") is True:
            continue
        population.append({"candidate_id": candidate_id, "candidate": candidate})
    return population


def _risk_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
    candidate = item["candidate"]
    return (
        -_SEVERITY_RANK.get(_severity(candidate), 0),
        _confidence(candidate),
        str(item["candidate_id"]),
    )


def _default_sampling_configuration(record: Mapping[str, Any], ledger: Mapping[str, Any]) -> dict[str, Any]:
    population = _qc_population(record)
    population_ids = sorted(str(item["candidate_id"]) for item in population)
    legacy_ids = sorted(
        candidate_id
        for candidate_id in (str(value) for value in ledger.get("quality_control_required_candidate_ids") or [])
        if candidate_id in set(population_ids)
    )
    if population_ids and not legacy_ids:
        legacy_ids = [population_ids[0]]
    return {
        "sampling_strategy": "deterministic",
        "sampling_version": QC_SAMPLING_VERSION,
        "population_candidate_ids": population_ids,
        "population_size": len(population_ids),
        "sample_size": len(legacy_ids),
        "selected_candidate_ids": legacy_ids,
        "risk_reason_basis": {
            candidate_id: "deterministic high-confidence lower-risk not_actionable quality-control sample"
            for candidate_id in legacy_ids
        },
        "configured_by": "system_default",
        "configured_by_role": "system_default",
        "configured_at": str(ledger.get("created_at") or _utc_now()),
        "human_action_required_for_disposition": True,
        "sampling_does_not_approve_unsampled_candidates": True,
    }


def _prepare_ledger(record: Mapping[str, Any]) -> dict[str, Any]:
    ledger = legacy.ledger_for_record(record)
    expected_source = _source_fingerprint(record)
    existing_source = str(ledger.get("review_source_sha256") or "").strip()
    if existing_source and existing_source != expected_source:
        raise ValueError("review_work_source_evidence_changed")

    expected_scope = _scope_binding(record)
    existing_scope = ledger.get("scope_binding")
    if isinstance(existing_scope, Mapping) and dict(existing_scope) != expected_scope:
        raise ValueError("review_work_scope_binding_changed")

    ledger["artifact_schema"] = VERSION
    ledger["review_source_sha256"] = expected_source
    ledger["scope_binding"] = expected_scope
    if not isinstance(ledger.get("quality_control_sampling"), Mapping):
        ledger["quality_control_sampling"] = _default_sampling_configuration(record, ledger)
    ledger["state_hash"] = _ledger_hash(ledger)
    return ledger


def _record_with_prepared_ledger(record: Mapping[str, Any]) -> dict[str, Any]:
    prepared = deepcopy(dict(record))
    prepared["review_work_ledger"] = _prepare_ledger(record)
    return prepared


def _assert_actor(*, reviewer_id: str, reviewer_role: str, reviewer_authorized: bool) -> tuple[str, str]:
    normalized_id = str(reviewer_id or "").strip()
    normalized_role = str(reviewer_role or "").strip()
    if not normalized_id:
        raise ValueError("reviewer_identity_required")
    if not normalized_role:
        raise ValueError("reviewer_role_required")
    if reviewer_authorized is not True:
        raise PermissionError("authorized_reviewer_required")
    return normalized_id, normalized_role


def _assert_revision(ledger: Mapping[str, Any], expected_revision: int | None) -> None:
    current = int(ledger.get("revision") or 0)
    if expected_revision is not None and int(expected_revision) != current:
        raise ValueError(f"review_work_revision_conflict:expected={expected_revision}:actual={current}")


def _append_audit_event(
    ledger: dict[str, Any],
    *,
    action: str,
    reviewer_id: str,
    reviewer_role: str,
    detail: Mapping[str, Any],
) -> None:
    events = list(ledger.get("audit_events") or [])
    revision = int(ledger.get("revision") or 0) + 1
    timestamp = _utc_now()
    previous_hash = str(events[-1].get("event_sha256") or "") if events else ""
    core = {
        "event_id": f"review-event:{revision}",
        "revision": revision,
        "action": action,
        "reviewer_id": reviewer_id,
        "reviewer_role": reviewer_role,
        "reviewer_authorized": True,
        "timestamp": timestamp,
        "detail": deepcopy(dict(detail)),
        "previous_event_sha256": previous_hash,
    }
    event = {**core, "event_sha256": _canonical_hash(core)}
    events.append(event)
    ledger["audit_events"] = events
    ledger["revision"] = revision
    ledger["updated_at"] = timestamp
    ledger["state_hash"] = _ledger_hash(ledger)


def _configured_selected_ids(ledger: Mapping[str, Any]) -> list[str]:
    config = ledger.get("quality_control_sampling")
    if not isinstance(config, Mapping):
        return []
    return sorted({str(value) for value in config.get("selected_candidate_ids") or [] if str(value).strip()})


def _effective_qc_ids(ledger: Mapping[str, Any]) -> list[str]:
    return sorted(
        {
            *(str(value) for value in ledger.get("quality_control_required_candidate_ids") or [] if str(value).strip()),
            *_configured_selected_ids(ledger),
        }
    )


def _configure_sampling(
    record: Mapping[str, Any],
    ledger: dict[str, Any],
    *,
    payload: Mapping[str, Any],
    reviewer_id: str,
    reviewer_role: str,
) -> dict[str, Any]:
    strategy = str(payload.get("sampling_strategy") or "deterministic").strip().casefold()
    if strategy not in _ALLOWED_SAMPLING_STRATEGIES:
        raise ValueError("invalid_quality_control_sampling_strategy")

    population = _qc_population(record)
    population_ids = sorted(str(item["candidate_id"]) for item in population)
    requested = payload.get("sample_size")
    if requested in (None, ""):
        sample_size = min(len(population_ids), max(1, ceil(len(population_ids) * 0.05))) if population_ids else 0
    else:
        try:
            sample_size = int(requested)
        except (TypeError, ValueError) as exc:
            raise ValueError("quality_control_sample_size_must_be_integer") from exc
        if sample_size < 0 or sample_size > len(population_ids):
            raise ValueError("quality_control_sample_size_out_of_range")

    if strategy == "risk_weighted":
        ordered = sorted(population, key=_risk_key)
    else:
        ordered = sorted(population, key=lambda item: str(item["candidate_id"]))
    selected = [str(item["candidate_id"]) for item in ordered[:sample_size]]
    reason_basis: dict[str, str] = {}
    for candidate_id in selected:
        candidate = _candidate_rows(record)[candidate_id]
        reason_basis[candidate_id] = (
            f"{strategy} sample; severity={_severity(candidate)}; "
            f"technical_verdict={_verdict(candidate)}; confidence={_confidence(candidate):.3f}"
        )

    ledger["quality_control_sampling"] = {
        "sampling_strategy": strategy,
        "sampling_version": QC_SAMPLING_VERSION,
        "population_candidate_ids": population_ids,
        "population_size": len(population_ids),
        "sample_size": len(selected),
        "selected_candidate_ids": selected,
        "risk_reason_basis": reason_basis,
        "configured_by": reviewer_id,
        "configured_by_role": reviewer_role,
        "configured_at": _utc_now(),
        "human_action_required_for_disposition": True,
        "sampling_does_not_approve_unsampled_candidates": True,
    }
    _append_audit_event(
        ledger,
        action="configure_qc_sampling",
        reviewer_id=reviewer_id,
        reviewer_role=reviewer_role,
        detail={
            "sampling_strategy": strategy,
            "sampling_version": QC_SAMPLING_VERSION,
            "population_size": len(population_ids),
            "sample_size": len(selected),
            "selected_candidate_ids": selected,
        },
    )
    return ledger


def _record_additional_qc(
    ledger: dict[str, Any],
    *,
    candidate_id: str,
    result: str,
    rationale: str,
    reviewer_id: str,
    reviewer_role: str,
) -> dict[str, Any]:
    dispositions = ledger.get("candidate_dispositions") if isinstance(ledger.get("candidate_dispositions"), Mapping) else {}
    disposition = dispositions.get(candidate_id) if isinstance(dispositions, Mapping) else None
    if not isinstance(disposition, Mapping):
        raise ValueError("quality_control_requires_completed_human_disposition")
    if str(disposition.get("reviewer_id") or "").strip() == reviewer_id:
        raise ValueError("quality_control_requires_independent_reviewer")
    normalized_result = str(result or "").strip()
    normalized_rationale = str(rationale or "").strip()
    if not normalized_result:
        raise ValueError("quality_control_result_required")
    if not normalized_rationale:
        raise ValueError("quality_control_rationale_required")
    qc = deepcopy(dict(ledger.get("quality_control_results") or {}))
    qc[candidate_id] = {
        "candidate_id": candidate_id,
        "result": normalized_result,
        "rationale": normalized_rationale,
        "reviewer_id": reviewer_id,
        "reviewer_role": reviewer_role,
        "reviewer_authorized": True,
        "reviewed_at": _utc_now(),
        "independent_of_disposition_reviewer": True,
    }
    ledger["quality_control_results"] = qc
    _append_audit_event(
        ledger,
        action="quality_control",
        reviewer_id=reviewer_id,
        reviewer_role=reviewer_role,
        detail={"candidate_id": candidate_id, "result": normalized_result},
    )
    return ledger


def apply_review_work_action(
    record: Mapping[str, Any],
    *,
    action: str,
    payload: Mapping[str, Any] | None,
    reviewer_id: str,
    reviewer_role: str,
    reviewer_authorized: bool,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    actor_id, actor_role = _assert_actor(
        reviewer_id=reviewer_id,
        reviewer_role=reviewer_role,
        reviewer_authorized=reviewer_authorized,
    )
    prepared_record = _record_with_prepared_ledger(record)
    ledger = deepcopy(dict(prepared_record["review_work_ledger"]))
    _assert_revision(ledger, expected_revision)
    normalized_action = str(action or "").strip().casefold()
    data = payload if isinstance(payload, Mapping) else {}

    if normalized_action == "configure_qc_sampling":
        return _configure_sampling(
            prepared_record,
            ledger,
            payload=data,
            reviewer_id=actor_id,
            reviewer_role=actor_role,
        )

    if normalized_action == "quality_control":
        candidate_id = str(data.get("candidate_id") or "").strip()
        if candidate_id in _configured_selected_ids(ledger) and candidate_id not in {
            str(value) for value in ledger.get("quality_control_required_candidate_ids") or []
        }:
            if not candidate_id:
                raise ValueError("quality_control_candidate_id_required")
            return _record_additional_qc(
                ledger,
                candidate_id=candidate_id,
                result=str(data.get("result") or ""),
                rationale=str(data.get("rationale") or data.get("reason") or ""),
                reviewer_id=actor_id,
                reviewer_role=actor_role,
            )

    updated = legacy.apply_review_work_action(
        prepared_record,
        action=action,
        payload=data,
        reviewer_id=actor_id,
        reviewer_role=actor_role,
        reviewer_authorized=True,
        expected_revision=expected_revision,
    )
    updated["artifact_schema"] = VERSION
    updated["review_source_sha256"] = _source_fingerprint(record)
    updated["scope_binding"] = _scope_binding(record)
    if not isinstance(updated.get("quality_control_sampling"), Mapping):
        updated["quality_control_sampling"] = _default_sampling_configuration(record, updated)
    updated["state_hash"] = _ledger_hash(updated)
    return updated


def _primary_queue(candidate: Mapping[str, Any], disposition: Mapping[str, Any] | None) -> str:
    if isinstance(disposition, Mapping):
        return "human_disposition_completed"
    if _is_material(candidate):
        return "critical_material"
    if _needs_individual_attention(candidate):
        return "human_technical_review"
    lineage = _lineage(candidate)
    lineage_status = str(
        candidate.get("lineage_status") or lineage.get("status") or lineage.get("lineage_status") or ""
    ).strip().casefold()
    if lineage_status in {"stable", "carried", "carried_forward", "unchanged"} or _evidence_change(candidate) == "unchanged":
        return "stable_carry_forward"
    return "new_automated_triage_complete"


def review_work_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    prepared_record = _record_with_prepared_ledger(record)
    ledger = deepcopy(dict(prepared_record["review_work_ledger"]))
    base = legacy.review_work_projection(prepared_record)
    rows = _candidate_rows(record)
    dispositions = ledger.get("candidate_dispositions") if isinstance(ledger.get("candidate_dispositions"), Mapping) else {}
    effective_qc = _effective_qc_ids(ledger)
    qc_results = ledger.get("quality_control_results") if isinstance(ledger.get("quality_control_results"), Mapping) else {}
    configured_qc = set(_configured_selected_ids(ledger))
    legacy_qc = {str(value) for value in ledger.get("quality_control_required_candidate_ids") or []}

    clusters = base.get("clusters") if isinstance(base.get("clusters"), list) else []
    grouped_ids: set[str] = set()
    for cluster in clusters:
        if not isinstance(cluster, Mapping):
            continue
        for candidate_id in cluster.get("candidate_ids") or []:
            grouped_ids.add(str(candidate_id))

    candidate_projection: list[dict[str, Any]] = []
    queue_counts = {
        "critical_material": 0,
        "human_technical_review": 0,
        "new_automated_triage_complete": 0,
        "stable_carry_forward": 0,
        "quality_control_sample": len(effective_qc),
        "human_disposition_completed": 0,
    }
    for candidate_id, candidate in sorted(rows.items()):
        disposition = dispositions.get(candidate_id) if isinstance(dispositions, Mapping) else None
        queue = _primary_queue(candidate, disposition if isinstance(disposition, Mapping) else None)
        queue_counts[queue] += 1
        enriched = deepcopy(candidate)
        enriched.update(
            {
                "candidate_id": candidate_id,
                "primary_review_queue": queue,
                "quality_control_sample": candidate_id in set(effective_qc),
                "quality_control_source": (
                    "configured" if candidate_id in configured_qc else "baseline_cluster_guardrail" if candidate_id in legacy_qc else ""
                ),
                "human_disposition": deepcopy(disposition) if isinstance(disposition, Mapping) else None,
                "human_disposition_state": "completed" if isinstance(disposition, Mapping) else "pending",
                "individual_attention_required": _needs_individual_attention(candidate),
                "grouped_review_eligible": candidate_id in grouped_ids and not _needs_individual_attention(candidate),
                "technical_triage_verdict": _verdict(candidate),
                "technical_triage_confidence": _confidence(candidate),
                "evidence_change_state": _evidence_change(candidate),
            }
        )
        candidate_projection.append(enriched)

    pending_ids = sorted(candidate_id for candidate_id in rows if candidate_id not in dispositions)
    missing_qc = sorted(candidate_id for candidate_id in effective_qc if candidate_id not in qc_results)
    base_summary = deepcopy(dict(base.get("summary") or {}))
    unresolved_evidence = list(base_summary.get("unresolved_evidence_request_ids") or [])
    unresolved_escalations = list(base_summary.get("unresolved_high_impact_candidate_ids") or [])
    review_ready = not (pending_ids or missing_qc or unresolved_evidence or unresolved_escalations)

    pending_grouped = {
        candidate_id
        for candidate_id in grouped_ids
        if candidate_id in rows and candidate_id not in dispositions and not _needs_individual_attention(rows[candidate_id])
    }
    clusters_remaining = 0
    for cluster in clusters:
        if not isinstance(cluster, Mapping):
            continue
        if any(str(candidate_id) in pending_grouped for candidate_id in cluster.get("candidate_ids") or []):
            clusters_remaining += 1

    sessions = ledger.get("review_sessions") if isinstance(ledger.get("review_sessions"), list) else []
    completed_seconds = sum(
        int(session.get("duration_seconds") or 0)
        for session in sessions
        if isinstance(session, Mapping) and session.get("ended_at")
    )
    workload = {
        "individual_attention_count": sum(
            1
            for candidate_id, candidate in rows.items()
            if candidate_id not in dispositions and _needs_individual_attention(candidate)
        ),
        "grouped_review_eligible_count": len(pending_grouped),
        "quality_control_sample_size": len(effective_qc),
        "human_dispositions_pending": len(pending_ids),
        "human_dispositions_completed": len(rows) - len(pending_ids),
        "clusters_remaining": clusters_remaining,
        "reviewer_interactions": len(ledger.get("audit_events") or []),
        "measured_specialist_seconds": completed_seconds,
        "measured_specialist_hours": round(completed_seconds / 3600.0, 3),
        "four_hour_engineering_target_seconds": legacy.FOUR_HOUR_TARGET_SECONDS,
        "four_hour_target_is_safety_gate": False,
    }

    summary = {
        **base_summary,
        "review_ready": review_ready,
        "human_dispositions_pending": len(pending_ids),
        "human_dispositions_completed": len(rows) - len(pending_ids),
        "missing_quality_control_candidate_ids": missing_qc,
        "quality_control_sample_size": len(effective_qc),
        "queue_counts": queue_counts,
        "workload_metrics": workload,
        "review_source_sha256": str(ledger.get("review_source_sha256") or ""),
        "scope_binding": deepcopy(ledger.get("scope_binding") or {}),
    }
    return {
        **base,
        "artifact_schema": VERSION,
        "summary": summary,
        "candidates": candidate_projection,
        "quality_control_sampling": deepcopy(ledger.get("quality_control_sampling") or {}),
        "quality_control_required_candidate_ids": effective_qc,
        "workload_metrics": workload,
    }


def assert_ready_for_approval(record: Mapping[str, Any]) -> dict[str, Any]:
    projection = review_work_projection(record)
    summary = projection["summary"]
    if not summary.get("review_ready"):
        blockers: list[str] = []
        if summary.get("human_dispositions_pending"):
            blockers.append("human_dispositions_pending")
        if summary.get("missing_quality_control_candidate_ids"):
            blockers.append("quality_control_pending")
        if summary.get("unresolved_evidence_request_ids"):
            blockers.append("evidence_requests_unresolved")
        if summary.get("unresolved_high_impact_candidate_ids"):
            blockers.append("high_impact_escalations_unresolved")
        raise ValueError("phase2_review_not_ready_for_approval:" + ",".join(blockers))
    return summary


canonical_candidate_register = legacy.canonical_candidate_register
new_review_work_ledger = legacy.new_review_work_ledger
ledger_for_record = _prepare_ledger


__all__ = [
    "VERSION",
    "QC_SAMPLING_VERSION",
    "apply_review_work_action",
    "assert_ready_for_approval",
    "canonical_candidate_register",
    "ledger_for_record",
    "new_review_work_ledger",
    "review_work_projection",
]
