from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.phase16.client-delivery-verification.v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _finding_id(item: Mapping[str, Any]) -> str:
    return _text(item.get("finding_id") or item.get("id"))


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

    canonical_titles = {
        _finding_id(item): _text(item.get("title") or item.get("decision_title"))
        for item in findings
        if isinstance(item, Mapping) and _finding_id(item)
    }
    observed: dict[str, set[str]] = {}
    for surface in (
        "executive_findings",
        "executive_risk_register",
        "priority_findings",
        "roadmap",
        "backlog",
        "work_packages",
        "remediation_plan",
        "recommendations",
    ):
        if surface in report:
            _surface_titles(report[surface], observed)
    for finding_id, titles in observed.items():
        canonical_title = canonical_titles.get(finding_id)
        if canonical_title and titles != {canonical_title}:
            errors.append(f"finding {finding_id} is not title-consistent across client surfaces")

    filename = _text(payload.get("pdf_filename"))
    if not filename.lower().endswith(".pdf"):
        errors.append("client PDF filename is missing or invalid")
    if filename.count("FINAL-PENDING-APPROVAL") > 1:
        errors.append("client PDF filename contains a duplicated approval state")

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
            scanner_names = [
                _text(item.get("scanner") or item.get("name")).casefold()
                for item in analyzers
                if isinstance(item, Mapping)
            ]
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
    fingerprint = hashlib.sha256(
        json.dumps(verification_material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

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


__all__ = ["VERSION", "verify_client_delivery_package", "assert_client_delivery_package"]
