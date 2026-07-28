from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from nico.final_assessment_truth_v1 import ReportStatus, TruthViolation
from nico.report_package_release_verifier_v1 import verify_report_package

VERSION = "nico.phase8_operational_acceptance.v1"


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_scanner_ledger(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_revision: str,
    required_scanners: Sequence[str],
) -> dict[str, Any]:
    by_name = {str(item.get("scanner") or item.get("tool") or "").casefold(): dict(item) for item in records}
    failures: list[str] = []
    normalized: list[dict[str, Any]] = []
    for scanner in required_scanners:
        key = scanner.casefold()
        record = by_name.get(key)
        if not record:
            failures.append(f"missing:{scanner}")
            continue
        revision = str(record.get("commit_sha") or record.get("assessed_revision") or "")
        status = str(record.get("status") or "").casefold()
        artifact_hash = str(record.get("artifact_sha256") or "")
        command = str(record.get("command") or "")
        version = str(record.get("version") or "")
        exit_code = record.get("exit_code")
        if revision != expected_revision:
            failures.append(f"revision_mismatch:{scanner}")
        if status not in {"completed", "success", "not_applicable"}:
            failures.append(f"incomplete:{scanner}:{status or 'unknown'}")
        if status != "not_applicable" and exit_code != 0:
            failures.append(f"exit_code:{scanner}:{exit_code}")
        if status != "not_applicable" and not artifact_hash:
            failures.append(f"missing_artifact_hash:{scanner}")
        if not command or not version:
            failures.append(f"missing_execution_identity:{scanner}")
        normalized.append(record)
    if failures:
        raise TruthViolation("Scanner ledger is not release-complete: " + ", ".join(sorted(failures)))
    return {
        "valid": True,
        "expected_revision": expected_revision,
        "required_scanners": sorted(required_scanners),
        "records": normalized,
        "ledger_sha256": _digest(normalized),
    }


def validate_pdf_review(review: Mapping[str, Any]) -> dict[str, Any]:
    page_count = int(review.get("page_count") or 0)
    blank_pages = list(review.get("blank_pages") or [])
    overflow_pages = list(review.get("overflow_pages") or [])
    clipped_pages = list(review.get("clipped_pages") or [])
    reviewer = str(review.get("reviewer") or "").strip()
    status = str(review.get("status") or "").casefold()
    if page_count <= 0:
        raise TruthViolation("PDF review did not retain a positive page count")
    if blank_pages or overflow_pages or clipped_pages:
        raise TruthViolation(
            f"PDF visual review failed: blank={blank_pages}, overflow={overflow_pages}, clipped={clipped_pages}"
        )
    if status != "approved" or not reviewer:
        raise TruthViolation("PDF visual review requires an identified human reviewer and approved status")
    result = {
        "page_count": page_count,
        "blank_pages": blank_pages,
        "overflow_pages": overflow_pages,
        "clipped_pages": clipped_pages,
        "reviewer": reviewer,
        "status": status,
    }
    result["review_sha256"] = _digest(result)
    return result


def build_operational_acceptance(
    *,
    assessment: Mapping[str, Any],
    english: Mapping[str, Any],
    spanish: Mapping[str, Any],
    surfaces: Mapping[str, Mapping[str, Any]],
    artifact_paths: Mapping[str, str],
    scanner_records: Sequence[Mapping[str, Any]],
    required_scanners: Sequence[str],
    pdf_review: Mapping[str, Any],
) -> dict[str, Any]:
    identity = assessment.get("assessment_identity") or {}
    revision = str(identity.get("immutable_revision") or identity.get("commit_sha") or "")
    if not revision:
        raise TruthViolation("Operational acceptance requires an immutable assessed revision")
    approval_state = str(assessment.get("approval_state") or "")
    if approval_state not in {ReportStatus.FINAL_PENDING_APPROVAL.value, ReportStatus.APPROVED.value}:
        raise TruthViolation(f"Unsupported report approval state: {approval_state}")

    package = verify_report_package(
        assessment=assessment,
        english=english,
        spanish=spanish,
        surfaces=surfaces,
        artifact_paths=artifact_paths,
    )
    scanner = validate_scanner_ledger(
        scanner_records,
        expected_revision=revision,
        required_scanners=required_scanners,
    )
    visual = validate_pdf_review(pdf_review)

    artifacts = package.get("artifacts") or []
    manifest = {
        "version": VERSION,
        "repository": identity.get("repository"),
        "immutable_revision": revision,
        "truth_sha256": assessment.get("truth_sha256"),
        "report_artifacts": artifacts,
        "scanner_ledger_sha256": scanner["ledger_sha256"],
        "pdf_review_sha256": visual["review_sha256"],
    }
    manifest["manifest_sha256"] = _digest(manifest)
    client_delivery_allowed = approval_state == ReportStatus.APPROVED.value
    return {
        "version": VERSION,
        "valid": True,
        "client_delivery_allowed": client_delivery_allowed,
        "package": package,
        "scanner_ledger": scanner,
        "pdf_review": visual,
        "manifest": manifest,
    }


__all__ = [
    "build_operational_acceptance",
    "validate_pdf_review",
    "validate_scanner_ledger",
]
