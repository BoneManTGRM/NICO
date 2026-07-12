from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nico.operations_readiness import OPERATIONS_READINESS_SCHEMA


def normalize_base_url(value: str) -> str:
    cleaned = (value or "").strip().rstrip("/")
    if not cleaned:
        raise ValueError("Hosted NICO API URL is required.")
    if not cleaned.startswith(("http://", "https://")):
        raise ValueError("Hosted NICO API URL must start with http:// or https://.")
    return cleaned


def fetch_operations_readiness(
    base_url: str,
    *,
    timeout_seconds: int = 20,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    url = f"{normalize_base_url(base_url)}/operations/readiness"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "nico-operations-readiness-check"})
    try:
        with opener(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            status_code = getattr(response, "status", None) or getattr(response, "code", None)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "status": "blocked",
            "error": f"HTTP {exc.code}",
            "status_code": exc.code,
            "body": body[:1000],
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {"status": "blocked", "error": str(exc), "status_code": None}

    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        return {"status": "blocked", "error": f"Invalid JSON: {exc}", "status_code": status_code}

    if not isinstance(payload, dict):
        return {"status": "blocked", "error": "Readiness response must be a JSON object.", "status_code": status_code}
    payload.setdefault("status_code", status_code)
    return payload


def evaluate_operations_readiness(payload: dict[str, Any], *, allow_degraded: bool = False) -> tuple[bool, str]:
    if payload.get("artifact_schema") != OPERATIONS_READINESS_SCHEMA:
        return False, "Operations readiness schema is missing or unsupported."
    status = str(payload.get("status") or "blocked")
    if status == "ready" and payload.get("operational_ready") is True:
        return True, "NICO reports semantic operational readiness."
    if status == "degraded" and allow_degraded:
        return True, "NICO is degraded and was explicitly allowed for this diagnostic run."
    blockers = payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
    warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
    detail = blockers or warnings or ["unknown readiness failure"]
    return False, f"NICO operations readiness is {status}: {', '.join(str(item) for item in detail)}"


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    allow_degraded = "--allow-degraded" in args
    args = [item for item in args if item != "--allow-degraded"]
    base_url = args[0] if args else os.getenv("NICO_API_URL") or os.getenv("NEXT_PUBLIC_NICO_API_URL") or ""
    try:
        payload = fetch_operations_readiness(base_url)
    except ValueError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, indent=2, sort_keys=True))
        return 2

    passed, message = evaluate_operations_readiness(payload, allow_degraded=allow_degraded)
    output = dict(payload)
    output["checker_passed"] = passed
    output["checker_message"] = message
    output["allow_degraded"] = allow_degraded
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
