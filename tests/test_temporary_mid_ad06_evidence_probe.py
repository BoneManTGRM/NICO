from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


RUN_ID = "midrun_ad06e0cfbe81447f"
BASE = "https://app.nicoaudit.com/api/nico"
SCOPES = [
    {"customer_id": "default_customer", "project_id": "default_project"},
    {"customer_id": "customer_cody_jenkins", "project_id": "project_nico"},
    {"customer_id": "customer_cody_jenkins", "project_id": "project_nico_audit"},
]


def _get(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "NICO-read-only-mid-evidence-probe"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _texts(value, limit: int = 30):
    if not isinstance(value, list):
        return []
    output = []
    for item in value:
        if isinstance(item, dict):
            compact = {
                key: item.get(key)
                for key in (
                    "id",
                    "tool",
                    "path",
                    "file",
                    "line",
                    "title",
                    "summary",
                    "finding",
                    "message",
                    "severity",
                    "status",
                    "category",
                    "rule_id",
                    "code",
                    "reason",
                )
                if item.get(key) not in (None, "", [], {})
            }
            output.append(compact or str(item)[:500])
        else:
            output.append(str(item)[:500])
        if len(output) >= limit:
            break
    return output


def _summary(body: str) -> dict:
    payload = json.loads(body)
    assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else {}
    scanner = payload.get("scanner_evidence") if isinstance(payload.get("scanner_evidence"), dict) else {}
    if not scanner:
        scanner = payload.get("scanner") if isinstance(payload.get("scanner"), dict) else {}
    sections = assessment.get("sections") if isinstance(assessment.get("sections"), list) else []
    tool_results = scanner.get("tool_results") if isinstance(scanner.get("tool_results"), list) else []
    return {
        "status": payload.get("status"),
        "run_id": payload.get("run_id"),
        "customer_id": payload.get("customer_id"),
        "project_id": payload.get("project_id"),
        "report_generation_status": payload.get("report_generation_status"),
        "approval_request_status": payload.get("approval_request_status"),
        "approval_error": payload.get("approval_request_error"),
        "scanner": {
            "status": scanner.get("status"),
            "scanner_status": scanner.get("scanner_status"),
            "scan_id": scanner.get("scan_id"),
            "tools_requested": scanner.get("tools_requested"),
            "tools_run": scanner.get("tools_run"),
            "failed_tools": scanner.get("failed_tools"),
            "timed_out_tools": scanner.get("timed_out_tools"),
            "unavailable_tools": scanner.get("unavailable_tools"),
            "full_history_verified_tools": scanner.get("full_history_verified_tools"),
            "tool_results": [
                {
                    "tool": item.get("tool") or item.get("name"),
                    "status": item.get("status"),
                    "exit_code": item.get("exit_code"),
                    "error": str(item.get("error") or item.get("message") or "")[:500],
                    "finding_count": item.get("finding_count"),
                    "parsed_finding_count": item.get("parsed_finding_count"),
                    "findings": _texts(item.get("findings"), 12),
                }
                for item in tool_results
                if isinstance(item, dict)
            ],
        },
        "sections": [
            {
                "id": item.get("id"),
                "score": item.get("score"),
                "truth_status": item.get("truth_status"),
                "summary": item.get("summary"),
                "evidence": _texts(item.get("evidence"), 30),
                "findings": _texts(item.get("findings"), 30),
                "unavailable": _texts(item.get("unavailable"), 20),
                "missing_evidence_sources": _texts(item.get("missing_evidence_sources"), 20),
                "failed_evidence_tools": _texts(item.get("failed_evidence_tools"), 20),
                "score_evidence_breakdown": item.get("score_evidence_breakdown"),
            }
            for item in sections
            if isinstance(item, dict)
        ],
        "complexity": {
            key: payload.get("complexity_evidence", {}).get(key)
            for key in (
                "status",
                "files_analyzed",
                "functions_analyzed",
                "high_complexity_count",
                "very_high_complexity_count",
                "long_unit_count",
                "duplicate_group_count",
                "top_complexity_units",
                "long_units",
                "duplicate_groups",
            )
            if isinstance(payload.get("complexity_evidence"), dict)
        },
    }


def test_capture_exact_mid_evidence_for_bounded_remediation() -> None:
    results = []
    for scope in SCOPES:
        query = urllib.parse.urlencode(scope)
        try:
            status, body = _get(f"{BASE}/assessment/mid-run/{RUN_ID}/live-status?{query}")
            results.append({
                "scope": scope,
                "http_status": status,
                "summary": _summary(body) if status == 200 else json.loads(body),
            })
        except Exception as exc:
            results.append({"scope": scope, "probe_error": type(exc).__name__})
    raise AssertionError("NICO_MID_AD06_EVIDENCE_PROBE=" + json.dumps(results, sort_keys=True, default=str))
