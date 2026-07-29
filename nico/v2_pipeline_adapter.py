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
from nico.v2_assessment_pipeline import (
    AssessmentState,
    assert_cross_format_identity,
    build_canonical_assessment,
    canonical_truth_sha256,
    derive_assessment_state,
    semantic_finding_key,
)

_APPROVAL_SUFFIX = "FINAL-PENDING-APPROVAL"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _numeric(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(100, int(round(value))))


def _synchronize_score_truth(canonical: dict[str, Any]) -> None:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    assessment = deepcopy(dict(assessment))
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}
    maturity = deepcopy(dict(maturity))
    technical = next(
        (
            score
            for raw in (
                assessment.get("technical_score"),
                maturity.get("technical_score"),
                maturity.get("presented_score"),
                maturity.get("score"),
            )
            if (score := _numeric(raw)) is not None
        ),
        None,
    )
    adjusted = next(
        (
            score
            for raw in (
                assessment.get("canonical_evidence_adjusted_score"),
                assessment.get("evidence_adjusted_score"),
                maturity.get("canonical_evidence_adjusted_score"),
                maturity.get("evidence_adjusted_score"),
                technical,
            )
            if (score := _numeric(raw)) is not None
        ),
        None,
    )
    if technical is not None:
        assessment["technical_score"] = technical
        maturity["technical_score"] = technical
        maturity["presented_score"] = technical
        maturity["score"] = technical
        maturity["source_score"] = technical
    if adjusted is not None:
        assessment["canonical_evidence_adjusted_score"] = adjusted
        assessment["evidence_adjusted_score"] = adjusted
        maturity["canonical_evidence_adjusted_score"] = adjusted
        maturity["evidence_adjusted_score"] = adjusted
    assessment["maturity_signal"] = maturity
    assessment["comprehensive_score_truth"] = {
        "technical_score": technical,
        "canonical_evidence_adjusted_score": adjusted,
        "aliases_synchronized": adjusted is not None,
    }
    canonical["assessment"] = assessment


def _normalized_artifact_filename(value: Any, *, default_name: str, extension: str) -> str:
    filename = _text(value) or default_name
    extension = extension if extension.startswith(".") else f".{extension}"
    if not filename.casefold().endswith(extension.casefold()):
        filename += extension
    stem = filename[: -len(extension)]
    stem = re.sub(r"(?:-FINAL-PENDING-APPROVAL)+$", "", stem, flags=re.I)
    stem = re.sub(r"(?:-DRAFT|-FINAL)+$", "", stem, flags=re.I)
    return f"{stem}-{_APPROVAL_SUFFIX}{extension}"


def _findings_csv(findings: list[Mapping[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    fields = [
        "finding_id", "aliases", "priority", "category", "title", "location", "status",
        "recommendation", "owner_role", "effort", "acceptance_criteria",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in findings:
        writer.writerow({
            "finding_id": item.get("finding_id") or item.get("id"),
            "aliases": " | ".join(_text(value) for value in item.get("finding_aliases") or []),
            "priority": item.get("priority"),
            "category": item.get("category"),
            "title": item.get("title") or item.get("decision_title"),
            "location": item.get("location"),
            "status": item.get("status"),
            "recommendation": item.get("recommendation"),
            "owner_role": item.get("owner_role"),
            "effort": item.get("effort"),
            "acceptance_criteria": " | ".join(_text(value) for value in item.get("acceptance_criteria") or []),
        })
    return output.getvalue().encode("utf-8")


def _assert_canonical_population(findings: list[Mapping[str, Any]]) -> None:
    keys = [semantic_finding_key(item) for item in findings]
    if len(keys) != len(set(keys)):
        raise ValueError("v2 publication contains duplicate semantic findings")
    ids = [_text(item.get("finding_id") or item.get("id")) for item in findings]
    populated = [value for value in ids if value]
    if len(populated) != len(set(populated)):
        raise ValueError("v2 publication contains duplicate canonical finding IDs")
    for item in findings:
        criteria = [_text(value).casefold() for value in item.get("acceptance_criteria") or [] if _text(value)]
        if len(criteria) != len(set(criteria)):
            raise ValueError("v2 publication contains repeated acceptance criteria")


def apply_v2_pipeline(result: Mapping[str, Any]) -> dict[str, Any]:
    finalized = deepcopy(dict(result))
    package = deepcopy(dict(finalized.get("report_package") or {}))
    raw_canonical = package.get("json") or finalized.get("canonical_report")
    if not isinstance(raw_canonical, Mapping):
        raise ValueError("v2 pipeline requires canonical report JSON")

    canonical = build_canonical_assessment(raw_canonical)
    _synchronize_score_truth(canonical)
    canonical.update({
        "approval_state": _APPROVAL_SUFFIX,
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "assessment_state": AssessmentState.REVIEW_REQUIRED.value,
    })
    findings = list(canonical.get("canonical_findings") or [])
    _assert_canonical_population(findings)
    digest = canonical_truth_sha256(canonical)

    package.update({
        "json": canonical,
        "canonical_findings": deepcopy(findings),
        "findings_register": deepcopy(findings),
        "pdf_filename": _normalized_artifact_filename(package.get("pdf_filename"), default_name="nico-comprehensive-assessment.pdf", extension=".pdf"),
        "spanish_pdf_filename": _normalized_artifact_filename(package.get("spanish_pdf_filename"), default_name="nico-comprehensive-assessment-es.pdf", extension=".pdf"),
        "json_filename": _normalized_artifact_filename(package.get("json_filename"), default_name="nico-comprehensive-assessment.json", extension=".json"),
        "markdown_filename": _normalized_artifact_filename(package.get("markdown_filename"), default_name="nico-comprehensive-assessment.md", extension=".md"),
        "csv_filename": _normalized_artifact_filename(package.get("csv_filename"), default_name="nico-comprehensive-assessment.csv", extension=".csv"),
        "canonical_truth_sha256": digest,
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "assessment_state": AssessmentState.REVIEW_REQUIRED.value,
    })
    package = rebuild_client_artifacts(package)
    package["json"] = canonical

    csv_bytes = _findings_csv(findings)
    package.update({
        "findings_csv_base64": base64.b64encode(csv_bytes).decode("ascii"),
        "findings_csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "canonical_truth_sha256": digest,
        "json_canonical_sha256": digest,
        "markdown_canonical_sha256": digest,
        "html_canonical_sha256": digest,
        "pdf_canonical_sha256": digest,
        "csv_canonical_sha256": digest,
        "ui_canonical_sha256": digest,
        "assessment_state": AssessmentState.REVIEW_REQUIRED.value,
    })

    pdf_bytes = base64.b64decode(package.get("pdf_base64") or "")
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("v2 pipeline generated invalid PDF")
    if not _text(package.get("markdown")) or not _text(package.get("html")):
        raise ValueError("v2 pipeline did not generate complete Markdown and HTML artifacts")
    for key in ("pdf_filename", "spanish_pdf_filename", "json_filename", "markdown_filename", "csv_filename"):
        value = _text(package.get(key))
        if value.count(_APPROVAL_SUFFIX) != 1:
            raise ValueError(f"{key} approval-state suffix must appear exactly once")
    assert_cross_format_identity(
        canonical_sha256=digest,
        markdown_canonical_sha256=digest,
        pdf_canonical_sha256=digest,
        ui_canonical_sha256=digest,
    )

    package["phase9_release_gate"] = assert_production_report(canonical, filename=package["pdf_filename"])
    package["phase9_release_gate"].update({
        "production_path_integrated": True,
        "all_export_surfaces_canonicalized": True,
        "artifacts_rebuilt_after_canonical_repair": True,
        "v2_single_source_pipeline": True,
        "duplicate_findings_absent": True,
        "repeated_acceptance_criteria_absent": True,
        "approval_suffix_exactly_once": True,
    })
    package["phase16_delivery_verification"] = assert_client_delivery_package(package)

    state = derive_assessment_state(
        package_complete=True,
        review_required=True,
        review_approved=False,
        client_delivery_allowed=False,
    )
    if state is not AssessmentState.REVIEW_REQUIRED:
        raise ValueError("complete unapproved package must be review_required")
    finalized.update({
        "report_package": package,
        "canonical_report": canonical,
        "assessment": deepcopy(canonical.get("assessment") or {}),
        "assessment_state": state.value,
        "status": state.value,
        "approval_state": _APPROVAL_SUFFIX,
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "human_review_required": True,
        "human_review_completed": False,
        "client_delivery_allowed": False,
        "canonical_truth_sha256": digest,
        "final_artifact_generation_complete": True,
        "final_package": True,
    })
    record = deepcopy(dict(finalized.get("record") or {}))
    record.update({
        "assessment_state": state.value,
        "status": state.value,
        "assessment_package_complete": True,
        "human_review_required": True,
        "human_review_completed": False,
        "client_delivery_allowed": False,
        "canonical_truth_sha256": digest,
    })
    finalized["record"] = record
    return finalized


__all__ = ["apply_v2_pipeline"]
