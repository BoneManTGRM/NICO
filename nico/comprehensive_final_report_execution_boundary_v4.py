from __future__ import annotations

import base64
import hashlib
import os
import queue
import threading
import time
from typing import Any, Mapping

VERSION = "nico.comprehensive_final_report_execution_boundary.v4"
FINAL_REPORT_STAGE_ID = "final_comprehensive_report_generation"
DEFAULT_FINAL_REPORT_TIMEOUT_SECONDS = 240


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _timeout_seconds(value: int | None) -> int:
    if value is not None:
        return max(1, min(900, int(value)))
    try:
        configured = int(
            os.getenv(
                "NICO_COMPREHENSIVE_FINAL_REPORT_TIMEOUT_SECONDS",
                str(DEFAULT_FINAL_REPORT_TIMEOUT_SECONDS),
            )
        )
    except (TypeError, ValueError):
        configured = DEFAULT_FINAL_REPORT_TIMEOUT_SECONDS
    return max(30, min(900, configured))


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
            **dict(execution or {}),
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
    identity = (
        canonical_json.get("identity")
        if isinstance(canonical_json.get("identity"), Mapping)
        else canonical_json
    )
    if isinstance(identity, Mapping) and not _exact_identity_matches(identity, context):
        return False, "final_report_identity_mismatch", {}
    return True, "", {
        "report_id": report_id,
        "pdf_page_count": package.get("pdf_page_count"),
        "pdf_sha256": _text(package.get("pdf_sha256"))
        or hashlib.sha256(pdf).hexdigest(),
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


def _finalize_provider_result(
    value: Any,
    context: Mapping[str, Any],
    *,
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return _blocked(
            context,
            reason="final_report_provider_invalid_result",
            message="The final report provider did not return a structured result.",
            execution=execution,
        )

    output = dict(value)
    prior_execution = (
        output.get("stage_execution")
        if isinstance(output.get("stage_execution"), Mapping)
        else {}
    )
    merged_execution = {
        **dict(prior_execution),
        **dict(execution),
        "completed_within_boundary": True,
    }
    status = _text(output.get("status")).casefold()
    if status != "complete":
        output.setdefault("run_id", _text(context.get("run_id")))
        output.setdefault("repository", _text(context.get("repository")))
        output.setdefault("commit_sha", _text(context.get("commit_sha")))
        output.setdefault("evidence_ledger_id", _text(context.get("evidence_ledger_id")))
        output["human_review_required"] = True
        output["client_delivery_allowed"] = False
        output["stage_execution"] = merged_execution
        return output
    if not _exact_identity_matches(output, context):
        return _blocked(
            context,
            reason="final_report_result_identity_mismatch",
            message="The final report provider result did not match the exact run identity.",
            execution=merged_execution,
        )
    package = output.get("report_package")
    if not isinstance(package, Mapping):
        return _blocked(
            context,
            reason="final_report_package_missing",
            message="The final report provider completed without a retained report package.",
            execution=merged_execution,
        )
    valid, reason, evidence = _validate_package(package, context)
    if not valid:
        return _blocked(
            context,
            reason=reason,
            message=f"The final report package failed validation: {reason}.",
            execution=merged_execution,
        )

    output["run_id"] = _text(context.get("run_id"))
    output["repository"] = _text(context.get("repository"))
    output["commit_sha"] = _text(context.get("commit_sha"))
    output["evidence_ledger_id"] = _text(context.get("evidence_ledger_id"))
    output["report_package"] = dict(package)
    output["artifacts_available"] = True
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False
    output["stage_execution"] = {
        **merged_execution,
        "canonical_run_write_required": True,
        "artifact_validation_complete": True,
        "exact_identity_verified": True,
    }
    retained = output.get("evidence") if isinstance(output.get("evidence"), Mapping) else {}
    output["evidence"] = {**dict(retained), **evidence}
    return output


def execute_final_report_provider(
    executor,
    context: Mapping[str, Any],
    *,
    execution_mode: str = "durable_final_report_worker",
) -> dict[str, Any]:
    """Run and validate the provider without creating an unkillable timeout thread.

    Request-bound callers should not use this directly. The durable worker owns its
    lease and heartbeat while this function runs, then writes the result to the canonical
    Comprehensive record. The provider is allowed to finish rather than being orphaned
    after an HTTP timeout.
    """

    started = time.perf_counter()
    value = executor(dict(context))
    elapsed = round(time.perf_counter() - started, 3)
    return _finalize_provider_result(
        value,
        context,
        execution={
            "artifact_schema": VERSION,
            "mode": execution_mode,
            "elapsed_seconds": elapsed,
            "detached_background_execution": False,
            "durable_worker_execution": True,
            "request_lifetime_independent": True,
            "full_context_deepcopy_skipped": True,
        },
    )


def _execute_bounded(
    executor,
    context: Mapping[str, Any],
    limit: int,
) -> tuple[str, Any, float]:
    results: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
    started = time.perf_counter()

    def invoke() -> None:
        try:
            results.put_nowait(("result", executor(dict(context))))
        except BaseException as exc:
            try:
                results.put_nowait(("error", exc))
            except queue.Full:
                pass

    worker = threading.Thread(
        target=invoke,
        name="nico-atomic-final-report",
        daemon=True,
    )
    worker.start()
    worker.join(limit)
    elapsed = round(time.perf_counter() - started, 3)
    if worker.is_alive():
        return "timeout", None, elapsed
    kind, value = results.get_nowait()
    return kind, value, elapsed


def execute_final_report_stage(
    executor,
    context: Mapping[str, Any],
    *,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Legacy bounded helper retained for focused compatibility tests.

    Production run orchestration must use ``execute_final_report_provider`` through the
    durable leased worker. This helper still proves fail-closed validation but must not be
    used on the public request path because Python cannot terminate its timed-out thread.
    """

    limit = _timeout_seconds(timeout_seconds)
    kind, value, elapsed = _execute_bounded(executor, context, limit)
    execution = {
        "artifact_schema": VERSION,
        "mode": "atomic_final_report_publication",
        "execution_timeout_seconds": limit,
        "elapsed_seconds": elapsed,
        "detached_background_execution": False,
        "full_context_deepcopy_skipped": True,
    }
    if kind == "timeout":
        return _blocked(
            context,
            reason="final_report_execution_timeout",
            message=(
                f"Final report generation exceeded the {limit}-second bounded "
                "publication window."
            ),
            execution=execution,
        )
    if kind == "error":
        raise value
    return _finalize_provider_result(value, context, execution=execution)


__all__ = [
    "DEFAULT_FINAL_REPORT_TIMEOUT_SECONDS",
    "FINAL_REPORT_STAGE_ID",
    "VERSION",
    "execute_final_report_provider",
    "execute_final_report_stage",
]
