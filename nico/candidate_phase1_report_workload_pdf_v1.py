from __future__ import annotations

import html
import io
from typing import Any, Mapping

VERSION = "nico.candidate-phase1-report-workload-pdf.v1"
_HEAVY = {"pdf_base64", "html", "markdown", "scanner_results", "raw_output", "stdout", "stderr"}


def _text(value: Any, limit: int = 3000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _find(node: Any, name: str, depth: int = 0) -> Mapping[str, Any]:
    if depth > 10:
        return {}
    if isinstance(node, Mapping):
        direct = node.get(name)
        if isinstance(direct, Mapping):
            return direct
        for key, value in node.items():
            if str(key).casefold() in _HEAVY:
                continue
            found = _find(value, name, depth + 1)
            if found:
                return found
    elif isinstance(node, list) and len(node) <= 500:
        for value in node:
            found = _find(value, name, depth + 1)
            if found:
                return found
    return {}


def render_phase1_evidence_review_gate_pdf(
    canonical: Mapping[str, Any],
    register: Mapping[str, Any],
    *,
    spanish: bool,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from nico import comprehensive_client_ready_projection_v1 as projection

    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}
    technical_score = assessment.get("technical_score", maturity.get("technical_score", maturity.get("score")))
    adjusted_score = assessment.get("canonical_evidence_adjusted_score", assessment.get("evidence_adjusted_score"))
    scanners = [item for item in canonical.get("scanner_execution_records") or [] if isinstance(item, Mapping)]
    completed_scanners = sum(1 for item in scanners if item.get("completed") is True)
    review, _, categories = projection._candidate_summary(canonical)
    triage = _find(canonical, "technical_triage")
    metrics = triage.get("workload_metrics") if isinstance(triage.get("workload_metrics"), Mapping) else {}
    total = _integer(metrics.get("total_candidates")) or review
    completed = _integer(metrics.get("technical_triage_completed"))
    coverage = metrics.get("technical_triage_coverage_pct", 0)
    individual = _integer(metrics.get("candidates_requiring_individual_human_attention"))
    grouped_candidates = _integer(metrics.get("grouped_human_review_candidate_count"))
    grouped_clusters = _integer(metrics.get("grouped_review_cluster_count"))
    work_units = _integer(metrics.get("human_review_work_units"))
    stable = _integer(metrics.get("stable_carry_forward_count"))
    fresh = _integer(triage.get("fresh_technical_triage_completed"))
    qc_pool = _integer(metrics.get("quality_control_sample_pool"))
    exact_findings = _integer((register.get("summary") or {}).get("exact_source_code_finding_count"))

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("P1-H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=colors.HexColor("#0f172a"), spaceAfter=9)
    h2 = ParagraphStyle("P1-H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=colors.HexColor("#075985"), spaceBefore=5, spaceAfter=4)
    body = ParagraphStyle("P1-Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.2, leading=10.8, textColor=colors.HexColor("#334155"), spaceAfter=4)
    small = ParagraphStyle("P1-Small", parent=body, fontSize=7, leading=8.8)
    warning = ParagraphStyle("P1-Warning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=.7, borderPadding=7, spaceAfter=7)

    def p(
        value: Any,
        style: ParagraphStyle = body,
        *,
        client_literal: bool = False,
    ) -> Paragraph:
        if client_literal:
            from nico.comprehensive_engagement_metadata_v1 import reportlab_literal_markup

            return Paragraph(reportlab_literal_markup(value, 4000), style)
        else:
            rendered = _text(value)
        return Paragraph(html.escape(rendered), style)

    def table(
        rows: list[list[Any]],
        widths: list[float],
        *,
        client_literal_rows: set[int] | None = None,
    ) -> Table:
        literal_rows = client_literal_rows or set()
        value = Table(
            [
                [
                    p(
                        cell,
                        small,
                        client_literal=row_index in literal_rows and column_index == 1,
                    )
                    for column_index, cell in enumerate(row)
                ]
                for row_index, row in enumerate(rows)
            ],
            colWidths=widths,
            repeatRows=1,
        )
        value.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return value

    boundary = projection.ES_BOUNDARY if spanish else projection.EN_BOUNDARY
    from nico.comprehensive_engagement_metadata_v1 import _literal

    def engagement_value(key: str) -> str:
        value = _literal(identity.get(key), 4000)
        return value or ("No proporcionado" if spanish else "Not supplied")

    labels = (
        {
            "field": "Campo",
            "value": "Valor",
            "repository": "Repositorio",
            "client_name": "Nombre del cliente",
            "project_name": "Nombre del proyecto",
            "primary_technical_contact": "Contacto técnico principal",
            "access_method": "Método de acceso",
            "authorized_scope": "Alcance autorizado",
            "exact_commit": "Commit exacto",
            "run_id": "ID de ejecución",
            "technical_maturity": "Madurez técnica",
            "evidence_adjusted": "Ajuste por evidencia",
            "reviewer_workload": "Métrica de carga del revisor",
            "stable": "Arrastre estable",
            "fresh": "Nuevo triaje técnico",
            "individual": "Candidatos que requieren atención individual",
            "grouped_candidates": "Candidatos cubiertos por revisión agrupada",
            "grouped_clusters": "Grupos para revisión humana conjunta",
            "work_units": "Unidades de trabajo de revisión humana",
            "qc_pool": "Conjunto de muestra para control de calidad",
            "category": "Categoría",
            "raw": "Bruto",
            "confirmed": "Confirmado",
            "review_required": "Requiere revisión",
            "state": "Estado",
            "candidate_state": "Estado canónico de candidatos",
            "client_boundary": "Límite del paquete del cliente",
            "exact_findings": "Hallazgos con fuente exacta en el índice",
        }
        if spanish
        else {
            "field": "Field",
            "value": "Value",
            "repository": "Repository",
            "client_name": "Client name",
            "project_name": "Project name",
            "primary_technical_contact": "Primary technical contact",
            "access_method": "Access method",
            "authorized_scope": "Authorized scope",
            "exact_commit": "Exact commit",
            "run_id": "Run ID",
            "technical_maturity": "Technical maturity",
            "evidence_adjusted": "Evidence-Adjusted",
            "reviewer_workload": "Reviewer workload metric",
            "stable": "Stable carry-forward",
            "fresh": "Fresh technical triage",
            "individual": "Candidates requiring individual attention",
            "grouped_candidates": "Candidates covered by grouped review",
            "grouped_clusters": "Grouped human-review clusters",
            "work_units": "Human review work units",
            "qc_pool": "Quality-control sample pool",
            "category": "Category",
            "raw": "Raw",
            "confirmed": "Confirmed",
            "review_required": "Review required",
            "state": "State",
            "candidate_state": "Canonical candidate state",
            "client_boundary": "Client package boundary",
            "exact_findings": "Exact-source findings in index",
        }
    )
    story: list[Any] = [
        p("Resumen de evidencia del cliente" if spanish else "Client Evidence Summary", h1),
        p(boundary, warning),
        table(
            [
                [labels["field"], labels["value"]],
                [labels["client_name"], engagement_value("customer_name")],
                [labels["project_name"], engagement_value("project_name")],
                [labels["primary_technical_contact"], engagement_value("primary_technical_contact")],
                [labels["access_method"], engagement_value("access_method")],
                [labels["authorized_scope"], engagement_value("authorized_scope")],
                [labels["repository"], _text(identity.get("repository"))],
                [labels["exact_commit"], _text(identity.get("commit_sha"))],
                [labels["run_id"], _text(identity.get("run_id"))],
                [labels["technical_maturity"], f"{int(technical_score)}/100" if isinstance(technical_score, (int, float)) else ("SIN PUNTUACIÓN" if spanish else "NOT SCORED")],
                [labels["evidence_adjusted"], f"{int(adjusted_score)}/100" if isinstance(adjusted_score, (int, float)) else ("SIN PUNTUACIÓN" if spanish else "NOT SCORED")],
            ],
            [1.55 * inch, 5.85 * inch],
            client_literal_rows={1, 2, 3, 4, 5},
        ),
        p("El triaje técnico y la disposición humana están separados" if spanish else "Technical triage and human disposition are separate", h2),
        p(
            (
                f"{'Se completó' if len(scanners) == 1 else 'Se completaron'} {completed_scanners} de {len(scanners)} {'analizador' if len(scanners) == 1 else 'analizadores'}. NICO completó el triaje técnico para {completed} de {total} {'candidato' if total == 1 else 'candidatos'} ({coverage}%). Las disposiciones humanas siguen pendientes; completar el triaje técnico no equivale a aprobación humana."
                if spanish
                else f"{completed_scanners} of {len(scanners)} applicable scanner executions completed. NICO completed automated technical triage for {completed} of {total} candidates ({coverage}%). Human dispositions remain pending; technical triage completion does not equal human approval."
            )
        ),
        p("Carga de revisión por excepción" if spanish else "Review-by-exception workload", h2),
        table(
            [
                [labels["reviewer_workload"], labels["value"]],
                [labels["stable"], stable],
                [labels["fresh"], fresh],
                [labels["individual"], individual],
                [labels["grouped_candidates"], grouped_candidates],
                [labels["grouped_clusters"], grouped_clusters],
                [labels["work_units"], work_units],
                [labels["qc_pool"], qc_pool],
            ],
            [5.75 * inch, 1.65 * inch],
        ),
    ]
    if categories:
        rows = [[labels["category"], labels["raw"], labels["confirmed"], labels["review_required"], labels["state"]]]
        spanish_categories = {
            "dependency": "Dependencias",
            "secret": "Secretos",
            "static": "Análisis estático",
            "code": "Código",
            "operational": "Operativa",
            "test": "Pruebas",
        }
        for category, counts in categories.items():
            rows.append([
                spanish_categories.get(str(category).casefold(), str(category))
                if spanish
                else str(category).title(),
                _integer(counts.get("raw")),
                _integer(counts.get("material")),
                _integer(counts.get("review_required")),
                "Disposición humana pendiente; triaje técnico de NICO completo"
                if spanish
                else "Human disposition pending; NICO technical triage complete",
            ])
        story.extend([p(labels["candidate_state"], h2), table(rows, [1.05 * inch, .55 * inch, .75 * inch, .9 * inch, 4.15 * inch])])
    story.extend([
        p(labels["client_boundary"], h2),
        p(
            "La evidencia completa de candidatos, la pertenencia determinista a grupos, los hashes de analizadores y los datos de remediación listos para exportar permanecen en JSON y CSV canónicos. Los resúmenes de grupo nunca sustituyen los ID ni la evidencia de los candidatos subyacentes."
            if spanish
            else "Full candidate evidence, deterministic cluster membership, scanner hashes, and export-ready remediation data remain in canonical JSON and CSV. Group summaries never replace underlying candidate IDs or evidence."
        ),
        p(f"{labels['exact_findings']}: {exact_findings}", small),
        PageBreak(),
        p("Puerta de revisión humana y aceptación" if spanish else "Human Review and Acceptance Gate", h1),
        p(boundary, warning),
    ])
    checklist = (
        [
            "Verificar identidades de repositorio, ejecución, commit, evidencia, cliente y proyecto.",
            "Revisar individualmente candidatos críticos o ambiguos y revisar grupos homogéneos elegibles como unidades agrupadas; conservar una disposición humana explícita para cada candidato subyacente.",
            "Aplicar muestreo profesional al conjunto de control de calidad y ampliar cualquier grupo cuya evidencia no sea homogénea.",
            "Confirmar puntuaciones, aseguramiento, limitaciones y entrega en JSON, CSV, Markdown, HTML y PDF.",
            "Disponer riesgos ejecutivos y registrar riesgo residual, responsable y evidencia de aceptación.",
            "Aprobar o rechazar este borrador inmutable antes de autorizar la entrega.",
        ]
        if spanish
        else [
            "Verify repository, run, commit, evidence-ledger, customer, and project identities.",
            "Individually review critical or ambiguous candidates and review eligible homogeneous clusters as grouped work units; retain an explicit human disposition for every underlying candidate.",
            "Apply professional spot-check sampling to the quality-control pool and expand any cluster whose evidence is not homogeneous.",
            "Confirm technical score, Evidence-Adjusted score, assurance state, limitations, and delivery status across JSON, CSV, Markdown, HTML, and PDF.",
            "Disposition every executive risk and record residual risk, owner, and acceptance evidence.",
            "Approve or reject this exact immutable automated draft before authorizing client delivery.",
        ]
    )
    for index, item in enumerate(checklist, 1):
        story.append(p(f"{index}. {item}"))
    story.extend([
        Spacer(1, .1 * inch),
        p(
            "Solo un revisor humano autorizado puede aprobar los artefactos inmutables exactos. La entrega al cliente requiere una acción autorizada independiente."
            if spanish
            else "Only an authorized human reviewer may approve the exact immutable artifacts. Client delivery requires a separate authorized action.",
            warning,
        ),
    ])
    SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.55 * inch,
        rightMargin=.55 * inch,
        topMargin=.55 * inch,
        bottomMargin=.6 * inch,
        invariant=1,
        title="NICO Client Evidence and Review Gate",
        author="NICO",
    ).build(story)
    return buffer.getvalue()


__all__ = ["VERSION", "render_phase1_evidence_review_gate_pdf"]
