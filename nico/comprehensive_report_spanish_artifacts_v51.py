from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import re
from copy import deepcopy
from typing import Any

from nico.comprehensive_report_scanner_detection_v51 import _text
from nico.comprehensive_report_spanish_text_v51 import _es, _spanish_markdown
from nico.comprehensive_spanish_canonical_report_v87 import (
    render_spanish_html as _canonical_spanish_html,
    render_spanish_markdown as _canonical_spanish_markdown,
    render_spanish_pdf as _canonical_spanish_pdf,
)

VERSION = "nico.comprehensive_report_spanish_artifacts.v51"

def _spanish_html(markdown: str, title: str) -> str:
    rows = markdown.splitlines()
    blocks: list[str] = []
    index = 0
    while index < len(rows):
        line = rows[index].rstrip()
        if line.startswith("| ") and index + 1 < len(rows) and rows[index + 1].startswith("|"):
            header = [cell.strip() for cell in line.strip("|").split("|")]
            index += 2
            body_rows: list[list[str]] = []
            while index < len(rows) and rows[index].startswith("|"):
                body_rows.append([cell.strip() for cell in rows[index].strip("|").split("|")])
                index += 1
            blocks.append("<table><thead><tr>" + "".join(f"<th>{html.escape(cell)}</th>" for cell in header) + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>" for row in body_rows) + "</tbody></table>")
            continue
        if line.startswith("### "):
            blocks.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            blocks.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            blocks.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("- "):
            blocks.append(f"<p class='bullet'>• {html.escape(line[2:])}</p>")
        elif line.startswith("**") and line.endswith("**"):
            blocks.append(f"<p class='warning'>{html.escape(line.strip('*'))}</p>")
        elif line.startswith("<!--"):
            blocks.append(line)
        elif line.strip():
            blocks.append(f"<p>{html.escape(line)}</p>")
        index += 1
    return f"""<!doctype html><html lang='es-MX'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>body{{font:15px/1.55 Inter,system-ui,sans-serif;margin:0;background:#071124;color:#dbeafe}}main{{max-width:1120px;margin:auto;padding:36px 22px 80px}}article{{background:#0b172c;border:1px solid #274060;border-radius:24px;padding:28px}}h1{{font-size:38px;color:#fff}}h2{{color:#7dd3fc;border-top:1px solid #274060;padding-top:24px;margin-top:34px}}h3{{color:#e0f2fe}}p{{color:#cbd5e1}}table{{width:100%;border-collapse:collapse;margin:18px 0;font-size:13px}}th,td{{border:1px solid #315070;padding:8px;vertical-align:top}}th{{background:#075985;color:white}}.warning{{background:#4a2406;border:1px solid #f59e0b;padding:14px;border-radius:12px;color:#fde68a;font-weight:800}}.bullet{{margin:4px 0 4px 18px}}</style></head><body><main><article>{''.join(blocks)}</article></main></body></html>"""


def _spanish_pdf(canonical: dict[str, Any]) -> tuple[bytes, int]:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("ES-Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=28, leading=32, alignment=TA_CENTER, textColor=colors.HexColor("#0f172a"))
    h1 = ParagraphStyle("ES-H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor("#075985"), spaceBefore=10, spaceAfter=8)
    h2 = ParagraphStyle("ES-H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=5)
    body = ParagraphStyle("ES-Body", parent=styles["BodyText"], fontSize=8.5, leading=12, textColor=colors.HexColor("#334155"), spaceAfter=5)
    small = ParagraphStyle("ES-Small", parent=body, fontSize=7, leading=9.2)
    warning = ParagraphStyle("ES-Warning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=.8, borderPadding=8)

    identity = canonical.get("identity") if isinstance(canonical.get("identity"), dict) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    sections = [item for item in assessment.get("sections") or [] if isinstance(item, dict)]
    findings = [item for item in canonical.get("findings_register") or [] if isinstance(item, dict)]
    stages = [item for item in canonical.get("stage_summaries") or [] if isinstance(item, dict)]
    roadmap = [item for item in canonical.get("roadmap") or [] if isinstance(item, dict)]
    staffing = [item for item in canonical.get("staffing_plan") or [] if isinstance(item, dict)]
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    technical = assessment.get("technical_score", maturity.get("score"))
    adjusted = assessment.get("canonical_evidence_adjusted_score", assessment.get("evidence_adjusted_score"))
    health = assessment.get("evidence_health_summary") if isinstance(assessment.get("evidence_health_summary"), dict) else {}

    def p(value: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(html.escape(_es(value)), style)

    def table(headers: list[str], rows: list[list[Any]], widths: list[float]) -> LongTable:
        data = [[p(cell, small) for cell in headers]] + [[p(cell, small) for cell in row] for row in rows]
        result = LongTable(data, colWidths=widths, repeatRows=1, splitByRow=1)
        result.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#075985")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return result

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(.55 * inch, .35 * inch, f"NICO Integral · {_text(identity.get('run_id'), 34)} · {_text(identity.get('commit_sha'), 12)}")
        canvas.drawRightString(7.95 * inch, .35 * inch, f"Página {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=.55 * inch, rightMargin=.55 * inch, topMargin=.55 * inch, bottomMargin=.6 * inch, title="Evaluación Técnica Integral NICO", author="NICO", invariant=1)
    story: list[Any] = [
        Spacer(1, 1.0 * inch),
        p("NICO", ParagraphStyle("ES-Brand", parent=title, fontSize=19, textColor=colors.HexColor("#0284c7"))),
        p("Evaluación Técnica Integral", title),
        p("Informe técnico para decisiones", ParagraphStyle("ES-Sub", parent=body, alignment=TA_CENTER, fontSize=12)),
        Spacer(1, .25 * inch),
        p(identity.get("repository"), ParagraphStyle("ES-Repo", parent=body, alignment=TA_CENTER, fontName="Helvetica-Bold", fontSize=13)),
        p(f"Commit inmutable: {_text(identity.get('commit_sha'))}", ParagraphStyle("ES-Meta", parent=small, alignment=TA_CENTER)),
        p(f"ID de ejecución: {_text(identity.get('run_id'))}", ParagraphStyle("ES-Meta2", parent=small, alignment=TA_CENTER)),
        Spacer(1, .35 * inch),
        table(
            ["MADUREZ TÉCNICA", "AJUSTE POR EVIDENCIA", "REVISIÓN", "ENTREGA"],
            [[f"{technical}/100" if isinstance(technical, (int, float)) else "S/P", f"{adjusted}/100" if isinstance(adjusted, (int, float)) else "S/P", "REQUERIDA", "BORRADOR"]],
            [1.85 * inch] * 4,
        ),
        Spacer(1, .35 * inch),
        p("ENTREGA AL CLIENTE BLOQUEADA HASTA LA APROBACIÓN HUMANA DEL PAQUETE EXACTO", warning),
        PageBreak(),
        p("Resumen ejecutivo para decisiones", h1),
        p(assessment.get("executive_summary") or "La evaluación automatizada terminó y conserva las limitaciones de evidencia de forma explícita."),
        p("Estado de la evaluación", h2),
        table(
            ["Dimensión", "Resultado"],
            [
                ["Ejecución de la evaluación", "COMPLETA"],
                ["Generación de artefactos", "COMPLETA"],
                ["Ejecución de analizadores", "PARCIAL" if health.get("incomplete_scanners") else "COMPLETA"],
                ["Aprobación", "PENDIENTE DE REVISIÓN HUMANA"],
                ["Entrega al cliente", "BLOQUEADA"],
            ],
            [2.4 * inch, 5.0 * inch],
        ),
        PageBreak(),
        p("Cuadro de puntuación técnica", h1),
        table(
            ["Control", "Puntuación", "Ejecución", "Garantía"],
            [[section.get("label") or section.get("id"), f"{section.get('score_value')}/100" if isinstance(section.get("score_value"), (int, float)) else "SIN PUNTUACIÓN", str(section.get("execution_status") or "pendiente").upper(), section.get("assurance_label") or "REVISIÓN LIMITADA"] for section in sections],
            [2.4 * inch, 1.1 * inch, 1.3 * inch, 2.6 * inch],
        ),
        p("La existencia de hallazgos abiertos no convierte una ejecución de evidencia completa en incompleta. La ejecución, la garantía, la disposición de hallazgos y la aprobación se presentan por separado.", body),
        PageBreak(),
        p("Salud de la evidencia", h1),
        p(health.get("confidence_effect") or "Las limitaciones se aplican únicamente a los controles afectados."),
        table(
            ["Analizador", "Estado", "Requerido", "Control afectado", "Remediación"],
            [[item.get("scanner_name") or item.get("scanner"), str(item.get("status") or "desconocido").upper(), "Sí" if item.get("required") else "No", ", ".join(item.get("score_controls_affected") or item.get("affected_controls") or []), item.get("remediation_guidance") or item.get("remediation") or "Ninguna"] for item in assessment.get("scanner_execution_records") or health.get("incomplete_scanners") or [] if isinstance(item, dict)],
            [1.05 * inch, .75 * inch, .55 * inch, 1.2 * inch, 3.85 * inch],
        ),
    ]

    if findings:
        story += [PageBreak(), p("Registro detallado de hallazgos", h1)]
        for index, finding in enumerate(findings):
            story += [
                p(f"{finding.get('priority') or 'P2'} · {_es(finding.get('title'))} · {finding.get('finding_id') or finding.get('id')}", h2),
                table(
                    ["Campo", "Detalle"],
                    [
                        ["Categoría / estado", f"{_es(finding.get('category'))} · {_es(finding.get('status'))}"],
                        ["Ubicación", _text(finding.get("location"))],
                        ["Hecho observado", _es(finding.get("fact") or finding.get("evidence"))],
                        ["Interpretación", _es(finding.get("interpretation"))],
                        ["Impacto empresarial", _es(finding.get("business_impact") or finding.get("impact"))],
                        ["Recomendación", _es(finding.get("recommendation"))],
                        ["Responsable / esfuerzo", f"{_es(finding.get('owner_role'))} · {_text(finding.get('effort'))}"],
                        ["Costo de no actuar", _es(finding.get("cost_of_inaction"))],
                        ["Riesgo residual", _es(finding.get("residual_risk"))],
                    ],
                    [1.55 * inch, 5.85 * inch],
                ),
            ]
            if index and index % 5 == 0:
                story.append(PageBreak())

    story += [PageBreak(), p("Hoja de ruta de seis meses", h1)]
    for window in roadmap:
        story.append(p(f"{_es(window.get('window'))} — {_es(window.get('objective'))}", h2))
        packages = [item for item in window.get("work_packages") or [] if isinstance(item, dict)]
        if packages:
            story.append(table(
                ["ID / paquete", "Responsable", "Esfuerzo", "Aceptación / impacto"],
                [[package.get("work_package_id") or package.get("id"), package.get("owner_role") or package.get("owner"), package.get("effort") or package.get("effort_range"), f"{_es('; '.join(str(item) for item in package.get('acceptance_criteria') or []))} {_es(package.get('expected_impact'))}"] for package in packages],
                [1.65 * inch, 1.45 * inch, .8 * inch, 3.5 * inch],
            ))

    story += [PageBreak(), p("Personal y secuencia", h1)]
    story.append(table(
        ["Secuencia", "Rol", "Enfoque", "Capacidad indicativa"],
        [[item.get("sequence"), item.get("role"), item.get("focus"), item.get("indicative_capacity") or item.get("capacity")] for item in staffing],
        [.65 * inch, 1.65 * inch, 3.7 * inch, 1.4 * inch],
    ))

    story += [p("Límites de alcance y riesgo no evaluado", h1)]
    boundaries = [item for item in assessment.get("scope_boundaries") or [] if isinstance(item, dict)]
    if boundaries:
        story.append(table(["Área", "Límite"], [[item.get("area"), item.get("boundary")] for item in boundaries], [2.0 * inch, 5.4 * inch]))

    story += [PageBreak(), p("Apéndice de evidencia", h1)]
    for stage in stages:
        story += [p(f"{_es(stage.get('title'))} — {_es(str(stage.get('status') or '').upper())}", h2), p(stage.get("summary"))]
        for label, field in (("Evidencia conservada", "evidence"), ("Hallazgos", "findings"), ("Evidencia no disponible o limitada", "unavailable")):
            values = stage.get(field) or []
            if values:
                story.append(p(label, ParagraphStyle(f"ES-{label}-{id(stage)}", parent=small, fontName="Helvetica-Bold")))
                story.extend(p(f"• {_es(item)}", small) for item in values)

    story += [PageBreak(), p("Puerta de revisión y aceptación humana", h1), p("La evaluación automatizada está completa como borrador. Antes de cualquier entrega al cliente, una persona autorizada debe verificar las identidades exactas, disponer todos los hallazgos prioritarios, confirmar la coherencia entre formatos y aprobar o rechazar el paquete inmutable exacto."), p("ENTREGA AL CLIENTE BLOQUEADA · APROBACIÓN HUMANA PENDIENTE", warning)]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf = buffer.getvalue()
    try:
        from pypdf import PdfReader
        page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    except Exception:
        page_count = max(1, pdf.count(b"/Type /Page"))
    return pdf, page_count


def _localize_package(result: dict[str, Any]) -> dict[str, Any]:
    package = result.get("report_package") if isinstance(result.get("report_package"), dict) else {}
    if not package:
        return result
    canonical = deepcopy(package.get("json") if isinstance(package.get("json"), dict) else {})
    canonical["report_language"] = "es-MX"
    canonical["locale"] = "es-MX"
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    assessment["report_language"] = "es-MX"
    canonical["assessment"] = assessment
    markdown = _canonical_spanish_markdown(canonical)
    rendered_html = _canonical_spanish_html(
        markdown,
        "Evaluación Técnica Integral NICO",
    )
    pdf, page_count = _canonical_spanish_pdf(canonical)
    truth_sha = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
    safe_repo = re.sub(r"[^A-Za-z0-9_.-]+", "-", _text((canonical.get("identity") or {}).get("repository"))).strip("-") or "repositorio"
    run_id = _text((canonical.get("identity") or {}).get("run_id")) or "run"
    quality = dict(package.get("report_quality_contract") or {})
    quality.update(
        {
            "report_language": "es-MX",
            "spanish_markdown_complete": True,
            "spanish_html_complete": (
                '<html lang="es-MX">' in rendered_html
                or "<html lang='es-MX'>" in rendered_html
            ),
            "spanish_pdf_complete": pdf.startswith(b"%PDF"),
            "localized_client_artifacts_share_canonical_truth": True,
            "assessment_completion_separated_from_evidence_assurance": True,
            "per_control_assurance_present": True,
            "structured_scanner_completion_records_present": bool(assessment.get("scanner_execution_records")),
        }
    )
    package.update(
        {
            "markdown": markdown,
            "html": rendered_html,
            "json": canonical,
            "pdf_base64": base64.b64encode(pdf).decode("ascii"),
            "pdf_error": None,
            "pdf_filename": f"nico-evaluacion-tecnica-integral-{safe_repo}-{run_id}-es-MX-BORRADOR.pdf",
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "pdf_page_count": page_count,
            "core_report_page_count": page_count,
            "final_package_page_count": page_count,
            "canonical_truth_sha256": truth_sha,
            "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
            "report_language": "es-MX",
            "locale": "es-MX",
            "report_quality_contract": quality,
        }
    )
    result["report_package"] = package
    result["report_language"] = "es-MX"
    result["locale"] = "es-MX"
    return result



__all__ = ["VERSION", "_localize_package", "_spanish_html", "_spanish_pdf"]
