from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any


MID_REPORT_V6_DESIGN_VERSION = "mid-assessment-professional-v6"
_PATCH_MARKER = "_nico_mid_report_professional_v6"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return " ".join(str(value or "").replace("_", " ").split())


def _client_breakdown(section: dict[str, Any]) -> dict[str, Any]:
    source = _dict(section.get("score_evidence_breakdown"))
    completed = source.get("completed_exact_snapshot_tools") or source.get("verified_tools") or []
    return {
        "Starting score": source.get("pre_recovery_score", source.get("pre_typescript_score", source.get("base_score", section.get("score")))),
        "Verified tool coverage": ", ".join(str(item) for item in completed) if isinstance(completed, list) and completed else "See retained evidence",
        "Material findings": source.get("material_finding_count", source.get("scanner_material_finding_count", 0)),
        "Review items": source.get("review_required_finding_count", source.get("scanner_review_required_count", 0)),
        "Evidence basis": source.get("recovery_basis", "Repository and same-run scanner evidence"),
        "Final score": section.get("score"),
    }


def _professional_payload(payload: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(payload)
    output["visual_design_version"] = MID_REPORT_V6_DESIGN_VERSION
    sections = []
    for raw in _list(output.get("sections")):
        if not isinstance(raw, dict):
            continue
        section = deepcopy(raw)
        section["score_evidence_breakdown"] = _client_breakdown(section)
        limitations: list[str] = []
        seen: set[str] = set()
        for value in _list(section.get("unavailable")) + _list(section.get("missing_evidence_sources")):
            text = _text(value)
            key = text.lower()
            if not text or key in seen:
                continue
            if "bandit and semgrep did not both" in key and any("bandit did not provide" in item.lower() for item in limitations):
                continue
            seen.add(key)
            limitations.append(text)
        section["unavailable"] = limitations
        sections.append(section)
    output["sections"] = sections
    contract = _dict(output.get("report_depth_contract"))
    contract.update({
        "visual_design_version": MID_REPORT_V6_DESIGN_VERSION,
        "professional_hierarchy": True,
        "client_safe_score_evidence": True,
        "visible_document_title": True,
        "alternating_table_rows": True,
        "dense_decision_layout": True,
    })
    output["report_depth_contract"] = contract
    return output


def install_mid_report_professional_v6() -> dict[str, Any]:
    from nico import mid_assessment_report as report_module
    from nico import report_flowable_safety as flowable

    if getattr(report_module, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": MID_REPORT_V6_DESIGN_VERSION}

    current_payload = report_module._report_payload
    current_markdown = report_module._markdown
    current_html = report_module._html
    current_pdf = report_module._pdf

    @wraps(current_payload)
    def payload_v6(record: dict[str, Any], packet: dict[str, Any], identity: dict[str, Any], generated_at: str) -> dict[str, Any]:
        return _professional_payload(current_payload(record, packet, identity, generated_at))

    @wraps(current_markdown)
    def markdown_v6(payload: dict[str, Any]) -> str:
        text = current_markdown(_professional_payload(payload))
        text = text.replace("# NICO MID ASSESSMENT", "# NICO MID ASSESSMENT\n\n**Professional Technical Review - Draft**", 1)
        text = text.replace("## Method and score sensitivity", "## Assessment Method and Score Sensitivity", 1)
        text = text.replace("## Prioritized repair intelligence", "## Prioritized Remediation Plan", 1)
        return text

    @wraps(current_html)
    def html_v6(payload: dict[str, Any]) -> str:
        return current_html(_professional_payload(payload)).replace(
            "<head>",
            "<head><style>body{font-family:Inter,Arial,sans-serif;color:#172033;max-width:960px;margin:40px auto;padding:0 24px}pre{white-space:pre-wrap;line-height:1.55}</style>",
            1,
        )

    @wraps(current_pdf)
    def pdf_v6(payload: dict[str, Any]) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import TableStyle

        original_styles = flowable._document_styles
        original_paragraph = flowable._paragraph
        original_table = flowable._table
        original_footer = flowable._footer

        def professional_styles(prefix: str) -> dict[str, Any]:
            styles = original_styles(prefix)
            styles["title"] = ParagraphStyle(
                f"{prefix}ProfessionalTitle",
                parent=styles["title"],
                fontName="Helvetica-Bold",
                fontSize=21,
                leading=24,
                textColor=colors.HexColor("#12213d"),
                spaceAfter=7,
            )
            styles["h2"] = ParagraphStyle(
                f"{prefix}ProfessionalH2",
                parent=styles["h2"],
                fontName="Helvetica-Bold",
                fontSize=12.5,
                leading=15,
                textColor=colors.HexColor("#12213d"),
                spaceBefore=8,
                spaceAfter=4,
            )
            styles["callout"] = ParagraphStyle(
                f"{prefix}ProfessionalCallout",
                parent=styles["callout"],
                fontName="Helvetica",
                fontSize=8.4,
                leading=10.8,
                textColor=colors.HexColor("#164e63"),
                backColor=colors.HexColor("#ecfeff"),
                borderColor=colors.HexColor("#22d3ee"),
                borderWidth=0.8,
                borderPadding=8,
                spaceAfter=7,
            )
            return styles

        def professional_paragraph(value: Any, style: Any, limit: int = 1000):
            if str(value) == "NICO MID TECHNICAL ASSESSMENT":
                style = ParagraphStyle(
                    "NicoMidHeroWhite",
                    parent=style,
                    fontName="Helvetica-Bold",
                    fontSize=19,
                    leading=22,
                    textColor=colors.white,
                    alignment=0,
                    spaceAfter=0,
                )
            return original_paragraph(value, style, limit)

        def professional_table(rows: list[list[Any]], widths: list[Any], *, header_color: str = "#e0f2fe"):
            table = original_table(rows, widths, header_color="#dbeafe")
            commands: list[tuple[Any, ...]] = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#0ea5e9")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
            ]
            for index in range(1, len(rows)):
                if index % 2 == 0:
                    commands.append(("BACKGROUND", (0, index), (-1, index), colors.HexColor("#f8fafc")))
            table.setStyle(TableStyle(commands))
            return table

        def professional_footer(label: str):
            base = original_footer(label)

            def draw(canvas: Any, document: Any) -> None:
                base(canvas, document)
                canvas.saveState()
                canvas.setFillColor(colors.HexColor("#0ea5e9"))
                canvas.rect(document.leftMargin, document.pagesize[1] - 0.25 * 72, 0.35 * 72, 0.04 * 72, fill=1, stroke=0)
                canvas.restoreState()

            return draw

        flowable._document_styles = professional_styles
        flowable._paragraph = professional_paragraph
        flowable._table = professional_table
        flowable._footer = professional_footer
        try:
            return current_pdf(_professional_payload(payload))
        finally:
            flowable._document_styles = original_styles
            flowable._paragraph = original_paragraph
            flowable._table = original_table
            flowable._footer = original_footer

    report_module._report_payload = payload_v6
    report_module._markdown = markdown_v6
    report_module._html = html_v6
    report_module._pdf = pdf_v6
    setattr(report_module, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "version": MID_REPORT_V6_DESIGN_VERSION,
        "visible_title_repaired": True,
        "client_safe_score_evidence": True,
        "alternating_table_rows": True,
        "score_logic_changed": False,
        "human_review_required": True,
    }


__all__ = ["MID_REPORT_V6_DESIGN_VERSION", "install_mid_report_professional_v6"]
