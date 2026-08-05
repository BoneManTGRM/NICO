from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

from nico.client_assessment_truth_v3 import normalize_repository_path

VERSION = "nico.comprehensive-finding-integrity.v1"
MANIFEST_KEY = "finding_integrity_manifest"
EXECUTIVE_DETAIL_LIMIT = 7
_VALID_PRIORITY = {"P0", "P1", "P2", "P3"}
_LOCATION = re.compile(r"^(.*?):(\d+)(?:-\d+)?(?::\d+)?$")


def _text(value: Any) -> str:
    return " ".join(str(value or "").replace("\x7f", "-").split()).strip()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def _location(item: Mapping[str, Any]) -> tuple[str, int | None, str]:
    nested = item.get("source") if isinstance(item.get("source"), Mapping) else {}
    raw_location = _text(item.get("location") or nested.get("location"))
    path = normalize_repository_path(
        item.get("path")
        or item.get("file_path")
        or item.get("source_path")
        or nested.get("path")
        or ""
    )
    raw_line = (
        item.get("line")
        or item.get("start_line")
        or item.get("line_number")
        or nested.get("line")
    )
    line = int(raw_line) if str(raw_line or "").isdigit() else None
    match = _LOCATION.match(raw_location)
    if match:
        path = normalize_repository_path(match.group(1))
        line = line or int(match.group(2))
    elif not path and raw_location:
        path = normalize_repository_path(raw_location)
    location = f"{path}:{line}" if path and line is not None else path
    return path, line, location


def _first_text(item: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, Mapping):
            text = _text(value.get("summary") or value.get("text") or value.get("status"))
        elif isinstance(value, (list, tuple)):
            text = "; ".join(_text(part) for part in value if _text(part))
        else:
            text = _text(value)
        if text:
            return text
    return ""


def _finding_id(item: Mapping[str, Any]) -> str:
    return _text(item.get("finding_id") or item.get("id"))


def _finding_record(item: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
    finding_id = _finding_id(item)
    priority = _text(item.get("priority")).upper()
    path, line, location = _location(item)
    evidence = _first_text(
        item,
        "evidence",
        "observed_evidence",
        "fact",
        "problematic_code",
    )
    impact = _first_text(item, "impact", "business_impact", "probable_impact", "interpretation")
    correction = _first_text(
        item,
        "correction",
        "recommendation",
        "remediation",
        "recommended_action",
    )
    verification = _first_text(
        item,
        "verification",
        "acceptance_criteria",
        "verification_method",
        "test_strategy",
    )
    complexity = item.get("cyclomatic_complexity")
    if complexity in (None, ""):
        nested = item.get("complexity") if isinstance(item.get("complexity"), Mapping) else {}
        complexity = nested.get("cyclomatic_complexity") or nested.get("value")
    errors: list[str] = []
    if not finding_id:
        errors.append("finding_id:required")
    if priority not in _VALID_PRIORITY:
        errors.append("priority:invalid_or_missing")
    if kind == "code":
        if not path:
            errors.append("source.path:required")
        if line is None or line < 1:
            errors.append("source.line:required_positive_integer")
        if not evidence:
            errors.append("evidence:required")
        if not impact:
            errors.append("impact:required")
        if not correction:
            errors.append("correction:required")
        if not verification:
            errors.append("verification:required")
    anchor = f"{path.casefold()}:{line}" if path and line is not None else ""
    subject = {
        "finding_id": finding_id,
        "kind": kind,
        "priority": priority,
        "source": {"path": path, "line": line, "location": location},
        "evidence": evidence,
        "impact": impact,
        "correction": correction,
        "verification": verification,
        "cyclomatic_complexity": complexity,
        "disposition": _text(item.get("disposition") or "human_review_required"),
    }
    return {
        **subject,
        "source_anchor": anchor,
        "record_sha256": _sha256(subject),
        "validation_errors": errors,
    }


def _records(register: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for kind, key in (
        ("code", "code_findings"),
        ("operational", "operational_findings"),
    ):
        for raw in register.get(key) or []:
            if isinstance(raw, Mapping):
                records.append(_finding_record(raw, kind=kind))
    return sorted(records, key=lambda item: (item["priority"], item["finding_id"]))


def _canonical_surface(canonical: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in (
        "canonical_findings",
        "findings_register",
        "decision_grade_findings_register",
        "findings",
    ):
        value = canonical.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    for key in ("decision_grade_findings_register", "executive_risk_register"):
        value = assessment.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    return []


def build_finding_integrity_manifest(
    canonical: Mapping[str, Any],
    register: Mapping[str, Any],
) -> dict[str, Any]:
    records = _records(register)
    errors: list[str] = []
    ids = [item["finding_id"] for item in records]
    anchors = [item["source_anchor"] for item in records if item["kind"] == "code"]
    duplicate_ids = sorted({value for value in ids if value and ids.count(value) > 1})
    duplicate_anchors = sorted({value for value in anchors if value and anchors.count(value) > 1})
    for record in records:
        errors.extend(
            f"{record['finding_id'] or '<missing>'}.{error}"
            for error in record["validation_errors"]
        )
    if duplicate_ids:
        errors.extend(f"duplicate_finding_id:{value}" for value in duplicate_ids)
    if duplicate_anchors:
        errors.extend(f"duplicate_exact_source_anchor:{value}" for value in duplicate_anchors)

    surface = _canonical_surface(canonical)
    surface_ids = sorted(_finding_id(item) for item in surface if _finding_id(item))
    register_ids = sorted(value for value in ids if value)
    if surface and surface_ids != register_ids:
        missing = sorted(set(register_ids) - set(surface_ids))
        extra = sorted(set(surface_ids) - set(register_ids))
        errors.append(
            "canonical_surface_finding_ids:mismatch;"
            f"missing={','.join(missing)};extra={','.join(extra)}"
        )

    surface_locations = {
        _finding_id(item): _location(item)[2]
        for item in surface
        if _finding_id(item)
    }
    for record in records:
        finding_id = record["finding_id"]
        if finding_id in surface_locations and surface_locations[finding_id] != record["source"]["location"]:
            errors.append(
                f"{finding_id}.canonical_surface_location:mismatch;"
                f"register={record['source']['location']};"
                f"surface={surface_locations[finding_id]}"
            )

    summary = register.get("summary") if isinstance(register.get("summary"), Mapping) else {}
    expected_count = int(summary.get("decision_finding_count") or len(records))
    if expected_count != len(records):
        errors.append(
            "decision_finding_count:mismatch;"
            f"summary={expected_count};records={len(records)}"
        )

    priority_counts = {
        priority: sum(1 for item in records if item["priority"] == priority)
        for priority in sorted(_VALID_PRIORITY)
        if any(item["priority"] == priority for item in records)
    }
    code_count = sum(1 for item in records if item["kind"] == "code")
    operational_count = len(records) - code_count
    subject = {
        "record_digests": [item["record_sha256"] for item in records],
        "priority_counts": priority_counts,
        "decision_finding_count": len(records),
        "exact_source_code_finding_count": code_count,
        "operational_or_context_finding_count": operational_count,
        "executive_detail_policy": {
            "expanded_detail_limit": EXECUTIVE_DETAIL_LIMIT,
            "all_findings_remain_in_exact_source_index": True,
            "bounded_expansion_does_not_change_priority": True,
        },
    }
    return {
        "artifact_schema": VERSION,
        **subject,
        "records": records,
        "duplicate_finding_ids": duplicate_ids,
        "duplicate_exact_source_anchors": duplicate_anchors,
        "validation_status": "valid" if not errors else "invalid",
        "validation_errors": sorted(set(errors)),
        "finding_integrity_sha256": _sha256(subject),
        "human_disposition_required": True,
        "automation_may_disposition_findings": False,
    }


def attach_finding_integrity_manifest(
    canonical: Mapping[str, Any],
    register: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(canonical))
    manifest = build_finding_integrity_manifest(result, register)
    if manifest["validation_status"] != "valid":
        raise ValueError(
            "finding_integrity_invalid:"
            + ",".join(manifest["validation_errors"])
        )
    result[MANIFEST_KEY] = manifest
    contract = deepcopy(dict(result.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "finding_integrity_version": VERSION,
            "exact_source_findings_field_complete": True,
            "finding_priority_policy_explicit": True,
            "bounded_executive_detail_preserves_full_index": True,
            "finding_disposition_remains_human_only": True,
        }
    )
    result["v2_pipeline_contract"] = contract
    return result


def validate_finding_integrity_manifest(canonical: Mapping[str, Any]) -> dict[str, Any]:
    manifest = canonical.get(MANIFEST_KEY)
    if not isinstance(manifest, Mapping):
        return {"status": "invalid", "validation_errors": [f"{MANIFEST_KEY}:required"]}
    errors = list(manifest.get("validation_errors") or [])
    records = [item for item in manifest.get("records") or [] if isinstance(item, Mapping)]
    subject = {
        "record_digests": [item.get("record_sha256") for item in records],
        "priority_counts": deepcopy(manifest.get("priority_counts") or {}),
        "decision_finding_count": int(manifest.get("decision_finding_count") or 0),
        "exact_source_code_finding_count": int(manifest.get("exact_source_code_finding_count") or 0),
        "operational_or_context_finding_count": int(manifest.get("operational_or_context_finding_count") or 0),
        "executive_detail_policy": deepcopy(manifest.get("executive_detail_policy") or {}),
    }
    if _sha256(subject) != _text(manifest.get("finding_integrity_sha256")):
        errors.append("finding_integrity_sha256:mismatch")
    if int(manifest.get("decision_finding_count") or 0) != len(records):
        errors.append("decision_finding_count:does_not_match_records")
    return {
        "status": "valid" if not errors else "invalid",
        "validation_errors": sorted(set(errors)),
        "finding_integrity_sha256": _text(manifest.get("finding_integrity_sha256")),
    }


__all__ = [
    "EXECUTIVE_DETAIL_LIMIT",
    "MANIFEST_KEY",
    "VERSION",
    "attach_finding_integrity_manifest",
    "build_finding_integrity_manifest",
    "validate_finding_integrity_manifest",
]
