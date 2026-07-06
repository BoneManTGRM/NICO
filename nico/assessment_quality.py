from __future__ import annotations

import base64
import html
import io
import re
from typing import Any


PDF_STYLE_VERSION = "professional_report_v10"


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    for item in result.get("sections", []) or []:
        if item.get("id") == section_id:
            return item
    return None


def _metadata_limited(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in ["github returned 403", "github returned 429", "api rate", "request limit", "abuse detection", "rate-limited", "rate limited"])


def _notes_limited(item: dict[str, Any] | None) -> bool:
    if not item:
        return False
    notes = list(item.get("unavailable", []) or []) + list(item.get("evidence", []) or [])
    return any(_metadata_limited(str(note)) for note in notes)


def _friendly_note(value: Any) -> str:
    text = str(value or "").replace("\u2014", "-").replace("\u2013", "-").replace("\u2022", "-")
    text = re.sub(r"<\s*br\s*/?\s*>", " ", text, flags=re.IGNORECASE)
    lower = text.lower()
    if "github returned 403" in lower or "github returned 429" in lower or "api rate" in lower or "abuse detection" in lower:
        prefix = "GitHub metadata was rate-limited during this run."
        if "workflow" in lower or "ci/cd" in lower or ".github/workflows" in lower:
            return "Workflow metadata was unavailable because GitHub rate-limited the request. Treat this section as degraded and rerun later or use authenticated GitHub access."
        if "pull" in lower or "pr" in lower:
            return "Pull-request metadata was unavailable because GitHub rate-limited the request. Do not treat missing PR metadata as proof of direct-to-main work."
        if "commit" in lower:
            return "Commit metadata was unavailable because GitHub rate-limited the request. Do not treat missing commit metadata as proof of inactivity."
        return f"{prefix} Rerun later or configure authenticated GitHub access for stronger confidence."
    text = re.sub(r"https?://\S+", "[link omitted]", text)
    text = re.sub(r"\{\s*\"documentation_url\".*", "GitHub returned a metadata access error; raw response omitted from client report.", text)
    return " ".join(text.split())


def _sanitize_list(items: list[Any]) -> list[str]:
    return _unique([_friendly_note(item) for item in items if _friendly_note(item)])


def _clean_text(value: Any, limit: int = 1200) -> str:
    text = _friendly_note(value)
    if len(text) > limit:
        return text[: max(0, limit - 18)].rstrip() + "... [truncated]"
    return text


def _status_from_score(score: int) -> str:
    if score >= 75:
        return "green"
    if score >= 45:
        return "yellow"
    return "red"


def _apply_score(item: dict[str, Any], score: int) -> None:
    item["score"] = max(0, min(100, int(score)))
    item["status"] = _status_from_score(item["score"])


def _status_color(status: str) -> str:
    status = (status or "").lower()
    if status == "green":
        return "#059669"
    if status == "yellow":
        return "#d97706"
    if status == "red":
        return "#dc2626"
    return "#64748b"


def _client_verdict(result: dict[str, Any]) -> dict[str, Any]:
    sections = [item for item in result.get("sections", []) if isinstance(item, dict)]
    red = sum(1 for item in sections if item.get("status") == "red")
    unavailable = sum(len(item.get("unavailable", []) or []) for item in sections)
    degraded = result.get("assessment_quality") == "degraded_metadata" or any(_notes_limited(item) for item in sections)
    blockers: list[str] = []
    if red:
        blockers.append(f"{red} red section(s) need triage before client-final delivery.")
    if degraded:
        blockers.append("GitHub metadata was degraded; rerun with authenticated metadata access before firm claims.")
    if unavailable:
        blockers.append("Unavailable evidence remains disclosed and must be reviewed.")
    return {"status": "human_review_required" if blockers else "review_ready", "blockers": blockers, "red_sections": red, "unavailable_items": unavailable, "confidence": "limited" if degraded else "standard"}


def _classify_secret_hit(note: str) -> str:
    lower = note.lower()
    if any(marker in lower for marker in ["private_key", "aws_access_key", "github_token"]):
        return "suspected_secret"
    if any(marker in lower for marker in ["tests/", "test_lab", "fake_", "fixture"]):
        return "test_fixture"
    if any(marker in lower for marker in ["docs/", ".env.example", "example"]):
        return "docs_example"
    if "generic_secret_assignment" in lower and any(marker in lower for marker in ["toke...oken", "api/main.py", "token"]):
        return "backend_token_variable"
    if "generic_secret_assignment" in lower:
        return "suspected_secret"
    return "review_required"


def _classify_static_hit(note: str) -> str:
    lower = note.lower()
    if any(marker in lower for marker in ["tests/", "test_lab", "sample_repo", "mock_"]):
        return "test_fixture"
    if any(marker in lower for marker in ["docs/", "readme"]):
        return "docs_example"
    if "nico/hosted_assessment.py:" in lower:
        return "scanner_pattern_definition"
    if "nico/cli.py:87:" in lower or "nico/cli.py:726:" in lower:
        return "scanner_or_test_fixture"
    return "production_source"


def _is_broad_dependency_note(note: str) -> bool:
    lower = note.lower()
    return "vulnerability record" in lower and any(op in note for op in [">=", "<=", "~=", ">", "<", "[standard]>="])


def _polish_secrets(item: dict[str, Any] | None) -> None:
    if not item:
        return
    evidence = list(item.get("evidence", []) or [])
    hit_notes = [note for note in evidence if ": potential " in note]
    classes = [_classify_secret_hit(note) for note in hit_notes]
    suspected = sum(1 for label in classes if label in {"suspected_secret", "review_required"})
    safe_review = len(classes) - suspected
    if hit_notes and suspected == 0:
        item["summary"] = "Secrets review classifies masked pattern hits before scoring so backend token variable names, fixtures, and examples are not treated as confirmed leaks."
        item["evidence"] = _unique(evidence + [f"Secret-pattern classification: confirmed=0, review-only={safe_review}, total={len(hit_notes)}.", "No confirmed exposed secret was identified by hosted masked pattern review; full git-history scanning is still required for final assurance."])
        item["findings"] = []
        _apply_score(item, max(int(item.get("score", 0)), 82))
    elif suspected:
        item["evidence"] = _unique(evidence + [f"Secret-pattern classification: suspected={suspected}, review-only={safe_review}, total={len(hit_notes)}."])
        _apply_score(item, max(45, 75 - suspected * 12))


def _polish_dependencies(item: dict[str, Any] | None) -> None:
    if not item:
        return
    evidence = list(item.get("evidence", []) or [])
    findings = list(item.get("findings", []) or [])
    broad = [note for note in _unique(evidence + findings) if _is_broad_dependency_note(note)]
    lockfile_missing = any("no javascript lockfile" in note.lower() for note in findings)
    confirmed = [note for note in findings if "vulnerability record" in note.lower() and note not in broad]
    if broad:
        item["evidence"] = _unique(evidence + ["Hosted OSV records based on manifest version ranges are broad-range warnings, not confirmed installed-package vulnerabilities. Use pip-audit/npm audit/lockfile evidence for client-final dependency claims."])
        item["findings"] = _unique([note for note in findings if note not in broad])
        if not confirmed:
            target = 68 if lockfile_missing else 76
            _apply_score(item, max(int(item.get("score", 0)), target))
    elif not confirmed and evidence:
        _apply_score(item, max(int(item.get("score", 0)), 72))


def _polish_static(item: dict[str, Any] | None) -> None:
    if not item:
        return
    evidence = list(item.get("evidence", []) or [])
    findings = list(item.get("findings", []) or [])
    hit_notes = [note for note in _unique(evidence + findings) if " - " in note and ":" in note]
    production = [note for note in hit_notes if _classify_static_hit(note) == "production_source"]
    review_only = [note for note in hit_notes if note not in production]
    if review_only:
        item["evidence"] = _unique(evidence + [f"Static finding classification: production-risk={len(production)}, rule/test/docs-review={len(review_only)}."])
    if not production and hit_notes:
        item["findings"] = []
        item["summary"] = "Static analysis classifies built-in pattern hits by source type before scoring so scanner rules and test fixtures are not treated as production findings."
        _apply_score(item, max(int(item.get("score", 0)), 86))
    elif production:
        item["findings"] = _unique(production)
        _apply_score(item, max(45, 86 - len(production) * 8))


def _polish_code_audit(item: dict[str, Any] | None) -> None:
    if not item:
        return
    evidence = list(item.get("evidence", []) or [])
    findings = list(item.get("findings", []) or [])
    risky = [note for note in findings if " - " in note and ":" in note]
    production_risks = [note for note in risky if _classify_static_hit(note) == "production_source"]
    nonprod = [note for note in risky if note not in production_risks]
    if nonprod:
        item["evidence"] = _unique(evidence + [f"Code-risk classification: production-risk={len(production_risks)}, rule/test/docs-review={len(nonprod)}."])
        item["findings"] = _unique([note for note in findings if note not in nonprod])
    if not production_risks:
        _apply_score(item, max(int(item.get("score", 0)), 80))


def _refresh_maturity(result: dict[str, Any]) -> None:
    sections = [item for item in result.get("sections", []) if isinstance(item, dict) and item.get("status") != "gray"]
    avg = round(sum(int(item.get("score", 0)) for item in sections) / len(sections)) if sections else 0
    if avg >= 82:
        level = "Senior"
        summary = "Evidence suggests mature delivery foundations with documented structure, automation, and low-risk signals, pending human validation."
    elif avg >= 58:
        level = "Mid"
        summary = "Evidence suggests useful foundations exist, but operating maturity depends on closing traceability, test, dependency, or automation gaps."
    else:
        level = "Junior"
        summary = "Evidence suggests early-stage maturity or missing access to the signals needed for confident assessment."
    result["maturity_signal"] = {"level": level, "score": avg, "summary": summary}
    result["maturity_semaphore"] = {item.get("label", item.get("id", "Section")): item.get("status") for item in sections}
    result["maturity_semaphore"]["Work vs Expected"] = level


def _p(text: Any, style: Any, limit: int = 1200) -> Any:
    from reportlab.platypus import Paragraph
    return Paragraph(html.escape(_clean_text(text, limit)), style)


def _bullets(items: list[str], style: Any, max_items: int = 6) -> list[Any]:
    if not items:
        return [_p("No evidence returned.", style)]
    flowables: list[Any] = []
    for item in _sanitize_list(items)[:max_items]:
        flowables.append(_p(f"- {_clean_text(item, 520)}", style, limit=560))
    if len(items) > max_items:
        flowables.append(_p(f"- {len(items) - max_items} additional item(s) omitted from PDF; use Markdown/HTML for full detail.", style))
    return flowables


def _draw_footer(canvas: Any, doc: Any) -> None:
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#dbeafe"))
    canvas.line(doc.leftMargin, 0.52 * inch, doc.pagesize[0] - doc.rightMargin, 0.52 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(doc.leftMargin, 0.33 * inch, "NICO - powered by Reparodynamics - evidence-bound - human review required")
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 0.33 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _metric_card(label: str, value: Any, value_style: Any, label_style: Any) -> list[Any]:
    return [_p(label, label_style), _p(str(value), value_style)]


def _build_polished_pdf_base64(result: dict[str, Any]) -> tuple[str | None, str | None]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import KeepTogether, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        return None, f"PDF polish unavailable because reportlab is not installed: {exc}"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.58 * inch, leftMargin=0.58 * inch, topMargin=0.52 * inch, bottomMargin=0.72 * inch, title="NICO Express Technical Health Assessment", author="NICO")
    styles = getSampleStyleSheet()
    hero_brand = ParagraphStyle("HeroBrand", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=34, leading=36, textColor=colors.white, alignment=1, spaceAfter=1)
    hero_powered = ParagraphStyle("HeroPowered", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9.5, leading=11, textColor=colors.HexColor("#67e8f9"), alignment=1, spaceAfter=4)
    hero_title = ParagraphStyle("HeroTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=15.5, leading=19, textColor=colors.HexColor("#e0f2fe"), alignment=1, spaceAfter=0)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12.7, leading=15.5, textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=4, keepWithNext=True)
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=9.6, leading=11.5, textColor=colors.HexColor("#111827"), spaceBefore=4, spaceAfter=2, keepWithNext=True)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.35, leading=10.8, textColor=colors.HexColor("#334155"), spaceAfter=3.0)
    small = ParagraphStyle("Small", parent=body, fontSize=7.55, leading=9.3, textColor=colors.HexColor("#475569"), spaceAfter=1.8)
    label_style = ParagraphStyle("MetricLabel", parent=small, fontName="Helvetica-Bold", textColor=colors.HexColor("#64748b"), fontSize=7.1, leading=8.4, spaceAfter=1)
    metric_style = ParagraphStyle("MetricValue", parent=body, fontName="Helvetica-Bold", fontSize=11.0, leading=13.0, textColor=colors.HexColor("#0f172a"), spaceAfter=0)
    badge = ParagraphStyle("Badge", parent=small, fontName="Helvetica-Bold", fontSize=7.6, leading=9.0, textColor=colors.white, alignment=1, spaceAfter=0)
    callout = ParagraphStyle("Callout", parent=body, fontName="Helvetica-Bold", fontSize=8.5, leading=10.8, textColor=colors.HexColor("#075985"), backColor=colors.HexColor("#e0f2fe"), borderColor=colors.HexColor("#7dd3fc"), borderWidth=0.7, borderPadding=7, spaceAfter=7)
    warn = ParagraphStyle("Warn", parent=body, fontName="Helvetica-Bold", fontSize=8.35, leading=10.6, textColor=colors.HexColor("#854d0e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=0.7, borderPadding=7, spaceAfter=7)

    repo = _clean_text(result.get("repository") or "Not specified")
    generated = _clean_text(result.get("generated_at") or "Not specified")
    client = _clean_text(result.get("client_name") or "Not specified")
    project = _clean_text(result.get("project_name") or "Not specified")
    maturity = result.get("maturity_signal") or {}
    sections = [item for item in result.get("sections", []) if isinstance(item, dict)]
    verdict = _client_verdict(result)
    counts = {"green": sum(1 for item in sections if item.get("status") == "green"), "yellow": sum(1 for item in sections if item.get("status") == "yellow"), "red": sum(1 for item in sections if item.get("status") == "red"), "gray": sum(1 for item in sections if item.get("status") == "gray")}

    hero = Table([[_p("NICO", hero_brand)], [_p("POWERED BY REPARODYNAMICS", hero_powered)], [_p("Express Technical Health Assessment", hero_title)]], colWidths=[7.08 * inch])
    hero.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")), ("BOX", (0, 0), (-1, -1), 0.0, colors.HexColor("#0f172a")), ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10), ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12)]))
    metadata = Table([[_p("Repository", label_style), _p(repo, small), _p("Client", label_style), _p(client, small)], [_p("Project", label_style), _p(project, small), _p("Generated", label_style), _p(generated, small)]], colWidths=[0.95 * inch, 2.45 * inch, 0.85 * inch, 2.83 * inch])
    metadata.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbe3ef")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    status_color = colors.HexColor(_status_color("red" if verdict["red_sections"] else "yellow" if verdict["blockers"] else "green"))
    metric_table = Table([[_metric_card("MATURITY", maturity.get("level", "Unknown"), metric_style, label_style), _metric_card("SCORE", f"{maturity.get('score', 'N/A')}/100", metric_style, label_style), _metric_card("CONFIDENCE", verdict["confidence"], metric_style, label_style), [_p("DELIVERY VERDICT", label_style), Table([[_p(str(verdict["status"]).replace("_", " ").upper(), badge)]], colWidths=[1.55 * inch], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), status_color), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))]]], colWidths=[1.65 * inch, 1.45 * inch, 1.55 * inch, 2.43 * inch])
    metric_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.white), ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#dbe3ef")), ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#e2e8f0")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    score_rows = [[_p("Area", label_style), _p("Status", label_style), _p("Score", label_style), _p("Summary", label_style)]]
    for item in sections:
        score_rows.append([_p(item.get("label") or item.get("id") or "Section", small), _p(str(item.get("status") or "unknown").upper(), small), _p(str(item.get("score", "N/A")), small), _p(item.get("summary") or "", small, limit=190)])
    scorecard = Table(score_rows, colWidths=[1.7 * inch, 0.82 * inch, 0.55 * inch, 4.01 * inch], repeatRows=1)
    score_styles = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    for row_idx, item in enumerate(sections, start=1):
        score_styles.append(("TEXTCOLOR", (1, row_idx), (2, row_idx), colors.HexColor(_status_color(str(item.get("status") or "")))))
    scorecard.setStyle(TableStyle(score_styles))

    story: list[Any] = [hero, Spacer(1, 0.08 * inch), metadata, Spacer(1, 0.08 * inch), metric_table, Spacer(1, 0.08 * inch), _p("Human review is required before client-facing delivery. Missing evidence is shown as unavailable, not invented.", callout)]
    if verdict["blockers"]:
        story.append(_p("Delivery verdict: human review required. " + " ".join(verdict["blockers"]), warn))
    story += [_p("Executive Summary", h2), _p(result.get("executive_summary") or "No executive summary returned.", body, limit=900), _p("Section Scorecard", h2), scorecard, Spacer(1, 0.10 * inch), _p(f"Score mix: green={counts['green']}, yellow={counts['yellow']}, red={counts['red']}, unavailable={counts['gray']}.", small)]
    for item in sections:
        section_title = f"{item.get('label') or item.get('id')} - {str(item.get('status') or 'unknown').upper()} {item.get('score', 'N/A')}/100"
        story.append(KeepTogether([_p(section_title, h2), _p(item.get("summary") or "", body), _p("Evidence", h3)]))
        story.extend(_bullets(list(item.get("evidence", []) or []), small, max_items=5))
        if item.get("findings"):
            story.append(_p("Findings", h3)); story.extend(_bullets(list(item.get("findings", []) or []), small, max_items=4))
        if item.get("unavailable"):
            story.append(_p("Unavailable data", h3)); story.extend(_bullets(list(item.get("unavailable", []) or []), small, max_items=4))
        story.append(Spacer(1, 0.08 * inch))
    for title_text, key in [("Quick Wins", "quick_wins"), ("Medium-Term Plan", "medium_term_plan"), ("Resourcing Recommendation", "resourcing_recommendation"), ("Risk Register", "risk_register"), ("Verification Checklist", "verification_checklist")]:
        items = result.get(key) or []
        if items:
            story.append(KeepTogether([_p(title_text, h2)] + _bullets(list(items), small, max_items=6)))
            story.append(Spacer(1, 0.05 * inch))
    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return base64.b64encode(buffer.getvalue()).decode("ascii"), None


def _polish_pdf_report(result: dict[str, Any]) -> None:
    reports = result.setdefault("reports", {})
    pdf, error = _build_polished_pdf_base64(result)
    if pdf:
        reports["pdf_base64"] = pdf
        reports["pdf_filename"] = f"nico-express-{str(result.get('repository') or 'assessment').replace('/', '-')}.pdf"
        reports["pdf_style"] = PDF_STYLE_VERSION
    elif error:
        reports.setdefault("pdf_error", error)


def polish_express_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "complete":
        return result
    for item in result.get("sections", []) or []:
        item["evidence"] = _sanitize_list(list(item.get("evidence", []) or []))
        item["findings"] = _sanitize_list(list(item.get("findings", []) or []))
        item["unavailable"] = _sanitize_list(list(item.get("unavailable", []) or []))

    code = _section(result, "code_audit")
    ci = _section(result, "ci_cd")
    velocity = _section(result, "velocity_complexity")
    deps = _section(result, "dependency_health")
    secrets = _section(result, "secrets_review")
    static = _section(result, "static_analysis")
    arch = _section(result, "architecture_debt")
    arch_evidence = " ".join((arch or {}).get("evidence", []) or [])
    limited = _notes_limited(code) or _notes_limited(ci) or _notes_limited(velocity)

    if code and _notes_limited(code):
        code["findings"] = [note for note in code.get("findings", []) if "No recent pull-request evidence" not in note]
        code["evidence"] = [note for note in code.get("evidence", []) if "No recent pull-request evidence" not in note]
        code["evidence"].insert(0, "Commit and pull-request metadata were unavailable in this run; missing metadata is not treated as proof of direct-to-main work.")
        code["evidence"] = _unique(code["evidence"])
        _apply_score(code, max(int(code.get("score", 0)), 55))
    if ci and (_notes_limited(ci) or "Repository root contains .github/." in arch_evidence):
        if any("No CI/CD workflow" in note or "No GitHub Actions workflow" in note for note in ci.get("evidence", []) + ci.get("findings", [])):
            ci["findings"] = [note for note in ci.get("findings", []) if "No CI/CD workflow" not in note]
            ci["evidence"] = [note for note in ci.get("evidence", []) if "No GitHub Actions workflow" not in note and "No CI/CD workflow" not in note]
            ci["evidence"].insert(0, "CI/CD file metadata was unavailable or incomplete in this run; missing workflow metadata is not treated as proof that CI is absent.")
            ci["evidence"] = _unique(ci["evidence"])
            _apply_score(ci, max(int(ci.get("score", 0)), 50))
    if velocity and limited:
        velocity["evidence"] = [note for note in velocity.get("evidence", []) if "0 commits over" not in note and "0 PRs / 0 commits" not in note]
        velocity["evidence"].insert(0, "Velocity and PR traceability are degraded because commit or PR metadata was unavailable in this run.")
        velocity["evidence"] = _unique(velocity["evidence"])
        _apply_score(velocity, max(int(velocity.get("score", 0)), 55))

    _polish_dependencies(deps)
    _polish_secrets(secrets)
    _polish_static(static)
    _polish_code_audit(code)

    if limited:
        result["assessment_quality"] = "degraded_metadata"
        result["executive_summary"] += " Some GitHub metadata was unavailable, so affected sections are degraded rather than final negative evidence."
    _refresh_maturity(result)
    all_findings: list[str] = []
    for item in result.get("sections", []) or []:
        all_findings.extend(item.get("findings", []) or [])
    result["findings"] = _unique(all_findings) or ["No high-confidence finding was returned by available hosted checks."]
    result["client_delivery_verdict"] = _client_verdict(result)
    _polish_pdf_report(result)
    return result
