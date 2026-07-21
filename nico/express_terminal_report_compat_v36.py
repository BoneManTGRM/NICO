from __future__ import annotations

import html
import io
import re
from typing import Any

VERSION = "nico.express_terminal_report_compat.v36"
_PATCH_MARKER = "_nico_express_terminal_report_compat_v36"
_STATUS_SCORE_RE = re.compile(r"\b(GREEN|YELLOW|RED)\s+(\d{1,3})(?!\s*/\s*100)", re.I)
_EXACT_STATUS_RE = re.compile(r"\bstatus\s*[=:]\s*(?:completed|failed|timeout|timed[_ -]?out|unavailable|error)", re.I)
_SHA_RE = re.compile(r"\b[0-9a-f]{40}\b", re.I)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _merge_lists(*groups: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in _list(group):
            item = str(value or "").strip()
            key = " ".join(item.split()).casefold()
            if item and key not in seen:
                seen.add(key)
                output.append(item)
    return output


def _section_text(section: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("evidence", "findings", "unavailable", "limitations"):
        values.extend(str(value or "") for value in _list(section.get(key)))
    return "\n".join(values)


def _has_authoritative_current_run_evidence(result: dict[str, Any]) -> bool:
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for statement in _section_text(section).splitlines():
            lowered = statement.casefold()
            immutable = bool(_SHA_RE.search(statement)) and "scan_id=" in lowered
            exact_scope = "exact-snapshot" in lowered or "current-run" in lowered
            if _EXACT_STATUS_RE.search(statement) and (immutable or exact_scope):
                return True
    return False


def _not_scored(section: dict[str, Any]) -> bool:
    section_id = _text(section.get("id")).casefold()
    if section_id in {"scanner_worker", "scanner_worker_evidence"}:
        return True
    if section_id in {"client_acceptance", "client_human_acceptance"}:
        status = _text(section.get("status") or section.get("acceptance_status")).casefold()
        return not bool(section.get("approved") or section.get("accepted") or status in {"approved", "accepted", "green"})
    return section.get("directly_scored") is False and section.get("presented_score", section.get("score")) is None


def _ensure_presented_fields(result: dict[str, Any]) -> None:
    from nico.express_terminal_report_truth_v34 import normalize_section_aliases

    normalize_section_aliases(result)
    scores: list[int] = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        if _not_scored(section):
            continue
        score = section.get("presented_score", section.get("score"))
        if isinstance(score, (int, float)):
            value = int(score)
            section.setdefault("source_score", int(section.get("score") or value))
            section.setdefault("presented_score", value)
            section.setdefault("presented_status", _text(section.get("status") or "unknown").casefold())
            section.setdefault("presented_confidence", section.get("confidence") or "standard")
            section.setdefault("directly_scored", True)
            section.setdefault("score_deductions", [])
            scores.append(value)
    maturity = result.get("maturity_signal") if isinstance(result.get("maturity_signal"), dict) else {}
    existing = result.get("evidence_adjusted_score", maturity.get("presented_score"))
    if isinstance(existing, (int, float)):
        adjusted = int(existing)
    else:
        adjusted = round(sum(scores) / len(scores)) if scores else int(maturity.get("score") or 0)
    result["evidence_adjusted_score"] = adjusted
    if isinstance(maturity, dict):
        maturity.setdefault("source_score", maturity.get("score"))
        maturity.setdefault("presented_score", adjusted)


def _transparent_summary(result: dict[str, Any]) -> str:
    maturity = result.get("maturity_signal") if isinstance(result.get("maturity_signal"), dict) else {}
    source = maturity.get("source_score", maturity.get("score"))
    level = _text(maturity.get("level") or "Unknown")
    adjusted = result.get("evidence_adjusted_score", maturity.get("presented_score"))
    adjusted_text = f"{int(adjusted)}/100" if isinstance(adjusted, (int, float)) else "not calculated"
    repository = _text(result.get("repository") or result.get("source_scope") or "the authorized repository")
    return (
        f"NICO completed an authorized hosted Express Technical Health Assessment for {repository}. "
        f"The baseline source maturity is {level} ({source}/100), while the evidence-adjusted score is {adjusted_text}. "
        "When authoritative exact-run scanner records are present, failed, timed-out, unavailable, and triage-required evidence produces explicit deductions; established legacy trust caps are not deducted twice. "
        "Supplemental scanner evidence and pending client acceptance are NOT SCORED. "
        "Client delivery remains blocked pending exact-snapshot human review."
    )


def _sanitize_stale_status_score_phrases(markdown: str) -> str:
    return _STATUS_SCORE_RE.sub(lambda match: f"{match.group(2)}/100 {match.group(1).upper()}", markdown)


def _pdf_page(result: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from nico.express_not_scored_pdf_append_v35 import _controls

    controls = _controls(result)
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.66 * inch,
        title="NICO Express Non-Scored Controls",
        author="NICO",
        invariant=1,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("NotScoredTitleV36", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=25, textColor=colors.HexColor("#0f172a"), spaceAfter=9)
    body = ParagraphStyle("NotScoredBodyV36", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.2, leading=10.4, textColor=colors.HexColor("#334155"), spaceAfter=4)
    label = ParagraphStyle("NotScoredLabelV36", parent=body, fontName="Helvetica-Bold", fontSize=7.2, leading=9.0, textColor=colors.HexColor("#64748b"))

    def p(value: Any, style: Any = body) -> Paragraph:
        return Paragraph(html.escape(_text(value)), style)

    rows = [[p("Control", label), p("Status", label), p("Score treatment", label), p("Reason", label)]]
    for item in controls:
        rows.append([p(item["label"]), p(item["status"]), p(item["score"]), p(item["reason"])])
    table = Table(rows, colWidths=[1.75 * inch, 1.25 * inch, 1.15 * inch, 2.9 * inch], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    document.build([
        p("Non-Scored Controls and Approval Boundary", title),
        p("These controls remain visible in every report format but are excluded from automated maturity scoring. Numeric score placeholders are prohibited."),
        Spacer(1, 0.08 * inch),
        table,
        Spacer(1, 0.1 * inch),
        p("Human review is required. Client delivery remains blocked until the exact-snapshot approval record is complete."),
    ])
    return buffer.getvalue()


def install_express_terminal_report_compat_v36() -> dict[str, Any]:
    from nico import express_client_report_postprocessor_v27 as postprocessor
    from nico import express_cross_format_contract_v24 as cross_format
    from nico import express_evidence_specific_scoring_v33 as scoring
    from nico import express_not_scored_pdf_append_v35 as pdf_append
    from nico import express_scanner_disposition_truth_v1 as scanner
    from nico import express_terminal_report_truth_v34 as terminal
    from nico import final_report_consistency as final

    if getattr(terminal._finalize_result_truth, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    original_markdown = terminal.build_presentation_markdown

    def finalize_result_truth(result: dict[str, Any]) -> None:
        preserved = {
            key: list(result.get(key) or [])
            for key in ("priority_actions", "quick_wins", "medium_term_plan", "resourcing_recommendation", "risk_register", "verification_checklist")
        }
        authoritative = _has_authoritative_current_run_evidence(result)
        terminal.normalize_section_aliases(result)
        if authoritative:
            scanner.reconcile_express_scanner_dispositions(result)
            scoring.reconcile_express_scores(result)
        else:
            _ensure_presented_fields(result)
        result["executive_summary"] = _transparent_summary(result)
        postprocessor.prepare_express_client_report(result)
        for key, values in preserved.items():
            result[key] = _merge_lists(values, result.get(key))
        result["executive_summary"] = _transparent_summary(result)
        scoring.rewrite_cross_format_scores(result)
        postprocessor.postprocess_express_client_reports(result)
        scoring.rewrite_cross_format_scores(result)
        cross_format.build_cross_format_contract(result)
        result["express_terminal_report_truth"] = {
            "status": "complete",
            "version": VERSION,
            "authoritative_current_run_scoring": authoritative,
            "legacy_truth_caps_preserved_without_double_deduction": True,
            "scanner_alias_normalized": True,
            "not_scored_numeric_leakage_blocked": True,
            "service_tier_guidance_preserved": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    def presentation_markdown(result: dict[str, Any]) -> str:
        markdown = original_markdown(result)
        return _sanitize_stale_status_score_phrases(markdown)

    setattr(finalize_result_truth, _PATCH_MARKER, True)
    setattr(finalize_result_truth, "_nico_previous", terminal._finalize_result_truth)
    setattr(presentation_markdown, _PATCH_MARKER, True)
    setattr(presentation_markdown, "_nico_previous", original_markdown)
    terminal._finalize_result_truth = finalize_result_truth
    terminal.build_presentation_markdown = presentation_markdown
    final.build_markdown = presentation_markdown
    pdf_append._page = _pdf_page
    return {
        "status": "installed",
        "version": VERSION,
        "legacy_truth_caps_preserved": True,
        "authoritative_exact_run_deductions_preserved": True,
        "service_tier_guidance_preserved": True,
        "stale_status_score_phrase_sanitization": True,
        "pdf_not_scored_layout_repaired": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_express_terminal_report_compat_v36"]
