from __future__ import annotations

import base64
import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Mapping

from nico.comprehensive_client_delivery_contract_v1 import (
    canonical_sha256,
    reviewer_binding,
)
from nico.comprehensive_engagement_metadata_v1 import (
    build_comprehensive_engagement_metadata,
    verify_comprehensive_engagement_metadata,
)
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_report_package import _canonical_hash as _legacy_canonical_hash
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.decision_grade_accepted_edition_guard_v1 import validate_accepted_edition

VERSION = "nico.comprehensive_api_controller.v8"
MAX_PROJECTED_STRING_CHARS = 1_200
MAX_PROJECTED_LIST_ITEMS = 24
MAX_PROJECTED_OBJECT_ITEMS = 24
MAX_PROJECTED_DEPTH = 2

_OMITTED_STAGE_KEYS = {
    "assessment",
    "report_package",
    "reports",
    "pdf_base64",
    "markdown",
    "markdown_sha256",
    "html",
    "html_sha256",
    "raw_evidence",
    "raw_evidence_json",
    "scanner_outputs",
    "scanner_outputs_json",
    "evidence_artifact_bundle",
    "evidence_bundle_json",
    "evidence_ledger_json",
}
_FINAL_REPORT_STAGE_ID = "final_comprehensive_report_generation"
_FINAL_REPORT_STAGE_SUCCESS_STATUSES = {
    "complete",
    "completed",
    "passed",
    "review_required",
    "success",
    "succeeded",
}
_FINAL_REPORT_RUN_STATUSES = {
    "complete",
    "completed",
    "review_required",
    "approved",
    "rejected",
    "declined",
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_MANIFEST_FAMILY_FIELDS = (
    "artifact_manifest",
    "evidence_manifest_json",
    "evidence_manifest_sha256",
    "canonical_json",
    "canonical_json_sha256",
    "draft_artifact_identity",
)
_REPORT_KEYS = (
    "service_id",
    "report_id",
    "markdown",
    "markdown_sha256",
    "html",
    "html_sha256",
    "pdf_base64",
    "pdf_filename",
    "pdf_error",
    "pdf_sha256",
    "canonical_truth_sha256",
    "canonical_json",
    "canonical_json_sha256",
    "findings_csv",
    "findings_csv_sha256",
    "evidence_csv",
    "evidence_csv_sha256",
    "candidate_register_json",
    "candidate_register_sha256",
    "remediation_backlog_json",
    "remediation_backlog_sha256",
    "artifact_manifest",
    "evidence_manifest_json",
    "evidence_manifest_sha256",
    "draft_artifact_identity",
)
_REPORT_MANIFEST_KEYS = (
    "service_id",
    "report_id",
    "report_language",
    "locale",
    "generated_at",
    "generation_timestamp",
    "pdf_filename",
    "pdf_error",
    "pdf_sha256",
    "canonical_truth_sha256",
    "assessment_state",
    "report_finality",
    "approval_status",
    "delivery_status",
    "artifact_delivery",
)


def _ordered_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow canonical-order view without cloning large stage payloads."""

    ordered_record = dict(record)
    raw_results = record.get("stage_results")
    if not isinstance(raw_results, dict):
        ordered_record["stage_results"] = {}
        return ordered_record

    ordered_results: dict[str, Any] = {}
    for stage_id in COMPREHENSIVE_STAGES:
        if stage_id in raw_results:
            ordered_results[stage_id] = raw_results[stage_id]
    for stage_id, result in raw_results.items():
        if stage_id not in ordered_results:
            ordered_results[str(stage_id)] = result
    ordered_record["stage_results"] = ordered_results
    return ordered_record


def _bounded_percent(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return max(0.0, min(100.0, parsed))


def _active_stage_percent(record: dict[str, Any]) -> float | None:
    current_stage = str(record.get("current_stage") or "")
    stage_results = record.get("stage_results")
    if not current_stage or not isinstance(stage_results, dict):
        return None
    result = stage_results.get(current_stage)
    if not isinstance(result, dict):
        return None

    scanner = result.get("scanner")
    if isinstance(scanner, dict):
        nested = _bounded_percent(scanner.get("progress_percent"))
        if nested is not None:
            return nested
    evidence = result.get("evidence")
    if isinstance(evidence, dict):
        nested = _bounded_percent(evidence.get("progress_percent"))
        if nested is not None:
            return nested
    return _bounded_percent(result.get("stage_progress_percent"))


def _display_progress(record: dict[str, Any]) -> tuple[float, float | None]:
    """Interpolate active-stage progress for UI display only."""

    canonical = _bounded_percent(record.get("progress_percent")) or 0.0
    if record.get("terminal"):
        return canonical, None
    active = _active_stage_percent(record)
    if active is None:
        return canonical, None
    stage_width = 100.0 / len(COMPREHENSIVE_STAGES)
    interpolated = min(99.99, canonical + (stage_width * active / 100.0))
    return round(max(canonical, interpolated), 2), round(active, 2)


def _bounded_value(value: Any, *, depth: int = 0) -> Any:
    """Project JSON-like evidence into a deterministic browser-safe structure."""

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= MAX_PROJECTED_STRING_CHARS:
            return value
        return value[:MAX_PROJECTED_STRING_CHARS] + "…"
    if depth >= MAX_PROJECTED_DEPTH:
        if isinstance(value, dict):
            return {"type": "object", "item_count": len(value), "bounded": True}
        if isinstance(value, list):
            return {"type": "array", "item_count": len(value), "bounded": True}
        return str(type(value).__name__)
    if isinstance(value, list):
        projected = [
            _bounded_value(item, depth=depth + 1)
            for item in value[:MAX_PROJECTED_LIST_ITEMS]
        ]
        if len(value) > MAX_PROJECTED_LIST_ITEMS:
            projected.append(
                {
                    "bounded": True,
                    "omitted_item_count": len(value) - MAX_PROJECTED_LIST_ITEMS,
                }
            )
        return projected
    if isinstance(value, dict):
        projected: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_PROJECTED_OBJECT_ITEMS:
                projected["_bounded"] = {
                    "omitted_item_count": len(value) - MAX_PROJECTED_OBJECT_ITEMS,
                }
                break
            projected[str(key)] = _bounded_value(item, depth=depth + 1)
        return projected
    return str(value)[:MAX_PROJECTED_STRING_CHARS]


def _project_engagement_metadata(value: Any) -> dict[str, Any]:
    """Return the verified, independently field-bounded intake snapshot exactly."""

    if not isinstance(value, dict):
        return {}
    try:
        if not verify_comprehensive_engagement_metadata(value):
            return {}
    except (TypeError, ValueError):
        return {}
    return deepcopy(value)


def _project_accepted_edition(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """Project the immutable approval identity without touching persisted state."""

    candidate = record.get("accepted_edition")
    if not isinstance(candidate, Mapping):
        return {}
    return deepcopy(dict(candidate))


def _project_stage_result(stage_id: str, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {
            "stage_id": stage_id,
            "status": "unknown",
            "summary": "Stage result was not an object.",
            "response_bounded": True,
        }

    projected: dict[str, Any] = {
        "stage_id": stage_id,
        "status": str(result.get("status") or "unknown"),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "response_bounded": True,
    }
    for key, value in result.items():
        normalized = str(key)
        if normalized in _OMITTED_STAGE_KEYS or normalized in projected:
            continue
        if value is None or isinstance(value, (bool, int, float, str)):
            projected[normalized] = _bounded_value(value)
            continue
        if normalized in {
            "evidence",
            "scanner",
            "metrics",
            "coverage",
            "unavailable",
            "findings",
        }:
            projected[normalized] = _bounded_value(value)
    omitted = [key for key in _OMITTED_STAGE_KEYS if key in result]
    if omitted:
        projected["omitted_large_fields"] = sorted(omitted)
    return projected


def _human_evidence_summary(record: dict[str, Any]) -> dict[str, Any]:
    package = record.get("human_evidence")
    if not isinstance(package, dict):
        return {
            "status": "not_assessed",
            "provided_module_ids": [],
            "provided_module_count": 0,
        }
    provided = [str(item) for item in package.get("provided_module_ids") or []]
    return {
        "artifact_schema": str(package.get("artifact_schema") or ""),
        "status": str(package.get("status") or "not_assessed"),
        "provided_module_ids": provided,
        "provided_module_count": len(provided),
        "status_counts": _bounded_value(package.get("status_counts") or {}),
        "human_statement_count": int(package.get("human_statement_count") or 0),
        "attachment_reference_count": int(
            package.get("attachment_reference_count") or 0
        ),
        "structured_record_count": int(package.get("structured_record_count") or 0),
        "human_evidence_sha256": str(package.get("human_evidence_sha256") or ""),
        "repository_inference_prohibited": True,
    }


def _project_record(record: dict[str, Any]) -> dict[str, Any]:
    stage_results = (
        record.get("stage_results")
        if isinstance(record.get("stage_results"), dict)
        else {}
    )
    delivery_allowed = record.get("client_delivery_allowed") is True
    human_review_completed = record.get("human_review_completed") is True
    return {
        "artifact_schema": str(record.get("artifact_schema") or ""),
        "service_id": "comprehensive",
        "status": str(record.get("status") or "unknown"),
        "identity": _bounded_value(
            record.get("identity") if isinstance(record.get("identity"), dict) else {}
        ),
        "engagement_metadata": _project_engagement_metadata(
            record.get("engagement_metadata")
        ),
        "human_evidence_summary": _human_evidence_summary(record),
        "current_stage": record.get("current_stage"),
        "completed_stages": [str(item) for item in record.get("completed_stages") or []],
        "stage_results": {
            stage_id: _project_stage_result(stage_id, result)
            for stage_id, result in stage_results.items()
        },
        "blockers": _bounded_value(record.get("blockers") or []),
        "progress_percent": record.get("progress_percent"),
        "revision": record.get("revision"),
        "terminal": bool(record.get("terminal")),
        "human_review_required": True,
        "human_review_completed": human_review_completed,
        "client_delivery_allowed": delivery_allowed,
        "delivery_status": (
            "approved_for_delivery"
            if delivery_allowed
            else "pending_authorization"
            if str(record.get("status") or "").casefold() == "approved"
            else "blocked"
        ),
        "integrity_sha256": str(record.get("integrity_sha256") or ""),
        "response_projection": {
            "version": VERSION,
            "bounded": True,
            "persisted_record_mutated": False,
            "large_stage_payloads_omitted": True,
            "report_payload_deferred_until_terminal": True,
        },
    }


def _normalized_report_language(value: Any) -> str:
    normalized = str(value or "").strip().casefold().replace("_", "-")
    if normalized == "en":
        return "en"
    if normalized == "es-mx":
        return "es-MX"
    return ""


def _final_report_identity_and_language_bound(
    record: Mapping[str, Any],
    report: Mapping[str, Any],
) -> bool:
    """Require the final package JSON to bind exact run and locale truth."""

    run_identity = (
        record.get("identity")
        if isinstance(record.get("identity"), Mapping)
        else {}
    )
    canonical = report.get("json") if isinstance(report.get("json"), Mapping) else {}
    canonical_identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        run_value = str(run_identity.get(field) or "").strip()
        canonical_value = str(canonical_identity.get(field) or "").strip()
        if not run_value or not canonical_value or run_value != canonical_value:
            return False

    run_language = _normalized_report_language(run_identity.get("report_language"))
    if not run_language:
        return False
    canonical_assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    canonical_language_values = [
        value
        for value in (
            canonical.get("report_language"),
            canonical.get("locale"),
            canonical_identity.get("report_language"),
            canonical_identity.get("locale"),
            canonical_assessment.get("report_language"),
            canonical_assessment.get("locale"),
        )
        if str(value or "").strip()
    ]
    if not canonical_language_values:
        return False
    language_values = [
        *canonical_language_values,
        *[
            value
            for value in (report.get("report_language"), report.get("locale"))
            if str(value or "").strip()
        ],
    ]
    normalized_languages = {
        _normalized_report_language(value) for value in language_values
    }
    if "" in normalized_languages or normalized_languages != {run_language}:
        return False

    report_id = str(report.get("report_id") or "").strip()
    canonical_report_id = str(canonical.get("report_id") or "").strip()
    if canonical_report_id and report_id != canonical_report_id:
        return False
    return True


def _final_report_package_integrity_bound(report: Mapping[str, Any]) -> bool:
    """Require immutable JSON/PDF digests before treating a final stage as authority."""

    canonical = report.get("json")
    if not isinstance(canonical, Mapping) or not canonical:
        return False
    truth_sha256 = str(report.get("canonical_truth_sha256") or "").strip().casefold()
    if not _SHA256_RE.fullmatch(truth_sha256):
        return False
    if not _canonical_truth_hash_integrity_bound(report, canonical):
        return False

    if not isinstance(report.get("markdown"), str) or not report.get("markdown"):
        return False
    if not isinstance(report.get("html"), str) or not report.get("html"):
        return False
    encoded_pdf = report.get("pdf_base64")
    if not isinstance(encoded_pdf, str) or not encoded_pdf.strip():
        return False
    if str(report.get("pdf_error") or "").strip():
        return False
    try:
        pdf = base64.b64decode(encoded_pdf.strip(), validate=True)
    except (TypeError, ValueError):
        return False
    if not pdf.startswith(b"%PDF"):
        return False
    pdf_sha256 = str(report.get("pdf_sha256") or "").strip().casefold()
    if not _SHA256_RE.fullmatch(pdf_sha256):
        return False
    if pdf_sha256 != hashlib.sha256(pdf).hexdigest():
        return False

    for value_key, digest_key in (
        ("markdown", "markdown_sha256"),
        ("html", "html_sha256"),
    ):
        claimed = str(report.get(digest_key) or "").strip().casefold()
        if not claimed:
            continue
        if not _SHA256_RE.fullmatch(claimed):
            return False
        observed = hashlib.sha256(str(report[value_key]).encode("utf-8")).hexdigest()
        if claimed != observed:
            return False
    if not _retained_manifest_integrity_bound(report):
        return False
    return True


def _manifest_family_claimed(report: Mapping[str, Any]) -> bool:
    top_level_claimed = any(
        report.get(field) not in (None, "") for field in _MANIFEST_FAMILY_FIELDS
    )
    canonical = report.get("json")
    nested_manifest_claimed = (
        isinstance(canonical, Mapping)
        and isinstance(canonical.get("artifact_manifest"), Mapping)
    )
    return top_level_claimed or nested_manifest_claimed


def _canonical_truth_hash_integrity_bound(
    report: Mapping[str, Any],
    canonical: Mapping[str, Any] | None = None,
) -> bool:
    """Accept current raw hashes or exact manifest-bound legacy report hashes."""

    canonical_value = canonical if isinstance(canonical, Mapping) else report.get("json")
    if not isinstance(canonical_value, Mapping) or not canonical_value:
        return False
    stored = str(report.get("canonical_truth_sha256") or "").strip().casefold()
    if not _SHA256_RE.fullmatch(stored):
        return False
    if stored == canonical_sha256(canonical_value):
        return True
    # Reports persisted before the raw-hash transition excluded nested rendered
    # presentation fields from this one digest. Permit that exact historical value
    # only when the complete retained manifest family separately binds every byte.
    if stored != _legacy_canonical_hash(canonical_value):
        return False
    return _manifest_family_claimed(report) and _retained_manifest_integrity_bound(
        report
    )


def _retained_manifest_integrity_bound(report: Mapping[str, Any]) -> bool:
    """Bind detached evidence-manifest claims to their exact retained bytes."""

    if not _manifest_family_claimed(report):
        return True
    if any(report.get(field) in (None, "") for field in _MANIFEST_FAMILY_FIELDS):
        return False

    manifest_text = report.get("evidence_manifest_json")
    manifest_sha256 = str(
        report.get("evidence_manifest_sha256") or ""
    ).strip().casefold()
    manifest_claimed = manifest_text not in (None, "") or bool(manifest_sha256)
    parsed_manifest: Mapping[str, Any] | None = None
    if manifest_claimed:
        if not isinstance(manifest_text, str) or not manifest_text:
            return False
        if not _SHA256_RE.fullmatch(manifest_sha256):
            return False
        manifest_bytes = manifest_text.encode("utf-8")
        if hashlib.sha256(manifest_bytes).hexdigest() != manifest_sha256:
            return False
        try:
            parsed = json.loads(manifest_text)
        except (TypeError, ValueError):
            return False
        if not isinstance(parsed, Mapping):
            return False
        parsed_manifest = parsed

    detached_manifest = report.get("artifact_manifest")
    if detached_manifest is not None:
        if (
            not isinstance(detached_manifest, Mapping)
            or parsed_manifest is None
            or dict(detached_manifest) != dict(parsed_manifest)
        ):
            return False

    canonical_text = report.get("canonical_json")
    canonical_json_sha256 = str(
        report.get("canonical_json_sha256") or ""
    ).strip().casefold()
    canonical_claimed = canonical_text not in (None, "") or bool(
        canonical_json_sha256
    )
    observed_canonical_sha256 = ""
    if canonical_claimed:
        if not isinstance(canonical_text, str) or not canonical_text:
            return False
        if not _SHA256_RE.fullmatch(canonical_json_sha256):
            return False
        observed_canonical_sha256 = hashlib.sha256(
            canonical_text.encode("utf-8")
        ).hexdigest()
        if observed_canonical_sha256 != canonical_json_sha256:
            return False
        try:
            parsed_canonical = json.loads(canonical_text)
        except (TypeError, ValueError):
            return False
        if not isinstance(parsed_canonical, Mapping):
            return False
        canonical_mapping = report.get("json")
        if (
            not isinstance(canonical_mapping, Mapping)
            or dict(parsed_canonical) != dict(canonical_mapping)
        ):
            return False

    draft_identity = report.get("draft_artifact_identity")
    if (
        not isinstance(draft_identity, Mapping)
        or not isinstance(detached_manifest, Mapping)
        or parsed_manifest is None
        or not observed_canonical_sha256
    ):
        return False

    manifest_id = str(detached_manifest.get("manifest_id") or "").strip()
    if not manifest_id or str(draft_identity.get("manifest_id") or "").strip() != manifest_id:
        return False
    observed_claims = {
        "pdf_sha256": str(report.get("pdf_sha256") or "").strip().casefold(),
        "canonical_json_sha256": observed_canonical_sha256,
        "evidence_manifest_sha256": manifest_sha256,
    }
    for field, observed in observed_claims.items():
        if (
            not _SHA256_RE.fullmatch(observed)
            or str(report.get(field) or "").strip().casefold() != observed
            or str(draft_identity.get(field) or "").strip().casefold() != observed
        ):
            return False

    canonical = report.get("json")
    canonical_identity = (
        canonical.get("identity")
        if isinstance(canonical, Mapping)
        and isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    manifest_identity = (
        detached_manifest.get("identity")
        if isinstance(detached_manifest.get("identity"), Mapping)
        else {}
    )
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        expected = str(canonical_identity.get(field) or "").strip()
        if (
            not expected
            or str(manifest_identity.get(field) or "").strip() != expected
        ):
            return False
        # Historical draft identities predate this field, but every detached
        # manifest has always carried it. New drafts bind it explicitly too.
        if field != "evidence_ledger_id" or draft_identity.get(field) not in (
            None,
            "",
        ):
            if str(draft_identity.get(field) or "").strip() != expected:
                return False
    try:
        from nico.comprehensive_exact_artifact_hash_binding_v1 import (
            _validate_exact_artifact_hashes,
        )

        _validate_exact_artifact_hashes(report)
    except (TypeError, ValueError):
        return False
    return True


def _accepted_final_report_integrity_bound(
    record: Mapping[str, Any],
    report: Mapping[str, Any],
) -> bool:
    """Prevent approval or delivery state from carrying across changed artifacts."""

    status = str(record.get("status") or "").strip().casefold()
    if status != "approved":
        return record.get("client_delivery_allowed") is not True
    if record.get("human_review_completed") is not True:
        return False
    if not _review_decision_integrity_bound(record):
        return False
    accepted = record.get("accepted_edition")
    if not isinstance(accepted, Mapping):
        return False
    if (
        accepted.get("accepted_edition") is not True
        or accepted.get("client_delivery_allowed") is not False
        or str(accepted.get("delivery_status") or "").strip()
        != "pending_authorization"
    ):
        return False

    manifest_payload = deepcopy(dict(accepted))
    manifest_sha256 = str(
        manifest_payload.pop("accepted_edition_manifest_sha256", "") or ""
    ).strip().casefold()
    if (
        not _SHA256_RE.fullmatch(manifest_sha256)
        or manifest_sha256 != canonical_sha256(manifest_payload)
    ):
        return False

    review = accepted.get("review")
    if not isinstance(review, Mapping):
        return False
    review_payload = deepcopy(dict(review))
    certificate_sha256 = str(
        review_payload.pop("approval_certificate_sha256", "") or ""
    ).strip().casefold()
    if (
        not _SHA256_RE.fullmatch(certificate_sha256)
        or certificate_sha256 != canonical_sha256(review_payload)
    ):
        return False
    try:
        reviewer_binding(
            reviewer=str(review.get("reviewer") or ""),
            reviewer_role=str(review.get("reviewer_role") or ""),
            decision=str(review.get("decision") or ""),
            decided_at=str(review.get("decided_at") or ""),
            decision_reason=str(review.get("reason") or ""),
        )
    except ValueError:
        return False

    validation = validate_accepted_edition(report, accepted)
    if validation.get("status") != "valid" or list(
        validation.get("validation_errors") or []
    ):
        return False

    return True


def _client_delivery_integrity_bound(record: Mapping[str, Any]) -> bool:
    """Validate the distinct post-approval human delivery authorization chain."""

    if record.get("client_delivery_allowed") is not True:
        return True
    if (
        str(record.get("status") or "").strip().casefold() != "approved"
        or record.get("human_review_completed") is not True
        or not _review_decision_integrity_bound(record)
    ):
        return False
    accepted = record.get("accepted_edition")
    if not isinstance(accepted, Mapping):
        return False
    try:
        from nico.comprehensive_approved_delivery_v4 import (
            validate_approved_delivery_package,
        )
        from nico.comprehensive_delivery_authorization_v1 import (
            validate_delivery_authorization,
        )

        authorization = validate_delivery_authorization(
            record,
            accepted,
            record.get("delivery_authorization"),
        )
        delivery = validate_approved_delivery_package(
            record,
            record.get("approved_delivery_package"),
        )
    except (TypeError, ValueError):
        return False
    return (
        authorization.get("status") == "valid"
        and not list(authorization.get("validation_errors") or [])
        and delivery.get("status") == "valid"
        and not list(delivery.get("validation_errors") or [])
    )


def _review_decision_integrity_bound(record: Mapping[str, Any]) -> bool:
    """Bind the exposed receipt to the final review transition it represents."""

    decision = record.get("review_decision")
    if decision is None:
        history = record.get("review_history")
        return (
            not history
            and not isinstance(record.get("accepted_edition"), Mapping)
            and str(record.get("status") or "").strip().casefold()
            not in {"approved", "rejected"}
        )
    if not isinstance(decision, Mapping):
        return False
    try:
        from nico.comprehensive_run_record import _review_manifest_errors

        if _review_manifest_errors(record, decision):
            return False
    except (TypeError, ValueError):
        return False

    history = record.get("review_history")
    if not isinstance(history, list) or not history:
        return False
    final_history_entry = history[-1]
    if not isinstance(final_history_entry, Mapping) or dict(final_history_entry) != dict(
        decision
    ):
        return False

    review = decision.get("review")
    if not isinstance(review, Mapping):
        return False
    review_decision = str(review.get("decision") or "").strip().casefold()
    expected_status = {
        "approved": "approved",
        "rejected": "rejected",
        "request_more_evidence": "review_required",
    }.get(review_decision)
    if expected_status is None:
        return False
    if str(record.get("status") or "").strip().casefold() != expected_status:
        return False

    accepted = record.get("accepted_edition")
    if review_decision == "approved":
        return isinstance(accepted, Mapping) and dict(accepted) == dict(decision)
    return not isinstance(accepted, Mapping)


def _rejected_review_integrity_bound(record: Mapping[str, Any]) -> bool:
    """Require the exact final hashed human decision before projecting rejection."""

    if str(record.get("status") or "").strip().casefold() not in {
        "rejected",
        "declined",
    }:
        return True
    if (
        record.get("human_review_completed") is not True
        or record.get("client_delivery_allowed") is True
        or isinstance(record.get("accepted_edition"), Mapping)
    ):
        return False
    decision = record.get("review_decision")
    if not isinstance(decision, Mapping):
        return False
    review = decision.get("review")
    if (
        not isinstance(review, Mapping)
        or str(review.get("decision") or "").strip().casefold() != "rejected"
    ):
        return False
    return _review_decision_integrity_bound(record)


def _canonical_final_report_outputs(
    record: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return only the language-bound package published by the canonical final stage.

    Earlier decision/report stages may contain useful internal drafts. They are never
    final artifact authority and must not become downloadable merely because a later
    final-render failure made the run terminal.
    """

    if record.get("terminal") is not True:
        return {}, {}
    if str(record.get("status") or "").strip().casefold() not in _FINAL_REPORT_RUN_STATUSES:
        return {}, {}
    if _FINAL_REPORT_STAGE_ID not in {
        str(item) for item in record.get("completed_stages") or []
    }:
        return {}, {}
    stage_results = (
        record.get("stage_results")
        if isinstance(record.get("stage_results"), dict)
        else {}
    )
    final_stage = stage_results.get(_FINAL_REPORT_STAGE_ID)
    if not isinstance(final_stage, dict):
        return {}, {}
    if (
        str(final_stage.get("status") or "").strip().casefold()
        not in _FINAL_REPORT_STAGE_SUCCESS_STATUSES
    ):
        return {}, {}
    candidate = (
        final_stage.get("report_package")
        if isinstance(final_stage.get("report_package"), dict)
        else final_stage.get("reports")
    )
    if not isinstance(candidate, dict) or not _final_report_identity_and_language_bound(
        record,
        candidate,
    ):
        return {}, {}
    if not _final_report_package_integrity_bound(candidate):
        return {}, {}
    if not _accepted_final_report_integrity_bound(record, candidate):
        return {}, {}
    report = candidate
    assessment = (
        final_stage.get("assessment")
        if isinstance(final_stage.get("assessment"), dict)
        else {}
    )
    return report, assessment


def _report_outputs(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compatibility hook over the one canonical final artifact source."""

    return _canonical_final_report_outputs(record)


def _project_report(report: dict[str, Any]) -> dict[str, Any]:
    """Attach exact terminal artifacts for established non-browser API consumers."""

    projected = {
        key: deepcopy(report[key])
        for key in _REPORT_KEYS
        if key in report
    }
    json_value = report.get("json")
    if isinstance(json_value, dict) and json_value:
        projected["json"] = deepcopy(json_value)
    return projected


def _project_report_manifest(report: dict[str, Any]) -> dict[str, Any]:
    """Return a lightweight exact-run artifact manifest for browser lifecycle reads."""

    projected = {
        key: _bounded_value(report[key])
        for key in _REPORT_MANIFEST_KEYS
        if key in report
    }
    projected.update(
        {
            "markdown_available": bool(str(report.get("markdown") or "").strip()),
            "html_available": bool(str(report.get("html") or "").strip()),
            "json_available": isinstance(report.get("json"), dict)
            and bool(report.get("json")),
            "pdf_available": bool(str(report.get("pdf_base64") or "").strip())
            and not bool(str(report.get("pdf_error") or "").strip()),
            "response_bounded": True,
            "artifact_delivery": "on_demand_exact_run",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    return projected


def _project_assessment(assessment: dict[str, Any]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for key in (
        "executive_summary",
        "evidence_coverage",
        "evidence_completion_contract",
        "technical_score",
        "canonical_evidence_adjusted_score",
        "evidence_adjusted_score",
        "maturity_signal",
        "unavailable_data_notes",
        "human_review_required",
        "client_ready",
        "client_delivery_allowed",
    ):
        if key in assessment:
            projected[key] = _bounded_value(assessment[key])

    sections = assessment.get("sections")
    if isinstance(sections, list):
        projected_sections: list[dict[str, Any]] = []
        for section in sections[:MAX_PROJECTED_LIST_ITEMS]:
            if not isinstance(section, dict):
                continue
            item: dict[str, Any] = {}
            for key in (
                "id",
                "label",
                "score",
                "presented_score",
                "status",
                "presented_status",
                "summary",
                "evidence",
                "findings",
                "unavailable",
            ):
                if key in section:
                    item[key] = _bounded_value(section[key])
            projected_sections.append(item)
        projected["sections"] = projected_sections
    projected["human_review_required"] = True
    projected["client_ready"] = False
    projected["client_delivery_allowed"] = False
    return projected


class ComprehensiveApiController:
    """Framework-neutral controller for the customer-facing Comprehensive API.

    The durable store keeps the full canonical run. Active-stage response records stay
    bounded. Established API consumers keep the full terminal report package, while a
    caller that explicitly requests the browser projection receives only an artifact
    manifest and retrieves Markdown/HTML/JSON/PDF through exact-run artifact endpoints.
    This changes browser transport only; durable assessment truth and approval/delivery
    authority remain unchanged.
    """

    def __init__(self, service: ComprehensiveRunService) -> None:
        self._service = service

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = self._object(payload)
        repository = self._required(body.get("repository"), "repository")
        commit_sha = self._required(body.get("commit_sha"), "commit_sha")
        run_id = self._required(body.get("run_id"), "run_id")
        evidence_ledger_id = self._required(
            body.get("evidence_ledger_id"),
            "evidence_ledger_id",
        )
        customer_id = self._required(body.get("customer_id"), "customer_id")
        project_id = self._required(body.get("project_id"), "project_id")
        assessment_depth = self._required(
            body.get("assessment_depth") or "strategic",
            "assessment_depth",
        )
        report_language = self._required(
            body.get("report_language") or "en",
            "report_language",
        )
        if (
            body.get("authorization_confirmed") is not True
            or body.get("authorized") is not True
        ):
            raise ValueError("explicit_authorization_required")

        engagement_metadata = build_comprehensive_engagement_metadata(
            client_name=body.get("client_name"),
            project_name=body.get("project_name"),
            human_evidence=body.get("human_evidence"),
        )
        record = self._service.start(
            run_id=run_id,
            repository=repository,
            commit_sha=commit_sha,
            evidence_ledger_id=evidence_ledger_id,
            customer_id=customer_id,
            project_id=project_id,
            authorized=True,
            assessment_depth=assessment_depth,
            report_language=report_language,
            human_evidence=body.get("human_evidence"),
            engagement_metadata=engagement_metadata,
        )
        return self._response(record, operation="started")

    def status(self, run_id: str) -> dict[str, Any]:
        record = self._service.load(self._required(run_id, "run_id"))
        return self._response(record, operation="status")

    def status_read_only(self, run_id: str) -> dict[str, Any]:
        """Project stored truth without resuming or regenerating the assessment."""

        record = self._service.load_read_only(self._required(run_id, "run_id"))
        return self._response(record, operation="status")

    def status_artifact_read_only(self, run_id: str) -> dict[str, Any]:
        """Return validated artifact authority without cloning every artifact body.

        Exact-run artifact endpoints need the canonical terminal package, but they do
        not need the established non-browser status response to deep-copy that package
        before immediately reducing it to one artifact.  Validate the stored package
        through the same canonical response boundary, project only its browser
        manifest, and then attach the already-validated in-memory package reference for
        the synchronous artifact builder.  The returned value is request-local and the
        builders treat the attached package as read-only.
        """

        record = self._service.load_read_only(self._required(run_id, "run_id"))
        response = self._response(
            record,
            operation="status",
            browser_projection=True,
        )
        manifest = (
            response.get("reports")
            if isinstance(response.get("reports"), Mapping)
            else {}
        )
        if not manifest:
            return response

        stage_results = (
            record.get("stage_results")
            if isinstance(record.get("stage_results"), Mapping)
            else {}
        )
        final_stage = stage_results.get(_FINAL_REPORT_STAGE_ID)
        if not isinstance(final_stage, Mapping):
            return response
        candidate = (
            final_stage.get("report_package")
            if isinstance(final_stage.get("report_package"), Mapping)
            else final_stage.get("reports")
        )
        if not isinstance(candidate, Mapping):
            return response

        # `_response(..., browser_projection=True)` attaches a manifest only after the
        # exact candidate passes package, identity, locale, and lifecycle validation.
        # Bind the reference back to that manifest so a later structural refactor
        # cannot accidentally substitute another stage's package here.
        for field in ("report_id", "canonical_truth_sha256"):
            if str(candidate.get(field) or "").strip() != str(
                manifest.get(field) or ""
            ).strip():
                return response

        projected = dict(response)
        projected["reports"] = candidate
        return projected

    def continue_run(
        self,
        run_id: str,
        payload: dict[str, Any] | None = None,
        *,
        browser_projection: bool = False,
    ) -> dict[str, Any]:
        body = self._object(payload or {})
        bounded = body.get("max_stages")
        max_stages = None if bounded is None else int(bounded)
        if max_stages is not None and max_stages < 0:
            raise ValueError("max_stages_must_be_non_negative")
        record = self._service.resume(
            self._required(run_id, "run_id"),
            max_stages=max_stages,
        )
        return self._response(
            record,
            operation="continued",
            browser_projection=browser_projection,
        )

    @staticmethod
    def _object(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise TypeError("request_body_must_be_object")
        return dict(payload)

    @staticmethod
    def _required(value: Any, field: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"{field}_required")
        return normalized

    @staticmethod
    def _response(
        record: dict[str, Any],
        *,
        operation: str,
        browser_projection: bool = False,
    ) -> dict[str, Any]:
        canonical_record = _ordered_record(record)
        identity = canonical_record["identity"]
        display_progress, active_stage_progress = _display_progress(canonical_record)
        terminal = bool(canonical_record.get("terminal"))
        report: dict[str, Any] = {}
        assessment: dict[str, Any] = {}
        if terminal:
            report, assessment = _report_outputs(canonical_record)
        terminal_report_available = bool(report)
        canonical_status = str(canonical_record.get("status") or "unknown")
        normalized_status = canonical_status.casefold()
        approved_status = normalized_status == "approved"
        rejected_status = normalized_status in {"rejected", "declined"}
        terminal_report_required = (
            terminal and normalized_status in _FINAL_REPORT_RUN_STATUSES
        )
        artifact_integrity_failed = (
            terminal_report_required and not terminal_report_available
        )
        review_decision_integrity_valid = _review_decision_integrity_bound(
            canonical_record
        )
        rejection_integrity_failed = (
            rejected_status
            and not _rejected_review_integrity_bound(canonical_record)
        )
        delivery_integrity_failed = (
            canonical_record.get("client_delivery_allowed") is True
            and not _client_delivery_integrity_bound(canonical_record)
        )
        projected_status = (
            "blocked"
            if artifact_integrity_failed or rejection_integrity_failed
            else canonical_status
        )
        human_review_completed = (
            (
                approved_status
                and canonical_record.get("human_review_completed") is True
                and not artifact_integrity_failed
            )
            or (
                rejected_status
                and not artifact_integrity_failed
                and not rejection_integrity_failed
            )
        )
        delivery_allowed = (
            approved_status
            and human_review_completed
            and canonical_record.get("client_delivery_allowed") is True
            and not artifact_integrity_failed
            and not delivery_integrity_failed
        )
        approval_status = (
            "invalidated_artifact_mismatch"
            if artifact_integrity_failed
            else "invalidated_review_receipt_mismatch"
            if rejection_integrity_failed
            else "approved_final"
            if approved_status and human_review_completed
            else "rejected"
            if rejected_status
            else "pending_human_approval"
        )
        stale_approval_state_suppressed = (
            not approved_status
            and not rejected_status
            and (
                canonical_record.get("human_review_completed") is True
                or isinstance(canonical_record.get("accepted_edition"), Mapping)
            )
        )
        projected_delivery_status = (
            "blocked_artifact_integrity"
            if artifact_integrity_failed
            else "blocked_review_integrity"
            if rejection_integrity_failed
            else "blocked_authorization_integrity"
            if delivery_integrity_failed
            else "approved_for_delivery"
            if delivery_allowed
            else "pending_authorization"
            if approved_status and human_review_completed
            else "blocked"
        )
        projection_record = canonical_record
        if (
            artifact_integrity_failed
            or rejection_integrity_failed
            or delivery_integrity_failed
            or stale_approval_state_suppressed
            or canonical_record.get("human_review_completed") is not human_review_completed
            or canonical_record.get("client_delivery_allowed") is not delivery_allowed
        ):
            projection_record = dict(canonical_record)
            if artifact_integrity_failed or rejection_integrity_failed:
                projection_record["canonical_status"] = canonical_status
                projection_record["status"] = "blocked"
            projection_record["human_review_completed"] = human_review_completed
            projection_record["client_delivery_allowed"] = delivery_allowed
        projected_record = _project_record(projection_record)
        projected_record["delivery_status"] = projected_delivery_status
        response: dict[str, Any] = {
            "artifact_schema": VERSION,
            "service_id": "comprehensive",
            "operation": operation,
            "run_id": identity["run_id"],
            "repository": identity["repository"],
            "commit_sha": identity["commit_sha"],
            "evidence_ledger_id": identity["evidence_ledger_id"],
            "customer_id": identity["customer_id"],
            "project_id": identity["project_id"],
            "assessment_depth": str(identity.get("assessment_depth") or "strategic"),
            "report_language": str(identity.get("report_language") or "en"),
            "engagement_metadata": _project_engagement_metadata(
                canonical_record.get("engagement_metadata")
            ),
            "human_evidence_summary": _human_evidence_summary(canonical_record),
            "status": projected_status,
            "canonical_status": canonical_status,
            "current_stage": canonical_record["current_stage"],
            "completed_stages": list(canonical_record["completed_stages"]),
            "progress_percent": display_progress,
            "canonical_progress_percent": canonical_record["progress_percent"],
            "active_stage_progress_percent": active_stage_progress,
            "revision": canonical_record["revision"],
            "terminal": terminal,
            "human_review_required": True,
            "human_review_completed": human_review_completed,
            "client_delivery_allowed": delivery_allowed,
            "approval_status": approval_status,
            "delivery_status": projected_delivery_status,
            "integrity_sha256": canonical_record["integrity_sha256"],
            "record": projected_record,
            "response_projection": {
                "version": VERSION,
                "bounded": True,
                "terminal_report_attached": terminal_report_available
                and not browser_projection,
                "terminal_canonical_json_attached": terminal_report_available
                and not browser_projection,
                "terminal_report_manifest_attached": terminal_report_available
                and browser_projection,
                "terminal_report_artifacts_inlined": terminal_report_available
                and not browser_projection,
                "full_record_persisted": True,
                "large_stage_payloads_omitted": True,
                "exact_run_artifact_endpoints_required": terminal_report_available
                and browser_projection,
                "browser_projection": browser_projection,
                "artifact_integrity_valid": not artifact_integrity_failed,
                "terminal_report_package_integrity_valid": (
                    terminal_report_available
                ),
                "rejection_review_integrity_valid": (
                    not rejection_integrity_failed
                ),
                "review_decision_integrity_valid": (
                    review_decision_integrity_valid
                ),
                "delivery_authorization_integrity_valid": (
                    not delivery_integrity_failed
                ),
                "approval_invalidated_by_artifact_mismatch": (
                    artifact_integrity_failed
                ),
                "review_package_invalidated_by_artifact_mismatch": (
                    artifact_integrity_failed
                ),
                "rejection_invalidated_by_review_mismatch": (
                    rejection_integrity_failed
                ),
                "delivery_authorization_invalidated": (
                    delivery_integrity_failed
                ),
                "stale_approval_state_suppressed": (
                    stale_approval_state_suppressed
                ),
            },
        }
        if terminal:
            if report:
                response["reports"] = (
                    _project_report_manifest(report)
                    if browser_projection
                    else _project_report(report)
                )
            if assessment:
                response["assessment"] = _project_assessment(assessment)
            accepted_edition = (
                _project_accepted_edition(canonical_record)
                if approved_status
                and human_review_completed
                and not artifact_integrity_failed
                else {}
            )
            if accepted_edition:
                response["accepted_edition"] = accepted_edition
        return response


__all__ = ["ComprehensiveApiController", "VERSION"]
