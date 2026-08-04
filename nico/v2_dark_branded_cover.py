from __future__ import annotations

import base64
import hashlib
import io
from copy import deepcopy
from typing import Any, Mapping

from nico.comprehensive_client_ready_projection_v1 import (
    EN_BOUNDARY,
    ES_BOUNDARY,
    clean_finding_title,
)

VERSION = "nico.v2.dark-branded-cover.v3.2"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _score_pair(assessment: Mapping[str, Any]) -> tuple[str, str]:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}
    technical = assessment.get("technical_score", maturity.get("technical_score", maturity.get("presented_score", maturity.get("score"))))
    adjusted = assessment.get("canonical_evidence_adjusted_score", assessment.get("evidence_adjusted_score", maturity.get("evidence_adjusted_score", technical)))
    technical_label = f"{int(round(technical))}/100" if isinstance(technical, (int, float)) and not isinstance(technical, bool) else "NOT SCORED"
    adjusted_label = f"{int(round(adjusted))}/100" if isinstance(adjusted, (int, float)) and not isinstance(adjusted, bool) else "NOT SCORED"
    return technical_label, adjusted_label


def _priority_titles(canonical: Mapping[str, Any]) -> list[str]:
    findings = [item for item in canonical.get("canonical_findings") or [] if isinstance(item, Mapping)]
    titles: list[str] = []
    for item in findings:
        title = clean_finding_title(item.get("decision_title") or item.get("title"))
        if title and title.casefold() not in {value.casefold() for value in titles}:
            titles.append(title)
        if len(titles) == 3:
            break
    return titles or ["No unresolved priority finding retained"]


def _executive_posture(canonical: Mapping[str, Any], technical: str, adjusted: str, *, spanish: bool) -> str:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    repository = _text(identity.get("repository"))
    if spanish:
        return (
            f"NICO generó un borrador automatizado de evaluación técnica integral para {repository}. "
            f"La madurez técnica ponderada es {technical} y la preparación ajustada por evidencia es {adjusted}. "
            "El paquete conserva salud del repositorio, hallazgos con ubicación exacta, evidencia de arquitectura, "
            "un marco de hoja de ruta y exportaciones estructuradas para revisión humana; no constituye aprobación ni autorización de entrega."
        )
    return (
        f"NICO generated an automated Comprehensive Technical Assessment draft for {repository}. "
        f"Weighted technical maturity is {technical}; independently evidence-adjusted readiness is {adjusted}. "
        "The evidence-bound package retains repository health, exact-location findings, architecture evidence, "
        "a roadmap framework, and structured exports for human review; it is not approval or client-delivery authorization."
    )


def _cover(canonical: Mapping[str, Any], *, spanish: bool) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    technical, adjusted = _score_pair(assessment)
    priorities = _priority_titles(canonical)
    width, height = letter
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)

    navy = colors.HexColor("#030817")
    panel = colors.HexColor("#0b1b34")
    border = colors.HexColor("#173f65")
    cyan = colors.HexColor("#38c7f2")
    teal = colors.HexColor("#35d5bf")
    muted = colors.HexColor("#9fb3ca")
    white = colors.white

    pdf.setFillColor(navy)
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setFillColor(cyan)
    pdf.rect(0, height - 8, width * 0.73, 8, fill=1, stroke=0)
    pdf.setFillColor(teal)
    pdf.rect(width * 0.73, height - 8, width * 0.27, 8, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#0b2942"))
    pdf.circle(width + 12, height - 35, 165, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#0a3b4b"))
    pdf.circle(5, -30, 125, fill=1, stroke=0)

    left = 42
    pdf.setFillColor(cyan)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawString(left, height - 42, "NICO / EVIDENCE-BOUND ENGINEERING INTELLIGENCE")
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 25)
    pdf.drawString(left, height - 88, "NICO COMPREHENSIVE")
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 11)
    pdf.drawString(
        left,
        height - 108,
        "Evidence-Bound Technical Review Package"
        if not spanish
        else "Paquete técnico basado en evidencia para revisión",
    )

    labels = [
        ("TECHNICAL MATURITY" if not spanish else "MADUREZ TÉCNICA", technical, cyan),
        ("EVIDENCE-ADJUSTED" if not spanish else "AJUSTE POR EVIDENCIA", adjusted, teal),
        ("HUMAN REVIEW" if not spanish else "REVISIÓN HUMANA", "Pending" if not spanish else "Pendiente", colors.HexColor("#f5a623")),
        ("CLIENT DELIVERY" if not spanish else "ENTREGA AL CLIENTE", "Blocked" if not spanish else "Bloqueada", colors.HexColor("#d95df5")),
    ]
    gap = 9
    card_w = (width - 84 - gap * 3) / 4
    y = height - 182
    for index, (label, value, accent) in enumerate(labels):
        x = left + index * (card_w + gap)
        pdf.setFillColor(panel)
        pdf.setStrokeColor(border)
        pdf.roundRect(x, y, card_w, 58, 8, fill=1, stroke=1)
        pdf.setFillColor(accent)
        pdf.setFont("Helvetica-Bold", 6.2)
        pdf.drawString(x + 10, y + 39, label)
        pdf.setFillColor(white)
        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawString(x + 10, y + 15, value)

    y_repo = height - 255
    pdf.setFillColor(panel)
    pdf.setStrokeColor(border)
    pdf.roundRect(left, y_repo, width - 84, 60, 9, fill=1, stroke=1)
    pdf.setFillColor(cyan)
    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.drawString(left + 13, y_repo + 40, "ASSESSED REPOSITORY" if not spanish else "REPOSITORIO EVALUADO")
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(left + 13, y_repo + 22, _text(identity.get("repository"))[:82])
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 6.2)
    pdf.drawString(left + 13, y_repo + 9, _text(identity.get("commit_sha")))
    pdf.drawRightString(width - 55, y_repo + 9, _text(canonical.get("generated_at") or identity.get("generated_at")))

    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(left, height - 285, "Executive posture" if not spanish else "Postura ejecutiva")
    posture = _executive_posture(canonical, technical, adjusted, spanish=spanish)
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 7.1)
    words = posture.split()
    lines: list[str] = []
    line = ""
    max_width = width - 84
    for word in words:
        candidate = f"{line} {word}".strip()
        if stringWidth(candidate, "Helvetica", 7.1) <= max_width:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    for i, value in enumerate(lines[:5]):
        pdf.drawString(left, height - 303 - i * 10, value)

    box_y = 155
    pdf.setFillColor(panel)
    pdf.setStrokeColor(border)
    pdf.roundRect(left, box_y, width - 84, 132, 10, fill=1, stroke=1)
    pdf.setFillColor(cyan)
    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.drawString(left + 14, box_y + 111, "PRIORITY REVIEW ITEMS" if not spanish else "ELEMENTOS PRIORITARIOS PARA REVISIÓN")
    for index, title in enumerate(priorities[:3], start=1):
        cy = box_y + 82 - (index - 1) * 28
        pdf.setFillColor(teal)
        pdf.circle(left + 18, cy + 3, 7, fill=1, stroke=0)
        pdf.setFillColor(navy)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawCentredString(left + 18, cy + 1, str(index))
        pdf.setFillColor(white)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(left + 34, cy, title[:88])

    boundary = ES_BOUNDARY if spanish else EN_BOUNDARY
    pdf.setFillColor(colors.HexColor("#f0a23a"))
    pdf.setFont("Helvetica-Bold", 6.4)
    pdf.drawString(left, 75, boundary[:115])
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 6.2)
    pdf.drawString(left, 60, "READ-ONLY · IMMUTABLE SNAPSHOT · HUMAN REVIEW REQUIRED")
    pdf.setFillColor(cyan)
    pdf.setFont("Helvetica-Bold", 6.2)
    pdf.drawRightString(width - left, 60, "POWERED BY REPARODYNAMICS")
    pdf.setFillColor(colors.HexColor("#f0a23a"))
    pdf.setFont("Helvetica", 6.2)
    pdf.drawString(left, 45, "Client delivery remains blocked until explicit authorized human approval")
    pdf.setFillColor(muted)
    pdf.drawRightString(width - left, 45, "Page 1")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _existing_cover_page(text: str) -> bool:
    normalized = _text(text).casefold()
    if not normalized:
        return False
    explicit = (
        "decision-grade technical assessment",
        "evidence-bound technical review package",
        "canonical score summary",
        "resumen canónico de puntuación",
        "completed an authorized comprehensive technical assessment",
        "completó una evaluación técnica integral autorizada",
    )
    if any(marker in normalized for marker in explicit):
        return True
    return (
        "nico comprehensive" in normalized
        and "executive posture" in normalized
        and "client delivery" in normalized
    )


def apply_dark_branded_cover(package: Mapping[str, Any]) -> dict[str, Any]:
    from pypdf import PdfReader, PdfWriter

    result = deepcopy(dict(package))
    canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    language = _text(canonical.get("report_language") or canonical.get("locale")).casefold()
    original = base64.b64decode(str(result.get("pdf_base64") or ""))
    if not original.startswith(b"%PDF"):
        raise ValueError("dark branded cover requires a valid PDF")
    old_reader = PdfReader(io.BytesIO(original))
    cover_reader = PdfReader(io.BytesIO(_cover(canonical, spanish=language.startswith("es"))))
    writer = PdfWriter()
    writer.add_page(cover_reader.pages[0])
    removed_cover_pages = 0
    for page in old_reader.pages:
        if _existing_cover_page(page.extract_text() or ""):
            removed_cover_pages += 1
            continue
        writer.add_page(page)
    if len(writer.pages) < 2:
        raise ValueError("dark branded cover replacement removed the complete report body")
    output = io.BytesIO()
    writer.write(output)
    pdf = output.getvalue()
    contract = deepcopy(dict(result.get("premium_report_renderer") or {}))
    contract.update({
        "dark_branded_cover_restored": True,
        "dark_cover_version": VERSION,
        "golden_cover_layout_restored": True,
        "canonical_score_sheet_removed": True,
        "duplicate_cover_pages_removed": removed_cover_pages,
        "single_cover_enforced": True,
        "automated_draft_boundary_visible": True,
        "authorized_automation_claims_absent": True,
        "decision_grade_claim_absent": True,
    })
    page_count = len(writer.pages)
    result.update({
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "pdf_page_count": page_count,
        "core_report_page_count": page_count,
        "final_package_page_count": page_count,
        "premium_report_renderer": contract,
    })
    return result


__all__ = ["VERSION", "apply_dark_branded_cover"]
