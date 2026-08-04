from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable, Mapping

from nico.client_finding_remediation_register_v5 import (
    build_finding_remediation_register,
    synchronize_canonical_finding_surfaces,
)
from nico.comprehensive_artifact_filename_truth_v1 import (
    install_comprehensive_artifact_filename_truth_v1,
)
from nico.comprehensive_client_ready_projection_v1 import APPROVAL_SUFFIX
from nico.phase15_production_integration_v1 import integrate_production_truth
from nico.phase16_client_delivery_verification_v1 import repair_client_delivery_package
from nico.v2_assessment_pipeline import canonicalize_findings as v2_canonicalize_findings
from nico.v2_pipeline_adapter import apply_v2_pipeline
from nico.v2_scanner_reconciliation import reconcile_scanner_records

VERSION = "nico.v2.comprehensive.finalizer.v7.3"
_ARTIFACT_FILENAME_TRUTH = install_comprehensive_artifact_filename_truth_v1()
_FINDING_SURFACES = (
    "canonical_findings",
    "findings_register",
    "findings",
    "decision_grade_findings_register",
    "executive_risk_register",
    "priority_findings",
)
_EXACT_MANIFEST_SCHEMA = "nico.comprehensive-artifact-manifest.v1"
_EXACT_IDENTITY_SCHEMA = "nico.comprehensive-draft-artifact-identity.v1"
_REQUIRED_ARTIFACT_TYPES = {
    "findings_csv",
    "evidence_csv",
    "candidate_register_json",
    "remediation_backlog_json",
    "markdown_report",
    "html_report",
    "comprehensive_pdf",
    "canonical_json",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: Any) -> str:
    candidate = _text(value).lower()
    if len(candidate) != 64:
        return ""
    return candidate if all(character in "0123456789abcdef" for character in candidate) else ""


def _already_finalized_exact_artifact_result(result: Mapping[str, Any]) -> bool:
    """Recognize only a complete, internally consistent unapproved artifact package.

    Re-running publication over an already finalized package appends manifest pages,
    changes rendered HTML, and necessarily changes the PDF and detached digests.
    Preserve exact bytes only after independently recomputing all three retained
    digests, verifying the complete artifact inventory, and confirming the
    fail-closed Automated Draft lifecycle. The canonical JSON's embedded manifest
    is informative and self-referential; the detached manifest is authoritative.
    """

    package = result.get("report_package")
    if not isinstance(package, Mapping):
        return False
    canonical = package.get("json")
    detached_manifest = package.get("artifact_manifest")
    identity = package.get("draft_artifact_identity")
    completion = package.get("client_report_completion")
    if not all(
        isinstance(value, Mapping)
        for value in (canonical, detached_manifest, identity, completion)
    ):
        return False
    if detached_manifest.get("artifact_schema") != _EXACT_MANIFEST_SCHEMA:
        return False
    if identity.get("artifact_schema") != _EXACT_IDENTITY_SCHEMA:
        return False

    manifest_id = _text(detached_manifest.get("manifest_id"))
    if not manifest_id or manifest_id != _text(identity.get("manifest_id")):
        return False
    artifact_types = {
        _text(item.get("artifact_type"))
        for item in detached_manifest.get("artifacts") or []
        if isinstance(item, Mapping)
    }
    if not _REQUIRED_ARTIFACT_TYPES.issubset(artifact_types):
        return False

    if completion.get("artifact_manifest_present") is not True:
        return False
    if package.get("review_package_ready") is not True:
        return False
    if package.get("human_review_required") is not True:
        return False
    if package.get("client_delivery_allowed") is not False:
        return False
    if _text(package.get("report_finality")).lower() != "automated_draft":
        return False
    if "pending" not in _text(package.get("approval_status")).lower():
        return False
    if "blocked" not in _text(package.get("delivery_status")).lower():
        return False

    expected_pdf = _digest(identity.get("pdf_sha256"))
    expected_json = _digest(identity.get("canonical_json_sha256"))
    expected_manifest = _digest(identity.get("evidence_manifest_sha256"))
    if not all((expected_pdf, expected_json, expected_manifest)):
        return False
    if _digest(package.get("pdf_sha256")) != expected_pdf:
        return False
    if _digest(package.get("canonical_json_sha256")) != expected_json:
        return False
    if _digest(package.get("evidence_manifest_sha256")) != expected_manifest:
        return False

    try:
        pdf = base64.b64decode(str(package.get("pdf_base64") or ""), validate=True)
        canonical_json = str(package.get("canonical_json") or "").encode("utf-8")
        manifest_json = str(package.get("evidence_manifest_json") or "").encode("utf-8")
        canonical_payload = json.loads(canonical_json.decode("utf-8"))
        manifest_payload = json.loads(manifest_json.decode("utf-8"))
    except Exception:
        return False
    if not pdf.startswith(b"%PDF") or _sha256(pdf) != expected_pdf:
        return False
    if not canonical_json or _sha256(canonical_json) != expected_json:
        return False
    if not manifest_json or _sha256(manifest_json) != expected_manifest:
        return False
    if not isinstance(canonical_payload, Mapping):
        return False
    if not isinstance(manifest_payload, Mapping):
        return False
    if _text(manifest_payload.get("manifest_id")) != manifest_id:
        return False
    manifest_payload_types = {
        _text(item.get("artifact_type"))
        for item in manifest_payload.get("artifacts") or []
        if isinstance(item, Mapping)
    }
    if not _REQUIRED_ARTIFACT_TYPES.issubset(manifest_payload_types):
        return False
    return True


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
            "finding_id",
            "id",
            "title",
            "decision_title",
            "category",
            "priority",
            "severity",
            "status",
            "location",
            "fact",
            "evidence",
            "interpretation",
            "business_impact",
            "impact",
            "recommendation",
            "owner_role",
            "effort",
            "cost_of_inaction",
            "residual_risk",
            "acceptance_criteria",
            "finding_aliases",
            "supporting_evidence",
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
        for value in [
            item.get("finding_id"),
            item.get("id"),
            *(item.get("finding_aliases") or []),
        ]:
            key = _text(value)
            if key:
                by_id[key] = item

    for surface in (
        "canonical_findings",
        "findings_register",
        "findings",
        "decision_grade_findings_register",
    ):
        normalized[surface] = deepcopy(findings)
    normalized["executive_risk_register"] = deepcopy(findings[:7])
    normalized["priority_findings"] = deepcopy(findings[:5])
    for surface in (
        "executive_findings",
        "finding_cards",
        "roadmap",
        "backlog",
        "work_packages",
        "remediation_plan",
        "recommendations",
        "assessment",
        "stage_summaries",
    ):
        if surface in normalized:
            normalized[surface] = _sync_surface(normalized[surface], by_id)

    register = build_finding_remediation_register(normalized)
    normalized = synchronize_canonical_finding_surfaces(normalized, register)
    stable_findings = [
        item
        for item in normalized.get("canonical_findings") or []
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
        "automated_draft_is_default_unapproved_state": True,
        "complete_exact_artifact_idempotence": True,
        "artifact_filename_truth_version": _ARTIFACT_FILENAME_TRUTH.get("version"),
    }
    return normalized


def finalize_report_package(
    result: Mapping[str, Any],
    *,
    approval_state: str = APPROVAL_SUFFIX,
) -> dict[str, Any]:
    """The only Comprehensive publication boundary."""

    if _already_finalized_exact_artifact_result(result):
        return deepcopy(dict(result))

    finalized = deepcopy(dict(result))
    package = deepcopy(
        finalized.get("report_package")
        if isinstance(finalized.get("report_package"), Mapping)
        else {}
    )
    canonical = (
        package.get("json")
        if isinstance(package.get("json"), Mapping)
        else finalized.get("canonical_report")
    )
    if not isinstance(canonical, Mapping):
        raise ValueError("report package is missing canonical JSON")
    canonical = normalize_canonical_report(canonical)
    canonical["approval_state"] = approval_state
    package["json"] = canonical
    package = repair_client_delivery_package(package)
    repaired = (
        package.get("json")
        if isinstance(package.get("json"), Mapping)
        else canonical
    )
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


__all__ = [
    "VERSION",
    "canonicalize_findings",
    "normalize_canonical_report",
    "finalize_report_package",
]
