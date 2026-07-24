from __future__ import annotations

import html
import io
import re
from collections import Counter
from copy import deepcopy
from typing import Any, Callable

from pypdf import PdfReader

from nico.report_semantic_cleanup_v46 import normalize_final_report_semantics as _base_semantic_cleanup

VERSION = "nico.express_report_quality.v47"
_MARKER = "_nico_express_report_quality_v47"
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _text(value: Any, limit: int = 1400) -> str:
    text = _CONTROL_RE.sub("", str(value or ""))
    text = " ".join(text.split())
    text = re.sub(r",(?=[A-Za-z0-9])", ", ", text)
    text = re.sub(r";(?=[A-Za-z0-9])", "; ", text)
    text = re.sub(r"\bSUPPLEMENTA\s+L\b", "SUPPLEMENTAL", text, flags=re.I)
    text = re.sub(r"\bdisposition,\s*repair\b", "disposition, repair", text, flags=re.I)
    text = re.sub(r"\bevidence,\s*score\b", "evidence, score", text, flags=re.I)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _unique(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = _text(raw)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            output.append(value)
    return output


def _recursive_copy(value: Any) -> Any:
    if isinstance(value, str):
        return _text(value, 100_000)
    if isinstance(value, list):
        return [_recursive_copy(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_recursive_copy(item) for item in value)
    if isinstance(value, dict):
        return {key: _recursive_copy(item) for key, item in value.items()}
    return value


def _section_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    aliases = {
        "dependency_library_ecosystem": "dependency_health",
        "ci_cd_analysis": "ci_cd",
        "scanner_worker_evidence": "scanner_assurance_ledger",
        "scanner_evidence": "scanner_assurance_ledger",
        "client_human_acceptance": "review_delivery",
        "client_acceptance": "review_delivery",
    }
    output: dict[str, dict[str, Any]] = {}
    for item in payload.get("sections") or []:
        if not isinstance(item, dict):
            continue
        raw = _text(item.get("id"), 100).casefold()
        output[aliases.get(raw, raw)] = item
    return output


def _scanner_tools(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    ledger = payload.get("scanner_assurance_ledger")
    analyzers = ledger.get("analyzers") if isinstance(ledger, dict) else []
    for item in analyzers or []:
        if isinstance(item, dict) and _text(item.get("tool")):
            output[_text(item.get("tool"), 80).casefold()] = item
    for section in payload.get("sections") or []:
        if not isinstance(section, dict):
            continue
        dispositions = section.get("scanner_dispositions")
        if not isinstance(dispositions, dict):
            continue
        for name, item in dispositions.items():
            if isinstance(item, dict):
                output.setdefault(_text(name, 80).casefold(), item)
    return output


def _tool_status(tool: dict[str, Any]) -> str:
    return _text(
        tool.get("lifecycle_result")
        or tool.get("canonical_disposition")
        or tool.get("status"),
        80,
    ).casefold().replace("-", "_").replace(" ", "_")


def _confidence_for_assurance(value: Any) -> str:
    assurance = _text(value, 80).upper()
    return {
        "VERIFIED": "high",
        "REVIEW LIMITED": "review-limited",
        "INCOMPLETE": "low",
        "UNAVAILABLE": "low",
        "SUPPLEMENTAL": "supplemental",
        "PENDING HUMAN APPROVAL": "pending-human-approval",
    }.get(assurance, "unverified")


def _reconcile_secret_timeout(section: dict[str, Any], tools: dict[str, dict[str, Any]]) -> None:
    combined = " ".join(
        _text(item).casefold()
        for key in ("evidence", "findings", "unavailable", "review_items")
        for item in section.get(key) or []
    )
    timed_out = _tool_status(tools.get("gitleaks") or {}) in {"timeout", "timed_out"} or "gitleaks ended with status timeout" in combined
    if not timed_out:
        return
    retained: list[str] = []
    for raw in section.get("findings") or []:
        value = _text(raw)
        lowered = value.casefold()
        if "gitleaks timed out with 0 retained" in lowered:
            continue
        if "parsed gitleaks artifact reported" in lowered:
            match = re.search(r"reported\s+(\d+)", value, flags=re.I)
            count = match.group(1) if match else "retained"
            retained.append(
                f"Partial Gitleaks output contained {count} review-only candidate(s) before timeout; these are neither verified secret findings nor clean evidence."
            )
            continue
        retained.append(value)
    retained.append(
        "Gitleaks timed out before a complete result was established. Partial output remains review-only; no clean or verified-finding conclusion is permitted."
    )
    section["findings"] = _unique(retained)
    section["gitleaks_partial_artifact_disposition"] = "review_only_timeout"


def _reconcile_static_execution(section: dict[str, Any], tools: dict[str, dict[str, Any]]) -> None:
    all_values = [
        _text(item)
        for key in ("evidence", "findings", "unavailable", "review_items")
        for item in section.get(key) or []
    ]
    combined = " ".join(all_values).casefold()
    bandit_failed = _tool_status(tools.get("bandit") or {}) == "failed" or "bandit status=failed" in combined
    eslint_status = _tool_status(tools.get("eslint") or {})
    eslint_not_configured = eslint_status in {"not_configured", "inapplicable", "not_applicable"} or (
        "no eslint configuration exists" in combined
        or "eslint is not configured" in combined
        or "package lint script does not execute eslint" in combined
    )

    evidence: list[str] = []
    for raw in section.get("evidence") or []:
        value = _text(raw)
        lowered = value.casefold()
        if bandit_failed and (
            "bandit, semgrep, eslint, and typescript artifacts are complete" in lowered
            or "clean bandit triage supersedes" in lowered
            or "canonical scanner disposition: bandit=unknown" in lowered
        ):
            continue
        if eslint_not_configured and "canonical scanner disposition: eslint=unknown" in lowered:
            continue
        evidence.append(value)
    if bandit_failed:
        evidence.append(
            "Live Bandit execution failed for this exact run. Attached triage records remain diagnostic and cannot establish a clean or completed Bandit result."
        )
    if eslint_not_configured:
        evidence.append(
            "ESLint is not configured for this repository snapshot. It is classified as not configured rather than unavailable or failed; TypeScript remains independently evaluated."
        )

    limitations: list[str] = []
    for raw in section.get("unavailable") or []:
        value = _text(raw)
        lowered = value.casefold()
        if eslint_not_configured and "eslint" in lowered:
            continue
        limitations.append(value)
    section["evidence"] = _unique(evidence)
    section["unavailable"] = _unique(limitations)
    if bandit_failed:
        section["bandit_execution_disposition"] = "failed_review_only"
    if eslint_not_configured:
        section["eslint_execution_disposition"] = "not_configured"


def normalize_client_report_quality_v47(payload: dict[str, Any]) -> dict[str, Any]:
    output = _recursive_copy(_base_semantic_cleanup(deepcopy(payload)))
    sections = _section_map(output)
    tools = _scanner_tools(output)
    secrets = sections.get("secrets_review")
    if secrets:
        _reconcile_secret_timeout(secrets, tools)
    static = sections.get("static_analysis")
    if static:
        _reconcile_static_execution(static, tools)

    for section in output.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section["evidence"] = _unique(section.get("evidence"))
        section["findings"] = _unique(section.get("findings"))
        section["unavailable"] = _unique(section.get("unavailable"))
        section["review_items"] = _unique(section.get("review_items"))
        assurance = _text(section.get("assurance_label") or section.get("evidence_assurance"), 80).upper()
        if assurance:
            confidence = _confidence_for_assurance(assurance)
            section["confidence"] = confidence
            section["presented_confidence"] = confidence

    output["express_client_report_quality"] = {
        "status": "normalized",
        "version": VERSION,
        "punctuation_spacing_normalized": True,
        "assurance_confidence_consistent": True,
        "gitleaks_timeout_zero_count_removed": True,
        "bandit_failure_explicit": True,
        "eslint_not_configured_explicit": True,
        "human_review_required": bool(output.get("human_review_required", True)),
        "client_delivery_allowed": bool(output.get("client_delivery_allowed", False)),
    }
    return output


def _compact_risk(value: Any, section: dict[str, Any]) -> str:
    if section.get("section_group") == "assurance_ledger":
        return "REVIEW ONLY"
    if section.get("section_group") == "review_delivery":
        return "APPROVED" if section.get("approval_status") == "approved" else "DELIVERY BLOCKED"
    normalized = _text(value, 120).upper()
    replacements = {
        "HUMAN TRIAGE REQUIRED": "TRIAGE REQUIRED",
        "DELIVERY BLOCKED PENDING APPROVAL": "DELIVERY BLOCKED",
        "NO MATERIAL FINDING": "NO MATERIAL RISK",
        "EVIDENCE LIMITATION": "EVIDENCE LIMITED",
    }
    return replacements.get(normalized, normalized or "REVIEW REQUIRED")


def _quality_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    original: Callable[[dict[str, Any]], list[dict[str, Any]]] = getattr(_quality_records, "_nico_original")
    records = original(result)
    sections = _section_map(result)
    for record in records:
        section_id = _text(record.get("section_id"), 100).casefold()
        section = sections.get(section_id, {})
        assurance = _text(record.get("assurance") or section.get("assurance_label"), 80).upper() or "UNVERIFIED"
        record["assurance"] = assurance
        record["confidence"] = _confidence_for_assurance(assurance)
        record["risk_display"] = _compact_risk(record.get("canonical_status"), section)
    return records


def _styles() -> dict[str, Any]:
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("QualityTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=21, leading=24, textColor=colors.HexColor("#0f172a"), spaceAfter=8),
        "h2": ParagraphStyle("QualityH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=13, textColor=colors.HexColor("#075985"), spaceBefore=5, spaceAfter=3),
        "body": ParagraphStyle("QualityBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.1, leading=10.3, textColor=colors.HexColor("#334155"), spaceAfter=4),
        "small": ParagraphStyle("QualitySmall", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.15, leading=8.9, textColor=colors.HexColor("#475569"), spaceAfter=2.5),
        "label": ParagraphStyle("QualityLabel", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=6.9, leading=8.4, textColor=colors.HexColor("#64748b")),
        "callout": ParagraphStyle("QualityCallout", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=8.1, leading=10.2, textColor=colors.HexColor("#075985"), backColor=colors.HexColor("#e0f2fe"), borderColor=colors.HexColor("#38bdf8"), borderWidth=.7, borderPadding=7, spaceAfter=7),
        "warning": ParagraphStyle("QualityWarning", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=8.0, leading=10.1, textColor=colors.HexColor("#854d0e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=.7, borderPadding=7, spaceAfter=7),
    }


def _p(value: Any, style: Any):
    from reportlab.platypus import Paragraph

    return Paragraph(html.escape(_text(value)), style)


def _table(rows: list[list[Any]], widths: list[float], *, repeat_rows: int = 1):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    widget = Table(rows, colWidths=widths, repeatRows=repeat_rows, hAlign="LEFT")
    commands: list[tuple[Any, ...]] = [
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]
    if repeat_rows:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")),
            ]
        )
        for row in range(1, len(rows)):
            if row % 2 == 0:
                commands.append(("BACKGROUND", (0, row), (-1, row), colors.HexColor("#f8fafc")))
    widget.setStyle(TableStyle(commands))
    return widget


def _overview_pdf(result: dict[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Spacer

    records = _quality_records(result)
    styles = _styles()
    rows = [[_p("Control", styles["label"]), _p("Technical score", styles["label"]), _p("Technical band", styles["label"]), _p("Evidence assurance", styles["label"]), _p("Risk disposition", styles["label"])]]
    for item in records:
        rows.append([
            _p(item.get("label"), styles["small"]),
            _p(item.get("score_label"), styles["small"]),
            _p(item.get("band"), styles["small"]),
            _p(item.get("assurance"), styles["small"]),
            _p(item.get("risk_display"), styles["small"]),
        ])
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=.45*inch, leftMargin=.45*inch, topMargin=.48*inch, bottomMargin=.58*inch, title="NICO Express Technical Score and Assurance", author="NICO", invariant=1)
    story: list[Any] = [
        _p("Technical Score and Evidence Assurance", styles["title"]),
        _p("Technical score, evidence assurance, and risk disposition are independent. A strong technical score can remain review-limited without being recolored as weak. Delivery approval remains a separate authorized human decision.", styles["callout"]),
        Spacer(1, .04*inch),
        _table(rows, [2.15*inch, .95*inch, 1.0*inch, 1.35*inch, 1.55*inch]),
        Spacer(1, .12*inch),
        _p("Reading the scorecard", styles["h2"]),
        _p("Technical band reflects the measured score. Evidence assurance reflects whether the retained proof is complete and trustworthy. Risk disposition indicates the action still required. Supplemental scanner execution and review approval remain outside technical maturity.", styles["body"]),
    ]
    doc.build(story)
    return buffer.getvalue()


def _contribution_pdf(result: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import Flowable, SimpleDocTemplate, Spacer

    class ScoreBar(Flowable):
        def __init__(self, score: Any, tone: str, width: float = 104.0, height: float = 8.0) -> None:
            super().__init__()
            self.score = max(0.0, min(100.0, float(score or 0)))
            self.tone = tone
            self.width = width
            self.height = height

        def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
            return self.width, self.height

        def draw(self) -> None:
            palette = {"green": "#059669", "yellow": "#d97706", "red": "#dc2626", "gray": "#64748b", "blue": "#0284c7"}
            self.canv.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.canv.setFillColor(colors.HexColor("#f8fafc"))
            self.canv.roundRect(0, 0, self.width, self.height, 2, stroke=1, fill=1)
            fill_width = self.width * self.score / 100.0
            if fill_width:
                self.canv.setFillColor(colors.HexColor(palette.get(self.tone, "#64748b")))
                self.canv.roundRect(0, 0, fill_width, self.height, 2, stroke=0, fill=1)

    records = [item for item in _quality_records(result) if item.get("directly_scored")]
    styles = _styles()
    rows = [[_p("Control", styles["label"]), _p("Technical", styles["label"]), _p("Score contribution", styles["label"]), _p("Evidence assurance", styles["label"])]]
    constraints: list[str] = []
    for item in records:
        score = int(item.get("score") or 0)
        rows.append([
            _p(item.get("label"), styles["small"]),
            _p(f"{item.get('band')} · {item.get('score_label')}", styles["small"]),
            ScoreBar(score, str(item.get("score_tone") or "gray")),
            _p(item.get("assurance"), styles["small"]),
        ])
        rationale = _text(item.get("rationale"), 500)
        if rationale and "no material" not in rationale.casefold():
            constraints.append(f"{item.get('label')}: {rationale}")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=.48*inch, leftMargin=.48*inch, topMargin=.48*inch, bottomMargin=.58*inch, title="NICO Express Score Contribution and Assurance", author="NICO", invariant=1)
    story: list[Any] = [
        _p("Score Contribution and Assurance Constraints", styles["title"]),
        _p("Bar width and color represent technical score only. Evidence assurance remains separate and never recolors a strong technical score.", styles["callout"]),
        _table(rows, [2.15*inch, 1.35*inch, 1.65*inch, 1.55*inch]),
        Spacer(1, .10*inch),
        _p("Material score constraints", styles["h2"]),
    ]
    story.extend(_p(f"• {item}", styles["small"]) for item in constraints[:5])
    if not constraints:
        story.append(_p("No evidence-specific score deduction was retained.", styles["small"]))
    doc.build(story)
    return buffer.getvalue()


def _decision_pdf(result: dict[str, Any], section_id: str, title: str) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether, SimpleDocTemplate, Spacer
    from nico import express_pdf_score_assurance_v1 as target

    section = target._section(result, section_id)
    record = next((item for item in _quality_records(result) if item.get("section_id") == section_id), {})
    styles = _styles()

    limits = {
        "code_audit": (5, 3, 2),
        "dependency_health": (6, 3, 2),
        "secrets_review": (6, 4, 2),
        "static_analysis": (6, 4, 2),
        "ci_cd": (6, 3, 2),
        "architecture_debt": (6, 5, 2),
        "velocity_complexity": (6, 3, 2),
    }
    evidence_limit, finding_limit, limitation_limit = limits.get(section_id, (6, 4, 2))

    def bullets(values: Any, maximum: int) -> list[Any]:
        items = _unique(values)
        if not items:
            return [_p("No retained item.", styles["small"])]
        output = [_p(f"• {item}", styles["small"]) for item in items[:maximum]]
        if len(items) > maximum:
            output.append(_p(f"• {len(items) - maximum} additional item(s) are retained in the evidence appendix and machine-readable package.", styles["small"]))
        return output

    scored = bool(record.get("directly_scored"))
    treatment = "Canonical scored control" if scored else "Supplemental review control"
    summary = _table(
        [
            [_p("Technical score", styles["label"]), _p(record.get("score_label") or "NOT SCORED", styles["body"]), _p("Technical band", styles["label"]), _p(record.get("band") or "NOT SCORED", styles["body"])],
            [_p("Evidence assurance", styles["label"]), _p(record.get("assurance") or "UNVERIFIED", styles["body"]), _p("Risk disposition", styles["label"]), _p(record.get("risk_display") or "REVIEW REQUIRED", styles["body"])],
            [_p("Treatment", styles["label"]), _p(treatment, styles["body"]), _p("Delivery", styles["label"]), _p("Pending authorized approval", styles["body"])],
        ],
        [1.15*inch, 2.35*inch, 1.15*inch, 2.35*inch],
        repeat_rows=0,
    )
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=.55*inch, leftMargin=.55*inch, topMargin=.5*inch, bottomMargin=.62*inch, title=title, author="NICO", invariant=1)
    story: list[Any] = [
        _p(title, styles["title"]),
        KeepTogether([summary, Spacer(1, .07*inch), _p(section.get("summary") or "No section summary retained.", styles["body"])]),
        _p("Exact evidence", styles["h2"]),
        *bullets(section.get("evidence"), evidence_limit),
        _p("Open findings", styles["h2"]),
        *bullets(section.get("findings"), finding_limit),
        _p("Evidence limitations", styles["h2"]),
        *bullets(section.get("unavailable"), limitation_limit),
        _p("Score and assurance rationale", styles["h2"]),
        _p(record.get("rationale") or "No material score constraint retained.", styles["body"]),
        _p("Technical score, evidence assurance, risk disposition, and client-delivery approval remain independent. Full evidence remains available in the immutable package.", styles["callout"]),
    ]
    doc.build(story)
    return buffer.getvalue()


def _dossier_pdf(result: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from nico import express_report_dossier_export_v15 as target
    from nico.express_report_finding_dossiers_v15 import report_labels

    locale = target._locale(result)
    labels = report_labels(locale)
    dossiers = target._ordered_dossiers(result)
    detailed = dossiers[:5]
    remaining = dossiers[5:]
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=.55*inch, leftMargin=.55*inch, topMargin=.48*inch, bottomMargin=.58*inch, title=labels["title"], author="NICO", invariant=1)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("PremiumDossierTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=18, leading=21, textColor=colors.HexColor("#0f172a"), spaceAfter=6)
    h2 = ParagraphStyle("PremiumDossierH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=13, textColor=colors.HexColor("#075985"), spaceBefore=5, spaceAfter=3)
    body = ParagraphStyle("PremiumDossierBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.2, leading=10.4, textColor=colors.HexColor("#334155"), spaceAfter=4)
    small = ParagraphStyle("PremiumDossierSmall", parent=body, fontSize=7.2, leading=9.0, textColor=colors.HexColor("#475569"), spaceAfter=3)

    def p(value: Any, style: Any = body) -> Paragraph:
        return Paragraph(html.escape(_text(value, 2200)), style)

    intro = (
        "The PDF presents the highest-priority decision records at readable size. The complete finding set, exact locations, and full evidence remain in Markdown, HTML, JSON, and the immutable ledger."
        if locale == "en"
        else "El PDF presenta los registros de decisión de mayor prioridad en un tamaño legible. El conjunto completo, las ubicaciones exactas y toda la evidencia permanecen en Markdown, HTML, JSON y el libro mayor inmutable."
    )
    story: list[Any] = []
    if not detailed:
        story.extend([p(f"{labels['finding_dossier']} Appendix", title_style), p(labels["human_review"], h2), p(intro)])
    for index, dossier in enumerate(detailed):
        if index == 0:
            story.extend([p(f"{labels['finding_dossier']} Appendix", title_style), p(labels["human_review"], h2), p(intro), Spacer(1, .06*inch)])
        story.append(p(f"{dossier.finding_id} — {dossier.title}", h2))
        metadata = Table(
            [
                [p("Section", small), p(dossier.section_id, small), p("Severity", small), p(str(dossier.severity).upper(), small)],
                [p("Confidence", small), p(dossier.confidence, small), p("Disposition", small), p(dossier.disposition, small)],
                [p("Owner", small), p(dossier.owner, small), p("Effort", small), p(dossier.effort, small)],
            ],
            colWidths=[.8*inch, 2.6*inch, .8*inch, 2.8*inch],
            style=TableStyle([
                ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#e0f2fe")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]),
        )
        story.extend([
            metadata,
            Spacer(1, .08*inch),
            p(labels["business_impact"], h2),
            p(dossier.business_impact),
            p("Evidence", h2),
            *[p(f"• {item}", small) for item in list(dossier.evidence or [])[:3]],
            p(labels["repair_specification"], h2),
            p(dossier.repair_specification),
            p(labels["verification"], h2),
            p(dossier.verification, small),
            p(labels["rollback"], h2),
            p(dossier.rollback, small),
            p(labels["residual_risk"], h2),
            p(dossier.residual_risk, small),
        ])
        if index < len(detailed) - 1:
            story.append(PageBreak())

    if remaining:
        severity_counts = Counter(_text(item.severity).casefold() or "pending" for item in remaining)
        section_counts = Counter(_text(item.section_id) or "unknown" for item in remaining)
        story.extend([
            Spacer(1, .12*inch),
            p("Remaining finding inventory", h2),
            p(
                f"{len(remaining)} additional decision records remain in the complete package. "
                f"Severity inventory: {', '.join(f'{key}={value}' for key, value in sorted(severity_counts.items()))}. "
                f"Section inventory: {', '.join(f'{key}={value}' for key, value in sorted(section_counts.items()))}.",
                small,
            ),
        ])
    doc.build(story)
    return buffer.getvalue()


def _quality_visual_qa(pdf_bytes: bytes, result: dict[str, Any]) -> dict[str, Any]:
    original: Callable[[bytes, dict[str, Any]], dict[str, Any]] = getattr(_quality_visual_qa, "_nico_original")
    base = dict(original(pdf_bytes, result))
    issues = [
        item
        for item in list(base.get("issues") or [])
        if not str(item).startswith("Express page count ")
        and "Required en report label missing: Transparent Technical Score" not in str(item)
    ]
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_text = [_text(page.extract_text() or "", 200_000) for page in reader.pages]
    full_text = "\n".join(page_text)
    page_count = len(page_text)
    if not 16 <= page_count <= 28:
        issues.append(f"Express page count {page_count} is outside the quality range 16-28.")
    near_blank = [index + 1 for index, text in enumerate(page_text[1:], start=1) if len(text) < 150]
    if near_blank:
        issues.append(f"Sparse or orphan report pages detected: {near_blank}.")
    forbidden = {
        "SUPPLEMENTA L": "Split SUPPLEMENTAL label detected.",
        "evidence,score": "Missing space after comma detected.",
        "disposition,repair": "Missing space after comma detected.",
        "Gitleaks timed out with 0 retained": "Misleading zero-count Gitleaks timeout wording detected.",
        "Accepted current-run execution evidence remains unresolved for: eslint": "ESLint not-configured state was relabeled unavailable.",
    }
    for marker, issue in forbidden.items():
        if marker.casefold() in full_text.casefold():
            issues.append(issue)
    for heading in (
        "Technical Score and Evidence Assurance",
        "Score Contribution and Assurance Constraints",
        "Integrity, Independence, and Reviewer Record",
        "Finding Dossier Appendix",
    ):
        if heading not in full_text:
            issues.append(f"Required premium report section missing: {heading}.")
    base.update(
        {
            "status": "pass" if not issues else "fail",
            "version": VERSION,
            "page_count": page_count,
            "sparse_pages": near_blank,
            "issues": list(dict.fromkeys(issues)),
            "client_delivery_allowed": not issues and not bool(result.get("human_review_required", True)),
            "premium_layout_verified": not issues,
        }
    )
    return base


def install_express_report_quality_v47() -> dict[str, Any]:
    from nico import express_assurance_projection_compat_v45 as compat
    from nico import express_pdf_score_assurance_v1 as pdf_score
    from nico import express_report_dossier_export_v15 as dossier
    from nico import express_report_visual_qa_v16 as visual
    from nico import report_semantic_cleanup_v46 as semantic

    changed = 0
    semantic.normalize_final_report_semantics = normalize_client_report_quality_v47
    compat.normalize_final_report_semantics = normalize_client_report_quality_v47

    if pdf_score._records is not _quality_records:
        setattr(_quality_records, "_nico_original", pdf_score._records)
        pdf_score._records = _quality_records
        changed += 1
    if pdf_score._overview_pdf is not _overview_pdf:
        pdf_score._overview_pdf = _overview_pdf
        changed += 1
    if pdf_score._contribution_pdf is not _contribution_pdf:
        pdf_score._contribution_pdf = _contribution_pdf
        changed += 1
    if pdf_score._decision_pdf is not _decision_pdf:
        pdf_score._decision_pdf = _decision_pdf
        changed += 1
    if dossier._dossier_pdf is not _dossier_pdf:
        dossier._dossier_pdf = _dossier_pdf
        changed += 1

    if visual.validate_express_pdf is not _quality_visual_qa:
        setattr(_quality_visual_qa, "_nico_original", visual.validate_express_pdf)
        visual.validate_express_pdf = _quality_visual_qa
        dossier.validate_express_pdf = _quality_visual_qa
        changed += 1

    return {
        "status": "installed" if changed else "already_installed",
        "version": VERSION,
        "functions_rebound": changed,
        "premium_scorecard_layout": True,
        "one_page_control_records": True,
        "readable_paginated_appendix": True,
        "orphan_page_detection": True,
        "punctuation_spacing_normalized": True,
        "assurance_confidence_consistent": True,
        "scanner_timeout_language_reconciled": True,
        "eslint_not_configured_preserved": True,
        "full_machine_readable_evidence_preserved": True,
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_express_report_quality_v47",
    "normalize_client_report_quality_v47",
]
