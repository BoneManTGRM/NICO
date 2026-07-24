from __future__ import annotations

import io
from typing import Any

from pypdf import PdfReader, PdfWriter

from nico.express_section_status_truth_v26 import reconcile_section_status_truth

VERSION = "nico.express_pdf_score_assurance.v1"
_PATCH_MARKER = "_nico_express_pdf_score_assurance_v1"

_SECTION_PAGES = (
    (("code audit decision record",), "code_audit", "Code Audit Decision Record"),
    (("dependency and supply-chain decision record", "dependency / library ecosystem"), "dependency_health", "Dependency and Supply-Chain Decision Record"),
    (("secrets exposure decision record",), "secrets_review", "Secrets Exposure Decision Record"),
    (("static analysis decision record",), "static_analysis", "Static Analysis Decision Record"),
    (("ci/cd and release decision record",), "ci_cd", "CI/CD and Release Decision Record"),
    (("architecture decision record",), "architecture_debt", "Architecture Decision Record"),
    (("velocity, complexity, and ownership decision record",), "velocity_complexity", "Velocity, Complexity, and Ownership Decision Record"),
)


def _text(value: Any, limit: int = 900) -> str:
    normalized = " ".join(str(value or "").replace("\u00ad", "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _norm(value: Any) -> str:
    return _text(value, 20_000).casefold()


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any]:
    aliases = {
        "dependency_health": {"dependency_health", "dependency_library_ecosystem"},
        "ci_cd": {"ci_cd", "ci_cd_analysis"},
    }
    expected = aliases.get(section_id, {section_id})
    return next(
        (
            item
            for item in result.get("sections") or []
            if isinstance(item, dict) and _text(item.get("id")).casefold() in expected
        ),
        {},
    )


def _records(result: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = reconcile_section_status_truth(result)
    result.clear()
    result.update(normalized)
    output: list[dict[str, Any]] = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        score = section.get("score_value")
        output.append(
            {
                "section_id": _text(section.get("id")),
                "label": _text(section.get("label") or section.get("title") or section.get("id"), 180),
                "score": score,
                "score_label": "NOT SCORED" if score is None else f"{int(score)}/100",
                "band": _text(section.get("score_band_label") or "NOT SCORED", 60),
                "score_tone": _text(section.get("score_tone") or "gray", 30).casefold(),
                "assurance": _text(section.get("assurance_label") or "UNVERIFIED", 80),
                "assurance_tone": _text(section.get("assurance_tone") or "gray", 30).casefold(),
                "canonical_status": _text(section.get("status") or "unknown", 30).upper(),
                "confidence": _text(section.get("presented_confidence") or section.get("confidence") or "unknown", 60),
                "rationale": _text(section.get("score_rationale") or section.get("status_reason") or "No material score constraint retained.", 700),
                "directly_scored": section.get("directly_scored") is not False and score is not None,
            }
        )
    return output


def _record(result: dict[str, Any], section_id: str) -> dict[str, Any]:
    return next((item for item in _records(result) if item.get("section_id") == section_id), {})


def _styles():
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("ScoreAssuranceTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=25, textColor=colors.HexColor("#0f172a"), spaceAfter=9),
        "h2": ParagraphStyle("ScoreAssuranceH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=13, textColor=colors.HexColor("#075985"), spaceBefore=5, spaceAfter=3),
        "body": ParagraphStyle("ScoreAssuranceBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.2, leading=10.4, textColor=colors.HexColor("#334155"), spaceAfter=4),
        "small": ParagraphStyle("ScoreAssuranceSmall", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.3, leading=9.1, textColor=colors.HexColor("#475569"), spaceAfter=3),
        "label": ParagraphStyle("ScoreAssuranceLabel", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=7.2, leading=9, textColor=colors.HexColor("#64748b")),
        "callout": ParagraphStyle("ScoreAssuranceCallout", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=8.3, leading=10.5, textColor=colors.HexColor("#075985"), backColor=colors.HexColor("#e0f2fe"), borderColor=colors.HexColor("#38bdf8"), borderWidth=.7, borderPadding=7, spaceAfter=7),
    }


def _paragraph(value: Any, style: Any):
    import html
    from reportlab.platypus import Paragraph

    return Paragraph(html.escape(_text(value)), style)


def _table(rows: list[list[Any]], widths: list[float], *, repeat_rows: int = 1):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    widget = Table(rows, colWidths=widths, repeatRows=repeat_rows)
    commands = [
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if repeat_rows:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")),
            ]
        )
    widget.setStyle(TableStyle(commands))
    return widget


def _overview_pdf(result: dict[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Spacer

    records = _records(result)
    styles = _styles()
    p = lambda value, style=styles["body"]: _paragraph(value, style)
    rows = [[p("Control", styles["label"]), p("Technical score", styles["label"]), p("Technical band", styles["label"]), p("Assurance", styles["label"]), p("Risk disposition", styles["label"])]]
    for item in records:
        rows.append([p(item["label"]), p(item["score_label"]), p(item["band"]), p(item["assurance"]), p(item["canonical_status"])])
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=.45*inch, leftMargin=.45*inch, topMargin=.5*inch, bottomMargin=.6*inch, title="NICO Express Technical Score and Assurance", author="NICO", invariant=1)
    doc.build(
        [
            p("Technical Score and Evidence Assurance", styles["title"]),
            p("Technical health and evidence assurance are independent dimensions. A high technical score can remain review-limited when an analyzer failed, timed out, returned unresolved candidates, or material evidence is unavailable. Delivery approval remains a separate human decision.", styles["callout"]),
            Spacer(1, .06*inch),
            _table(rows, [2.25*inch, 1.05*inch, 1.15*inch, 1.25*inch, 1.05*inch]),
        ]
    )
    return buffer.getvalue()


def _contribution_pdf(result: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import Flowable, SimpleDocTemplate, Spacer

    class ScoreBar(Flowable):
        def __init__(self, score: Any, tone: str, width: float = 94.0, height: float = 8.0) -> None:
            super().__init__()
            self.score = max(0.0, min(100.0, float(score or 0)))
            self.tone = tone
            self.width = width
            self.height = height
            self.fill_width = self.width * self.score / 100.0

        def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
            return self.width, self.height

        def draw(self) -> None:
            palette = {"green": "#059669", "yellow": "#d97706", "red": "#dc2626", "gray": "#64748b", "blue": "#0284c7"}
            self.canv.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.canv.setFillColor(colors.HexColor("#f8fafc"))
            self.canv.roundRect(0, 0, self.width, self.height, 2, stroke=1, fill=1)
            if self.fill_width > 0:
                self.canv.setFillColor(colors.HexColor(palette.get(self.tone, "#64748b")))
                self.canv.roundRect(0, 0, self.fill_width, self.height, 2, stroke=0, fill=1)

    records = [item for item in _records(result) if item["directly_scored"]]
    styles = _styles()
    p = lambda value, style=styles["body"]: _paragraph(value, style)
    rows = [[p("Control", styles["label"]), p("Technical", styles["label"]), p("Score-derived contribution", styles["label"]), p("Assurance", styles["label"]), p("Primary constraint", styles["label"])]]
    geometry = []
    for item in records:
        score = int(item["score"] or 0)
        geometry.append({"section_id": item["section_id"], "score": score, "technical_band": item["band"], "score_tone": item["score_tone"], "assurance": item["assurance"], "rendered_ratio": score / 100.0})
        rows.append([p(item["label"]), p(f"{item['band']} · {item['score_label']}"), ScoreBar(score, item["score_tone"]), p(item["assurance"]), p(item["rationale"])])
    result["express_pdf_score_assurance_geometry"] = {
        "status": "complete",
        "version": VERSION,
        "records": geometry,
        "score_band_coloring": True,
        "assurance_separate": True,
        "canonical_status_retained": True,
    }
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=.4*inch, leftMargin=.4*inch, topMargin=.5*inch, bottomMargin=.6*inch, title="NICO Express Score Contribution and Assurance", author="NICO", invariant=1)
    doc.build(
        [
            p("Score Contribution and Assurance Constraints", styles["title"]),
            p("Bar width and bar color represent technical score and technical band only. Evidence assurance appears in its own column and can remain REVIEW LIMITED even when the technical score is STRONG or EXCEPTIONAL.", styles["callout"]),
            Spacer(1, .05*inch),
            _table(rows, [1.45*inch, 1.15*inch, 1.35*inch, 1.15*inch, 2.55*inch]),
        ]
    )
    return buffer.getvalue()


def _decision_pdf(result: dict[str, Any], section_id: str, title: str) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Spacer

    _records(result)
    section = _section(result, section_id)
    record = next((item for item in _records(result) if item.get("section_id") == section_id), {})
    styles = _styles()
    p = lambda value, style=styles["body"]: _paragraph(value, style)

    def bullets(values: Any, maximum: int) -> list[Any]:
        items = [_text(item, 650) for item in values or [] if _text(item)]
        return [p(f"• {item}", styles["small"]) for item in items[:maximum]] or [p("No retained item.", styles["small"])]

    scored = bool(record.get("directly_scored"))
    treatment = "Canonical scored control" if scored else "Supplemental / review control"
    summary = _table(
        [
            [p("Technical score", styles["label"]), p(record.get("score_label") or "NOT SCORED"), p("Technical band", styles["label"]), p(record.get("band") or "NOT SCORED")],
            [p("Assurance", styles["label"]), p(record.get("assurance") or "UNVERIFIED"), p("Risk disposition", styles["label"]), p(record.get("canonical_status") or "UNKNOWN")],
            [p("Confidence", styles["label"]), p(record.get("confidence") or "unknown"), p("Treatment", styles["label"]), p(treatment)],
        ],
        [1.05*inch, 2.45*inch, 1.05*inch, 2.45*inch],
        repeat_rows=0,
    )
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=.55*inch, leftMargin=.55*inch, topMargin=.55*inch, bottomMargin=.66*inch, title=title, author="NICO", invariant=1)
    doc.build(
        [
            p(title, styles["title"]),
            summary,
            Spacer(1, .08*inch),
            p(section.get("summary") or "No section summary retained."),
            p("Exact evidence", styles["h2"]),
            *bullets(section.get("evidence"), 7),
            p("Open findings", styles["h2"]),
            *bullets(section.get("findings"), 6),
            p("Limitations", styles["h2"]),
            *bullets(section.get("unavailable"), 5),
            p("Score and assurance rationale", styles["h2"]),
            p(record.get("rationale") or "No material score constraint retained."),
            p("Assurance remains separate from the technical percentage. Human review and client-delivery controls are not changed by the technical band.", styles["callout"]),
        ]
    )
    return buffer.getvalue()


def replace_score_assurance_pages(pdf_bytes: bytes, result: dict[str, Any]) -> bytes:
    _records(result)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    overview_replaced = False
    contribution_replaced = False
    section_replaced: set[str] = set()

    for page in reader.pages:
        text = _norm(page.extract_text() or "")
        if "transparent technical score" in text or "technical score and evidence assurance" in text:
            for replacement in PdfReader(io.BytesIO(_overview_pdf(result))).pages:
                writer.add_page(replacement)
            overview_replaced = True
            continue
        if "score contribution" in text and ("constraint" in text or "assurance" in text):
            for replacement in PdfReader(io.BytesIO(_contribution_pdf(result))).pages:
                writer.add_page(replacement)
            contribution_replaced = True
            continue
        matched = False
        for markers, section_id, title in _SECTION_PAGES:
            if any(marker in text for marker in markers):
                for replacement in PdfReader(io.BytesIO(_decision_pdf(result, section_id, title))).pages:
                    writer.add_page(replacement)
                section_replaced.add(section_id)
                matched = True
                break
        if not matched:
            writer.add_page(page)

    if not overview_replaced:
        for replacement in PdfReader(io.BytesIO(_overview_pdf(result))).pages:
            writer.add_page(replacement)
        overview_replaced = True
    if not contribution_replaced:
        for replacement in PdfReader(io.BytesIO(_contribution_pdf(result))).pages:
            writer.add_page(replacement)
        contribution_replaced = True

    output = io.BytesIO()
    writer.write(output)
    result["express_pdf_score_assurance"] = {
        "status": "complete" if overview_replaced and contribution_replaced else "degraded",
        "version": VERSION,
        "overview_replaced": overview_replaced,
        "contribution_replaced": contribution_replaced,
        "decision_sections_replaced": sorted(section_replaced),
        "score_band_coloring": True,
        "assurance_separate": True,
        "delivery_status_separate": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "page_count": len(writer.pages),
    }
    return output.getvalue()


def install_express_pdf_score_assurance_v1() -> dict[str, Any]:
    from nico import express_report_premium_v14 as premium

    current = premium._premium_pdf
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    def score_assurance_pdf(result: dict[str, Any]) -> bytes:
        normalized = reconcile_section_status_truth(result)
        result.clear()
        result.update(normalized)
        return replace_score_assurance_pages(current(result), result)

    setattr(score_assurance_pdf, _PATCH_MARKER, True)
    setattr(score_assurance_pdf, "_nico_previous", current)
    premium._premium_pdf = score_assurance_pdf
    return {
        "status": "installed",
        "version": VERSION,
        "score_band_coloring": True,
        "assurance_separate": True,
        "decision_pages_separated": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_express_pdf_score_assurance_v1",
    "replace_score_assurance_pages",
]
