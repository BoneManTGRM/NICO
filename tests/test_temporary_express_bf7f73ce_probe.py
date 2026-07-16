from __future__ import annotations

import json
import urllib.error
import urllib.request


RUN_ID = "express_run_bf7f73cef08c410496e0cd602be33236"
BASE = "https://app.nicoaudit.com/api/nico"
STATUS_URL = f"{BASE}/assessment/express-run/{RUN_ID}/status"
DIAGNOSTIC_URL = f"{BASE}/diagnostics/express-runtime"
SCOPES = [
    {"customer_id": "default_customer", "project_id": "default_project"},
    {"customer_id": "customer_cody_jenkins", "project_id": "project_nico_audit"},
]


def _request(url: str, *, method: str = "GET", payload: dict[str, str] | None = None) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "NICO-read-only-production-proof"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def test_capture_exact_terminal_payload() -> None:
    results = []
    try:
        status, body = _request(DIAGNOSTIC_URL)
        results.append({"kind": "runtime", "http_status": status, "body": body[:30000]})
    except Exception as exc:
        results.append({"kind": "runtime", "probe_error": type(exc).__name__})
    for scope in SCOPES:
        try:
            status, body = _request(STATUS_URL, method="POST", payload=scope)
            results.append({"kind": "status", "scope": scope, "http_status": status, "body": body[:50000]})
        except Exception as exc:
            results.append({"kind": "status", "scope": scope, "probe_error": type(exc).__name__})
    raise AssertionError("NICO_EXPRESS_BF7F73CE_PROBE=" + json.dumps(results, sort_keys=True))
