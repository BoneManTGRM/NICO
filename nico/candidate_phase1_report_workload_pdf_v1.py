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

    def p(value: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(html.escape(_text(value)), style)

    def table(rows: list[list[Any]], widths: list[float]) -> Table:
        value = Table([[p(cell, small) for cell in row] for row in rows], colWidths=widths, repeatRows=1)
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
    story: list[Any] = [
        p("Resumen de evidencia para revisión" if spanish else "Client Evidence Summary", h1),
        p(boundary, warning),
        table(
            [
                ["Field", "Value"],
                ["Repository", _text(identity.get("repository"))],
                ["Exact commit", _text(identity.get("commit_sha"))],
                ["Run ID", _text(identity.get("run_id"))],
                ["Technical maturity", f"{int(technical_score)}/100" if isinstance(technical_score, (int, float)) else "NOT SCORED"],
                ["Evidence-Adjusted", f"{int(adjusted_score)}/100" if isinstance(adjusted_score, (int, float)) else "NOT SCORED"],
            ],
            [1.55 * inch, 5.85 * inch],
        ),
        p("Triage técnico y disposición humana" if spanish else "Technical triage and human disposition are separate", h2),
        p(
            (
                f"Se completaron {completed_scanners} de {len(scanners)} analizadores. NICO completó triage técnico para {completed} de {total} candidatos ({coverage}%). Las disposiciones humanas siguen pendientes; completar el triage técnico no equivale a aprobación humana."
                if spanish
                else f"{completed_scanners} of {len(scanners)} applicable scanner executions completed. NICO completed automated technical triage for {completed} of {total} candidates ({coverage}%). Human dispositions remain pending; technical triage completion does not equal human approval."
            )
        ),
        p("Carga de revisión por excepción" if spanish else "Review-by-exception workload", h2),
        table(
            [
                ["Reviewer workload metric", "Value"],
                ["Stable carry-forward", stable],
                ["Fresh technical triage", fresh],
                ["Candidates requiring individual attention", individual],
                ["Candidates covered by grouped review", grouped_candidates],
                ["Grouped human-review clusters", grouped_clusters],
                ["Human review work units", work_units],
                ["Quality-control sample pool", qc_pool],
            ],
            [5.75 * inch, 1.65 * inch],
        ),
    ]
    if categories:
        rows = [["Category", "Raw", "Confirmed", "Review required", "State"]]
        for category, counts in categories.items():
            rows.append([
                str(category).title(),
                _integer(counts.get("raw")),
                _integer(counts.get("material")),
                _integer(counts.get("review_required")),
                "Human disposition pending; NICO technical triage complete",
            ])
        story.extend([p("Canonical candidate state", h2), table(rows, [1.05 * inch, .55 * inch, .75 * inch, .9 * inch, 4.15 * inch])])
    story.extend([
        p("Client package boundary", h2),
        p("Full candidate evidence, deterministic cluster membership, scanner hashes, and export-ready remediation data remain in canonical JSON and CSV. Group summaries never replace underlying candidate IDs or evidence."),
        p(f"Exact-source findings in index: {exact_findings}", small),
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
            "Solo un revisor autorizado puede cambiar el estado a FINAL APROBADO y ENTREGA AUTORIZADA."
            if spanish
            else "Only an authorized reviewer may change the status to APPROVED FINAL and CLIENT DELIVERY AUTHORIZED.",
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
