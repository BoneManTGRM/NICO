from __future__ import annotations

import base64
import hashlib
import io
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.v2.dark-branded-cover.v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _score_pair(assessment: Mapping[str, Any]) -> tuple[str, str]:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}
    technical = assessment.get("technical_score", maturity.get("technical_score", maturity.get("presented_score", maturity.get("score"))))
    adjusted = assessment.get("canonical_evidence_adjusted_score", assessment.get("evidence_adjusted_score", maturity.get("evidence_adjusted_score", technical)))
    technical_label = f"{int(round(technical))}/100" if isinstance(technical, (int, float)) and not isinstance(technical, bool) else "NOT SCORED"
    adjusted_label = f"{int(round(adjusted))}/100" if isinstance(adjusted, (int, float)) and not isinstance(adjusted, bool) else "NOT SCORED"
    return technical_label, adjusted_label


def _cover(canonical: Mapping[str, Any], *, spanish: bool) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    technical, adjusted = _score_pair(assessment)
    width, height = letter
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.setFillColor(colors.HexColor("#050b18"))
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#0b213b"))
    pdf.circle(width + 25, height - 75, 210, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#0c4a6e"))
    pdf.circle(width - 15, height - 55, 125, fill=1, stroke=0)

    pdf.setFillColor(colors.HexColor("#55d7f4"))
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawCentredString(width / 2, height - 110, "NICO")
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 27)
    title = "EVALUACIÓN TÉCNICA INTEGRAL" if spanish else "COMPREHENSIVE TECHNICAL ASSESSMENT"
    pdf.drawCentredString(width / 2, height - 160, title)
    pdf.setFillColor(colors.HexColor("#cbd5e1"))
    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(width / 2, height - 188, _text(identity.get("repository"))[:90])

    x, y, box_w, box_h = 95, height - 335, width - 190, 62
    pdf.setFillColor(colors.HexColor("#081426"))
    pdf.roundRect(x, y, box_w, box_h, 10, fill=1, stroke=0)
    pdf.setStrokeColor(colors.HexColor("#1e7494"))
    pdf.roundRect(x, y, box_w, box_h, 10, fill=0, stroke=1)
    pdf.setFillColor(colors.HexColor("#cbd5e1"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(x + 20, y + 39, "MADUREZ TÉCNICA" if spanish else "TECHNICAL MATURITY")
    pdf.drawString(x + box_w / 2 + 20, y + 39, "AJUSTE POR EVIDENCIA" if spanish else "EVIDENCE-ADJUSTED")
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(x + 20, y + 14, technical)
    pdf.drawString(x + box_w / 2 + 20, y + 14, adjusted)

    pdf.setFillColor(colors.HexColor("#94a3b8"))
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(width / 2, height - 395, f"Run ID: {_text(identity.get('run_id'))}")
    pdf.drawCentredString(width / 2, height - 410, f"Exact commit: {_text(identity.get('commit_sha'))}")

    pdf.setFillColor(colors.HexColor("#3b2108"))
    pdf.setStrokeColor(colors.HexColor("#f59e0b"))
    pdf.roundRect(75, 130, width - 150, 54, 10, fill=1, stroke=1)
    pdf.setFillColor(colors.HexColor("#fde68a"))
    pdf.setFont("Helvetica-Bold", 10)
    boundary = (
        "INFORME FINAL · APROBACIÓN HUMANA PENDIENTE · ENTREGA BLOQUEADA"
        if spanish
        else "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"
    )
    pdf.drawCentredString(width / 2, 158, boundary)
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(width / 2, 143, "CLIENT DELIVERY NOT AUTHORIZED")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


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
    for page in list(old_reader.pages)[1:]:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    pdf = output.getvalue()
    contract = deepcopy(dict(result.get("premium_report_renderer") or {}))
    contract.update({"dark_branded_cover_restored": True, "dark_cover_version": VERSION})
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
