from __future__ import annotations

import html
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Mapping

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ByteStringObject,
    ContentStream,
    TextStringObject,
    encode_pdfdocencoding,
)

from nico.comprehensive_report_language_truth_v77 import resolve_report_language

VERSION = "nico.comprehensive-spanish-client-surface-localization.v85"
_MARKER = "__nico_comprehensive_spanish_client_surface_localization_v85__"
_DIGEST_INDEPENDENT_MANIFEST_MARKER = (
    "__nico_digest_independent_artifact_manifest_guide_v1__"
)

ES_BOUNDARY = (
    "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · "
    "ENTREGA AL CLIENTE BLOQUEADA"
)
EN_BOUNDARY = "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"
SPANISH_MANIFEST_TITLE = "Manifiesto de artefactos del cliente"
SPANISH_APPROVAL_TITLE = (
    "Registro de revisión humana y aprobación de artefactos exactos"
)

# Only NICO-owned presentation copy belongs here. Source code, paths, identifiers,
# filenames, hashes, scanner output, raw diagnostics, and retained evidence are not
# passed through a general-purpose translator.
_PRESENTATION_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED", ES_BOUNDARY),
    ("DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED", ES_BOUNDARY),
    ("DRAFT · HUMAN REVIEW REQUIRED", ES_BOUNDARY),
    ("DRAFT — HUMAN REVIEW REQUIRED", ES_BOUNDARY),
    (EN_BOUNDARY, ES_BOUNDARY),
    ("Client Artifact Manifest", SPANISH_MANIFEST_TITLE),
    ("Retained structured artifacts", "Artefactos estructurados preservados"),
    ("Human Review and Exact-Artifact Approval Record", SPANISH_APPROVAL_TITLE),
    ("Review package ready", "Paquete de revisión listo"),
    ("Human approval", "Aprobación humana"),
    ("Client delivery", "Entrega al cliente"),
    ("Reviewer identity", "Identidad del revisor"),
    ("Reviewer role", "Rol del revisor"),
    ("Reviewer authorization", "Autorización del revisor"),
    ("Review timestamp", "Fecha y hora de revisión"),
    ("Residual-risk acceptance", "Aceptación del riesgo residual"),
    ("Approval record ID", "ID del registro de aprobación"),
    ("Reviewer notes", "Notas del revisor"),
    ("Required approval record", "Registro de aprobación requerido"),
    ("Approval rule", "Regla de aprobación"),
    ("NICO | exact-artifact review package | automated draft", "NICO | paquete de revisión de artefactos exactos | borrador automatizado"),
    ("NICO | Comprehensive client review | automated draft", "NICO | revisión integral del cliente | borrador automatizado"),
    ("NICO · compact finding register · automated draft", "NICO · registro compacto de hallazgos · borrador automatizado"),
    ("Finding ID", "ID de hallazgo"),
    ("Exact source", "Fuente exacta"),
    ("Finding / disposition", "Hallazgo / disposición"),
    ("Human disposition required", "Se requiere disposición humana"),
    ("review required", "se requiere revisión"),
    ("requires review", "requiere revisión"),
    ("NOT SCORED", "SIN PUNTUACIÓN"),
    ("Confirmed material", "Material confirmado"),
    ("Review required", "Revisión requerida"),
    ("Score effect", "Efecto en la puntuación"),
    ("Assurance-only until triaged", "Solo afecta al aseguramiento hasta su revisión"),
    ("Category", "Categoría"),
    ("Raw", "Sin procesar"),
    ("Bound in detached manifest after final rendering", "Vinculado en el manifiesto separado después del renderizado final"),
    ("Not available", "No disponible"),
    ("Pending exact-artifact approval", "Pendiente de aprobación del artefacto exacto"),
    ("Recorded in detached approval receipt after decision", "Se registra en el recibo de aprobación separado después de la decisión"),
    ("The package is an automated draft pending human approval", "El paquete es un borrador automatizado pendiente de aprobación humana"),
    ("The report is an automated draft pending human approval.", "El informe es un borrador automatizado pendiente de aprobación humana."),
    ("The automated assessment is complete and pending human approval.", "La evaluación automatizada está completa y pendiente de aprobación humana."),
    ("Reduce complexity in ", "Reducir la complejidad en "),
    ("Concentrated branch logic increases regression risk, review cost, and the difficulty of safe change.", "La lógica de ramas concentrada aumenta el riesgo de regresión, el costo de revisión y la dificultad de realizar cambios seguros."),
    ("Decompose the function around cohesive branch groups while preserving behavior and add focused regression coverage.", "Descomponer la función por grupos de ramas cohesivos, conservar el comportamiento y añadir cobertura de regresión específica."),
    ("Workflow outcomes are operational context only and do not change immutable CI configuration maturity.", "Los resultados de los flujos de trabajo son solo contexto operativo y no cambian la madurez inmutable de la configuración de CI."),
)

_EN_STATUS_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED", EN_BOUNDARY),
    ("DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED", EN_BOUNDARY),
    ("DRAFT · HUMAN REVIEW REQUIRED", EN_BOUNDARY),
    ("DRAFT — HUMAN REVIEW REQUIRED", EN_BOUNDARY),
)

_LITERAL_MARKDOWN_RE = re.compile(
    r"(?ms)(^```[^\n]*\n.*?^```\s*$|^~~~[^\n]*\n.*?^~~~\s*$)"
)
_INLINE_LITERAL_RE = re.compile(r"(`[^`\n]+`|<!--.*?-->)", re.S)


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _is_spanish(canonical: Mapping[str, Any]) -> bool:
    return resolve_report_language(canonical) == "es-MX"


def _localize_presentation_text(value: str) -> str:
    output = str(value or "")
    for old, new in _PRESENTATION_REPLACEMENTS:
        output = output.replace(old, new)

    output = re.sub(
        r"\bDecision findings:\s*(\d+)",
        r"Hallazgos de decisión: \1",
        output,
    )
    output = re.sub(
        r"\bExact-source findings:\s*(\d+)",
        r"Hallazgos con ubicación exacta: \1",
        output,
    )
    output = re.sub(
        r"\bConfirmed material scanner findings:\s*(\d+)",
        r"Hallazgos materiales confirmados por analizadores: \1",
        output,
    )
    output = re.sub(
        r"\bReview-required scanner candidates:\s*(\d+)",
        r"Candidatos de analizadores que requieren revisión: \1",
        output,
    )
    output = re.sub(
        r"\bObserved workflow runs:\s*(\d+)",
        r"Ejecuciones observadas de flujos de trabajo: \1",
        output,
    )
    output = output.replace("Outcome taxonomy:", "Taxonomía de resultados:")
    output = re.sub(
        r"Review page (\d+) of (\d+) \| Sections (\d+)-(\d+) of (\d+)",
        r"Página de revisión \1 de \2 | Secciones \3-\4 de \5",
        output,
    )
    output = re.sub(
        r"Section (\d+) of (\d+) \| Page (\d+) of (\d+)",
        r"Sección \1 de \2 | Página \3 de \4",
        output,
    )
    output = re.sub(r"\bRegister (\d+)\b", r"Registro \1", output)
    output = re.sub(r"\bIntegrity (\d+)\b", r"Integridad \1", output)
    # Review, register, gate, and workload pages are appended after the canonical
    # report renderer. Reuse its presentation vocabulary so late Spanish-only
    # surfaces cannot drift back to partial English copy.
    from nico.comprehensive_spanish_canonical_report_v87 import (
        _translate_presentation,
    )

    output = _translate_presentation(output)
    return output


def localize_spanish_markdown(markdown: str) -> str:
    """Translate known NICO presentation copy while preserving code literals."""

    parts = _LITERAL_MARKDOWN_RE.split(str(markdown or ""))
    localized: list[str] = []
    for part in parts:
        stripped = part.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            localized.append(part)
            continue

        # This is renderer-owned placeholder copy, not a client code literal.
        part = part.replace("`the identified unit`", "`la unidad identificada`")

        placeholders: dict[str, str] = {}

        def protect(match: re.Match[str]) -> str:
            token = f"\x00NICO_LITERAL_{len(placeholders)}\x00"
            placeholders[token] = match.group(0)
            return token

        protected = _INLINE_LITERAL_RE.sub(protect, part)
        protected = _localize_presentation_text(protected)
        for token, literal in placeholders.items():
            protected = protected.replace(token, literal)
        localized.append(protected)
    output = "".join(localized)
    return re.sub(
        r"(?m)(^## Estado de entrega[ \t]*\n\*\*.*ENTREGA AL CLIENTE BLOQUEADA)(\*\*)$",
        r"\1 — ENTREGA AL CLIENTE NO AUTORIZADA\2",
        output,
        count=1,
    )


def _localize_review_sections(value: Any) -> Any:
    if isinstance(value, list):
        return [_localize_review_sections(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_localize_review_sections(item) for item in value)
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            # Exact source, code, raw evidence, hashes, and machine identifiers are
            # immutable evidence. Only renderer-owned prose fields are localized.
            if key in {
                "path",
                "location",
                "exact_source",
                "source_path",
                "problematic_code",
                "code",
                "raw_output",
                "raw_payload",
                "sha256",
                "commit_sha",
                "run_id",
                "finding_id",
                "candidate_id",
                "rule_id",
                "scanner_name",
                "tool",
                "filename",
                "url",
            }:
                output[str(key)] = deepcopy(item)
            else:
                output[str(key)] = _localize_review_sections(item)
        return output
    if isinstance(value, str):
        return _localize_presentation_text(value)
    return deepcopy(value)


def _translate_pdf_operand(value: Any, translator: Callable[[str], str]) -> tuple[Any, bool]:
    if isinstance(value, TextStringObject):
        original = str(value)
        translated = translator(original)
        return TextStringObject(translated), translated != original
    if isinstance(value, ByteStringObject):
        original = bytes(value)
        for encoding in ("utf-8", "latin-1"):
            try:
                decoded = original.decode(encoding)
            except UnicodeDecodeError:
                continue
            translated = translator(decoded)
            if translated == decoded:
                return value, False
            # A changed byte operand may now contain Spanish characters. Encode
            # them with PDFDocEncoding; UTF-8 bytes render as mojibake in the
            # source Type-1 font, while UTF-16 text strings introduce NUL glyphs.
            try:
                return ByteStringObject(encode_pdfdocencoding(translated)), True
            except UnicodeEncodeError:
                return ByteStringObject(translated.encode("cp1252", errors="replace")), True
    return value, False


def _transform_pdf_text(pdf: bytes, translator: Callable[[str], str]) -> bytes:
    if not pdf.startswith(b"%PDF"):
        raise ValueError("Spanish client localization requires a valid PDF")
    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    for source_page in reader.pages:
        writer.add_page(source_page)
        page = writer.pages[-1]
        contents = page.get_contents()
        if contents is None:
            continue
        stream = ContentStream(contents, writer)
        changed = False
        for operands, operator in stream.operations:
            if operator == b"Tj" and operands:
                operands[0], operand_changed = _translate_pdf_operand(
                    operands[0], translator
                )
                changed = changed or operand_changed
            elif operator == b"TJ" and operands:
                for index, item in enumerate(operands[0]):
                    operands[0][index], operand_changed = _translate_pdf_operand(
                        item, translator
                    )
                    changed = changed or operand_changed
            elif operator in {b"'", b'"'} and operands:
                operands[-1], operand_changed = _translate_pdf_operand(
                    operands[-1], translator
                )
                changed = changed or operand_changed
        if changed:
            page.replace_contents(stream)
    if not writer.pages:
        raise ValueError("Spanish client localization removed every PDF page")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def _looks_spanish_pdf(pdf: bytes) -> bool:
    text = _pdf_text(pdf)
    return any(
        marker in text
        for marker in (
            "BORRADOR AUTOMATIZADO",
            "QA funcional",
            "Evaluación Técnica Integral NICO",
            "Registro compacto de hallazgos",
            "Puerta de revisión humana y aceptación",
        )
    )


def _english_status_only(value: str) -> str:
    output = str(value or "")
    for old, new in _EN_STATUS_REPLACEMENTS:
        output = output.replace(old, new)
    return output


def _artifact_label(value: Any) -> str:
    labels = {
        "findings_csv": "Hallazgos (CSV)",
        "evidence_csv": "Evidencia (CSV)",
        "candidate_register_json": "Registro de candidatos (JSON)",
        "remediation_backlog_json": "Trabajo pendiente de remediación (JSON)",
        "comprehensive_pdf": "Informe integral (PDF)",
        "canonical_json": "JSON canónico",
        "evidence_manifest_json": "Manifiesto de evidencia (JSON)",
    }
    raw = _text(value, 180)
    return labels.get(raw, raw)


def _approval_value(value: Any, *, fallback: str = "Pendiente") -> str:
    raw = _text(value, 1200)
    if not raw:
        return fallback
    values = {
        "pending": "Pendiente",
        "blocked": "Bloqueada",
        "ready": "Listo",
        "complete": "Completo",
        "confirmed": "Confirmado",
    }
    return values.get(raw.casefold(), raw)


def _render_spanish_manifest(
    manifest: Any,
    canonical: Mapping[str, Any],
    entries: list[dict[str, Any]],
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    identity = manifest._canonical_identity(canonical)
    lifecycle = (
        canonical.get("lifecycle")
        if isinstance(canonical.get("lifecycle"), Mapping)
        else manifest._lifecycle()
    )
    approval = (
        canonical.get("approval")
        if isinstance(canonical.get("approval"), Mapping)
        else manifest._pending_approval_record()
    )
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ManifestTitleES",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=9,
    )
    heading = ParagraphStyle(
        "ManifestHeadingES",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=14,
        textColor=colors.HexColor("#075985"),
        spaceBefore=6,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "ManifestBodyES",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.8,
        leading=10.1,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )
    small = ParagraphStyle(
        "ManifestSmallES",
        parent=body,
        fontSize=6.7,
        leading=8.3,
        textColor=colors.HexColor("#475569"),
        spaceAfter=2,
    )
    warning = ParagraphStyle(
        "ManifestWarningES",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#92400e"),
        backColor=colors.HexColor("#fef3c7"),
        borderColor=colors.HexColor("#f59e0b"),
        borderWidth=.7,
        borderPadding=7,
        spaceAfter=8,
    )

    def p(value: Any, style: ParagraphStyle = body, limit: int = 1800) -> Paragraph:
        return Paragraph(html.escape(_text(value, limit)), style)

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(
            .55 * inch,
            .35 * inch,
            "NICO | paquete de revisión de artefactos exactos | borrador automatizado",
        )
        canvas.drawRightString(7.95 * inch, .35 * inch, f"Integridad {doc.page}")
        canvas.restoreState()

    unavailable = "No disponible"
    identity_rows = [
        ["Repositorio", identity.get("repository") or unavailable],
        ["Commit exacto", identity.get("commit_sha") or unavailable],
        ["ID de ejecución", identity.get("run_id") or unavailable],
        ["ID del registro de evidencia", identity.get("evidence_ledger_id") or unavailable],
        ["Generado", identity.get("generation_timestamp") or unavailable],
    ]
    identity_table = Table(
        [[p(left, small), p(right, small)] for left, right in identity_rows],
        colWidths=[1.55 * inch, 5.85 * inch],
    )
    identity_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    artifact_rows = [["Artefacto", "Nombre de archivo", "SHA-256"]]
    for item in entries:
        artifact_rows.append(
            [
                _artifact_label(item.get("artifact_type")),
                item.get("filename") or "",
                item.get("sha256")
                or "SHA-256 no disponible — integridad del artefacto no establecida",
            ]
        )
    artifact_table = Table(
        [[p(cell, small, 900) for cell in row] for row in artifact_rows],
        colWidths=[1.55 * inch, 2.65 * inch, 3.2 * inch],
        repeatRows=1,
    )
    artifact_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story: list[Any] = [
        p(SPANISH_MANIFEST_TITLE, title),
        p(ES_BOUNDARY, warning),
        identity_table,
        p("Artefactos estructurados preservados", heading),
        artifact_table,
        Spacer(1, .08 * inch),
        p(
            "Los valores SHA-256 mostrados arriba vinculan artefactos conservados cuyos bytes finales inmutables existían antes de renderizar este PDF. Los hashes finales del PDF y del JSON canónico se registran después del renderizado en el manifiesto de evidencia separado; el hash propio del manifiesto se devuelve fuera de este en la identidad exacta del borrador. Un documento no puede incorporar de forma veraz su propio hash final sin modificarlo.",
            body,
        ),
        PageBreak(),
        p(SPANISH_APPROVAL_TITLE, title),
        p(
            "PAQUETE DE REVISIÓN LISTO · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA",
            warning,
        ),
        p("Ciclo de vida", heading),
        p(
            f"Paquete de revisión listo: {'Sí' if lifecycle.get('review_package_ready') else 'No'}",
            body,
        ),
        p(
            f"Aprobación humana: {_approval_value(lifecycle.get('human_review_status'))}",
            body,
        ),
        p(
            f"Entrega al cliente: {_approval_value(lifecycle.get('client_delivery_status'), fallback='Bloqueada')}",
            body,
        ),
        p("Registro de aprobación requerido", heading),
    ]
    approval_rows = [
        ["Identidad del revisor", approval.get("reviewer_identity") or "Pendiente"],
        ["Rol del revisor", approval.get("reviewer_role") or "Pendiente"],
        [
            "Autorización del revisor",
            "Confirmada" if approval.get("reviewer_authorized") else "Pendiente",
        ],
        ["Fecha y hora de revisión", approval.get("review_timestamp") or "Pendiente"],
        ["Decisión", _approval_value(approval.get("decision"))],
        [
            "Aceptación del riesgo residual",
            approval.get("residual_risk_acceptance") or "Pendiente",
        ],
        [
            "PDF aprobado SHA-256",
            approval.get("approved_pdf_sha256")
            or "Se registra en el recibo de aprobación separado después de la decisión",
        ],
        [
            "JSON aprobado SHA-256",
            approval.get("approved_json_sha256")
            or "Se registra en el recibo de aprobación separado después de la decisión",
        ],
        [
            "Manifiesto de evidencia SHA-256",
            approval.get("evidence_manifest_sha256")
            or "Se registra en el recibo de aprobación separado después de la decisión",
        ],
        ["ID del registro de aprobación", approval.get("approval_record_id") or "Pendiente"],
        ["Notas del revisor", approval.get("reviewer_notes") or "Pendiente"],
    ]
    approval_table = Table(
        [[p(left, small), p(right, small, 1000)] for left, right in approval_rows],
        colWidths=[1.85 * inch, 5.55 * inch],
    )
    approval_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend(
        [
            approval_table,
            p("Regla de aprobación", heading),
            p(
                "Solo un revisor humano autorizado puede aprobar los hashes del PDF inmutable exacto, el JSON canónico y el manifiesto de evidencia separado. Cualquier regeneración, cambio de puntuación, hallazgo, disposición de candidato, evidencia o sustitución de artefacto crea un nuevo borrador e invalida la aprobación anterior.",
                body,
            ),
            p(
                "La automatización no puede cambiar este paquete a FINAL APROBADO ni AUTORIZAR LA ENTREGA AL CLIENTE.",
                warning,
            ),
        ]
    )
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.55 * inch,
        rightMargin=.55 * inch,
        topMargin=.55 * inch,
        bottomMargin=.62 * inch,
        invariant=1,
        title="NICO Manifiesto de artefactos y registro de aprobación",
        author="NICO",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _spanish_markdown_manifest(
    manifest: Any,
    identity: Mapping[str, str],
    entries: list[dict[str, Any]],
    *,
    pdf_sha256: str,
    canonical_json_sha256: str,
    manifest_sha256: str,
) -> str:
    unavailable = "No disponible"
    lines = [
        f"## {SPANISH_MANIFEST_TITLE}",
        "",
        ES_BOUNDARY,
        "",
        f"- Repositorio: {identity.get('repository') or unavailable}",
        f"- Commit exacto: {identity.get('commit_sha') or unavailable}",
        f"- ID de ejecución: {identity.get('run_id') or unavailable}",
        f"- ID del registro de evidencia: {identity.get('evidence_ledger_id') or unavailable}",
        "",
        "| Artefacto | Nombre de archivo | SHA-256 |",
        "|---|---|---|",
    ]
    for item in entries:
        lines.append(
            f"| {_artifact_label(item.get('artifact_type'))} | {item.get('filename')} | {item.get('sha256')} |"
        )
    run = manifest._safe_filename(identity.get("run_id"), "run")
    lines.extend(
        [
            f"| Informe integral (PDF) | nico-{run}-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf | {pdf_sha256} |",
            f"| JSON canónico | nico-{run}-canonical.json | {canonical_json_sha256} |",
            f"| Manifiesto de evidencia (JSON) | nico-{run}-evidence-manifest.json | {manifest_sha256} |",
            "",
            f"## {SPANISH_APPROVAL_TITLE}",
            "",
            "- Paquete de revisión listo: Sí",
            "- Aprobación humana: Pendiente",
            "- Entrega al cliente: Bloqueada",
            "- Identidad del revisor: Pendiente",
            "- Rol del revisor: Pendiente",
            "- Autorización del revisor: Pendiente",
            "- Decisión: Pendiente",
            "- PDF aprobado SHA-256: Pendiente de aprobación del artefacto exacto",
            "- JSON aprobado SHA-256: Pendiente de aprobación del artefacto exacto",
            "- Manifiesto de evidencia SHA-256: Pendiente de aprobación del artefacto exacto",
            "",
            "Solo un revisor humano autorizado puede aprobar estos hashes exactos. Cualquier artefacto regenerado vuelve a Borrador Automatizado y bloquea la entrega.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _assert_spanish_full_data_parity(
    finish: Any,
    localization: Any,
    canonical: Mapping[str, Any],
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> dict[str, Any]:
    validation_canonical = localization._normalize_required_stage_titles(canonical)
    if finish.classify_report_proof(validation_canonical) != "full_comprehensive":
        raise ValueError("sparse fixture cannot satisfy full-data Comprehensive parity validation")

    extracted = _pdf_text(pdf)
    visible_html = html.unescape(re.sub(r"<[^>]+>", "\n", str(rendered_html or "")))
    combined = "\n".join((markdown or "", visible_html, extracted))
    sections = finish._sections(canonical)
    if not sections:
        raise ValueError("full-data proof is missing the canonical scorecard")

    localization._assert_localized_worksheet_surfaces(
        markdown,
        rendered_html,
        extracted,
    )
    scanners = finish._scanners(canonical)
    assessment = finish._assessment(canonical)
    requested = assessment.get("requested_scanner_records") or canonical.get(
        "requested_scanner_records"
    )
    if requested and not scanners:
        raise ValueError("full-data proof is missing applicable scanner execution evidence")

    candidates = finish._candidate_total(canonical)
    if candidates and not finish._candidate_register(canonical):
        raise ValueError("full-data proof has candidates but no canonical candidate register")
    if candidates and localization.SPANISH_CANDIDATE_REGISTER not in combined:
        raise ValueError("full-data proof is missing the localized candidate register section")

    findings = finish._findings(canonical)
    localization._assert_spanish_exact_source_index(findings, extracted)
    for title in (
        SPANISH_MANIFEST_TITLE,
        SPANISH_APPROVAL_TITLE,
        localization.SPANISH_REVIEW_GATE,
        localization.SPANISH_EXACT_SOURCE_INDEX,
    ):
        if title not in extracted:
            raise ValueError(f"full-data PDF is missing required Spanish section: {title}")

    forbidden = (
        "Client Artifact Manifest",
        "Human Review and Exact-Artifact Approval Record",
        "NICO | Comprehensive client review | automated draft",
        "NICO · compact finding register · automated draft",
        "DRAFT · HUMAN REVIEW REQUIRED",
        "DRAFT — HUMAN REVIEW REQUIRED",
    )
    retained = [marker for marker in forbidden if marker in combined]
    if retained:
        raise ValueError(
            "Spanish client package retained English presentation marker(s): "
            + ", ".join(retained)
        )

    timestamp = finish.canonical_generation_timestamp(canonical)
    if not timestamp:
        raise ValueError("full-data manifest is missing a canonical generation timestamp")
    if "Generado\nNo disponible" in extracted or "Generado: No disponible" in extracted:
        raise ValueError("full-data manifest silently degraded the generation timestamp")

    return {
        "proof_kind": "full_comprehensive",
        "scored_control_count": len(sections),
        "scanner_execution_count": len(scanners),
        "candidate_count": candidates,
        "exact_source_finding_count": len(findings),
        "worksheet_count": len(localization.WORKSHEET_TITLES_BY_STAGE_ID),
        "generation_timestamp": timestamp,
        "localized_spanish_full_data_validation": True,
        "spanish_manifest_and_approval_localized": True,
        "english_presentation_markers_absent": True,
        "worksheet_identity_source": "stable_stage_id_or_established_alias",
        "persisted_report_language_authority": True,
    }


def _state(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "version": VERSION,
        "canonical_language_resolver_reused": True,
        "spanish_manifest_and_approval_localized": True,
        "digest_independent_exact_manifest_guide_preserved": True,
        "spanish_review_companion_localized": True,
        "spanish_register_and_review_gate_localized": True,
        "code_and_exact_source_literals_preserved": True,
        "english_stale_review_status_normalized": True,
        "spanish_full_data_truth_gate_updated": True,
        "english_path_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def install_comprehensive_spanish_client_surface_localization_v85() -> dict[str, Any]:
    """Localize final es-MX presentation after every late compatibility installer."""

    from nico import client_pdf_status_sanitizer_v1 as sanitizer
    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_artifact_manifest_approval_v1 as manifest
    from nico import comprehensive_client_ready_projection_v1 as projection
    from nico import comprehensive_client_review_companion_v5 as review_v5
    from nico import comprehensive_client_review_companion_v7 as review_v7
    from nico import comprehensive_full_data_worksheet_localization_v1 as localization
    from nico import comprehensive_full_report_finish_v1 as finish

    if getattr(completion.sanitize_client_pdf_status, _MARKER, False):
        return _state("already_installed")

    current_sections = review_v5.substantive_review_sections

    @wraps(current_sections)
    def substantive_review_sections(
        canonical: Mapping[str, Any],
        *,
        spanish: bool,
    ) -> list[dict[str, Any]]:
        sections = current_sections(canonical, spanish=spanish)
        if not spanish:
            return sections
        return [deepcopy(dict(_localize_review_sections(section))) for section in sections]

    setattr(substantive_review_sections, _MARKER, True)
    review_v5.substantive_review_sections = substantive_review_sections

    current_merge = completion.merge_review_companion_markdown

    @wraps(current_merge)
    def merge_review_companion_markdown(
        markdown: str,
        canonical: Mapping[str, Any],
        *,
        spanish: bool,
    ) -> str:
        rendered = current_merge(markdown, canonical, spanish=spanish)
        return localize_spanish_markdown(rendered) if spanish else _english_status_only(rendered)

    setattr(merge_review_companion_markdown, _MARKER, True)
    completion.merge_review_companion_markdown = merge_review_companion_markdown
    if hasattr(review_v5, "merge_substantive_review_markdown"):
        review_v5.merge_substantive_review_markdown = merge_review_companion_markdown

    current_compact_markdown = completion.compact_client_markdown

    @wraps(current_compact_markdown)
    def compact_client_markdown(
        markdown: str,
        canonical: Mapping[str, Any],
        register: Mapping[str, Any],
        *,
        spanish: bool,
    ) -> str:
        rendered = current_compact_markdown(
            markdown,
            canonical,
            register,
            spanish=spanish,
        )
        return localize_spanish_markdown(rendered) if spanish else _english_status_only(rendered)

    setattr(compact_client_markdown, _MARKER, True)
    completion.compact_client_markdown = compact_client_markdown
    projection.compact_client_markdown = compact_client_markdown

    current_register_pdf = completion.render_compact_finding_register_pdf

    @wraps(current_register_pdf)
    def render_compact_finding_register_pdf(
        register: Mapping[str, Any],
        *,
        spanish: bool,
    ) -> bytes:
        localized_register = (
            _localize_review_sections(register) if spanish else register
        )
        pdf = current_register_pdf(localized_register, spanish=spanish)
        return _transform_pdf_text(pdf, _localize_presentation_text) if spanish else pdf

    setattr(render_compact_finding_register_pdf, _MARKER, True)
    completion.render_compact_finding_register_pdf = render_compact_finding_register_pdf
    projection.render_compact_finding_register_pdf = render_compact_finding_register_pdf

    current_gate_pdf = completion.render_evidence_review_gate_pdf

    @wraps(current_gate_pdf)
    def render_evidence_review_gate_pdf(
        canonical: Mapping[str, Any],
        register: Mapping[str, Any],
        *,
        spanish: bool,
    ) -> bytes:
        source_canonical = _localize_review_sections(canonical) if spanish else canonical
        source_register = _localize_review_sections(register) if spanish else register
        pdf = current_gate_pdf(source_canonical, source_register, spanish=spanish)
        return _transform_pdf_text(pdf, _localize_presentation_text) if spanish else pdf

    setattr(render_evidence_review_gate_pdf, _MARKER, True)
    completion.render_evidence_review_gate_pdf = render_evidence_review_gate_pdf
    projection.render_evidence_review_gate_pdf = render_evidence_review_gate_pdf

    current_review_pdf = completion.render_comprehensive_review_companion_pdf

    @wraps(current_review_pdf)
    def render_comprehensive_review_companion_pdf(
        canonical: Mapping[str, Any],
        *,
        spanish: bool,
    ) -> bytes:
        pdf = current_review_pdf(canonical, spanish=spanish)
        return _transform_pdf_text(pdf, _localize_presentation_text) if spanish else pdf

    setattr(render_comprehensive_review_companion_pdf, _MARKER, True)
    completion.render_comprehensive_review_companion_pdf = (
        render_comprehensive_review_companion_pdf
    )
    review_v7.render_paired_substantive_review_pdf = (
        render_comprehensive_review_companion_pdf
    )

    current_sanitizer = completion.sanitize_client_pdf_status

    @wraps(current_sanitizer)
    def sanitize_client_pdf_status(pdf: bytes) -> bytes:
        cleaned = current_sanitizer(pdf)
        if _looks_spanish_pdf(cleaned):
            return _transform_pdf_text(cleaned, _localize_presentation_text)
        return _transform_pdf_text(cleaned, _english_status_only)

    setattr(sanitize_client_pdf_status, _MARKER, True)
    completion.sanitize_client_pdf_status = sanitize_client_pdf_status
    sanitizer.sanitize_client_pdf_status = sanitize_client_pdf_status

    current_manifest_pdf = manifest._render_manifest_approval_supplement

    @wraps(current_manifest_pdf)
    def render_manifest_approval_supplement(
        canonical: Mapping[str, Any],
        entries: list[dict[str, Any]],
    ) -> bytes:
        if not _is_spanish(canonical):
            return current_manifest_pdf(canonical, entries)
        return _render_spanish_manifest(manifest, canonical, entries)

    setattr(render_manifest_approval_supplement, _MARKER, True)
    manifest._render_manifest_approval_supplement = render_manifest_approval_supplement

    current_manifest_markdown = manifest._markdown_manifest

    @wraps(current_manifest_markdown)
    def markdown_manifest(
        identity: Mapping[str, str],
        entries: list[dict[str, Any]],
        *,
        pdf_sha256: str,
        canonical_json_sha256: str,
        manifest_sha256: str,
    ) -> str:
        language = _text(identity.get("report_language"), 40)
        if not language.casefold().startswith("es"):
            return current_manifest_markdown(
                identity,
                entries,
                pdf_sha256=pdf_sha256,
                canonical_json_sha256=canonical_json_sha256,
                manifest_sha256=manifest_sha256,
            )
        if getattr(current_manifest_markdown, _DIGEST_INDEPENDENT_MANIFEST_MARKER, False):
            # The exact-artifact binder deliberately emits a guide without an
            # artifact hash table. A Markdown artifact cannot contain its own final
            # digest without changing those bytes. Preserve that locale-aware guide
            # instead of replacing it with the older self-referential table.
            return current_manifest_markdown(
                identity,
                entries,
                pdf_sha256=pdf_sha256,
                canonical_json_sha256=canonical_json_sha256,
                manifest_sha256=manifest_sha256,
            )
        return _spanish_markdown_manifest(
            manifest,
            identity,
            entries,
            pdf_sha256=pdf_sha256,
            canonical_json_sha256=canonical_json_sha256,
            manifest_sha256=manifest_sha256,
        )

    setattr(markdown_manifest, _MARKER, True)
    manifest._markdown_manifest = markdown_manifest

    current_full_data = finish.assert_full_data_parity

    @wraps(current_full_data)
    def assert_full_data_parity(
        canonical: Mapping[str, Any],
        markdown: str,
        rendered_html: str,
        pdf: bytes,
    ) -> dict[str, Any]:
        if not _is_spanish(canonical):
            return current_full_data(canonical, markdown, rendered_html, pdf)
        return _assert_spanish_full_data_parity(
            finish,
            localization,
            canonical,
            markdown,
            rendered_html,
            pdf,
        )

    setattr(assert_full_data_parity, _MARKER, True)
    setattr(assert_full_data_parity, "_nico_previous", current_full_data)
    finish.assert_full_data_parity = assert_full_data_parity

    # A code-safe localization probe must remain true at startup. This prevents a
    # future broad replacement from silently translating client source literals.
    probe = (
        "## Client Artifact Manifest\n\n"
        "```python\nprint('Client Artifact Manifest')\n```\n\n"
        "Inline `Client Artifact Manifest` literal."
    )
    localized_probe = localize_spanish_markdown(probe)
    if SPANISH_MANIFEST_TITLE not in localized_probe:
        raise RuntimeError("Spanish presentation localization did not translate its heading")
    if "print('Client Artifact Manifest')" not in localized_probe:
        raise RuntimeError("Spanish presentation localization altered fenced code")
    if "`Client Artifact Manifest`" not in localized_probe:
        raise RuntimeError("Spanish presentation localization altered inline code")

    return _state("installed")


__all__ = [
    "EN_BOUNDARY",
    "ES_BOUNDARY",
    "SPANISH_APPROVAL_TITLE",
    "SPANISH_MANIFEST_TITLE",
    "VERSION",
    "install_comprehensive_spanish_client_surface_localization_v85",
    "localize_spanish_markdown",
]
