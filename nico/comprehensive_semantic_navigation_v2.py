from __future__ import annotations

import io
import re
from functools import wraps
from typing import Any

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

VERSION = "nico.comprehensive_semantic_navigation.v2"
_MARKER = "__nico_comprehensive_semantic_navigation_v2__"

# Ordered by report semantics, but discovered in physical-page/line order. The
# localized titles below are presentation labels only. Machine identifiers remain
# unchanged and can be used as an additional detection anchor after localization.
_SECTIONS: tuple[dict[str, Any], ...] = (
    {"id": "comprehensive_technical_assessment", "en": "Comprehensive Technical Assessment", "es": "Evaluación Técnica Integral", "aliases": ()},
    {"id": "executive_decision_brief", "en": "Executive Decision Brief", "es": "Resumen ejecutivo para decisiones", "aliases": ()},
    {"id": "priority_constraints", "en": "Priority Constraints and Decision Risks", "es": "Restricciones prioritarias y riesgos de decisión", "aliases": ("Priority Constraints and Risks", "Restricciones prioritarias y riesgos")},
    {"id": "canonical_technical_scorecard", "en": "Canonical Technical Scorecard", "es": "Cuadro de puntuación técnica", "aliases": ("Technical Scorecard",)},
    {"id": "code_audit", "en": "Code audit", "es": "Auditoría de código", "aliases": ("Code Audit",)},
    {"id": "dependency_health", "en": "Dependency / Library Ecosystem", "es": "Ecosistema de dependencias y bibliotecas", "aliases": ()},
    {"id": "secrets_review", "en": "Secrets Exposure Review", "es": "Revisión de exposición de secretos", "aliases": ()},
    {"id": "static_analysis", "en": "Static Analysis", "es": "Análisis estático", "aliases": ()},
    {"id": "ci_cd", "en": "CI/CD Analysis", "es": "Análisis de CI/CD", "aliases": ()},
    {"id": "architecture_debt", "en": "Architecture & Technical Debt", "es": "Arquitectura y deuda técnica", "aliases": ()},
    {"id": "velocity_complexity", "en": "Velocity / Complexity", "es": "Velocidad y complejidad", "aliases": ()},
    {"id": "authorization_and_scope", "en": "Authorization and Scope", "es": "Autorización y alcance", "aliases": ("authorization_and_scope",)},
    {"id": "historical_trends_and_change_failure", "en": "Historical Trends and Change Failure", "es": "Tendencias históricas y fallos de cambio", "aliases": ("historical_trends_and_change_failure",)},
    {"id": "risk_reduction_and_executive_briefing", "en": "Risk Reduction and Executive Briefing", "es": "Reducción de riesgo y resumen ejecutivo", "aliases": ("risk_reduction_and_executive_briefing",)},
    {"id": "architecture_and_data_flow", "en": "Architecture and Data Flow", "es": "Arquitectura y flujo de datos", "aliases": ("architecture_and_data_flow",)},
    {"id": "ci_cd_architecture_complexity_velocity", "en": "CI/CD, Architecture, Complexity, and Velocity", "es": "CI/CD, arquitectura, complejidad y velocidad", "aliases": ("ci_cd_architecture_complexity_velocity",)},
    {"id": "dependency_security_static_analysis", "en": "Dependency, Security, and Static Analysis", "es": "Análisis de dependencias, seguridad y análisis estático", "aliases": ("dependency_security_static_analysis",)},
    {"id": "developer_delivery_process", "en": "Developer Delivery Process", "es": "Proceso de entrega de desarrollo", "aliases": ("developer_delivery_process",)},
    {"id": "review_required_candidate_register", "en": "Review-Required Candidate Register", "es": "Registro de candidatos que requieren revisión", "aliases": ("review_required_candidate_register",)},
    {"id": "ci_cd_operational_readiness", "en": "CI/CD Operational Readiness and Historical Health", "es": "Preparación operativa y salud histórica de CI/CD", "aliases": ("ci_cd_operational_readiness",)},
    {"id": "client_evidence_summary", "en": "Client Evidence Summary", "es": "Resumen de evidencia del cliente", "aliases": ("client_evidence_summary",)},
    {"id": "functional_qa", "en": "Functional QA", "es": "QA funcional", "aliases": ("functional_qa",)},
    {"id": "platform_parity", "en": "Platform Parity", "es": "Paridad de plataformas", "aliases": ("platform_parity",)},
    {"id": "requirements_traceability", "en": "Requirements Traceability", "es": "Trazabilidad de requisitos", "aliases": ("requirements_traceability",)},
    {"id": "stakeholder_and_business_alignment", "en": "Stakeholder and Business Alignment", "es": "Alineación comercial y de partes interesadas", "aliases": ("stakeholder_and_business_alignment",)},
    {"id": "six_month_roadmap", "en": "Six-Month Roadmap", "es": "Hoja de ruta de seis meses", "aliases": ("six_month_roadmap",)},
    {"id": "staffing_sequencing_and_cost", "en": "Staffing, Sequencing, and Cost", "es": "Personal, secuencia y costo", "aliases": ("staffing_sequencing_and_cost",)},
    {"id": "compact_finding_register", "en": "Compact Finding and Remediation Register", "es": "Registro compacto de hallazgos y remediación", "aliases": ()},
    {"id": "complete_exact_source_index", "en": "Complete Exact-Source Index", "es": "Índice completo de fuentes exactas", "aliases": ()},
    {"id": "human_review_acceptance_gate", "en": "Human Review and Acceptance Gate", "es": "Puerta de revisión y aceptación humana", "aliases": ()},
    {"id": "client_artifact_manifest", "en": "Client Artifact Manifest", "es": "Manifiesto de artefactos del cliente", "aliases": ()},
    {"id": "exact_artifact_approval_record", "en": "Human Review and Exact-Artifact Approval Record", "es": "Registro de revisión humana y aprobación del artefacto exacto", "aliases": ()},
)


def _text(value: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _spanish_document(reader: PdfReader) -> bool:
    sample = "\n".join(
        (reader.pages[index].extract_text() or "")
        for index in range(min(8, len(reader.pages)))
    ).casefold()
    return any(
        marker in sample
        for marker in (
            "borrador automatizado",
            "evaluación técnica integral",
            "resumen ejecutivo para decisiones",
            "cuadro de puntuación técnica",
            "aprobación humana pendiente",
        )
    )


def _heading_candidate(line: str) -> str:
    candidate = _text(line, 500)
    candidate = re.sub(r"^\s*\d+\.\s*", "", candidate)
    return candidate.strip()


def _visible_heading_match(candidate: str, marker: str) -> bool:
    folded = candidate.casefold()
    target = _text(marker, 500).casefold()
    if not target:
        return False
    if folded == target:
        return True
    return any(
        folded.startswith(target + suffix)
        for suffix in (" ·", " —", " -", ":")
    )


def _section_for_line(line: str, *, spanish: bool) -> tuple[str, str] | None:
    candidate = _heading_candidate(line)
    folded = candidate.casefold()
    if not candidate:
        return None
    for section in _SECTIONS:
        visible = [section["es"] if spanish else section["en"], section["en"], section["es"], *section["aliases"]]
        if any(_visible_heading_match(candidate, marker) for marker in visible if marker):
            return str(section["id"]), str(section["es"] if spanish else section["en"])
        # Stage IDs are machine evidence and remain stable across locales. Match them
        # only when they appear as a standalone token inside a Stage-ID style line.
        section_id = str(section["id"])
        if section_id in folded and (
            "stage id" in folded
            or "id de etapa" in folded
            or folded == section_id
        ):
            return section_id, str(section["es"] if spanish else section["en"])
    return None


def semantic_entries(reader: PdfReader) -> tuple[list[tuple[str, int]], bool]:
    """Return every first-occurrence semantic section with its final physical page.

    The source PDF has no inserted TOC yet. Final page 1 remains the source cover and
    the new TOC becomes page 2, so every source page after the cover shifts by +1.
    Multiple semantic headings on one compacted source page therefore intentionally
    receive the same final page number.
    """

    spanish = _spanish_document(reader)
    entries: list[tuple[str, int]] = []
    seen: set[str] = set()
    for source_index, page in enumerate(reader.pages):
        if source_index == 0:
            continue
        text = page.extract_text() or ""
        for raw_line in text.splitlines():
            match = _section_for_line(raw_line, spanish=spanish)
            if match is None:
                continue
            section_id, title = match
            if section_id in seen:
                continue
            seen.add(section_id)
            entries.append((title, source_index + 2))
    return entries, spanish


def _fit_title(value: str, *, max_width: float, font_name: str, font_size: float) -> str:
    title = _text(value, 160)
    if stringWidth(title, font_name, font_size) <= max_width:
        return title
    while title and stringWidth(title + "...", font_name, font_size) > max_width:
        title = title[:-1]
    return title.rstrip() + "..."


def _toc_page(entries: list[tuple[str, int]], total_pages: int, *, spanish: bool) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.setTitle("Tabla de contenido de NICO" if spanish else "NICO Table of Contents")
    pdf.setAuthor("NICO")
    pdf.setFillColorRGB(0.06, 0.09, 0.16)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(48, 744, "Tabla de contenido" if spanish else "Table of Contents")
    pdf.setFillColorRGB(0.57, 0.25, 0.04)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawString(
        48,
        722,
        (
            "BORRADOR AUTOMATIZADO | APROBACIÓN HUMANA PENDIENTE | ENTREGA AL CLIENTE BLOQUEADA"
            if spanish
            else "AUTOMATED DRAFT | PENDING HUMAN APPROVAL | CLIENT DELIVERY BLOCKED"
        ),
    )
    pdf.setStrokeColorRGB(0.80, 0.84, 0.89)
    pdf.line(48, 710, 564, 710)
    pdf.setFillColorRGB(0.20, 0.25, 0.33)
    y = 690
    for title, page_number in entries[:32]:
        fitted = _fit_title(title, max_width=445, font_name="Helvetica", font_size=8.2)
        pdf.setFont("Helvetica", 8.2)
        pdf.drawString(54, y, fitted)
        pdf.setFont("Helvetica-Bold", 8.2)
        pdf.drawRightString(558, y, str(page_number))
        y -= 18
    if len(entries) > 32:
        pdf.setFont("Helvetica-Oblique", 7.2)
        pdf.drawString(
            54,
            y,
            (
                "Las entradas adicionales se conservan como marcadores PDF."
                if spanish
                else "Additional navigation entries are retained as PDF bookmarks."
            ),
        )
    pdf.setFont("Helvetica", 7)
    pdf.setFillColorRGB(0.39, 0.45, 0.55)
    pdf.drawString(
        48,
        36,
        (
            "NICO | paquete de revisión técnica basado en evidencia"
            if spanish
            else "NICO | evidence-bound technical review package"
        ),
    )
    pdf.drawRightString(
        564,
        36,
        f"{total_pages} páginas físicas" if spanish else f"{total_pages} physical pages",
    )
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _page_overlay(page_number: int, total_pages: int, *, spanish: bool) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.setFillGray(0.42)
    label = (
        f"Página del documento {page_number} de {total_pages}"
        if spanish
        else f"Document page {page_number} of {total_pages}"
    )
    pdf.drawCentredString(letter[0] / 2, 16, label)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def semantic_renumber_and_outline(pdf_bytes: bytes) -> bytes:
    from nico import comprehensive_manifest_navigation_v1 as navigation

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        raise ValueError("final Comprehensive PDF contains no pages")

    entries, spanish = semantic_entries(reader)
    if not entries:
        # Fail closed to the established navigation path rather than publishing a TOC
        # with no semantic anchors if a future renderer changes every heading contract.
        return navigation._renumber_and_outline(pdf_bytes)

    total = len(reader.pages) + 1
    toc = PdfReader(io.BytesIO(_toc_page(entries, total, spanish=spanish))).pages[0]
    writer = PdfWriter()
    source_pages: list[tuple[Any, bool]] = [(reader.pages[0], True), (toc, False)]
    source_pages.extend((page, True) for page in reader.pages[1:])

    for index, (source, rewrite_labels) in enumerate(source_pages, start=1):
        writer.add_page(source)
        page = writer.pages[-1]
        if rewrite_labels:
            navigation._rewrite_local_page_labels(page, writer)
        overlay = PdfReader(
            io.BytesIO(_page_overlay(index, total, spanish=spanish))
        ).pages[0]
        page.merge_page(overlay, over=True)

    try:
        writer.add_outline_item("Tabla de contenido" if spanish else "Table of Contents", 1)
    except Exception:
        pass

    # Entry page numbers are one-based physical-page numbers after TOC insertion.
    # PdfWriter outline targets are zero-based page indexes.
    for title, page_number in entries:
        try:
            writer.add_outline_item(title, page_number - 1)
        except Exception:
            pass

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def install_comprehensive_semantic_navigation_v2() -> dict[str, Any]:
    from nico import comprehensive_manifest_navigation_v1 as navigation

    current = navigation._renumber_and_outline
    if getattr(current, _MARKER, False):
        return {
            "artifact_schema": VERSION,
            "status": "already_installed",
            "bound": True,
            "multiple_sections_per_page_supported": True,
            "semantic_toc_complete": True,
            "bilingual_toc_and_page_labels": True,
            "canonical_truth_mutated": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def semantic_navigation(pdf_bytes: bytes) -> bytes:
        return semantic_renumber_and_outline(pdf_bytes)

    setattr(semantic_navigation, _MARKER, True)
    setattr(semantic_navigation, "_nico_previous", current)
    navigation._renumber_and_outline = semantic_navigation
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "bound": True,
        "multiple_sections_per_page_supported": True,
        "semantic_toc_complete": True,
        "bilingual_toc_and_page_labels": True,
        "canonical_truth_mutated": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_semantic_navigation_v2",
    "semantic_entries",
    "semantic_renumber_and_outline",
]
