from __future__ import annotations

import inspect
from typing import Any

BROWSER_PROJECTION_HEADER = "x-nico-browser-projection"
BROWSER_PROJECTION_VALUE = "terminal-manifest-v1"
VERSION = "nico.bounded_terminal_reconnect.v1"


def _accepts_headers(request_get: Any) -> bool:
    """Return false only for narrow legacy test doubles without header support."""

    try:
        parameters = inspect.signature(request_get).parameters.values()
    except (TypeError, ValueError):
        return True
    return any(
        parameter.name == "headers"
        or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


def install(runtime: Any, acceptance: Any) -> dict[str, Any]:
    """Use the bounded exact-run manifest only for post-run reconnect proof."""

    if getattr(runtime, "_nico_bounded_terminal_reconnect_installed", False):
        return {"status": "already_installed", "version": VERSION}

    original_status_request = runtime._status_request

    def bounded_status_request(
        page: Any,
        service: str,
        payload: dict[str, Any],
        *,
        bounded: bool = False,
    ) -> tuple[Any, str]:
        if service != "comprehensive" or not bounded:
            return original_status_request(page, service, payload)

        rid = acceptance.run_id(payload)
        if not rid:
            raise AssertionError(
                "comprehensive status read is missing the exact run ID"
            )
        path = f"/api/nico/assessment/comprehensive-run/{rid}"
        request_url = runtime._same_origin_url(page, path)
        if _accepts_headers(page.request.get):
            response = page.request.get(
                request_url,
                headers={BROWSER_PROJECTION_HEADER: BROWSER_PROJECTION_VALUE},
                timeout=30_000,
            )
        else:
            # Compatibility for legacy unit-test doubles whose GET signature
            # predates Playwright's supported headers keyword. Real Playwright
            # request contexts always take the bounded projection path above.
            response = page.request.get(request_url, timeout=30_000)
        return response, path

    def bounded_status_reconnect(
        page: Any,
        service: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        rid = acceptance.run_id(payload)
        projection_supported = bool(
            service == "comprehensive" and _accepts_headers(page.request.get)
        )
        response, path = bounded_status_request(
            page,
            service,
            payload,
            bounded=service == "comprehensive",
        )
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

        reports = current.get("reports") if isinstance(current.get("reports"), dict) else {}
        projection = ""
        response_bounded = False
        artifact_delivery = ""
        canonical_truth_sha256 = ""
        if service == "comprehensive" and projection_supported:
            assert reports.get("response_bounded") is True, (
                "comprehensive reconnect did not use the bounded terminal manifest"
            )
            assert reports.get("artifact_delivery") == "on_demand_exact_run"
            for body_field in ("markdown", "html", "pdf_base64", "json"):
                assert body_field not in reports, (
                    f"bounded reconnect unexpectedly included {body_field}"
                )
            projection = BROWSER_PROJECTION_VALUE
            response_bounded = True
            artifact_delivery = str(reports.get("artifact_delivery") or "")
            canonical_truth_sha256 = str(
                reports.get("canonical_truth_sha256") or ""
            )

        return {
            "artifact_schema": VERSION,
            "http_status": response.status,
            "run_id": rid,
            "request_url": runtime._same_origin_url(page, path),
            "revision_before": before_revision,
            "revision_after": after_revision,
            "integrity_before": before_integrity,
            "integrity_after": after_integrity,
            "identity_preserved": True,
            "projection": projection,
            "response_bounded": response_bounded,
            "artifact_delivery": artifact_delivery,
            "canonical_truth_sha256": canonical_truth_sha256,
        }

    runtime._status_request = bounded_status_request
    runtime.status_reconnect = bounded_status_reconnect
    acceptance.status_reconnect = bounded_status_reconnect
    runtime._nico_bounded_terminal_reconnect_installed = True
    return {
        "status": "installed",
        "version": VERSION,
        "full_report_validation_preserved": True,
        "post_run_reconnect_bounded": True,
    }


__all__ = [
    "BROWSER_PROJECTION_HEADER",
    "BROWSER_PROJECTION_VALUE",
    "VERSION",
    "install",
]
