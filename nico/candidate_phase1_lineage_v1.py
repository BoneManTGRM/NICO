from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from nico.candidate_lineage_identity_v1 import baseline_subject, subject_identity
from nico.candidate_lineage_migration_v1 import apply_candidate_lineage, load_default_baseline

VERSION = "nico.candidate-phase1-lineage.v1"
_FIELDS = ("repository", "project_id", "workspace_id", "assessment_target_id")


def _subject_gate(register: Mapping[str, Any], baseline: Mapping[str, Any]) -> tuple[bool, dict[str, str], dict[str, str], str]:
    current = subject_identity(register); prior = baseline_subject(baseline)
    if not current.get("repository"): return False, current, prior, "current_subject_identity_missing"
    if not prior.get("repository"): return False, current, prior, "prior_subject_identity_missing"
    for field in _FIELDS:
        current_value = current.get(field); prior_value = prior.get(field)
        if current_value and not prior_value: return False, current, prior, "prior_subject_identity_incomplete"
        if prior_value and current_value != prior_value: return False, current, prior, "assessment_subject_mismatch"
    return True, current, prior, "assessment_subject_exact_match"


def apply_subject_safe_lineage(register: Mapping[str, Any], *, baseline: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Apply existing lineage only when the prior baseline proves the same subject."""
    output = deepcopy(dict(register))
    try:
        source = dict(baseline or load_default_baseline())
    except Exception as exc:
        source = {}; reason = type(exc).__name__; matched = False; current = subject_identity(output); prior: dict[str, str] = {}
    else:
        matched, current, prior, reason = _subject_gate(output, source)
    if matched:
        result = apply_candidate_lineage(output, baseline=source)
        lineage = dict(result.get("candidate_lineage") or {})
        lineage.update({"subject_identity_schema": VERSION, "assessment_subject_match": True, "assessment_subject_match_reason": reason, "current_subject": current, "prior_subject": prior, "cross_project_carry_forward_allowed": True})
        result["candidate_lineage"] = lineage
        return result
    findings = [deepcopy(dict(item)) for item in output.get("findings") or [] if isinstance(item, Mapping)]
    for item in findings:
        item["candidate_id"] = item.get("candidate_id") or item.get("finding_id")
        item["lineage_status"] = "newly_observed"; item["evidence_changed"] = False
        item["human_approval_status"] = "pending"; item["human_approval_carried_forward"] = False
        item.pop("prior_candidate_id", None); item.pop("prior_proposed_disposition", None); item.pop("prior_cluster_id", None)
    output["findings"] = findings
    total = sum(max(1, int(item.get("occurrence_count") or 1)) for item in findings)
    output["candidate_lineage"] = {
        "artifact_schema": VERSION, "status": "complete", "prior_register_available": bool(source),
        "prior_candidate_count": int(source.get("n") or 0) if source else 0,
        "assessment_subject_match": False, "assessment_subject_match_reason": reason, "current_subject": current, "prior_subject": prior,
        "current_candidate_count": total, "carried_forward_exact": 0, "carried_forward_location_changed": 0,
        "carried_forward_evidence_changed": 0, "carried_forward_total": 0, "newly_observed": total,
        "no_longer_observed": 0, "tombstones": [], "human_approval_carried_forward": False,
        "client_delivery_allowed": False, "cross_project_carry_forward_allowed": False,
    }
    return output

__all__ = ["VERSION", "apply_subject_safe_lineage"]
