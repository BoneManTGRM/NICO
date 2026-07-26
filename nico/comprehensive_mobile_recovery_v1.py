from __future__ import annotations

import base64
import hashlib
import json
from contextvars import ContextVar
from functools import wraps
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

import nico.comprehensive_api_controller as controller_module
import nico.comprehensive_api_routes as routes_module

VERSION = "nico.comprehensive_mobile_recovery.v1"
BROWSER_PROJECTION_HEADER = "x-nico-browser-projection"
BROWSER_PROJECTION_VALUE = "terminal-manifest-v1"
ARTIFACT_ROUTE_PATHS = {
    "/assessment/comprehensive-run/{run_id}/report/markdown",
    "/assessment/comprehensive-run/{run_id}/report/html",
    "/assessment/comprehensive-run/{run_id}/report/json",
    "/assessment/comprehensive-run/{run_id}/report/pdf",
}

_BROWSER_PROJECTION: ContextVar[bool] = ContextVar(
    "nico_comprehensive_browser_projection",
    default=False,
)
_INSTALLED = False
_ORIGINAL_PROJECT_REPORT: Callable[[dict[str, Any]], dict[str, Any]] | None = None
_ORIGINAL_REGISTER: Callable[..., Any] | None = None


def _text(value: Any) -> str:
    return str(value or "")


def _report_manifest(report: dict[str, Any]) -> dict[str, Any]:
    markdown = _text(report.get("markdown"))
    html = _text(report.get("html"))
    encoded_pdf = _text(report.get("pdf_base64")).strip()
    json_value = report.get("json")
    canonical_hash = _text(
        report.get("canonical_truth_sha256")
        or (json_value.get("canonical_truth_sha256") if isinstance(json_value, dict) else "")
    )
    return {
        "service_id": _text(report.get("service_id") or "comprehensive"),
        "report_id": _text(report.get("report_id")),
        "pdf_filename": _text(
            report.get("pdf_filename")
            or "nico-comprehensive-assessment-FINAL-PENDING-APPROVAL.pdf"
        ),
        "pdf_error": _text(report.get("pdf_error")),
        "pdf_sha256": _text(report.get("pdf_sha256")),
        "canonical_truth_sha256": canonical_hash,
        "markdown_available": bool(markdown),
        "html_available": bool(html),
        "json_available": isinstance(json_value, dict),
        "pdf_available": bool(encoded_pdf),
        "markdown_size_bytes": len(markdown.encode("utf-8")),
        "html_size_bytes": len(html.encode("utf-8")),
        "json_size_bytes": (
            len(json.dumps(json_value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))
            if isinstance(json_value, dict)
            else 0
        ),
        "pdf_base64_size_bytes": len(encoded_pdf.encode("ascii", errors="ignore")),
        "artifact_delivery": "on_demand_exact_run",
        "response_bounded": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _project_report(report: dict[str, Any]) -> dict[str, Any]:
    assert _ORIGINAL_PROJECT_REPORT is not None
    if _BROWSER_PROJECTION.get():
        return _report_manifest(report)
    return _ORIGINAL_PROJECT_REPORT(report)


class _BrowserProjectionContextMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers") or []
        }
        enabled = headers.get(BROWSER_PROJECTION_HEADER, "").strip().lower() == BROWSER_PROJECTION_VALUE
        token = _BROWSER_PROJECTION.set(enabled)
        try:
            await self.app(scope, receive, send)
        finally:
            _BROWSER_PROJECTION.reset(token)


def _artifact_record(request: Request, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    controller = routes_module._controller(request)
    record = routes_module._service(controller).load(run_id)
    status = _text(record.get("status")).strip().lower()
    if not bool(record.get("terminal")) and status not in {
        "review_required",
        "complete",
        "completed",
        "approved",
    }:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "comprehensive_report_not_ready",
                "message": "The final report is not ready for this exact run.",
                "retryable": True,
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )
    report, _assessment = controller_module._report_outputs(record)
    if not report:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "comprehensive_report_artifact_missing",
                "message": "The final report artifact is missing for this exact run.",
                "retryable": False,
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )
    return record, report


def _safe_filename(value: Any, fallback: str) -> str:
    normalized = _text(value).replace("\r", "").replace("\n", "").replace('"', "'").strip()
    return normalized or fallback


def _artifact_headers(run_id: str, report: dict[str, Any]) -> dict[str, str]:
    headers = {
        "Cache-Control": "no-store, private, max-age=0",
        "X-NICO-Run-ID": run_id,
        "X-NICO-Report-ID": _text(report.get("report_id")),
        "X-NICO-Human-Review-Required": "true",
        "X-NICO-Client-Delivery-Allowed": "false",
    }
    canonical_hash = _text(report.get("canonical_truth_sha256"))
    if canonical_hash:
        headers["X-NICO-Canonical-Truth-SHA256"] = canonical_hash
    return headers


def _install_artifact_routes(app: Any) -> None:
    existing = {str(getattr(route, "path", "")) for route in app.routes}
    if ARTIFACT_ROUTE_PATHS <= existing:
        return

    @app.get("/assessment/comprehensive-run/{run_id}/report/markdown")
    async def comprehensive_report_markdown(run_id: str, request: Request) -> Response:
        try:
            _record, report = _artifact_record(request, run_id)
            markdown = _text(report.get("markdown"))
            if not markdown:
                raise HTTPException(status_code=409, detail="comprehensive_report_markdown_missing")
            filename = _safe_filename(
                _text(report.get("pdf_filename")).removesuffix(".pdf") + ".md",
                f"nico-comprehensive-{run_id}.md",
            )
            return Response(
                content=markdown.encode("utf-8"),
                media_type="text/markdown; charset=utf-8",
                headers={
                    **_artifact_headers(run_id, report),
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-NICO-Artifact-SHA256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                },
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise routes_module._translate_error(exc) from exc

    @app.get("/assessment/comprehensive-run/{run_id}/report/html")
    async def comprehensive_report_html(run_id: str, request: Request) -> Response:
        try:
            _record, report = _artifact_record(request, run_id)
            html = _text(report.get("html"))
            if not html:
                raise HTTPException(status_code=409, detail="comprehensive_report_html_missing")
            return Response(
                content=html.encode("utf-8"),
                media_type="text/html; charset=utf-8",
                headers={
                    **_artifact_headers(run_id, report),
                    "X-NICO-Artifact-SHA256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
                },
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise routes_module._translate_error(exc) from exc

    @app.get("/assessment/comprehensive-run/{run_id}/report/json")
    async def comprehensive_report_json(run_id: str, request: Request) -> JSONResponse:
        try:
            _record, report = _artifact_record(request, run_id)
            value = report.get("json")
            if not isinstance(value, dict):
                raise HTTPException(status_code=409, detail="comprehensive_report_json_missing")
            return JSONResponse(
                content=value,
                headers=_artifact_headers(run_id, report),
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise routes_module._translate_error(exc) from exc

    @app.get("/assessment/comprehensive-run/{run_id}/report/pdf")
    async def comprehensive_report_pdf(run_id: str, request: Request) -> Response:
        try:
            _record, report = _artifact_record(request, run_id)
            encoded = _text(report.get("pdf_base64")).strip()
            try:
                pdf = base64.b64decode(encoded, validate=True)
            except Exception as exc:
                raise HTTPException(
                    status_code=409,
                    detail="comprehensive_report_pdf_invalid_base64",
                ) from exc
            if not pdf.startswith(b"%PDF"):
                raise HTTPException(status_code=409, detail="comprehensive_report_pdf_invalid_signature")
            expected_hash = _text(report.get("pdf_sha256")).strip().lower()
            observed_hash = hashlib.sha256(pdf).hexdigest()
            if expected_hash and expected_hash != observed_hash:
                raise HTTPException(status_code=409, detail="comprehensive_report_pdf_sha256_mismatch")
            filename = _safe_filename(
                report.get("pdf_filename"),
                f"nico-comprehensive-{run_id}-FINAL-PENDING-APPROVAL.pdf",
            )
            return Response(
                content=pdf,
                media_type="application/pdf",
                headers={
                    **_artifact_headers(run_id, report),
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-NICO-Artifact-SHA256": observed_hash,
                },
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise routes_module._translate_error(exc) from exc

    app.openapi_schema = None


def _install_registration_wrapper() -> None:
    global _ORIGINAL_REGISTER
    if _ORIGINAL_REGISTER is not None:
        return
    _ORIGINAL_REGISTER = routes_module.register_comprehensive_api_routes

    @wraps(_ORIGINAL_REGISTER)
    def register_comprehensive_api_routes(*args: Any, **kwargs: Any) -> Any:
        assert _ORIGINAL_REGISTER is not None
        app = _ORIGINAL_REGISTER(*args, **kwargs)
        if not getattr(app.state, "nico_mobile_projection_middleware_v1", False):
            app.add_middleware(_BrowserProjectionContextMiddleware)
            app.state.nico_mobile_projection_middleware_v1 = True
        _install_artifact_routes(app)
        return app

    routes_module.register_comprehensive_api_routes = register_comprehensive_api_routes


def install_comprehensive_mobile_recovery_v1() -> dict[str, Any]:
    global _INSTALLED, _ORIGINAL_PROJECT_REPORT
    if _INSTALLED:
        return {"status": "already_installed", "version": VERSION}
    _ORIGINAL_PROJECT_REPORT = controller_module._project_report
    controller_module._project_report = _project_report
    _install_registration_wrapper()
    _INSTALLED = True
    return {
        "status": "installed",
        "version": VERSION,
        "browser_projection_header": BROWSER_PROJECTION_HEADER,
        "browser_projection_value": BROWSER_PROJECTION_VALUE,
        "artifact_routes": sorted(ARTIFACT_ROUTE_PATHS),
        "terminal_report_embedded_for_browser": False,
        "durable_record_mutated": False,
    }


__all__ = [
    "ARTIFACT_ROUTE_PATHS",
    "BROWSER_PROJECTION_HEADER",
    "BROWSER_PROJECTION_VALUE",
    "VERSION",
    "install_comprehensive_mobile_recovery_v1",
]
