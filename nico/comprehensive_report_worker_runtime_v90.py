from __future__ import annotations

import base64
import hashlib
import html
import io
from copy import deepcopy
from typing import Any, Mapping

from nico import comprehensive_ci_boundary_compat_v74 as ci_v74
from nico.comprehensive_report_package import (
    build_comprehensive_report_package as _build_comprehensive_report_package_base,
)

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


def _nested_display_value(value: Any, keys: tuple[str, ...]) -> str:
    if isinstance(value, Mapping):
        for key in keys:
            if key in value:
                direct = _text(value.get(key))
                if direct:
                    return direct
        for nested in value.values():
            result = _nested_display_value(nested, keys)
            if result:
                return result
    elif isinstance(value, (list, tuple)):
        for nested in value:
            result = _nested_display_value(nested, keys)
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
            direct = _text(context.get(source_key))
            if direct:
                break
        value = direct or _nested_display_value(human_evidence, source_keys)
        if value:
            identity[output_key] = value
    return identity


def _display_identity(identity: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: _text(identity.get(key), 300)
        for key in (
            "customer_name",
            "project_name",
            "primary_technical_contact",
            "report_language",
            "locale",
        )
        if _text(identity.get(key), 300)
    }


def build_comprehensive_report_package(
    *,
    identity: dict[str, Any],
    stage_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Authoritative detached-worker package builder with durable display identity.

    The native package builder intentionally narrows identity to canonical scope IDs.
    That is correct for authorization boundaries but previously discarded optional
    client/project/contact display metadata immediately before canonical report truth was
    frozen. The detached worker is the first boundary that has both the durable recovered
    display metadata and the final package, so preserve those fields here as stable source
    behavior rather than through an installer or process-order-sensitive monkey patch.

    Canonical customer_id/project_id, repository identity, scores, findings, candidate
    dispositions, human-review state and delivery authority are not modified.
    """

    from nico import comprehensive_report_package as report_module

    result = _build_comprehensive_report_package_base(
        identity=identity,
        stage_results=stage_results,
    )
    if not isinstance(result, dict):
        return result

    display = _display_identity(identity)
    if not display:
        return result

    report_package = (
        deepcopy(dict(result.get("report_package") or {}))
        if isinstance(result.get("report_package"), Mapping)
        else {}
    )
    canonical = (
        deepcopy(dict(report_package.get("json") or {}))
        if isinstance(report_package.get("json"), Mapping)
        else {}
    )
    if not canonical:
        return result

    canonical_identity = (
        deepcopy(dict(canonical.get("identity") or {}))
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    canonical_identity.update(display)
    canonical["identity"] = canonical_identity

    assessment = (
        deepcopy(dict(canonical.get("assessment") or {}))
        if isinstance(canonical.get("assessment"), Mapping)
        else deepcopy(dict(result.get("assessment") or {}))
    )
    stages = (
        deepcopy(list(canonical.get("stage_summaries") or []))
        if isinstance(canonical.get("stage_summaries"), list)
        else deepcopy(list(result.get("stage_summaries") or []))
    )
    generated_at = _text(result.get("generated_at"), 100)
    if not generated_at:
        return result

    # Regenerate the three report presentation formats from the repaired canonical
    # identity. This closes the exact production failure where canonical metadata was
    # repaired only after the first PDF had already been rendered.
    markdown = report_module._markdown(
        canonical_identity,
        assessment,
        stages,
        generated_at,
    )
    title = (
        "NICO Comprehensive Technical Assessment — "
        + _text(canonical_identity.get("repository"), 300)
    )
    rendered_html = report_module._semantic_html(markdown, title)

    # The PDF row is explicitly labelled Customer / Project, so use the supplied display
    # names for that human-facing row when present while keeping canonical scope IDs in
    # the canonical JSON untouched.
    pdf_identity = dict(canonical_identity)
    if _text(pdf_identity.get("customer_name"), 180):
        pdf_identity["customer_id"] = _text(pdf_identity.get("customer_name"), 180)
    if _text(pdf_identity.get("project_name"), 180):
        pdf_identity["project_id"] = _text(pdf_identity.get("project_name"), 180)
    pdf_base64, pdf_error, page_count = report_module._pdf(
        pdf_identity,
        assessment,
        stages,
        generated_at,
    )
    pdf_bytes = base64.b64decode(pdf_base64) if pdf_base64 else b""

    report_id = (
        "comprehensive_report_"
        + report_module._canonical_hash(
            {"identity": canonical_identity, "stages": stages}
        )[:20]
    )
    canonical_truth_sha256 = report_module._canonical_hash(canonical)
    report_package.update(
        {
            "report_id": report_id,
            "markdown": markdown,
            "html": rendered_html,
            "json": canonical,
            "pdf_base64": pdf_base64,
            "pdf_error": pdf_error,
            "pdf_page_count": page_count,
            "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else "",
            "canonical_truth_sha256": canonical_truth_sha256,
        }
    )
    quality = (
        deepcopy(dict(report_package.get("report_quality_contract") or {}))
        if isinstance(report_package.get("report_quality_contract"), Mapping)
        else {}
    )
    quality.update(
        {
            "display_metadata_preserved_in_canonical_report_identity": True,
            "cross_format_outputs_regenerated_from_repaired_identity": True,
            "canonical_scope_ids_unchanged": True,
            "scores_findings_review_and_delivery_authority_unchanged": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    report_package["report_quality_contract"] = quality

    result.update(
        {
            "status": (
                "complete"
                if pdf_base64 and not pdf_error and pdf_bytes.startswith(b"%PDF")
                else "blocked"
            ),
            "report_id": report_id,
            "assessment": assessment,
            "canonical_truth_sha256": canonical_truth_sha256,
            "report_quality_contract": deepcopy(quality),
            "report_package": report_package,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    return result


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

    v92 additionally makes display-metadata preservation part of the stable detached
    report builder itself. No installer or process-order-sensitive patch is required for
    client/project/contact metadata to survive into canonical report truth and the first
    rendered package.
    """

    from nico import comprehensive_ci_pdf_control_safety_v89 as v89
    from nico import comprehensive_native_providers as providers
    from nico import comprehensive_rendered_ci_boundary_producer_v79 as producer
    from nico import comprehensive_spanish_exit_criteria_v88 as v88

    # Intentionally repair the private compatibility delegates here. They are process-
    # local implementation pointers, not canonical evidence. Resetting them does not
    # alter run identity, score, findings, review state, or client-delivery authority.
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
        "display_metadata_preserved_without_runtime_installer": True,
        "cross_format_outputs_regenerated_from_repaired_identity": True,
        "canonical_scope_identity_unchanged": True,
        "spanish_guard_bound": spanish_guard.get("bound") is True,
        "ci_pdf_guard_bound": pdf_guard.get("bound") is True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "build_comprehensive_report_package",
    "install_report_worker_runtime_v90",
    "report_stage",
]
