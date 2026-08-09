#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

VERSION = "nico.phase1-structured-artifact-audit.v1"
EXPLICIT_UNKNOWN = {
    "unknown",
    "not_assessed",
    "not_available",
    "not_applicable",
    "not_supportable_from_retained_evidence",
}
TRIAGE_VERDICTS = {"not_actionable", "needs_review", "confirmed"}
ROUTING_CLASSES = {
    "CRITICAL_ATTENTION",
    "HUMAN_TECHNICAL_REVIEW",
    "AUTOMATED_TRIAGE_COMPLETE",
    "STABLE_CARRY_FORWARD",
    "QUALITY_CONTROL_ELIGIBLE",
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _require(condition: bool, code: str, errors: list[str]) -> None:
    if not condition:
        errors.append(code)


def _manifest_entry(payload: dict[str, Any], artifact_type: str) -> dict[str, Any]:
    manifest = payload.get("artifact_manifest") if isinstance(payload.get("artifact_manifest"), dict) else {}
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    return next(
        (dict(item) for item in artifacts if isinstance(item, dict) and item.get("artifact_type") == artifact_type),
        {},
    )


def audit(payload: dict[str, Any], *, expected_sha: str = "") -> dict[str, Any]:
    errors: list[str] = []
    identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
    assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else {}
    register = (
        assessment.get("canonical_scanner_finding_register")
        if isinstance(assessment.get("canonical_scanner_finding_register"), dict)
        else {}
    )
    records = register.get("findings") if isinstance(register.get("findings"), list) else []
    records = [dict(item) for item in records if isinstance(item, dict)]
    ids = [_text(item.get("candidate_id")) for item in records]
    id_set = set(ids)

    run_id = _text(identity.get("run_id"))
    commit_sha = _text(identity.get("commit_sha"))
    repository = _text(identity.get("repository"))
    _require(bool(run_id), "identity.run_id_missing", errors)
    _require(bool(commit_sha), "identity.commit_sha_missing", errors)
    _require(bool(repository), "identity.repository_missing", errors)
    if expected_sha:
        _require(commit_sha == expected_sha, "identity.commit_sha_mismatch", errors)
    _require(len(records) > 0, "candidate_register.empty", errors)
    _require(all(ids), "candidate.candidate_id_missing", errors)
    _require(len(ids) == len(id_set), "candidate.candidate_id_duplicate", errors)
    _require(register.get("candidate_record_count") == len(records), "candidate_register.count_mismatch", errors)
    _require(register.get("count_parity_verified") is True, "candidate_register.count_parity_not_verified", errors)
    _require(
        register.get("mutually_exclusive_dispositions_verified") is True,
        "candidate_register.dispositions_not_mutually_exclusive",
        errors,
    )

    universal = (
        "candidate_id",
        "category",
        "scanner",
        "tool",
        "exact_commit_sha",
        "technical_triage_status",
        "technical_triage_verdict",
        "technical_triage_confidence",
        "technical_triage_rationale",
        "technical_triage_rationale_code",
        "technical_triage_source",
        "technical_triage_model_or_version",
        "technical_triage_boundary_assessment",
        "technical_triage_proof_gaps",
        "technical_triage_recommended_next_step",
        "lineage_status",
        "evidence_changed",
        "review_routing_class",
        "grouped_review_eligible",
        "human_approval_status",
        "human_review_required",
    )
    missing_fields: Counter[str] = Counter()
    category_counts = Counter()
    verdict_counts = Counter()
    lineage_counts = Counter()
    routing_counts = Counter()
    clusters: dict[str, list[dict[str, Any]]] = {}

    for record in records:
        candidate_id = _text(record.get("candidate_id")) or "missing"
        category = _text(record.get("category"))
        category_counts[category] += 1
        verdict = _text(record.get("technical_triage_verdict"))
        verdict_counts[verdict] += 1
        lineage_counts[_text(record.get("lineage_status"))] += 1
        routing = _text(record.get("review_routing_class"))
        routing_counts[routing] += 1

        for field in universal:
            value = record.get(field)
            if value is None or value == "":
                missing_fields[field] += 1
                errors.append(f"candidate.{candidate_id}.{field}_missing")

        _require(record.get("exact_commit_sha") == commit_sha, f"candidate.{candidate_id}.commit_mismatch", errors)
        _require(verdict in TRIAGE_VERDICTS, f"candidate.{candidate_id}.triage_verdict_invalid", errors)
        _require(routing in ROUTING_CLASSES, f"candidate.{candidate_id}.routing_class_invalid", errors)
        _require(record.get("human_review_required") is True, f"candidate.{candidate_id}.human_review_not_required", errors)
        _require(
            record.get("human_approval_status") == "pending",
            f"candidate.{candidate_id}.human_approval_not_pending",
            errors,
        )
        _require(
            record.get("human_approval_carried_forward") is False,
            f"candidate.{candidate_id}.human_approval_carried_forward",
            errors,
        )
        _require(
            record.get("technical_triage_client_delivery_allowed") is False,
            f"candidate.{candidate_id}.technical_triage_delivery_allowed",
            errors,
        )
        _require(
            not record.get("human_disposition"),
            f"candidate.{candidate_id}.automation_created_human_disposition",
            errors,
        )
        _require(
            not record.get("reviewer_identity"),
            f"candidate.{candidate_id}.automation_created_reviewer_identity",
            errors,
        )
        _require(bool(record.get("evidence_digest_sha256")), f"candidate.{candidate_id}.evidence_digest_missing", errors)
        _require(bool(record.get("raw_fingerprint")), f"candidate.{candidate_id}.raw_fingerprint_missing", errors)
        _require(record.get("proof_gaps") is not None, f"candidate.{candidate_id}.proof_gaps_missing", errors)
        _require(
            bool(_text(record.get("rule") or record.get("advisory") or record.get("rule_id"))),
            f"candidate.{candidate_id}.rule_or_advisory_missing",
            errors,
        )

        if category == "dependency":
            for field in ("dependency_package", "dependency_version", "dependency_ecosystem", "manifest_path"):
                _require(bool(_text(record.get(field))), f"candidate.{candidate_id}.{field}_missing", errors)
            if _text(record.get("reachability_assessment")) in EXPLICIT_UNKNOWN:
                _require(
                    "first_party_reachability" in (record.get("proof_gaps") or []),
                    f"candidate.{candidate_id}.reachability_gap_not_explicit",
                    errors,
                )
        elif category == "secret":
            evidence = _text(record.get("evidence"))
            _require(
                "REDACTED" in evidence or "without a human-readable message" in evidence,
                f"candidate.{candidate_id}.secret_projection_not_redacted",
                errors,
            )
            _require(
                record.get("raw_payload_retention_state") == "retained",
                f"candidate.{candidate_id}.raw_payload_not_retained",
                errors,
            )
        elif category == "static":
            _require(
                bool(_text(record.get("source_path") or record.get("path"))),
                f"candidate.{candidate_id}.source_path_missing",
                errors,
            )
            _require(record.get("line") is not None, f"candidate.{candidate_id}.source_line_missing", errors)
            if verdict == "confirmed":
                _require(
                    not record.get("technical_triage_proof_gaps"),
                    f"candidate.{candidate_id}.confirmed_with_proof_gaps",
                    errors,
                )
        else:
            errors.append(f"candidate.{candidate_id}.category_invalid")

        cluster_id = _text(record.get("cluster_id"))
        _require(bool(cluster_id), f"candidate.{candidate_id}.cluster_id_missing", errors)
        if cluster_id:
            clusters.setdefault(cluster_id, []).append(record)

        lineage_status = _text(record.get("lineage_status"))
        source = _text(record.get("technical_triage_source"))
        if lineage_status in {"newly_observed", "evidence_changed"}:
            _require(source.startswith("fresh_"), f"candidate.{candidate_id}.fresh_triage_source_required", errors)
        if lineage_status == "exact_carry_forward":
            _require(
                bool(_text(record.get("previous_candidate_identity"))),
                f"candidate.{candidate_id}.previous_identity_missing",
                errors,
            )
            _require(
                "retained" in source or "carry" in source,
                f"candidate.{candidate_id}.carry_forward_source_invalid",
                errors,
            )
        if record.get("evidence_changed") is True:
            _require(
                lineage_status == "evidence_changed",
                f"candidate.{candidate_id}.evidence_changed_lineage_mismatch",
                errors,
            )
            _require(source.startswith("fresh_"), f"candidate.{candidate_id}.stale_triage_inherited", errors)

    cluster_errors = 0
    grouped_ids: set[str] = set()
    for cluster_id, members in clusters.items():
        declared_ids = set()
        for member in members:
            declared_ids.update(str(item) for item in (member.get("cluster_candidate_ids") or []))
        member_ids = {str(item.get("candidate_id")) for item in members}
        expected_ids = declared_ids or member_ids
        representative = _text(members[0].get("representative_candidate_id"))
        valid = (
            expected_ids <= id_set
            and representative in expected_ids
            and all(int(item.get("cluster_size") or 0) == len(expected_ids) for item in members)
            and len({_text(item.get("technical_triage_verdict")) for item in members}) == 1
            and all(item.get("homogeneous_evidence") is True for item in members)
            and all(item.get("homogeneous_verdict") is True for item in members)
        )
        if not valid:
            cluster_errors += 1
            errors.append(f"cluster.{cluster_id}.integrity_failed")
        if any(item.get("grouped_review_eligible") is True for item in members):
            _require(len(expected_ids) > 1, f"cluster.{cluster_id}.grouped_singleton", errors)
            grouped_ids.update(expected_ids)

    triage = register.get("technical_triage") if isinstance(register.get("technical_triage"), dict) else {}
    _require(triage.get("human_disposition_created") is False, "triage.human_disposition_created", errors)
    _require(triage.get("human_approval_status") == "pending", "triage.human_approval_not_pending", errors)
    _require(triage.get("client_delivery_allowed") is False, "triage.client_delivery_allowed", errors)
    _require(sum(verdict_counts.values()) == len(records), "triage.verdict_count_mismatch", errors)
    for verdict, field in (
        ("not_actionable", "not_actionable_count"),
        ("needs_review", "needs_review_count"),
        ("confirmed", "confirmed_count"),
    ):
        _require(
            int(triage.get(field) or 0) == verdict_counts.get(verdict, 0),
            f"triage.{field}_mismatch",
            errors,
        )

    individual_ids = {
        item["candidate_id"]
        for item in records
        if item.get("review_requires_individual_attention") is True
    }
    _require(not (individual_ids & grouped_ids), "workload.individual_grouped_overlap", errors)
    expected_work_units = len(individual_ids) + sum(
        1
        for members in clusters.values()
        if any(item.get("grouped_review_eligible") is True for item in members)
    )
    _require(
        int(triage.get("human_review_work_units") or 0) == expected_work_units,
        "workload.human_review_work_units_mismatch",
        errors,
    )
    _require(
        int(triage.get("candidates_requiring_individual_human_attention") or 0) == len(individual_ids),
        "workload.individual_count_mismatch",
        errors,
    )
    _require(
        int(triage.get("candidates_eligible_for_grouped_review") or 0) == len(grouped_ids),
        "workload.grouped_count_mismatch",
        errors,
    )

    refinement = (
        register.get("candidate_review_workload_refinement")
        if isinstance(register.get("candidate_review_workload_refinement"), dict)
        else {}
    )
    _require(refinement.get("candidate_counts_changed") is False, "workload.candidate_counts_changed", errors)
    _require(
        refinement.get("canonical_dispositions_changed") is False,
        "workload.canonical_dispositions_changed",
        errors,
    )
    _require(refinement.get("technical_verdicts_changed") is False, "workload.technical_verdicts_changed", errors)
    _require(refinement.get("score_effect") == "none", "workload.score_effect_not_none", errors)
    _require(refinement.get("human_disposition_created") is False, "workload.human_disposition_created", errors)
    _require(refinement.get("human_approval_created") is False, "workload.human_approval_created", errors)
    _require(refinement.get("risk_acceptance_created") is False, "workload.risk_acceptance_created", errors)

    entry = _manifest_entry(payload, "candidate_register_json")
    register_bytes = _canonical_bytes(register)
    observed_digest = hashlib.sha256(register_bytes).hexdigest()
    _require(bool(entry), "artifact_manifest.candidate_register_missing", errors)
    if entry:
        _require(entry.get("run_id") == run_id, "artifact_manifest.run_id_mismatch", errors)
        _require(entry.get("commit_sha") == commit_sha, "artifact_manifest.commit_sha_mismatch", errors)
        _require(entry.get("repository") == repository, "artifact_manifest.repository_mismatch", errors)
        _require(entry.get("customer_id") == identity.get("customer_id"), "artifact_manifest.customer_id_mismatch", errors)
        _require(entry.get("project_id") == identity.get("project_id"), "artifact_manifest.project_id_mismatch", errors)
        _require(
            entry.get("evidence_ledger_id") == identity.get("evidence_ledger_id"),
            "artifact_manifest.evidence_ledger_id_mismatch",
            errors,
        )
        _require(
            entry.get("sha256") == observed_digest,
            "artifact_manifest.candidate_register_sha256_mismatch",
            errors,
        )
        _require(
            int(entry.get("size_bytes") or 0) == len(register_bytes),
            "artifact_manifest.candidate_register_size_mismatch",
            errors,
        )

    _require(payload.get("human_review_required") is True, "package.human_review_not_required", errors)
    _require(payload.get("client_delivery_allowed") is False, "package.client_delivery_allowed", errors)
    _require(
        _text(payload.get("approval_state")).lower()
        in {"pending", "review_required", "automated-draft-pending-approval"}
        or _text(payload.get("approval_status")).lower() in {"pending", "pending_human_approval"},
        "package.approval_state_not_pending",
        errors,
    )
    _require(payload.get("review_package_ready") is True, "package.review_package_not_ready", errors)

    result = {
        "artifact_schema": VERSION,
        "status": "passed" if not errors else "failed",
        "repository": repository,
        "run_id": run_id,
        "commit_sha": commit_sha,
        "candidate_register_filename": entry.get("filename", ""),
        "candidate_register_sha256_expected": entry.get("sha256", ""),
        "candidate_register_sha256_observed": observed_digest,
        "candidate_register_size_bytes": len(register_bytes),
        "candidate_count": len(records),
        "category_counts": dict(sorted(category_counts.items())),
        "verdict_counts": dict(sorted(verdict_counts.items())),
        "lineage_counts": dict(sorted(lineage_counts.items())),
        "routing_counts": dict(sorted(routing_counts.items())),
        "cluster_count": len(clusters),
        "grouped_candidate_count": len(grouped_ids),
        "individual_attention_count": len(individual_ids),
        "human_review_work_units": expected_work_units,
        "quality_control_sample_pool": int(triage.get("quality_control_sample_pool") or 0),
        "human_review_required": payload.get("human_review_required") is True,
        "client_delivery_allowed": payload.get("client_delivery_allowed") is True,
        "score_effect": refinement.get("score_effect"),
        "missing_field_counts": dict(sorted(missing_fields.items())),
        "cluster_integrity_error_count": cluster_errors,
        "errors": errors,
    }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-json", type=Path, required=True)
    parser.add_argument("--expected-sha", default="")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(args.canonical_json.read_text(encoding="utf-8"))
    result = audit(payload, expected_sha=args.expected_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    if result["status"] != "passed":
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "status",
                    "run_id",
                    "commit_sha",
                    "candidate_count",
                    "cluster_count",
                    "grouped_candidate_count",
                    "individual_attention_count",
                    "human_review_work_units",
                    "candidate_register_sha256_observed",
                )
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
