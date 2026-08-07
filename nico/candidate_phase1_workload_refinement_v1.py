from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from typing import Any, Mapping, Sequence

from nico.candidate_lineage_migration_v1 import subject_identity

VERSION = "nico.candidate-phase1-workload-refinement.v1"

_OPTIONAL_SUBJECT_PLACEHOLDERS: dict[str, frozenset[str]] = {
    "project_id": frozenset({"default_project", "default-project"}),
    "workspace_id": frozenset({"default_workspace", "default-workspace"}),
    "assessment_target_id": frozenset({"default_target", "default-target"}),
}
_HUMAN_ROUTES = frozenset({"CRITICAL_ATTENTION", "HUMAN_TECHNICAL_REVIEW"})
_ALLOWED_GROUP_CATEGORIES = frozenset({"dependency", "static"})
_UNGROUPABLE_EVIDENCE_QUALITY = frozenset({"count_only", "payload_without_source"})
_HIGH_RISK_SEVERITIES = frozenset({"critical", "high"})


def _text(value: Any, limit: int = 2000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _norm(value: Any) -> str:
    return _text(value).casefold().replace("-", "_").replace(" ", "_")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _count(record: Mapping[str, Any]) -> int:
    try:
        return max(1, int(record.get("occurrence_count") or 1))
    except (TypeError, ValueError):
        return 1


def _candidate_id(record: Mapping[str, Any]) -> str:
    return _text(record.get("candidate_id") or record.get("finding_id"), 300)


def _proof_gaps(record: Mapping[str, Any]) -> tuple[str, ...]:
    values = record.get("technical_triage_proof_gaps") or record.get("proof_gaps") or []
    if isinstance(values, str):
        values = [values]
    return tuple(sorted({_text(value, 300) for value in values if _text(value, 300)}))


def _explicit_conflict(record: Mapping[str, Any]) -> bool:
    for source in (
        record,
        _mapping(record.get("deterministic_evidence")),
        _mapping(record.get("scanner_evidence")),
    ):
        for key in ("conflicting_evidence", "evidence_conflict", "scanner_conflict"):
            value = source.get(key)
            if value is True or _norm(value) in {"true", "yes", "conflict", "conflicting"}:
                return True
    return False


def normalize_optional_assessment_subject(
    value: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, Any]]:
    """Normalize only known system placeholder identities.

    Real project, workspace, and target identities remain part of the lineage
    boundary. This function only removes the exact placeholder values that NICO
    itself uses when an optional identity was not supplied.
    """

    raw = subject_identity(value)
    normalized = dict(raw)
    ignored: dict[str, str] = {}
    for field, placeholders in _OPTIONAL_SUBJECT_PLACEHOLDERS.items():
        current = normalized.get(field)
        if current and _norm(current) in {_norm(item) for item in placeholders}:
            ignored[field] = current
            normalized.pop(field, None)
    metadata = {
        "artifact_schema": VERSION,
        "raw_subject": raw,
        "normalized_subject": normalized,
        "ignored_optional_placeholders": ignored,
        "placeholder_normalization_applied": bool(ignored),
        "real_optional_identities_remain_partitioning_boundaries": True,
        "cross_repository_carry_forward_allowed": False,
        "cross_project_carry_forward_allowed": False,
        "cross_workspace_carry_forward_allowed": False,
        "cross_target_carry_forward_allowed": False,
    }
    return normalized, metadata


def scan_assessment_subject(scan: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    candidates: list[tuple[str, Mapping[str, Any]]] = [("scan", scan)]
    for key in ("assessment", "target", "repository", "project", "metadata", "context"):
        nested = scan.get(key)
        if isinstance(nested, Mapping):
            candidates.append((key, nested))

    merged: dict[str, str] = {}
    raw_by_source: dict[str, dict[str, str]] = {}
    ignored: dict[str, str] = {}
    conflicts: dict[str, list[str]] = {}
    for source_name, candidate in candidates:
        raw = subject_identity(candidate)
        if not raw:
            continue
        raw_by_source[source_name] = raw
        normalized, metadata = normalize_optional_assessment_subject(
            {"assessment_subject": raw}
        )
        for field, value in (
            metadata.get("ignored_optional_placeholders") or {}
        ).items():
            ignored[field] = value
        for field, value in normalized.items():
            prior = merged.get(field)
            if prior is None:
                merged[field] = value
            elif prior != value:
                conflicts[field] = sorted({prior, value})

    fail_closed = bool(conflicts)
    subject = {} if fail_closed else merged
    metadata = {
        "artifact_schema": VERSION,
        "source": "merged_scan_context",
        "raw_subjects_by_source": raw_by_source,
        "normalized_subject": subject,
        "ignored_optional_placeholders": ignored,
        "placeholder_normalization_applied": bool(ignored),
        "identity_conflicts": conflicts,
        "identity_conflict_fail_closed": fail_closed,
        "repository_identity_available": "repository" in subject,
        "real_optional_identities_remain_partitioning_boundaries": True,
        "cross_repository_carry_forward_allowed": False,
        "cross_project_carry_forward_allowed": False,
        "cross_workspace_carry_forward_allowed": False,
        "cross_target_carry_forward_allowed": False,
    }
    return subject, metadata


def _dependency_identity(record: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        _norm(record.get("dependency_package")),
        _norm(record.get("dependency_version")),
        _norm(record.get("dependency_ecosystem")),
        _norm(record.get("advisory") or record.get("rule") or record.get("rule_id")),
    )


def _review_profile(record: Mapping[str, Any]) -> tuple[Any, ...] | None:
    verdict = _norm(record.get("technical_triage_verdict"))
    category = _norm(record.get("category"))
    scanner = _norm(record.get("scanner") or record.get("tool"))
    rule = _norm(record.get("rule") or record.get("rule_id") or record.get("advisory"))
    severity = _norm(record.get("severity")) or "unknown"
    confidence = _norm(record.get("technical_triage_confidence")) or "unknown"
    scope = _norm(
        record.get("production_test_development_scope")
        or record.get("scope")
        or record.get("dependency_scope")
    ) or "unknown"
    rationale = _norm(
        record.get("technical_triage_rationale_code") or record.get("rationale_code")
    )
    triage_source = _norm(record.get("technical_triage_source"))
    gaps = _proof_gaps(record)
    evidence_quality = _norm(record.get("evidence_quality"))

    if category not in _ALLOWED_GROUP_CATEGORIES:
        return None
    if verdict not in {"needs_review", "not_actionable"}:
        return None
    if evidence_quality in _UNGROUPABLE_EVIDENCE_QUALITY:
        return None
    if record.get("evidence_changed") is True or _explicit_conflict(record):
        return None
    if not scanner or not rule or rule in {"unclassified", "count_only"}:
        return None

    if verdict == "not_actionable":
        if (
            confidence != "high"
            or gaps
            or record.get("review_routing_class") != "QUALITY_CONTROL_ELIGIBLE"
        ):
            return None
    else:
        if severity in _HIGH_RISK_SEVERITIES or not gaps:
            return None

    if category == "dependency":
        package, version, ecosystem, advisory = _dependency_identity(record)
        if not all((package, version, ecosystem, advisory)):
            return None
        return (
            "dependency",
            verdict,
            scanner,
            advisory,
            package,
            version,
            ecosystem,
            scope,
            severity,
            confidence,
            rationale,
            triage_source,
            gaps,
        )

    return (
        "static",
        verdict,
        scanner,
        rule,
        scope,
        severity,
        confidence,
        rationale,
        triage_source,
        gaps,
    )


def _individual_profile(record: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        "individual",
        _candidate_id(record),
        _text(record.get("raw_fingerprint") or record.get("lineage_id"), 300),
    )


def _cluster_reason(profile: tuple[Any, ...] | None) -> str:
    if not profile:
        return "candidate-specific evidence or risk boundary requires individual review"
    if profile[0] == "dependency":
        return (
            "same scanner/advisory/package/version/ecosystem/scope/rationale/proof-gap profile; "
            "every underlying candidate and location remains preserved"
        )
    return (
        "same scanner/rule/scope/severity/rationale/proof-gap profile; "
        "every underlying candidate and location remains preserved"
    )


def _refined_clusters(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    profiles: dict[tuple[Any, ...], tuple[Any, ...] | None] = {}
    for record in records:
        review_profile = _review_profile(record)
        key = review_profile if review_profile is not None else _individual_profile(record)
        grouped[key].append(record)
        profiles[key] = review_profile

    summaries: list[dict[str, Any]] = []
    for key in sorted(grouped, key=lambda value: json.dumps(value, sort_keys=True, default=str)):
        members = grouped[key]
        review_profile = profiles[key]
        candidate_ids = sorted({_candidate_id(item) for item in members if _candidate_id(item)})
        representative = candidate_ids[0] if candidate_ids else ""
        cluster_size = sum(_count(item) for item in members)
        verdicts = {_norm(item.get("technical_triage_verdict")) for item in members}
        routes = {_text(item.get("review_routing_class"), 80) for item in members}
        eligible = review_profile is not None and len(members) > 1 and len(verdicts) == 1
        digest = hashlib.sha256(
            json.dumps(key, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()[:20].upper()
        cluster_id = f"NICO-CLUSTER-{digest}"
        human_cluster = eligible and bool(routes & _HUMAN_ROUTES)
        summary = {
            "cluster_id": cluster_id,
            "cluster_reason": _cluster_reason(review_profile),
            "cluster_size": cluster_size,
            "candidate_record_count": len(members),
            "candidate_ids": candidate_ids,
            "representative_candidate_id": representative,
            "homogeneous_evidence": review_profile is not None or len(members) == 1,
            "homogeneous_evidence_basis": (
                "identical normalized technical-review profile; source evidence remains candidate-specific"
                if review_profile is not None
                else "candidate-specific cluster"
            ),
            "homogeneous_verdict": len(verdicts) == 1,
            "grouped_review_eligible": eligible,
            "grouped_human_review_cluster": human_cluster,
            "review_routing_classes": sorted(route for route in routes if route),
            "underlying_candidate_disposition_required": True,
        }
        summaries.append(summary)
        for item in members:
            item.update(
                {
                    "cluster_id": cluster_id,
                    "cluster_reason": summary["cluster_reason"],
                    "cluster_size": cluster_size,
                    "cluster_candidate_ids": candidate_ids,
                    "representative_candidate_id": representative,
                    "homogeneous_evidence": summary["homogeneous_evidence"],
                    "homogeneous_evidence_basis": summary["homogeneous_evidence_basis"],
                    "homogeneous_verdict": summary["homogeneous_verdict"],
                    "grouped_review_eligible": eligible,
                    "review_requires_individual_attention": (
                        item.get("review_routing_class") in _HUMAN_ROUTES and not eligible
                    ),
                    "review_unit_id": cluster_id if eligible else _candidate_id(item),
                    "review_grouping_is_human_decision": False,
                }
            )
    return summaries


def _refined_metrics(
    records: Sequence[Mapping[str, Any]],
    clusters: Sequence[Mapping[str, Any]],
    existing: Mapping[str, Any],
) -> dict[str, Any]:
    metrics = deepcopy(dict(existing))
    human_before = sum(
        _count(item)
        for item in records
        if item.get("review_routing_class") in _HUMAN_ROUTES
    )
    grouped_human_candidates = sum(
        _count(item)
        for item in records
        if item.get("review_routing_class") in _HUMAN_ROUTES
        and item.get("grouped_review_eligible") is True
    )
    individual = sum(
        _count(item)
        for item in records
        if item.get("review_routing_class") in _HUMAN_ROUTES
        and item.get("grouped_review_eligible") is not True
    )
    grouped_candidates = sum(
        _count(item)
        for item in records
        if item.get("review_routing_class") in _HUMAN_ROUTES
        and item.get("grouped_review_eligible") is True
    )
    grouped_human_clusters = sum(
        1 for cluster in clusters if cluster.get("grouped_human_review_cluster") is True
    )
    individual_records = sum(
        1
        for item in records
        if item.get("review_routing_class") in _HUMAN_ROUTES
        and item.get("grouped_review_eligible") is not True
    )
    quality_control_records = [
        item
        for item in records
        if item.get("review_routing_class")
        in {"QUALITY_CONTROL_ELIGIBLE", "STABLE_CARRY_FORWARD"}
        and _norm(item.get("technical_triage_verdict")) == "not_actionable"
        and _norm(item.get("technical_triage_confidence")) == "high"
        and not _proof_gaps(item)
        and item.get("evidence_changed") is not True
        and not _explicit_conflict(item)
    ]
    quality_control_pool = sum(_count(item) for item in quality_control_records)
    work_units = individual_records + grouped_human_clusters
    reduction = max(0, human_before - work_units)
    metrics.update(
        {
            "cluster_count": len(clusters),
            "candidates_requiring_individual_human_attention": individual,
            "candidates_eligible_for_grouped_review": grouped_candidates,
            "grouped_human_review_candidate_count": grouped_human_candidates,
            "grouped_review_cluster_count": grouped_human_clusters,
            "human_attention_candidate_count_before_grouping": human_before,
            "individual_human_review_record_count": individual_records,
            "human_review_work_units": work_units,
            "review_workload_reduction_count": reduction,
            "review_workload_reduction_pct": (
                round(reduction * 100 / human_before, 2) if human_before else 0.0
            ),
            "quality_control_sample_pool": quality_control_pool,
            "quality_control_sample_record_count": len(quality_control_records),
            "stable_carry_forward_quality_control_eligible": True,
        }
    )
    return metrics


def refine_candidate_review_workload(register: Mapping[str, Any]) -> dict[str, Any]:
    """Refine review routing without changing technical or human dispositions."""

    output = deepcopy(dict(register))
    records = [
        deepcopy(dict(item))
        for item in output.get("findings") or []
        if isinstance(item, Mapping)
    ]
    technical = deepcopy(
        dict(output.get("technical_triage"))
        if isinstance(output.get("technical_triage"), Mapping)
        else {}
    )
    existing_metrics = (
        technical.get("workload_metrics")
        if isinstance(technical.get("workload_metrics"), Mapping)
        else {}
    )
    clusters = _refined_clusters(records)
    metrics = _refined_metrics(records, clusters, existing_metrics)

    technical.update(metrics)
    technical["workload_metrics"] = deepcopy(metrics)
    technical["review_workload_clusters"] = deepcopy(clusters)
    technical["workload_refinement"] = {
        "artifact_schema": VERSION,
        "status": "complete",
        "candidate_counts_changed": False,
        "canonical_dispositions_changed": False,
        "technical_verdicts_changed": False,
        "human_disposition_created": False,
        "reviewer_identity_created": False,
        "risk_acceptance_created": False,
        "human_approval_created": False,
        "client_delivery_allowed": False,
        "score_effect": "none",
        "secrets_grouped_for_required_human_review": False,
        "confirmed_or_high_risk_candidates_grouped": False,
        "count_only_candidates_grouped": False,
    }
    output["findings"] = records
    output["technical_triage"] = technical
    output["review_workload_clusters"] = deepcopy(clusters)
    output["candidate_review_workload_refinement"] = deepcopy(
        technical["workload_refinement"]
    )
    output["canonical_digest_sha256"] = hashlib.sha256(
        json.dumps(records, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    return output


__all__ = [
    "VERSION",
    "normalize_optional_assessment_subject",
    "refine_candidate_review_workload",
    "scan_assessment_subject",
]
