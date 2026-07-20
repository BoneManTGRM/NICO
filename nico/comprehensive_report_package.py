from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Iterable

VERSION = "nico.comprehensive_report_package.v1"

_STAGE_TITLES = {
    "authorization_and_scope": "Authorization and Scope",
    "immutable_repository_snapshot": "Immutable Repository Snapshot",
    "repository_and_delivery_evidence": "Repository and Delivery Evidence",
    "dependency_security_static_analysis": "Dependency, Security, and Static Analysis",
    "ci_cd_architecture_complexity_velocity": "CI/CD, Architecture, Complexity, and Velocity",
    "evidence_reconciliation_and_scoring": "Evidence Reconciliation and Scoring",
    "decision_report_generation": "Core Decision Report",
    "deep_scanner_triage": "Deep Scanner Triage",
    "functional_qa": "Functional QA",
    "platform_parity": "Platform Parity",
    "deployment_and_infrastructure": "Deployment and Infrastructure",
    "architecture_and_data_flow": "Architecture and Data Flow",
    "developer_delivery_process": "Developer Delivery Process",
    "stakeholder_and_business_alignment": "Stakeholder and Business Alignment",
    "requirements_traceability": "Requirements Traceability",
    "historical_trends_and_change_failure": "Historical Trends and Change Failure",
    "six_month_roadmap": "Six-Month Roadmap",
    "staffing_sequencing_and_cost": "Staffing, Sequencing, and Cost",
    "risk_reduction_and_executive_briefing": "Risk Reduction and Executive Briefing",
    "final_comprehensive_report_generation": "Final Comprehensive Report",
    "cross_format_truth_verification": "Cross-Format Truth Verification",
    "human_review_request": "Human Review Request",
    "client_acceptance_pending": "Client Acceptance Pending",
}


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any, limit: int = 1200) -> str:
    normalized = " ".join(str(value or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items() if str(key) not in {"pdf_base64", "html", "markdown"}}
    if isinstance(value, (list, tuple, set)):
        return [_safe(item) for item in value]
    return _text(value)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _flatten(value: Any, *, prefix: str = "", depth: int = 0, maximum: int = 80) -> list[str]:
    if depth > 4:
        return []
    output: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"pdf_base64", "markdown", "html", "scanner_results", "stage_results"}:
                continue
            label = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(item, (dict, list, tuple)):
                output.extend(_flatten(item, prefix=label, depth=depth + 1, maximum=maximum))
            else:
                text = _text(item, 500)
                if text:
                    output.append(f"{label}: {text}")
            if len(output) >= maximum:
                break
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            label = f"{prefix}[{index}]" if prefix else str(index + 1)
            if isinstance(item, (dict, list, tuple)):
                output.extend(_flatten(item, prefix=label, depth=depth + 1, maximum=maximum))
            else:
                text = _text(item, 500)
                if text:
                    output.append(f"{label}: {text}")
            if len(output) >= maximum:
                break
    elif value not in (None, ""):
        output.append(f"{prefix}: {_text(value, 500)}" if prefix else _text(value, 500))
    return output[:maximum]


def _stage_summary(stage_id: str, result: dict[str, Any]) -> dict[str, Any]:
    evidence = result.get("evidence")
    evidence_lines = _flatten(evidence, maximum=48)
    if not evidence_lines:
        evidence_lines = _flatten(
            {
                key: value
                for key, value in result.items()
                if key
                not in {
                    "stage_id",
                    "status",
                    "message",
                    "summary",
                    "run_id",
                    "repository",
                    "commit_sha",
                    "evidence_ledger_id",
                    "human_review_required",
                    "client_delivery_allowed",
                    "report_package",
                    "reports",
                    "assessment",
                }
            },
            maximum=48,
        )
    unavailable = [
        _text(item, 700)
        for item in result.get("unavailable_data_notes") or result.get("unavailable") or []
        if _text(item)
    ]
    findings = [
        _text(item, 700)
        for item in result.get("findings") or []
        if _text(item)
    ]
    return {
        "stage_id": stage_id,
        "title": _STAGE_TITLES.get(stage_id, stage_id.replace("_", " ").title()),
        "status": _text(result.get("status") or "unknown", 40).lower(),
        "summary": _text(result.get("summary") or result.get("message") or "Stage evidence was recorded.", 1200),
        "evidence": evidence_lines,
        "findings": findings,
        "unavailable": unavailable,
    }


def _assessment(stage_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    scoring = stage_results.get("evidence_reconciliation_and_scoring") or {}
    assessment = scoring.get("assessment")
    if isinstance(assessment, dict):
        return deepcopy(assessment)
    return {
        "status": "not_scored",
        "executive_summary": "A canonical technical score was not available. The report retains stage evidence and requires human review.",
        "maturity_signal": {"level": "Pending", "score": None},
        "sections": [],
        "unavailable_data_notes": ["Canonical scoring evidence was unavailable at report-generation time."],
        "human_review_required": True,
        "client_ready": False,
    }


def _decision_summary(identity: dict[str, Any], assessment: dict[str, Any], stages: list[dict[str, Any]]) -> str:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    level = _text(maturity.get("level") or "Pending", 80)
    score = maturity.get("presented_score", maturity.get("score"))
    score_text = f"{int(score)}/100" if isinstance(score, (int, float)) else "not scored"
    limited = sum(bool(item["unavailable"]) for item in stages)
    blocked = [item["title"] for item in stages if item["status"] in {"blocked", "failed", "unavailable", "timed_out"}]
    boundary = (
        f"{len(blocked)} stage(s) remain blocked or unavailable: {', '.join(blocked[:4])}."
        if blocked
        else "Every automated stage represented in this package completed without a terminal execution failure."
    )
    return (
        f"NICO completed a native Comprehensive Technical Assessment for {_text(identity.get('repository'))} at immutable commit "
        f"{_text(identity.get('commit_sha'))}. The evidence-bound maturity signal is {level} ({score_text}). "
        f"{limited} stage(s) disclose unavailable or limited evidence. {boundary} "
        "The package is a review-gated draft: automated evidence and recommendations are not client approval or delivery authorization."
    )


def _markdown(identity: dict[str, Any], assessment: dict[str, Any], stages: list[dict[str, Any]], generated_at: str) -> str:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    score = maturity.get("presented_score", maturity.get("score"))
    score_text = f"{int(score)}/100" if isinstance(score, (int, float)) else "NOT SCORED"
    lines = [
        f"# NICO Comprehensive Technical Assessment — {_text(identity.get('repository'))}",
        "",
        f"Generated: {generated_at}",
        f"Service ID: comprehensive",
        f"Run ID: {_text(identity.get('run_id'))}",
        f"Immutable commit SHA: {_text(identity.get('commit_sha'))}",
        f"Evidence ledger ID: {_text(identity.get('evidence_ledger_id'))}",
        f"Customer scope: {_text(identity.get('customer_id'))}",
        f"Project scope: {_text(identity.get('project_id'))}",
        "",
        "## Executive Decision Brief",
        _decision_summary(identity, assessment, stages),
        "",
        "## Decision Boundary",
        "Human review is required. Client delivery is blocked. Missing evidence is disclosed and is never converted into a passing claim.",
        "",
        "## Canonical Maturity Signal",
        f"- Level: {_text(maturity.get('level') or 'Pending')}",
        f"- Presented score: {score_text}",
        f"- Evidence readiness: {_text(maturity.get('evidence_readiness_score') or 'Pending')}",
        "",
        "## Technical Scorecard",
    ]
    sections = assessment.get("sections") if isinstance(assessment.get("sections"), list) else []
    if sections:
        for item in sections:
            if not isinstance(item, dict):
                continue
            section_score = item.get("presented_score", item.get("score"))
            score_label = f"{int(section_score)}/100" if isinstance(section_score, (int, float)) else "NOT SCORED"
            status = _text(item.get("presented_status") or item.get("status") or "unknown").upper()
            lines.append(f"- **{_text(item.get('label') or item.get('id'))}** — {status} — {score_label}")
    else:
        lines.append("- Canonical scorecard unavailable; see the evidence limitations below.")

    lines += ["", "## Comprehensive Modules"]
    for stage in stages:
        lines += [
            "",
            f"### {stage['title']} — {stage['status'].upper()}",
            stage["summary"],
            "",
            "Evidence:",
        ]
        if stage["evidence"]:
            lines.extend(f"- {item}" for item in stage["evidence"])
        else:
            lines.append("- No structured evidence line was retained for this stage.")
        if stage["findings"]:
            lines += ["", "Findings:"] + [f"- {item}" for item in stage["findings"]]
        if stage["unavailable"]:
            lines += ["", "Unavailable or limited evidence:"] + [f"- {item}" for item in stage["unavailable"]]

    unavailable = [
        _text(item, 900)
        for item in assessment.get("unavailable_data_notes") or []
        if _text(item)
    ]
    lines += [
        "",
        "## Assessment-Wide Limitations",
        *([f"- {item}" for item in unavailable] or ["- No assessment-wide limitation was recorded beyond stage-level disclosures."]),
        "",
        "## Human Review Checklist",
        "- [ ] Verify repository, run, commit, ledger, customer, and project identities.",
        "- [ ] Review every failed, timed-out, unavailable, and triage-required analyzer result.",
        "- [ ] Confirm the scorecard matches the evidence and all report formats.",
        "- [ ] Validate business context, requirements, roadmap, staffing, and cost assumptions.",
        "- [ ] Approve or reject the exact immutable report package before any client delivery.",
        "",
        "## Delivery Status",
        "**DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED**",
        "",
    ]
    return "\n".join(lines).strip() + "\n"


def _html(markdown: str, title: str) -> str:
    escaped = html.escape(markdown)
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{html.escape(title)}</title>
<style>body{{margin:0;background:#071124;color:#dbeafe;font:16px/1.6 Inter,system-ui,sans-serif}}main{{max-width:1080px;margin:0 auto;padding:48px 24px}}header{{padding:32px;border:1px solid #274060;border-radius:24px;background:#0d1a31;margin-bottom:24px}}h1{{margin:0;color:#fff}}.badge{{display:inline-block;margin-top:14px;padding:8px 12px;border:1px solid #f59e0b;border-radius:999px;color:#fde68a;background:#4a2406;font-weight:800}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;padding:32px;border:1px solid #274060;border-radius:24px;background:#0b172c;color:#dbeafe;font:14px/1.65 ui-monospace,SFMono-Regular,Menlo,monospace}}</style></head>
<body><main><header><h1>{html.escape(title)}</h1><span class=\"badge\">DRAFT · HUMAN REVIEW REQUIRED</span></header><pre>{escaped}</pre></main></body></html>"""


def _pdf(identity: dict[str, Any], assessment: dict[str, Any], stages: list[dict[str, Any]], generated_at: str) -> tuple[str | None, str | None, int]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            KeepTogether,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except Exception as exc:  # pragma: no cover - deployment dependency boundary
        return None, f"PDF export unavailable: {type(exc).__name__}", 0

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=28, leading=32, textColor=colors.HexColor("#0f172a"), alignment=TA_CENTER, spaceAfter=16)
    subtitle = ParagraphStyle("Subtitle", parent=styles["BodyText"], fontName="Helvetica", fontSize=12, leading=17, textColor=colors.HexColor("#334155"), alignment=TA_CENTER, spaceAfter=12)
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=colors.HexColor("#0f172a"), spaceAfter=12)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=colors.HexColor("#075985"), spaceBefore=8, spaceAfter=6)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.2, leading=13.5, textColor=colors.HexColor("#334155"), spaceAfter=6)
    small = ParagraphStyle("Small", parent=body, fontSize=7.8, leading=10.5, textColor=colors.HexColor("#475569"))
    warning = ParagraphStyle("Warning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=0.8, borderPadding=10, spaceBefore=12, spaceAfter=12)

    def p(value: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(html.escape(_text(value, 4000)), style)

    def bullets(values: Iterable[str], *, limit: int = 50) -> list[Paragraph]:
        items = [item for item in values if _text(item)][:limit]
        return [p(f"• {item}", small) for item in items] or [p("No structured item was retained.", small)]

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(0.55 * inch, 0.38 * inch, f"NICO Comprehensive · {_text(identity.get('run_id'), 60)} · DRAFT")
        canvas.drawRightString(7.95 * inch, 0.38 * inch, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.58 * inch,
        bottomMargin=0.62 * inch,
        title="NICO Comprehensive Technical Assessment",
        author="NICO",
        subject=f"Comprehensive assessment {_text(identity.get('run_id'))}",
        invariant=1,
    )
    story: list[Any] = [
        Spacer(1, 1.1 * inch),
        p("NICO", ParagraphStyle("Brand", parent=title_style, fontSize=18, textColor=colors.HexColor("#0284c7"))),
        p("Comprehensive Technical Assessment", title_style),
        p(_text(identity.get("repository")), subtitle),
        Spacer(1, 0.3 * inch),
        p(f"Immutable commit: {_text(identity.get('commit_sha'))}", subtitle),
        p(f"Run ID: {_text(identity.get('run_id'))}", subtitle),
        p(f"Generated: {generated_at}", subtitle),
        Spacer(1, 0.45 * inch),
        p("DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED", warning),
        PageBreak(),
        p("Executive Decision Brief", h1),
        p(_decision_summary(identity, assessment, stages), body),
        p("Decision Boundary", h2),
        p("The report is an evidence-bound draft. NICO has not approved findings, accepted business assumptions, or authorized delivery. Missing evidence remains visible and constrains conclusions.", body),
    ]

    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    score = maturity.get("presented_score", maturity.get("score"))
    score_text = f"{int(score)}/100" if isinstance(score, (int, float)) else "NOT SCORED"
    identity_rows = [
        ["Service", "Comprehensive", "Run ID", _text(identity.get("run_id"), 80)],
        ["Repository", _text(identity.get("repository"), 80), "Commit", _text(identity.get("commit_sha"), 80)],
        ["Customer", _text(identity.get("customer_id"), 80), "Project", _text(identity.get("project_id"), 80)],
        ["Maturity", _text(maturity.get("level") or "Pending", 80), "Score", score_text],
    ]
    identity_table = Table(identity_rows, colWidths=[0.85 * inch, 2.35 * inch, 0.8 * inch, 3.5 * inch])
    identity_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#e0f2fe")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [Spacer(1, 0.15 * inch), identity_table, PageBreak(), p("Canonical Technical Scorecard", h1)]

    sections = assessment.get("sections") if isinstance(assessment.get("sections"), list) else []
    score_rows = [["Control", "Status", "Score", "Summary"]]
    for item in sections:
        if not isinstance(item, dict):
            continue
        section_score = item.get("presented_score", item.get("score"))
        score_label = f"{int(section_score)}/100" if isinstance(section_score, (int, float)) else "NOT SCORED"
        score_rows.append([
            _text(item.get("label") or item.get("id"), 90),
            _text(item.get("presented_status") or item.get("status") or "unknown", 30).upper(),
            score_label,
            _text(item.get("summary"), 240),
        ])
    if len(score_rows) == 1:
        score_rows.append(["Canonical scoring", "PENDING", "NOT SCORED", "No canonical section scorecard was available."])
    score_table = Table(score_rows, colWidths=[1.5 * inch, 0.75 * inch, 0.75 * inch, 4.45 * inch], repeatRows=1)
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("FONTSIZE", (0, 0), (-1, -1), 7.2),
        ("LEADING", (0, 0), (-1, -1), 9.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [score_table]

    for stage in stages:
        story += [PageBreak(), p(stage["title"], h1)]
        status_table = Table([["Status", stage["status"].upper()], ["Stage ID", stage["stage_id"]]], colWidths=[1.0 * inch, 6.45 * inch])
        status_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story += [status_table, Spacer(1, 0.12 * inch), p(stage["summary"], body), p("Evidence", h2), *bullets(stage["evidence"], limit=60)]
        if stage["findings"]:
            story += [p("Findings", h2), *bullets(stage["findings"], limit=40)]
        if stage["unavailable"]:
            story += [p("Unavailable or Limited Evidence", h2), *bullets(stage["unavailable"], limit=40)]

    story += [
        PageBreak(),
        p("Human Review and Acceptance Gate", h1),
        p("The automated assessment is complete only as a draft. The following decisions remain human responsibilities:", body),
        *bullets([
            "Verify the exact repository, run, commit, evidence ledger, customer, and project identities.",
            "Triage every failed, timed-out, unavailable, and review-required scanner result.",
            "Validate business context, requirements, roadmap, staffing, sequencing, and cost assumptions.",
            "Confirm Markdown, HTML, JSON, and PDF show the same status and score truth.",
            "Approve or reject the immutable report package before creating any delivery access.",
        ]),
        p("DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED", warning),
    ]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf_bytes = buffer.getvalue()
    page_count = 0
    try:
        from pypdf import PdfReader
        page_count = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    except Exception:
        page_count = 0
    return base64.b64encode(pdf_bytes).decode("ascii"), None, page_count


def build_comprehensive_report_package(
    *,
    identity: dict[str, Any],
    stage_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    required_identity = {
        field: _text(identity.get(field), 180)
        for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id", "customer_id", "project_id")
    }
    missing = [field for field, value in required_identity.items() if not value]
    if missing:
        return {
            "status": "blocked",
            "reason": "missing_report_identity:" + ",".join(missing),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    generated_at = _now()
    ordered = [
        _stage_summary(stage_id, result)
        for stage_id, result in stage_results.items()
        if isinstance(result, dict) and stage_id != "final_comprehensive_report_generation"
    ]
    assessment = _assessment(stage_results)
    assessment["human_review_required"] = True
    assessment["client_ready"] = False
    assessment["client_delivery_allowed"] = False
    assessment["service_id"] = "comprehensive"
    assessment["repository"] = required_identity["repository"]
    assessment["commit_sha"] = required_identity["commit_sha"]
    assessment["run_id"] = required_identity["run_id"]
    assessment["executive_summary"] = _decision_summary(required_identity, assessment, ordered)

    markdown = _markdown(required_identity, assessment, ordered, generated_at)
    title = f"NICO Comprehensive Technical Assessment — {required_identity['repository']}"
    rendered_html = _html(markdown, title)
    pdf_base64, pdf_error, page_count = _pdf(required_identity, assessment, ordered, generated_at)
    pdf_bytes = base64.b64decode(pdf_base64) if pdf_base64 else b""
    report_id = f"comprehensive_report_{_canonical_hash({'identity': required_identity, 'stages': ordered})[:20]}"
    safe_repo = re.sub(r"[^A-Za-z0-9_.-]+", "-", required_identity["repository"]).strip("-") or "repository"
    filename = f"nico-comprehensive-assessment-{safe_repo}-{required_identity['run_id']}-DRAFT.pdf"
    canonical = {
        "service_id": "comprehensive",
        "identity": required_identity,
        "assessment": assessment,
        "stage_summaries": ordered,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    truth_sha = _canonical_hash(canonical)
    return {
        "status": "complete" if pdf_base64 and not pdf_error else "blocked",
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "report_id": report_id,
        "generated_at": generated_at,
        "identity": required_identity,
        "assessment": assessment,
        "stage_summary_count": len(ordered),
        "canonical_truth_sha256": truth_sha,
        "report_package": {
            "report_id": report_id,
            "markdown": markdown,
            "html": rendered_html,
            "pdf_base64": pdf_base64,
            "pdf_filename": filename,
            "pdf_error": pdf_error,
            "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else "",
            "pdf_page_count": page_count,
            "canonical_truth_sha256": truth_sha,
            "service_id": "comprehensive",
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "build_comprehensive_report_package"]
