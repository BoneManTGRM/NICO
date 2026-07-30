from __future__ import annotations

import hashlib
import inspect
import json
from copy import deepcopy
from typing import Any, Callable, Mapping

import nico.scanner_tool_runners as scanner_module
from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace, run_command

VERSION = "nico.scanner-evidence-contract.v2"
_ORIGINAL_RUN_SCANNER_TOOL: Callable[..., dict[str, Any]] | None = None
_INSTALLED = False


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _git_history_evidence(workspace: WorkerWorkspace) -> dict[str, Any]:
    """Prove that a scanner had a complete local Git history before calling it history-aware."""
    repo_dir = workspace.repo_dir
    git_dir = repo_dir / ".git"
    if not git_dir.exists():
        return {
            "verified": False,
            "reason": "checked-out repository does not contain Git metadata",
            "shallow": None,
            "head_verified": False,
            "source": "local_git_probe",
        }

    shallow_result = run_command(
        ("git", "rev-parse", "--is-shallow-repository"),
        cwd=repo_dir,
        limits=WorkerLimits(timeout_seconds=20, max_output_chars=2_000),
    )
    head_result = run_command(
        ("git", "cat-file", "-e", "HEAD^{commit}"),
        cwd=repo_dir,
        limits=WorkerLimits(timeout_seconds=20, max_output_chars=2_000),
    )
    shallow_text = (shallow_result.stdout or "").strip().casefold()
    shallow = shallow_text == "true"
    shallow_known = shallow_text in {"true", "false"}
    head_verified = head_result.returncode == 0 and not head_result.timed_out
    verified = (
        shallow_result.returncode == 0
        and not shallow_result.timed_out
        and shallow_known
        and not shallow
        and head_verified
    )
    reasons: list[str] = []
    if shallow_result.timed_out or head_result.timed_out:
        reasons.append("Git history verification timed out")
    if not shallow_known:
        reasons.append("Git shallow-state verification was inconclusive")
    elif shallow:
        reasons.append("repository checkout is shallow")
    if not head_verified:
        reasons.append("HEAD commit object was not verified")
    return {
        "verified": verified,
        "reason": "; ".join(reasons),
        "shallow": shallow if shallow_known else None,
        "head_verified": head_verified,
        "source": "local_git_probe",
    }


def _trusted_upstream_history_evidence(result: Mapping[str, Any]) -> dict[str, Any] | None:
    """Recognize the existing fail-closed history guard without re-probing fixtures.

    ``scanner_history_truth`` verifies or expands the checkout before invoking a history
    scanner, then emits a redundant proof tuple. The terminal evidence wrapper may trust
    that tuple only when every positive field agrees. A lone boolean is never sufficient.
    """
    full_verified = result.get("full_history_verified") is True
    depth_verified = result.get("history_depth_verified") is True
    depth = str(result.get("history_depth") or "").strip().casefold()
    scope = str(result.get("history_scope") or "").strip().casefold()
    if not (
        full_verified
        and depth_verified
        and depth == "full"
        and scope == "full_git_history"
    ):
        return None
    return {
        "verified": True,
        "reason": str(result.get("history_verification_note") or "Full Git history was verified by the upstream history guard."),
        "shallow": False,
        "head_verified": True,
        "source": "upstream_scanner_history_truth_guard",
    }


def _invoke_original(
    spec: scanner_module.ScannerToolSpec,
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult],
    preparation: scanner_module.ProjectCommandPreparation | None,
) -> dict[str, Any]:
    """Call whichever scanner wrapper is installed without breaking legacy signatures."""
    assert _ORIGINAL_RUN_SCANNER_TOOL is not None
    kwargs: dict[str, Any] = {"runner": runner}
    try:
        parameters = inspect.signature(_ORIGINAL_RUN_SCANNER_TOOL).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "preparation" in parameters:
        kwargs["preparation"] = preparation
    return _ORIGINAL_RUN_SCANNER_TOOL(spec, workspace, **kwargs)


def _run_scanner_tool(
    spec: scanner_module.ScannerToolSpec,
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult] = run_command,
    preparation: scanner_module.ProjectCommandPreparation | None = None,
) -> dict[str, Any]:
    raw = _invoke_original(
        spec,
        workspace,
        runner=runner,
        preparation=preparation,
    )
    result = deepcopy(dict(raw))
    result["scanner_evidence_contract_version"] = VERSION
    result["execution_observed_for_this_report"] = True
    result["current_run"] = True
    result["findings_count"] = len(result.get("findings") or [])

    if spec.scans_git_history:
        history = _trusted_upstream_history_evidence(result) or _git_history_evidence(workspace)
        result["full_history_verified"] = history["verified"]
        result["history_depth_verified"] = history["verified"]
        result["history_checkout_shallow"] = history["shallow"]
        result["history_head_verified"] = history["head_verified"]
        result["history_verification_source"] = history["source"]
        if history["verified"]:
            result["history_depth"] = "full"
            result["history_scope"] = "full_git_history"
            result.setdefault("history_verification_note", history["reason"])
        elif result.get("status") == "completed":
            result["status"] = "partial"
            result["verified_for_this_report"] = False
            result["reason"] = history["reason"] or "full Git history was not verified"
            result["failure_or_unavailable_reason"] = result["reason"]
    else:
        result["full_history_verified"] = False

    result["raw_artifact_retention_complete"] = bool(
        result.get("output_capture_complete") is True
        and not result.get("output_truncated")
        and result.get("status") in {"completed", "partial"}
    )
    result["verified_complete"] = bool(
        result.get("status") == "completed"
        and result.get("verified_for_this_report") is True
        and result["raw_artifact_retention_complete"]
        and (not spec.scans_git_history or result.get("full_history_verified") is True)
    )

    # Redact first, then fingerprint the exact report-safe record. This prevents a
    # hash from claiming the scope of a returned payload that differs from what was
    # actually hashed and keeps the identity independently reproducible downstream.
    safe_result = scanner_module.redact_payload(result)
    safe_result["artifact_hash_scope"] = "redacted_normalized_scanner_record"
    evidence_projection = {
        key: value
        for key, value in safe_result.items()
        if key not in {"artifact_hash", "deterministic_fingerprint"}
    }
    fingerprint = _canonical_hash(evidence_projection)
    safe_result["deterministic_fingerprint"] = fingerprint
    safe_result["artifact_hash"] = fingerprint
    return safe_result


def install_scanner_evidence_contract_v2() -> dict[str, Any]:
    global _INSTALLED, _ORIGINAL_RUN_SCANNER_TOOL
    if _INSTALLED:
        return {"status": "already_installed", "version": VERSION}

    _ORIGINAL_RUN_SCANNER_TOOL = scanner_module.run_scanner_tool
    scanner_module.run_scanner_tool = _run_scanner_tool
    _INSTALLED = True
    return {
        "status": "installed",
        "version": VERSION,
        "history_scanners_fail_closed": True,
        "deterministic_record_hash_required": True,
        "raw_capture_required_for_verified_complete": True,
        "legacy_wrapper_signature_compatible": True,
        "upstream_history_guard_proof_requires_redundant_fields": True,
        "hash_is_computed_after_redaction": True,
    }


__all__ = ["VERSION", "install_scanner_evidence_contract_v2"]