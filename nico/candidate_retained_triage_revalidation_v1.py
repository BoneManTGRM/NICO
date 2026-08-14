from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Mapping

from nico.candidate_technical_triage_v1 import _fresh_triage, _route

VERSION = "nico.candidate-retained-triage-revalidation.v1"

_UNKNOWN_REACHABILITY = frozenset(
    {
        "",
        "unknown",
        "unresolved",
        "not_assessed",
        "not_available",
        "not_applicable",
        "not_supportable_from_retained_evidence",
    }
)
_RETAINED_SOURCE = "retained_prior_nico_recommendation"
_SAFE_RETAINED_LINEAGE = frozenset(
    {"carried_forward_exact", "carried_forward_location_changed"}
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _norm(value: Any) -> str:
    return _text(value).casefold().replace("-", "_").replace(" ", "_")


def _count(record: Mapping[str, Any]) -> int:
    try:
        return max(1, int(record.get("occurrence_count") or 1))
    except (TypeError, ValueError):
        return 1


def _proof_gaps(record: Mapping[str, Any]) -> set[str]:
    raw = record.get("technical_triage_proof_gaps") or record.get("proof_gaps") or []
    if isinstance(raw, str):
        raw = [raw]
    return {_norm(value) for value in raw if _text(value)}


def _requires_current_contract_revalidation(record: Mapping[str, Any]) -> bool:
    """Reject only retained dependency recommendations that violate current safety truth.

    A retained exact-lineage recommendation is reusable only while its reasoning still
    satisfies the current deterministic triage contract. In particular, an unresolved
    dependency reachability state cannot remain silently cleared by a historical
    recommendation that did not record the missing first-party reachability proof.

    Deterministically unaffected current package resolutions are exempt because their
    materiality does not depend on reachability; fresh triage emits the canonical
    `dependency_resolution_not_affected` rationale for that case.
    """

    if _norm(record.get("category")) != "dependency":
        return False
    if _text(record.get("technical_triage_source")) != _RETAINED_SOURCE:
        return False
    if _text(record.get("lineage_status")) not in _SAFE_RETAINED_LINEAGE:
        return False
    reachability = _norm(
        record.get("reachability_assessment")
        or record.get("technical_triage_reachability_assessment")
    )
    if reachability not in _UNKNOWN_REACHABILITY:
        return False
    if _norm(
        record.get("technical_triage_rationale_code") or record.get("rationale_code")
    ) == "dependency_resolution_not_affected":
        return False
    return "first_party_reachability" not in _proof_gaps(record)


def revalidate_retained_candidate_triage(register: Mapping[str, Any]) -> dict[str, Any]:
    """Freshly re-triage stale retained dependency recommendations, fail safe.

    This does not change candidate identity, scanner evidence, canonical candidate
    disposition, scoring, human disposition, reviewer identity, approval, or delivery
    authorization. It only refuses to carry forward an old proposal when its retained
    proof-gap contract is weaker than the current Phase 1 safety boundary.
    """

    output = deepcopy(dict(register))
    findings = [
        deepcopy(dict(item))
        for item in output.get("findings") or []
        if isinstance(item, Mapping)
    ]
    revalidated = 0
    revalidated_ids: list[str] = []

    for record in findings:
        if not _requires_current_contract_revalidation(record):
            continue
        previous_source = _text(record.get("technical_triage_source"))
        previous_rationale = _text(
            record.get("technical_triage_rationale_code") or record.get("rationale_code")
        )
        record.update(_fresh_triage(record))
        record["review_routing_class"] = _route(record)
        record["review_routing_is_human_decision"] = False
        record["retained_triage_revalidated_against_current_contract"] = True
        record["retained_triage_previous_source"] = previous_source
        record["retained_triage_previous_rationale_code"] = previous_rationale
        revalidated += _count(record)
        candidate_id = _text(record.get("candidate_id") or record.get("finding_id"))
        if candidate_id:
            revalidated_ids.append(candidate_id)

    technical = deepcopy(
        dict(output.get("technical_triage"))
        if isinstance(output.get("technical_triage"), Mapping)
        else {}
    )
    verdict_counts: Counter[str] = Counter()
    completed = 0
    for record in findings:
        verdict = _norm(record.get("technical_triage_verdict"))
        if verdict in {"not_actionable", "needs_review", "confirmed"}:
            count = _count(record)
            verdict_counts[verdict] += count
            completed += count

    total = sum(_count(record) for record in findings)
    canonical_counts = {
        "confirmed_count": verdict_counts["confirmed"],
        "needs_review_count": verdict_counts["needs_review"],
        "not_actionable_count": verdict_counts["not_actionable"],
        "technical_triage_completed": completed,
        "technical_triage_pending": max(0, total - completed),
        "technical_triage_coverage_pct": round(completed * 100 / total, 2) if total else 100.0,
    }
    technical.update(canonical_counts)
    existing_metrics = (
        deepcopy(dict(technical.get("workload_metrics")))
        if isinstance(technical.get("workload_metrics"), Mapping)
        else {}
    )
    existing_metrics.update(canonical_counts)
    technical["workload_metrics"] = existing_metrics
    technical["verdict_counts"] = {
        "confirmed": verdict_counts["confirmed"],
        "needs_review": verdict_counts["needs_review"],
        "not_actionable": verdict_counts["not_actionable"],
    }
    technical["imported_candidate_count"] = max(
        0,
        int(technical.get("imported_candidate_count") or 0) - revalidated,
    )
    technical["retained_prior_revalidation"] = {
        "artifact_schema": VERSION,
        "status": "complete",
        "revalidated_candidate_count": revalidated,
        "revalidated_candidate_ids": sorted(set(revalidated_ids)),
        "current_contract": "unresolved_dependency_reachability_requires_explicit_proof_gap_or_fresh_determination",
        "candidate_counts_changed": False,
        "scanner_evidence_changed": False,
        "canonical_dispositions_changed": False,
        "human_disposition_created": False,
        "reviewer_identity_created": False,
        "human_approval_created": False,
        "client_delivery_allowed": False,
        "score_effect": "none",
    }
    technical["retained_prior_revalidation_count"] = revalidated
    technical["human_disposition_created"] = False
    technical["reviewer_identity_created"] = False
    technical["human_approval_status"] = "pending"
    technical["client_delivery_allowed"] = False

    output["findings"] = findings
    output["technical_triage"] = technical
    output["candidate_retained_triage_revalidation"] = deepcopy(
        technical["retained_prior_revalidation"]
    )
    return output


__all__ = [
    "VERSION",
    "revalidate_retained_candidate_triage",
]
