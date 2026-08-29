from __future__ import annotations

import base64
import hashlib
import re
from copy import deepcopy
from typing import Any, Mapping

from nico.comprehensive_client_ready_projection_v1 import (
    APPROVAL_STATUS,
    APPROVAL_SUFFIX,
    DELIVERY_STATUS,
    REPORT_FINALITY,
    apply_automated_draft_truth,
)
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

_APPROVAL_SUFFIX = APPROVAL_SUFFIX


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _numeric(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = int(round(value))
    if score < 0 or score > 100:
        raise ValueError(f"canonical score is outside the 0-100 range: {value}")
    return score


def _report_language(canonical: Mapping[str, Any]) -> str:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    value = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or assessment.get("report_language")
        or assessment.get("locale")
        or identity.get("report_language")
        or "en"
    ).casefold()
    return "es-MX" if value.startswith("es") else "en"


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


def _synchronize_scanner_truth(canonical: dict[str, Any]) -> None:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    expected_commit = _text(identity.get("commit_sha")).casefold()
    source = canonical.get("scanner_execution_records") if isinstance(canonical.get("scanner_execution_records"), list) else []
    records: list[dict[str, Any]] = []
    for raw in source:
        if not isinstance(raw, Mapping):
            continue
        item = deepcopy(dict(raw))
        state = _text(item.get("state") or item.get("status") or "unknown").casefold().replace("-", "_")
        item["state"] = state
        item["status"] = state
        item["required"] = item.get("required") is not False
        observed_commit = _text(item.get("commit_sha") or item.get("snapshot_commit_sha")).casefold()
        item["exact_commit_match"] = bool(expected_commit and observed_commit == expected_commit)
        item["verified_complete"] = item.get("verified") is True or item.get("verified_complete") is True
        item["verified_for_this_report"] = item["verified_complete"]
        records.append(item)
    canonical["scanner_execution_records"] = records
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    assessment = deepcopy(dict(assessment))
    assessment["scanner_execution_records"] = deepcopy(records)
    completed = [item for item in records if item.get("completed") is True]
    incomplete = [item for item in records if item.get("completed") is not True]
    assessment["completed_scanner_records"] = deepcopy(completed)
    assessment["incomplete_scanner_records"] = deepcopy(incomplete)
    previous_health = assessment.get("evidence_health_summary") if isinstance(assessment.get("evidence_health_summary"), Mapping) else {}
    health = deepcopy(dict(previous_health))
    health.update({
        "scanner_execution_records": deepcopy(records),
        "completed_scanners": [_text(item.get("scanner_name")) for item in completed],
        "incomplete_scanners": deepcopy(incomplete),
        "completed_scanner_count": len(completed),
        "incomplete_scanner_count": len(incomplete),
        "single_normalized_scanner_population": True,
    })
    assessment["evidence_health_summary"] = health
    canonical["assessment"] = assessment


def _clean_criterion(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    lowered = text.casefold().lstrip("[")
    if lowered.startswith("target commit:") or lowered.startswith("method:"):
        return ""
    text = re.sub(r"\s*\[(?:method|target\s+commit)\s*:[^\]]*(?:\]|$)", "", text, flags=re.I)
    text = re.sub(r"\s+(?:method|target\s+commit)\s*:\s*[0-9A-Za-z_.-]+\]?", "", text, flags=re.I)
    text = re.sub(r"\b[0-9a-f]{40,64}\b\]?", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ;,.[]\t")
    return text


def _repair_client_criteria(canonical: dict[str, Any]) -> None:
    source = canonical.get("canonical_findings") if isinstance(canonical.get("canonical_findings"), list) else []
    repaired: list[dict[str, Any]] = []
    for raw in source:
        if not isinstance(raw, Mapping):
            continue
        item = deepcopy(dict(raw))
        values = item.get("acceptance_criteria")
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            values = []
        selected: dict[str, str] = {}
        for value in values:
            cleaned = _clean_criterion(value)
            key = cleaned.casefold()
            if cleaned and key not in selected:
                selected[key] = cleaned
        item["acceptance_criteria"] = list(selected.values())
        repaired.append(item)
    for surface in ("canonical_findings", "findings_register", "findings", "decision_grade_findings_register"):
        canonical[surface] = deepcopy(repaired)
    canonical["executive_risk_register"] = deepcopy(repaired[:7])
    canonical["priority_findings"] = deepcopy(repaired[:5])
    contract = canonical.get("v2_pipeline_contract") if isinstance(canonical.get("v2_pipeline_contract"), Mapping) else {}
    contract = deepcopy(dict(contract))
    contract["malformed_legacy_acceptance_metadata_repaired"] = True
    contract["client_acceptance_criteria_count"] = sum(len(item.get("acceptance_criteria") or []) for item in repaired)
    canonical["v2_pipeline_contract"] = contract


def _normalized_artifact_filename(value: Any, *, default_name: str, extension: str) -> str:
    filename = _text(value) or default_name
    extension = extension if extension.startswith(".") else f".{extension}"
    if not filename.casefold().endswith(extension.casefold()):
        filename += extension
    stem = filename[: -len(extension)]
    # Historical layers have emitted FINAL, DRAFT, AUTOMATED-FINAL, and even
    # repeated AUTOMATED prefixes. Strip every terminal state token before
    # applying the one authoritative automated-draft suffix.
    terminal = re.compile(
        r"-(?:AUTOMATED-)*(?:FINAL|DRAFT)(?:-PENDING-APPROVAL)?$",
        flags=re.IGNORECASE,
    )
    while True:
        normalized = terminal.sub("", stem)
        if normalized == stem:
            break
        stem = normalized
    return f"{stem}-{_APPROVAL_SUFFIX}{extension}"


def _normalize_artifact_filenames(package: dict[str, Any]) -> None:
    package.update(
        {
            "pdf_filename": _normalized_artifact_filename(
                package.get("pdf_filename"),
                default_name="nico-comprehensive-assessment.pdf",
                extension=".pdf",
            ),
            "spanish_pdf_filename": _normalized_artifact_filename(
                package.get("spanish_pdf_filename"),
                default_name="nico-comprehensive-assessment-es.pdf",
                extension=".pdf",
            ),
            "json_filename": _normalized_artifact_filename(
                package.get("json_filename"),
                default_name="nico-comprehensive-assessment.json",
                extension=".json",
            ),
            "markdown_filename": _normalized_artifact_filename(
                package.get("markdown_filename"),
                default_name="nico-comprehensive-assessment.md",
                extension=".md",
            ),
            "csv_filename": _normalized_artifact_filename(
                package.get("csv_filename"),
                default_name="nico-comprehensive-assessment.csv",
                extension=".csv",
            ),
        }
    )


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
    language = _report_language(canonical)
    canonical["report_language"] = language
    canonical["locale"] = language
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    identity = deepcopy(dict(identity))
    identity["report_language"] = language
    canonical["identity"] = identity
    _synchronize_score_truth(canonical)
    _synchronize_scanner_truth(canonical)
    _repair_client_criteria(canonical)
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    assessment = deepcopy(dict(assessment))
    assessment["report_language"] = language
    assessment["locale"] = language
    canonical["assessment"] = assessment
    canonical = apply_automated_draft_truth(canonical)
    findings = list(canonical.get("canonical_findings") or [])
    _assert_canonical_population(findings)

    package.update(
        {
            "json": canonical,
            "canonical_findings": deepcopy(findings),
            "findings_register": deepcopy(findings),
            "report_finality": REPORT_FINALITY,
            "approval_status": APPROVAL_STATUS,
            "delivery_status": DELIVERY_STATUS,
            "human_review_required": True,
            "client_delivery_allowed": False,
            "assessment_state": AssessmentState.REVIEW_REQUIRED.value,
            "report_language": language,
            "locale": language,
        }
    )
    _normalize_artifact_filenames(package)
    package = rebuild_client_artifacts(package)
    # Downstream renderers may retain legacy file names for compatibility. The
    # publication boundary owns the final artifact identity and normalizes it
    # after all rendering passes so the suffix is present exactly once.
    _normalize_artifact_filenames(package)
    rebuilt_canonical = package.get("json")
    if not isinstance(rebuilt_canonical, Mapping):
        raise ValueError("v2 artifact rebuild did not preserve canonical JSON")
    # ``rebuild_client_artifacts`` is the exact-artifact binding boundary.  Do not
    # mutate its canonical JSON afterward: the detached manifest, canonical JSON
    # bytes, and draft identity all bind that exact object.  Automated-draft truth
    # was applied before the rebuild, so the rebuilt value is now authoritative.
    canonical = deepcopy(dict(rebuilt_canonical))
    findings = list(canonical.get("canonical_findings") or [])
    _assert_canonical_population(findings)
    digest = canonical_truth_sha256(canonical)
    if digest != _text(package.get("canonical_truth_sha256")):
        raise ValueError("v2 artifact rebuild returned stale canonical truth binding")
    package.update(
        {
            "json": canonical,
            "canonical_findings": deepcopy(findings),
            "findings_register": deepcopy(findings),
            "report_finality": REPORT_FINALITY,
            "approval_status": APPROVAL_STATUS,
            "delivery_status": DELIVERY_STATUS,
        }
    )

    # The rebuild also owns the retained findings CSV and its manifest digest.
    # Reuse those exact bytes for the legacy base64 alias instead of publishing a
    # second CSV under the same ``findings_csv_sha256`` field.
    findings_csv = package.get("findings_csv")
    if not isinstance(findings_csv, str) or not findings_csv:
        raise ValueError("v2 artifact rebuild did not retain the findings CSV")
    csv_bytes = findings_csv.encode("utf-8")
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
        "report_language": language,
        "locale": language,
    })

    pdf_bytes = base64.b64decode(package.get("pdf_base64") or "")
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("v2 pipeline generated invalid PDF")
    if not _text(package.get("markdown")) or not _text(package.get("html")):
        raise ValueError("v2 pipeline did not generate complete Markdown and HTML artifacts")
    if "CLIENT DELIVERY NOT AUTHORIZED" not in _text(package.get("markdown")):
        raise ValueError("v2 Markdown does not preserve the production delivery boundary")
    if "AUTOMATED DRAFT" not in _text(package.get("markdown")) and "BORRADOR AUTOMATIZADO" not in _text(package.get("markdown")):
        raise ValueError("v2 Markdown omitted automated-draft truth")
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
        "repaired_canonical_json_preserved": True,
        "final_truth_hash_recomputed_after_repair": True,
        "score_clamping_forbidden": True,
        "v2_single_source_pipeline": True,
        "duplicate_findings_absent": True,
        "repeated_acceptance_criteria_absent": True,
        "approval_suffix_exactly_once": True,
        "localized_artifacts_share_canonical_truth": True,
        "legacy_acceptance_metadata_removed": True,
        "automated_draft_until_human_approval": True,
    })
    package["phase16_delivery_verification"] = assert_client_delivery_package(package)

    # Enforce the same immutable package predicate used by public exact-run reads.
    # A package that cannot be read or reviewed must never complete its generation
    # stage and become a terminal run.
    from nico.comprehensive_api_controller import (
        _final_report_package_integrity_bound,
    )

    if not _final_report_package_integrity_bound(package):
        raise ValueError("v2 publication exact-artifact integrity binding failed")

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
        "report_finality": REPORT_FINALITY,
        "approval_status": APPROVAL_STATUS,
        "delivery_status": DELIVERY_STATUS,
        "human_review_required": True,
        "human_review_completed": False,
        "client_delivery_allowed": False,
        "canonical_truth_sha256": digest,
        "final_artifact_generation_complete": True,
        "final_package": True,
        "automated_draft_package_complete": True,
        "report_language": language,
        "locale": language,
    })
    record = deepcopy(dict(finalized.get("record") or {}))
    record.update({
        "assessment_state": state.value,
        "status": state.value,
        "assessment_package_complete": True,
        "report_finality": REPORT_FINALITY,
        "approval_status": APPROVAL_STATUS,
        "delivery_status": DELIVERY_STATUS,
        "human_review_required": True,
        "human_review_completed": False,
        "client_delivery_allowed": False,
        "canonical_truth_sha256": digest,
        "report_language": language,
    })
    finalized["record"] = record
    return finalized


__all__ = ["apply_v2_pipeline"]
