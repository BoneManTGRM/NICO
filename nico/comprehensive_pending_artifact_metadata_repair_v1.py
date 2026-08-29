from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime
from typing import Any, Mapping

from nico.comprehensive_final_report_execution_boundary_v4 import FINAL_REPORT_STAGE_ID
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import _record_hash, validate_comprehensive_run_record

VERSION = "nico.comprehensive-pending-artifact-metadata-repair.v1"
_SHA256_LENGTH = 64


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _pending_unapproved_record(record: Mapping[str, Any]) -> bool:
    return bool(
        _text(record.get("status")).casefold() == "review_required"
        and record.get("terminal") is True
        and list(record.get("completed_stages") or []) == list(COMPREHENSIVE_STAGES)
        and _text(record.get("current_stage")) == "client_acceptance_pending"
        and float(record.get("progress_percent") or 0.0) == 100.0
        and record.get("human_review_required") is True
        and record.get("human_review_completed") is not True
        and record.get("client_delivery_allowed") is not True
        and not isinstance(record.get("accepted_edition"), Mapping)
        and not isinstance(record.get("approved_delivery_package"), Mapping)
        and not isinstance(record.get("delivery_authorization"), Mapping)
        and not isinstance(record.get("review_decision"), Mapping)
        and not isinstance(record.get("review_context"), Mapping)
        and not list(record.get("review_history") or [])
    )


def _successful_v2_review_boundary(
    stage_results: Mapping[str, Any],
    final_stage: Mapping[str, Any],
    package: Mapping[str, Any],
) -> bool:
    cross_format = stage_results.get("cross_format_truth_verification")
    human_review = stage_results.get("human_review_request")
    acceptance = stage_results.get("client_acceptance_pending")
    evidence = final_stage.get("evidence")
    final_truth = (
        cross_format.get("final_artifact_truth")
        if isinstance(cross_format, Mapping)
        else None
    )
    return bool(
        _text(final_stage.get("status")).casefold() == "complete"
        and isinstance(evidence, Mapping)
        and evidence.get("v2_single_source_pipeline") is True
        and evidence.get("final_artifact_generation_complete") is True
        and isinstance(cross_format, Mapping)
        and _text(cross_format.get("status")).casefold() == "complete"
        and not list(cross_format.get("failed_checks") or [])
        and isinstance(final_truth, Mapping)
        and _text(final_truth.get("status")).casefold() == "verified"
        and not list(final_truth.get("failed_checks") or [])
        and isinstance(human_review, Mapping)
        and _text(human_review.get("status")).casefold() == "complete"
        and isinstance(acceptance, Mapping)
        and _text(acceptance.get("status")).casefold() == "review_required"
        and package.get("human_review_required") is True
        and package.get("human_review_completed") is not True
        and package.get("client_delivery_allowed") is not True
        and _text(package.get("report_finality")).casefold() == "automated_draft"
        and "pending" in _text(package.get("approval_status")).casefold()
        and "blocked" in _text(package.get("delivery_status")).casefold()
    )


def repair_pending_findings_csv_alias(
    record: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Repair one known pre-approval V2 digest-alias defect without changing artifacts.

    A short-lived V2 publication revision retained the manifest-bound findings CSV but
    overwrote the legacy ``findings_csv_sha256`` and base64 alias with a second CSV
    serialization.  The public read boundary correctly rejected those packages.  This
    migration is deliberately narrow: the legacy alias must be internally consistent,
    the retained CSV must differ, and replacing only that redundant alias must make the
    complete strict exact-artifact predicate pass.  Unknown integrity failures, reviewed
    packages, and delivery-authorized packages remain untouched and fail closed.
    """

    validation = validate_comprehensive_run_record(record)
    if validation["status"] != "valid":
        raise ValueError("invalid_run_record:" + ",".join(validation["violations"]))
    if not _pending_unapproved_record(record):
        return record

    stage_results = record.get("stage_results")
    if not isinstance(stage_results, Mapping):
        return record
    final_stage = stage_results.get(FINAL_REPORT_STAGE_ID)
    if not isinstance(final_stage, Mapping):
        return record
    package = final_stage.get("report_package")
    if not isinstance(package, Mapping):
        return record
    if not _successful_v2_review_boundary(stage_results, final_stage, package):
        return record

    from nico.comprehensive_api_controller import (
        _canonical_final_report_outputs,
        _final_report_package_integrity_bound,
    )

    if _final_report_package_integrity_bound(package):
        return record

    retained_csv = package.get("findings_csv")
    legacy_base64 = package.get("findings_csv_base64")
    legacy_sha256 = _text(package.get("findings_csv_sha256")).casefold()
    if (
        not isinstance(retained_csv, str)
        or not retained_csv
        or not isinstance(legacy_base64, str)
        or not legacy_base64.strip()
        or len(legacy_sha256) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in legacy_sha256)
    ):
        return record

    try:
        legacy_bytes = base64.b64decode(legacy_base64.strip(), validate=True)
    except (TypeError, ValueError):
        return record
    if hashlib.sha256(legacy_bytes).hexdigest() != legacy_sha256:
        return record

    retained_bytes = retained_csv.encode("utf-8")
    retained_sha256 = hashlib.sha256(retained_bytes).hexdigest()
    if retained_sha256 == legacy_sha256 or retained_bytes == legacy_bytes:
        return record

    candidate_package = dict(package)
    candidate_package["findings_csv_base64"] = base64.b64encode(
        retained_bytes
    ).decode("ascii")
    candidate_package["findings_csv_sha256"] = retained_sha256

    if not _final_report_package_integrity_bound(candidate_package):
        return record

    candidate_record = dict(record)
    candidate_stage_results = dict(stage_results)
    candidate_final_stage = dict(final_stage)
    candidate_final_stage["report_package"] = candidate_package
    candidate_stage_results[FINAL_REPORT_STAGE_ID] = candidate_final_stage
    candidate_record["stage_results"] = candidate_stage_results
    projected_report, _assessment = _canonical_final_report_outputs(candidate_record)
    if projected_report is not candidate_package:
        return record

    updated = candidate_record
    updated_final_stage = candidate_final_stage
    updated_final_stage["report_package"] = candidate_package
    repaired_at = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    history = [
        dict(item)
        for item in updated.get("artifact_metadata_repair_history") or []
        if isinstance(item, Mapping)
    ]
    history.append(
        {
            "artifact_schema": VERSION,
            "repair": "legacy_findings_csv_alias_rebound_to_retained_manifest",
            "previous_findings_csv_sha256": legacy_sha256,
            "retained_findings_csv_sha256": retained_sha256,
            "retained_artifact_bytes_changed": False,
            "manifest_rebuilt": False,
            "repaired_fields": [
                "findings_csv_base64",
                "findings_csv_sha256",
            ],
            "exact_run_identity_preserved": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
            "repaired_at": repaired_at,
        }
    )
    updated["artifact_metadata_repair_history"] = history
    updated["updated_at"] = repaired_at
    updated["revision"] = int(updated.get("revision") or 0) + 1
    updated["human_review_required"] = True
    updated["human_review_completed"] = False
    updated["client_delivery_allowed"] = False
    updated["integrity_sha256"] = _record_hash(updated)

    final_validation = validate_comprehensive_run_record(updated)
    if final_validation["status"] != "valid":
        raise ValueError(
            "invalid_repaired_run_record:"
            + ",".join(final_validation["violations"])
        )
    return updated


__all__ = ["VERSION", "repair_pending_findings_csv_alias"]
