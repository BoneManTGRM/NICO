from __future__ import annotations

import json
import urllib.error
import urllib.request


RUN_ID = "express_run_2496656474d04b9bb709cdcb6e0a2c27"
BASE = "https://app.nicoaudit.com/api/nico"
STATUS_URL = f"{BASE}/assessment/express-run/{RUN_ID}/status"
DIAGNOSTIC_URLS = [
    f"{BASE}/diagnostics/express-runtime",
    f"{BASE}/operations/readiness",
]
SCOPES = [
    {"customer_id": "default_customer", "project_id": "default_project"},
    {"customer_id": "customer_cody_jenkins", "project_id": "project_nico_audit"},
]


def _request(url: str, *, method: str = "GET", payload: dict[str, str] | None = None) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "NICO-production-proof"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def test_read_retained_express_terminal_evidence() -> None:
    results = []
    for url in DIAGNOSTIC_URLS:
        try:
            status, body = _request(url)
            results.append({"url": url, "http_status": status, "body": body[:30000]})
        except Exception as exc:
            results.append({"url": url, "probe_error": type(exc).__name__})
    for scope in SCOPES:
        try:
            status, body = _request(STATUS_URL, method="POST", payload=scope)
            results.append({"scope": scope, "http_status": status, "body": body[:20000]})
        except Exception as exc:
            results.append({"scope": scope, "probe_error": type(exc).__name__})
    payload = json.dumps(results, sort_keys=True)
    raise AssertionError("NICO_PRODUCTION_EXPRESS_PROBE=" + payload)
