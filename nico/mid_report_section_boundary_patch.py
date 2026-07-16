from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

MID_REPORT_SECTION_BOUNDARY_VERSION = "nico.mid_report_section_boundary.v1"
_MARKER = "_nico_mid_report_section_boundary_v1"
_BOUNDARY_FIELDS = (
    "evidence",
    "verified_claims",
    "findings",
    "unavailable",
    "missing_evidence_sources",
    "failed_evidence_tools",
    "unverified_claims",
    "scope_disclosures",
)
_NON_VERIFIED_STATUSES = {
    "unavailable",
    "failed",
    "human review required",
    "verified with limitations",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _texts(value: Any) -> list[str]:
    values: list[str] = []
    for item in _list(value):
        text = " ".join(str(item or "").split())
        if text and text not in values:
            values.append(text)
    return values


def _merge_texts(*values: Any) -> list[str]:
    merged: list[str] = []
    for value in values:
        for item in _texts(value):
            if item not in merged:
                merged.append(item)
    return merged


def _source_sections(record: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    response = _dict(record.get("response"))
    assessment = _dict(response.get("assessment"))
    truth = _dict(response.get("mid_truth_status"))
    sources: dict[str, list[dict[str, Any]]] = {}
    for collection in (truth.get("sections"), assessment.get("sections")):
        for item in _list(collection):
            if not isinstance(item, dict):
                continue
            section_id = str(item.get("id") or "")
            if section_id:
                sources.setdefault(section_id, []).append(item)
    return sources


def reconcile_mid_report_section_boundaries(payload: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(payload)
    sources = _source_sections(record)
    sections: list[dict[str, Any]] = []
    fallback_count = 0
    merged_count = 0

    for raw in _list(output.get("sections")):
        if not isinstance(raw, dict):
            continue
        section = deepcopy(raw)
        section_id = str(section.get("id") or "")
        retained = sources.get(section_id, [])
        for field in _BOUNDARY_FIELDS:
            merged = _merge_texts(section.get(field), *(item.get(field) for item in retained))
            if merged != _texts(section.get(field)):
                merged_count += 1
            section[field] = merged

        for source in retained:
            if not section.get("truth_status") and source.get("truth_status"):
                section["truth_status"] = source.get("truth_status")
            if not section.get("summary") and source.get("summary"):
                section["summary"] = source.get("summary")
            if not section.get("source_classification") and source.get("source_classification"):
                section["source_classification"] = source.get("source_classification")

        evidence = _merge_texts(section.get("evidence"), section.get("verified_claims"))
        limitations = _merge_texts(
            section.get("unavailable"),
            section.get("missing_evidence_sources"),
            section.get("failed_evidence_tools"),
            section.get("unverified_claims"),
        )
        truth_status = " ".join(str(section.get("truth_status") or section.get("status") or "").lower().split())

        if not evidence and not limitations and truth_status in _NON_VERIFIED_STATUSES:
            summary = " ".join(str(section.get("summary") or "").split())
            disclosures = _texts(section.get("scope_disclosures"))
            boundary = summary or (disclosures[0] if disclosures else "")
            if boundary:
                section["unavailable"] = _merge_texts(section.get("unavailable"), [boundary])
                section["explicit_evidence_boundary_source"] = "retained_non_verified_truth_summary"
                fallback_count += 1

        section["unsupported_claims_permitted"] = False
        sections.append(section)

    output["sections"] = sections
    output["mid_report_section_boundary_version"] = MID_REPORT_SECTION_BOUNDARY_VERSION
    output["mid_report_section_boundary_reconciliation"] = {
        "section_count": len(sections),
        "retained_boundary_fields_merged": merged_count,
        "non_verified_summary_boundaries_added": fallback_count,
        "verified_empty_sections_allowed": False,
        "missing_evidence_converted_to_pass": False,
        "scores_changed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return output


def install_mid_report_section_boundary_patch() -> dict[str, Any]:
    from nico import mid_assessment_report as report_module

    current: Callable[[dict[str, Any], dict[str, Any], dict[str, Any], str], dict[str, Any]] = report_module._report_payload
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": MID_REPORT_SECTION_BOUNDARY_VERSION}

    @wraps(current)
    def payload_with_retained_boundaries(
        record: dict[str, Any],
        packet: dict[str, Any],
        identity: dict[str, Any],
        generated_at: str,
    ) -> dict[str, Any]:
        return reconcile_mid_report_section_boundaries(
            current(record, packet, identity, generated_at),
            record,
        )

    setattr(payload_with_retained_boundaries, _MARKER, True)
    setattr(payload_with_retained_boundaries, "_nico_previous", current)
    report_module._report_payload = payload_with_retained_boundaries
    return {
        "status": "installed",
        "version": MID_REPORT_SECTION_BOUNDARY_VERSION,
        "retained_assessment_sections_reconciled": True,
        "retained_truth_sections_reconciled": True,
        "non_verified_summary_boundary_allowed": True,
        "verified_empty_section_allowed": False,
        "missing_evidence_converted_to_pass": False,
        "scores_changed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MID_REPORT_SECTION_BOUNDARY_VERSION",
    "install_mid_report_section_boundary_patch",
    "reconcile_mid_report_section_boundaries",
]
