#!/usr/bin/env python3
from __future__ import annotations

import sys
from typing import Any
from urllib.parse import urlparse

import two_service_live_acceptance as acceptance

VERSION = "nico.two_service_live_acceptance_reconnect.v2"


def _same_origin_url(page: Any, path: str) -> str:
    parsed = urlparse(str(page.url or ""))
    if parsed.scheme != "https" or not parsed.netloc:
        raise AssertionError("acceptance page did not expose an HTTPS origin for reconnect")
    if not path.startswith("/"):
        raise AssertionError("reconnect path must be same-origin absolute")
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def status_reconnect(
    page: Any,
    service: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Reconnect to the exact completed run through an absolute same-origin URL.

    Playwright's page request context does not inherit the browser page URL as a
    base URL. Relative paths therefore raise ``APIRequestContext: Invalid URL``
    even when the deployed application and run completed correctly. Build the
    URL from the already validated browser origin and preserve the original
    exact-run identity and integrity assertions.
    """

    rid = acceptance.run_id(payload)
    if not rid:
        raise AssertionError(f"{service} reconnect is missing the exact run ID")

    if service == "express":
        customer = acceptance.first_text(payload.get("customer_id"))
        project = acceptance.first_text(payload.get("project_id"))
        path = f"/api/nico/assessment/express-run/{rid}/status"
        response = page.request.post(
            _same_origin_url(page, path),
            data={"customer_id": customer, "project_id": project},
        )
    elif service == "comprehensive":
        path = f"/api/nico/assessment/comprehensive-run/{rid}"
        response = page.request.get(_same_origin_url(page, path))
    else:
        raise AssertionError(f"unsupported acceptance service: {service}")

    assert 200 <= response.status < 300, (
        f"{service} reconnect returned HTTP {response.status}"
    )
    current = acceptance.response_json(response)
    assert acceptance.run_id(current) == rid, (
        f"{service} reconnect changed run identity"
    )

    before_revision, before_integrity = acceptance.integrity(payload)
    after_revision, after_integrity = acceptance.integrity(current)
    if before_revision is not None and after_revision is not None:
        assert after_revision >= before_revision
    if before_integrity and after_integrity:
        assert after_integrity == before_integrity

    return {
        "artifact_schema": VERSION,
        "http_status": response.status,
        "run_id": rid,
        "request_url": _same_origin_url(page, path),
        "revision_before": before_revision,
        "revision_after": after_revision,
        "integrity_before": before_integrity,
        "integrity_after": after_integrity,
        "identity_preserved": True,
    }


def main(argv: list[str] | None = None) -> int:
    acceptance.status_reconnect = status_reconnect
    return acceptance.main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Configuration blocked: {exc}", file=sys.stderr)
        raise SystemExit(2)
