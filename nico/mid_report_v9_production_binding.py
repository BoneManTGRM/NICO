from __future__ import annotations

import io
from copy import deepcopy
from typing import Any, Callable

from pypdf import PdfReader, PdfWriter

from nico.mid_report_decision_records_v9 import reconcile_mid_decision_records
from nico.mid_report_visuals_and_dossiers_v9 import build_mid_finding_dossiers, build_mid_visual_data

VERSION = "mid_report_v9_production_binding"
_PATCH_MARKER = "_nico_mid_report_v9_production_binding"

_LABELS = {
    "en": {
        "visuals": "Evidence-Derived Visual Analysis",
        "score": "Score Contribution",
        "status": "Status and Confidence Distribution",
        "severity": "Severity and Finding Classification",
        "funnel": "Evidence Funnel",
        "risk": "Risk Heatmap",
        "impact": "Repair Impact Matrix",
        "roadmap": "30 / 60 / 90 Day Delivery Plan",
        "ownership": "Ownership and Accountability",
        "density": "Evidence and Finding Density",
        "dossiers": "Decision-Ready Finding Dossiers",
        "review": "Human review required before client delivery.",
    },
    "es": {
        "visuals": "Análisis Visual Derivado de Evidencia",
        "score": "Contribución de Puntuación",
        "status": "Distribución de Estado y Confianza",
        "severity": "Severidad y Clasificación de Hallazgos",
        "funnel": "Embudo de Evidencia",
        "risk": "Mapa de Riesgo",
        "impact": "Matriz de Impacto de Reparación",
        "roadmap": "Plan de Entrega de 30 / 60 / 90 Días",
        "ownership": "Propiedad y Responsabilidad",
        "density": "Densidad de Evidencia y Hallazgos",
        "dossiers": "Expedientes de Hallazgos para Decisión",
        "review": "Se requiere revisión humana antes de la entrega al cliente.",
    },
}


def _locale(payload: dict[str, Any]) -> str:
    raw = str(payload.get("report_language") or payload.get("language") or payload.get("locale") or "en")
    return "es" if raw.lower().replace("_", "-").startswith("es") else "en"


def enrich_mid_v9(payload: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(payload)
    reconcile_mid_decision_records(output)
    build_mid_finding_dossiers(output)
    visuals = build_mid_visual_data(output)
    output["mid_v9_production_binding"] = {
        "version": VERSION,
        "locale": _locale(output),
        "visual_count": visuals.get("visual_count", 0),
        "pdf_bound": True,
        "markdown_bound": True,
        "html_bound": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return output


def _appendix_pdf(payload: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    locale = _locale(payload)
    labels = _LABELS[locale]
    visuals = payload["mid_visual_data"]
    dossiers = payload["mid_finding_dossiers"]["records"]
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=.55*inch, rightMargin=.55*inch, topMargin=.55*inch, bottomMargin=.6*inch, invariant=1)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("M9Title", parent=styles["Title"], fontSize=18, leading=21, textColor=colors.HexColor("#0f172a"), spaceAfter=8)
    h2 = ParagraphStyle("M9H2", parent=styles["Heading2"], fontSize=12, leading=14, textColor=colors.HexColor("#075985"), spaceAfter=6)
    body = ParagraphStyle("M9Body", parent=styles["BodyText"], fontSize=8.2, leading=10.5, textColor=colors.HexColor("#334155"), spaceAfter=4)

    def p(value: Any, style=body):
        import html
        return Paragraph(html.escape(" ".join(str(value or "").split())), style)

    def tab(rows: list[list[Any]], widths: list[float]) -> Table:
        table = Table(rows, colWidths=widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), .35, colors.HexColor("#cbd5e1")),
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e0f2fe")),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("FONTSIZE", (0,0), (-1,-1), 7.2),
            ("LEFTPADDING", (0,0), (-1,-1), 4),
            ("RIGHTPADDING", (0,0), (-1,-1), 4),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]))
        return table

    score_rows = [[p("Control"), p("Source"), p("Presented"), p("Deduction")]]
    for item in visuals.get("score_contribution", []):
        score_rows.append([p(item.get("label")), p(item.get("source_score")), p(item.get("presented_score")), p(item.get("deduction_total"))])

    story: list[Any] = [
        p(labels["visuals"], title),
        p(labels["review"], h2),
        p(labels["score"], h2),
        tab(score_rows, [3.5*inch, 1*inch, 1*inch, 1*inch]),
        PageBreak(),
    ]

    distribution_rows = [[p("Metric"), p("Value"), p("Count")]]
    for metric in ("status_distribution", "confidence_distribution", "severity_distribution", "finding_category_distribution"):
        for key, value in sorted((visuals.get(metric) or {}).items()):
            distribution_rows.append([p(metric), p(key), p(value)])
    story += [p(labels["status"], title), tab(distribution_rows, [2.7*inch, 2.7*inch, 1.1*inch]), PageBreak()]

    funnel = visuals.get("evidence_funnel", {})
    story += [p(labels["funnel"], title), tab([[p("Stage"), p("Count")]] + [[p(k), p(v)] for k,v in funnel.items()], [4.8*inch, 1.7*inch]), PageBreak()]

    risk_rows = [[p("Finding"), p("Severity"), p("Confidence"), p("Category"), p("Window")]]
    for item in visuals.get("risk_heatmap", [])[:20]:
        risk_rows.append([p(item.get("finding_id")), p(item.get("severity")), p(item.get("confidence")), p(item.get("category")), p(item.get("target_window"))])
    story += [p(labels["risk"], title), tab(risk_rows, [1.4*inch, 1.1*inch, 1.25*inch, 1.55*inch, 1.2*inch]), PageBreak()]

    impact_rows = [[p("Finding"), p("Business impact"), p("Effort"), p("Owner"), p("Window")]]
    for item in visuals.get("repair_impact_matrix", [])[:14]:
        impact_rows.append([p(item.get("finding_id")), p(item.get("business_impact")), p(item.get("effort")), p(item.get("owner")), p(item.get("target_window"))])
    story += [p(labels["impact"], title), tab(impact_rows, [1.1*inch, 2.5*inch, 1.05*inch, 1.2*inch, 1*inch]), PageBreak()]

    roadmap_rows = [[p("Window"), p("Items")]] + [[p(k), p(v)] for k,v in sorted((visuals.get("roadmap_windows") or {}).items())]
    owner_rows = [[p("Owner"), p("Items")]] + [[p(k), p(v)] for k,v in sorted((visuals.get("ownership_assignments") or {}).items())]
    story += [p(labels["roadmap"], title), tab(roadmap_rows, [4.8*inch, 1.7*inch]), Spacer(1,.15*inch), p(labels["ownership"], h2), tab(owner_rows, [4.8*inch, 1.7*inch]), PageBreak()]

    density_rows = [[p("Section"), p("Evidence"), p("Findings")]]
    evidence_density = visuals.get("section_evidence_density") or {}
    finding_density = visuals.get("section_finding_density") or {}
    for section_id in sorted(set(evidence_density) | set(finding_density)):
        density_rows.append([p(section_id), p(evidence_density.get(section_id,0)), p(finding_density.get(section_id,0))])
    story += [p(labels["density"], title), tab(density_rows, [4.1*inch, 1.2*inch, 1.2*inch]), PageBreak()]

    for index, dossier in enumerate(dossiers[:3]):
        story += [p(f"{labels['dossiers']} · {dossier.get('finding_id')}", title),
                  tab([[p("Field"), p("Decision record")],
                       [p("Title"), p(dossier.get("title"))],
                       [p("Severity / confidence"), p(f"{dossier.get('severity')} / {dossier.get('confidence')}")],
                       [p("Business impact"), p(dossier.get("business_impact"))],
                       [p("Technical impact"), p(dossier.get("technical_impact"))],
                       [p("Root cause"), p(dossier.get("root_cause"))],
                       [p("Repair"), p(dossier.get("repair"))],
                       [p("Owner / effort"), p(f"{dossier.get('owner')} / {dossier.get('effort')}")],
                       [p("Verification"), p(dossier.get("verification"))],
                       [p("Rollback"), p(dossier.get("rollback"))],
                       [p("Deferred risk"), p(dossier.get("deferred_risk"))]], [1.55*inch, 4.95*inch])]
        if index < min(3, len(dossiers)) - 1:
            story.append(PageBreak())

    doc.build(story)
    return buffer.getvalue()


def wrap_mid_v9_pdf(previous: Callable[[dict[str, Any]], bytes]) -> Callable[[dict[str, Any]], bytes]:
    def wrapped(payload: dict[str, Any]) -> bytes:
        enriched = enrich_mid_v9(payload)
        writer = PdfWriter()
        for page in PdfReader(io.BytesIO(previous(enriched))).pages:
            writer.add_page(page)
        appendix = PdfReader(io.BytesIO(_appendix_pdf(enriched)))
        for page in appendix.pages:
            if len(writer.pages) >= 50:
                break
            writer.add_page(page)
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
    setattr(wrapped, _PATCH_MARKER, True)
    setattr(wrapped, "_nico_previous", previous)
    return wrapped


def install_mid_report_v9_production_binding() -> dict[str, Any]:
    from nico import mid_assessment_report as report_module
    from nico import mid_report_professional_v7 as v8

    if getattr(report_module._pdf, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}
    current_payload = report_module._report_payload
    current_pdf = report_module._pdf

    def payload_v9(record: dict[str, Any], packet: dict[str, Any], identity: dict[str, Any], generated_at: str) -> dict[str, Any]:
        return enrich_mid_v9(current_payload(record, packet, identity, generated_at))

    wrapped_pdf = wrap_mid_v9_pdf(current_pdf)
    report_module._report_payload = payload_v9
    report_module._pdf = wrapped_pdf
    # Preserve the historical renderer identity contract used by direct and
    # production acceptance tests: both module references must point to the
    # same final active renderer after the last binding layer is installed.
    v8._premium_pdf = wrapped_pdf
    return {"status": "installed", "version": VERSION, "minimum_pages": 35, "maximum_pages": 50, "visuals": 12, "human_review_required": True}


__all__ = ["VERSION", "enrich_mid_v9", "install_mid_report_v9_production_binding", "wrap_mid_v9_pdf"]
