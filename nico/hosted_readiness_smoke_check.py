from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_ENDPOINTS = (
    "/health",
    "/operations/readiness",
    "/diagnostics/hosted-scanner-runtime",
    "/diagnostics/release-readiness",
)
REQUIRED_PAYLOAD_STATUSES = {
    "/health": {"ok"},
    "/operations/readiness": {"ready"},
}


@dataclass(frozen=True)
class EndpointCheck:
    path: str
    ok: bool
    status_code: int | None
    error: str
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "ok": self.ok,
            "status_code": self.status_code,
            "error": self.error,
            "payload": self.payload,
        }


def normalize_base_url(value: str) -> str:
    cleaned = (value or "").strip().rstrip("/")
    if not cleaned:
        raise ValueError("Hosted NICO API URL is required.")
    if not cleaned.startswith(("http://", "https://")):
        raise ValueError("Hosted NICO API URL must start with http:// or https://.")
    return cleaned


def _read_json(url: str, timeout_seconds: int = 15, opener: Callable[..., Any] = urlopen) -> tuple[int | None, dict[str, Any], str]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "nico-readiness-smoke-check"})
    try:
        with opener(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            status = getattr(response, "status", None) or getattr(response, "code", None)
            return int(status) if status is not None else None, json.loads(raw or "{}"), ""
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {"body": body}
        return exc.code, payload, f"HTTP {exc.code}"
    except (URLError, TimeoutError, OSError) as exc:
        return None, {}, str(exc)
    except json.JSONDecodeError as exc:
        return None, {}, f"Invalid JSON: {exc}"


def check_endpoint(base_url: str, path: str, timeout_seconds: int = 15, opener: Callable[..., Any] = urlopen) -> EndpointCheck:
    base = normalize_base_url(base_url)
    normalized_path = "/" + path.lstrip("/")
    status, payload, error = _read_json(f"{base}{normalized_path}", timeout_seconds=timeout_seconds, opener=opener)
    ok = bool(status and 200 <= status < 300 and not error)
    required_statuses = REQUIRED_PAYLOAD_STATUSES.get(normalized_path)
    if ok and required_statuses:
        observed_status = str(payload.get("status") or "missing")
        if observed_status not in required_statuses:
            ok = False
            expected = ", ".join(sorted(required_statuses))
            error = f"Semantic status {observed_status}; expected {expected}"
    return EndpointCheck(path=normalized_path, ok=ok, status_code=status, error=error, payload=payload)


def run_smoke_check(base_url: str, endpoints: tuple[str, ...] = DEFAULT_ENDPOINTS, timeout_seconds: int = 15, opener: Callable[..., Any] = urlopen) -> dict[str, Any]:
    checks = [check_endpoint(base_url, path, timeout_seconds=timeout_seconds, opener=opener) for path in endpoints]
    failed = [item for item in checks if not item.ok]
    return {
        "status": "passed" if not failed else "failed",
        "base_url": normalize_base_url(base_url),
        "endpoint_count": len(checks),
        "passed_count": len(checks) - len(failed),
        "failed_count": len(failed),
        "checks": [item.as_dict() for item in checks],
        "guardrail": "Smoke-check success confirms endpoint reachability and required semantic readiness states. It does not approve client delivery, lift scores, or replace human review.",
    }


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    base_url = args[0] if args else os.getenv("NICO_API_URL") or os.getenv("NEXT_PUBLIC_NICO_API_URL") or ""
    try:
        result = run_smoke_check(base_url)
    except ValueError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
