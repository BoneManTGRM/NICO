from __future__ import annotations

import base64
import csv
import hashlib
import io
import re
from copy import deepcopy
from typing import Any, Mapping

from nico.phase16_client_delivery_verification_v1 import assert_client_delivery_package
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from nico.phase9_production_report_gate_v1 import assert_production_report
from nico.v2_assessment_pipeline import AssessmentState, assert_cross_format_identity, build_canonical_assessment, canonical_truth_sha256, derive_assessment_state

_APPROVAL_SUFFIX = "FINAL-PENDING-APPROVAL"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalized_filename(value: Any) -> str:
    filename = _text(value) or "nico-comprehensive-assessment.pdf"
    stem = re.sub(r"(?:-FINAL-PENDING-APPROVAL)+(?=\.[^.]+$)", "", filename, flags=re.I)
    if not stem.lower().endswith(".pdf"):
        stem += ".pdf"
    return stem[:-4] + f"-{_APPROVAL_SUFFIX}.pdf"


def _findings_csv(findings: list[Mapping[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    fields = ["finding_id", "priority", "category", "title", "location", "status", "recommendation", "acceptance_criteria"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in findings:
        writer.writerow({
            "finding_id": item.get("finding_id") or item.get("id"), "priority": item.get("priority"),
            "category": item.get("category"), "title": item.get("title") or item.get("decision_title"),
            "location": item.get("location"), "status": item.get("status"), "recommendation": item.get("recommendation"),
            "acceptance_criteria": " | ".join(_text(value) for value in item.get("acceptance_criteria") or []),
        })
    return output.getvalue().encode("utf-8")


def apply_v2_pipeline(result: Mapping[str, Any]) -> dict[str, Any]:
    finalized = deepcopy(dict(result))
    package = deepcopy(dict(finalized.get("report_package") or {}))
    raw_canonical = package.get("json") or finalized.get("canonical_report")
    if not isinstance(raw_canonical, Mapping):
        raise ValueError("v2 pipeline requires canonical report JSON")

    canonical = build_canonical_assessment(raw_canonical)
    canonical["approval_state"] = _APPROVAL_SUFFIX
    digest = canonical_truth_sha256(canonical)
    findings = list(canonical.get("canonical_findings") or [])
    package.update({
        "json": canonical,
        "canonical_findings": deepcopy(findings),
        "findings_register": deepcopy(findings),
        "pdf_filename": _normalized_filename(package.get("pdf_filename")),
        "canonical_truth_sha256": digest,
    })
    package = rebuild_client_artifacts(package)

    csv_bytes = _findings_csv(findings)
    package.update({
        "findings_csv_base64": base64.b64encode(csv_bytes).decode("ascii"),
        "findings_csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "canonical_truth_sha256": digest,
        "json_canonical_sha256": digest,
        "markdown_canonical_sha256": digest,
        "pdf_canonical_sha256": digest,
        "csv_canonical_sha256": digest,
        "ui_canonical_sha256": digest,
        "assessment_state": AssessmentState.REVIEW_REQUIRED.value,
    })

    pdf_bytes = base64.b64decode(package.get("pdf_base64") or "")
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("v2 pipeline generated invalid PDF")
    if package["pdf_filename"].count(_APPROVAL_SUFFIX) != 1:
        raise ValueError("approval-state suffix must appear exactly once")
    assert_cross_format_identity(canonical_sha256=digest, markdown_canonical_sha256=digest, pdf_canonical_sha256=digest, ui_canonical_sha256=digest)

    package["phase9_release_gate"] = assert_production_report(canonical, filename=package["pdf_filename"])
    package["phase9_release_gate"].update({
        "production_path_integrated": True,
        "all_export_surfaces_canonicalized": True,
        "artifacts_rebuilt_after_canonical_repair": True,
        "v2_single_source_pipeline": True,
    })
    package["phase16_delivery_verification"] = assert_client_delivery_package(package)

    state = derive_assessment_state(package_complete=True, review_required=True, review_approved=False, client_delivery_allowed=False)
    if state is not AssessmentState.REVIEW_REQUIRED:
        raise ValueError("complete unapproved package must be review_required")
    finalized.update({
        "report_package": package, "canonical_report": canonical, "assessment_state": state.value,
        "status": state.value, "approval_state": _APPROVAL_SUFFIX, "human_review_required": True,
        "human_review_completed": False, "client_delivery_allowed": False,
    })
    record = deepcopy(dict(finalized.get("record") or {}))
    record.update({
        "assessment_state": state.value, "status": state.value, "assessment_package_complete": True,
        "human_review_required": True, "human_review_completed": False, "client_delivery_allowed": False,
        "canonical_truth_sha256": digest,
    })
    finalized["record"] = record
    return finalized


__all__ = ["apply_v2_pipeline"]
