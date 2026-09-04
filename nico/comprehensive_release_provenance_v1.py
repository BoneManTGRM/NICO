from __future__ import annotations

import base64
import io
import os
import re
from copy import deepcopy
from importlib import metadata
from typing import Any, Callable

VERSION = "nico.comprehensive_release_provenance.v1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


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

    backend_commit = _commit(
        "NICO_RELEASE_COMMIT_SHA",
        "RAILWAY_GIT_COMMIT_SHA",
        "GITHUB_SHA",
    )
    frontend_commit = _commit(
        "NICO_FRONTEND_BUILD_COMMIT_SHA",
        "VERCEL_GIT_COMMIT_SHA",
    )
    return {
        "artifact_schema": VERSION,
        "deployment_identity_established": backend_commit != "unavailable",
        "backend_build_commit": backend_commit,
        "frontend_build_commit": frontend_commit,
        "frontend_identity_established": frontend_commit != "unavailable",
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
    return [
        ("Backend source commit", str(provenance.get("backend_build_commit") or "unavailable")),
        ("Frontend source commit", str(provenance.get("frontend_build_commit") or "unavailable")),
        ("Railway deployment", str(provenance.get("railway_deployment_id") or "unavailable")),
        ("Report renderer", str(provenance.get("report_renderer_version") or "unavailable")),
        ("Release provenance", str(provenance.get("release_provenance_version") or "unavailable")),
        ("OSV-Scanner", str(scanner.get("osv_scanner") or "unavailable")),
        ("Gitleaks", str(scanner.get("gitleaks") or "unavailable")),
        ("TruffleHog", str(scanner.get("trufflehog") or "unavailable")),
        ("Semgrep", str(scanner.get("semgrep") or "unavailable")),
    ]


def _append_provenance_pdf(encoded: str, provenance: dict[str, Any]) -> str:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    source = base64.b64decode(encoded, validate=True)
    if not source.startswith(b"%PDF"):
        raise ValueError("comprehensive_release_provenance_source_pdf_invalid")
    page_buffer = io.BytesIO()
    page = canvas.Canvas(page_buffer, pagesize=letter, invariant=1)
    page.setTitle("NICO Release Provenance")
    page.setFont("Helvetica-Bold", 16)
    page.drawString(54, 738, "NICO Release Provenance")
    page.setFont("Helvetica", 8.5)
    y = 704
    for label, value in _provenance_lines(provenance):
        page.setFont("Helvetica-Bold", 8.5)
        page.drawString(54, y, f"{label}:")
        page.setFont("Helvetica", 8.5)
        page.drawString(190, y, value[:96])
        y -= 22
    page.setFont("Helvetica", 8)
    page.drawString(54, y - 8, str(provenance.get("truth_boundary") or "")[:115])
    page.save()

    writer = PdfWriter()
    for source_page in PdfReader(io.BytesIO(source)).pages:
        writer.add_page(source_page)
    for provenance_page in PdfReader(io.BytesIO(page_buffer.getvalue())).pages:
        writer.add_page(provenance_page)
    output = io.BytesIO()
    writer.write(output)
    return base64.b64encode(output.getvalue()).decode("ascii")


def install_comprehensive_release_provenance() -> dict[str, Any]:
    from nico import comprehensive_report_package as package

    if getattr(package, "_nico_release_provenance_v1_installed", False):
        return {"artifact_schema": VERSION, "installed": True}

    original_assessment = package._assessment
    original_markdown = package._markdown
    original_pdf = package._pdf

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
        localize = localize_presentation or (lambda value: value)
        lines = ["", f"## {localize('NICO Release Provenance')}", ""]
        lines.extend(f"- **{localize(label)}:** `{value}`" for label, value in _provenance_lines(provenance))
        lines.extend(["", localize(str(provenance.get("truth_boundary") or "")), ""])
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
            return _append_provenance_pdf(encoded, provenance), None, int(page_count or 0) + 1
        except Exception:
            return "", "release_provenance_pdf_generation_failed", 0

    package._assessment = assessment_with_provenance
    package._markdown = markdown_with_provenance
    package._pdf = pdf_with_provenance
    package._nico_release_provenance_v1_installed = True
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
