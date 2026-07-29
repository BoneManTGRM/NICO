from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from copy import deepcopy
from typing import Any, Iterable, Mapping

from nico.phase15_production_integration_v1 import integrate_production_truth
from nico.phase9_production_report_gate_v1 import (
    acceptance_key,
    assert_production_report,
    contextual_title,
    finding_semantic_key,
    normalized_filename,
)

VERSION = "nico.phase9_comprehensive_report_integration.v3"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _dedupe_values(values: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        key = acceptance_key(value)
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _normalize_finding(raw: Mapping[str, Any]) -> dict[str, Any]:
    finding = deepcopy(dict(raw))
    title = contextual_title(finding)
    finding["title"] = title
    finding["decision_title"] = title
    criteria = finding.get("acceptance_criteria") or []
    if isinstance(criteria, str):
        criteria = [part.strip() for part in criteria.split(";") if part.strip()]
    finding["acceptance_criteria"] = _dedupe_values(criteria)
    return finding


def canonicalize_findings(findings: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for raw in findings:
        finding = _normalize_finding(raw)
        key = finding_semantic_key(finding)
        if key in seen:
            continue
        seen.add(key)
        result.append(finding)
    return result


def _finding_ids(findings: Iterable[Mapping[str, Any]]) -> list[str]:
    return [_text(item.get("finding_id") or item.get("id")) for item in findings if _text(item.get("finding_id") or item.get("id"))]


def _sync_surface(value: Any, canonical_by_id: Mapping[str, Mapping[str, Any]]) -> Any:
    if isinstance(value, list):
        return [_sync_surface(item, canonical_by_id) for item in value]
    if not isinstance(value, Mapping):
        return value

    # Recurse through the original structure first. Enriching a matching record
    # before recursion can inject supporting_evidence records that carry the same
    # finding ID, causing unbounded self-similar expansion.
    original = dict(value)
    item = {key: _sync_surface(child, canonical_by_id) for key, child in original.items()}
    finding_id = _text(original.get("finding_id") or original.get("id"))
    if finding_id and finding_id in canonical_by_id:
        canonical = canonical_by_id[finding_id]
        for field in (
            "title", "decision_title", "category", "priority", "severity", "status",
            "location", "fact", "evidence", "interpretation", "business_impact",
            "impact", "recommendation", "owner_role", "effort", "cost_of_inaction",
            "residual_risk", "acceptance_criteria", "finding_aliases", "supporting_evidence",
        ):
            if field in canonical:
                item[field] = deepcopy(canonical[field])
    return item


def normalize_canonical_report(report: Mapping[str, Any]) -> dict[str, Any]:
    normalized = integrate_production_truth(report)
    source = normalized.get("canonical_findings") or normalized.get("findings_register") or normalized.get("findings") or []
    findings = canonicalize_findings(item for item in source if isinstance(item, Mapping))
    by_id: dict[str, Mapping[str, Any]] = {}
    for item in findings:
        ids = [item.get("finding_id"), item.get("id"), *(item.get("finding_aliases") or [])]
        for value in ids:
            key = _text(value)
            if key:
                by_id[key] = item

    normalized["canonical_findings"] = deepcopy(findings)
    normalized["findings_register"] = deepcopy(findings)
    normalized["findings"] = deepcopy(findings)
    normalized["decision_grade_findings_register"] = deepcopy(findings)
    normalized["executive_risk_register"] = deepcopy(findings[:7])
    normalized["priority_findings"] = deepcopy(findings[:5])
    for surface in (
        "executive_findings", "finding_cards", "roadmap", "backlog", "work_packages",
        "remediation_plan", "recommendations", "assessment", "stage_summaries",
    ):
        if surface in normalized:
            normalized[surface] = _sync_surface(normalized[surface], by_id)
    normalized["phase9_truth_contract"] = {
        "version": VERSION,
        "canonical_finding_count": len(findings),
        "canonical_finding_ids": _finding_ids(findings),
        "all_surfaces_share_canonical_population": True,
        "acceptance_criteria_deduplicated": True,
        "generic_titles_repaired": True,
        "phase13_and_phase14_applied_before_rendering": True,
        "recursive_surface_expansion_blocked": True,
    }
    return normalized


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _findings_csv(findings: Iterable[Mapping[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    fields = ["finding_id", "priority", "category", "title", "location", "status", "recommendation", "acceptance_criteria"]
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for item in findings:
        writer.writerow({
            "finding_id": item.get("finding_id") or item.get("id"),
            "priority": item.get("priority"),
            "category": item.get("category"),
            "title": item.get("title"),
            "location": item.get("location"),
            "status": item.get("status"),
            "recommendation": item.get("recommendation"),
            "acceptance_criteria": " | ".join(_text(v) for v in item.get("acceptance_criteria") or []),
        })
    return buffer.getvalue().encode("utf-8")


def finalize_report_package(result: Mapping[str, Any], *, approval_state: str = "FINAL-PENDING-APPROVAL") -> dict[str, Any]:
    finalized = deepcopy(dict(result))
    package = deepcopy(finalized.get("report_package") if isinstance(finalized.get("report_package"), Mapping) else {})
    canonical = package.get("json") if isinstance(package.get("json"), Mapping) else finalized.get("canonical_report")
    if not isinstance(canonical, Mapping):
        raise ValueError("report package is missing canonical JSON")
    canonical = normalize_canonical_report(canonical)
    canonical["approval_state"] = approval_state
    package["json"] = canonical
    package["canonical_findings"] = deepcopy(canonical["canonical_findings"])
    package["findings_register"] = deepcopy(canonical["findings_register"])
    package["analyzer_evidence_report"] = deepcopy(canonical.get("analyzer_evidence_report") or {})
    package["analyzer_evidence_ui"] = deepcopy(canonical.get("analyzer_evidence_ui") or {})
    package["findings_csv_base64"] = base64.b64encode(_findings_csv(canonical["canonical_findings"])).decode("ascii")
    package["canonical_truth_sha256"] = _sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8"))

    filename = _text(package.get("pdf_filename") or "nico-comprehensive-assessment.pdf")
    package["pdf_filename"] = normalized_filename(filename, approval_state)
    if package.get("spanish_pdf_filename"):
        package["spanish_pdf_filename"] = normalized_filename(_text(package["spanish_pdf_filename"]), approval_state)
    if package.get("json_filename"):
        package["json_filename"] = normalized_filename(_text(package["json_filename"]), approval_state).replace(".pdf", ".json")
    package["phase9_release_gate"] = assert_production_report(canonical, filename=package["pdf_filename"])
    package["phase9_release_gate"]["production_path_integrated"] = True
    package["phase9_release_gate"]["all_export_surfaces_canonicalized"] = True
    package["phase9_release_gate"]["phase13_and_phase14_visible"] = True
    finalized["report_package"] = package
    finalized["canonical_report"] = canonical
    finalized["approval_state"] = approval_state
    return finalized


__all__ = [
    "VERSION", "canonicalize_findings", "normalize_canonical_report", "finalize_report_package",
]