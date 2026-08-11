from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from nico import comprehensive_review_work_v2 as phase2

VERSION = "nico.comprehensive_review_work_safe.v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _validate_group_disposition(record: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
    cluster_id = _text(payload.get("cluster_id"))
    if not cluster_id:
        raise ValueError("review_work_cluster_id_invalid")
    projection = phase2.review_work_projection(record)
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
        queue = _text(candidate.get("primary_review_queue"))
        if (
            candidate.get("individual_attention_required") is True
            or candidate.get("grouped_review_eligible") is not True
            or queue in {"critical_material", "human_technical_review"}
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


review_work_projection = phase2.review_work_projection
assert_ready_for_approval = phase2.assert_ready_for_approval
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
