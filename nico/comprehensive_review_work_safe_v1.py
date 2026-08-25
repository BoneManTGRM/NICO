from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from nico import comprehensive_review_work_v2 as phase2

VERSION = "nico.comprehensive_review_work_safe.v2"
_HUMAN_ROUTES = {"CRITICAL_ATTENTION", "HUMAN_TECHNICAL_REVIEW"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _verdict(candidate: Mapping[str, Any]) -> str:
    triage = candidate.get("technical_triage")
    if not isinstance(triage, Mapping):
        triage = {}
    return _text(
        triage.get("verdict")
        or candidate.get("technical_triage_verdict")
        or candidate.get("triage_verdict")
        or candidate.get("verdict")
    ).casefold()


def _route(candidate: Mapping[str, Any]) -> str:
    return _text(candidate.get("review_routing_class")).upper()


def _raw_candidates(record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    register = phase2.canonical_candidate_register(record)
    findings = register.get("findings") if isinstance(register, Mapping) else []
    return {
        _text(item.get("candidate_id")): deepcopy(dict(item))
        for item in findings or []
        if isinstance(item, Mapping) and _text(item.get("candidate_id"))
    }


def _raw_grouped(candidate: Mapping[str, Any]) -> bool:
    return bool(
        candidate.get("grouped_review_eligible") is True
        and candidate.get("homogeneous_evidence") is not False
        and candidate.get("homogeneous_verdict") is not False
    )


def _required_human_candidate_ids(
    record: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> set[str]:
    raw = _raw_candidates(record)
    required: set[str] = set()
    for candidate_id, candidate in raw.items():
        if (
            _route(candidate) in _HUMAN_ROUTES
            or candidate.get("review_requires_individual_attention") is True
            or _verdict(candidate) in {"needs_review", "confirmed"}
        ):
            required.add(candidate_id)

    required.update(
        _text(value)
        for value in projection.get("quality_control_required_candidate_ids") or []
        if _text(value)
    )
    ledger = projection.get("ledger")
    if isinstance(ledger, Mapping):
        required.update(
            _text(value)
            for value in ledger.get("high_impact_candidate_ids") or []
            if _text(value)
        )
    return required


def review_work_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    """Project Phase 2 as an exception-first human-review queue.

    Automated not_actionable candidates remain part of the immutable candidate register,
    but they do not require one-by-one human dispositions unless selected for mandatory
    QC or elevated by a high-impact rule. Human-routed needs_review/confirmed candidates
    remain mandatory. Phase 1 homogeneous human-review clusters remain group-eligible.
    """

    base = deepcopy(phase2.review_work_projection(record))
    raw = _raw_candidates(record)
    ledger = base.get("ledger") if isinstance(base.get("ledger"), Mapping) else {}
    dispositions = ledger.get("dispositions") if isinstance(ledger.get("dispositions"), Mapping) else {}
    disposition_ids = {_text(value) for value in dispositions if _text(value)}
    high_impact = {
        _text(value) for value in ledger.get("high_impact_candidate_ids") or [] if _text(value)
    }
    required_ids = _required_human_candidate_ids(record, base)
    pending_ids = sorted(required_ids - disposition_ids)

    candidate_rows: list[dict[str, Any]] = []
    row_by_id: dict[str, dict[str, Any]] = {}
    for existing in base.get("candidates") or []:
        if not isinstance(existing, Mapping):
            continue
        row = deepcopy(dict(existing))
        candidate_id = _text(row.get("candidate_id"))
        source = raw.get(candidate_id, row)
        route = _route(source)
        grouped = bool(
            _raw_grouped(source)
            and route == "HUMAN_TECHNICAL_REVIEW"
            and candidate_id not in high_impact
        )
        individual = bool(
            candidate_id in required_ids
            and not grouped
            and candidate_id
            not in set(base.get("quality_control_required_candidate_ids") or [])
        )
        if candidate_id in high_impact or route == "CRITICAL_ATTENTION":
            grouped = False
            individual = True
        row["grouped_review_eligible"] = grouped
        row["individual_attention_required"] = individual
        row["human_disposition_required"] = candidate_id in required_ids
        row["human_disposition_state"] = (
            "completed"
            if candidate_id in disposition_ids
            else "pending"
            if candidate_id in required_ids
            else "automated_triage_complete"
        )
        candidate_rows.append(row)
        row_by_id[candidate_id] = row

    clusters: list[dict[str, Any]] = []
    pending_grouped_ids: set[str] = set()
    for raw_cluster in base.get("clusters") or []:
        if not isinstance(raw_cluster, Mapping):
            continue
        cluster = deepcopy(dict(raw_cluster))
        member_ids = [
            _text(value) for value in cluster.get("candidate_ids") or [] if _text(value)
        ]
        grouped_human = bool(
            cluster.get("grouped_human_review_cluster") is True
            and cluster.get("homogeneous_evidence") is not False
            and cluster.get("homogeneous_verdict") is not False
            and member_ids
            and all(
                row_by_id.get(candidate_id, {}).get("grouped_review_eligible") is True
                for candidate_id in member_ids
                if candidate_id in required_ids
            )
        )
        cluster["grouped_review_eligible"] = grouped_human
        if grouped_human:
            pending_grouped_ids.update(
                candidate_id for candidate_id in member_ids if candidate_id in pending_ids
            )
        clusters.append(cluster)

    missing_qc = list(base.get("missing_quality_control_candidate_ids") or [])
    open_requests = list(base.get("open_evidence_requests") or [])
    unresolved_high = list(base.get("unresolved_high_impact_candidate_ids") or [])
    ready = not (pending_ids or missing_qc or open_requests or unresolved_high)
    clusters_remaining = sum(
        1
        for cluster in clusters
        if cluster.get("grouped_review_eligible") is True
        and any(
            _text(candidate_id) in pending_grouped_ids
            for candidate_id in cluster.get("candidate_ids") or []
        )
    )
    required_completed = len(required_ids) - len(pending_ids)
    actual_dispositions = len(disposition_ids & set(raw))

    workload = deepcopy(dict(base.get("workload_metrics") or {}))
    workload.update(
        {
            "individual_attention_count": sum(
                1
                for candidate_id in pending_ids
                if row_by_id.get(candidate_id, {}).get("individual_attention_required") is True
            ),
            "grouped_review_eligible_count": len(pending_grouped_ids),
            "human_dispositions_required": len(required_ids),
            "human_dispositions_pending": len(pending_ids),
            "human_dispositions_completed": required_completed,
            "actual_human_disposition_record_count": actual_dispositions,
            "clusters_remaining": clusters_remaining,
            "exception_first_review": True,
            "automated_not_actionable_candidates_require_individual_disposition": False,
        }
    )

    base.update(
        {
            "artifact_schema": "nico.comprehensive_review_work_projection.v2.exception_first",
            "candidates": candidate_rows,
            "clusters": clusters,
            "required_human_disposition_candidate_ids": sorted(required_ids),
            "required_human_disposition_count": len(required_ids),
            "required_human_disposition_completed_count": required_completed,
            "dispositioned_candidate_count": actual_dispositions,
            "remaining_candidate_count": len(pending_ids),
            "ready_for_final_approval": ready,
            "workload_metrics": workload,
            "exception_first_review": True,
        }
    )
    return base


def assert_ready_for_approval(record: Mapping[str, Any]) -> dict[str, Any]:
    projection = review_work_projection(record)
    if projection.get("ready_for_final_approval") is not True:
        blockers = {
            "remaining_candidate_count": projection.get("remaining_candidate_count"),
            "quality_control_remaining_count": int(
                projection.get("quality_control_required_count") or 0
            )
            - int(projection.get("quality_control_completed_count") or 0),
            "open_evidence_request_count": projection.get("open_evidence_request_count"),
            "unresolved_high_impact_candidate_ids": projection.get(
                "unresolved_high_impact_candidate_ids"
            ),
        }
        raise ValueError(
            "review_work_not_ready_for_approval:"
            + json.dumps(blockers, sort_keys=True, separators=(",", ":"))
        )
    return projection


def _validate_group_disposition(record: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
    cluster_id = _text(payload.get("cluster_id"))
    if not cluster_id:
        raise ValueError("review_work_cluster_id_invalid")
    projection = review_work_projection(record)
    clusters = {
        _text(cluster.get("cluster_id")): cluster
        for cluster in projection.get("clusters") or []
        if isinstance(cluster, Mapping) and _text(cluster.get("cluster_id"))
    }
    cluster = clusters.get(cluster_id)
    if not isinstance(cluster, Mapping):
        raise ValueError("review_work_cluster_id_invalid")
    if (
        cluster.get("grouped_review_eligible") is not True
        or cluster.get("homogeneous_evidence") is not True
        or cluster.get("homogeneous_verdict") is not True
    ):
        raise ValueError("review_work_group_disposition_requires_homogeneous_group")

    candidates = {
        _text(candidate.get("candidate_id")): candidate
        for candidate in projection.get("candidates") or []
        if isinstance(candidate, Mapping) and _text(candidate.get("candidate_id"))
    }
    candidate_ids = [_text(value) for value in cluster.get("candidate_ids") or [] if _text(value)]
    if not candidate_ids:
        raise ValueError("review_work_group_disposition_requires_candidates")
    unsafe: list[str] = []
    for candidate_id in candidate_ids:
        candidate = candidates.get(candidate_id)
        if not isinstance(candidate, Mapping):
            unsafe.append(candidate_id)
            continue
        if (
            candidate.get("individual_attention_required") is True
            or candidate.get("grouped_review_eligible") is not True
            or _text(candidate.get("primary_review_queue")) == "critical_material"
            or _text(candidate.get("human_disposition_state")) == "completed"
        ):
            unsafe.append(candidate_id)
    if unsafe:
        raise ValueError(
            "review_work_group_disposition_contains_non_bulk_reviewable_candidates:"
            + ",".join(sorted(set(unsafe)))
        )


def apply_review_work_action(
    record: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    now=None,
) -> dict[str, Any]:
    if _text(payload.get("action")).casefold() == "disposition_group":
        _validate_group_disposition(record, payload)
    return phase2.apply_review_work_action(record, payload, now=now)


ledger_for_record = phase2.ledger_for_record
canonical_candidate_register = phase2.canonical_candidate_register


__all__ = [
    "VERSION",
    "apply_review_work_action",
    "assert_ready_for_approval",
    "canonical_candidate_register",
    "ledger_for_record",
    "review_work_projection",
]
