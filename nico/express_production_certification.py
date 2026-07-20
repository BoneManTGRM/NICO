from __future__ import annotations

from typing import Any, Iterable

VERSION = "nico.express_production_certification.v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _status(value: Any) -> str:
    return _text(value).casefold()


def _sha(value: Any) -> str:
    candidate = _text(value).lower()
    return candidate if len(candidate) == 40 and all(char in "0123456789abcdef" for char in candidate) else ""


def _run_fingerprint(result: dict[str, Any]) -> str:
    contract = result.get("express_cross_format_contract")
    if isinstance(contract, dict):
        return _text(contract.get("truth_fingerprint"))
    return ""


def _previous_same_sha_runs(result: dict[str, Any], prior_runs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    commit_sha = _sha(result.get("commit_sha") or result.get("snapshot_sha") or result.get("assessed_commit_sha"))
    if not commit_sha:
        return []
    matched: list[dict[str, Any]] = []
    for item in prior_runs:
        if not isinstance(item, dict):
            continue
        other_sha = _sha(item.get("commit_sha") or item.get("snapshot_sha") or item.get("assessed_commit_sha"))
        if other_sha == commit_sha and _status(item.get("status")) in {"complete", "completed"}:
            matched.append(item)
    return matched


def build_express_production_certification(
    result: dict[str, Any],
    *,
    prior_runs: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Build a fail-closed production certification record for one Express run."""

    commit_sha = _sha(result.get("commit_sha") or result.get("snapshot_sha") or result.get("assessed_commit_sha"))
    deployment = result.get("deployment_identity") if isinstance(result.get("deployment_identity"), dict) else {}
    persistence = result.get("persistence_truth") if isinstance(result.get("persistence_truth"), dict) else {}
    terminal = result.get("express_terminal_contract") if isinstance(result.get("express_terminal_contract"), dict) else {}
    visual = result.get("express_visual_qa") if isinstance(result.get("express_visual_qa"), dict) else {}
    artifact_review = result.get("express_artifact_inspection") if isinstance(result.get("express_artifact_inspection"), dict) else {}
    fingerprint = _run_fingerprint(result)
    same_sha = _previous_same_sha_runs(result, prior_runs)
    matching_fingerprints = [item for item in same_sha if fingerprint and _run_fingerprint(item) == fingerprint]

    deployed_sha = _sha(
        deployment.get("production_sha")
        or deployment.get("deployed_commit_sha")
        or deployment.get("commit_sha")
    )
    frontend_sha = _sha(deployment.get("frontend_sha") or deployment.get("vercel_sha"))
    backend_sha = _sha(deployment.get("backend_sha") or deployment.get("railway_sha"))

    checks = {
        "exact_snapshot_sha_present": bool(commit_sha),
        "terminal_contract_complete": _status(terminal.get("status")) == "complete",
        "frontend_deployment_sha_matches": bool(commit_sha and frontend_sha == commit_sha),
        "backend_deployment_sha_matches": bool(commit_sha and backend_sha == commit_sha),
        "production_deployment_sha_matches": bool(commit_sha and deployed_sha == commit_sha),
        "restart_retrieval_verified": persistence.get("restart_retrieval_verified") is True,
        "durable_store_verified": persistence.get("durable_store_verified") is True,
        "truth_fingerprint_present": bool(fingerprint),
        "two_completed_same_sha_runs": len(same_sha) >= 1,
        "two_run_truth_fingerprint_matches": len(matching_fingerprints) >= 1,
        "visual_qa_passed": _status(visual.get("status")) in {"pass", "complete"},
        "pdf_pages_inspected": artifact_review.get("pdf_pages_inspected") is True,
        "markdown_inspected": artifact_review.get("markdown_inspected") is True,
        "html_inspected": artifact_review.get("html_inspected") is True,
        "json_inspected": artifact_review.get("json_inspected") is True,
        "safe_api_inspected": artifact_review.get("safe_api_inspected") is True,
        "reviewer_record_inspected": artifact_review.get("reviewer_record_inspected") is True,
        "progress_ui_inspected": artifact_review.get("progress_ui_inspected") is True,
    }
    missing = [name for name, passed in checks.items() if not passed]
    certification = {
        "status": "certified_pending_human_review" if not missing else "not_certified",
        "version": VERSION,
        "commit_sha": commit_sha or None,
        "deployment_sha": deployed_sha or None,
        "frontend_sha": frontend_sha or None,
        "backend_sha": backend_sha or None,
        "truth_fingerprint": fingerprint or None,
        "same_sha_prior_completed_runs": len(same_sha),
        "same_fingerprint_prior_runs": len(matching_fingerprints),
        "checks": checks,
        "missing_requirements": missing,
        "fail_closed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    result["express_production_certification"] = certification
    return certification


__all__ = ["VERSION", "build_express_production_certification"]
