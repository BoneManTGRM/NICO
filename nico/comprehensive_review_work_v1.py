from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from nico.comprehensive_client_delivery_contract_v1 import human_reviewer_identity

VERSION = "nico.comprehensive_review_work.v1"
LEDGER_SCHEMA = "nico.comprehensive_review_work_ledger.v1"
PROJECTION_SCHEMA = "nico.comprehensive_review_work_projection.v1"
_FINAL_REPORT_STAGE_ID = "final_comprehensive_report_generation"
_ALLOWED_DISPOSITIONS = {
    "confirmed",
    "false_positive",
    "not_applicable",
    "accepted_risk",
    "needs_more_evidence",
}
_QC_OUTCOMES = {"agree", "disagree"}
_HIGH_SEVERITIES = {"critical", "high"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now(value: datetime | None = None) -> datetime:
    return (value or datetime.now(UTC)).astimezone(UTC)


def _iso(value: datetime | None = None) -> str:
    return _now(value).isoformat()


def _canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _identity(record: Mapping[str, Any]) -> dict[str, str]:
    raw = record.get("identity")
    if not isinstance(raw, Mapping):
        raise ValueError("review_work_identity_missing")
    result = {
        field: _text(raw.get(field))
        for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id")
    }
    if not all(result.values()):
        raise ValueError("review_work_identity_incomplete")
    return result


def canonical_candidate_register(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the one terminal canonical scanner register for human review.

    This intentionally reads the same final Comprehensive report JSON used by the
    reviewer queue. It never creates another scanner/candidate source of truth.
    """

    identity = _identity(record)
    stage_results = record.get("stage_results")
    stage_results = stage_results if isinstance(stage_results, Mapping) else {}
    stage = stage_results.get(_FINAL_REPORT_STAGE_ID)
    package = stage.get("report_package") if isinstance(stage, Mapping) else None
    canonical = package.get("json") if isinstance(package, Mapping) else None
    if not isinstance(canonical, Mapping):
        raise ValueError("review_work_canonical_register_unavailable")
    canonical_identity = canonical.get("identity")
    if not isinstance(canonical_identity, Mapping):
        raise ValueError("review_work_canonical_register_unavailable")
    for field, expected in identity.items():
        if _text(canonical_identity.get(field)) != expected:
            raise ValueError(f"review_work_identity_mismatch:{field}")
    assessment = canonical.get("assessment")
    register = (
        assessment.get("canonical_scanner_finding_register")
        if isinstance(assessment, Mapping)
        else None
    )
    if not isinstance(register, Mapping):
        raise ValueError("review_work_canonical_register_unavailable")
    findings = register.get("findings")
    if not isinstance(findings, list):
        raise ValueError("review_work_canonical_findings_missing")
    candidates = [dict(item) for item in findings if isinstance(item, Mapping)]
    if len(candidates) != len(findings):
        raise ValueError("review_work_canonical_findings_malformed")
    ids = [_text(item.get("candidate_id")) for item in candidates]
    if any(not item for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("review_work_candidate_identity_invalid")
    try:
        declared = int(register.get("candidate_record_count"))
    except (TypeError, ValueError):
        declared = -1
    if declared != len(candidates):
        raise ValueError("review_work_candidate_count_mismatch")
    return deepcopy(dict(register))


def _catalog(register: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    candidates = {
        _text(item.get("candidate_id")): dict(item)
        for item in register.get("findings") or []
        if isinstance(item, Mapping)
    }
    clusters: dict[str, dict[str, Any]] = {}
    raw_clusters = register.get("review_workload_clusters")
    if isinstance(raw_clusters, list):
        for item in raw_clusters:
            if not isinstance(item, Mapping):
                raise ValueError("review_work_cluster_malformed")
            cluster_id = _text(item.get("cluster_id"))
            if not cluster_id or cluster_id in clusters:
                raise ValueError("review_work_cluster_identity_invalid")
            candidate_ids = [_text(value) for value in item.get("candidate_ids") or []]
            if not candidate_ids or len(set(candidate_ids)) != len(candidate_ids):
                raise ValueError(f"review_work_cluster_membership_invalid:{cluster_id}")
            if any(candidate_id not in candidates for candidate_id in candidate_ids):
                raise ValueError(f"review_work_cluster_unknown_candidate:{cluster_id}")
            clusters[cluster_id] = dict(item)
    if candidates and not clusters:
        raise ValueError("review_work_cluster_metadata_unavailable")
    clustered = [
        candidate_id
        for cluster in clusters.values()
        for candidate_id in [_text(value) for value in cluster.get("candidate_ids") or []]
    ]
    if len(clustered) != len(candidates) or len(set(clustered)) != len(candidates) or set(clustered) != set(candidates):
        raise ValueError("review_work_clusters_do_not_preserve_candidates")
    return candidates, clusters


def _qc_required_ids(clusters: Mapping[str, Mapping[str, Any]]) -> list[str]:
    result: list[str] = []
    for cluster_id in sorted(clusters):
        cluster = clusters[cluster_id]
        if cluster.get("grouped_review_eligible") is not True:
            continue
        candidate_ids = [_text(value) for value in cluster.get("candidate_ids") or []]
        if len(candidate_ids) < 2:
            continue
        representative = _text(cluster.get("representative_candidate_id"))
        if representative not in candidate_ids:
            raise ValueError(f"review_work_qc_representative_invalid:{cluster_id}")
        result.append(representative)
    return result


def _high_impact_ids(candidates: Mapping[str, Mapping[str, Any]]) -> list[str]:
    result: list[str] = []
    for candidate_id, candidate in candidates.items():
        severity = _text(candidate.get("severity")).casefold()
        routing = _text(candidate.get("review_routing_class")).upper()
        if severity in _HIGH_SEVERITIES or routing == "CRITICAL_ATTENTION":
            result.append(candidate_id)
    return sorted(result)


def _empty_ledger(record: Mapping[str, Any], register: Mapping[str, Any]) -> dict[str, Any]:
    identity = _identity(record)
    candidates, clusters = _catalog(register)
    return {
        "artifact_schema": LEDGER_SCHEMA,
        "version": 1,
        **identity,
        "candidate_count": len(candidates),
        "cluster_count": len(clusters),
        "candidate_ids": sorted(candidates),
        "qc_required_candidate_ids": _qc_required_ids(clusters),
        "high_impact_candidate_ids": _high_impact_ids(candidates),
        "reviewer_identities": {},
        "assignments": {},
        "dispositions": {},
        "quality_control": {},
        "evidence_requests": [],
        "stakeholder_evidence": [],
        "review_sessions": [],
        "audit_events": [],
        "empirical_study": {
            "status": "not_yet_measured",
            "completed_at": "",
            "completed_by": "",
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _has_human_review_state(ledger: Mapping[str, Any]) -> bool:
    """Return whether rebuilding a stale machine ledger would discard human work."""

    for field in (
        "reviewer_identities",
        "assignments",
        "dispositions",
        "quality_control",
        "evidence_requests",
        "stakeholder_evidence",
        "review_sessions",
        "audit_events",
    ):
        if ledger.get(field):
            return True
    empirical = ledger.get("empirical_study")
    return bool(
        isinstance(empirical, Mapping)
        and _text(empirical.get("status")) not in {"", "not_yet_measured"}
    )


def ledger_for_record(record: Mapping[str, Any], register: Mapping[str, Any] | None = None) -> dict[str, Any]:
    register = dict(register or canonical_candidate_register(record))
    expected = _empty_ledger(record, register)
    existing = record.get("review_work_ledger")
    if not isinstance(existing, Mapping):
        return expected
    ledger = deepcopy(dict(existing))
    if _text(ledger.get("artifact_schema")) != LEDGER_SCHEMA:
        raise ValueError("review_work_ledger_schema_invalid")
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        if _text(ledger.get(field)) != _text(expected.get(field)):
            raise ValueError(f"review_work_ledger_identity_mismatch:{field}")
    if int(ledger.get("candidate_count") or -1) != expected["candidate_count"]:
        # The final report compiler can legitimately collapse or remove machine-only
        # candidates after a preliminary review ledger has been initialized. Rebuild
        # that untouched ledger against the final canonical register. Once any human
        # review state exists, keep failing closed rather than discarding it.
        if _has_human_review_state(ledger):
            raise ValueError("review_work_ledger_candidate_count_mismatch")
        return expected
    if sorted(_text(value) for value in ledger.get("candidate_ids") or []) != expected["candidate_ids"]:
        raise ValueError("review_work_ledger_candidate_identity_mismatch")
    if sorted(_text(value) for value in ledger.get("qc_required_candidate_ids") or []) != expected["qc_required_candidate_ids"]:
        raise ValueError("review_work_ledger_qc_sample_drift")
    if sorted(_text(value) for value in ledger.get("high_impact_candidate_ids") or []) != expected["high_impact_candidate_ids"]:
        raise ValueError("review_work_ledger_escalation_drift")
    return ledger


def _require_human(payload: Mapping[str, Any]) -> tuple[str, str]:
    if payload.get("review_authorized") is not True or payload.get("authorization_confirmed") is not True:
        raise ValueError("explicit_review_authorization_required")
    return human_reviewer_identity(
        reviewer=_text(payload.get("reviewer")),
        reviewer_role=_text(payload.get("reviewer_role")),
    )


def _append_event(ledger: dict[str, Any], *, action: str, reviewer: str, reviewer_role: str, payload: Mapping[str, Any], now: datetime) -> None:
    events = [dict(item) for item in ledger.get("audit_events") or [] if isinstance(item, Mapping)]
    sequence = len(events) + 1
    previous_hash = _text(events[-1].get("event_sha256")) if events else ""
    event = {
        "sequence": sequence,
        "action": action,
        "reviewer": reviewer,
        "reviewer_role": reviewer_role,
        "recorded_at": _iso(now),
        "previous_event_sha256": previous_hash,
        "payload": deepcopy(dict(payload)),
    }
    event["event_sha256"] = _canonical_hash(event)
    events.append(event)
    ledger["audit_events"] = events


def _reviewer_identity(ledger: dict[str, Any], reviewer: str, reviewer_role: str, now: datetime) -> None:
    identities = dict(ledger.get("reviewer_identities") or {})
    key = reviewer.casefold()
    previous = identities.get(key) if isinstance(identities.get(key), Mapping) else {}
    identities[key] = {
        "reviewer": reviewer,
        "reviewer_role": reviewer_role,
        "first_seen_at": _text(previous.get("first_seen_at")) or _iso(now),
        "last_seen_at": _iso(now),
        "explicit_authorization_confirmed": True,
    }
    ledger["reviewer_identities"] = identities


def _cluster_members(cluster: Mapping[str, Any]) -> list[str]:
    return [_text(value) for value in cluster.get("candidate_ids") or []]


def _disposition_payload(payload: Mapping[str, Any], *, candidate: Mapping[str, Any]) -> dict[str, str]:
    disposition = _text(payload.get("disposition")).casefold()
    if disposition not in _ALLOWED_DISPOSITIONS:
        raise ValueError("review_work_disposition_invalid")
    rationale = _text(payload.get("rationale"))
    if not rationale:
        raise ValueError("review_work_disposition_rationale_required")
    residual_risk = _text(payload.get("residual_risk"))
    residual_risk_owner = _text(payload.get("residual_risk_owner"))
    if disposition in {"confirmed", "accepted_risk"} and (not residual_risk or not residual_risk_owner):
        raise ValueError("review_work_residual_risk_and_owner_required")
    severity = _text(candidate.get("severity")).casefold()
    routing = _text(candidate.get("review_routing_class")).upper()
    high_impact = severity in _HIGH_SEVERITIES or routing == "CRITICAL_ATTENTION"
    escalation_resolution = _text(payload.get("escalation_resolution"))
    escalation_owner = _text(payload.get("escalation_owner"))
    if high_impact and (not escalation_resolution or not escalation_owner):
        raise ValueError("review_work_high_impact_escalation_resolution_required")
    return {
        "disposition": disposition,
        "rationale": rationale,
        "residual_risk": residual_risk,
        "residual_risk_owner": residual_risk_owner,
        "escalation_resolution": escalation_resolution,
        "escalation_owner": escalation_owner,
    }


def _next_identifier(ledger: Mapping[str, Any], prefix: str, now: datetime, material: str) -> str:
    sequence = len(ledger.get("audit_events") or []) + 1
    digest = hashlib.sha256(
        f"{ledger.get('run_id')}|{prefix}|{sequence}|{_iso(now)}|{material}".encode("utf-8")
    ).hexdigest()[:20]
    return f"{prefix}_{digest}"


def apply_review_work_action(
    record: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    if str(record.get("status") or "").casefold() != "review_required" or record.get("terminal") is not True:
        raise ValueError("review_work_requires_terminal_review_required_run")
    if record.get("human_review_completed") is True or record.get("client_delivery_allowed") is True:
        raise ValueError("review_work_requires_preapproval_run")
    reviewer, reviewer_role = _require_human(payload)
    action = _text(payload.get("action")).casefold()
    if not action:
        raise ValueError("review_work_action_required")
    timestamp = _now(now)
    register = canonical_candidate_register(record)
    candidates, clusters = _catalog(register)
    ledger = ledger_for_record(record, register)
    _reviewer_identity(ledger, reviewer, reviewer_role, timestamp)

    if action == "assign":
        target_id = _text(payload.get("target_id"))
        if target_id not in candidates and target_id not in clusters:
            raise ValueError("review_work_assignment_target_invalid")
        assignee = _text(payload.get("assignee"))
        specialist_role = _text(payload.get("specialist_role"))
        if not assignee or not specialist_role:
            raise ValueError("review_work_assignee_and_specialist_role_required")
        assignments = dict(ledger.get("assignments") or {})
        assignments[target_id] = {
            "target_id": target_id,
            "target_type": "cluster" if target_id in clusters else "candidate",
            "assignee": assignee,
            "specialist_role": specialist_role,
            "assigned_by": reviewer,
            "assigned_at": _iso(timestamp),
        }
        ledger["assignments"] = assignments

    elif action in {"disposition_candidate", "disposition_group"}:
        target_id = _text(payload.get("candidate_id") if action == "disposition_candidate" else payload.get("cluster_id"))
        if action == "disposition_candidate":
            if target_id not in candidates:
                raise ValueError("review_work_candidate_id_invalid")
            target_candidates = [target_id]
            cluster_id = _text(candidates[target_id].get("cluster_id"))
        else:
            if target_id not in clusters:
                raise ValueError("review_work_cluster_id_invalid")
            cluster = clusters[target_id]
            if cluster.get("grouped_review_eligible") is not True or cluster.get("homogeneous_evidence") is not True or cluster.get("homogeneous_verdict") is not True:
                raise ValueError("review_work_group_disposition_requires_homogeneous_group")
            target_candidates = _cluster_members(cluster)
            cluster_id = target_id
        dispositions = dict(ledger.get("dispositions") or {})
        group_action_id = _next_identifier(ledger, "groupreview", timestamp, target_id) if action == "disposition_group" else ""
        for candidate_id in target_candidates:
            candidate = candidates[candidate_id]
            disposition = _disposition_payload(payload, candidate=candidate)
            dispositions[candidate_id] = {
                "candidate_id": candidate_id,
                "cluster_id": cluster_id,
                "source": "group" if action == "disposition_group" else "candidate",
                "group_action_id": group_action_id,
                **disposition,
                "reviewer": reviewer,
                "reviewer_role": reviewer_role,
                "decided_at": _iso(timestamp),
                "human_decision": True,
            }
        ledger["dispositions"] = dispositions

    elif action == "quality_control":
        candidate_id = _text(payload.get("candidate_id"))
        required = set(_text(value) for value in ledger.get("qc_required_candidate_ids") or [])
        if candidate_id not in required or candidate_id not in candidates:
            raise ValueError("review_work_qc_candidate_not_required")
        disposition = (ledger.get("dispositions") or {}).get(candidate_id)
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

    elif action == "request_evidence":
        request_text = _text(payload.get("request_text"))
        owner = _text(payload.get("owner"))
        candidate_id = _text(payload.get("candidate_id"))
        if candidate_id and candidate_id not in candidates:
            raise ValueError("review_work_evidence_request_candidate_invalid")
        if not request_text or not owner:
            raise ValueError("review_work_evidence_request_text_and_owner_required")
        request_id = _next_identifier(ledger, "evidence_request", timestamp, candidate_id + request_text)
        requests = [dict(item) for item in ledger.get("evidence_requests") or [] if isinstance(item, Mapping)]
        requests.append({
            "request_id": request_id,
            "candidate_id": candidate_id,
            "request_text": request_text,
            "owner": owner,
            "status": "open",
            "requested_by": reviewer,
            "requested_at": _iso(timestamp),
            "resolution_note": "",
            "evidence_references": [],
        })
        ledger["evidence_requests"] = requests

    elif action == "resolve_evidence_request":
        request_id = _text(payload.get("request_id"))
        resolution_note = _text(payload.get("resolution_note"))
        evidence_references = [_text(value) for value in payload.get("evidence_references") or [] if _text(value)]
        if not request_id or not resolution_note or not evidence_references:
            raise ValueError("review_work_evidence_resolution_note_and_references_required")
        found = False
        requests: list[dict[str, Any]] = []
        for item in ledger.get("evidence_requests") or []:
            if not isinstance(item, Mapping):
                continue
            entry = dict(item)
            if _text(entry.get("request_id")) == request_id:
                found = True
                if _text(entry.get("status")) != "open":
                    raise ValueError("review_work_evidence_request_already_resolved")
                entry.update({
                    "status": "resolved",
                    "resolution_note": resolution_note,
                    "evidence_references": evidence_references,
                    "resolved_by": reviewer,
                    "resolved_at": _iso(timestamp),
                })
            requests.append(entry)
        if not found:
            raise ValueError("review_work_evidence_request_not_found")
        ledger["evidence_requests"] = requests

    elif action == "stakeholder_evidence":
        statement = _text(payload.get("statement"))
        source_role = _text(payload.get("source_role"))
        evidence_reference = _text(payload.get("evidence_reference"))
        if not statement or not source_role:
            raise ValueError("review_work_stakeholder_statement_and_source_role_required")
        entries = [dict(item) for item in ledger.get("stakeholder_evidence") or [] if isinstance(item, Mapping)]
        entries.append({
            "evidence_id": _next_identifier(ledger, "stakeholder", timestamp, statement),
            "statement": statement,
            "source_role": source_role,
            "evidence_reference": evidence_reference,
            "recorded_by": reviewer,
            "recorded_at": _iso(timestamp),
            "human_authored": True,
            "technical_score_unchanged": True,
        })
        ledger["stakeholder_evidence"] = entries

    elif action == "start_session":
        sessions = [dict(item) for item in ledger.get("review_sessions") or [] if isinstance(item, Mapping)]
        if any(_text(item.get("status")) == "running" and _text(item.get("reviewer")).casefold() == reviewer.casefold() for item in sessions):
            raise ValueError("review_work_session_already_running")
        sessions.append({
            "session_id": _next_identifier(ledger, "review_session", timestamp, reviewer),
            "reviewer": reviewer,
            "reviewer_role": reviewer_role,
            "status": "running",
            "started_at": _iso(timestamp),
            "ended_at": "",
            "duration_seconds": None,
            "server_measured": True,
        })
        ledger["review_sessions"] = sessions

    elif action == "stop_session":
        sessions = [dict(item) for item in ledger.get("review_sessions") or [] if isinstance(item, Mapping)]
        running_index = next((index for index in range(len(sessions) - 1, -1, -1) if _text(sessions[index].get("status")) == "running" and _text(sessions[index].get("reviewer")).casefold() == reviewer.casefold()), None)
        if running_index is None:
            raise ValueError("review_work_running_session_not_found")
        started = datetime.fromisoformat(_text(sessions[running_index].get("started_at")))
        duration = max(0, int((timestamp - started.astimezone(UTC)).total_seconds()))
        sessions[running_index].update({
            "status": "completed",
            "ended_at": _iso(timestamp),
            "duration_seconds": duration,
        })
        ledger["review_sessions"] = sessions

    elif action == "complete_empirical_study":
        projection = review_work_projection(record, ledger=ledger, register=register)
        if projection["ready_for_final_approval"] is not True:
            raise ValueError("review_work_empirical_study_requires_completed_candidate_review")
        completed_sessions = [item for item in ledger.get("review_sessions") or [] if isinstance(item, Mapping) and _text(item.get("status")) == "completed"]
        if not completed_sessions:
            raise ValueError("review_work_empirical_study_requires_measured_session")
        empirical = dict(ledger.get("empirical_study") or {})
        empirical.update({
            "status": "completed",
            "completed_at": _iso(timestamp),
            "completed_by": reviewer,
        })
        ledger["empirical_study"] = empirical

    else:
        raise ValueError(f"review_work_action_unsupported:{action}")

    _append_event(
        ledger,
        action=action,
        reviewer=reviewer,
        reviewer_role=reviewer_role,
        payload={key: value for key, value in payload.items() if key not in {"operator_token"}},
        now=timestamp,
    )
    ledger["updated_at"] = _iso(timestamp)
    ledger["human_review_required"] = True
    ledger["client_delivery_allowed"] = False
    return ledger


def review_work_projection(
    record: Mapping[str, Any],
    *,
    ledger: Mapping[str, Any] | None = None,
    register: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    register_value = dict(register or canonical_candidate_register(record))
    candidates, clusters = _catalog(register_value)
    ledger_value = deepcopy(dict(ledger or ledger_for_record(record, register_value)))
    dispositions = ledger_value.get("dispositions") if isinstance(ledger_value.get("dispositions"), Mapping) else {}
    qc = ledger_value.get("quality_control") if isinstance(ledger_value.get("quality_control"), Mapping) else {}
    required_qc = [_text(value) for value in ledger_value.get("qc_required_candidate_ids") or []]
    high_impact = [_text(value) for value in ledger_value.get("high_impact_candidate_ids") or []]
    unresolved_high = [
        candidate_id
        for candidate_id in high_impact
        if not isinstance(dispositions.get(candidate_id), Mapping)
        or not _text(dispositions[candidate_id].get("escalation_resolution"))
        or not _text(dispositions[candidate_id].get("escalation_owner"))
    ]
    open_requests = [
        dict(item)
        for item in ledger_value.get("evidence_requests") or []
        if isinstance(item, Mapping) and _text(item.get("status")) == "open"
    ]
    qc_complete_ids = [
        candidate_id
        for candidate_id in required_qc
        if isinstance(qc.get(candidate_id), Mapping)
        and qc[candidate_id].get("independent_reviewer_verified") is True
    ]
    completed_dispositions = [candidate_id for candidate_id in candidates if isinstance(dispositions.get(candidate_id), Mapping)]
    ready = (
        len(completed_dispositions) == len(candidates)
        and len(qc_complete_ids) == len(required_qc)
        and not open_requests
        and not unresolved_high
    )
    completed_sessions = [
        dict(item)
        for item in ledger_value.get("review_sessions") or []
        if isinstance(item, Mapping) and _text(item.get("status")) == "completed"
    ]
    total_seconds = sum(max(0, int(item.get("duration_seconds") or 0)) for item in completed_sessions)
    empirical = ledger_value.get("empirical_study") if isinstance(ledger_value.get("empirical_study"), Mapping) else {}
    study_completed = _text(empirical.get("status")) == "completed"
    target_verified = bool(study_completed and completed_sessions and total_seconds <= 4 * 60 * 60)
    measurement_status = (
        "verified_within_four_hours"
        if target_verified
        else "measured_over_four_hours"
        if study_completed and completed_sessions
        else "not_yet_measured"
    )
    return {
        "artifact_schema": PROJECTION_SCHEMA,
        "service_id": "comprehensive",
        "run_id": _text(ledger_value.get("run_id")),
        "repository": _text(ledger_value.get("repository")),
        "commit_sha": _text(ledger_value.get("commit_sha")),
        "evidence_ledger_id": _text(ledger_value.get("evidence_ledger_id")),
        "candidate_count": len(candidates),
        "cluster_count": len(clusters),
        "dispositioned_candidate_count": len(completed_dispositions),
        "remaining_candidate_count": len(candidates) - len(completed_dispositions),
        "quality_control_required_count": len(required_qc),
        "quality_control_completed_count": len(qc_complete_ids),
        "quality_control_required_candidate_ids": required_qc,
        "high_impact_candidate_ids": high_impact,
        "unresolved_high_impact_candidate_ids": unresolved_high,
        "open_evidence_request_count": len(open_requests),
        "open_evidence_requests": open_requests,
        "ready_for_final_approval": ready,
        "reviewer_identity_count": len(ledger_value.get("reviewer_identities") or {}),
        "assignment_count": len(ledger_value.get("assignments") or {}),
        "stakeholder_evidence_count": len(ledger_value.get("stakeholder_evidence") or []),
        "audit_event_count": len(ledger_value.get("audit_events") or []),
        "empirical_measurement": {
            "status": measurement_status,
            "completed_session_count": len(completed_sessions),
            "combined_specialist_seconds": total_seconds,
            "combined_specialist_hours": round(total_seconds / 3600, 3),
            "four_hour_target_seconds": 4 * 60 * 60,
            "four_combined_specialist_hours_empirically_proven": target_verified,
            "study_completed": study_completed,
            "completed_at": _text(empirical.get("completed_at")),
            "completed_by": _text(empirical.get("completed_by")),
            "server_measured_only": True,
        },
        "ledger": ledger_value,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def assert_ready_for_approval(record: Mapping[str, Any]) -> dict[str, Any]:
    projection = review_work_projection(record)
    if projection.get("ready_for_final_approval") is not True:
        blockers = {
            "remaining_candidate_count": projection.get("remaining_candidate_count"),
            "quality_control_remaining_count": int(projection.get("quality_control_required_count") or 0) - int(projection.get("quality_control_completed_count") or 0),
            "open_evidence_request_count": projection.get("open_evidence_request_count"),
            "unresolved_high_impact_candidate_ids": projection.get("unresolved_high_impact_candidate_ids"),
        }
        raise ValueError("review_work_not_ready_for_approval:" + json.dumps(blockers, sort_keys=True, separators=(",", ":")))
    return projection


__all__ = [
    "LEDGER_SCHEMA",
    "PROJECTION_SCHEMA",
    "VERSION",
    "apply_review_work_action",
    "assert_ready_for_approval",
    "canonical_candidate_register",
    "ledger_for_record",
    "review_work_projection",
]
