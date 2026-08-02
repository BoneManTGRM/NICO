from __future__ import annotations

import base64
import hashlib
from copy import deepcopy
from typing import Any, Mapping

from nico.comprehensive_stage_execution_timeout_v1 import execute_stage_with_timeout

VERSION = "nico.comprehensive_final_report_execution_boundary.v3"
FINAL_REPORT_STAGE_ID = "final_comprehensive_report_generation"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _blocked(
    context: Mapping[str, Any],
    *,
    reason: str,
    message: str,
    execution: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason": reason,
        "error_code": reason,
        "error_message": message,
        "technical_reason": f"{reason}:stage={FINAL_REPORT_STAGE_ID}",
        "retryable": True,
        "cancelable": True,
        "artifacts_available": False,
        "run_id": _text(context.get("run_id")),
        "repository": _text(context.get("repository")),
        "commit_sha": _text(context.get("commit_sha")),
        "evidence_ledger_id": _text(context.get("evidence_ledger_id")),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "stage_execution": {
            **deepcopy(dict(execution or {})),
            "artifact_schema": VERSION,
            "mode": "atomic_final_report_publication",
            "canonical_run_write_required": True,
            "detached_background_execution": False,
        },
    }


def _exact_identity_matches(
    value: Mapping[str, Any],
    context: Mapping[str, Any],
) -> bool:
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        expected = _text(context.get(field))
        observed = _text(value.get(field))
        if expected and observed and expected != observed:
            return False
    return True


def _validate_package(
    package: Mapping[str, Any],
    context: Mapping[str, Any],
) -> tuple[bool, str, dict[str, Any]]:
    report_id = _text(package.get("report_id"))
    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    pdf_base64 = _text(package.get("pdf_base64"))
    canonical_json = package.get("json")

    if not report_id:
        return False, "final_report_id_missing", {}
    if not markdown.strip():
        return False, "final_report_markdown_missing", {}
    if not rendered_html.strip():
        return False, "final_report_html_missing", {}
    if not isinstance(canonical_json, Mapping):
        return False, "final_report_json_missing", {}
    if not pdf_base64:
        return False, "final_report_pdf_missing", {}
    try:
        pdf = base64.b64decode(pdf_base64, validate=True)
    except Exception:
        return False, "final_report_pdf_invalid_base64", {}
    if not pdf.startswith(b"%PDF"):
        return False, "final_report_pdf_invalid", {}

    identity = canonical_json.get("identity") if isinstance(canonical_json.get("identity"), Mapping) else canonical_json
    if isinstance(identity, Mapping) and not _exact_identity_matches(identity, context):
        return False, "final_report_identity_mismatch", {}

    evidence = {
        "report_id": report_id,
        "pdf_page_count": package.get("pdf_page_count"),
        "pdf_sha256": _text(package.get("pdf_sha256")) or hashlib.sha256(pdf).hexdigest(),
        "markdown_sha256": _text(package.get("markdown_sha256"))
        or hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "html_sha256": _text(package.get("html_sha256"))
        or hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
        "canonical_truth_sha256": _text(package.get("canonical_truth_sha256")),
        "exact_run_identity_verified": True,
        "pdf_valid": True,
        "markdown_available": True,
        "html_available": True,
        "json_available": True,
    }
    return True, "", evidence


def execute_final_report_stage(
    executor,
    context: Mapping[str, Any],
    *,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Generate and validate the final report inside the canonical request boundary.

    Final report artifacts can be large. They must not depend on a process-local daemon
    thread or on storing the complete PDF/HTML/Markdown payload in the generic
    ``client_jobs`` telemetry surface. The provider runs behind the existing bounded
    request timeout, and only a complete, identity-bound artifact package is returned
    to ``ComprehensiveRunService`` for the canonical run-store write.
    """

    raw = execute_stage_with_timeout(
        executor,
        context,
        stage_id=FINAL_REPORT_STAGE_ID,
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(raw, Mapping):
        return _blocked(
            context,
            reason="final_report_provider_invalid_result",
            message="The final report provider did not return a structured result.",
        )

    output = deepcopy(dict(raw))
    execution = output.get("stage_execution") if isinstance(output.get("stage_execution"), Mapping) else {}
    status = _text(output.get("status")).casefold()
    if status != "complete":
        output.setdefault("run_id", _text(context.get("run_id")))
        output.setdefault("repository", _text(context.get("repository")))
        output.setdefault("commit_sha", _text(context.get("commit_sha")))
        output.setdefault("evidence_ledger_id", _text(context.get("evidence_ledger_id")))
        output["human_review_required"] = True
        output["client_delivery_allowed"] = False
        output["stage_execution"] = {
            **deepcopy(dict(execution)),
            "artifact_schema": VERSION,
            "mode": "atomic_final_report_publication",
            "canonical_run_write_required": True,
            "detached_background_execution": False,
        }
        return output

    if not _exact_identity_matches(output, context):
        return _blocked(
            context,
            reason="final_report_result_identity_mismatch",
            message="The final report provider result did not match the exact run identity.",
            execution=execution,
        )

    package = output.get("report_package")
    if not isinstance(package, Mapping):
        return _blocked(
            context,
            reason="final_report_package_missing",
            message="The final report provider completed without a retained report package.",
            execution=execution,
        )

    valid, reason, evidence = _validate_package(package, context)
    if not valid:
        return _blocked(
            context,
            reason=reason,
            message=f"The final report package failed validation: {reason}.",
            execution=execution,
        )

    output["run_id"] = _text(context.get("run_id"))
    output["repository"] = _text(context.get("repository"))
    output["commit_sha"] = _text(context.get("commit_sha"))
    output["evidence_ledger_id"] = _text(context.get("evidence_ledger_id"))
    output["report_package"] = deepcopy(dict(package))
    output["artifacts_available"] = True
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False
    output["stage_execution"] = {
        **deepcopy(dict(execution)),
        "artifact_schema": VERSION,
        "mode": "atomic_final_report_publication",
        "canonical_run_write_required": True,
        "canonical_run_written_only_by_request_thread": True,
        "detached_background_execution": False,
        "artifact_validation_complete": True,
        "exact_identity_verified": True,
    }
    retained_evidence = output.get("evidence") if isinstance(output.get("evidence"), Mapping) else {}
    output["evidence"] = {**deepcopy(dict(retained_evidence)), **evidence}
    return output


__all__ = [
    "FINAL_REPORT_STAGE_ID",
    "VERSION",
    "execute_final_report_stage",
]
