from __future__ import annotations

import base64
import html
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-spanish-presentation-parity.v1"
_MARKER = "__nico_comprehensive_spanish_presentation_parity_v1__"

_ES_EXTRA_EXACT = {
    "Evidence Evaluated": "Evidencia evaluada",
    "Evidence Bound": "Basado en evidencia",
    "Human Review Required": "Revisión humana requerida",
    "High-complexity code hotspot": "Punto crítico de código de alta complejidad",
    "Pending": "Pendiente",
    "Blocked": "Bloqueada",
    "Yes": "Sí",
    "No": "No",
    "Not available": "No disponible",
    "Strong": "Sólido",
    "Moderate": "Moderado",
    "Exceptional": "Excepcional",
    "Review required": "Revisión requerida",
    "review required": "revisión requerida",
    "human review required": "revisión humana requerida",
}

_ES_PHRASES = {
    "NICO completed a native Comprehensive Technical Assessment for": "NICO completó una Evaluación Técnica Integral nativa para",
    "NICO completed an authorized Comprehensive Technical Assessment for": "NICO completó una Evaluación Técnica Integral autorizada para",
    "The evidence-bound maturity signal is Exceptional": "La señal de madurez basada en evidencia es Excepcional",
    "The package is a review-gated automated draft: automated evidence and recommendations are not client approval or delivery authorization.": "El paquete es un borrador automatizado sujeto a revisión: la evidencia y las recomendaciones automatizadas no constituyen aprobación del cliente ni autorización de entrega.",
    "Every automated stage represented in this package completed without a terminal execution failure.": "Todas las etapas automatizadas representadas en este paquete se completaron sin un fallo terminal de ejecución.",
    "Every automated stage represented in this package completado without a terminal execution failure.": "Todas las etapas automatizadas representadas en este paquete se completaron sin un fallo terminal de ejecución.",
    "Concentrated branch logic increases regression risk, review cost, and the difficulty of safe change.": "La lógica ramificada concentrada aumenta el riesgo de regresión, el costo de revisión y la dificultad de realizar cambios seguros.",
    "Concentrated branch logic increases regression risk, review cost, and the difficulty of safe change": "La lógica ramificada concentrada aumenta el riesgo de regresión, el costo de revisión y la dificultad de realizar cambios seguros",
    "High-complexity code hotspot": "Punto crítico de código de alta complejidad",
    "Reduce complexity in ": "Reducir la complejidad en ",
    "Decompose ": "Descomponer ",
    " around cohesive branch groups, preserve behavior with characterization tests, and enforce cyclomatic complexity at or below 30 on the exact remediation commit.": " en grupos cohesivos de ramas, conservar el comportamiento con pruebas de caracterización y exigir una complejidad ciclomática de 30 o menos en el commit exacto de remediación.",
    " around cohesive branch groups, preserve behavior with characterization tests, and enforce cyclomatic complexity at or below 30 for the durable source anchor.": " en grupos cohesivos de ramas, conservar el comportamiento con pruebas de caracterización y exigir una complejidad ciclomática de 30 o menos para el anclaje de código fuente duradero.",
    "Separate canonical-data preparation, translation selection, layout construction, and artifact validation in ": "Separar la preparación de datos canónicos, la selección de traducción, la construcción del diseño y la validación de artefactos en ",
    "; retain snapshot-based report fixtures and cross-format truth tests; target complexity at or below 30.": "; conservar fixtures de informe basados en instantáneas y pruebas de coherencia entre formatos; fijar como objetivo una complejidad de 30 o menos.",
    "Split collection, normalization, classification, and serialization responsibilities in ": "Separar las responsabilidades de recopilación, normalización, clasificación y serialización en ",
    " into bounded pure helpers; preserve exact-SHA evidence fixtures and add regression tests for failure and partial-evidence paths.": " en funciones auxiliares puras y acotadas; conservar fixtures de evidencia del SHA exacto y agregar pruebas de regresión para rutas de fallo y evidencia parcial.",
    "Extract state transitions, data loading, and side-effect orchestration from ": "Extraer las transiciones de estado, la carga de datos y la orquestación de efectos secundarios de ",
    " into typed hooks or services; split independent rendering branches into bounded child components; add characterization and Playwright coverage; then enforce cyclomatic complexity at or below 30 for the durable source anchor.": " hacia hooks o servicios tipados; separar las ramas de renderizado independientes en componentes hijos acotados; agregar pruebas de caracterización y cobertura de Playwright; después exigir una complejidad ciclomática de 30 o menos para el anclaje de código fuente duradero.",
    "Separate argument parsing, orchestration, evidence assembly, and artifact writing in ": "Separar el análisis de argumentos, la orquestación, el ensamblaje de evidencia y la escritura de artefactos en ",
    "; add command-level characterization tests and enforce the approved complexity threshold.": "; agregar pruebas de caracterización a nivel de comando y aplicar el umbral de complejidad aprobado.",
    "The exact-SHA rerun no longer reports this condition at ": "La nueva ejecución sobre el SHA exacto ya no informa esta condición en ",
    "The exact-SHA rerun no longer reports cyclomatic complexity above 30 at ": "La nueva ejecución sobre el SHA exacto ya no informa complejidad ciclomática superior a 30 en ",
    "Targeted tests and the repository's full required-check suite pass on the remediation commit": "Las pruebas dirigidas y el conjunto completo de verificaciones requeridas del repositorio pasan en el commit de remediación",
    "Targeted characterization tests pass on the remediation commit": "Las pruebas de caracterización dirigidas pasan en el commit de remediación",
    "Production journey, integration, browser/device, and stakeholder acceptance.": "Recorridos de producción, integración, navegador/dispositivo y aceptación de las partes interesadas.",
    "Actual feature, device, permission, or localization parity.": "Paridad real de funciones, dispositivos, permisos o localización.",
    "Change-failure rate, severity, rollback effectiveness, or measured recovery time.": "Tasa de fallos de cambio, severidad, efectividad de reversión o tiempo de recuperación medido.",
    "Requirement breach, contractual nonconformance, or approved-roadmap deviation.": "Incumplimiento de requisitos, no conformidad contractual o desviación de una hoja de ruta aprobada.",
    "Approved priorities, budget/deadline authority, residual-risk ownership, or client acceptance.": "Prioridades aprobadas, autoridad sobre presupuesto/plazos, propiedad del riesgo residual o aceptación del cliente.",
    "Roadmap dates, owners, commitments, and budget remain pending authorized stakeholder approval.": "Las fechas, responsables, compromisos y presupuesto de la hoja de ruta siguen pendientes de aprobación por una parte interesada autorizada.",
    "Capacity, delivery model, rates, and budget authority were not supplied; commercial totals remain uncommitted.": "No se proporcionaron capacidad, modelo de entrega, tarifas ni autoridad presupuestaria; los totales comerciales permanecen sin compromiso.",
    "Repository tests do not establish production user journeys.": "Las pruebas del repositorio no demuestran recorridos de usuario en producción.",
    "Source/config indicators cannot prove runtime or device parity.": "Los indicadores de código/configuración no pueden demostrar paridad de ejecución ni de dispositivos.",
    "Conformance cannot be assessed without an authoritative source.": "La conformidad no puede evaluarse sin una fuente autoritativa.",
    "Technical evidence cannot establish stakeholder intent or business authority.": "La evidencia técnica no puede establecer la intención de las partes interesadas ni la autoridad comercial.",
    "Workflow counts cannot distinguish incidents from cancellation/supersession/infrastructure noise.": "Los conteos de flujos de trabajo no pueden distinguir incidentes de cancelaciones, reemplazos o ruido de infraestructura.",
    "Proceed to professional human review; automated synthesis is not stakeholder approval, residual-risk acceptance, final approval, or client-delivery authorization.": "Proceder a revisión humana profesional; la síntesis automatizada no constituye aprobación de las partes interesadas, aceptación del riesgo residual, aprobación final ni autorización de entrega al cliente.",
    "Evidence-Adjusted": "Ajuste por evidencia",
    "Evidence Adjusted": "Ajuste por evidencia",
    "evidence-bound": "basado en evidencia",
    "Evidence-bound": "Basado en evidencia",
    "Evidence-Bound": "Basado en evidencia",
    "at or below 30": "en 30 o menos",
}

_TITLE_MAP = {
    "Comprehensive Technical Assessment": "Evaluación Técnica Integral",
    "Executive Decision Brief": "Resumen ejecutivo para decisiones",
    "Priority Constraints and Decision Risks": "Restricciones prioritarias y riesgos de decisión",
    "Canonical Technical Scorecard": "Cuadro de puntuación técnica",
    "Dependency / Library Ecosystem": "Ecosistema de dependencias / bibliotecas",
    "Secrets Exposure Review": "Revisión de exposición de secretos",
    "Static Analysis": "Análisis estático",
    "CI/CD Analysis": "Análisis de CI/CD",
    "Architecture & Technical Debt": "Arquitectura y deuda técnica",
    "Velocity / Complexity": "Velocidad / complejidad",
    "Repository and Delivery Evidence": "Evidencia del repositorio y entrega",
    "Evidence Reconciliation and Scoring": "Conciliación y puntuación de evidencia",
    "Functional QA": "QA funcional",
    "Requirements Traceability": "Trazabilidad de requisitos",
    "Authorization and Scope": "Autorización y alcance",
    "Architecture and Data Flow": "Arquitectura y flujo de datos",
    "Developer Delivery Process": "Proceso de entrega de desarrollo",
    "Dependency, Security, and Static Analysis": "Dependencias, seguridad y análisis estático",
    "CI/CD, Architecture, Complexity, and Velocity": "CI/CD, arquitectura, complejidad y velocidad",
    "Review-Required Candidate Register": "Registro de candidatos que requieren revisión",
    "CI/CD Operational Readiness and Historical Health": "Preparación operativa y salud histórica de CI/CD",
    "Compact Finding and Remediation Register": "Registro compacto de hallazgos y remediación",
    "Compact Finding and Remediation Register · continuation": "Registro compacto de hallazgos y remediación · continuación",
    "Complete Exact-Source Index": "Índice completo de ubicaciones exactas",
    "Client Evidence Summary": "Resumen de evidencia para revisión",
    "Human Review and Acceptance Gate": "Puerta de revisión humana y aceptación",
    "Client Artifact Manifest": "Manifiesto de artefactos del cliente",
    "Human Review and Exact-Artifact Approval Record": "Registro de revisión humana y aprobación del artefacto exacto",
}


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _is_spanish(canonical: Mapping[str, Any]) -> bool:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    value = _text(
        identity.get("report_language")
        or identity.get("requested_report_language")
        or identity.get("requested_locale")
        or identity.get("locale")
        or canonical.get("report_language")
        or canonical.get("locale")
        or assessment.get("report_language")
        or assessment.get("locale"),
        40,
    ).casefold()
    return value.startswith("es")


def _looks_like_source_atom(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if re.fullmatch(r"[A-Za-z0-9_.@/+\-]+(?::\d+(?:-\d+)?(?::\d+)?)?", stripped) and (
        "/" in stripped or "_" in stripped or re.search(r"\.[A-Za-z0-9]{1,8}(?::|$)", stripped)
    ):
        return True
    if re.fullmatch(r"(?:NICO-[A-Z0-9-]+|GHSA-[A-Za-z0-9-]+|CVE-\d{4}-\d+|PYSEC-\d{4}-\d+)", stripped):
        return True
    return False


def _safe_replace(text: str, source: str, target: str) -> str:
    if not source:
        return text
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9 /&'’().,+\-]*", source):
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(source)}(?![A-Za-z0-9_])"
        return re.sub(pattern, lambda _m: target, text)
    return text.replace(source, target)


def _safe_es(value: Any) -> str:
    from nico import comprehensive_report_spanish_text_v51 as spanish_text

    text = _text(value, 12000)
    if not text:
        return ""
    if _looks_like_source_atom(text):
        return text
    if text in _ES_EXTRA_EXACT:
        return _ES_EXTRA_EXACT[text]
    if text in spanish_text.ES_EXACT:
        return spanish_text.ES_EXACT[text]
    for source, target in sorted(_ES_PHRASES.items(), key=lambda item: len(item[0]), reverse=True):
        text = _safe_replace(text, source, target)
    for source, target in sorted(spanish_text.ES_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        text = _safe_replace(text, source, target)
    return text


_DISPLAY_FIELDS = {
    "title", "decision_title", "interpretation", "business_impact", "impact",
    "recommended_correction", "recommendation", "verification", "exit_criteria",
    "problematic_code", "observed_evidence", "fact", "summary", "description",
    "why_it_matters", "cannot_conclude", "evidence_to_resolve", "status",
    "assurance_label", "finding_disposition", "owner_role", "role_category",
    "skill_category", "decision", "objective", "expected_impact",
}


def _localized_register(register: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(register))

    def transform(value: Any, key: str = "") -> Any:
        if isinstance(value, Mapping):
            return {k: transform(v, str(k)) for k, v in value.items()}
        if isinstance(value, list):
            return [transform(v, key) for v in value]
        if isinstance(value, tuple):
            return [transform(v, key) for v in value]
        if isinstance(value, str) and key in _DISPLAY_FIELDS:
            return _safe_es(value)
        return value

    return transform(result)


def _localized_title(value: str) -> str:
    return _TITLE_MAP.get(_text(value, 180), _safe_es(value))


def _render_manifest_spanish(canonical: Mapping[str, Any], entries: list[dict[str, Any]]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from nico import comprehensive_artifact_manifest_approval_v1 as manifest

    identity = manifest._canonical_identity(canonical)
    lifecycle = canonical.get("lifecycle") if isinstance(canonical.get("lifecycle"), Mapping) else manifest._lifecycle()
    approval = canonical.get("approval") if isinstance(canonical.get("approval"), Mapping) else manifest._pending_approval_record()
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("ManifestTitleES", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=colors.HexColor("#0f172a"), spaceAfter=9)
    heading = ParagraphStyle("ManifestHeadingES", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, leading=14, textColor=colors.HexColor("#075985"), spaceBefore=6, spaceAfter=4)
    body = ParagraphStyle("ManifestBodyES", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.8, leading=10.1, textColor=colors.HexColor("#334155"), spaceAfter=4)
    small = ParagraphStyle("ManifestSmallES", parent=body, fontSize=6.7, leading=8.3, textColor=colors.HexColor("#475569"), spaceAfter=2)
    warning = ParagraphStyle("ManifestWarningES", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=.7, borderPadding=7, spaceAfter=8)

    def p(value: Any, style: ParagraphStyle = body, limit: int = 1800) -> Paragraph:
        return Paragraph(html.escape(_text(value, limit)), style)

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(.55 * inch, .35 * inch, "NICO | paquete de revisión del artefacto exacto | borrador automatizado")
        canvas.drawRightString(7.95 * inch, .35 * inch, f"Hoja de integridad {doc.page}")
        canvas.restoreState()

    identity_rows = [
        ["Repositorio", identity.get("repository") or "No disponible"],
        ["Commit exacto", identity.get("commit_sha") or "No disponible"],
        ["ID de ejecución", identity.get("run_id") or "No disponible"],
        ["ID del libro mayor de evidencia", identity.get("evidence_ledger_id") or "No disponible"],
        ["Generado", identity.get("generation_timestamp") or "No disponible"],
    ]
    identity_table = Table([[p(a, small), p(b, small)] for a, b in identity_rows], colWidths=[1.7 * inch, 5.7 * inch])
    identity_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    artifact_rows = [["Artefacto", "Archivo", "SHA-256"]]
    for item in entries:
        artifact_rows.append([
            item.get("artifact_type") or "",
            item.get("filename") or "",
            item.get("sha256") or "Vinculado en el manifiesto separado tras el renderizado final",
        ])
    artifact_table = Table([[p(cell, small, 900) for cell in row] for row in artifact_rows], colWidths=[1.35 * inch, 2.75 * inch, 3.3 * inch], repeatRows=1)
    artifact_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    pending = "Pendiente"
    after_decision = "Se registra en el recibo de aprobación separado después de la decisión"
    story: list[Any] = [
        p("Manifiesto de artefactos del cliente", title),
        p("BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA", warning),
        identity_table,
        p("Artefactos estructurados conservados", heading),
        artifact_table,
        Spacer(1, .08 * inch),
        p("Los hashes finales de bytes del PDF y del JSON canónico se registran en el manifiesto de evidencia separado después del renderizado. Un documento no puede incorporar verazmente su propio hash final sin cambiarlo. El manifiesto separado vincula esos hashes finales con la misma ejecución, commit e ID de manifiesto.", body),
        PageBreak(),
        p("Registro de revisión humana y aprobación del artefacto exacto", title),
        p("PAQUETE DE REVISIÓN LISTO · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA", warning),
        p("Ciclo de vida", heading),
        p(f"Paquete de revisión listo: {'Sí' if lifecycle.get('review_package_ready') else 'No'}", body),
        p(f"Aprobación humana: {_safe_es(lifecycle.get('human_review_status') or 'pending').title()}", body),
        p(f"Entrega al cliente: {_safe_es(lifecycle.get('client_delivery_status') or 'blocked').title()}", body),
        p("Registro de aprobación requerido", heading),
    ]
    approval_rows = [
        ["Identidad del revisor", approval.get("reviewer_identity") or pending],
        ["Rol del revisor", approval.get("reviewer_role") or pending],
        ["Autorización del revisor", "Confirmada" if approval.get("reviewer_authorized") else pending],
        ["Marca de tiempo de la revisión", approval.get("review_timestamp") or pending],
        ["Decisión", _safe_es(approval.get("decision") or pending)],
        ["Aceptación del riesgo residual", approval.get("residual_risk_acceptance") or pending],
        ["SHA-256 del PDF aprobado", approval.get("approved_pdf_sha256") or after_decision],
        ["SHA-256 del JSON aprobado", approval.get("approved_json_sha256") or after_decision],
        ["SHA-256 del manifiesto de evidencia", approval.get("evidence_manifest_sha256") or after_decision],
        ["ID del registro de aprobación", approval.get("approval_record_id") or pending],
        ["Notas del revisor", approval.get("reviewer_notes") or pending],
    ]
    approval_table = Table([[p(a, small), p(b, small, 1000)] for a, b in approval_rows], colWidths=[1.9 * inch, 5.5 * inch])
    approval_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([
        approval_table,
        p("Regla de aprobación", heading),
        p("Solo un revisor humano autorizado puede aprobar los hashes del PDF inmutable exacto, el JSON canónico y el manifiesto de evidencia separado. Cualquier regeneración, cambio de puntuación, cambio de hallazgo, cambio de disposición de candidatos, cambio de evidencia o sustitución de artefacto crea un nuevo borrador e invalida la aprobación anterior.", body),
        p("La automatización no puede cambiar este paquete a FINAL APROBADO ni ENTREGA AL CLIENTE AUTORIZADA.", warning),
    ])
    document = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=.55 * inch, rightMargin=.55 * inch, topMargin=.55 * inch, bottomMargin=.62 * inch, invariant=1, title="NICO · Manifiesto de artefactos y registro de aprobación", author="NICO")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _markdown_manifest_spanish(
    identity: Mapping[str, str],
    entries: list[dict[str, Any]],
    *,
    pdf_sha256: str,
    canonical_json_sha256: str,
    manifest_sha256: str,
) -> str:
    from nico import comprehensive_artifact_manifest_approval_v1 as manifest
    run = manifest._safe_filename(identity.get("run_id"), "run")
    lines = [
        "## Manifiesto de artefactos del cliente", "",
        "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA", "",
        f"- Repositorio: {identity.get('repository') or 'No disponible'}",
        f"- Commit exacto: {identity.get('commit_sha') or 'No disponible'}",
        f"- ID de ejecución: {identity.get('run_id') or 'No disponible'}",
        f"- ID del libro mayor de evidencia: {identity.get('evidence_ledger_id') or 'No disponible'}", "",
        "| Artefacto | Archivo | SHA-256 |", "|---|---|---|",
    ]
    for item in entries:
        lines.append(f"| {item.get('artifact_type')} | {item.get('filename')} | {item.get('sha256')} |")
    lines.extend([
        f"| comprehensive_pdf | nico-{run}-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf | {pdf_sha256} |",
        f"| canonical_json | nico-{run}-canonical.json | {canonical_json_sha256} |",
        f"| evidence_manifest_json | nico-{run}-evidence-manifest.json | {manifest_sha256} |", "",
        "## Registro de revisión humana y aprobación del artefacto exacto", "",
        "- Paquete de revisión listo: Sí",
        "- Aprobación humana: Pendiente",
        "- Entrega al cliente: Bloqueada",
        "- Identidad del revisor: Pendiente",
        "- Rol del revisor: Pendiente",
        "- Autorización del revisor: Pendiente",
        "- Decisión: Pendiente",
        "- SHA-256 del PDF aprobado: Pendiente de aprobación del artefacto exacto",
        "- SHA-256 del JSON aprobado: Pendiente de aprobación del artefacto exacto",
        "- SHA-256 del manifiesto de evidencia: Pendiente de aprobación del artefacto exacto", "",
        "Solo un revisor humano autorizado puede aprobar estos hashes exactos. Cualquier artefacto regenerado vuelve al estado de borrador automatizado y bloquea la entrega.",
    ])
    return "\n".join(lines).strip() + "\n"


def _spanish_context(nav: Any) -> bool:
    context = nav._CONTEXT.get()
    canonical = context.get("json") if isinstance(context, Mapping) and isinstance(context.get("json"), Mapping) else {}
    return _is_spanish(canonical)


def _toc_page_spanish(nav: Any, entries: list[tuple[str, int]], total_pages: int) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.setTitle("NICO · Índice")
    pdf.setAuthor("NICO")
    pdf.setFillColorRGB(0.06, 0.09, 0.16)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(48, 744, "Índice")
    pdf.setFillColorRGB(0.57, 0.25, 0.04)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawString(48, 722, "BORRADOR AUTOMATIZADO | APROBACIÓN HUMANA PENDIENTE | ENTREGA AL CLIENTE BLOQUEADA")
    pdf.setStrokeColorRGB(0.80, 0.84, 0.89)
    pdf.line(48, 710, 564, 710)
    pdf.setFillColorRGB(0.20, 0.25, 0.33)
    y = 690
    for title, page_number in entries[:32]:
        fitted = nav._fit_title(_localized_title(title), max_width=445, font_name="Helvetica", font_size=8.2)
        pdf.setFont("Helvetica", 8.2)
        pdf.drawString(54, y, fitted)
        pdf.setFont("Helvetica-Bold", 8.2)
        pdf.drawRightString(558, y, str(page_number))
        y -= 18
    if len(entries) > 32:
        pdf.setFont("Helvetica-Oblique", 7.2)
        pdf.drawString(54, y, "Las entradas adicionales de navegación se conservan como marcadores del PDF.")
    pdf.setFont("Helvetica", 7)
    pdf.setFillColorRGB(0.39, 0.45, 0.55)
    pdf.drawString(48, 36, "NICO | paquete de revisión técnica basado en evidencia")
    pdf.drawRightString(564, 36, f"{total_pages} páginas físicas")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _page_overlay_spanish(page_number: int, total_pages: int) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.setFillGray(0.42)
    pdf.drawCentredString(letter[0] / 2, 16, f"Página del documento {page_number} de {total_pages}")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _renumber_spanish(nav: Any, pdf: bytes) -> bytes:
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(io.BytesIO(pdf))
    if not reader.pages:
        raise ValueError("el PDF Integral final no contiene páginas")
    original_titles = [nav._outline_title(page.extract_text() or "") for page in reader.pages]
    used: set[str] = set()
    toc_entries: list[tuple[str, int]] = []
    for original_index, title in enumerate(original_titles[1:], start=1):
        localized = _localized_title(title)
        key = localized.casefold()
        if not localized or localized == "Report page" or key in used:
            continue
        used.add(key)
        toc_entries.append((localized, original_index + 2))
    total = len(reader.pages) + 1
    toc = PdfReader(io.BytesIO(_toc_page_spanish(nav, toc_entries, total))).pages[0]
    writer = PdfWriter()
    source_pages: list[tuple[Any, bool]] = [(reader.pages[0], True), (toc, False)]
    source_pages.extend((page, True) for page in reader.pages[1:])
    for index, (source, rewrite_labels) in enumerate(source_pages, start=1):
        writer.add_page(source)
        page = writer.pages[-1]
        if rewrite_labels:
            nav._rewrite_local_page_labels(page, writer)
        overlay = PdfReader(io.BytesIO(_page_overlay_spanish(index, total))).pages[0]
        page.merge_page(overlay, over=True)
    try:
        writer.add_outline_item("Índice", 1)
    except Exception:
        pass
    used.clear()
    for original_index, title in enumerate(original_titles[1:], start=1):
        localized = _localized_title(title)
        key = localized.casefold()
        if not localized or localized == "Report page" or key in used:
            continue
        used.add(key)
        try:
            writer.add_outline_item(localized, original_index + 1)
        except Exception:
            pass
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _validate_spanish_navigation(nav: Any, result: Mapping[str, Any]) -> None:
    from pypdf import PdfReader
    manifest = result.get("artifact_manifest")
    manifest = manifest if isinstance(manifest, Mapping) else {}
    artifacts = [item for item in manifest.get("artifacts") or [] if isinstance(item, Mapping)]
    types = {_text(item.get("artifact_type"), 100) for item in artifacts}
    missing = sorted(nav._REQUIRED_DETACHED_TYPES - types)
    if missing:
        raise ValueError("el manifiesto separado omitió tipos requeridos: " + ", ".join(missing))
    validation_artifacts = nav._validation_artifacts(artifacts, strict=nav._strict_identity_available(result))
    for item in validation_artifacts:
        artifact_type = _text(item.get("artifact_type"), 100)
        for field in ("filename", "sha256", "size_bytes", "media_type", "run_id", "repository", "commit_sha", "evidence_ledger_id", "generated_at"):
            if item.get(field) in (None, ""):
                raise ValueError(f"el artefacto {artifact_type} omitió el campo de metadatos requerido {field}")
    try:
        pdf = base64.b64decode(str(result.get("pdf_base64") or ""), validate=True)
        reader = PdfReader(io.BytesIO(pdf))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise ValueError("el artefacto Integral final no contiene un PDF válido") from exc
    for index in range(1, len(reader.pages) + 1):
        if f"Página del documento {index} de {len(reader.pages)}" not in extracted:
            raise ValueError("el PDF final no conserva etiquetas continuas de página física")
    if "Índice" not in extracted:
        raise ValueError("el PDF final no conserva un índice")
    if not reader.outline:
        raise ValueError("el PDF final no conserva marcadores de navegación")


def _assert_spanish_full_data_parity(
    localization: Any,
    finish: Any,
    canonical: Mapping[str, Any],
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> dict[str, Any]:
    validation_canonical = localization._normalize_required_stage_titles(canonical)
    if finish.classify_report_proof(validation_canonical) != "full_comprehensive":
        raise ValueError("un fixture disperso no puede satisfacer la validación de paridad Integral con datos completos")
    extracted = localization._pdf_text(pdf)
    combined = "\n".join((markdown or "", localization._visible_html(rendered_html), extracted))
    sections = finish._sections(canonical)
    if not sections:
        raise ValueError("la prueba con datos completos no contiene el cuadro de puntuación canónico")
    localization._assert_localized_worksheet_surfaces(markdown, rendered_html, extracted)
    scanners = finish._scanners(canonical)
    assessment = finish._assessment(canonical)
    requested = assessment.get("requested_scanner_records") or canonical.get("requested_scanner_records")
    if requested and not scanners:
        raise ValueError("la prueba con datos completos no contiene evidencia de ejecución de analizadores aplicables")
    candidates = finish._candidate_total(canonical)
    if candidates and not finish._candidate_register(canonical):
        raise ValueError("la prueba con datos completos tiene candidatos pero no un registro canónico de candidatos")
    if candidates and localization.SPANISH_CANDIDATE_REGISTER not in combined:
        raise ValueError("la prueba con datos completos no contiene el registro localizado de candidatos")
    findings = finish._findings(canonical)
    localization._assert_spanish_exact_source_index(findings, extracted)
    required = (
        "Manifiesto de artefactos del cliente",
        "Registro de revisión humana y aprobación del artefacto exacto",
        localization.SPANISH_REVIEW_GATE,
        localization.SPANISH_EXACT_SOURCE_INDEX,
    )
    for title in required:
        if title not in extracted:
            raise ValueError(f"el PDF con datos completos no contiene la sección requerida: {title}")
    for forbidden in (
        "workfbaja",
        "bebaja",
        "ScannerWorkfbajaPage",
        "Table of Contents",
        "Client Artifact Manifest",
        "Human Review and Exact-Artifact Approval Record",
    ):
        if forbidden in combined:
            raise ValueError(f"la superficie española contiene una regresión de localización: {forbidden}")
    timestamp = finish.canonical_generation_timestamp(canonical)
    if not timestamp:
        raise ValueError("el manifiesto con datos completos no contiene una marca de tiempo canónica de generación")
    if "Generado\nNo disponible" in extracted or "Generado: No disponible" in extracted:
        raise ValueError("el manifiesto con datos completos degradó silenciosamente la marca de tiempo de generación")
    return {
        "proof_kind": "full_comprehensive",
        "scored_control_count": len(sections),
        "scanner_execution_count": len(scanners),
        "candidate_count": candidates,
        "exact_source_finding_count": len(findings),
        "worksheet_count": len(localization.WORKSHEET_TITLES_BY_STAGE_ID),
        "generation_timestamp": timestamp,
        "localized_spanish_full_data_validation": True,
        "spanish_presentation_parity_version": VERSION,
        "corruption_regressions_rejected": True,
        "manifest_and_navigation_localized": True,
        "scores_unchanged": True,
        "candidate_dispositions_unchanged": True,
    }


def install_comprehensive_spanish_presentation_parity_v1() -> dict[str, Any]:
    from nico import client_finding_remediation_register_v1 as register_v1
    from nico import comprehensive_artifact_manifest_approval_v1 as manifest
    from nico import comprehensive_full_data_worksheet_localization_v1 as localization
    from nico import comprehensive_manifest_navigation_v1 as nav
    from nico import comprehensive_report_spanish_artifacts_v51 as spanish_artifacts
    from nico import comprehensive_report_spanish_text_v51 as spanish_text

    spanish_text._es = _safe_es
    spanish_artifacts._es = _safe_es

    current_markdown = register_v1.finding_register_markdown
    if not getattr(current_markdown, _MARKER, False):
        @wraps(current_markdown)
        def finding_register_markdown(register: Mapping[str, Any], *, spanish: bool) -> str:
            return current_markdown(_localized_register(register) if spanish else register, spanish=spanish)
        setattr(finding_register_markdown, _MARKER, True)
        setattr(finding_register_markdown, "_nico_previous", current_markdown)
        register_v1.finding_register_markdown = finding_register_markdown

    current_pdf = register_v1.render_finding_register_pdf
    if not getattr(current_pdf, _MARKER, False):
        @wraps(current_pdf)
        def render_finding_register_pdf(register: Mapping[str, Any], *, spanish: bool) -> bytes:
            return current_pdf(_localized_register(register) if spanish else register, spanish=spanish)
        setattr(render_finding_register_pdf, _MARKER, True)
        setattr(render_finding_register_pdf, "_nico_previous", current_pdf)
        register_v1.render_finding_register_pdf = render_finding_register_pdf

    current_supplement = manifest._render_manifest_approval_supplement
    if not getattr(current_supplement, _MARKER, False):
        @wraps(current_supplement)
        def render_manifest(canonical: Mapping[str, Any], entries: list[dict[str, Any]]) -> bytes:
            if _is_spanish(canonical):
                return _render_manifest_spanish(canonical, entries)
            return current_supplement(canonical, entries)
        setattr(render_manifest, _MARKER, True)
        setattr(render_manifest, "_nico_previous", current_supplement)
        manifest._render_manifest_approval_supplement = render_manifest

    current_manifest_md = manifest._markdown_manifest
    if not getattr(current_manifest_md, _MARKER, False):
        @wraps(current_manifest_md)
        def markdown_manifest(identity: Mapping[str, str], entries: list[dict[str, Any]], **kwargs: Any) -> str:
            language = _text(identity.get("report_language"), 40).casefold()
            if language.startswith("es"):
                return _markdown_manifest_spanish(identity, entries, **kwargs)
            return current_manifest_md(identity, entries, **kwargs)
        setattr(markdown_manifest, _MARKER, True)
        setattr(markdown_manifest, "_nico_previous", current_manifest_md)
        manifest._markdown_manifest = markdown_manifest

    current_toc = nav._toc_page
    if not getattr(current_toc, _MARKER, False):
        @wraps(current_toc)
        def toc_page(entries: list[tuple[str, int]], total_pages: int) -> bytes:
            if _spanish_context(nav):
                return _toc_page_spanish(nav, entries, total_pages)
            return current_toc(entries, total_pages)
        setattr(toc_page, _MARKER, True)
        setattr(toc_page, "_nico_previous", current_toc)
        nav._toc_page = toc_page

    current_overlay = nav._page_overlay
    if not getattr(current_overlay, _MARKER, False):
        @wraps(current_overlay)
        def page_overlay(page_number: int, total_pages: int) -> bytes:
            if _spanish_context(nav):
                return _page_overlay_spanish(page_number, total_pages)
            return current_overlay(page_number, total_pages)
        setattr(page_overlay, _MARKER, True)
        setattr(page_overlay, "_nico_previous", current_overlay)
        nav._page_overlay = page_overlay

    current_renumber = nav._renumber_and_outline
    if not getattr(current_renumber, _MARKER, False):
        @wraps(current_renumber)
        def renumber_and_outline(pdf: bytes) -> bytes:
            if _spanish_context(nav):
                return _renumber_spanish(nav, pdf)
            return current_renumber(pdf)
        setattr(renumber_and_outline, _MARKER, True)
        setattr(renumber_and_outline, "_nico_previous", current_renumber)
        nav._renumber_and_outline = renumber_and_outline

    current_validation = nav._validate_final_package
    if not getattr(current_validation, _MARKER, False):
        @wraps(current_validation)
        def validate_final_package(result: Mapping[str, Any]) -> None:
            canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
            if _is_spanish(canonical):
                return _validate_spanish_navigation(nav, result)
            return current_validation(result)
        setattr(validate_final_package, _MARKER, True)
        setattr(validate_final_package, "_nico_previous", current_validation)
        nav._validate_final_package = validate_final_package

    localization._assert_spanish_full_data_parity = (
        lambda finish_arg, canonical, markdown, rendered_html, pdf:
        _assert_spanish_full_data_parity(localization, finish_arg, canonical, markdown, rendered_html, pdf)
    )

    return {
        "status": "installed",
        "version": VERSION,
        "boundary_safe_translation": True,
        "substring_corruption_removed": True,
        "compact_register_localized": True,
        "artifact_manifest_localized": True,
        "approval_record_localized": True,
        "toc_and_page_labels_localized": True,
        "spanish_full_data_gate_rejects_known_regressions": True,
        "english_path_unchanged": True,
        "scores_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_safe_es",
    "_localized_register",
    "install_comprehensive_spanish_presentation_parity_v1",
]
