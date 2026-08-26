from __future__ import annotations

import html
import io
from typing import Any, Mapping

from nico import comprehensive_ci_boundary_compat_v74 as ci_v74
from nico.comprehensive_report_package import build_comprehensive_report_package

VERSION = "nico.comprehensive-report-worker-runtime.v92"
_REPORT_STAGES = {
    "decision_report_generation",
    "final_comprehensive_report_generation",
}
_DISPLAY_IDENTITY_FIELDS = (
    ("customer_name", ("customer_name", "client_name")),
    ("project_name", ("project_name",)),
    ("primary_technical_contact", ("primary_technical_contact",)),
)


def report_stage(stage_id: Any) -> bool:
    return str(stage_id or "").strip() in _REPORT_STAGES


def _text(value: Any, limit: int = 300) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _display_scalar(value: Any, keys: tuple[str, ...]) -> str:
    """Return one retained display value without serializing list/container syntax."""

    if isinstance(value, Mapping):
        return _nested_display_value(value, keys)
    if isinstance(value, (list, tuple)):
        for item in value:
            result = _display_scalar(item, keys)
            if result:
                return result
        return ""
    return _text(value)


def _nested_display_value(value: Any, keys: tuple[str, ...]) -> str:
    if isinstance(value, Mapping):
        for key in keys:
            if key in value:
                direct = _display_scalar(value.get(key), keys)
                if direct:
                    return direct
        for nested in value.values():
            result = _nested_display_value(nested, keys)
            if result:
                return result
    elif isinstance(value, (list, tuple)):
        for nested in value:
            result = _display_scalar(nested, keys)
            if result:
                return result
    return ""


def _report_identity(context: Mapping[str, Any]) -> dict[str, str]:
    """Build final-report identity with durable display-metadata fallback.

    The final report runs behind a detached publication boundary. Canonical scope
    identity remains sourced from the native provider, while optional display metadata
    is recovered from the exact run context first and from normalized retained human
    evidence second. This avoids relying on process-order-sensitive runtime wrappers.
    """

    from nico import comprehensive_native_providers as providers

    identity = providers._identity(dict(context))
    human_evidence = context.get("human_evidence")
    for output_key, source_keys in _DISPLAY_IDENTITY_FIELDS:
        direct = ""
        for source_key in source_keys:
            direct = _display_scalar(context.get(source_key), source_keys)
            if direct:
                break
        value = direct or _nested_display_value(human_evidence, source_keys)
        if value:
            identity[output_key] = value
    return identity


def _native_report_base_v90(context: dict[str, Any], final: bool) -> dict[str, Any]:
    """Stable native report implementation independent of mutable provider aliases.

    The production provider entry points intentionally resolve ``providers._build_report``
    at call time. Compatibility guards may rebind that public alias. This base function
    reproduces the native provider contract without delegating through the mutable alias,
    so it cannot become self-recursive when a detached worker starts after late runtime
    compatibility installation.
    """

    from nico import comprehensive_native_providers as providers

    prior = (
        context.get("prior_stage_results")
        if isinstance(context.get("prior_stage_results"), dict)
        else {}
    )
    package = build_comprehensive_report_package(
        identity=_report_identity(context),
        stage_results=prior,
    )
    if str(package.get("status") or "blocked") != "complete":
        report = (
            package.get("report_package")
            if isinstance(package.get("report_package"), dict)
            else {}
        )
        return providers._result(
            context,
            "blocked",
            reason=(
                package.get("reason")
                or report.get("pdf_error")
                or "report_generation_failed"
            ),
            report_package=report,
        )
    return providers._result(
        context,
        summary=(
            "The final native Comprehensive Markdown, HTML, JSON, and PDF draft package was generated."
            if final
            else "The core decision report was generated from reconciled technical evidence."
        ),
        report_package=package["report_package"],
        assessment=package["assessment"],
        evidence={
            "report_id": package.get("report_id"),
            "pdf_page_count": package["report_package"].get("pdf_page_count"),
            "canonical_truth_sha256": package.get("canonical_truth_sha256"),
            "final_package": final,
        },
    )


def _boundary_pdf_page_base_v90(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> bytes:
    """Stable CI/CD boundary-page producer independent of its mutable public alias."""

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    section = ci_v74.ci_operational_truth_markdown(
        canonical,
        spanish=spanish,
        force=True,
    )
    if not section:
        raise ValueError("rendered CI/CD producer could not build the canonical boundary")

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "RenderedCIBoundaryHeading",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        textColor=colors.HexColor("#075985"),
        spaceAfter=12,
    )
    subheading = ParagraphStyle(
        "RenderedCIBoundarySubheading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=8,
        spaceAfter=6,
    )
    body = ParagraphStyle(
        "RenderedCIBoundaryBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )
    bullet = ParagraphStyle(
        "RenderedCIBoundaryBullet",
        parent=body,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=7,
    )

    story: list[Any] = [Spacer(1, 0.2 * inch)]
    for raw in section.splitlines():
        line = raw.strip()
        if not line:
            continue
        escaped = html.escape(line)
        if line.startswith("## "):
            story.append(Paragraph(html.escape(line[3:]), heading))
        elif line.startswith("### "):
            story.append(Paragraph(html.escape(line[4:]), subheading))
        elif line.startswith("- "):
            story.append(Paragraph("• " + html.escape(line[2:]), bullet))
        else:
            story.append(Paragraph(escaped, body))

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=(
            "Preparación operativa y salud histórica de CI/CD"
            if spanish
            else "CI/CD Operational Readiness and Historical Health"
        ),
        author="NICO",
        invariant=1,
    )
    document.build(story)
    return buffer.getvalue()


def install_report_worker_runtime_v90() -> dict[str, Any]:
    """Rebind detached report workers to stable non-recursive base delegates.

    Earlier runtime guards made their first captured delegate immutable, which prevents
    later recapture but does not protect the *first* installation when a late wrapper is
    already occupying a mutable alias. A production detached worker can therefore still
    inherit a recursive base on process/runtime ordering that differs from tests.

    v90 removes that ordering dependency at the report-worker boundary. The two base
    implementations below never delegate through the mutable public aliases. The v88
    Spanish/report guard and v89 CI/CD PDF sanitizer remain authoritative wrappers, but
    their stored delegates are reset to these stable bases immediately before a report
    stage executes.

    v92 additionally normalizes list-shaped retained engagement fields before resolving
    optional client/project/contact display metadata. This prevents compact mobile human
    evidence such as ``["Primary Contact"]`` from being rendered as Python container
    syntax in canonical identity or the final report. Canonical scope IDs remain unchanged.
    """

    from nico import comprehensive_ci_pdf_control_safety_v89 as v89
    from nico import comprehensive_native_providers as providers
    from nico import comprehensive_rendered_ci_boundary_producer_v79 as producer
    from nico import comprehensive_spanish_exit_criteria_v88 as v88

    v88._ORIGINAL_NATIVE_BUILD_REPORT = _native_report_base_v90
    v89._ORIGINAL_BOUNDARY_PDF_PAGE = _boundary_pdf_page_base_v90

    providers._build_report = v88._native_build_report_v88
    producer._boundary_pdf_page = v89._boundary_pdf_page_v89

    spanish_guard = v88.install_comprehensive_spanish_exit_criteria_v88()
    pdf_guard = v89.install_comprehensive_ci_pdf_control_safety_v89()

    if providers._build_report is not v88._native_build_report_v88:
        raise RuntimeError("v90 report worker failed to bind the stable report guard")
    if producer._boundary_pdf_page is not v89._boundary_pdf_page_v89:
        raise RuntimeError("v90 report worker failed to bind the stable CI/CD PDF guard")
    if v88._ORIGINAL_NATIVE_BUILD_REPORT is not _native_report_base_v90:
        raise RuntimeError("v90 report worker lost its stable native report base")
    if v89._ORIGINAL_BOUNDARY_PDF_PAGE is not _boundary_pdf_page_base_v90:
        raise RuntimeError("v90 report worker lost its stable CI/CD PDF base")

    return {
        "status": "installed",
        "version": VERSION,
        "native_report_base_stable": True,
        "ci_pdf_base_stable": True,
        "first_install_order_independent": True,
        "detached_report_alias_recursion_blocked": True,
        "display_metadata_identity_fallback_bound": True,
        "list_shaped_display_metadata_normalized": True,
        "canonical_scope_identity_unchanged": True,
        "spanish_guard_bound": spanish_guard.get("bound") is True,
        "ci_pdf_guard_bound": pdf_guard.get("bound") is True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_report_worker_runtime_v90",
    "report_stage",
]
