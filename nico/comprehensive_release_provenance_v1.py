from __future__ import annotations

import base64
import io
import os
import re
import sys
from copy import deepcopy
from importlib import metadata
from typing import Any, Callable

VERSION = "nico.comprehensive_release_provenance.v1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SCANNER_VERSION_BOUNDARY = (
    "Configured versions are declarations, not per-run execution evidence. Actual scanner versions "
    "come from retained per-run records; execution evidence and full configuration are qualified separately."
)


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _commit(*names: str) -> str:
    value = _first_env(*names).lower()
    return value if _SHA_RE.fullmatch(value) else "unavailable"


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "unavailable"


def comprehensive_release_provenance() -> dict[str, Any]:
    from nico import comprehensive_report_package as report_package

    # Native deployment identity outranks a manually configured release label.
    # An invalid native value must not be rescued by an unverified fallback.
    backend_commit = _commit(
        "RAILWAY_GIT_COMMIT_SHA",
        "NICO_RELEASE_COMMIT_SHA",
        "GITHUB_SHA",
    )
    identity_conflict = bool(
        _first_env("RAILWAY_GIT_COMMIT_SHA")
        and _first_env("NICO_RELEASE_COMMIT_SHA")
        and _commit("RAILWAY_GIT_COMMIT_SHA") != _commit("NICO_RELEASE_COMMIT_SHA")
    )
    frontend_commit = _commit(
        "NICO_FRONTEND_BUILD_COMMIT_SHA",
        "VERCEL_GIT_COMMIT_SHA",
    )
    return {
        "artifact_schema": VERSION,
        "deployment_identity_established": backend_commit != "unavailable" and not identity_conflict,
        "deployment_identity_conflict": identity_conflict,
        "backend_build_commit": backend_commit,
        "backend_identity_source": "RAILWAY_GIT_COMMIT_SHA" if _first_env("RAILWAY_GIT_COMMIT_SHA") else "configured_release_label",
        "frontend_build_commit": frontend_commit,
        "frontend_identity_established": frontend_commit != "unavailable",
        "frontend_identity_source": "configured_release_label" if _first_env("NICO_FRONTEND_BUILD_COMMIT_SHA") else "native_environment" if _first_env("VERCEL_GIT_COMMIT_SHA") else "unavailable",
        "frontend_deployment_id": _first_env("NICO_FRONTEND_DEPLOYMENT_ID") or "unavailable",
        "frontend_deployment_identity_verified": False,
        "railway_deployment_id": _first_env("RAILWAY_DEPLOYMENT_ID") or "unavailable",
        "railway_service_id": _first_env("RAILWAY_SERVICE_ID") or "unavailable",
        "railway_environment_id": _first_env("RAILWAY_ENVIRONMENT_ID") or "unavailable",
        "report_renderer_version": str(getattr(report_package, "VERSION", "unavailable")),
        "release_provenance_version": VERSION,
        "runtime_versions": {
            "python_package_nico": _package_version("nico-cyber-defense"),
            "reportlab": _package_version("reportlab"),
            "pypdf": _package_version("pypdf"),
        },
        "scanner_versions": {
            "osv_scanner": _first_env("NICO_OSV_SCANNER_VERSION") or "v2.3.8",
            "gitleaks": _first_env("NICO_GITLEAKS_VERSION") or "v8.30.1",
            "trufflehog": _first_env("NICO_TRUFFLEHOG_VERSION") or "v3.95.0",
            "semgrep": _first_env("NICO_SEMGREP_VERSION") or "1.170.0",
            "eslint": _first_env("NICO_ESLINT_VERSION") or "9.39.3",
            "typescript": _first_env("NICO_TYPESCRIPT_VERSION") or "6.0.3",
        },
        "truth_boundary": (
            "Unavailable values remain explicit. No deployment or tool identity is inferred "
            "from repository state alone."
        ),
    }


def _provenance_lines(provenance: dict[str, Any]) -> list[tuple[str, str]]:
    scanner = provenance.get("scanner_versions") if isinstance(provenance.get("scanner_versions"), dict) else {}
    lines = [
        ("Backend source commit", str(provenance.get("backend_build_commit") or "unavailable")),
        ("Frontend source commit", str(provenance.get("frontend_build_commit") or "unavailable")),
        ("Railway deployment", str(provenance.get("railway_deployment_id") or "unavailable")),
        ("Report renderer", str(provenance.get("report_renderer_version") or "unavailable")),
        ("Release provenance", str(provenance.get("release_provenance_version") or "unavailable")),
        ("Configured OSV-Scanner", str(scanner.get("osv_scanner") or "unavailable")),
        ("Configured Gitleaks", str(scanner.get("gitleaks") or "unavailable")),
        ("Configured TruffleHog", str(scanner.get("trufflehog") or "unavailable")),
        ("Configured Semgrep", str(scanner.get("semgrep") or "unavailable")),
        ("Configured ESLint", str(scanner.get("eslint") or "unavailable")),
        ("Configured TypeScript", str(scanner.get("typescript") or "unavailable")),
    ]
    execution = provenance.get("scanner_execution_evidence")
    if not isinstance(execution, dict):
        return lines
    lines.extend([
        ("Assessed repository commit", str(provenance.get("assessed_repository_commit") or "unavailable")),
        ("Assessment run", str(provenance.get("assessment_run_id") or "unavailable")),
        ("Scanner snapshot", str(execution.get("scan_id") or "unavailable")),
        ("Frontend deployment", str(provenance.get("frontend_deployment_id") or "unavailable")),
        ("Frontend deployment verification", "verified" if provenance.get("frontend_deployment_identity_verified") is True else "unverified"),
        ("Scanner evidence verification", str(execution.get("verification_status") or "unverified")),
    ])
    for row in execution.get("scanner_records") or []:
        name = str(row.get("scanner_name") or "unknown")
        raw = row.get("raw_artifact") or {}
        receipt = (row.get("execution_provenance") or {}).get("execution_receipt") or {}
        config = row.get("configuration") or {}
        lines.extend([
            ("Actual scanner version", f"{name}: {row.get('scanner_version') or 'unavailable'}"),
            ("Scanner execution status", f"{name}: {row.get('execution_status') or 'unknown'}; execution_evidence_verified={row.get('execution_evidence_verified') is True}; inapplicability_evidence_verified={row.get('inapplicability_evidence_verified') is True}"),
            ("Raw artifact SHA-256", f"{name}: {raw.get('sha256') or 'unavailable'}; availability={raw.get('availability') or 'unavailable'}"),
            ("Execution receipt SHA-256", f"{name}: {receipt.get('receipt_sha256') or 'unavailable'}; status={receipt.get('status') or 'not_recorded'}"),
            ("Configuration SHA-256", f"{name}: {config.get('generated_config_sha256') or 'unavailable'}; full_configuration_verified=False"),
            ("Command identity SHA-256", f"{name}: {config.get('retained_command_intent_sha256') or 'unavailable'}"),
        ])
    return lines


_ES_LABELS = {
    "Configured OSV-Scanner": "OSV-Scanner configurado",
    "Configured Gitleaks": "Gitleaks configurado",
    "Configured TruffleHog": "TruffleHog configurado",
    "Configured Semgrep": "Semgrep configurado",
    "Configured ESLint": "ESLint configurado",
    "Configured TypeScript": "TypeScript configurado",
    _SCANNER_VERSION_BOUNDARY: "Las versiones configuradas son declaraciones, no evidencia de ejecución de cada evaluación. Las versiones observadas de analizadores proceden de registros conservados; la evidencia de ejecución y la configuración completa se califican por separado.",
    "Assessed repository commit": "Commit del repositorio evaluado",
    "Assessment run": "Ejecución de la evaluación",
    "Scanner snapshot": "Instantánea de analizadores",
    "Frontend deployment": "Despliegue del frontend",
    "Frontend deployment verification": "Verificación del despliegue del frontend",
    "Scanner evidence verification": "Verificación de evidencia de analizadores",
    "Actual scanner version": "Versión observada del analizador",
    "Scanner execution status": "Estado de ejecución del analizador",
    "Raw artifact SHA-256": "SHA-256 del artefacto original",
    "Execution receipt SHA-256": "SHA-256 del comprobante de ejecución",
    "Configuration SHA-256": "SHA-256 de la configuración",
    "Command identity SHA-256": "SHA-256 de la identidad del comando",
    "Scanner evidence (continued)": "Evidencia de analizadores (continuación)",
    "unverified": "no verificado",
    "verified": "verificado",
    "unavailable": "no disponible",
}


def _presentation_localizer(localize: Callable[[str], str] | None) -> Callable[[str], str]:
    if localize is None:
        return lambda value: value
    spanish = localize("NICO Release Provenance") != "NICO Release Provenance"
    return lambda value: _ES_LABELS[value] if spanish and value in _ES_LABELS else localize(value)


def _append_provenance_pdf(
    encoded: str,
    provenance: dict[str, Any],
    localize_presentation: Callable[[str], str] | None = None,
) -> str:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen import canvas

    source = base64.b64decode(encoded, validate=True)
    if not source.startswith(b"%PDF"):
        raise ValueError("comprehensive_release_provenance_source_pdf_invalid")
    page_buffer = io.BytesIO()
    page = canvas.Canvas(page_buffer, pagesize=letter, invariant=1)
    localize = _presentation_localizer(localize_presentation)
    title = localize("NICO Release Provenance")
    page.setTitle(title)
    page.setFont("Helvetica-Bold", 16)
    page.drawString(54, 738, title)
    page.setFont("Helvetica", 8.5)
    y = 704
    def continuation() -> float:
        page.showPage()
        page.setFont("Helvetica-Bold", 12)
        page.drawString(54, 738, localize("Scanner evidence (continued)"))
        return 710

    for label, value in _provenance_lines(provenance):
        if value in {"verified", "unverified", "unavailable"}:
            value = localize(value)
        if y < 96:
            y = continuation()
        page.setFont("Helvetica-Bold", 8.5)
        page.drawString(54, y, f"{localize(label)}:")
        page.setFont("Helvetica", 8.5)
        for line in simpleSplit(value, "Helvetica", 8.5, 504):
            if y < 72:
                y = continuation()
                page.setFont("Helvetica", 8.5)
            y -= 12
            page.drawString(54, y, line)
        y -= 24
    page.setFont("Helvetica", 8)
    disclosure = localize(_SCANNER_VERSION_BOUNDARY) + " " + localize(str(provenance.get("truth_boundary") or ""))
    for line in simpleSplit(disclosure, "Helvetica", 8, 504):
        if y < 72:
            y = continuation()
            page.setFont("Helvetica", 8)
        page.drawString(54, y - 8, line)
        y -= 12
    page.save()

    writer = PdfWriter()
    for source_page in PdfReader(io.BytesIO(source)).pages:
        writer.add_page(source_page)
    for provenance_page in PdfReader(io.BytesIO(page_buffer.getvalue())).pages:
        writer.add_page(provenance_page)
    output = io.BytesIO()
    writer.write(output)
    return base64.b64encode(output.getvalue()).decode("ascii")


def _bind_release_provenance(package: Any) -> None:
    if getattr(package, "_nico_release_provenance_v1_installed", False):
        return

    original_assessment = getattr(package, "_assessment", None)
    original_markdown = getattr(package, "_markdown", None)
    original_pdf = getattr(package, "_pdf", None)

    def assessment_with_provenance(stage_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
        assessment = deepcopy(original_assessment(stage_results))
        assessment["nico_release_provenance"] = comprehensive_release_provenance()
        return assessment

    def markdown_with_provenance(
        identity: dict[str, Any],
        assessment: dict[str, Any],
        stages: list[dict[str, Any]],
        generated_at: str,
        *,
        localize_presentation: Callable[[str], str] | None = None,
    ) -> str:
        markdown = original_markdown(
            identity,
            assessment,
            stages,
            generated_at,
            localize_presentation=localize_presentation,
        )
        provenance = assessment.get("nico_release_provenance")
        if not isinstance(provenance, dict):
            provenance = comprehensive_release_provenance()
        localize = _presentation_localizer(localize_presentation)
        lines = ["", f"## {localize('NICO Release Provenance')}", ""]
        lines.extend(f"- **{localize(label)}:** `{localize(value) if value in {'verified', 'unverified', 'unavailable'} else value}`" for label, value in _provenance_lines(provenance))
        lines.extend(["", localize(_SCANNER_VERSION_BOUNDARY), "", localize(str(provenance.get("truth_boundary") or "")), ""])
        return markdown.rstrip() + "\n" + "\n".join(lines)

    def pdf_with_provenance(
        identity: dict[str, Any],
        assessment: dict[str, Any],
        stages: list[dict[str, Any]],
        generated_at: str,
        *,
        localize_presentation: Callable[[str], str] | None = None,
    ) -> tuple[str, str | None, int]:
        encoded, error, page_count = original_pdf(
            identity,
            assessment,
            stages,
            generated_at,
            localize_presentation=localize_presentation,
        )
        if not encoded or error:
            return encoded, error, page_count
        provenance = assessment.get("nico_release_provenance")
        if not isinstance(provenance, dict):
            provenance = comprehensive_release_provenance()
        try:
            from pypdf import PdfReader
            appended = _append_provenance_pdf(encoded, provenance, localize_presentation)
            actual_pages = len(PdfReader(io.BytesIO(base64.b64decode(appended, validate=True))).pages)
            return appended, None, actual_pages
        except Exception:
            return "", "release_provenance_pdf_generation_failed", 0

    for name, original, wrapped in (
        ("_assessment", original_assessment, assessment_with_provenance),
        ("_markdown", original_markdown, markdown_with_provenance),
        ("_pdf", original_pdf, pdf_with_provenance),
    ):
        if original is not None and not getattr(original, "_nico_release_provenance_bound", False):
            wrapped._nico_release_provenance_bound = True
            setattr(package, name, wrapped)
    package._nico_release_provenance_v1_installed = True


def install_comprehensive_release_provenance() -> dict[str, Any]:
    from nico import comprehensive_report_package as package

    _bind_release_provenance(package)
    # Package initialization can eagerly capture these helpers before a bootstrap
    # executes. Preserve each captured implementation while binding the same release
    # boundary; modules imported later capture the already-bound base helpers.
    for name in (
        "nico.comprehensive_canonical_report_source_v1",
        "nico.v2_premium_report_renderer",
        "nico.comprehensive_spanish_canonical_report_v87",
        "nico.comprehensive_same_run_locale_report_v1",
    ):
        captured = sys.modules.get(name)
        if captured is not None:
            _bind_release_provenance(captured)
    return {
        "artifact_schema": VERSION,
        "installed": True,
        "canonical_json_bound": True,
        "markdown_bound": True,
        "html_bound_via_markdown": True,
        "pdf_bound": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "comprehensive_release_provenance",
    "install_comprehensive_release_provenance",
]
