from __future__ import annotations
import hashlib, json
from copy import deepcopy
from typing import Any, Mapping
from nico.candidate_phase1_triage_fresh_v1 import fresh_triage
from nico.candidate_phase1_triage_grouping_v1 import cluster_candidates
from nico.candidate_phase1_triage_metrics_v1 import finalize_routes_and_metrics
from nico.candidate_phase1_triage_record_v1 import normalize_retained
from nico.candidate_phase1_triage_utils_v1 import ALGORITHM_VERSION, count
from nico.candidate_phase1_retained_v1 import attach_retained_proposals

VERSION = "nico.candidate-phase1-technical-triage.v1"
_SYSTEM_FIELDS = {
    "rationale_code", "boundary_assessment", "recommended_next_step", "proof_gaps", "evidence_used", "counterevidence",
    "review_routing_class", "review_routing_is_human_decision", "cluster_id", "cluster_reason", "cluster_size",
    "representative_candidate_id", "homogeneous_evidence", "homogeneous_verdict", "grouped_review_eligible",
}


def _clear_untrusted_prior_technical_state(record: dict[str, Any]) -> None:
    """Only lineage-authorized retained artifacts may seed Phase 1 technical reasoning."""
    for key in list(record):
        if key.startswith("technical_triage_") or key in _SYSTEM_FIELDS:
            record.pop(key, None)


def apply_phase1_technical_triage(register: Mapping[str, Any], *, triage: Mapping[str, Any] | None = None) -> dict[str, Any]:
    output = deepcopy(dict(register))
    records = [deepcopy(dict(item)) for item in output.get("findings") or [] if isinstance(item, Mapping)]
    for record in records:
        _clear_untrusted_prior_technical_state(record)
    imported, retained_status = attach_retained_proposals(records, triage=triage)
    fresh = 0
    for record in records:
        record["technical_triage_human_approval_status"] = "pending"
        record["technical_triage_human_approval_carried_forward"] = False
        record["technical_triage_client_delivery_allowed"] = False
        if record.get("technical_triage_status") == "imported_proposal":
            normalize_retained(record)
        else:
            record.update(fresh_triage(record)); fresh += count(record)
    clusters = cluster_candidates(records)
    metrics = finalize_routes_and_metrics(records)
    output["findings"] = records
    output["technical_triage"] = {
        "artifact_schema": VERSION, "algorithm_version": ALGORITHM_VERSION, "status": "complete",
        "technical_triage_available": True, "retained_artifact_status": retained_status, "imported_candidate_count": imported,
        "fresh_technical_triage_completed": fresh, "runtime_validation_performed": False,
        "human_approval_status": "pending", "human_approval_carried_forward": False,
        "human_disposition_created": False, "reviewer_identity_created": False, "risk_acceptance_created": False,
        "client_delivery_allowed": False, "score_effect": "none", "clusters": clusters,
        "workload_metrics": deepcopy(metrics), **metrics,
    }
    output["canonical_digest_sha256"] = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    return output

__all__ = ["VERSION", "apply_phase1_technical_triage"]
