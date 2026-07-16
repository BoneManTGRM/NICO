from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


RUN_ID = "midrun_ad06e0cfbe81447f"
BASE = "https://app.nicoaudit.com/api/nico"
SCOPE = {"customer_id": "customer_cody_jenkins", "project_id": "project_nico_audit"}


def _request_json(url: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "NICO-read-only-mid-detail-probe"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"raw_body": body[:4000]}
        return exc.code, payload


def _compact(value: Any, *, depth: int = 0, list_limit: int = 20, text_limit: int = 1200) -> Any:
    if depth >= 6:
        return str(value)[:text_limit]
    if isinstance(value, dict):
        return {
            str(key): _compact(item, depth=depth + 1, list_limit=list_limit, text_limit=text_limit)
            for key, item in value.items()
            if item not in (None, "", [], {})
        }
    if isinstance(value, list):
        result = [
            _compact(item, depth=depth + 1, list_limit=list_limit, text_limit=text_limit)
            for item in value[:list_limit]
        ]
        if len(value) > list_limit:
            result.append({"_truncated_items": len(value) - list_limit})
        return result
    if isinstance(value, str):
        return value[:text_limit]
    return value


def _scanner_result(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "tool",
        "scanner",
        "status",
        "completion_state",
        "category",
        "returncode",
        "timed_out",
        "output_truncated",
        "verified_for_this_report",
        "current_run",
        "execution_source",
        "full_history_verified",
        "scans_git_history",
        "finding_count",
        "findings_count",
        "reason",
        "failure_or_unavailable_reason",
        "command_intent",
        "command_resolved",
        "cwd",
        "bandit_triage",
    )
    output = {key: _compact(item.get(key)) for key in keys if item.get(key) not in (None, "", [], {})}
    output["result_keys"] = sorted(item)
    findings = item.get("findings") if isinstance(item.get("findings"), list) else []
    output["findings"] = _compact(findings, list_limit=30, text_limit=1600)
    attempts = item.get("attempts") if isinstance(item.get("attempts"), list) else []
    if attempts:
        output["attempts"] = _compact(attempts, list_limit=8, text_limit=1000)
    return output


def test_capture_exact_mid_detail_evidence() -> None:
    diagnostics_status, diagnostics = _request_json(f"{BASE}/diagnostics/mid-runtime")
    query = urllib.parse.urlencode(SCOPE)
    live_url = f"{BASE}/assessment/mid-run/{RUN_ID}/live-status?{query}"
    attempts: list[dict[str, Any]] = []
    payload: dict[str, Any] = {}
    status = 0
    for attempt in range(1, 7):
        status, payload = _request_json(live_url)
        attempts.append({"attempt": attempt, "http_status": status, "payload": _compact(payload, list_limit=8)})
        if status == 200:
            break
        time.sleep(5)

    if status != 200:
        raise AssertionError(
            "NICO_MID_AD06_RUNTIME_PROBE="
            + json.dumps(
                {
                    "diagnostics_http_status": diagnostics_status,
                    "diagnostics": _compact(diagnostics, list_limit=20),
                    "live_attempts": attempts,
                },
                sort_keys=True,
                default=str,
            )
        )

    scanner = payload.get("scanner_evidence") if isinstance(payload.get("scanner_evidence"), dict) else {}
    repository = payload.get("repository_evidence") if isinstance(payload.get("repository_evidence"), dict) else {}
    complexity = payload.get("complexity_evidence") if isinstance(payload.get("complexity_evidence"), dict) else {}
    assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else {}
    scanner_results = scanner.get("scanner_results") if isinstance(scanner.get("scanner_results"), list) else []
    sections = assessment.get("sections") if isinstance(assessment.get("sections"), list) else []

    evidence = {
        "diagnostics_http_status": diagnostics_status,
        "diagnostics": _compact(diagnostics, list_limit=30),
        "identity": {
            "status": payload.get("status"),
            "run_id": payload.get("run_id"),
            "customer_id": payload.get("customer_id"),
            "project_id": payload.get("project_id"),
            "repository": payload.get("repository"),
            "snapshot_commit_sha": payload.get("snapshot_commit_sha")
            or (payload.get("repository_snapshot") or {}).get("commit_sha"),
            "report_generation_status": payload.get("report_generation_status"),
            "approval_request_status": payload.get("approval_request_status"),
            "same_run_approval_repair": _compact(payload.get("same_run_approval_repair") or {}),
        },
        "scanner_summary": {
            key: _compact(scanner.get(key))
            for key in (
                "status",
                "scanner_status",
                "scan_id",
                "snapshot_match",
                "tools_requested",
                "tools_run",
                "unavailable_tools",
                "failed_tools",
                "timed_out_tools",
                "full_history_verified_tools",
                "scanner_results_count",
                "finding_summary",
                "finding_count",
                "material_finding_count",
                "review_required_finding_count",
                "excluded_test_only_finding_count",
                "evidence_summary",
                "unavailable_data_notes",
            )
            if scanner.get(key) not in (None, "", [], {})
        },
        "scanner_results": [_scanner_result(item) for item in scanner_results if isinstance(item, dict)],
        "repository_code_signals": _compact(repository.get("code_signal_evidence") or {}, list_limit=60, text_limit=1800),
        "repository_evidence_keys": sorted(repository),
        "complexity_evidence": _compact(complexity, list_limit=40, text_limit=1800),
        "complexity_evidence_keys": sorted(complexity),
        "sections": [
            {
                "id": section.get("id"),
                "score": section.get("score"),
                "truth_status": section.get("truth_status"),
                "confidence": section.get("confidence"),
                "evidence": _compact(section.get("evidence") or [], list_limit=40),
                "findings": _compact(section.get("findings") or [], list_limit=40),
                "unavailable": _compact(section.get("unavailable") or [], list_limit=30),
                "missing_evidence_sources": _compact(section.get("missing_evidence_sources") or [], list_limit=30),
                "failed_evidence_tools": _compact(section.get("failed_evidence_tools") or [], list_limit=30),
                "score_evidence_breakdown": _compact(section.get("score_evidence_breakdown") or {}),
            }
            for section in sections
            if isinstance(section, dict)
        ],
    }
    rendered = json.dumps(evidence, sort_keys=True, default=str)
    raise AssertionError("NICO_MID_AD06_DETAIL_PROBE=" + rendered[:120000])
