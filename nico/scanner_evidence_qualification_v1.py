from __future__ import annotations

from typing import Any, Iterable

from nico.scanner_evidence_pipeline_v1 import REQUIRED_EVIDENCE_TOOLS

VERSION = "nico.scanner_evidence_qualification.v1"
_PATCH_MARKER = "_nico_scanner_evidence_qualification_v1"


def _tool_blockers(name: str, payload: dict[str, Any], retained: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    status = str(payload.get("status") or "missing")
    if status != "completed":
        blockers.append(f"status:{status}")
    if payload.get("verified_for_this_report") is not True:
        blockers.append("not_verified_for_report")
    if payload.get("output_capture_complete") is not True:
        blockers.append("output_capture_incomplete")
    if payload.get("timed_out") is True:
        blockers.append("timed_out")
    if payload.get("returncode_valid") is False:
        blockers.append("invalid_returncode")
    artifact = retained.get(name) if isinstance(retained.get(name), dict) else {}
    if not artifact:
        blockers.append("retained_artifact_missing")
    else:
        if not artifact.get("storage_key"):
            blockers.append("storage_key_missing")
        if not artifact.get("sha256"):
            blockers.append("sha256_missing")
        if not artifact.get("gzip_sha256"):
            blockers.append("gzip_sha256_missing")
        if not artifact.get("raw_format"):
            blockers.append("raw_format_missing")
        if artifact.get("redacted") is not True:
            blockers.append("artifact_not_redacted")
    if payload.get("scans_git_history") is True and payload.get("full_history_verified") is not True:
        blockers.append("full_history_unverified")
    return blockers


def qualify_scanner_evidence(
    artifact: dict[str, Any],
    *,
    required_tools: Iterable[str] = REQUIRED_EVIDENCE_TOOLS,
) -> dict[str, Any]:
    tools = artifact.get("tools") if isinstance(artifact.get("tools"), dict) else {}
    retained = artifact.get("raw_artifacts") if isinstance(artifact.get("raw_artifacts"), dict) else {}
    required = tuple(required_tools)
    per_tool: dict[str, Any] = {}
    blocking_tools: list[str] = []
    for name in required:
        payload = tools.get(name) if isinstance(tools.get(name), dict) else {}
        blockers = _tool_blockers(name, payload, retained)
        per_tool[name] = {
            "ready": not blockers,
            "status": str(payload.get("status") or "missing"),
            "blockers": blockers,
            "reason": str(payload.get("failure_or_unavailable_reason") or payload.get("reason") or ""),
            "deterministic_fingerprint": payload.get("deterministic_fingerprint"),
        }
        if blockers:
            blocking_tools.append(name)

    target = str(artifact.get("target_commit_sha") or "")
    checkout = artifact.get("checkout") if isinstance(artifact.get("checkout"), dict) else {}
    checkout_sha = str(checkout.get("commit_sha") or "")
    application = str(artifact.get("application_commit_sha") or "")
    provenance_blockers: list[str] = []
    if not target:
        provenance_blockers.append("target_commit_missing")
    if checkout_sha and target and checkout_sha != target:
        provenance_blockers.append("checkout_commit_mismatch")
    if application and target and application != target:
        provenance_blockers.append("application_commit_mismatch")
    if artifact.get("provenance_verified") is not True:
        provenance_blockers.append("provenance_not_verified")

    ready = not blocking_tools and not provenance_blockers
    result = {
        "schema": VERSION,
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "required_tools": list(required),
        "blocking_tools": blocking_tools,
        "tool_readiness": per_tool,
        "provenance": {
            "target_commit_sha": target,
            "checkout_commit_sha": checkout_sha,
            "application_commit_sha": application,
            "verified": not provenance_blockers,
            "blockers": provenance_blockers,
        },
        "missing_evidence_is_not_clean": True,
    }
    artifact["scanner_evidence_qualification"] = result
    artifact["scanner_evidence_ready"] = ready
    if not ready:
        artifact["human_review_required"] = True
        artifact["client_delivery_allowed"] = False
        artifact["worker_execution_state"] = "partial"
    return result


def compare_frozen_runs(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    first_q = qualify_scanner_evidence(first)
    second_q = qualify_scanner_evidence(second)
    required = tuple(first_q["required_tools"])
    fingerprint_mismatches = [
        name
        for name in required
        if first_q["tool_readiness"][name].get("deterministic_fingerprint")
        != second_q["tool_readiness"][name].get("deterministic_fingerprint")
    ]
    target_match = first_q["provenance"]["target_commit_sha"] == second_q["provenance"]["target_commit_sha"]
    equivalent = first_q["ready"] and second_q["ready"] and target_match and not fingerprint_mismatches
    return {
        "schema": "nico.scanner_evidence_repeatability.v1",
        "equivalent": equivalent,
        "two_consecutive_clean_runs": first_q["ready"] and second_q["ready"],
        "target_commit_equal": target_match,
        "fingerprint_mismatches": fingerprint_mismatches,
    }


def install_scanner_evidence_qualification_v1() -> dict[str, Any]:
    from nico import hosted_scanner_worker

    if getattr(hosted_scanner_worker, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}
    original = hosted_scanner_worker.run_hosted_scanner_worker

    def qualified_worker(payload: dict[str, Any]) -> dict[str, Any]:
        artifact = original(payload)
        if isinstance(artifact, dict):
            qualify_scanner_evidence(artifact)
        return artifact

    hosted_scanner_worker.run_hosted_scanner_worker = qualified_worker
    setattr(hosted_scanner_worker, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "version": VERSION,
        "blocking_tool_diagnostics": True,
        "retained_artifact_integrity_required": True,
        "exact_commit_provenance_required": True,
        "missing_evidence_is_not_clean": True,
        "client_delivery_blocked_when_incomplete": True,
    }


__all__ = [
    "VERSION",
    "qualify_scanner_evidence",
    "compare_frozen_runs",
    "install_scanner_evidence_qualification_v1",
]
