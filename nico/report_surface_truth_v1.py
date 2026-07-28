from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from nico.final_assessment_truth_v1 import TruthViolation

VERSION = "nico.report_surface_truth.v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def truth_projection(assessment: Mapping[str, Any]) -> dict[str, Any]:
    maturity = dict(assessment.get("maturity_signal") or {})
    findings = list(assessment.get("canonical_findings") or assessment.get("findings_register") or [])
    limitations = list(assessment.get("unavailable_data_notes") or [])
    return {
        "repository": assessment.get("repository"),
        "commit_sha": assessment.get("commit_sha") or (assessment.get("assessment_identity") or {}).get("immutable_revision"),
        "run_id": assessment.get("run_id"),
        "observed_performance": maturity.get("observed_performance", assessment.get("observed_performance")),
        "coverage_adjusted_maturity": maturity.get("coverage_adjusted_maturity", assessment.get("coverage_adjusted_maturity")),
        "evidence_adjusted_readiness": maturity.get("evidence_adjusted_readiness", assessment.get("evidence_adjusted_readiness")),
        "approval_state": assessment.get("approval_state"),
        "client_ready": bool(assessment.get("client_ready")),
        "client_delivery_allowed": bool(assessment.get("client_delivery_allowed")),
        "finding_ids": sorted(str(item.get("finding_id") or item.get("record_id") or item.get("id") or "") for item in findings),
        "limitations": sorted(str(item) for item in limitations),
    }


def validate_report_surfaces(
    assessment: Mapping[str, Any],
    surfaces: Mapping[str, Mapping[str, Any]],
    *,
    required_surfaces: Sequence[str] = ("json", "markdown", "html", "pdf", "csv"),
) -> dict[str, Any]:
    expected = truth_projection(assessment)
    expected_digest = _digest(expected)
    missing = sorted(set(required_surfaces) - set(surfaces))
    mismatches: dict[str, Any] = {}
    for name, payload in surfaces.items():
        projection = truth_projection(payload)
        if projection != expected:
            mismatches[name] = {"expected_digest": expected_digest, "actual_digest": _digest(projection)}
    if missing or mismatches:
        raise TruthViolation(f"Cross-format truth validation failed: missing={missing}; mismatches={sorted(mismatches)}")
    return {
        "version": VERSION,
        "truth_digest": expected_digest,
        "validated_surfaces": sorted(surfaces),
        "valid": True,
    }


def validate_localizations(english: Mapping[str, Any], spanish: Mapping[str, Any]) -> dict[str, Any]:
    left = truth_projection(english)
    right = truth_projection(spanish)
    if left != right:
        raise TruthViolation("English and Spanish report truth projections differ")
    return {"version": VERSION, "truth_digest": _digest(left), "valid": True}


__all__ = ["truth_projection", "validate_localizations", "validate_report_surfaces"]
