from __future__ import annotations

import html
import io
import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

VERSION = "nico.comprehensive-client-review-companion.v2.2"
MIN_CLIENT_REVIEW_PAGES = 8
MAX_CLIENT_REVIEW_PAGES = 45

# These late review-companion strings are assembled from canonical stage summaries
# after the broader report localization pass. Keep the translations at this final
# presentation boundary as well so Spanish correctness does not depend on bootstrap
# monkey-patch ordering.
_SPANISH_DYNAMIC_PHRASES = {
    "Review-Required Candidate Register": "Registro de candidatos que requieren revisión",
    "Material confirmado findings": "Hallazgos materiales confirmados",
    "verificada material findings": "hallazgos materiales verificados",
    "Confirmed material findings": "Hallazgos materiales confirmados",
    "Exact-commit executable source signals were analyzed without promoting comments, strings, detector definitions, examples, or tests.": (
        "Se analizaron las señales ejecutables del código fuente del commit exacto sin convertir comentarios, cadenas, "
        "definiciones de detectores, ejemplos ni pruebas en defectos."
    ),
    "Authoritative manifests and contextual dependency evidence were reconciled by package, installed version, advisory, fixed version, path, scope, and reachability.": (
        "Los manifiestos autoritativos y la evidencia contextual de dependencias se conciliaron por paquete, versión instalada, "
        "aviso, versión corregida, ruta, alcance y accesibilidad."
    ),
    "History-aware secret evidence was separated into verified material findings, review-required candidates, explicit example placeholders, and non-production observations.": (
        "La evidencia de secretos con conocimiento del historial se separó en hallazgos materiales verificados, candidatos que requieren "
        "revisión, marcadores explícitos de ejemplo y observaciones ajenas a producción."
    ),
    "Sustainable delivery capacity is derived from immutable architecture maintainability and workflow automation; mutable activity volume is unscored context.": (
        "La capacidad de entrega sostenible se deriva de la mantenibilidad inmutable de la arquitectura y la automatización de los flujos "
        "de trabajo; el volumen de actividad mutable es contexto sin puntuación."
    ),
    "Strengthen architecture boundaries, test/release automation, functional QA evidence, and remediation verification.": (
        "Reforzar los límites de arquitectura, la automatización de pruebas y publicaciones, la evidencia de QA funcional y la verificación de remediaciones."
    ),
    "Non-success deployment classification": "Clasificación de despliegues no exitosos",
    "Not available": "No disponible",
    "Job success rate": "Tasa de éxito de trabajos",
    "Successful workflow runs": "Ejecuciones exitosas de flujos de trabajo",
    "Non-success workflow runs": "Ejecuciones no exitosas de flujos de trabajo",
    "Jobs observed": "Trabajos observados",
    "Jobs observado": "Trabajos observados",
    "Deployments observed": "Despliegues observados",
    "Deployments observado": "Despliegues observados",
    "Successful deployments": "Despliegues exitosos",
    "Non-success deployments": "Despliegues no exitosos",
    "Cybersecurity specialist": "Especialista en ciberseguridad",
    "Code audit": "Auditoría de código",
    "Exceptional": "Excepcional",
    "immutable native-control vector=not applicable; provider-neutral objective coverage is reported separately.": (
        "vector inmutable de controles nativos=no aplica; la cobertura de objetivos neutral al proveedor se informa por separado."
    ),
    "Human context or additional evidence is required before this section can be accepted.": (
        "Se requiere contexto humano o evidencia adicional antes de aceptar esta sección."
    ),
    "Named people, rates, contract structure, geographic mix, and budget require client input.": (
        "Las personas, tarifas, estructura contractual, distribución geográfica y presupuesto requieren información del cliente."
    ),
}

_SECTION_SPECS = (
    {
        "id": "functional_qa",
        "aliases": ("functional_qa",),
        "title": "Functional QA",
        "title_es": "QA funcional",
        "questions": (
            "Which critical user journeys were executed outside repository-only evidence?",
            "What acceptance criteria and regression tests must pass before delivery?",
            "Which runtime, browser, device, or integration environments remain untested?",
        ),
        "questions_es": (
            "¿Qué recorridos críticos se ejecutaron fuera de la evidencia del repositorio?",
            "¿Qué criterios de aceptación y pruebas de regresión deben aprobarse antes de la entrega?",
            "¿Qué entornos de ejecución, navegador, dispositivo o integración siguen sin probarse?",
        ),
    },
    {
        "id": "platform_parity",
        "aliases": ("platform_parity",),
        "title": "Platform Parity",
        "title_es": "Paridad de plataformas",
        "questions": (
            "Which platforms are actually in scope for this client engagement?",
            "Which features, permissions, copy, and failure states require cross-platform comparison?",
            "What runnable builds or device evidence must be supplied to validate parity?",
        ),
        "questions_es": (
            "¿Qué plataformas están realmente dentro del alcance del encargo?",
            "¿Qué funciones, permisos, textos y estados de error requieren comparación?",
            "¿Qué compilaciones o evidencia de dispositivos debe aportarse para validar la paridad?",
        ),
    },
    {
        "id": "historical_trends_and_change_failure",
        "aliases": ("historical_trends_and_change_failure", "historical_trends"),
        "title": "Historical Trends and Change Failure",
        "title_es": "Tendencias históricas y fallos de cambio",
        "questions": (
            "Which workflow outcomes represent genuine product failures versus cancellation, supersession, or infrastructure noise?",
            "Are incident, deployment, rollback, and recovery-time records available?",
            "Which historical indicators are context only and must remain outside the technical score?",
        ),
        "questions_es": (
            "¿Qué resultados representan fallos reales frente a cancelaciones, reemplazos o ruido de infraestructura?",
            "¿Existen registros de incidentes, despliegues, reversión y tiempo de recuperación?",
            "¿Qué indicadores son solo contexto y deben permanecer fuera de la puntuación técnica?",
        ),
    },
    {
        "id": "requirements_traceability",
        "aliases": ("requirements_traceability",),
        "title": "Requirements Traceability",
        "title_es": "Trazabilidad de requisitos",
        "questions": (
            "Which specifications, ADRs, roadmap commitments, and acceptance criteria are authoritative?",
            "Can each priority finding be linked to a requirement, owner, and verification artifact?",
            "Which requirements remain inferred, missing, or unapproved?",
        ),
        "questions_es": (
            "¿Qué especificaciones, ADR, compromisos y criterios de aceptación son autoritativos?",
            "¿Puede vincularse cada hallazgo prioritario con requisito, responsable y evidencia de verificación?",
            "¿Qué requisitos siguen inferidos, faltantes o sin aprobación?",
        ),
    },
    {
        "id": "stakeholder_and_business_alignment",
        "aliases": ("stakeholder_and_business_alignment", "stakeholder_alignment"),
        "title": "Stakeholder and Business Alignment",
        "title_es": "Alineación comercial y de partes interesadas",
        "questions": (
            "Who owns the business decision, technical acceptance, budget, and residual-risk approval?",
            "Which objectives, deadlines, constraints, and success measures were explicitly supplied?",
            "Which assumptions must be confirmed rather than inferred from repository evidence?",
        ),
        "questions_es": (
            "¿Quién decide sobre negocio, aceptación técnica, presupuesto y riesgo residual?",
            "¿Qué objetivos, plazos, restricciones y medidas de éxito fueron aportados explícitamente?",
            "¿Qué supuestos deben confirmarse en vez de inferirse del repositorio?",
        ),
    },
    {
        "id": "risk_reduction_and_executive_briefing",
        "aliases": ("risk_reduction_and_executive_briefing",),
        "title": "Risk Reduction and Executive Briefing",
        "title_es": "Reducción de riesgo y resumen ejecutivo",
        "questions": (
            "Which findings are accepted, rejected, deferred, or require more evidence?",
            "What is the residual risk, owner, expected impact, and verification method for each priority decision?",
            "Which recommendations are advisory rather than approved commitments?",
        ),
        "questions_es": (
            "¿Qué hallazgos se aceptan, rechazan, aplazan o requieren más evidencia?",
            "¿Cuál es el riesgo residual, responsable, impacto y método de verificación de cada decisión?",
            "¿Qué recomendaciones son asesoría y no compromisos aprobados?",
        ),
    },
    {
        "id": "six_month_roadmap",
        "aliases": ("six_month_roadmap",),
        "title": "Six-Month Roadmap",
        "title_es": "Hoja de ruta de seis meses",
        "questions": (
            "Are the 0-30, 31-90, and 91-180 day objectives correctly sequenced?",
            "Which dependencies, owners, acceptance criteria, and expected impacts are approved?",
            "Which calendar dates remain illustrative until stakeholder confirmation?",
        ),
        "questions_es": (
            "¿Están correctamente secuenciados los objetivos de 0-30, 31-90 y 91-180 días?",
            "¿Qué dependencias, responsables, criterios e impactos están aprobados?",
            "¿Qué fechas siguen siendo ilustrativas hasta su confirmación?",
        ),
    },
    {
        "id": "staffing_sequencing_and_cost",
        "aliases": ("staffing_sequencing_and_cost", "resourcing"),
        "title": "Staffing, Sequencing, and Cost",
        "title_es": "Personal, secuencia y costo",
        "questions": (
            "Which roles and sequence are required to execute the approved roadmap?",
            "What capacity, contract structure, geographic mix, and budget ceiling are authorized?",
            "Which effort or cost values remain indicative because rates and scope were not supplied?",
        ),
        "questions_es": (
            "¿Qué funciones y secuencia se requieren para ejecutar la hoja de ruta aprobada?",
            "¿Qué capacidad, contrato, mezcla geográfica y límite presupuestario están autorizados?",
            "¿Qué valores siguen siendo indicativos porque no se aportaron tarifas o alcance?",
        ),
    },
)


def _text(value: Any, limit: int = 1200) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _localize_spanish_dynamic(value: Any) -> str:
    """Localize late NICO-authored display copy without depending on patch order."""

    from nico import comprehensive_spanish_presentation_parity_v1 as presentation

    text = _text(value, 12000)
    for source, target in sorted(
        _SPANISH_DYNAMIC_PHRASES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        text = text.replace(source, target)
    return presentation._safe_es(text)


def _values(value: Any, *, limit: int, item_limit: int = 700) -> list[str]:
    if isinstance(value, Mapping):
        raw_values: Iterable[Any] = (
            f"{key}: {item}"
            for key, item in value.items()
            if item not in (None, "", [], {})
        )
    elif isinstance(value, (list, tuple, set)):
        raw_values = value
    elif value not in (None, ""):
        raw_values = (value,)
    else:
        raw_values = ()
    output: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        item = _text(raw, item_limit)
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= limit:
            break
    return output


def _stage_map(canonical: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    sources = (
        canonical.get("stage_summaries"),
        assessment.get("stage_summaries"),
        canonical.get("stages"),
        assessment.get("stages"),
    )
    output: dict[str, dict[str, Any]] = {}
    for source in sources:
        if isinstance(source, Mapping):
            records = source.values()
        elif isinstance(source, list):
            records = source
        else:
            continue
        for raw in records:
            if not isinstance(raw, Mapping):
                continue
            item = deepcopy(dict(raw))
            stage_id = _text(
                item.get("stage_id") or item.get("id") or item.get("capability"),
                160,
            ).casefold().replace("-", "_").replace(" ", "_")
            if stage_id:
                output[stage_id] = item
    return output


def _fallback_stage(canonical: Mapping[str, Any], section_id: str) -> dict[str, Any]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    if section_id == "six_month_roadmap":
        roadmap = canonical.get("roadmap") or assessment.get("roadmap") or []
        return {
            "status": "complete" if roadmap else "unavailable",
            "summary": "A bounded roadmap was retained from the canonical assessment." if roadmap else "No structured roadmap was retained in the canonical package.",
            "evidence": roadmap,
            "unavailable": [] if roadmap else ["Dates, owners, dependencies, and budget require explicit stakeholder confirmation."],
        }
    if section_id == "staffing_sequencing_and_cost":
        staffing = canonical.get("staffing_plan") or assessment.get("staffing_plan") or []
        return {
            "status": "complete" if staffing else "unavailable",
            "summary": "A role-based staffing sequence was retained without treating unverified rates as committed cost." if staffing else "No structured staffing plan was retained in the canonical package.",
            "evidence": staffing,
            "unavailable": [] if staffing else ["Named people, rates, contract structure, geographic mix, and budget require client input."],
        }
    return {
        "status": "unavailable",
        "summary": "No retained structured stage summary was available in this automated package.",
        "evidence": [],
        "findings": [],
        "unavailable": ["Human context or additional evidence is required before this section can be accepted."],
    }


def review_sections(canonical: Mapping[str, Any], *, spanish: bool) -> list[dict[str, Any]]:
    stages = _stage_map(canonical)
    output: list[dict[str, Any]] = []
    for spec in _SECTION_SPECS:
        stage: dict[str, Any] | None = None
        for alias in spec["aliases"]:
            normalized = str(alias).casefold().replace("-", "_")
            if normalized in stages:
                stage = deepcopy(stages[normalized])
                break
        if stage is None:
            stage = _fallback_stage(canonical, str(spec["id"]))
        evidence = _values(
            stage.get("evidence") or stage.get("retained_evidence"),
            limit=8,
        )
        findings = _values(stage.get("findings"), limit=3)
        limitations = _values(
            stage.get("unavailable")
            or stage.get("limitations")
            or stage.get("unavailable_data_notes"),
            limit=6,
        )
        if not limitations and str(stage.get("status") or "").casefold() in {
            "unavailable",
            "review_required",
            "limited",
        }:
            limitations = [
                "Se requiere revisión humana o evidencia adicional antes de la aceptación."
                if spanish
                else "Human review or additional evidence is required before acceptance."
            ]
        output.append(
            {
                "id": spec["id"],
                "title": spec["title_es"] if spanish else spec["title"],
                "status": _text(stage.get("status") or "unavailable", 80),
                "summary": _text(stage.get("summary") or stage.get("description"), 1100),
                "evidence": evidence,
                "findings": findings,
                "limitations": limitations,
                "questions": list(spec["questions_es"] if spanish else spec["questions"]),
            }
        )
    if spanish:
        for section in output:
            for field in ("status", "summary"):
                section[field] = _localize_spanish_dynamic(section.get(field))
            for field in ("evidence", "findings", "limitations"):
                section[field] = [
                    _localize_spanish_dynamic(item)
                    for item in section.get(field, [])
                ]
    return output


def _remove_heading_section(markdown: str, heading: str) -> str:
    start = markdown.find(heading)
    if start < 0:
        return markdown
    level = len(heading) - len(heading.lstrip("#"))
    match = re.compile(rf"(?m)^#{{1,{level}}}\s+.+$").search(
        markdown,
        start + len(heading),
    )
    end = match.start() if match else len(markdown)
    return markdown[:start].rstrip() + "\n\n" + markdown[end:].lstrip()


def merge_review_companion_markdown(
    markdown: str,
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    output = str(markdown or "")
    sections = review_sections(canonical, spanish=spanish)
    for section in sections:
        heading = f"## {section['title']}"
        while heading in output:
            output = _remove_heading_section(output, heading)

    lines = [
        "## Revisión integral del cliente" if spanish else "## Comprehensive Client Review",
        "",
        (
            "Estas secciones conservan evidencia útil para decisiones sin reintroducir el volcado interno completo. Los datos faltantes permanecen identificados y toda conclusión sigue pendiente de revisión humana."
            if spanish
            else "These sections retain decision-useful evidence without reintroducing the full internal stage dump. Missing data remains identified and every conclusion remains pending human review."
        ),
        "",
    ]
    for section in sections:
        lines.extend(
            [
                f"## {section['title']}",
                "",
                f"- {('Estado' if spanish else 'Status')}: {section['status']}",
                f"- {('Resumen' if spanish else 'Summary')}: {section['summary'] or ('No disponible' if spanish else 'Unavailable')}",
                "",
                f"### {('Evidencia conservada' if spanish else 'Retained evidence')}",
                "",
            ]
        )
        lines.extend(
            f"- {item}" for item in (
                section["evidence"]
                or (["No se conservó evidencia estructurada adicional."] if spanish else ["No additional structured evidence was retained."])
            )
        )
        if section["findings"]:
            lines.extend(["", f"### {('Observaciones' if spanish else 'Observations')}", ""])
            lines.extend(f"- {item}" for item in section["findings"])
        lines.extend(["", f"### {('Limitaciones y decisiones del revisor' if spanish else 'Limitations and reviewer decisions')}", ""])
        lines.extend(
            f"- {item}" for item in (
                section["limitations"]
                or (["No se conservó una limitación adicional."] if spanish else ["No additional limitation was retained."])
            )
        )
        lines.extend(f"- [ ] {item}" for item in section["questions"])
        lines.append("")

    companion = "\n".join(lines).strip() + "\n"
    markers = (
        "## Compact Finding and Remediation Register",
        "## Registro compacto de hallazgos y remediación",
        "## Evidence Package Summary",
        "## Resumen del paquete de evidencia",
    )
    for marker in markers:
        if marker in output:
            output = output.replace(marker, companion + "\n" + marker, 1)
            break
    else:
        output = output.rstrip() + "\n\n" + companion
    # Remove orphan Markdown heading tokens left by legacy section extraction.
    output = re.sub(r"(?m)^#{1,6}\s*$\n?", "", output)
    return output.strip() + "\n"


def render_comprehensive_review_companion_pdf(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    sections = review_sections(canonical, spanish=spanish)
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "NICOReviewTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15.5,
        leading=18.5,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=5,
    )
    heading = ParagraphStyle(
        "NICOReviewHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=9.4,
        leading=11.4,
        textColor=colors.HexColor("#075985"),
        spaceBefore=3,
        spaceAfter=2,
    )
    body = ParagraphStyle(
        "NICOReviewBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=6.9,
        leading=8.4,
        textColor=colors.HexColor("#334155"),
        spaceAfter=2,
    )
    small = ParagraphStyle(
        "NICOReviewSmall",
        parent=body,
        fontSize=6.2,
        leading=7.5,
        textColor=colors.HexColor("#475569"),
        spaceAfter=1.5,
    )
    warning = ParagraphStyle(
        "NICOReviewWarning",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=6.7,
        leading=8.1,
        textColor=colors.HexColor("#92400e"),
        backColor=colors.HexColor("#fef3c7"),
        borderColor=colors.HexColor("#f59e0b"),
        borderWidth=.6,
        borderPadding=4,
        spaceAfter=4,
    )

    def p(value: Any, style: ParagraphStyle = body, limit: int = 1200) -> Paragraph:
        return Paragraph(html.escape(_text(value, limit)), style)

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(.55 * inch, .35 * inch, "NICO | Comprehensive client review | automated draft")
        canvas.drawRightString(7.95 * inch, .35 * inch, f"Review sheet {doc.page}")
        canvas.restoreState()

    story: list[Any] = []
    for section_index, section in enumerate(sections):
        story.extend(
            [
                p(section["title"], title),
                p(
                    "BORRADOR AUTOMATIZADO | DECISIÓN HUMANA PENDIENTE | ENTREGA BLOQUEADA"
                    if spanish
                    else "AUTOMATED DRAFT | HUMAN DECISION PENDING | CLIENT DELIVERY BLOCKED",
                    warning,
                ),
            ]
        )
        status_table = Table(
            [
                [p("Estado" if spanish else "Status", small), p(section["status"], small)],
                [p("Resumen" if spanish else "Summary", small), p(section["summary"] or ("No disponible" if spanish else "Unavailable"), small, 900)],
            ],
            colWidths=[1.05 * inch, 6.35 * inch],
        )
        status_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.extend([status_table, p("Evidencia conservada" if spanish else "Retained evidence", heading)])
        evidence = section["evidence"] or [
            "No se conservó evidencia estructurada adicional."
            if spanish
            else "No additional structured evidence was retained."
        ]
        for item in evidence[:8]:
            story.append(p(f"- {item}", small, 420))
        if section["findings"]:
            story.append(p("Observaciones" if spanish else "Observations", heading))
            for item in section["findings"][:3]:
                story.append(p(f"- {item}", small, 420))

        story.append(p("Limitaciones conservadas" if spanish else "Retained limitations", heading))
        limitations = section["limitations"] or [
            "No se conservó una limitación adicional."
            if spanish
            else "No additional limitation was retained."
        ]
        for item in limitations[:6]:
            story.append(p(f"- {item}", small, 420))

        story.append(p("Decisiones del revisor" if spanish else "Reviewer decisions", heading))
        for item in section["questions"]:
            story.append(p(f"[ ] {item}", small, 420))
        story.extend(
            [
                p("Registro de decisión" if spanish else "Decision record", heading),
                p(
                    "Resultado: [ ] aceptar  [ ] solicitar evidencia  [ ] rechazar  [ ] diferir"
                    if spanish
                    else "Outcome: [ ] accept  [ ] request evidence  [ ] reject  [ ] defer",
                    small,
                ),
                p(
                    "Revisor / fecha / evidencia: _________________________________________________"
                    if spanish
                    else "Reviewer / date / acceptance evidence: __________________________________________",
                    small,
                ),
                Spacer(1, .03 * inch),
                p(
                    "La evidencia completa permanece en los artefactos estructurados; esta hoja no constituye aceptación del cliente."
                    if spanish
                    else "Full retained evidence remains in the structured artifacts; this worksheet is not client acceptance.",
                    small,
                ),
            ]
        )
        if section_index < len(sections) - 1:
            story.append(PageBreak())

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.55 * inch,
        rightMargin=.55 * inch,
        topMargin=.48 * inch,
        bottomMargin=.58 * inch,
        invariant=1,
        title="NICO Comprehensive Client Review Companion",
        author="NICO",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


__all__ = [
    "MAX_CLIENT_REVIEW_PAGES",
    "MIN_CLIENT_REVIEW_PAGES",
    "VERSION",
    "merge_review_companion_markdown",
    "render_comprehensive_review_companion_pdf",
    "review_sections",
]
