from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

TOOL_SECTION_MAP = {
    "pip-audit": "dependency_health",
    "npm-audit": "dependency_health",
    "npm audit": "dependency_health",
    "osv-scanner": "dependency_health",
    "osv api": "dependency_health",
    "bandit": "static_analysis",
    "semgrep": "static_analysis",
    "eslint": "static_analysis",
    "typescript": "static_analysis",
    "gitleaks": "secrets_review",
    "trufflehog": "secrets_review",
    "credential-scan": "secrets_review",
    "coverage": "coverage",
    "codeql": "ci_cd",
    "github actions": "ci_cd",
}

REQUIRED_BY_SECTION = {
    "dependency_health": ["pip-audit", "npm-audit", "osv-scanner"],
    "static_analysis": ["bandit", "semgrep", "eslint", "typescript"],
    "secrets_review": ["gitleaks", "trufflehog"],
    "ci_cd": ["github actions"],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(_text(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(_text(item) for item in value)
    return str(value or "")


def _section_text(section: dict[str, Any]) -> str:
    return "\n".join(_text(section.get(key)) for key in ("summary", "evidence", "findings", "unavailable"))


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _section_id(section: dict[str, Any]) -> str:
    return str(section.get("id") or section.get("label") or "unknown_section")


def _detect_tool_from_text(text: str) -> str | None:
    lower = text.lower()
    for tool in TOOL_SECTION_MAP:
        if tool in lower:
            return tool
    if "workflow" in lower or "actions" in lower:
        return "github actions"
    return None


def _entry_status(text: str, *, source: str) -> str:
    lower = text.lower()
    if any(marker in lower for marker in ("unavailable", "not attached", "not verified", "still required", "missing")):
        return "unavailable"
    if any(marker in lower for marker in ("finding", "vulnerab", "completed_with_findings", "review_required")):
        return "completed_with_findings"
    if source == "evidence":
        return "completed"
    return "not_verified"


def _findings_count(text: str) -> int | None:
    lower = text.lower()
    for marker in ("finding(s)", "findings", "vulnerability record(s)", "vulnerability records"):
        idx = lower.find(marker)
        if idx == -1:
            continue
        prefix = lower[:idx].split()[-4:]
        for token in reversed(prefix):
            digits = "".join(ch for ch in token if ch.isdigit())
            if digits:
                return int(digits)
    if any(word in lower for word in ("zero", "no high-confidence", "no credential findings")):
        return 0
    return None


def _entry_from_line(
    *,
    report_run_id: str,
    section: dict[str, Any],
    line: str,
    source: str,
    generated_at: str,
    repository: str,
    commit_sha: str,
) -> dict[str, Any] | None:
    text = str(line or "").strip()
    if not text:
        return None
    tool = _detect_tool_from_text(text)
    if not tool:
        return None
    status = _entry_status(text, source=source)
    linked_section = _section_id(section)
    return {
        "artifact_id": f"{report_run_id}:{linked_section}:{tool}:{source}:{_hash_payload(text)[:12]}",
        "tool_name": tool,
        "source": source,
        "repository": repository,
        "commit_sha": commit_sha,
        "run_timestamp": generated_at,
        "command_used": None,
        "exit_code": None,
        "status": status,
        "content_hash": _hash_payload({"section": linked_section, "source": source, "text": text}),
        "findings_count": _findings_count(text),
        "linked_section": linked_section,
        "verified_for_this_report": status == "completed",
        "evidence_excerpt": text[:280],
    }


def _section_entries(result: dict[str, Any], report_run_id: str) -> list[dict[str, Any]]:
    generated_at = str(result.get("generated_at") or _now_iso())
    repository = str(result.get("repository") or result.get("repo") or "")
    commit_sha = str(result.get("commit_sha") or result.get("head_sha") or result.get("deploy_commit") or "unknown")
    entries: list[dict[str, Any]] = []
    for section in result.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        for source in ("evidence", "findings", "unavailable"):
            values = section.get(source) or []
            if not isinstance(values, list):
                values = [values]
            for line in values:
                entry = _entry_from_line(
                    report_run_id=report_run_id,
                    section=section,
                    line=str(line),
                    source=source,
                    generated_at=generated_at,
                    repository=repository,
                    commit_sha=commit_sha,
                )
                if entry:
                    entries.append(entry)
    return entries


def _scanner_artifact_entries(result: dict[str, Any], report_run_id: str) -> list[dict[str, Any]]:
    generated_at = str(result.get("generated_at") or _now_iso())
    repository = str(result.get("repository") or result.get("repo") or "")
    commit_sha = str(result.get("commit_sha") or result.get("head_sha") or result.get("deploy_commit") or "unknown")
    scanner = result.get("scanner_worker_artifact") or result.get("scanner_artifacts") or result.get("scanner_worker")
    if not isinstance(scanner, dict):
        return []
    tools = scanner.get("tools") if isinstance(scanner.get("tools"), dict) else {}
    entries: list[dict[str, Any]] = []
    for tool_name, payload in tools.items():
        if not isinstance(payload, dict):
            continue
        tool = str(payload.get("tool") or tool_name)
        status = str(payload.get("status") or "not_verified")
        category = str(payload.get("category") or "")
        linked_section = TOOL_SECTION_MAP.get(tool.lower()) or {
            "dependency": "dependency_health",
            "static": "static_analysis",
            "secret": "secrets_review",
            "coverage": "coverage",
        }.get(category, "unknown_section")
        findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
        entries.append(
            {
                "artifact_id": f"{report_run_id}:{linked_section}:{tool}:scanner_worker:{_hash_payload(payload)[:12]}",
                "tool_name": tool,
                "source": "scanner_worker_artifact",
                "repository": repository,
                "commit_sha": commit_sha,
                "run_timestamp": generated_at,
                "command_used": payload.get("command_intent") or payload.get("command_used"),
                "exit_code": payload.get("returncode"),
                "status": status,
                "content_hash": _hash_payload(payload),
                "findings_count": len(findings),
                "linked_section": linked_section,
                "verified_for_this_report": status == "completed",
                "evidence_excerpt": f"{tool} scanner-worker artifact status={status}, findings={len(findings)}",
            }
        )
    return entries


def _dedupe_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for entry in entries:
        key = str(entry.get("artifact_id") or entry.get("content_hash"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def _coverage(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_section: dict[str, dict[str, Any]] = {}
    for section_id, required in REQUIRED_BY_SECTION.items():
        section_entries = [entry for entry in entries if entry.get("linked_section") == section_id]
        verified_tools = sorted({str(entry.get("tool_name")) for entry in section_entries if entry.get("verified_for_this_report")})
        unavailable_tools = sorted({str(entry.get("tool_name")) for entry in section_entries if entry.get("status") == "unavailable"})
        by_section[section_id] = {
            "required_tools": required,
            "verified_tools": verified_tools,
            "unavailable_tools": unavailable_tools,
            "verified_required_tools": [tool for tool in required if tool in verified_tools],
            "missing_required_tools": [tool for tool in required if tool not in verified_tools],
            "complete": all(tool in verified_tools for tool in required),
        }
    return by_section


def build_evidence_ledger(result: dict[str, Any]) -> dict[str, Any]:
    generated_at = str(result.get("generated_at") or _now_iso())
    repository = str(result.get("repository") or result.get("repo") or "unknown")
    report_run_id = str(result.get("report_run_id") or result.get("assessment_id") or _hash_payload({"generated_at": generated_at, "repository": repository})[:16])
    entries = _dedupe_entries(_scanner_artifact_entries(result, report_run_id) + _section_entries(result, report_run_id))
    coverage = _coverage(entries)
    verified_count = sum(1 for entry in entries if entry.get("verified_for_this_report"))
    unavailable_count = sum(1 for entry in entries if entry.get("status") == "unavailable")
    return {
        "version": "evidence-ledger-v1",
        "status": "partial" if unavailable_count else "available",
        "report_run_id": report_run_id,
        "repository": repository,
        "generated_at": generated_at,
        "entry_count": len(entries),
        "verified_entry_count": verified_count,
        "unavailable_entry_count": unavailable_count,
        "coverage_by_section": coverage,
        "entries": entries,
        "ledger_hash": _hash_payload(entries),
        "guardrail": "Ledger entries describe evidence attached or disclosed for this report run; unavailable entries are not clean proof.",
    }


def attach_evidence_ledger(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "complete":
        return result
    ledger = build_evidence_ledger(result)
    result["evidence_ledger"] = ledger
    result.setdefault("report_quality_guards", {})["evidence_ledger"] = {
        "status": ledger["status"],
        "entry_count": ledger["entry_count"],
        "ledger_hash": ledger["ledger_hash"],
    }
    medium_term = list(result.get("medium_term_plan") or [])
    summary = (
        f"Evidence ledger attached: {ledger['entry_count']} evidence entries, "
        f"{ledger['verified_entry_count']} verified for this report, {ledger['unavailable_entry_count']} unavailable."
    )
    if summary not in medium_term:
        medium_term.append(summary)
    result["medium_term_plan"] = medium_term
    return result
