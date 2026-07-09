from __future__ import annotations

from collections import Counter
from typing import Any


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _finding_count(payload: dict[str, Any]) -> int:
    findings = payload.get("findings")
    if isinstance(findings, list):
        return len(findings)
    for key in ("findings_count", "finding_count", "issue_count"):
        count = payload.get(key)
        if isinstance(count, int):
            return count
    return 0


def _bandit_triage_status(finding: dict[str, Any]) -> str:
    severity = str(finding.get("issue_severity") or finding.get("severity") or "unknown").lower()
    confidence = str(finding.get("issue_confidence") or finding.get("confidence") or "unknown").lower()
    if severity in {"high", "medium"}:
        return "blocker"
    if confidence == "high":
        return "blocker"
    return "needs-review"


def build_bandit_triage(findings: list[Any]) -> list[dict[str, Any]]:
    triage: list[dict[str, Any]] = []
    for index, raw in enumerate(findings, start=1):
        finding = raw if isinstance(raw, dict) else {"issue_text": str(raw)}
        status = _bandit_triage_status(finding)
        triage.append(
            {
                "finding_id": str(finding.get("test_id") or finding.get("issue_cwe", {}).get("id") if isinstance(finding.get("issue_cwe"), dict) else "") or f"bandit-{index}"),
                "rule_id": str(finding.get("test_id") or finding.get("test_name") or "unknown"),
                "filename": str(finding.get("filename") or finding.get("file") or "unknown"),
                "line_number": _as_int(finding.get("line_number") or finding.get("line")),
                "severity": str(finding.get("issue_severity") or finding.get("severity") or "unknown"),
                "confidence": str(finding.get("issue_confidence") or finding.get("confidence") or "unknown"),
                "issue_text": str(finding.get("issue_text") or finding.get("message") or finding.get("text") or ""),
                "triage_status": status,
                "triage_reason": "Automatic current-run triage. Treat as blocking until manually approved or fixed." if status == "blocker" else "Automatic current-run triage. Needs human review before it can be treated as non-blocking.",
                "approved_by": None,
            }
        )
    return triage


def summarize_bandit_triage(triage: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(item.get("triage_status") or "unknown") for item in triage)
    return {
        "total_findings": len(triage),
        "blocker_count": counts.get("blocker", 0),
        "needs_review_count": counts.get("needs-review", 0),
        "accepted_risk_count": counts.get("accepted-risk", 0),
        "false_positive_count": counts.get("false-positive", 0),
        "fixed_count": counts.get("fixed", 0),
        "static_lift_allowed": len(triage) == 0 or all(str(item.get("triage_status")) in {"accepted-risk", "false-positive", "fixed"} and item.get("approved_by") for item in triage),
        "guardrail": "Bandit findings remain blocking until zero findings or approved finding-level triage exists.",
    }


def _enrich_tool_payload(tool_payload: dict[str, Any], tool_name: str) -> dict[str, Any]:
    enriched = dict(tool_payload)
    status = str(enriched.get("status") or "missing")
    enriched.setdefault("current_run", True)
    enriched.setdefault("findings_count", _finding_count(enriched))
    enriched.setdefault("verified_for_this_report", status in {"completed", "unavailable", "timeout", "failed"})
    if status in {"unavailable", "timeout", "failed"}:
        reason = str(enriched.get("reason") or enriched.get("failure_reason") or enriched.get("stderr") or "no reason returned")
        enriched.setdefault("failure_or_unavailable_reason", reason[:2000])
    if tool_name == "bandit":
        findings = enriched.get("findings") if isinstance(enriched.get("findings"), list) else []
        triage = build_bandit_triage(findings)
        enriched["bandit_triage"] = triage
        enriched["bandit_triage_summary"] = summarize_bandit_triage(triage)
    return enriched


def _patch_scanner_tool_payloads() -> None:
    from nico import scanner_tool_runners
    from nico import hosted_scanner_worker

    original_tool = getattr(scanner_tool_runners, "_nico_original_run_scanner_tool_execution_patch", None)
    if original_tool is None:
        original_tool = scanner_tool_runners.run_scanner_tool
        scanner_tool_runners._nico_original_run_scanner_tool_execution_patch = original_tool

    def run_scanner_tool_with_current_run_metadata(spec: Any, workspace: Any, *, runner: Any = None) -> dict[str, Any]:
        if runner is None:
            payload = original_tool(spec, workspace)
        else:
            payload = original_tool(spec, workspace, runner=runner)
        if isinstance(payload, dict):
            return _enrich_tool_payload(payload, str(getattr(spec, "name", payload.get("tool") or "unknown")))
        return payload

    scanner_tool_runners.run_scanner_tool = run_scanner_tool_with_current_run_metadata

    original_tools = getattr(scanner_tool_runners, "_nico_original_run_scanner_tools_execution_patch", None)
    if original_tools is None:
        original_tools = scanner_tool_runners.run_scanner_tools
        scanner_tool_runners._nico_original_run_scanner_tools_execution_patch = original_tools

    def run_scanner_tools_with_execution_metadata(*args: Any, **kwargs: Any) -> dict[str, Any]:
        artifact = original_tools(*args, **kwargs)
        if not isinstance(artifact, dict):
            return artifact
        tools = artifact.get("tools") if isinstance(artifact.get("tools"), dict) else {}
        records = []
        for name, payload in tools.items():
            if isinstance(payload, dict):
                records.append(
                    {
                        "tool": name,
                        "category": payload.get("category"),
                        "status": payload.get("status"),
                        "returncode": payload.get("returncode"),
                        "findings_count": payload.get("findings_count", _finding_count(payload)),
                        "current_run": payload.get("current_run", True),
                        "verified_for_this_report": payload.get("verified_for_this_report", False),
                        "reason": payload.get("reason") or payload.get("failure_or_unavailable_reason") or "",
                    }
                )
        artifact["tool_records"] = records
        bandit = tools.get("bandit") if isinstance(tools, dict) else None
        if isinstance(bandit, dict):
            artifact["bandit_triage"] = bandit.get("bandit_triage") or []
            artifact["bandit_triage_summary"] = bandit.get("bandit_triage_summary") or summarize_bandit_triage([])
        return artifact

    scanner_tool_runners.run_scanner_tools = run_scanner_tools_with_execution_metadata
    hosted_scanner_worker.run_scanner_tools = run_scanner_tools_with_execution_metadata


def _patch_runtime_guard_tool_records() -> None:
    from nico import hosted_full_evidence_runtime_v2

    original_attach = getattr(hosted_full_evidence_runtime_v2, "_nico_original_attach_raw_artifact_execution_patch", None)
    if original_attach is None:
        original_attach = hosted_full_evidence_runtime_v2._attach_raw_artifact
        hosted_full_evidence_runtime_v2._nico_original_attach_raw_artifact_execution_patch = original_attach

    def attach_raw_artifact_with_tool_records(result: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
        updated = original_attach(result, artifact)
        guard = updated.setdefault("report_quality_guards", {}).setdefault("hosted_full_evidence_runtime", {})
        if isinstance(guard, dict):
            guard["tool_records"] = artifact.get("tool_records") or []
            guard["bandit_triage_summary"] = artifact.get("bandit_triage_summary") or {}
            guard["complexity_engine_attached"] = isinstance(artifact.get("complexity_engine"), dict)
            guard["score_lift_guardrail"] = "Dependency, secrets, static analysis, and velocity scores may only lift from completed current-run tools or approved formal triage."
        if artifact.get("bandit_triage") is not None:
            updated["bandit_triage"] = artifact.get("bandit_triage") or []
            updated["bandit_triage_summary"] = artifact.get("bandit_triage_summary") or summarize_bandit_triage([])
        return updated

    hosted_full_evidence_runtime_v2._attach_raw_artifact = attach_raw_artifact_with_tool_records


def install_hosted_evidence_execution_patch() -> None:
    _patch_scanner_tool_payloads()
    _patch_runtime_guard_tool_records()
