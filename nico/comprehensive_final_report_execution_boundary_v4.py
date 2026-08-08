from __future__ import annotations

import base64
import hashlib
import os
import queue
import threading
import time
from typing import Any, Mapping

from nico.comprehensive_final_report_compact_base_v1 import (
    install_comprehensive_final_report_compact_base_v1,
)

VERSION = "nico.comprehensive_final_report_execution_boundary.v7"
FINAL_REPORT_STAGE_ID = "final_comprehensive_report_generation"
DEFAULT_FINAL_REPORT_TIMEOUT_SECONDS = 600
MIN_CONFIGURED_FINAL_REPORT_TIMEOUT_SECONDS = 30
MAX_FINAL_REPORT_TIMEOUT_SECONDS = 900
_IDENTITY_FIELDS = ("run_id", "repository", "commit_sha", "evidence_ledger_id")


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _timeout_seconds(value: int | None) -> int:
    if value is not None:
        return max(1, min(MAX_FINAL_REPORT_TIMEOUT_SECONDS, int(value)))
    try:
        configured = int(
            os.getenv(
                "NICO_COMPREHENSIVE_FINAL_REPORT_TIMEOUT_SECONDS",
                str(DEFAULT_FINAL_REPORT_TIMEOUT_SECONDS),
            )
        )
    except (TypeError, ValueError):
        configured = DEFAULT_FINAL_REPORT_TIMEOUT_SECONDS
    return max(
        MIN_CONFIGURED_FINAL_REPORT_TIMEOUT_SECONDS,
        min(MAX_FINAL_REPORT_TIMEOUT_SECONDS, configured),
    )


def _blocked(
    context: Mapping[str, Any],
    *,
    reason: str,
    message: str,
    execution: Mapping[str, Any] | None = None,
    recovery_supported: bool = False,
    recovery_scope: str | None = None,
) -> dict[str, Any]:
    retained_execution = dict(execution or {})
    blocked = {
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
            **retained_execution,
            "artifact_schema": VERSION,
            "mode": "atomic_final_report_publication",
            "canonical_run_write_required": True,
            "detached_background_execution": bool(
                retained_execution.get("detached_background_execution")
            ),
        },
    }
    if recovery_supported:
        blocked["recovery_supported"] = True
        blocked["recovery_scope"] = recovery_scope or "final_report_only"
        blocked["stage_execution"]["recovery_supported"] = True
        blocked["stage_execution"]["recovery_scope"] = (
            recovery_scope or "final_report_only"
        )
    return blocked


def _exact_identity_matches(
    value: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    require_present: bool,
) -> bool:
    for field in _IDENTITY_FIELDS:
        expected = _text(context.get(field))
        observed = _text(value.get(field))
        if not expected:
            return False
        if require_present and not observed:
            return False
        if observed and observed != expected:
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
    canonical_truth_sha256 = _text(package.get("canonical_truth_sha256"))
    if not report_id:
        return False, "final_report_id_missing", {}
    if not markdown.strip():
        return False, "final_report_markdown_missing", {}
    if not rendered_html.strip():
        return False, "final_report_html_missing", {}
    if not isinstance(canonical_json, Mapping):
        return False, "final_report_json_missing", {}
    if not canonical_truth_sha256:
        return False, "final_report_canonical_hash_missing", {}
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
    if not isinstance(identity, Mapping):
        return False, "final_report_identity_missing", {}
    if not _exact_identity_matches(identity, context, require_present=True):
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
        "canonical_truth_sha256": canonical_truth_sha256,
        "exact_run_identity_verified": True,
        "exact_repository_identity_verified": True,
        "exact_commit_identity_verified": True,
        "exact_evidence_ledger_identity_verified": True,
        "pdf_valid": True,
        "markdown_available": True,
        "html_available": True,
        "json_available": True,
    }


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


def _execute_background_owned(
    executor,
    context: Mapping[str, Any],
) -> tuple[str, Any, float]:
    """Execute on the durable coordinator's tracked worker without nesting a timer thread.

    A Python thread cannot be safely terminated after a join timeout. Creating a second
    inner thread under the durable publication worker allowed a timed-out provider to
    continue consuming the single production process after the canonical run had been
    marked blocked. The durable coordinator already owns lifecycle, heartbeat, restart
    recovery, and exact-run publication, so its tracked worker must own the provider
    call directly.
    """

    started = time.perf_counter()
    try:
        value = executor(dict(context))
    except BaseException as exc:
        return "error", exc, round(time.perf_counter() - started, 3)
    return "result", value, round(time.perf_counter() - started, 3)


def execute_final_report_stage(
    executor,
    context: Mapping[str, Any],
    *,
    timeout_seconds: int | None = None,
    background_worker_owned: bool = False,
) -> dict[str, Any]:
    """Generate, validate, and return one exact final package for atomic run storage.

    Synchronous callers retain the bounded worker-thread contract. The durable
    background publication coordinator sets ``background_worker_owned`` so it invokes
    the provider on its already tracked worker and never leaves an untracked timeout
    thread running after a canonical blocked result.
    """

    if background_worker_owned:
        limit: int | None = None
        kind, value, elapsed = _execute_background_owned(executor, context)
    else:
        limit = _timeout_seconds(timeout_seconds)
        kind, value, elapsed = _execute_bounded(executor, context, limit)
    execution = {
        "artifact_schema": VERSION,
        "mode": "atomic_final_report_publication",
        "execution_timeout_seconds": limit,
        "elapsed_seconds": elapsed,
        "detached_background_execution": background_worker_owned,
        "background_worker_owned": background_worker_owned,
        "provider_thread_owned_by_background_coordinator": background_worker_owned,
        "nested_timeout_worker_created": not background_worker_owned,
        "timeout_boundary": (
            "durable_background_coordinator"
            if background_worker_owned
            else "bounded_worker_thread"
        ),
        "full_context_deepcopy_skipped": True,
        "compact_intermediate_pdf_projection_installed": True,
    }
    if kind == "timeout":
        return _blocked(
            context,
            reason="final_report_execution_timeout",
            message=(
                f"Final report generation exceeded the {limit}-second bounded "
                "publication window. The exact run may resume from final report "
                "generation without rerunning completed scanners."
            ),
            execution=execution,
            recovery_supported=True,
            recovery_scope="final_report_only",
        )
    if kind == "error":
        raise value
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
    execution = {
        **dict(prior_execution),
        **execution,
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
        output["stage_execution"] = execution
        return output
    if not _exact_identity_matches(output, context, require_present=False):
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
    output["report_package"] = dict(package)
    output["artifacts_available"] = True
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False
    output["stage_execution"] = {
        **execution,
        "canonical_run_write_required": True,
        "canonical_run_written_only_by_request_thread": not background_worker_owned,
        "artifact_validation_complete": True,
        "exact_identity_verified": True,
    }
    retained = (
        output.get("evidence") if isinstance(output.get("evidence"), Mapping) else {}
    )
    output["evidence"] = {**dict(retained), **evidence}
    return output


install_comprehensive_final_report_compact_base_v1()


__all__ = [
    "DEFAULT_FINAL_REPORT_TIMEOUT_SECONDS",
    "FINAL_REPORT_STAGE_ID",
    "MAX_FINAL_REPORT_TIMEOUT_SECONDS",
    "MIN_CONFIGURED_FINAL_REPORT_TIMEOUT_SECONDS",
    "VERSION",
    "execute_final_report_stage",
]
