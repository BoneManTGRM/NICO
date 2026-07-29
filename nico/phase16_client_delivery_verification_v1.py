from __future__ import annotations

import base64
import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.phase16.client-delivery-verification.v2"
_APPROVAL = "FINAL-PENDING-APPROVAL"
_FINDING_SURFACES = (
    "canonical_findings",
    "findings_register",
    "findings",
    "decision_grade_findings_register",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _norm(value: Any) -> str:
    return _text(value).casefold()


def _finding_id(item: Mapping[str, Any]) -> str:
    return _text(item.get("finding_id") or item.get("id"))


def _location(item: Mapping[str, Any]) -> str:
    value = item.get("location")
    if isinstance(value, Mapping):
        path = _text(value.get("path") or value.get("file") or value.get("file_path"))
        line = _text(value.get("line") or value.get("start_line"))
        return f"{path}:{line}".strip(":").casefold()
    return _text(value).replace("\\", "/").casefold()


def _family(item: Mapping[str, Any]) -> str:
    title = _norm(item.get("interpretation") or item.get("decision_title") or item.get("title"))
    if "complexity" in title and ("hotspot" in title or "complex" in title):
        return "complexity_hotspot"
    rule = _norm(item.get("rule_id") or item.get("rule") or item.get("check_id"))
    return rule or re.sub(r"\brisk(?:-p[0-3])?-[a-z0-9]+\b", "", title).strip()


def _semantic_key(item: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        _location(item),
        _norm(item.get("category")),
        _norm(item.get("symbol") or item.get("function") or item.get("component")),
        _family(item),
    )


def _criterion_key(value: Any) -> str:
    text = _norm(value)
    text = re.sub(r"\[method:[^\]]+\]", "", text)
    text = re.sub(r"\[target commit:[^\]]+\]", "", text)
    text = re.sub(r"\b[0-9a-f]{40}\b", "", text)
    return " ".join(text.split()).strip(" ;")


def _dedupe_criteria(values: Any) -> list[Any]:
    if isinstance(values, str):
        values = [part.strip() for part in values.split(";") if part.strip()]
    if not isinstance(values, list):
        return []
    selected: dict[str, Any] = {}
    for value in values:
        key = _criterion_key(value)
        if key and key not in selected:
            selected[key] = deepcopy(value)
    return list(selected.values())


def _quality(item: Mapping[str, Any]) -> tuple[int, int, int, str]:
    populated = sum(
        bool(_text(item.get(key)))
        for key in (
            "cost_of_inaction",
            "residual_risk",
            "recommendation",
            "owner_role",
            "business_impact",
            "evidence",
            "fact",
        )
    )
    mappings = sum(bool(item.get(key)) for key in ("roadmap", "roadmap_ids", "backlog", "backlog_id"))
    criteria = len(_dedupe_criteria(item.get("acceptance_criteria")))
    return populated, mappings, criteria, _finding_id(item)


def _merge_findings(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    preferred, other = (right, left) if _quality(right) > _quality(left) else (left, right)
    merged = deepcopy(dict(preferred))
    for key, value in other.items():
        if merged.get(key) in (None, "", [], {}):
            merged[key] = deepcopy(value)
    merged["acceptance_criteria"] = _dedupe_criteria(
        list(preferred.get("acceptance_criteria") or []) + list(other.get("acceptance_criteria") or [])
    )
    aliases = []
    for source in (preferred, other):
        aliases.extend(source.get("finding_aliases") or [])
        aliases.append(source.get("finding_id") or source.get("id"))
    merged["finding_aliases"] = list(dict.fromkeys(_text(value) for value in aliases if _text(value)))
    return merged


def _canonical_findings(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    selected: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str, str]] = []
    for raw in values:
        if not isinstance(raw, Mapping):
            continue
        item = deepcopy(dict(raw))
        item["acceptance_criteria"] = _dedupe_criteria(item.get("acceptance_criteria"))
        key = _semantic_key(item)
        if key not in selected:
            selected[key] = item
            order.append(key)
        else:
            selected[key] = _merge_findings(selected[key], item)
    return [selected[key] for key in order]


def _replace_nested_findings(value: Any, canonical_by_id: Mapping[str, Mapping[str, Any]]) -> Any:
    if isinstance(value, list):
        output = []
        seen: set[str] = set()
        for child in value:
            repaired = _replace_nested_findings(child, canonical_by_id)
            if isinstance(repaired, Mapping):
                finding_id = _finding_id(repaired)
                canonical = canonical_by_id.get(finding_id)
                repaired = deepcopy(dict(canonical or repaired))
                key = json.dumps(_semantic_key(repaired), separators=(",", ":")) if _location(repaired) else ""
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
            output.append(repaired)
        return output
    if not isinstance(value, Mapping):
        return value
    item = {key: _replace_nested_findings(child, canonical_by_id) for key, child in value.items()}
    finding_id = _finding_id(item)
    if finding_id and finding_id in canonical_by_id:
        return deepcopy(dict(canonical_by_id[finding_id]))
    if "acceptance_criteria" in item:
        item["acceptance_criteria"] = _dedupe_criteria(item.get("acceptance_criteria"))
    return item


def _normalized_filename(value: Any) -> str:
    filename = _text(value) or "nico-comprehensive-assessment.pdf"
    suffix = ".pdf" if filename.lower().endswith(".pdf") else ""
    stem = filename[:-4] if suffix else filename
    stem = re.sub(rf"(?:-{re.escape(_APPROVAL)})+\s*$", "", stem, flags=re.IGNORECASE)
    return f"{stem}-{_APPROVAL}{suffix or '.pdf'}"


def repair_client_delivery_package(package: Mapping[str, Any]) -> dict[str, Any]:
    payload = deepcopy(dict(package))
    report = deepcopy(dict(payload.get("json") or {})) if isinstance(payload.get("json"), Mapping) else {}
    source = []
    for key in _FINDING_SURFACES:
        values = report.get(key)
        if isinstance(values, list):
            source.extend(values)
    canonical = _canonical_findings(source)
    canonical_by_id: dict[str, Mapping[str, Any]] = {}
    for item in canonical:
        for alias in [_finding_id(item), *(item.get("finding_aliases") or [])]:
            if _text(alias):
                canonical_by_id[_text(alias)] = item

    report["canonical_findings"] = deepcopy(canonical)
    report["findings_register"] = deepcopy(canonical)
    report["findings"] = deepcopy(canonical)
    report["decision_grade_findings_register"] = deepcopy(canonical)
    report["executive_risk_register"] = deepcopy(canonical[:7])
    report["priority_findings"] = deepcopy(canonical[:5])
    for surface in ("executive_findings", "finding_cards", "roadmap", "backlog", "work_packages", "remediation_plan", "recommendations", "assessment", "stage_summaries"):
        if surface in report:
            report[surface] = _replace_nested_findings(report[surface], canonical_by_id)

    payload["json"] = report
    payload["canonical_findings"] = deepcopy(canonical)
    payload["findings_register"] = deepcopy(canonical)
    payload["pdf_filename"] = _normalized_filename(payload.get("pdf_filename"))
    if payload.get("spanish_pdf_filename"):
        payload["spanish_pdf_filename"] = _normalized_filename(payload.get("spanish_pdf_filename"))
    payload["canonical_truth_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
    payload["phase16_repair"] = {
        "version": VERSION,
        "semantic_duplicates_removed": True,
        "acceptance_criteria_deduplicated": True,
        "terminal_filename_normalized": True,
        "canonical_finding_count": len(canonical),
    }
    return payload


def _surface_titles(value: Any, output: dict[str, set[str]]) -> None:
    if isinstance(value, list):
        for item in value:
            _surface_titles(item, output)
        return
    if not isinstance(value, Mapping):
        return
    finding_id = _finding_id(value)
    title = _text(value.get("title") or value.get("decision_title"))
    if finding_id and title:
        output.setdefault(finding_id, set()).add(title)
    for child in value.values():
        _surface_titles(child, output)


def verify_client_delivery_package(package: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    payload = deepcopy(dict(package))
    report = payload.get("json") if isinstance(payload.get("json"), Mapping) else {}
    findings = report.get("canonical_findings") if isinstance(report.get("canonical_findings"), list) else []

    ids = [_finding_id(item) for item in findings if isinstance(item, Mapping)]
    populated_ids = [value for value in ids if value]
    if len(populated_ids) != len(set(populated_ids)):
        errors.append("canonical findings contain duplicate finding IDs")
    semantic = [_semantic_key(item) for item in findings if isinstance(item, Mapping)]
    if len(semantic) != len(set(semantic)):
        errors.append("canonical findings contain semantic duplicates")
    for item in findings:
        if isinstance(item, Mapping):
            criteria = item.get("acceptance_criteria") or []
            if isinstance(criteria, list) and len(criteria) != len({_criterion_key(value) for value in criteria if _criterion_key(value)}):
                errors.append(f"finding {_finding_id(item)} contains repeated acceptance criteria")

    canonical_titles = {
        _finding_id(item): _text(item.get("title") or item.get("decision_title"))
        for item in findings
        if isinstance(item, Mapping) and _finding_id(item)
    }
    observed: dict[str, set[str]] = {}
    for surface in ("executive_findings", "executive_risk_register", "priority_findings", "roadmap", "backlog", "work_packages", "remediation_plan", "recommendations"):
        if surface in report:
            _surface_titles(report[surface], observed)
    for finding_id, titles in observed.items():
        canonical_title = canonical_titles.get(finding_id)
        if canonical_title and titles != {canonical_title}:
            errors.append(f"finding {finding_id} is not title-consistent across client surfaces")

    filename = _text(payload.get("pdf_filename"))
    if not filename.lower().endswith(".pdf"):
        errors.append("client PDF filename is missing or invalid")
    if filename.upper().count(_APPROVAL) != 1:
        errors.append("client PDF filename must contain exactly one approval state")

    pdf_base64 = payload.get("pdf_base64")
    if pdf_base64:
        try:
            pdf_bytes = base64.b64decode(str(pdf_base64), validate=True)
            if not pdf_bytes.startswith(b"%PDF"):
                errors.append("client PDF payload does not have a PDF signature")
        except Exception:
            errors.append("client PDF payload is not valid base64")
    else:
        warnings.append("client PDF bytes were not available for signature verification")

    release_gate = payload.get("phase9_release_gate")
    if not isinstance(release_gate, Mapping) or release_gate.get("valid") is not True:
        errors.append("production report release gate is not valid")

    analyzer_report = payload.get("analyzer_evidence_report")
    if isinstance(analyzer_report, Mapping):
        analyzers = analyzer_report.get("analyzers")
        if isinstance(analyzers, list):
            scanner_names = [_text(item.get("scanner") or item.get("name")).casefold() for item in analyzers if isinstance(item, Mapping)]
            scanner_names = [name for name in scanner_names if name]
            if len(scanner_names) != len(set(scanner_names)):
                errors.append("analyzer evidence contains duplicate scanner records")

    truth_hash = _text(payload.get("canonical_truth_sha256"))
    if len(truth_hash) != 64:
        errors.append("canonical truth hash is missing or invalid")

    verification_material = {
        "canonical_truth_sha256": truth_hash,
        "pdf_filename": filename,
        "finding_ids": populated_ids,
        "errors": errors,
        "warnings": warnings,
    }
    fingerprint = hashlib.sha256(json.dumps(verification_material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "version": VERSION,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "canonical_finding_count": len(findings),
        "surface_reference_count": sum(len(values) for values in observed.values()),
        "pdf_signature_checked": bool(pdf_base64),
        "release_gate_verified": isinstance(release_gate, Mapping) and release_gate.get("valid") is True,
        "verification_fingerprint_sha256": fingerprint,
    }


def assert_client_delivery_package(package: Mapping[str, Any]) -> dict[str, Any]:
    result = verify_client_delivery_package(package)
    if not result["valid"]:
        raise ValueError("Phase 16 client-delivery verification failed: " + "; ".join(result["errors"]))
    return result


__all__ = ["VERSION", "repair_client_delivery_package", "verify_client_delivery_package", "assert_client_delivery_package"]
