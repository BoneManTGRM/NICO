from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from nico.scanner_tool_runners import ScannerToolSpec, redact_payload, run_command
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace

BANDIT_TRIAGE_STATUSES = {"blocking", "needs-review", "accepted-risk", "false-positive", "fixed"}
APPROVED_TRIAGE_STATUSES = {"accepted-risk", "false-positive", "fixed"}
OPEN_TRIAGE_STATUSES = {"blocking", "needs-review"}
TRIAGE_FILE_CANDIDATES = (
    ".nico/bandit-triage.json",
    "nico/bandit-triage.json",
    "bandit-triage.json",
)
HIGH_RISK_LEVELS = {"high", "critical"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _as_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    try:
        cleaned = _clean(value)
        if cleaned:
            return int(cleaned)
    except ValueError:
        return None
    return None


def bandit_finding_id(finding: dict[str, Any]) -> str:
    file_path = _clean(finding.get("filename") or finding.get("file_path") or finding.get("path"))
    line_number = _clean(finding.get("line_number") or finding.get("line"))
    issue_type = _clean(finding.get("test_id") or finding.get("issue_type") or finding.get("test_name"))
    issue_text = _clean(finding.get("issue_text") or finding.get("message") or finding.get("text"))
    payload = "|".join([file_path, line_number, issue_type, issue_text]).lower()
    return "bandit_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def normalize_bandit_finding(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "finding_id": _clean(finding.get("finding_id") or finding.get("finding_key")) or bandit_finding_id(finding),
        "file_path": _clean(finding.get("filename") or finding.get("file_path") or finding.get("path")),
        "line_number": _as_int(finding.get("line_number") or finding.get("line")),
        "issue_type": _clean(finding.get("test_id") or finding.get("issue_type") or finding.get("test_name")),
        "test_name": _clean(finding.get("test_name")),
        "severity": _clean(finding.get("issue_severity") or finding.get("severity")).lower() or "unknown",
        "confidence": _clean(finding.get("issue_confidence") or finding.get("confidence")).lower() or "unknown",
        "issue_text": _clean(finding.get("issue_text") or finding.get("message") or finding.get("text")),
    }


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        records = payload.get("records") or payload.get("triage") or payload.get("findings") or []
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict)]
    return []


def load_bandit_triage_records(repo_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    for relative in TRIAGE_FILE_CANDIDATES:
        candidate = repo_dir / relative
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception as exc:
            return [], [f"Bandit triage file {relative} could not be parsed: {exc}"]
        return _records_from_payload(payload), [f"Loaded Bandit triage file: {relative}"]
    return [], ["No Bandit triage file found. Expected one of: " + ", ".join(TRIAGE_FILE_CANDIDATES)]


def _record_finding_id(record: dict[str, Any]) -> str:
    return _clean(record.get("finding_id") or record.get("finding_key"))


def _validate_record(record: dict[str, Any]) -> tuple[bool, str]:
    status = _clean(record.get("status")).lower()
    if status not in BANDIT_TRIAGE_STATUSES:
        return False, "status must be one of: " + ", ".join(sorted(BANDIT_TRIAGE_STATUSES))
    if status in APPROVED_TRIAGE_STATUSES:
        missing = [field for field in ("reason", "approved_by", "approved_at") if not _clean(record.get(field))]
        if missing:
            return False, "approved triage statuses require: " + ", ".join(missing)
    if status in OPEN_TRIAGE_STATUSES and not _clean(record.get("reason")):
        return False, "blocking and needs-review triage records require a reason"
    if not _record_finding_id(record):
        return False, "triage record requires finding_id"
    return True, ""


def _is_high_risk(finding: dict[str, Any]) -> bool:
    return _clean(finding.get("severity")).lower() in HIGH_RISK_LEVELS or _clean(finding.get("confidence")).lower() in HIGH_RISK_LEVELS


def build_bandit_triage_summary(findings: list[dict[str, Any]], triage_records: list[dict[str, Any]], *, notes: list[str] | None = None) -> dict[str, Any]:
    normalized_findings = [normalize_bandit_finding(item) for item in findings if isinstance(item, dict)]
    valid_by_id: dict[str, dict[str, Any]] = {}
    invalid_records: list[dict[str, str]] = []

    for record in triage_records:
        valid, reason = _validate_record(record)
        finding_id = _record_finding_id(record)
        if valid:
            valid_by_id[finding_id] = record
        else:
            invalid_records.append({"finding_id": finding_id, "reason": reason})

    enriched_findings: list[dict[str, Any]] = []
    missing_triage_records: list[str] = []
    approved_count = 0
    blocking_count = 0
    needs_review_count = 0
    unresolved_high_confidence_count = 0

    for finding in normalized_findings:
        finding_id = _clean(finding.get("finding_id"))
        record = valid_by_id.get(finding_id)
        status = _clean(record.get("status")).lower() if record else "needs-review"
        approved = bool(record and status in APPROVED_TRIAGE_STATUSES)
        if not record:
            missing_triage_records.append(finding_id)
        if status == "blocking":
            blocking_count += 1
        if status == "needs-review" or not record:
            needs_review_count += 1
        if approved:
            approved_count += 1
        if _is_high_risk(finding) and not approved:
            unresolved_high_confidence_count += 1
        enriched_findings.append(
            {
                **finding,
                "triage_status": status,
                "triage_reason": _clean(record.get("reason")) if record else "No valid Bandit triage record attached.",
                "approved_by": _clean(record.get("approved_by")) if record else "",
                "approved_at": _clean(record.get("approved_at")) if record else "",
                "score_blocking": _is_high_risk(finding) and not approved,
            }
        )

    score_lift_allowed = not invalid_records and not blocking_count and not needs_review_count and not unresolved_high_confidence_count
    return redact_payload(
        {
            "artifact_schema": "nico.bandit_triage.v1",
            "total_findings": len(normalized_findings),
            "triage_records_loaded": len(triage_records),
            "triaged_count": len(valid_by_id),
            "approved_count": approved_count,
            "blocking_count": blocking_count,
            "needs_review_count": needs_review_count,
            "unresolved_high_confidence_count": unresolved_high_confidence_count,
            "missing_triage_records": missing_triage_records,
            "invalid_triage_records": invalid_records,
            "score_lift_allowed": score_lift_allowed,
            "human_review_required": bool(invalid_records or blocking_count or needs_review_count or unresolved_high_confidence_count),
            "notes": notes or [],
            "findings": enriched_findings,
            "guardrail": "Bandit findings only stop blocking score lift when every high-risk finding is fixed, false-positive, or accepted-risk with reason, approved_by, and approved_at.",
        }
    )


def apply_bandit_triage_to_tool_payload(tool_payload: dict[str, Any], repo_dir: Path) -> dict[str, Any]:
    findings = tool_payload.get("findings") if isinstance(tool_payload.get("findings"), list) else []
    records, notes = load_bandit_triage_records(repo_dir)
    enriched = dict(tool_payload)
    triage = build_bandit_triage_summary(findings, records, notes=notes)
    enriched["bandit_triage"] = triage
    enriched["human_review_required"] = bool(triage.get("human_review_required"))
    return enriched


def _patch_scanner_tool_runner() -> None:
    from nico import scanner_tool_runners

    original = getattr(scanner_tool_runners, "_nico_original_run_scanner_tool_bandit_triage_workflow", None)
    if original is None:
        original = scanner_tool_runners.run_scanner_tool
        scanner_tool_runners._nico_original_run_scanner_tool_bandit_triage_workflow = original

    def run_scanner_tool_with_bandit_triage(
        spec: ScannerToolSpec,
        workspace: WorkerWorkspace,
        *,
        runner: Callable[..., WorkerCommandResult] = run_command,
    ) -> dict[str, Any]:
        payload = original(spec, workspace, runner=runner)
        if spec.name == "bandit" and isinstance(payload, dict):
            return apply_bandit_triage_to_tool_payload(payload, workspace.repo_dir)
        return payload

    scanner_tool_runners.run_scanner_tool = run_scanner_tool_with_bandit_triage


def _patch_worker_artifact_summary() -> None:
    from nico import hosted_scanner_worker

    original = getattr(hosted_scanner_worker, "_nico_original_run_hosted_scanner_worker_bandit_triage_workflow", None)
    if original is None:
        original = hosted_scanner_worker.run_hosted_scanner_worker
        hosted_scanner_worker._nico_original_run_hosted_scanner_worker_bandit_triage_workflow = original

    def run_hosted_scanner_worker_with_bandit_triage_summary(payload: dict[str, Any]) -> dict[str, Any]:
        artifact = original(payload)
        if not isinstance(artifact, dict):
            return artifact
        tools = artifact.get("tools") if isinstance(artifact.get("tools"), dict) else {}
        bandit = tools.get("bandit") if isinstance(tools.get("bandit"), dict) else {}
        triage = bandit.get("bandit_triage") if isinstance(bandit.get("bandit_triage"), dict) else None
        if triage:
            artifact["bandit_triage_summary"] = {
                "artifact_schema": triage.get("artifact_schema"),
                "total_findings": triage.get("total_findings", 0),
                "approved_count": triage.get("approved_count", 0),
                "blocking_count": triage.get("blocking_count", 0),
                "needs_review_count": triage.get("needs_review_count", 0),
                "unresolved_high_confidence_count": triage.get("unresolved_high_confidence_count", 0),
                "score_lift_allowed": triage.get("score_lift_allowed", False),
                "human_review_required": triage.get("human_review_required", True),
                "guardrail": triage.get("guardrail"),
            }
        return artifact

    hosted_scanner_worker.run_hosted_scanner_worker = run_hosted_scanner_worker_with_bandit_triage_summary


def install_bandit_triage_workflow_patch() -> None:
    _patch_scanner_tool_runner()
    _patch_worker_artifact_summary()
