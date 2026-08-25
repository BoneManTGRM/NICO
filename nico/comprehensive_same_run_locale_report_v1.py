from __future__ import annotations

import base64
import hashlib
import re
from copy import deepcopy
from typing import Any, Mapping

from fastapi import FastAPI, HTTPException, Response

from nico.comprehensive_report_package import (
    _canonical_hash,
    _markdown,
    _pdf,
    _semantic_html,
)
from nico.comprehensive_spanish_canonical_report_v87 import (
    render_spanish_html,
    render_spanish_markdown,
    render_spanish_pdf,
)


VERSION = "nico.comprehensive_same_run_locale_report.v1"
ROUTE = "/assessment/comprehensive-run/{run_id}/localized-report/{report_language}"
PDF_ROUTE = f"{ROUTE}/pdf"
SUPPORTED_REPORT_LANGUAGES = ("en", "es-MX")


def _route_count(target: FastAPI, method: str, path: str) -> int:
    expected = method.upper()
    return sum(
        1
        for route in target.routes
        if str(getattr(route, "path", "")) == path
        and expected
        in {
            str(item).upper()
            for item in (getattr(route, "methods", set()) or set())
        }
    )


def _normalize_report_language(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.lower() == "en":
        return "en"
    if raw.lower() in {"es-mx", "es_mx"}:
        return "es-MX"
    raise ValueError("unsupported_report_language")


def _render_inputs(
    canonical: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str]:
    identity = (
        deepcopy(dict(canonical.get("identity") or {}))
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    assessment = (
        deepcopy(dict(canonical.get("assessment") or {}))
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    stages = [
        deepcopy(dict(item))
        for item in canonical.get("stage_summaries") or []
        if isinstance(item, Mapping)
    ]
    generated_at = str(
        identity.get("generated_at")
        or identity.get("generation_timestamp")
        or canonical.get("generated_at")
        or canonical.get("generation_timestamp")
        or ""
    )
    return identity, assessment, stages, generated_at


def _english_artifacts(canonical: Mapping[str, Any]) -> dict[str, Any]:
    identity, assessment, stages, generated_at = _render_inputs(canonical)
    repository = str(identity.get("repository") or "repository")
    markdown = _markdown(identity, assessment, stages, generated_at)
    title = f"NICO Comprehensive Technical Assessment — {repository}"
    html = _semantic_html(markdown, title)
    encoded, error, page_count = _pdf(identity, assessment, stages, generated_at)
    if error or not encoded:
        raise ValueError(
            f"canonical English PDF renderer failed: {error or 'empty PDF'}"
        )
    pdf_bytes = base64.b64decode(encoded)
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("canonical English PDF renderer returned an invalid PDF")
    return {
        "markdown": markdown,
        "html": html,
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "pdf_page_count": int(page_count or 0),
    }


def _spanish_artifacts(canonical: Mapping[str, Any]) -> dict[str, Any]:
    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    repository = str(identity.get("repository") or "repository")
    markdown = render_spanish_markdown(canonical)
    title = f"Evaluación Técnica Integral NICO — {repository}"
    html = render_spanish_html(markdown, title)
    pdf_bytes, page_count = render_spanish_pdf(canonical)
    return {
        "markdown": markdown,
        "html": html,
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "pdf_page_count": int(page_count or 0),
    }


def _render_target(
    canonical: Mapping[str, Any], report_language: str
) -> dict[str, Any]:
    if report_language == "en":
        return _english_artifacts(canonical)
    if report_language == "es-MX":
        return _spanish_artifacts(canonical)
    raise ValueError("unsupported_report_language")


def _safe_repository(value: Any) -> str:
    normalized = re.sub(
        r"[^A-Za-z0-9_.-]+", "-", str(value or "repository")
    ).strip("-")
    return normalized or "repository"


def _localized_filename(
    *, canonical: Mapping[str, Any], run_id: str, report_language: str
) -> str:
    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    repository = _safe_repository(identity.get("repository"))
    locale = "en" if report_language == "en" else "es-MX"
    return (
        f"nico-comprehensive-assessment-{repository}-{run_id}-{locale}-"
        "AUTOMATED-DRAFT-PENDING-APPROVAL.pdf"
    )


def build_same_run_locale_report(
    status: Mapping[str, Any],
    report_language: str,
) -> dict[str, Any]:
    """Render a presentation locale from one terminal immutable run.

    This function is deliberately read-only. It neither resumes the assessment nor
    changes review, approval, acceptance, or delivery state. Both language outputs are
    derived from the exact canonical JSON already attached to the terminal report.
    """

    target_language = _normalize_report_language(report_language)
    if status.get("terminal") is not True:
        raise ValueError("terminal_report_required")

    reports = (
        status.get("reports") if isinstance(status.get("reports"), Mapping) else {}
    )
    canonical = (
        reports.get("json") if isinstance(reports.get("json"), Mapping) else {}
    )
    if not canonical:
        raise ValueError("terminal_canonical_report_json_required")

    canonical_copy = deepcopy(dict(canonical))
    canonical_truth_sha256 = _canonical_hash(canonical_copy)
    expected_truth_sha256 = str(reports.get("canonical_truth_sha256") or "").strip()
    if expected_truth_sha256 and expected_truth_sha256 != canonical_truth_sha256:
        raise ValueError("canonical_truth_hash_mismatch")

    source_language = _normalize_report_language(
        status.get("report_language") or "en"
    )
    if target_language == source_language:
        markdown = reports.get("markdown")
        html = reports.get("html")
        encoded_pdf = reports.get("pdf_base64")
        if (
            isinstance(markdown, str)
            and isinstance(html, str)
            and isinstance(encoded_pdf, str)
            and encoded_pdf
        ):
            try:
                pdf_bytes = base64.b64decode(encoded_pdf, validate=True)
            except Exception as exc:
                raise ValueError("source_report_pdf_invalid") from exc
            if not pdf_bytes.startswith(b"%PDF"):
                raise ValueError("source_report_pdf_invalid")
            artifacts = {
                "markdown": markdown,
                "html": html,
                "pdf_base64": encoded_pdf,
                "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
                "pdf_page_count": reports.get("pdf_page_count"),
            }
        else:
            artifacts = _render_target(canonical_copy, target_language)
    else:
        artifacts = _render_target(canonical_copy, target_language)

    identity = (
        canonical_copy.get("identity")
        if isinstance(canonical_copy.get("identity"), Mapping)
        else {}
    )
    run_id = str(status.get("run_id") or identity.get("run_id") or "")
    if not run_id:
        raise ValueError("run_id_required")

    source_report_id = str(reports.get("report_id") or "")
    result = {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "run_id": run_id,
        "repository": str(status.get("repository") or ""),
        "commit_sha": str(status.get("commit_sha") or ""),
        "source_report_id": source_report_id,
        "source_report_language": source_language,
        "report_language": target_language,
        "same_canonical_run": True,
        "assessment_rerun": False,
        "canonical_truth_preserved": True,
        "canonical_truth_sha256": canonical_truth_sha256,
        "source_integrity_sha256": str(status.get("integrity_sha256") or ""),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "approval_state_mutated": False,
        "delivery_state_mutated": False,
        "report": {
            "service_id": "comprehensive",
            "report_id": source_report_id,
            "presentation_language": target_language,
            "canonical_truth_sha256": canonical_truth_sha256,
            "json": canonical_copy,
            "markdown": artifacts["markdown"],
            "html": artifacts["html"],
            "pdf_base64": artifacts["pdf_base64"],
            "pdf_filename": _localized_filename(
                canonical=canonical_copy,
                run_id=run_id,
                report_language=target_language,
            ),
            "pdf_sha256": artifacts["pdf_sha256"],
            "pdf_page_count": artifacts.get("pdf_page_count"),
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    }
    return result


def build_same_run_locale_pdf_response(
    status: Mapping[str, Any], report_language: str
) -> Response:
    projection = build_same_run_locale_report(status, report_language)
    report = projection["report"]
    try:
        pdf_bytes = base64.b64decode(report["pdf_base64"], validate=True)
    except Exception as exc:
        raise ValueError("localized_report_pdf_invalid") from exc
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("localized_report_pdf_invalid")

    expected_sha256 = str(report.get("pdf_sha256") or "")
    actual_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    if expected_sha256 and expected_sha256 != actual_sha256:
        raise ValueError("localized_report_pdf_hash_mismatch")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{report["pdf_filename"]}"',
            "X-NICO-Run-ID": str(projection["run_id"]),
            "X-NICO-Report-Language": str(projection["report_language"]),
            "X-NICO-Canonical-Truth-SHA256": str(
                projection["canonical_truth_sha256"]
            ),
            "X-NICO-Assessment-Rerun": "false",
        },
    )


def _controller_status(target: FastAPI, run_id: str) -> Mapping[str, Any]:
    controller = getattr(target.state, "comprehensive_api_controller", None)
    if controller is None or not callable(getattr(controller, "status", None)):
        raise HTTPException(
            status_code=503,
            detail={
                "status": "blocked",
                "reason": "comprehensive_controller_unavailable",
            },
        )
    try:
        return controller.status(run_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "not_found",
                "reason": "comprehensive_run_not_found",
            },
        ) from exc


def _projection_http_error(exc: ValueError) -> HTTPException:
    reason = str(exc)
    status_code = 422 if reason == "unsupported_report_language" else 409
    return HTTPException(
        status_code=status_code,
        detail={"status": "blocked", "reason": reason},
    )


def install_same_run_locale_report(target: FastAPI) -> dict[str, Any]:
    """Install read-only bilingual report projection routes exactly once."""

    if _route_count(target, "GET", ROUTE) == 0:

        def localized_report(run_id: str, report_language: str) -> dict[str, Any]:
            try:
                status = _controller_status(target, run_id)
                return build_same_run_locale_report(status, report_language)
            except ValueError as exc:
                raise _projection_http_error(exc) from exc

        target.add_api_route(
            ROUTE,
            localized_report,
            methods=["GET"],
            tags=["comprehensive"],
        )
        target.openapi_schema = None

    if _route_count(target, "GET", PDF_ROUTE) == 0:

        def localized_report_pdf(run_id: str, report_language: str) -> Response:
            try:
                status = _controller_status(target, run_id)
                return build_same_run_locale_pdf_response(status, report_language)
            except ValueError as exc:
                raise _projection_http_error(exc) from exc

        target.add_api_route(
            PDF_ROUTE,
            localized_report_pdf,
            methods=["GET"],
            tags=["comprehensive"],
            response_class=Response,
        )
        target.openapi_schema = None

    route_count = _route_count(target, "GET", ROUTE)
    pdf_route_count = _route_count(target, "GET", PDF_ROUTE)
    status = {
        "artifact_schema": VERSION,
        "route": ROUTE,
        "route_count": route_count,
        "pdf_route": PDF_ROUTE,
        "pdf_route_count": pdf_route_count,
        "supported_report_languages": list(SUPPORTED_REPORT_LANGUAGES),
        "same_canonical_run": True,
        "assessment_rerun": False,
        "canonical_truth_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    target.state.nico_same_run_locale_report = status
    return status


__all__ = [
    "PDF_ROUTE",
    "ROUTE",
    "SUPPORTED_REPORT_LANGUAGES",
    "VERSION",
    "build_same_run_locale_pdf_response",
    "build_same_run_locale_report",
    "install_same_run_locale_report",
]
