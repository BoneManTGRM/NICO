from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

from nico.client_finding_remediation_register_v4 import (
    build_finding_remediation_register,
    synchronize_canonical_finding_surfaces,
)
from nico.phase15_production_integration_v1 import integrate_production_truth
from nico.phase16_client_delivery_verification_v1 import repair_client_delivery_package
from nico.v2_assessment_pipeline import canonicalize_findings as v2_canonicalize_findings
from nico.v2_pipeline_adapter import apply_v2_pipeline
from nico.v2_scanner_reconciliation import reconcile_scanner_records

VERSION = "nico.v2.comprehensive.finalizer.v6"
_FINDING_SURFACES = (
    "canonical_findings",
    "findings_register",
    "findings",
    "decision_grade_findings_register",
    "executive_risk_register",
    "priority_findings",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def canonicalize_findings(findings: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return v2_canonicalize_findings(findings)


def _findings_from(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values: list[Mapping[str, Any]] = []
    for surface in _FINDING_SURFACES:
        candidate = report.get(surface)
        if isinstance(candidate, list):
            values.extend(item for item in candidate if isinstance(item, Mapping))
    return values


def _sync_surface(value: Any, canonical_by_id: Mapping[str, Mapping[str, Any]]) -> Any:
    if isinstance(value, list):
        return [_sync_surface(item, canonical_by_id) for item in value]
    if not isinstance(value, Mapping):
        return value
    original = dict(value)
    item = {key: _sync_surface(child, canonical_by_id) for key, child in original.items()}
    finding_id = _text(original.get("finding_id") or original.get("id"))
    if finding_id and finding_id in canonical_by_id:
        canonical = canonical_by_id[finding_id]
        for field in (
            "finding_id", "id", "title", "decision_title", "category", "priority", "severity", "status",
            "location", "fact", "evidence", "interpretation", "business_impact", "impact", "recommendation",
            "owner_role", "effort", "cost_of_inaction", "residual_risk", "acceptance_criteria",
            "finding_aliases", "supporting_evidence",
        ):
            if field in canonical:
                item[field] = deepcopy(canonical[field])
    return item


def normalize_canonical_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Build one scanner population and one stable semantic finding population."""

    original_findings = _findings_from(report)
    normalized = reconcile_scanner_records(integrate_production_truth(report))
    source_findings = [*original_findings, *_findings_from(normalized)]
    findings = canonicalize_findings(source_findings)

    by_id: dict[str, Mapping[str, Any]] = {}
    for item in findings:
        for value in [item.get("finding_id"), item.get("id"), *(item.get("finding_aliases") or [])]:
            key = _text(value)
            if key:
                by_id[key] = item

    for surface in ("canonical_findings", "findings_register", "findings", "decision_grade_findings_register"):
        normalized[surface] = deepcopy(findings)
    normalized["executive_risk_register"] = deepcopy(findings[:7])
    normalized["priority_findings"] = deepcopy(findings[:5])
    for surface in (
        "executive_findings", "finding_cards", "roadmap", "backlog", "work_packages",
        "remediation_plan", "recommendations", "assessment", "stage_summaries",
    ):
        if surface in normalized:
            normalized[surface] = _sync_surface(normalized[surface], by_id)

    # The legacy canonicalizer intentionally preserves pre-existing IDs. Convert
    # those aliases into the final source-anchor/finding-family identity before
    # any report, roadmap, backlog, or stage projection is generated. This makes
    # first and repeated publication passes byte-stable at the canonical JSON
    # boundary instead of relying on a later rendering repair.
    register = build_finding_remediation_register(normalized)
    normalized = synchronize_canonical_finding_surfaces(normalized, register)
    stable_findings = [
        item for item in normalized.get("canonical_findings") or []
        if isinstance(item, Mapping)
    ]

    normalized["v2_prepublication_contract"] = {
        "version": VERSION,
        "canonical_finding_count": len(stable_findings),
        "scanner_result_count": len(normalized.get("scanner_execution_records") or []),
        "legacy_post_generation_mutation_disabled": True,
        "single_v2_publisher": True,
        "phase16_repair_runs_before_v2_rendering": True,
        "repaired_json_preserved_for_rendering": True,
        "pre_integration_finding_aliases_preserved": True,
        "stable_finding_identity_before_rendering": True,
        "all_mirrored_finding_surfaces_synchronized": True,
    }
    return normalized


def finalize_report_package(result: Mapping[str, Any], *, approval_state: str = "FINAL-PENDING-APPROVAL") -> dict[str, Any]:
    """The only Comprehensive publication boundary.

    Compatibility repair is allowed only before v2 rendering. Every final artifact
    is rebuilt afterward from the repaired canonical JSON and no later layer may
    mutate the client-facing population.
    """

    finalized = deepcopy(dict(result))
    package = deepcopy(finalized.get("report_package") if isinstance(finalized.get("report_package"), Mapping) else {})
    canonical = package.get("json") if isinstance(package.get("json"), Mapping) else finalized.get("canonical_report")
    if not isinstance(canonical, Mapping):
        raise ValueError("report package is missing canonical JSON")
    canonical = normalize_canonical_report(canonical)
    canonical["approval_state"] = approval_state
    package["json"] = canonical
    package = repair_client_delivery_package(package)
    repaired = package.get("json") if isinstance(package.get("json"), Mapping) else canonical
    repaired = normalize_canonical_report(repaired)
    repaired["approval_state"] = approval_state
    package["json"] = repaired
    finalized["report_package"] = package
    finalized["canonical_report"] = repaired
    finalized["approval_state"] = approval_state

    published = apply_v2_pipeline(finalized)
    package = published["report_package"]
    if not package["canonical_truth_sha256"]:
        raise ValueError("v2 publication did not bind a canonical truth hash")
    if not package["findings_csv_base64"]:
        raise ValueError("v2 publication did not produce the canonical findings CSV")
    return published


__all__ = ["VERSION", "canonicalize_findings", "normalize_canonical_report", "finalize_report_package"]
