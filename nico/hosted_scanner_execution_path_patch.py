from __future__ import annotations

from typing import Any

from nico.scanner_worker_artifacts import DEPENDENCY_TOOLS, SECRET_TOOLS, STATIC_TOOLS

REQUIRED_EXECUTION_TOOLS = DEPENDENCY_TOOLS + STATIC_TOOLS + SECRET_TOOLS


def _category(tool: str) -> str:
    if tool in DEPENDENCY_TOOLS:
        return "dependency"
    if tool in STATIC_TOOLS:
        return "static"
    if tool in SECRET_TOOLS:
        return "secret"
    return "unknown"


def _tool_stub(tool: str, status: str, reason: str) -> dict[str, Any]:
    return {
        "tool": tool,
        "status": status,
        "category": _category(tool),
        "reason": reason,
        "findings": [],
        "findings_count": 0,
        "current_run": False,
        "verified_for_this_report": False,
        "execution_source": "hosted_scanner_worker",
    }


def _ensure_tool_records(artifact: dict[str, Any]) -> dict[str, Any]:
    tools = artifact.setdefault("tools", {})
    if not isinstance(tools, dict):
        tools = {}
        artifact["tools"] = tools
    state = str(artifact.get("worker_execution_state") or "unknown")
    notes = artifact.get("unavailable_data_notes") if isinstance(artifact.get("unavailable_data_notes"), list) else []
    reason = "; ".join(str(item) for item in notes if item) or f"Hosted scanner worker state={state}; no tool output was attached."
    for tool in REQUIRED_EXECUTION_TOOLS:
        if not isinstance(tools.get(tool), dict):
            tools[tool] = _tool_stub(tool, "unavailable", reason)
    records: list[dict[str, Any]] = []
    generated_at = bool(artifact.get("generated_at"))
    for tool in REQUIRED_EXECUTION_TOOLS:
        payload = tools.get(tool)
        if not isinstance(payload, dict):
            continue
        status = str(payload.get("status") or "unavailable")
        findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
        payload.setdefault("current_run", generated_at and status in {"completed", "unavailable", "failed", "timeout"})
        payload.setdefault("verified_for_this_report", generated_at and status == "completed")
        payload.setdefault("findings_count", len(findings))
        records.append(
            {
                "tool": tool,
                "category": payload.get("category") or _category(tool),
                "status": status,
                "returncode": payload.get("returncode"),
                "findings_count": payload.get("findings_count", len(findings)),
                "current_run": payload.get("current_run"),
                "verified_for_this_report": payload.get("verified_for_this_report"),
                "reason": payload.get("reason") or payload.get("failure_or_unavailable_reason") or payload.get("stderr") or "",
            }
        )
    artifact["tool_records"] = records
    return artifact


def _patch_worker_artifact_tool_stubs() -> None:
    from nico import hosted_scanner_worker

    original = getattr(hosted_scanner_worker, "_nico_original_run_hosted_scanner_worker_execution_path", None)
    if original is None:
        original = hosted_scanner_worker.run_hosted_scanner_worker
        hosted_scanner_worker._nico_original_run_hosted_scanner_worker_execution_path = original

    def run_hosted_scanner_worker_with_complete_tool_shape(payload: dict[str, Any]) -> dict[str, Any]:
        artifact = original(payload)
        if isinstance(artifact, dict):
            artifact["refresh_full_evidence_requested"] = bool(payload.get("refresh_full_evidence_requested") or "refresh-full-evidence" in str(payload.get("authorized_by") or "").lower())
            artifact["requested_flags"] = {
                "authorized": bool(payload.get("authorized")),
                "run_scanner_worker": payload.get("run_scanner_worker"),
                "scanner_worker_autorun": payload.get("scanner_worker_autorun"),
                "full_history_secret_scan": payload.get("full_history_secret_scan"),
            }
            return _ensure_tool_records(artifact)
        return artifact

    hosted_scanner_worker.run_hosted_scanner_worker = run_hosted_scanner_worker_with_complete_tool_shape


def _patch_runtime_payload_and_artifact_detection() -> None:
    from nico import hosted_full_evidence_runtime_v2

    def raw_artifact_accepting_tool_records(result: dict[str, Any]) -> dict[str, Any] | None:
        artifact = result.get("scanner_worker_artifact")
        if isinstance(artifact, dict) and isinstance(artifact.get("tools"), dict):
            return artifact
        return None

    def payload_for_result_with_refresh_flags(result: dict[str, Any]) -> dict[str, Any]:
        metadata = result.get("repository_metadata") if isinstance(result.get("repository_metadata"), dict) else {}
        payload = {
            "repository": str(result.get("repository") or result.get("repo") or "").strip(),
            "authorized": True,
            "authorized_by": str(result.get("authorized_by") or "frontend-refresh-full-evidence"),
            "refresh_full_evidence_requested": True,
            "full_history_secret_scan": True,
            "run_scanner_worker": True,
            "scanner_worker_autorun": True,
        }
        default_branch = metadata.get("default_branch")
        if default_branch:
            payload["default_branch"] = default_branch
        return payload

    hosted_full_evidence_runtime_v2._raw_artifact = raw_artifact_accepting_tool_records
    hosted_full_evidence_runtime_v2._payload_for_result = payload_for_result_with_refresh_flags


def _patch_api_request_model_contract() -> None:
    try:
        from nico.api import main as api_main
    except Exception:
        return
    request_model = getattr(api_main, "GithubAssessmentRequest", None)
    fields = getattr(request_model, "model_fields", None)
    if isinstance(fields, dict):
        # Pydantic v2 has already built the model by this point. The hosted
        # frontend still carries the explicit marker through authorized_by, so
        # this is kept as an observable compatibility note rather than mutating
        # model internals at runtime.
        setattr(request_model, "_nico_refresh_fields_documented", True)


def install_hosted_scanner_execution_path_patch() -> None:
    _patch_worker_artifact_tool_stubs()
    _patch_runtime_payload_and_artifact_detection()
    _patch_api_request_model_contract()
