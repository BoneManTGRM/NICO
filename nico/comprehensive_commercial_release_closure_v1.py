from __future__ import annotations

import base64
import hashlib
import io
import math
from collections.abc import Mapping
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_commercial_release_closure.v1"
_BUILD_MARKER = "__nico_commercial_release_display_identity_v1__"
_PDF_MARKER = "__nico_commercial_release_display_pdf_v1__"

_DISPLAY_FIELDS = (
    "customer_name",
    "project_name",
    "primary_technical_contact",
)
_OPTIONAL_IDENTITY_FIELDS = (
    *_DISPLAY_FIELDS,
    "report_language",
    "locale",
)

# Client-visible semantic navigation. The source PDF may place several of these
# headings on one physical page after sparse-page reflow. Navigation therefore
# must be derived from semantic headings, not one title per physical page.
_EN_SEMANTIC_TITLES = (
    "Comprehensive Technical Assessment",
    "Executive Decision Brief",
    "Priority Constraints and Decision Risks",
    "Canonical Technical Scorecard",
    "Code audit",
    "Code Audit",
    "Dependency / Library Ecosystem",
    "Secrets Exposure Review",
    "Static Analysis",
    "CI/CD Analysis",
    "Architecture & Technical Debt",
    "Velocity / Complexity",
    "Authorization and Scope",
    "Historical Trends and Change Failure",
    "Risk Reduction and Executive Briefing",
    "Executive Risk Register and Decision Briefing",
    "Architecture and Data Flow",
    "CI/CD, Architecture, Complexity, and Velocity",
    "Dependency, Security, and Static Analysis",
    "Developer Delivery Process",
    "Review-Required Candidate Register",
    "CI/CD Operational Readiness and Historical Health",
    "Client Evidence Summary",
    "Functional QA",
    "Platform Parity",
    "Stakeholder and Business Alignment",
    "Requirements Traceability",
    "Six-Month Roadmap",
    "Staffing, Sequencing, and Cost",
    "Compact Finding and Remediation Register",
    "Complete Exact-Source Index",
    "Human Review and Acceptance Gate",
    "Client Artifact Manifest",
    "Human Review and Exact-Artifact Approval Record",
)
_ES_SEMANTIC_TITLES = (
    "Evaluación Técnica Integral",
    "Resumen ejecutivo para decisiones",
    "Restricciones prioritarias y riesgos de decisión",
    "Cuadro de puntuación técnica",
    "Auditoría de código",
    "Ecosistema de dependencias y bibliotecas",
    "Revisión de exposición de secretos",
    "Análisis estático",
    "Análisis de CI/CD",
    "Arquitectura y deuda técnica",
    "Velocidad y complejidad",
    "Autorización y alcance",
    "Tendencias históricas y fallos de cambio",
    "Reducción de riesgo y resumen ejecutivo",
    "Arquitectura y flujo de datos",
    "CI/CD, arquitectura, complejidad y velocidad",
    "Dependencias, seguridad y análisis estático",
    "Proceso de entrega de desarrollo",
    "Registro de candidatos que requieren revisión",
    "Preparación operativa y salud histórica de CI/CD",
    "Resumen de evidencia del cliente",
    "QA funcional",
    "Control de calidad funcional",
    "Paridad de plataformas",
    "Alineación comercial y de partes interesadas",
    "Alineación con partes interesadas y negocio",
    "Trazabilidad de requisitos",
    "Hoja de ruta de seis meses",
    "Personal, secuencia y costo",
    "Registro compacto de hallazgos y remediación",
    "Índice completo de fuentes exactas",
    "Puerta de revisión y aceptación humana",
    "Manifiesto de artefactos del cliente",
    "Registro de revisión humana y aprobación del artefacto exacto",
)
_SEMANTIC_TITLES = tuple(dict.fromkeys((*_EN_SEMANTIC_TITLES, *_ES_SEMANTIC_TITLES)))
_TOC_ROWS_PER_PAGE = 39


def _text(value: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _display_identity(identity: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: _text(identity.get(key), 300)
        for key in _OPTIONAL_IDENTITY_FIELDS
        if _text(identity.get(key), 300)
    }


def _rehash_repaired_package(
    result: dict[str, Any],
    report_package: dict[str, Any],
    canonical: dict[str, Any],
) -> None:
    from nico import comprehensive_report_package as report_module

    truth_sha = report_module._canonical_hash(canonical)
    stages = canonical.get("stage_summaries")
    if not isinstance(stages, list):
        stages = result.get("stage_summaries") if isinstance(result.get("stage_summaries"), list) else []
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    report_id = (
        "comprehensive_report_"
        + report_module._canonical_hash({"identity": identity, "stages": stages})[:20]
    )
    report_package["canonical_truth_sha256"] = truth_sha
    report_package["report_id"] = report_id
    result["canonical_truth_sha256"] = truth_sha
    result["report_id"] = report_id


def _repair_report_package_display_identity(
    result: dict[str, Any],
    source_identity: Mapping[str, Any],
) -> dict[str, Any]:
    display = _display_identity(source_identity)
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

    identity = (
        deepcopy(dict(canonical.get("identity") or {}))
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    identity.update(display)
    canonical["identity"] = identity
    report_package["json"] = canonical
    result["report_package"] = report_package
    _rehash_repaired_package(result, report_package, canonical)

    quality = (
        deepcopy(dict(report_package.get("report_quality_contract") or {}))
        if isinstance(report_package.get("report_quality_contract"), Mapping)
        else {}
    )
    quality.update(
        {
            "display_metadata_preserved_in_canonical_report_identity": True,
            "canonical_scope_ids_unchanged": True,
        }
    )
    report_package["report_quality_contract"] = quality
    result["report_quality_contract"] = deepcopy(quality)
    return result


def install_report_display_identity_preservation() -> dict[str, Any]:
    """Preserve report-only display metadata across the canonical package boundary.

    The detached worker already reconstructs client/project/contact values from durable
    retained evidence. The legacy package builder then narrows identity to six scope
    fields. This wrapper retains the reconstructed display fields in canonical report
    truth without changing customer_id/project_id or any assessment/scoring state.
    """

    import nico.comprehensive_report_worker_runtime_v90 as worker

    current = worker.build_comprehensive_report_package
    if getattr(current, _BUILD_MARKER, False):
        return {
            "status": "already_installed",
            "artifact_schema": VERSION,
            "display_identity_preserved": True,
            "canonical_scope_ids_unchanged": True,
        }

    @wraps(current)
    def build_with_display_identity(*args: Any, **kwargs: Any) -> dict[str, Any]:
        source_identity = kwargs.get("identity")
        if not isinstance(source_identity, Mapping) and args:
            source_identity = args[0] if isinstance(args[0], Mapping) else {}
        source_identity = source_identity if isinstance(source_identity, Mapping) else {}
        result = current(*args, **kwargs)
        if not isinstance(result, dict):
            return result
        return _repair_report_package_display_identity(result, source_identity)

    setattr(build_with_display_identity, _BUILD_MARKER, True)
    setattr(build_with_display_identity, "_nico_previous", current)
    worker.build_comprehensive_report_package = build_with_display_identity
    return {
        "status": "installed",
        "artifact_schema": VERSION,
        "display_identity_preserved": True,
        "canonical_scope_ids_unchanged": True,
    }


def install_display_identity_pdf_projection() -> dict[str, Any]:
    """Use display names in the human-facing identity table only.

    The canonical scope identifiers remain unchanged in JSON and persistence. The base
    PDF renderer labels its third identity row Customer/Project but historically fed
    customer_id/project_id into that row. Present the explicitly supplied display names
    there when available, while leaving the canonical input mapping untouched.
    """

    from nico import comprehensive_report_package as package

    current = package._pdf
    if getattr(current, _PDF_MARKER, False):
        return {
            "status": "already_installed",
            "artifact_schema": VERSION,
            "pdf_display_identity_projected": True,
        }

    @wraps(current)
    def pdf_with_display_identity(
        identity: dict[str, Any],
        assessment: dict[str, Any],
        stages: list[dict[str, Any]],
        generated_at: str,
        *args: Any,
        **kwargs: Any,
    ):
        rendered_identity = dict(identity or {})
        customer_name = _text(rendered_identity.get("customer_name"), 180)
        project_name = _text(rendered_identity.get("project_name"), 180)
        if customer_name:
            rendered_identity["customer_id"] = customer_name
        if project_name:
            rendered_identity["project_id"] = project_name
        return current(
            rendered_identity,
            assessment,
            stages,
            generated_at,
            *args,
            **kwargs,
        )

    setattr(pdf_with_display_identity, _PDF_MARKER, True)
    setattr(pdf_with_display_identity, "_nico_previous", current)
    package._pdf = pdf_with_display_identity

    # These modules import _pdf by value. Rebind only the presentation alias; canonical
    # identity and scope IDs are not modified.
    try:
        import nico.v2_premium_report_renderer as renderer

        renderer._pdf = pdf_with_display_identity
    except Exception:
        pass
    try:
        import nico.comprehensive_spanish_canonical_report_v87 as spanish

        spanish._pdf = pdf_with_display_identity
    except Exception:
        pass

    return {
        "status": "installed",
        "artifact_schema": VERSION,
        "pdf_display_identity_projected": True,
        "canonical_scope_ids_unchanged": True,
    }


def _line_semantic_title(line: str) -> str:
    normalized = _text(line, 180)
    if not normalized:
        return ""
    folded = normalized.casefold()
    for title in _SEMANTIC_TITLES:
        target = title.casefold()
        if folded == target:
            return title
        if folded.startswith(target + " ·") or folded.startswith(target + " |"):
            return title
    return ""


def _semantic_titles_for_page(text: str, fallback: Callable[[str], str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in str(text or "").splitlines():
        title = _line_semantic_title(raw)
        if not title:
            continue
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(title)

    primary = _text(fallback(text), 120)
    if primary and primary != "Report page" and primary.casefold() not in seen:
        # Keep legacy navigation for specialized pages that are not part of the semantic
        # catalog (for example integrity sheets), without allowing it to suppress the
        # known second/third headings on compacted pages.
        output.insert(0, primary)
    return output


def _semantic_entries(reader: Any, fallback: Callable[[str], str]) -> list[tuple[str, int]]:
    entries: list[tuple[str, int]] = []
    used: set[str] = set()
    for original_index, page in enumerate(reader.pages[1:], start=1):
        text = page.extract_text() or ""
        for title in _semantic_titles_for_page(text, fallback):
            key = title.casefold()
            if key in used:
                continue
            used.add(key)
            entries.append((title, original_index))
    return entries


def _fit_title(value: str, *, max_width: float, font_name: str, font_size: float) -> str:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    title = _text(value, 140)
    if stringWidth(title, font_name, font_size) <= max_width:
        return title
    while title and stringWidth(title + "...", font_name, font_size) > max_width:
        title = title[:-1]
    return title.rstrip() + "..."


def _toc_pdf(
    entries: list[tuple[str, int]],
    *,
    total_pages: int,
    toc_page_count: int,
    spanish: bool,
) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.setTitle("NICO Table of Contents")
    pdf.setAuthor("NICO")

    chunks = [
        entries[index : index + _TOC_ROWS_PER_PAGE]
        for index in range(0, len(entries), _TOC_ROWS_PER_PAGE)
    ] or [[]]
    for chunk_index, chunk in enumerate(chunks, start=1):
        pdf.setFillColorRGB(0.06, 0.09, 0.16)
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(48, 744, "Tabla de contenido" if spanish else "Table of Contents")
        pdf.setFillColorRGB(0.57, 0.25, 0.04)
        pdf.setFont("Helvetica-Bold", 7)
        boundary = (
            "BORRADOR AUTOMATIZADO | APROBACIÓN HUMANA PENDIENTE | ENTREGA AL CLIENTE BLOQUEADA"
            if spanish
            else "AUTOMATED DRAFT | PENDING HUMAN APPROVAL | CLIENT DELIVERY BLOCKED"
        )
        pdf.drawString(48, 722, boundary)
        pdf.setStrokeColorRGB(0.80, 0.84, 0.89)
        pdf.line(48, 710, 564, 710)
        pdf.setFillColorRGB(0.20, 0.25, 0.33)
        y = 690
        for title, original_index in chunk:
            final_page_number = original_index + toc_page_count + 1
            fitted = _fit_title(
                title,
                max_width=445,
                font_name="Helvetica",
                font_size=7.7,
            )
            pdf.setFont("Helvetica", 7.7)
            pdf.drawString(54, y, fitted)
            pdf.setFont("Helvetica-Bold", 7.7)
            pdf.drawRightString(558, y, str(final_page_number))
            y -= 15.8
        pdf.setFont("Helvetica", 7)
        pdf.setFillColorRGB(0.39, 0.45, 0.55)
        pdf.drawString(
            48,
            36,
            "NICO | paquete de revisión técnica basado en evidencia"
            if spanish
            else "NICO | evidence-bound technical review package",
        )
        footer = (
            f"{total_pages} páginas físicas"
            if spanish
            else f"{total_pages} physical pages"
        )
        if toc_page_count > 1:
            footer += (
                f" | contenido {chunk_index}/{toc_page_count}"
                if spanish
                else f" | TOC {chunk_index}/{toc_page_count}"
            )
        pdf.drawRightString(564, 36, footer)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def semantic_renumber_and_outline(pdf_bytes: bytes) -> bytes:
    """Rebuild physical labels, TOC and bookmarks from semantic headings.

    Unlike the legacy navigation pass, this function records every recognized
    substantive heading on a page. Multiple sections are therefore allowed to point to
    the same physical page after compaction.
    """

    from pypdf import PdfReader, PdfWriter
    from nico import comprehensive_manifest_navigation_v1 as navigation

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        raise ValueError("final Comprehensive PDF contains no pages")

    entries = _semantic_entries(reader, navigation._outline_title)
    source_text = "\n".join(page.extract_text() or "" for page in reader.pages[:8])
    spanish = (
        "BORRADOR AUTOMATIZADO" in source_text.upper()
        or any(title in _ES_SEMANTIC_TITLES for title, _ in entries)
    )
    toc_page_count = max(1, math.ceil(len(entries) / _TOC_ROWS_PER_PAGE))
    total_pages = len(reader.pages) + toc_page_count
    toc_reader = PdfReader(
        io.BytesIO(
            _toc_pdf(
                entries,
                total_pages=total_pages,
                toc_page_count=toc_page_count,
                spanish=spanish,
            )
        )
    )
    if len(toc_reader.pages) != toc_page_count:
        raise ValueError("semantic TOC page-count contract failed")

    writer = PdfWriter()
    source_pages: list[tuple[Any, bool]] = [(reader.pages[0], True)]
    source_pages.extend((page, False) for page in toc_reader.pages)
    source_pages.extend((page, True) for page in reader.pages[1:])

    for index, (source, rewrite_labels) in enumerate(source_pages, start=1):
        writer.add_page(source)
        page = writer.pages[-1]
        if rewrite_labels:
            navigation._rewrite_local_page_labels(page, writer)
        overlay = PdfReader(
            io.BytesIO(navigation._page_overlay(index, total_pages))
        ).pages[0]
        page.merge_page(overlay, over=True)

    for toc_index in range(toc_page_count):
        try:
            if spanish:
                title = "Tabla de contenido" if toc_index == 0 else f"Tabla de contenido {toc_index + 1}"
            else:
                title = "Table of Contents" if toc_index == 0 else f"Table of Contents {toc_index + 1}"
            writer.add_outline_item(title, 1 + toc_index)
        except Exception:
            pass

    for title, original_index in entries:
        final_zero_based = original_index + toc_page_count
        try:
            writer.add_outline_item(title, final_zero_based)
        except Exception:
            pass

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def install_comprehensive_commercial_release_closure_v1() -> dict[str, Any]:
    identity = install_report_display_identity_preservation()
    pdf = install_display_identity_pdf_projection()
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "report_identity": identity,
        "pdf_identity_projection": pdf,
        "semantic_multi_heading_navigation": True,
        "toc_supports_shared_physical_pages": True,
        "canonical_scope_ids_unchanged": True,
        "scores_findings_review_and_delivery_authority_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_commercial_release_closure_v1",
    "install_display_identity_pdf_projection",
    "install_report_display_identity_preservation",
    "semantic_renumber_and_outline",
]
