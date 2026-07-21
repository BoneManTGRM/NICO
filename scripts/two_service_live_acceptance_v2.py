#!/usr/bin/env python3
from __future__ import annotations

import sys
from typing import Any
from urllib.parse import urlparse

from scripts import two_service_live_acceptance as base

VERSION = "nico.two_service_live_acceptance.v2"


def request_origin(page: Any) -> str:
    parsed = urlparse(str(page.url or ""))
    if parsed.scheme != "https" or not parsed.netloc:
        raise AssertionError(f"Cannot derive production request origin from page URL: {page.url!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


def status_reconnect(page: Any, service: str, payload: dict[str, Any]) -> dict[str, Any]:
    rid = base.run_id(payload)
    assert rid, f"{service} reconnect cannot continue without a run ID"
    origin = request_origin(page)
    if service == "express":
        customer = base.first_text(payload.get("customer_id"))
        project = base.first_text(payload.get("project_id"))
        response = page.request.post(
            f"{origin}/api/nico/assessment/express-run/{rid}/status",
            data={"customer_id": customer, "project_id": project},
        )
    else:
        response = page.request.get(
            f"{origin}/api/nico/assessment/comprehensive-run/{rid}"
        )
    assert 200 <= response.status < 300, f"{service} reconnect returned HTTP {response.status}"
    current = base.response_json(response)
    assert base.run_id(current) == rid, f"{service} reconnect changed run identity"
    before_revision, before_integrity = base.integrity(payload)
    after_revision, after_integrity = base.integrity(current)
    if before_revision is not None and after_revision is not None:
        assert after_revision >= before_revision
    if before_integrity and after_integrity:
        assert after_integrity == before_integrity
    return {
        "http_status": response.status,
        "run_id": rid,
        "request_origin": origin,
        "absolute_url_used": True,
        "revision_before": before_revision,
        "revision_after": after_revision,
        "integrity_before": before_integrity,
        "integrity_after": after_integrity,
        "identity_preserved": True,
    }


base.status_reconnect = status_reconnect


def main(argv: list[str] | None = None) -> int:
    return base.main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Configuration blocked: {exc}", file=sys.stderr)
        raise SystemExit(2)
