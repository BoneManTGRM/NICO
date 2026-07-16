from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


RUN_ID = "midrun_df6d55c9c7fd45b2"
BASE = "https://app.nicoaudit.com/api/nico"
SCOPES = [
    {"customer_id": "default_customer", "project_id": "default_project"},
    {"customer_id": "customer_cody_jenkins", "project_id": "project_nico"},
    {"customer_id": "customer_cody_jenkins", "project_id": "project_nico_audit"},
]


def _get(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "NICO-read-only-mid-report-probe"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def test_capture_exact_mid_report_quality_payload() -> None:
    results = []
    for scope in SCOPES:
        query = urllib.parse.urlencode(scope)
        try:
            status, body = _get(f"{BASE}/assessment/mid-run/{RUN_ID}/live-status?{query}")
            results.append({"scope": scope, "http_status": status, "body": body[:120000]})
        except Exception as exc:
            results.append({"scope": scope, "probe_error": type(exc).__name__})
    try:
        status, body = _get(f"{BASE}/diagnostics/mid-runtime")
        results.append({"kind": "runtime", "http_status": status, "body": body[:30000]})
    except Exception as exc:
        results.append({"kind": "runtime", "probe_error": type(exc).__name__})
    raise AssertionError("NICO_MID_DF6D55C9_PROBE=" + json.dumps(results, sort_keys=True))
