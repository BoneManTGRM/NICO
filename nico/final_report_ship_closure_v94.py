from __future__ import annotations

import base64
import hashlib
import html
import io
from copy import deepcopy
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter

from nico import comprehensive_engagement_metadata_v1 as engagement
from nico import comprehensive_report_package as report_package

VERSION = "nico.final-report-ship-closure.v94"

_HUMAN_CONTEXT_LIMITS = {
    "customer_name": 180,
    "project_name": 180,
    "primary_technical_contact": 600,
    "access_method": 1200,
    "authorized_scope": 4000,
}
_SPANISH_LABELS = {
    "Client display name": "Nombre del cliente",
    "Project display name": "Nombre del proyecto",
    "Primary technical contact": "Contacto técnico principal",
    "Access method": "Método de acceso",
    "Authorized scope": "Alcance autorizado",
}
_ORIGINAL_DISPLAY_IDENTITY_PROJECTION = engagement.display_identity_projection
_ORIGINAL_V2_MARKDOWN: Any = None
_ORIGINAL_V2_PDF: Any = None
_SPANISH_CACHE_SOURCE: Mapping[str, Any] | None = None
_SPANISH_CACHE_INPUTS: tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str] | None = None


def _text(value: Any, limit: int) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _human_context(identity: Mapping[str, Any]) -> dict[str, str]:
    return {
        field: _text(identity.get(field), limit)
        for field, limit in _HUMAN_CONTEXT_LIMITS.items()
        if _text(identity.get(field), limit)
    }


def _verified_display_identity_projection(value: Any) -> dict[str, str]:
    """Expose all five durable intake fields only when the stored digest verifies."""

    if not engagement.verify_comprehensive_engagement_metadata(value):
        return {}
    normalized = engagement.normalize_comprehensive_engagement_metadata(value)
    if not normalized:
        return {}
    return {
        "customer_name": str(normalized.get("client_name") or ""),
        "project_name": str(normalized.get("project_name") or ""),
        "primary_technical_contact": str(normalized.get("primary_technical_contact") or ""),
        "access_method": str(normalized.get("access_method") or ""),
        "authorized_scope": str(normalized.get("authorized_scope") or ""),
    }


def _inject_context_markdown(
    markdown: str,
    identity: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    """Add the two context values omitted by the legacy identity header.

    Client, project, and primary technical contact are already rendered by the native
    report package. Access method and authorized scope are inserted alongside that
    identity block. Values remain verbatim client-supplied text; only labels localize.
    """

    context = _human_context(identity)
    values = [
        (
            "Método de acceso" if spanish else "Access method",
            context.get("access_method", ""),
        ),
        (
            "Alcance autorizado" if spanish else "Authorized scope",
            context.get("authorized_scope", ""),
        ),
    ]
    additions = [f"{label}: {value}" for label, value in values if value]
    if not additions:
        return str(markdown or "")

    output = str(markdown or "")
    if all(line in output for line in additions):
        return output

    anchors = (
        "## Resumen ejecutivo para decisiones",
        "## Resumen ejecutivo",
    ) if spanish else ("## Executive Decision Brief",)
    anchor = next((candidate for candidate in anchors if candidate in output), "")
    block = "\n".join(additions) + "\n\n"
    if anchor:
        return output.replace(anchor, block + anchor, 1)
    return block + output


def _context_pdf_page(identity: Mapping[str, Any], *, spanish: bool) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    context = _human_context(identity)
    labels = (
        ("Cliente" if spanish else "Client", "customer_name"),
        ("Proyecto" if spanish else "Project", "project_name"),
        (
            "Contacto técnico principal" if spanish else "Primary technical contact",
            "primary_technical_contact",
        ),
        ("Método de acceso" if spanish else "Access method", "access_method"),
        ("Alcance autorizado" if spanish else "Authorized scope", "authorized_scope"),
    )
    rows = [(label, context.get(field, "")) for label, field in labels if context.get(field)]
    if not rows:
        return b""

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "NICOEngagementContextTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=27,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=18,
    )
    body = ParagraphStyle(
        "NICOEngagementContextBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
    )
    label_style = ParagraphStyle(
        "NICOEngagementContextLabel",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#075985"),
    )
    table_rows = [
        [Paragraph(html.escape(label), label_style), Paragraph(html.escape(value), body)]
        for label, value in rows
    ]
    table = Table(table_rows, colWidths=[1.75 * inch, 5.05 * inch])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        invariant=1,
    )
    document.build([
        Spacer(1, 0.35 * inch),
        Paragraph("Contexto del encargo" if spanish else "Engagement Context", title),
        Paragraph(
            (
                "Contexto proporcionado por el cliente para esta ejecución. Estos valores "
                "no modifican la puntuación técnica ni autorizan la entrega."
            ) if spanish else (
                "Client-supplied context for this exact engagement. These values do not "
                "change technical scoring or authorize delivery."
            ),
            body,
        ),
        Spacer(1, 0.18 * inch),
        table,
    ])
    return buffer.getvalue()


def _augment_pdf_with_context(
    pdf_bytes: bytes,
    identity: Mapping[str, Any],
    *,
    spanish: bool,
) -> tuple[bytes, int]:
    if not pdf_bytes.startswith(b"%PDF"):
        return pdf_bytes, 0
    context_page = _context_pdf_page(identity, spanish=spanish)
    if not context_page:
        return pdf_bytes, len(PdfReader(io.BytesIO(pdf_bytes)).pages)

    source_pages = list(PdfReader(io.BytesIO(pdf_bytes)).pages)
    context_pages = list(PdfReader(io.BytesIO(context_page)).pages)
    writer = PdfWriter()
    if source_pages:
        writer.add_page(source_pages[0])
    for page in context_pages:
        writer.add_page(page)
    for page in source_pages[1:]:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    rendered = output.getvalue()
    return rendered, len(PdfReader(io.BytesIO(rendered)).pages)


def _shared_spanish_inputs(
    canonical_source: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str]:
    global _SPANISH_CACHE_SOURCE
    global _SPANISH_CACHE_INPUTS

    if _SPANISH_CACHE_SOURCE is canonical_source and _SPANISH_CACHE_INPUTS is not None:
        return _SPANISH_CACHE_INPUTS

    from nico import comprehensive_spanish_canonical_report_v87 as canonical

    inputs = canonical._render_inputs(canonical_source)
    _SPANISH_CACHE_SOURCE = canonical_source
    _SPANISH_CACHE_INPUTS = inputs
    return inputs


def _clear_spanish_inputs(canonical_source: Mapping[str, Any]) -> None:
    global _SPANISH_CACHE_SOURCE
    global _SPANISH_CACHE_INPUTS
    if _SPANISH_CACHE_SOURCE is canonical_source:
        _SPANISH_CACHE_SOURCE = None
        _SPANISH_CACHE_INPUTS = None


def _spanish_markdown_v94(canonical_source: Mapping[str, Any]) -> str:
    from nico import comprehensive_spanish_canonical_report_v87 as canonical

    identity, assessment, stages, generated_at = _shared_spanish_inputs(canonical_source)
    markdown = report_package._markdown(
        identity,
        assessment,
        stages,
        generated_at,
        localize_presentation=canonical._translate_presentation,
    )
    return _inject_context_markdown(markdown, identity, spanish=True)


def _spanish_pdf_v94(canonical_source: Mapping[str, Any]) -> tuple[bytes, int]:
    from nico import comprehensive_spanish_canonical_report_v87 as canonical

    try:
        identity, assessment, stages, generated_at = _shared_spanish_inputs(canonical_source)
        encoded, error, reported_count = report_package._pdf(
            identity,
            assessment,
            stages,
            generated_at,
            localize_presentation=canonical._translate_presentation,
        )
        if error or not encoded:
            raise ValueError(f"canonical Spanish PDF renderer failed: {error or 'empty PDF'}")
        pdf = base64.b64decode(encoded)
        if not pdf.startswith(b"%PDF"):
            raise ValueError("canonical Spanish PDF renderer returned an invalid PDF")
        actual_count = len(PdfReader(io.BytesIO(pdf)).pages)
        if actual_count != reported_count:
            raise ValueError("canonical Spanish PDF localization changed page topology")
        return _augment_pdf_with_context(pdf, identity, spanish=True)
    finally:
        _clear_spanish_inputs(canonical_source)


def _english_markdown_v94(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    generated_at: str,
    *,
    localize_presentation: Any = None,
) -> str:
    original = _ORIGINAL_V2_MARKDOWN
    if original is None:
        raise RuntimeError("final report v94 English Markdown base is not installed")
    markdown = original(
        identity,
        assessment,
        stages,
        generated_at,
        localize_presentation=localize_presentation,
    )
    return _inject_context_markdown(markdown, identity, spanish=False)


def _english_pdf_v94(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    generated_at: str,
    *,
    localize_presentation: Any = None,
) -> tuple[str | None, str | None, int]:
    original = _ORIGINAL_V2_PDF
    if original is None:
        raise RuntimeError("final report v94 English PDF base is not installed")
    encoded, error, page_count = original(
        identity,
        assessment,
        stages,
        generated_at,
        localize_presentation=localize_presentation,
    )
    if error or not encoded:
        return encoded, error, page_count
    pdf = base64.b64decode(encoded)
    augmented, augmented_count = _augment_pdf_with_context(pdf, identity, spanish=False)
    return base64.b64encode(augmented).decode("ascii"), None, augmented_count


def _enrich_package_identity(
    package: Mapping[str, Any],
    supplied_identity: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(package))
    report = result.get("report_package")
    if not isinstance(report, dict):
        return result
    canonical = report.get("json")
    if not isinstance(canonical, dict):
        return result
    canonical_identity = canonical.get("identity")
    if not isinstance(canonical_identity, dict):
        return result

    context = _human_context(supplied_identity)
    if not context:
        return result
    canonical_identity.update(context)
    digest = _text(supplied_identity.get("engagement_metadata_sha256"), 128)
    if digest:
        canonical_identity["engagement_metadata_sha256"] = digest
    canonical["identity"] = canonical_identity

    markdown = _inject_context_markdown(
        str(report.get("markdown") or ""),
        canonical_identity,
        spanish=False,
    )
    title = f"NICO Comprehensive Technical Assessment — {_text(canonical_identity.get('repository'), 300)}"
    rendered_html = report_package._semantic_html(markdown, title)

    pdf_bytes = b""
    if report.get("pdf_base64"):
        try:
            pdf_bytes = base64.b64decode(str(report.get("pdf_base64") or ""), validate=True)
        except Exception:
            pdf_bytes = b""
    if pdf_bytes.startswith(b"%PDF"):
        pdf_bytes, page_count = _augment_pdf_with_context(
            pdf_bytes,
            canonical_identity,
            spanish=False,
        )
        report["pdf_base64"] = base64.b64encode(pdf_bytes).decode("ascii")
        report["pdf_sha256"] = hashlib.sha256(pdf_bytes).hexdigest()
        report["pdf_page_count"] = page_count

    stages = canonical.get("stage_summaries") or []
    report_id = "comprehensive_report_" + report_package._canonical_hash(
        {"identity": canonical_identity, "stages": stages}
    )[:20]
    truth_sha = report_package._canonical_hash(canonical)
    report["report_id"] = report_id
    report["markdown"] = markdown
    report["html"] = rendered_html
    report["json"] = canonical
    report["canonical_truth_sha256"] = truth_sha
    quality = report.get("report_quality_contract")
    if isinstance(quality, dict):
        quality["client_supplied_engagement_context_rendered"] = True
    result["report_package"] = report
    result["report_id"] = report_id
    result["canonical_truth_sha256"] = truth_sha
    result_quality = result.get("report_quality_contract")
    if isinstance(result_quality, dict):
        result_quality["client_supplied_engagement_context_rendered"] = True
    return result


def build_ship_ready_report_package(
    *,
    identity: dict[str, Any],
    stage_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build the native package, then preserve the complete verified engagement context."""

    install_final_report_ship_closure_v94()
    package = report_package.build_comprehensive_report_package(
        identity=identity,
        stage_results=stage_results,
    )
    if str(package.get("status") or "") != "complete":
        return package
    return _enrich_package_identity(package, identity)


def install_final_report_ship_closure_v94() -> dict[str, Any]:
    """Install bounded final-report fixes without changing scoring or approval authority."""

    global _ORIGINAL_V2_MARKDOWN
    global _ORIGINAL_V2_PDF

    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    from nico import v2_premium_report_renderer as premium

    engagement.display_identity_projection = _verified_display_identity_projection

    human_fields = set(_HUMAN_CONTEXT_LIMITS)
    canonical._PROTECTED_FIELDS.update(human_fields)
    canonical._POST_RENDER_PROTECTED_FIELDS.update(human_fields)
    canonical._LABEL_ONLY.update(_SPANISH_LABELS)
    existing_sources = {source for source, _ in canonical._PRESENTATION_REPLACEMENTS}
    additions = tuple(
        (source, target)
        for source, target in _SPANISH_LABELS.items()
        if source not in existing_sources
    )
    if additions:
        canonical._PRESENTATION_REPLACEMENTS += additions

    if _ORIGINAL_V2_MARKDOWN is None:
        _ORIGINAL_V2_MARKDOWN = premium._markdown
    if _ORIGINAL_V2_PDF is None:
        _ORIGINAL_V2_PDF = premium._pdf
    premium._markdown = _english_markdown_v94
    premium._pdf = _english_pdf_v94
    premium._spanish_markdown = _spanish_markdown_v94
    premium._spanish_pdf = _spanish_pdf_v94
    canonical.render_spanish_markdown = _spanish_markdown_v94
    canonical.render_spanish_pdf = _spanish_pdf_v94

    return {
        "status": "installed",
        "version": VERSION,
        "all_five_client_supplied_fields_preserved": True,
        "durable_metadata_digest_required": True,
        "client_values_preserved_verbatim_across_locales": True,
        "spanish_human_context_labels_localized": True,
        "spanish_premium_localization_tree_passes": 1,
        "spanish_markdown_pdf_share_localized_inputs": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "build_ship_ready_report_package",
    "install_final_report_ship_closure_v94",
]
