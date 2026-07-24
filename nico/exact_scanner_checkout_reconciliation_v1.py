from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.exact_scanner_checkout_reconciliation.v1"
_NORMALIZE_MARKER = "_nico_exact_scanner_checkout_normalize_v1"
_BIND_MARKER = "_nico_exact_scanner_checkout_bind_v1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _safe_checkout(payload: dict[str, Any]) -> dict[str, Any]:
    checkout = payload.get("checkout") if isinstance(payload.get("checkout"), dict) else {}
    commit_sha = str(checkout.get("commit_sha") or "").strip().lower()
    return {
        "commit_sha": commit_sha if _SHA_RE.fullmatch(commit_sha) else "",
        "returncode": checkout.get("returncode"),
        "timed_out": bool(checkout.get("timed_out")),
        "output_truncated": bool(checkout.get("output_truncated")),
        "history_depth": str(checkout.get("history_depth") or ""),
        "full_history_secret_scan_requested": bool(
            checkout.get("full_history_secret_scan_requested")
        ),
        "commit_count": checkout.get("commit_count"),
        "auth_mode": str(checkout.get("auth_mode") or ""),
    }


def _checkout_sha_from_result(result: dict[str, Any], expected: str) -> str:
    if result.get("scanner_worker_auto_ran") is not True:
        return ""
    artifact = (
        result.get("scanner_worker_artifact")
        if isinstance(result.get("scanner_worker_artifact"), dict)
        else {}
    )
    checkout = artifact.get("checkout") if isinstance(artifact.get("checkout"), dict) else {}
    observed = str(checkout.get("commit_sha") or "").strip().lower()
    execution_state = str(artifact.get("worker_execution_state") or "").strip().lower()
    if execution_state != "completed":
        return ""
    if not _SHA_RE.fullmatch(observed) or observed != expected:
        return ""
    return observed


def install_exact_scanner_checkout_reconciliation_v1() -> dict[str, Any]:
    """Retain worker checkout identity and reconcile it at the exact-commit gate.

    The hosted worker already records ``checkout.commit_sha`` after ``git rev-parse
    HEAD``. Earlier normalization discarded that safe identity, so the outer exact-
    commit gate could see an empty thread-local value and block a valid auto-run.
    This repair accepts only a completed, locally auto-run worker artifact whose
    retained checkout SHA exactly equals the canonical assessment SHA.
    """

    from nico import exact_commit_binding as binding
    from nico import hosted_scanner_artifacts as hosted

    current_normalize: Callable[[dict[str, Any]], dict[str, Any]] = (
        hosted.normalize_scanner_worker_artifact
    )
    current_bind: Callable[..., dict[str, Any]] = binding._bind_result

    normalize_installed = bool(getattr(current_normalize, _NORMALIZE_MARKER, False))
    bind_installed = bool(getattr(current_bind, _BIND_MARKER, False))
    if normalize_installed and bind_installed:
        return {
            "status": "already_installed",
            "version": VERSION,
            "checkout_identity_retained": True,
            "completed_autorun_required": True,
            "exact_sha_match_required": True,
            "mismatched_or_untrusted_artifacts_blocked": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    if not normalize_installed:
        @wraps(current_normalize)
        def normalize_with_checkout(payload: dict[str, Any]) -> dict[str, Any]:
            normalized = current_normalize(payload)
            normalized["checkout"] = _safe_checkout(payload)
            normalized["worker_execution_state"] = str(
                payload.get("worker_execution_state") or ""
            )
            normalized["scanner_run_id"] = str(payload.get("run_id") or "")
            normalized["artifact_hash"] = str(payload.get("artifact_hash") or "")
            return normalized

        setattr(normalize_with_checkout, _NORMALIZE_MARKER, True)
        setattr(normalize_with_checkout, "_nico_previous", current_normalize)
        hosted.normalize_scanner_worker_artifact = normalize_with_checkout

    if not bind_installed:
        @wraps(current_bind)
        def bind_with_retained_checkout(
            result: dict[str, Any],
            *,
            repository: str,
            commit_sha: str,
            requested_sha: str,
            scanner_checkout_sha: str,
            resolution: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            reconciled = str(scanner_checkout_sha or "").strip().lower()
            if not reconciled:
                reconciled = _checkout_sha_from_result(result, commit_sha)
            return current_bind(
                result,
                repository=repository,
                commit_sha=commit_sha,
                requested_sha=requested_sha,
                scanner_checkout_sha=reconciled,
                resolution=resolution,
            )

        setattr(bind_with_retained_checkout, _BIND_MARKER, True)
        setattr(bind_with_retained_checkout, "_nico_previous", current_bind)
        binding._bind_result = bind_with_retained_checkout

    return {
        "status": "installed",
        "version": VERSION,
        "checkout_identity_retained": True,
        "completed_autorun_required": True,
        "exact_sha_match_required": True,
        "mismatched_or_untrusted_artifacts_blocked": True,
        "thread_local_only_dependency_removed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_checkout_sha_from_result",
    "install_exact_scanner_checkout_reconciliation_v1",
]
