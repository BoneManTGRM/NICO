from __future__ import annotations

from typing import Any

from nico.hosted_scanner_worker import run_hosted_scanner_worker
from nico.scanner_worker_artifacts import DEPENDENCY_TOOLS, SECRET_TOOLS, STATIC_TOOLS, normalize_scanner_worker_artifact

REQUIRED_SECTION_TOOLS = DEPENDENCY_TOOLS + STATIC_TOOLS + SECRET_TOOLS


def _repo(result: dict[str, Any]) -> str:
    return str(result.get("repository") or result.get("repo") or "").strip()


def _explicit_refresh_requested(result: dict[str, Any]) -> bool:
    if result.get("refresh_full_evidence_requested") is True:
        return True
    marker = str(result.get("authorized_by") or "").lower()
    return "frontend-refresh-full-evidence" in marker or "refresh-full-evidence" in marker


def _raw_artifact(result: dict[str, Any]) -> dict[str, Any] | None:
    artifact = result.get("scanner_worker_artifact")
    if isinstance(artifact, dict) and isinstance(artifact.get("tools"), dict):
        tools = artifact.get("tools") or {}
        if any(isinstance(payload, dict) and "findings" in payload for payload in tools.values()):
            return artifact
    return None


def _missing_required_tools(result: dict[str, Any]) -> list[str]:
    artifact = _raw_artifact(result)
    if not artifact:
        return list(REQUIRED_SECTION_TOOLS)
    normalized = normalize_scanner_worker_artifact(artifact)
    missing: list[str] = []
    missing.extend(normalized.get("missing_dependency_tools") or [])
    missing.extend(normalized.get("missing_static_tools") or [])
    missing.extend(normalized.get("missing_secret_tools") or [])
    return [str(item) for item in missing]


def _guard(result: dict[str, Any], status: str, **extra: Any) -> None:
    result.setdefault("report_quality_guards", {})["hosted_full_evidence_runtime"] = {
        "status": status,
        "refresh_full_evidence_requested": _explicit_refresh_requested(result),
        "repository": _repo(result),
        "missing_required_tools": _missing_required_tools(result),
        "guardrail": "Refresh Full Evidence is diagnostic and evidence-bound: it only turns yellow sections green when the hosted worker actually returns current-run scanner and complexity artifacts.",
        **extra,
    }


def _should_refresh(result: dict[str, Any]) -> bool:
    if result.get("status") != "complete":
        _guard(result, "skipped_not_complete")
        return False
    if not _explicit_refresh_requested(result):
        _guard(result, "skipped_no_explicit_refresh_request")
        return False
    repository = _repo(result)
    if not repository or "/" not in repository:
        _guard(result, "skipped_invalid_repository")
        return False
    missing = _missing_required_tools(result)
    if not missing:
        _guard(result, "skipped_all_required_tools_already_present")
        return False
    _guard(result, "queued", missing_required_tools=missing)
    return True


def _payload_for_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "repository": _repo(result),
        "authorized": True,
        "authorized_by": str(result.get("authorized_by") or "refresh-full-evidence"),
        "full_history_secret_scan": True,
        "run_scanner_worker": True,
        "scanner_worker_autorun": True,
    }


def _attach_raw_artifact(result: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_scanner_worker_artifact(artifact)
    result["scanner_worker_artifact"] = artifact
    result["scanner_worker_artifact_normalized"] = normalized
    result["scanner_worker_evidence_attached"] = True
    result["scanner_worker_auto_ran"] = True
    result.setdefault("report_quality_guards", {})["hosted_full_evidence_runtime"] = {
        "status": artifact.get("worker_execution_state") or "attempted",
        "refresh_full_evidence_requested": _explicit_refresh_requested(result),
        "completed_dependency_tools": normalized.get("dependency_tools_completed"),
        "completed_static_tools": normalized.get("static_tools_completed"),
        "completed_secret_tools": normalized.get("secret_tools_completed"),
        "missing_dependency_tools": normalized.get("missing_dependency_tools"),
        "missing_static_tools": normalized.get("missing_static_tools"),
        "missing_secret_tools": normalized.get("missing_secret_tools"),
        "guardrail": "Refresh attaches only output returned by the worker. Missing tools and findings remain visible.",
    }
    if artifact.get("secret_history_scan"):
        result["secret_history_scan"] = artifact["secret_history_scan"]
    if artifact.get("complexity_engine"):
        result["complexity_engine"] = artifact["complexity_engine"]
    return result


def ensure_hosted_runtime_evidence(result: dict[str, Any]) -> dict[str, Any]:
    """Collect runtime evidence only for explicit Refresh Full Evidence requests."""
    if not _should_refresh(result):
        return result
    try:
        artifact = run_hosted_scanner_worker(_payload_for_result(result))
    except Exception as exc:  # pragma: no cover - defensive reporting path
        _guard(result, "failed_exception", error=str(exc))
        return result
    if not isinstance(artifact, dict):
        _guard(result, "failed_no_artifact")
        return result
    return _attach_raw_artifact(result, artifact)
