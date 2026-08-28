from __future__ import annotations

import base64
import html
import io
import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

from pypdf import PdfReader, PdfWriter

VERSION = "nico.comprehensive-client-ready-projection.v1"
REPORT_FINALITY = "automated_draft"
APPROVAL_STATUS = "pending_human_approval"
DELIVERY_STATUS = "blocked_pending_human_approval"
APPROVAL_SUFFIX = "AUTOMATED-DRAFT-PENDING-APPROVAL"
EN_BOUNDARY = "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"
ES_BOUNDARY = "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA"
MAX_EXECUTIVE_FINDINGS = 7
MAX_CLIENT_PDF_PAGES = 60

_REGISTER_HEADINGS = (
    "## Detailed Canonical Findings",
    "## Hallazgos canónicos detallados",
    "## Finding and Remediation Register",
    "## Registro de hallazgos y remediación",
)
_REMOVE_H2_HEADINGS = (
    "## Evidence Appendix",
    "## Apéndice de evidencia",
    "## Analyzer Applicability and Provenance",
    "## Procedencia y aplicabilidad de analizadores",
    "## Human Review and Acceptance Gate",
    "## Puerta de revisión humana y aceptación",
    "## Puerta de revisión y entrega",
)
_PROVENANCE_PAGE_MARKERS = (
    "analyzer applicability and provenance",
    "scanner provenance",
    "procedencia y aplicabilidad de analizadores",
    "procedencia de analizadores",
)
_REVIEW_PAGE_MARKERS = (
    "human review and acceptance gate",
    "puerta de revision humana y aceptacion",
    "puerta de revision y entrega",
)
_REGISTER_PAGE_MARKERS = (
    "finding and remediation register",
    "registro de hallazgos y remediacion",
    "operational and context findings",
)
_EVIDENCE_PAGE_MARKERS = (
    "evidence appendix",
    "apendice de evidencia",
)


def _text(value: Any, limit: int = 8000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    try:
        return max(0, int(str(value or "0").strip()))
    except (TypeError, ValueError):
        return 0


def _dedupe(values: Iterable[Any], limit: int | None = None) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _text(raw)
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        output.append(value)
        if limit is not None and len(output) >= limit:
            break
    return output


def clean_identifier(value: Any) -> str:
    text = _text(value, 500)
    if text.casefold() in {"<arrow>", "arrow", "anonymous arrow"}:
        return "anonymous callback"
    text = re.sub(r"\s*_\s*", "_", text)
    if "_" in text and " " in text and not text.lower().startswith("reduce complexity in "):
        text = text.replace(" ", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_finding_title(value: Any) -> str:
    title = _text(value, 700)
    match = re.match(r"(?i)^(reduce complexity in)\s+(.+)$", title)
    if match:
        return f"{match.group(1)} {clean_identifier(match.group(2))}"
    return title.replace("<arrow>", "anonymous callback")


def _authored_display(
    value: Any,
    key: str,
    *,
    spanish: bool,
    limit: int,
) -> str:
    rendered = _text(value, limit)
    if not spanish or not rendered:
        return rendered
    from nico.comprehensive_spanish_canonical_report_v87 import (
        _translate_presentation_field,
    )

    return _translate_presentation_field(rendered, key)


def _records(register: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for surface in ("code_findings", "operational_findings"):
        for raw in register.get(surface) or []:
            if not isinstance(raw, Mapping):
                continue
            item = deepcopy(dict(raw))
            item["title"] = clean_finding_title(item.get("title") or item.get("decision_title"))
            item["symbol"] = clean_identifier(item.get("symbol"))
            for field in ("problematic_code", "observed_evidence", "technical_consequence", "business_impact", "recommended_correction", "recommendation"):
                if item.get(field):
                    item[field] = _text(item[field]).replace("<arrow>", "anonymous callback")
            records.append(item)
    return records


def _location(item: Mapping[str, Any]) -> str:
    return _text(item.get("location") or item.get("exact_source") or item.get("path") or "location not retained", 500)


def _identifier(item: Mapping[str, Any]) -> str:
    return _text(item.get("finding_id") or item.get("id") or "unidentified finding", 160)


def _priority(item: Mapping[str, Any]) -> str:
    value = _text(item.get("priority") or item.get("severity") or "P2", 20).upper()
    return value if value in {"P0", "P1", "P2", "P3"} else "P2"


def compact_finding_register_markdown(register: Mapping[str, Any], *, spanish: bool) -> str:
    records = _records(register)
    summary = register.get("summary") if isinstance(register.get("summary"), Mapping) else {}
    heading = "## Registro compacto de hallazgos y remediación" if spanish else "## Compact Finding and Remediation Register"
    detail_heading = "### Detalle ejecutivo priorizado" if spanish else "### Prioritized executive detail"
    index_heading = "### Índice completo de fuentes exactas" if spanish else "### Complete exact-source index"
    boundary = ES_BOUNDARY if spanish else EN_BOUNDARY
    lines = [
        heading,
        "",
        (
            "El informe del cliente muestra detalle ejecutivo limitado y un índice completo de ubicaciones. "
            "El registro estructurado íntegro permanece en JSON y CSV para revisión técnica."
            if spanish
            else "The client report shows bounded executive detail and a complete exact-source index. "
            "The full structured register remains available in JSON and CSV for technical review."
        ),
        "",
        f"- {('Hallazgos de decisión' if spanish else 'Decision findings')}: {len(records)}",
        f"- {('Hallazgos de código con ubicación exacta' if spanish else 'Exact-source code findings')}: {_integer(summary.get('exact_source_code_finding_count'))}",
        f"- {('Hallazgos operativos o de contexto' if spanish else 'Operational or context findings')}: {_integer(summary.get('operational_or_context_finding_count'))}",
        f"- {('Estado de entrega' if spanish else 'Delivery status')}: {boundary}",
        "",
        detail_heading,
        "",
    ]
    for item in records[:MAX_EXECUTIVE_FINDINGS]:
        verification = item.get("verification") or item.get("acceptance_criteria") or []
        if isinstance(verification, str):
            verification = [verification]
        title = _authored_display(
            clean_finding_title(item.get("title")),
            "title",
            spanish=spanish,
            limit=700,
        )
        observed_evidence = _authored_display(
            item.get("observed_evidence")
            or item.get("fact")
            or ("revisión requerida" if spanish else "review required"),
            "observed_evidence",
            spanish=spanish,
            limit=900,
        )
        business_impact = _authored_display(
            item.get("business_impact")
            or item.get("impact")
            or ("requiere revisión" if spanish else "requires review"),
            "business_impact",
            spanish=spanish,
            limit=900,
        )
        correction = _authored_display(
            item.get("recommended_correction")
            or item.get("recommendation")
            or ("requiere revisión" if spanish else "requires review"),
            "recommended_correction",
            spanish=spanish,
            limit=1000,
        )
        localized_verification = [
            _authored_display(
                criterion,
                "verification",
                spanish=spanish,
                limit=900,
            )
            for criterion in _dedupe(verification, 2)
        ]
        lines.extend(
            [
                f"#### {_priority(item)} · {title} · {_identifier(item)}",
                f"- {('Fuente exacta' if spanish else 'Exact source')}: {_location(item)}",
                f"- {('Evidencia observada' if spanish else 'Observed evidence')}: {observed_evidence}",
                f"- {('Consecuencia comercial' if spanish else 'Business consequence')}: {business_impact}",
                f"- {('Corrección específica' if spanish else 'Specific correction')}: {correction}",
            ]
        )
        for criterion in localized_verification:
            lines.append(f"- {('Verificación' if spanish else 'Verification')}: {criterion}")
        lines.append("")

    lines.extend([index_heading, ""])
    for item in records:
        title = _authored_display(
            clean_finding_title(item.get("title")),
            "title",
            spanish=spanish,
            limit=700,
        )
        lines.append(
            f"- {_priority(item)} · {_identifier(item)} · {_location(item)} · "
            f"{title} · "
            f"{('revisión humana requerida' if spanish else 'human review required')}"
        )
    return "\n".join(lines).strip() + "\n"


def render_compact_finding_register_pdf(register: Mapping[str, Any], *, spanish: bool) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    records = _records(register)
    summary = register.get("summary") if isinstance(register.get("summary"), Mapping) else {}
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("CR-H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=colors.HexColor("#0f172a"), spaceAfter=9)
    h2 = ParagraphStyle("CR-H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, leading=15.5, textColor=colors.HexColor("#075985"), spaceBefore=6, spaceAfter=5)
    body = ParagraphStyle("CR-Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=10.6, textColor=colors.HexColor("#334155"), spaceAfter=4)
    small = ParagraphStyle("CR-Small", parent=body, fontSize=6.5, leading=8.1, textColor=colors.HexColor("#475569"), spaceAfter=2)
    warning = ParagraphStyle("CR-Warning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=.7, borderPadding=7, spaceAfter=8)

    def p(
        value: Any,
        style: ParagraphStyle = body,
        limit: int = 1800,
        *,
        client_literal: bool = False,
    ) -> Paragraph:
        if client_literal:
            from nico.comprehensive_engagement_metadata_v1 import reportlab_literal_markup

            return Paragraph(
                reportlab_literal_markup(value, min(4000, limit)),
                style,
            )
        else:
            rendered = _text(value, limit)
        return Paragraph(html.escape(rendered), style)

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(
            .55 * inch,
            .35 * inch,
            (
                "NICO · registro compacto de hallazgos · borrador automatizado"
                if spanish
                else "NICO · compact finding register · automated draft"
            ),
        )
        canvas.drawRightString(
            7.95 * inch,
            .35 * inch,
            f"{'Registro' if spanish else 'Register'} {doc.page}",
        )
        canvas.restoreState()

    boundary = ES_BOUNDARY if spanish else EN_BOUNDARY
    story: list[Any] = [
        p("Registro compacto de hallazgos y remediación" if spanish else "Compact Finding and Remediation Register", h1),
        p(boundary, warning),
        p(
            "El detalle completo permanece en los artefactos JSON y CSV. Este PDF conserva las decisiones prioritarias y todas las ubicaciones exactas sin repetir una página completa por hallazgo."
            if spanish
            else "Full detail remains in the JSON and CSV artifacts. This PDF preserves priority decisions and every exact source location without repeating a full page for each finding.",
            body,
        ),
    ]
    summary_rows = [
        ["Métrica" if spanish else "Metric", "Valor" if spanish else "Value"],
        ["Hallazgos de decisión" if spanish else "Decision findings", str(len(records))],
        ["Código con ubicación exacta" if spanish else "Exact-source code", str(_integer(summary.get("exact_source_code_finding_count")))],
        ["Operativos/contexto" if spanish else "Operational/context", str(_integer(summary.get("operational_or_context_finding_count")))],
    ]
    summary_table = Table([[p(cell, small) for cell in row] for row in summary_rows], colWidths=[2.3 * inch, 1.1 * inch])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([summary_table, Spacer(1, .12 * inch), p("Detalle ejecutivo priorizado" if spanish else "Prioritized executive detail", h2)])

    for item in records[:MAX_EXECUTIVE_FINDINGS]:
        verification = item.get("verification") or item.get("acceptance_criteria") or []
        if isinstance(verification, str):
            verification = [verification]
        title = _authored_display(
            clean_finding_title(item.get("title")),
            "title",
            spanish=spanish,
            limit=700,
        )
        observed_evidence = _authored_display(
            item.get("observed_evidence")
            or item.get("fact")
            or ("revisión requerida" if spanish else "review required"),
            "observed_evidence",
            spanish=spanish,
            limit=900,
        )
        business_impact = _authored_display(
            item.get("business_impact")
            or item.get("impact")
            or ("requiere revisión" if spanish else "requires review"),
            "business_impact",
            spanish=spanish,
            limit=900,
        )
        correction = _authored_display(
            item.get("recommended_correction")
            or item.get("recommendation")
            or ("requiere revisión" if spanish else "requires review"),
            "recommended_correction",
            spanish=spanish,
            limit=1000,
        )
        localized_verification = [
            _authored_display(
                criterion,
                "verification",
                spanish=spanish,
                limit=900,
            )
            for criterion in _dedupe(verification, 2)
        ]
        rows = [
            ["Prioridad / ID" if spanish else "Priority / ID", f"{_priority(item)} · {_identifier(item)}"],
            ["Hallazgo" if spanish else "Finding", title],
            ["Fuente exacta" if spanish else "Exact source", _location(item)],
            ["Evidencia" if spanish else "Evidence", observed_evidence],
            ["Impacto" if spanish else "Impact", business_impact],
            ["Corrección" if spanish else "Correction", correction],
            [
                "Verificación" if spanish else "Verification",
                "; ".join(localized_verification)
                or (
                    "Se requiere disposición humana"
                    if spanish
                    else "Human disposition required"
                ),
            ],
        ]
        table = Table([[p(left, small) if index else p(left, small) for index, left in enumerate(row)] for row in rows], colWidths=[1.15 * inch, 6.25 * inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.extend([table, Spacer(1, .1 * inch)])

    story.extend([PageBreak(), p("Índice completo de fuentes exactas" if spanish else "Complete Exact-Source Index", h1)])
    header = (
        ["Pri.", "ID del hallazgo", "Fuente exacta", "Hallazgo / disposición"]
        if spanish
        else ["Pri.", "Finding ID", "Exact source", "Finding / disposition"]
    )
    rows: list[list[Any]] = [[p(value, small) for value in header]]
    for item in records:
        title = _authored_display(
            clean_finding_title(item.get("title")),
            "title",
            spanish=spanish,
            limit=700,
        )
        rows.append([
            p(_priority(item), small),
            p(_identifier(item), small),
            p(_location(item), small, 700),
            p(
                f"{title} · "
                f"{'revisión humana requerida' if spanish else 'human review required'}",
                small,
                900,
            ),
        ])
    index = LongTable(rows, colWidths=[.36 * inch, 1.18 * inch, 2.8 * inch, 3.06 * inch], repeatRows=1, splitByRow=1)
    index.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(index)

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.55 * inch,
        rightMargin=.55 * inch,
        topMargin=.55 * inch,
        bottomMargin=.62 * inch,
        invariant=1,
        title="NICO Compact Finding and Remediation Register",
        author="NICO",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _candidate_summary(canonical: Mapping[str, Any]) -> tuple[int, int, dict[str, Mapping[str, Any]]]:
    summary = canonical.get("review_candidate_summary") if isinstance(canonical.get("review_candidate_summary"), Mapping) else {}
    if not summary:
        assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
        summary = assessment.get("review_candidate_summary") if isinstance(assessment.get("review_candidate_summary"), Mapping) else {}
    review = _integer(summary.get("review_required_total"))
    material = _integer(summary.get("verified_material_total"))
    categories = summary.get("by_category") if isinstance(summary.get("by_category"), Mapping) else {}
    return review, material, {str(key): value for key, value in categories.items() if isinstance(value, Mapping)}


def render_evidence_review_gate_pdf(canonical: Mapping[str, Any], register: Mapping[str, Any], *, spanish: bool) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}
    technical = assessment.get("technical_score", maturity.get("technical_score", maturity.get("score")))
    adjusted = assessment.get("canonical_evidence_adjusted_score", assessment.get("evidence_adjusted_score"))
    scanners = [item for item in canonical.get("scanner_execution_records") or [] if isinstance(item, Mapping)]
    completed = [item for item in scanners if item.get("completed") is True]
    review, material, categories = _candidate_summary(canonical)
    summary = register.get("summary") if isinstance(register.get("summary"), Mapping) else {}

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("CG-H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=colors.HexColor("#0f172a"), spaceAfter=10)
    h2 = ParagraphStyle("CG-H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=colors.HexColor("#075985"), spaceBefore=7, spaceAfter=5)
    body = ParagraphStyle("CG-Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.4, leading=11.2, textColor=colors.HexColor("#334155"), spaceAfter=5)
    small = ParagraphStyle("CG-Small", parent=body, fontSize=7.2, leading=9.3, textColor=colors.HexColor("#475569"), spaceAfter=3)
    warning = ParagraphStyle("CG-Warning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=.7, borderPadding=8, spaceAfter=9)

    def p(
        value: Any,
        style: ParagraphStyle = body,
        limit: int = 1800,
        *,
        client_literal: bool = False,
    ) -> Paragraph:
        if client_literal:
            from nico.comprehensive_engagement_metadata_v1 import reportlab_literal_markup

            return Paragraph(reportlab_literal_markup(value, limit), style)
        return Paragraph(html.escape(_text(value, limit)), style)

    boundary = ES_BOUNDARY if spanish else EN_BOUNDARY
    from nico.comprehensive_engagement_metadata_v1 import _literal

    def engagement_value(key: str, limit: int) -> str:
        value = _literal(identity.get(key), limit)
        return value or ("No proporcionado" if spanish else "Not supplied")

    story: list[Any] = [p("Resumen de evidencia del cliente" if spanish else "Client Evidence Summary", h1), p(boundary, warning)]
    identity_rows = [
        ["Nombre del cliente" if spanish else "Client name", engagement_value("customer_name", 180)],
        ["Nombre del proyecto" if spanish else "Project name", engagement_value("project_name", 180)],
        ["Contacto técnico principal" if spanish else "Primary technical contact", engagement_value("primary_technical_contact", 600)],
        ["Método de acceso" if spanish else "Access method", engagement_value("access_method", 1200)],
        ["Alcance autorizado" if spanish else "Authorized scope", engagement_value("authorized_scope", 4000)],
        ["Repositorio" if spanish else "Repository", _text(identity.get("repository"))],
        ["Commit exacto" if spanish else "Exact commit", _text(identity.get("commit_sha"))],
        ["ID de ejecución" if spanish else "Run ID", _text(identity.get("run_id"))],
        ["Madurez técnica" if spanish else "Technical maturity", f"{int(technical)}/100" if isinstance(technical, (int, float)) else ("SIN PUNTUACIÓN" if spanish else "NOT SCORED")],
        ["Ajuste por evidencia" if spanish else "Evidence-Adjusted", f"{int(adjusted)}/100" if isinstance(adjusted, (int, float)) else ("SIN PUNTUACIÓN" if spanish else "NOT SCORED")],
    ]
    identity_table = Table(
        [
            [p(a, small), p(b, small, 4000, client_literal=index < 5)]
            for index, (a, b) in enumerate(identity_rows)
        ],
        colWidths=[1.55 * inch, 5.85 * inch],
    )
    identity_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([identity_table, p("Separación de ejecución y disposición" if spanish else "Execution and disposition are separate", h2)])
    story.append(p(
        f"{len(completed)} of {len(scanners)} applicable scanner executions completed. {review} candidate(s) remain pending human triage; {material} confirmed material finding(s) are currently retained. Scanner completion does not equal candidate approval."
        if not spanish
        else f"Se completaron {len(completed)} de {len(scanners)} ejecuciones aplicables. {review} candidato(s) siguen pendientes de revisión humana; se conservan {material} hallazgo(s) material(es) confirmado(s). Completar el analizador no equivale a aprobar los candidatos.",
        body,
    ))
    if categories:
        rows = [[
            "Categoría" if spanish else "Category",
            "Brutos" if spanish else "Raw",
            "Materiales confirmados" if spanish else "Confirmed material",
            "Requieren revisión" if spanish else "Review required",
            "Efecto en la puntuación" if spanish else "Score effect",
        ]]
        category_labels_es = {
            "dependency": "Dependencias",
            "secret": "Secretos",
            "static": "Análisis estático",
        }
        for category, counts in categories.items():
            rows.append([
                category_labels_es.get(category.casefold(), category) if spanish else category.title(),
                str(_integer(counts.get("raw"))),
                str(_integer(counts.get("material"))),
                str(_integer(counts.get("review_required"))),
                (
                    "Solo aseguramiento mientras la disposición humana autorizada siga pendiente; el estado del triaje técnico se informa por separado"
                    if spanish
                    else "Assurance-only until triaged"
                ),
            ])
        table = Table([[p(cell, small) for cell in row] for row in rows], colWidths=[1.25 * inch, .6 * inch, 1.05 * inch, 1.0 * inch, 3.45 * inch], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)
    story.extend([
        p("Límite del paquete del cliente" if spanish else "Client package boundary", h2),
        p(
            "The PDF is decision-oriented. Full stage evidence, all finding fields, scanner hashes, and export-ready remediation data remain in the canonical JSON, findings CSV, evidence CSV, and backlog artifacts. Blank internal fields and duplicate finding cards are intentionally excluded from the client PDF."
            if not spanish
            else "El PDF está orientado a decisiones. La evidencia completa de etapas, todos los campos de hallazgos, hashes de analizadores y datos de remediación permanecen en JSON canónico, CSV de hallazgos, CSV de evidencia y artefactos de backlog. Los campos internos vacíos y tarjetas duplicadas se excluyen del PDF del cliente.",
            body,
        ),
        p(f"{('Hallazgos exactos en el índice' if spanish else 'Exact-source findings in index')}: {_integer(summary.get('exact_source_code_finding_count'))}", small),
        PageBreak(),
        p("Puerta de revisión humana y aceptación" if spanish else "Human Review and Acceptance Gate", h1),
        p(boundary, warning),
    ])
    checklist = [
        "Verify repository, run, commit, evidence-ledger, customer, and project identities.",
        "Triage every review-required scanner candidate against the retained exact-run artifacts.",
        "Confirm technical score, Evidence-Adjusted score, assurance state, limitation accounting, and delivery status match across JSON, CSV, Markdown, HTML, and PDF.",
        "Disposition every executive risk and record residual risk, owner, and acceptance evidence.",
        "Validate business context, assumptions, roadmap, staffing, effort, and any financial inputs.",
        "Approve or reject this exact immutable automated draft before authorizing client delivery.",
    ]
    if spanish:
        checklist = [
            "Verificar las identidades de repositorio, ejecución, commit, libro de evidencia, cliente y proyecto.",
            "Revisar cada candidato pendiente contra los artefactos conservados de la ejecución exacta.",
            "Confirmar que puntuaciones, aseguramiento, limitaciones y estado de entrega coincidan en JSON, CSV, Markdown, HTML y PDF.",
            "Disponer cada riesgo ejecutivo y registrar riesgo residual, responsable y evidencia de aceptación.",
            "Validar contexto comercial, supuestos, hoja de ruta, personal, esfuerzo y datos financieros.",
            "Aprobar o rechazar este borrador automatizado inmutable antes de autorizar la entrega.",
        ]
    for index, item in enumerate(checklist, start=1):
        story.append(p(f"{index}. {item}", body))
    story.extend([
        Spacer(1, .12 * inch),
        p(
            "Only an authorized human reviewer may approve the exact immutable artifacts. Client delivery requires a separate authorized action."
            if not spanish
            else "Solo un revisor humano autorizado puede aprobar los artefactos inmutables exactos. La entrega al cliente requiere una acción autorizada independiente.",
            warning,
        ),
    ])
    document = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=.55 * inch, rightMargin=.55 * inch, topMargin=.55 * inch, bottomMargin=.6 * inch, invariant=1, title="NICO Client Evidence and Review Gate", author="NICO")
    document.build(story)
    return buffer.getvalue()


def _normalized_page_text(page: Any) -> str:
    return " ".join((page.extract_text() or "").casefold().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").split())


def _finding_detail_page(text: str) -> bool:
    if "nico-finding-" in text and "exact source" in text and ("implementation sequence" in text or "disposition" in text):
        return True
    if "nico-code-" in text and "action:" in text and "cyclomatic_complexity" in text:
        return True
    return False


def compose_compact_client_pdf(base_pdf: bytes, register_pdf: bytes, gate_pdf: bytes) -> bytes:
    if not base_pdf.startswith(b"%PDF"):
        raise ValueError("compact client composition requires a valid base PDF")
    base = PdfReader(io.BytesIO(base_pdf))
    register = PdfReader(io.BytesIO(register_pdf))
    gate = PdfReader(io.BytesIO(gate_pdf))
    retained: list[Any] = []
    for page in base.pages:
        text = _normalized_page_text(page)
        if any(marker in text for marker in _PROVENANCE_PAGE_MARKERS):
            continue
        if any(marker in text for marker in _REGISTER_PAGE_MARKERS):
            continue
        if _finding_detail_page(text):
            continue
        if any(marker in text for marker in _EVIDENCE_PAGE_MARKERS):
            break
        if any(marker in text for marker in _REVIEW_PAGE_MARKERS):
            continue
        retained.append(page)

    writer = PdfWriter()
    for page in retained:
        writer.add_page(page)
    for page in register.pages:
        writer.add_page(page)
    for page in gate.pages:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    pdf = output.getvalue()
    page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    if page_count > MAX_CLIENT_PDF_PAGES:
        raise ValueError(f"client-ready PDF exceeds the {MAX_CLIENT_PDF_PAGES}-page boundary: {page_count}")
    return pdf


def _remove_heading_section(markdown: str, heading: str) -> str:
    start = markdown.find(heading)
    if start < 0:
        return markdown
    level = len(heading) - len(heading.lstrip("#"))
    pattern = re.compile(rf"(?m)^#{{1,{level}}}\s+.+$")
    match = pattern.search(markdown, start + len(heading))
    end = match.start() if match else len(markdown)
    return markdown[:start].rstrip() + "\n\n" + markdown[end:].lstrip()


def compact_client_markdown(existing: str, canonical: Mapping[str, Any], register: Mapping[str, Any], *, spanish: bool) -> str:
    markdown = str(existing or "")
    for heading in (*_REGISTER_HEADINGS, *_REMOVE_H2_HEADINGS):
        while heading in markdown:
            markdown = _remove_heading_section(markdown, heading)
    for heading in (
        "### Executive Risk Register and Decision Briefing",
        "### Registro ejecutivo de riesgos y decisiones",
    ):
        while heading in markdown:
            markdown = _remove_heading_section(markdown, heading)

    boundary = ES_BOUNDARY if spanish else EN_BOUNDARY
    replacements = {
        "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED · CLIENT DELIVERY NOT AUTHORIZED": boundary,
        "FINAL REPORT — PENDING HUMAN APPROVAL — CLIENT DELIVERY BLOCKED — CLIENT DELIVERY NOT AUTHORIZED": boundary,
        "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED": boundary,
        "FINAL REPORT": "AUTOMATED DRAFT",
        "INFORME FINAL PENDIENTE DE APROBACIÓN": "BORRADOR AUTOMATIZADO PENDIENTE DE APROBACIÓN",
        "INFORME FINAL": "BORRADOR AUTOMATIZADO",
        "The package is a final automated assessment pending human approval": "The package is an automated draft pending human approval",
        "The report is a final automated assessment pending human approval.": "The report is an automated draft pending human approval.",
    }
    for old, new in replacements.items():
        markdown = markdown.replace(old, new)

    compact_register = compact_finding_register_markdown(register, spanish=spanish).strip()
    evidence_heading = "## Resumen del paquete de evidencia" if spanish else "## Evidence Package Summary"
    review_heading = "## Puerta de revisión humana y aceptación" if spanish else "## Human Review and Acceptance Gate"
    review, material, _ = _candidate_summary(canonical)
    evidence = "\n".join(
        [
            evidence_heading,
            "",
            (
                "El PDF conserva decisiones, ubicaciones exactas y limitaciones. La evidencia completa permanece en JSON y CSV."
                if spanish
                else "The PDF retains decisions, exact source locations, and limitations. Full stage evidence remains in JSON and CSV."
            ),
            f"- {('Candidatos pendientes de revisión' if spanish else 'Review-required candidates')}: {review}",
            f"- {('Hallazgos materiales confirmados' if spanish else 'Confirmed material findings')}: {material}",
            "- Score effect: assurance-only until triaged." if not spanish else "- Efecto en puntuación: solo aseguramiento hasta completar la revisión.",
        ]
    )
    checklist = (
        "- [ ] Verify exact package identity and cross-format score/status truth.\n"
        "- [ ] Triage review-required candidates using retained scanner artifacts.\n"
        "- [ ] Approve or reject this immutable automated draft before delivery."
        if not spanish
        else "- [ ] Verificar la identidad exacta del paquete y la verdad de puntuación/estado.\n"
        "- [ ] Revisar candidatos pendientes usando los artefactos conservados.\n"
        "- [ ] Aprobar o rechazar este borrador automatizado antes de la entrega."
    )
    review_section = f"{review_heading}\n\n**{boundary}**\n\n{checklist}"
    marker = "## Delivery Status" if not spanish else "## Estado de entrega"
    insert = f"{compact_register}\n\n{evidence}\n\n{review_section}\n\n"
    if marker in markdown:
        markdown = markdown.replace(marker, insert + marker, 1)
    else:
        markdown = markdown.rstrip() + "\n\n" + insert
    if boundary not in markdown:
        rows = markdown.splitlines()
        rows.insert(2 if len(rows) >= 2 else len(rows), f"**{boundary}**")
        markdown = "\n".join(rows)
    if "CLIENT DELIVERY NOT AUTHORIZED" not in markdown:
        markdown = markdown.rstrip() + "\n\n<!-- CLIENT DELIVERY NOT AUTHORIZED -->\n"
    return markdown.strip() + "\n"


def apply_automated_draft_truth(value: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(value))
    output.update(
        {
            "approval_state": APPROVAL_SUFFIX,
            "report_finality": REPORT_FINALITY,
            "approval_status": APPROVAL_STATUS,
            "delivery_status": DELIVERY_STATUS,
            "assessment_state": "review_required",
            "human_review_required": True,
            "human_review_completed": False,
            "client_delivery_allowed": False,
        }
    )
    assessment = deepcopy(dict(output.get("assessment") or {}))
    assessment.update(
        {
            "automated_status": "complete",
            "human_review_status": "pending_human_approval",
            "client_delivery_status": "blocked",
            "report_finality": REPORT_FINALITY,
            "client_ready": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    output["assessment"] = assessment
    return output


__all__ = [
    "APPROVAL_STATUS",
    "APPROVAL_SUFFIX",
    "DELIVERY_STATUS",
    "EN_BOUNDARY",
    "ES_BOUNDARY",
    "MAX_CLIENT_PDF_PAGES",
    "REPORT_FINALITY",
    "VERSION",
    "apply_automated_draft_truth",
    "clean_finding_title",
    "clean_identifier",
    "compact_client_markdown",
    "compact_finding_register_markdown",
    "compose_compact_client_pdf",
    "render_compact_finding_register_pdf",
    "render_evidence_review_gate_pdf",
]
