from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


RUN_ID = "midrun_5019e3220d5c4db2"
BASE = "https://app.nicoaudit.com/api/nico"
SCOPES = [
    {"customer_id": "default_customer", "project_id": "default_project"},
    {"customer_id": "customer_cody_jenkins", "project_id": "project_nico_audit"},
]


def _request(url: str, *, method: str = "GET", payload: dict[str, str] | None = None) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "NICO-read-only-mid-proof"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def test_capture_mid_terminal_payload() -> None:
    results = []
    for path in ("/diagnostics/mid-runtime",):
        try:
            status, body = _request(BASE + path)
            results.append({"kind": "runtime", "http_status": status, "body": body[:30000]})
        except Exception as exc:
            results.append({"kind": "runtime", "probe_error": type(exc).__name__})
    for scope in SCOPES:
        query = urllib.parse.urlencode(scope)
        try:
            status, body = _request(f"{BASE}/assessment/mid-run/{RUN_ID}/live-status?{query}")
            results.append({"kind": "live", "scope": scope, "http_status": status, "body": body[:80000]})
        except Exception as exc:
            results.append({"kind": "live", "scope": scope, "probe_error": type(exc).__name__})
        try:
            status, body = _request(
                f"{BASE}/assessment/mid-run/{RUN_ID}/status",
                method="POST",
                payload=scope,
            )
            results.append({"kind": "status", "scope": scope, "http_status": status, "body": body[:80000]})
        except Exception as exc:
            results.append({"kind": "status", "scope": scope, "probe_error": type(exc).__name__})
    raise AssertionError("NICO_MID_5019E322_PROBE=" + json.dumps(results, sort_keys=True))
