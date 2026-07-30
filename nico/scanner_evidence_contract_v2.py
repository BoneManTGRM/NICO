from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Callable

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
    }


def _run_scanner_tool(
    spec: scanner_module.ScannerToolSpec,
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult] = run_command,
    preparation: scanner_module.ProjectCommandPreparation | None = None,
) -> dict[str, Any]:
    assert _ORIGINAL_RUN_SCANNER_TOOL is not None
    raw = _ORIGINAL_RUN_SCANNER_TOOL(
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
        history = _git_history_evidence(workspace)
        result["full_history_verified"] = history["verified"]
        result["history_checkout_shallow"] = history["shallow"]
        result["history_head_verified"] = history["head_verified"]
        if result.get("status") == "completed" and not history["verified"]:
            result["status"] = "partial"
            result["verified_for_this_report"] = False
            result["reason"] = history["reason"] or "full Git history was not verified"
    else:
        result["full_history_verified"] = False

    evidence_projection = {
        key: value
        for key, value in result.items()
        if key not in {"artifact_hash", "deterministic_fingerprint"}
    }
    fingerprint = _canonical_hash(evidence_projection)
    result["deterministic_fingerprint"] = fingerprint
    result["artifact_hash"] = fingerprint
    result["artifact_hash_scope"] = "redacted_normalized_scanner_record"
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
    return scanner_module.redact_payload(result)


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
    }


__all__ = ["VERSION", "install_scanner_evidence_contract_v2"]
