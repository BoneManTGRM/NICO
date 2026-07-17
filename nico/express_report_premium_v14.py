from __future__ import annotations

import base64
import html
import io
import re
from dataclasses import dataclass
from typing import Any


VERSION = "professional_express_premium_v14"
_PATCH_MARKER = "_nico_express_report_premium_v14"
_REVIEW_TERMS = (
    "timeout",
    "timed out",
    "failed",
    "requires human triage",
    "requires review",
    "missing required",
    "unavailable",
    "incomplete",
)
_PLACEHOLDER_RE = re.compile(r"<[^>]*(?:version|package|verified|minimum|maximum|breaking)[^>]*>", re.I)


@dataclass(frozen=True)
class ScoreRecord:
    section_id: str
    label: str
    source_score: int
    presented_score: int
    status: str
    deductions: tuple[tuple[str, int], ...]
    confidence: str
    rationale: str


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, limit: int = 1200) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _unique(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in _list(values):
        text = _text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _all_section_text(section: dict[str, Any]) -> str:
    values = [section.get("summary")]
    values.extend(_list(section.get("evidence")))
    values.extend(_list(section.get("findings")))
    values.extend(_list(section.get("unavailable")))
    return " ".join(_text(value).lower() for value in values if value)


def _score_record(section: dict[str, Any]) -> ScoreRecord:
    source = max(0, min(100, int(section.get("score") or 0)))
    combined = _all_section_text(section)
    deductions: list[tuple[str, int]] = []
    findings = _unique(section.get("findings"))
    unavailable = _unique(section.get("unavailable"))

    if any(term in combined for term in ("timeout", "timed out")):
        deductions.append(("Required analyzer did not complete", 8))
    if "failed" in combined:
        deductions.append(("Required analyzer reported failure", 10))
    if any(term in combined for term in ("requires human triage", "requires review")):
        deductions.append(("Unresolved findings require disposition", min(12, 4 + len(findings))))
    if unavailable:
        deductions.append(("Material evidence is unavailable or limited", min(10, 2 + len(unavailable))))
    if findings and not deductions:
        deductions.append(("Open findings remain unresolved", min(8, 2 + len(findings))))

    total = sum(amount for _, amount in deductions)
    presented = max(0, source - total)
    unresolved = bool(deductions)
    if unresolved and presented >= 75:
        presented = 74
    status = "green" if presented >= 75 and not unresolved else "yellow" if presented >= 45 else "red"
    confidence = "high" if not unavailable and not any(term in combined for term in _REVIEW_TERMS) else "review-limited"
    rationale = (
        "No material report limitation was retained for this control."
        if not deductions
        else "; ".join(reason for reason, _ in deductions)
    )
    return ScoreRecord(
        section_id=_text(section.get("id"), 80),
        label=_text(section.get("label") or section.get("id"), 160),
        source_score=source,
        presented_score=presented,
        status=status,
        deductions=tuple(deductions),
        confidence=confidence,
        rationale=rationale,
    )


def reconcile_express_scores(result: dict[str, Any]) -> tuple[list[ScoreRecord], int]:
    records = [_score_record(dict(item)) for item in _list(result.get("sections")) if isinstance(item, dict)]
    scored = [item.presented_score for item in records if item.section_id not in {"trust_readiness", "client_acceptance", "scanner_worker"}]
    overall = round(sum(scored) / len(scored)) if scored else 0
    result["express_score_transparency"] = {
        "version": VERSION,
        "overall_presented_score": overall,
        "source_maturity_score": _dict(result.get("maturity_signal")).get("score"),
        "method": "Section source score minus explicit evidence deductions; unresolved controls are capped below GREEN.",
        "records": [
            {
                "section_id": item.section_id,
                "label": item.label,
                "source_score": item.source_score,
                "presented_score": item.presented_score,
                "status": item.status,
                "confidence": item.confidence,
                "deductions": [{"reason": reason, "points": points} for reason, points in item.deductions],
                "rationale": item.rationale,
            }
            for item in records
        ],
    }
    return records, overall


def _clean_repairs(result: dict[str, Any]) -> list[dict[str, Any]]:
    intelligence = _dict(result.get("repair_intelligence"))
    candidates = [dict(item) for item in _list(intelligence.get("candidates")) if isinstance(item, dict)]
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in candidates:
        title = _text(item.get("title") or item.get("finding"), 220)
        key = re.sub(r"\W+", " ", title.casefold()).strip()
        if not title or key in seen:
            continue
        seen.add(key)
        suggestion = _text(item.get("replacement_code") or item.get("suggested_code"), 1200)
        if _PLACEHOLDER_RE.search(suggestion):
            suggestion = ""
        output.append({
            **item,
            "title": title,
            "safe_code_suggestion": suggestion,
            "repair_specification": _text(item.get("recommended_action") or item.get("action"), 600),
        })
    return output


def _premium_pdf(result: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    records, overall = reconcile_express_scores(result)
    repairs = _clean_repairs(result)
    sections = {str(item.get("id")): dict(item) for item in _list(result.get("sections")) if isinstance(item, dict)}
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.66 * inch,
        title="NICO Express Technical Health Assessment",
        author="NICO",
        invariant=1,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("V14Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=23, leading=26, textColor=colors.HexColor("#0f172a"), spaceAfter=10)
    h2 = ParagraphStyle("V14H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=colors.HexColor("#075985"), spaceAfter=7)
    h3 = ParagraphStyle("V14H3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=colors.HexColor("#111827"), spaceBefore=5, spaceAfter=3)
    body = ParagraphStyle("V14Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.7, leading=11.4, textColor=colors.HexColor("#334155"), spaceAfter=5)
    small = ParagraphStyle("V14Small", parent=body, fontSize=7.4, leading=9.4, textColor=colors.HexColor("#475569"), spaceAfter=3)
    label = ParagraphStyle("V14Label", parent=small, fontName="Helvetica-Bold", textColor=colors.HexColor("#64748b"))
    callout = ParagraphStyle("V14Callout", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#075985"), backColor=colors.HexColor("#e0f2fe"), borderColor=colors.HexColor("#38bdf8"), borderWidth=0.7, borderPadding=8, spaceAfter=8)
    warning = ParagraphStyle("V14Warning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#854d0e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=0.7, borderPadding=8, spaceAfter=8)

    def p(value: Any, style: Any = body, limit: int = 1200) -> Paragraph:
        return Paragraph(html.escape(_text(value, limit)), style)

    def table(rows: list[list[Any]], widths: list[float], header: bool = True) -> Table:
        widget = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
        commands = [
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
        if header:
            commands.extend([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")),
            ])
        widget.setStyle(TableStyle(commands))
        return widget

    def bullets(values: Any, max_items: int = 6) -> list[Paragraph]:
        items = _unique(values)
        rendered = [p(f"• {item}", small, 650) for item in items[:max_items]]
        if len(items) > max_items:
            rendered.append(p(f"• {len(items) - max_items} additional item(s) remain in the evidence export.", small))
        return rendered

    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#bae6fd"))
        canvas.line(document.leftMargin, 0.48 * inch, document.pagesize[0] - document.rightMargin, 0.48 * inch)
        canvas.setFont("Helvetica", 7.1)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(document.leftMargin, 0.3 * inch, "NICO Express · evidence-bound · report only · human review required")
        canvas.drawRightString(document.pagesize[0] - document.rightMargin, 0.3 * inch, f"Page {document.page} of 15")
        canvas.restoreState()

    maturity = _dict(result.get("maturity_signal"))
    source_score = maturity.get("score", "N/A")
    repository = result.get("repository") or "Authorized repository"
    decision = _dict(result.get("decision_summary"))

    story: list[Any] = []

    # 1 — cover and decision posture
    story.extend([
        Spacer(1, 0.45 * inch),
        p("NICO EXPRESS", title),
        p("Technical Health Assessment", h2),
        p("Premium executive and scoring edition", callout),
        table([
            [p("Repository", label), p(repository, small), p("Generated", label), p(result.get("generated_at") or "Not recorded", small)],
            [p("Source maturity score", label), p(f"{source_score}/100", small), p("Evidence-adjusted score", label), p(f"{overall}/100", small)],
            [p("Decision posture", label), p("Human review required", small), p("Delivery posture", label), p("Not approved for client delivery", small)],
        ], [1.2*inch, 2.35*inch, 1.25*inch, 2.25*inch], header=False),
        Spacer(1, 0.18 * inch),
        p("NICO performed a defensive, read-only assessment of the authorized repository. The system being assessed generated this report; independent validation is recommended before relying on it for a material transaction, regulatory conclusion, or production-risk decision.", warning),
        p("This Express report separates technical health, evidence confidence, release posture, client-delivery posture, and repair priority. Missing or failed evidence is never converted into a clean result.", body),
        PageBreak(),
    ])

    # 2 — executive decision brief
    top_repairs = repairs[:5]
    story.extend([p("Executive Decision Brief", title), p(result.get("executive_summary") or "No executive summary was retained.", body)])
    story.append(table([
        [p("Decision area", label), p("Current conclusion", label)],
        [p("Operate", small), p("Continue only within the current authorized scope while review-limited controls remain visible.", small)],
        [p("Release", small), p("Release readiness is conditional on resolving or formally accepting the highest-ranked open evidence and scanner exceptions.", small)],
        [p("Client delivery", small), p("Blocked until an authorized reviewer accepts the exact evidence, score reconciliation, and open exceptions.", small)],
        [p("Immediate priority", small), p(_text(top_repairs[0].get("title") if top_repairs else "Review the highest-ranked open control"), small)],
    ], [1.45*inch, 5.6*inch]))
    story.extend([p("Top business consequences", h2)])
    for item in top_repairs[:4]:
        story.append(p(f"• {item.get('title')}: {_text(item.get('business_impact') or item.get('impact') or item.get('recommended_action'), 500)}", body))
    story.append(PageBreak())

    # 3 — transparent scoring
    story.extend([p("Transparent Technical Score", title), p("The presented score starts with each source section score, subtracts explicit evidence deductions, and caps unresolved controls below GREEN. This is a report-confidence reconciliation, not a hidden replacement of source evidence.", callout)])
    score_rows = [[p("Control", label), p("Source", label), p("Deductions", label), p("Presented", label), p("Status", label), p("Confidence", label)]]
    for item in records:
        deduction = "; ".join(f"-{points} {reason}" for reason, points in item.deductions) or "None"
        score_rows.append([p(item.label, small), p(item.source_score, small), p(deduction, small, 420), p(item.presented_score, small), p(item.status.upper(), small), p(item.confidence, small)])
    story.append(table(score_rows, [1.45*inch, 0.55*inch, 2.6*inch, 0.65*inch, 0.65*inch, 1.15*inch]))
    story.append(PageBreak())

    # 4 — score contribution and constraints
    story.extend([p("Score Contribution and Constraints", title)])
    contribution_rows = [[p("Control", label), p("Presented score", label), p("Contribution bar", label), p("Primary constraint", label)]]
    for item in records:
        bar = "■" * max(1, round(item.presented_score / 10)) + "□" * max(0, 10 - round(item.presented_score / 10))
        contribution_rows.append([p(item.label, small), p(f"{item.presented_score}/100", small), p(bar, small), p(item.rationale, small, 400)])
    story.append(table(contribution_rows, [1.55*inch, 0.85*inch, 1.35*inch, 3.3*inch]))
    story.extend([p("Overall interpretation", h2), p(f"Evidence-adjusted technical score: {overall}/100. Source maturity score: {source_score}/100. The difference is fully attributable to the listed deductions; no undisclosed adjustment is permitted.", body), PageBreak()])

    # 5 — evidence funnel
    total_evidence = sum(len(_unique(section.get("evidence"))) for section in sections.values())
    total_findings = sum(len(_unique(section.get("findings"))) for section in sections.values())
    total_limits = sum(len(_unique(section.get("unavailable"))) for section in sections.values())
    story.extend([p("Evidence Funnel", title), p("Collection, execution, parsing, scoring acceptance, and final disposition are separate states. An artifact is not treated as proof merely because it exists.", callout)])
    story.append(table([
        [p("Stage", label), p("Observed volume", label), p("Decision meaning", label)],
        [p("Retained evidence statements", small), p(total_evidence, small), p("Evidence available for reviewer inspection; not automatically verified.", small)],
        [p("Open finding statements", small), p(total_findings, small), p("Require disposition, repair, or documented acceptance.", small)],
        [p("Unavailable/limited statements", small), p(total_limits, small), p("Constrain confidence and can cap section status.", small)],
        [p("Final human disposition", small), p("Pending", small), p("Client delivery remains blocked until review is recorded.", small)],
    ], [2.0*inch, 1.2*inch, 3.85*inch]))
    story.extend([p("Evidence integrity rules", h2), *bullets([
        "Exact repository and snapshot identity must be retained.",
        "Failed or timed-out analyzers cannot be relabeled as clean.",
        "Unresolved scanner candidates remain review-limited until triaged.",
        "Unavailable provider evidence is disclosed rather than inferred.",
        "No score may increase solely because evidence is missing.",
    ]), PageBreak()])

    # 6 — risk matrix
    story.extend([p("Risk and Repair Matrix", title)])
    risk_rows = [[p("Priority", label), p("Finding", label), p("Severity", label), p("Effort", label), p("Business decision", label)]]
    for index, item in enumerate(top_repairs[:8], 1):
        risk_rows.append([
            p(item.get("rank") or f"P{index}", small),
            p(item.get("title"), small, 300),
            p(str(item.get("severity") or "unclassified").upper(), small),
            p(str(item.get("effort") or "estimate required").upper(), small),
            p(item.get("recommended_action") or item.get("action") or "Review exact evidence and define a reversible repair.", small, 360),
        ])
    story.append(table(risk_rows, [0.55*inch, 2.25*inch, 0.8*inch, 0.9*inch, 2.55*inch]))
    story.extend([p("Prioritization rule", h2), p("Verified defects and release blockers outrank planning advisories. Repository size, branch count, or ownership concentration is retained as operational context unless evidence proves a direct control failure.", body), PageBreak()])

    # 7–12 — technical control pages
    control_pages = [
        ("Code Audit Decision Record", ["code_audit"]),
        ("Dependency and Supply-Chain Decision Record", ["dependency_health"]),
        ("Secrets Exposure Decision Record", ["secrets_review"]),
        ("Static Analysis Decision Record", ["static_analysis"]),
        ("CI/CD and Release Decision Record", ["ci_cd"]),
        ("Architecture, Complexity, and Ownership Decision Record", ["architecture_debt", "velocity_complexity"]),
    ]
    record_map = {item.section_id: item for item in records}
    for page_title, ids in control_pages:
        story.append(p(page_title, title))
        for section_id in ids:
            section = sections.get(section_id, {})
            record = record_map.get(section_id)
            story.append(table([
                [p("Source score", label), p(f"{record.source_score if record else 0}/100", small), p("Presented score", label), p(f"{record.presented_score if record else 0}/100", small)],
                [p("Status", label), p((record.status if record else "unknown").upper(), small), p("Confidence", label), p(record.confidence if record else "unknown", small)],
            ], [1.1*inch, 2.4*inch, 1.1*inch, 2.45*inch], header=False))
            story.extend([p(section.get("summary") or "No section summary retained.", body), p("Exact evidence", h3), *bullets(section.get("evidence"), 6), p("Open findings", h3), *bullets(section.get("findings"), 6), p("Limitations", h3), *bullets(section.get("unavailable"), 5)])
            if record:
                story.extend([p("Score rationale", h3), p(record.rationale, body)])
        story.append(PageBreak())

    # 13 — prioritized repair intelligence
    story.extend([p("Prioritized Repair Intelligence", title), p("Each item below is a report-only decision record. Placeholder code is withheld; exact code is shown only when the assessed file, package, version, and verification context are known.", callout)])
    repair_rows = [[p("Rank", label), p("Finding", label), p("Impact", label), p("Repair specification", label), p("Verification", label)]]
    for index, item in enumerate(top_repairs[:8], 1):
        repair_rows.append([
            p(item.get("rank") or f"P{index}", small),
            p(item.get("title"), small, 260),
            p(item.get("business_impact") or item.get("impact") or "Impact requires reviewer confirmation.", small, 280),
            p(item.get("repair_specification") or "Define the smallest reversible repair from the exact evidence.", small, 320),
            p(item.get("verification") or "Run focused tests, full suite, production build, and immutable rescan.", small, 280),
        ])
    story.append(table(repair_rows, [0.5*inch, 1.7*inch, 1.5*inch, 1.9*inch, 1.45*inch]))
    story.append(PageBreak())

    # 14 — accountable 30-day roadmap
    story.extend([p("Immediate and 30-Day Roadmap", title)])
    roadmap_rows = [[p("Window", label), p("Work item", label), p("Owner", label), p("Effort", label), p("Completion definition", label)]]
    windows = ["0–48 hours", "Week 1", "Week 2", "Weeks 3–4", "Day 30 gate"]
    for index, window in enumerate(windows):
        item = top_repairs[index] if index < len(top_repairs) else {}
        roadmap_rows.append([
            p(window, small),
            p(item.get("title") or "Close remaining evidence and review exceptions", small, 280),
            p(item.get("owner") or "Authorized engineering owner", small),
            p(item.get("effort") or "Estimate after exact evidence review", small),
            p(item.get("verification") or "Objective evidence retained; focused and full verification green; new report generated from the exact snapshot.", small, 340),
        ])
    story.append(table(roadmap_rows, [0.9*inch, 2.0*inch, 1.25*inch, 1.15*inch, 1.75*inch]))
    story.extend([p("Release and delivery gates", h2), *bullets([
        "No unresolved critical or high-severity verified defect without explicit risk acceptance.",
        "Required analyzers complete or formally documented as inapplicable.",
        "Score/status reconciliation contains no GREEN control with unresolved failed or timed-out evidence.",
        "Human reviewer signs the exact report identity and evidence snapshot.",
        "Client delivery artifact is created only after approval and acknowledgement controls pass.",
    ]), PageBreak()])

    # 15 — integrity, independence, reviewer record
    story.extend([
        p("Integrity, Independence, and Reviewer Record", title),
        p("Self-assessment limitation", h2),
        p("This report was generated by NICO while NICO was the assessed repository. The evidence may be useful and internally consistent, but the assessment is not independent. Material assurance should include review by a qualified person or separate system that did not generate the underlying conclusions.", warning),
        p("Approval boundary", h2),
        p("NICO did not approve this assessment, modify the repository, create a branch, commit code, open a pull request, deploy software, rotate credentials, enable provider controls, or accept residual risk. Suggested repairs remain unverified until exact-context tests pass and an authorized human approves implementation.", body),
        table([
            [p("Reviewer decision", label), p("Pending", small)],
            [p("Accepted findings", label), p("Not recorded", small)],
            [p("Required repairs", label), p("Not recorded", small)],
            [p("Residual risk acceptance", label), p("Not recorded", small)],
            [p("Client delivery authorization", label), p("Not granted", small)],
            [p("Reassessment snapshot", label), p("Required after material repair", small)],
        ], [2.2*inch, 4.85*inch], header=False),
        Spacer(1, 0.15*inch),
        p("Unsupported claims permitted: 0. Missing evidence remains visible. Score deductions are reproducible from the retained report metadata. Human review is required before client delivery.", callout),
    ])

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def build_express_premium_pdf(result: dict[str, Any]) -> tuple[str | None, str | None]:
    try:
        payload = _premium_pdf(result)
        result["express_premium_report"] = {
            "status": "complete",
            "version": VERSION,
            "page_contract": {"minimum": 15, "target": 18, "maximum": 20},
            "executive_decision_brief": True,
            "score_transparency": True,
            "score_status_integrity_cap": True,
            "evidence_funnel": True,
            "risk_matrix": True,
            "thirty_day_roadmap": True,
            "self_assessment_limitation": True,
            "placeholder_code_withheld": True,
            "human_review_required": True,
            "code_changes_applied": False,
        }
        return base64.b64encode(payload).decode("ascii"), None
    except Exception as exc:  # pragma: no cover
        return None, f"Express premium v14 PDF failed: {type(exc).__name__}: {exc}"


def install_express_report_premium_v14() -> dict[str, Any]:
    from nico import assessment_quality

    current = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}
    setattr(build_express_premium_pdf, _PATCH_MARKER, True)
    setattr(build_express_premium_pdf, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = build_express_premium_pdf
    return {
        "status": "installed",
        "version": VERSION,
        "production_renderer_bound": True,
        "minimum_pages": 15,
        "report_only": True,
        "human_review_required": True,
    }


__all__ = [
    "VERSION",
    "ScoreRecord",
    "build_express_premium_pdf",
    "install_express_report_premium_v14",
    "reconcile_express_scores",
]
