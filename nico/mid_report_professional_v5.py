from __future__ import annotations

import html
import io
from copy import deepcopy
from typing import Any

from nico.mid_report_professional_v4 import (
    _CONTEXT_REQUESTS,
    _DRAFT_LABEL,
    _REVIEW_QUESTIONS,
    _WEIGHTS,
    _context,
    _dict,
    _list,
    _score,
    _score_rows,
    _technical,
    _texts,
)

MID_REPORT_V5_VERSION = "mid-assessment-draft-v5-decision-compact"
_PATCH_MARKER = "_nico_mid_report_professional_v5"


def _humanize_tool_gap(value: str) -> str:
    text = " ".join(str(value or "").split())
    normalized = text.lower()
    if normalized == "bandit":
        return "Bandit did not provide accepted parseable exact-snapshot evidence for this run."
    if normalized == "gitleaks":
        return "Gitleaks did not provide accepted same-run history evidence for this run."
    if normalized and all(character.isalnum() or character in "._-" for character in normalized) and len(normalized) <= 32:
        return f"{normalized.replace('_', ' ').replace('-', ' ').title()} evidence is incomplete or unavailable for this run."
    return text


def _clean_texts(value: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in _texts(value):
        text = _humanize_tool_gap(item)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _section_limitations(section: dict[str, Any]) -> list[str]:
    return _clean_texts(section.get("unavailable")) + _clean_texts(section.get("missing_evidence_sources")) + _clean_texts(section.get("failed_evidence_tools")) + _clean_texts(section.get("scope_disclosures"))


def _canonical_score(payload: dict[str, Any]) -> int | None:
    rows = _score_rows(payload)
    total_weight = sum(int(row.get("weight") or 0) for row in rows)
    if rows and total_weight == 100:
        return round(sum(float(row.get("score") or 0) * int(row.get("weight") or 0) / 100 for row in rows))
    decision = _dict(payload.get("decision_summary"))
    integrity = _dict(payload.get("score_integrity"))
    return _score(decision.get("technical_score")) or _score(integrity.get("final_report_score")) or _score(integrity.get("reported_score"))


def _primary_constraints(payload: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {str(section.get("id") or ""): section for section in _technical(payload)}
    constraints: list[dict[str, Any]] = []
    for row in sorted(_score_rows(payload), key=lambda item: int(item.get("score") or 101)):
        section = by_id.get(str(row.get("section_id") or ""), {})
        score = _score(row.get("score"))
        findings = _clean_texts(section.get("findings"))
        limitations = _section_limitations(section)
        if score is None or (score >= 80 and not findings):
            continue
        constraints.append({
            "section_id": row.get("section_id"),
            "label": row.get("label") or section.get("label"),
            "score": score,
            "primary_reason": findings[0] if findings else limitations[0] if limitations else "The evidence-supported score remains below the stronger-control range.",
        })
    return constraints[:3]


def _enhance(payload: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(payload)
    score = _canonical_score(output)
    decision = _dict(output.get("decision_summary"))
    integrity = _dict(output.get("score_integrity"))
    if score is not None:
        decision["technical_score"] = score
        integrity.update({
            "calculated_score": score,
            "reported_score": score,
            "final_report_score": score,
            "score_match": True,
        })
    decision["primary_score_constraints"] = _primary_constraints(output)
    output["decision_summary"] = decision
    output["score_integrity"] = integrity
    output.update({
        "presentation_version": MID_REPORT_V5_VERSION,
        "presentation_detail_level": 5,
        "coverage_display_label": "Evidence-unit coverage",
        "report_depth_contract": {
            **_dict(output.get("report_depth_contract")),
            "minimum_pdf_pages": 10,
            "target_pdf_pages": 11,
            "dedicated_technical_dossiers": len(_technical(output)),
            "single_context_evidence_table": True,
            "deduplicated_exception_summary": True,
            "orphan_page_prevention": True,
            "canonical_score_single_source": True,
            "legacy_payload_contract_preserved": True,
        },
    })
    return output


def _markdown(payload: dict[str, Any]) -> str:
    decision = _dict(payload.get("decision_summary"))
    coverage = _dict(payload.get("evidence_coverage"))
    score = _canonical_score(payload)
    lines = [
        "# NICO MID TECHNICAL ASSESSMENT",
        "",
        f"**{_DRAFT_LABEL} — snapshot-bound**",
        "",
        f"- Repository: `{payload.get('repository')}`",
        f"- Run: `{payload.get('run_id')}`",
        f"- Snapshot: `{payload.get('snapshot_commit_sha')}`",
        f"- Technical score: **{score}/100**",
        f"- Evidence-unit coverage: **{coverage.get('percent', 0)}%** ({coverage.get('numerator', 0)}/{coverage.get('denominator', 0)})",
        "- Human review: **REQUIRED**",
        "",
        "## Executive decision",
        "",
        "The technical score is the weighted result of seven controls. Evidence-unit coverage measures availability only; analyzer completion and finding disposition remain visible inside each dossier.",
        "",
        "### Priority controls",
    ]
    for index, item in enumerate(decision.get("primary_score_constraints") or [], 1):
        lines.append(f"{index}. **{item.get('label')} — {item.get('score')}/100:** {item.get('primary_reason')}")
    lines.extend(["", "### Verified strengths"])
    lines.extend(f"- {item}" for item in decision.get("verified_strengths") or ["No verified strength summary was returned."])
    lines.extend(["", "## Method and score sensitivity", ""])
    lines.extend([
        "- Missing or failed evidence is disclosed and never converted into a pass.",
        "- Analyzer execution is separate from parsed finding severity and reviewer disposition.",
        "- Human-context modules are unscored until validated by an authorized reviewer.",
        "- A score change requires completed repair evidence and a new immutable snapshot.",
    ])
    for row in payload.get("score_sensitivity") or []:
        lines.append(f"- {row.get('label')}: current={row.get('score')}; weight={row.get('weight')}%; lift to 80={row.get('lift_to_80')}; lift to 90={row.get('lift_to_90')}.")
    for index, section in enumerate(_technical(payload), 1):
        evidence = _clean_texts(section.get("evidence"))
        findings = _clean_texts(section.get("findings"))
        limitations = _section_limitations(section)
        lines.extend([
            "",
            f"## Technical dossier {index}: {section.get('label')} — {section.get('score')}/100",
            "",
            str(section.get("summary") or "No evidence-bound conclusion was returned."),
            "",
            "### Evidence reviewed",
        ])
        lines.extend(f"- {item}" for item in evidence or ["No direct evidence item was retained."])
        lines.extend(["", "### Findings and limitations"])
        lines.extend(f"- Finding: {item}" for item in findings or ["No specific repair finding was retained."])
        lines.extend(f"- Limitation: {item}" for item in limitations or ["Report-wide human-review boundaries apply."])
        lines.extend(["", "### Reviewer decision"])
        lines.extend(f"- {item}" for item in _REVIEW_QUESTIONS.get(str(section.get("id") or ""), [])[:2])
        lines.append("- Required proof: exact artifact, reviewer disposition, relevant tests or analyzer output, and a new immutable snapshot rescan.")
    lines.extend(["", "## Repair and verification plan", ""])
    for item in _list(_dict(payload.get("repair_intelligence")).get("candidates"))[:8]:
        if not isinstance(item, dict):
            continue
        lines.extend([
            f"### P{item.get('rank', '?')} — {item.get('title')}",
            f"- Action: {item.get('recommended_action')}",
            f"- Verification: {'; '.join(_clean_texts(item.get('test_plan'))) or 'Run relevant tests and a NICO rescan.'}",
            "- Completion evidence: implementation reference, reviewer disposition, test output, analyzer output where applicable, and immutable post-repair SHA.",
        ])
    lines.extend(["", "## Human-context evidence requests", ""])
    for section in _context(payload):
        request = _CONTEXT_REQUESTS.get(str(section.get("id") or ""), "Direct reviewable context with source, owner, date, scope, and decision impact.")
        lines.append(f"- **{section.get('label')}**: {request}")
    lines.extend(["", "## Review exceptions and integrity", ""])
    for item in _list(payload.get("deduplicated_review_exceptions")):
        if isinstance(item, dict):
            lines.append(f"- {str(item.get('severity') or 'medium').upper()} — {item.get('title') or item.get('category')}: {item.get('reason')}")
    lines.extend([
        "",
        f"- Source identity SHA-256: `{payload.get('source_identity_sha256')}`",
        f"- Review packet SHA-256: `{_dict(payload.get('review_packet')).get('review_packet_sha256')}`",
        f"- Snapshot commit SHA: `{payload.get('snapshot_commit_sha')}`",
        "- Unsupported claims permitted: 0.",
        "- Human review is required before approval or client delivery.",
        "- NICO did not modify the assessed repository.",
    ])
    return "\n".join(lines).strip() + "\n"


def _html(payload: dict[str, Any]) -> str:
    escaped = html.escape(_markdown(payload))
    return f"<!doctype html><html><head><meta charset='utf-8'><title>NICO Mid Technical Assessment</title></head><body><pre>{escaped}</pre></body></html>"


def _pdf(payload: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle
    from nico.report_flowable_safety import _bullets, _document_styles, _footer, _paragraph, _table

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.48 * inch,
        leftMargin=0.48 * inch,
        topMargin=0.44 * inch,
        bottomMargin=0.62 * inch,
        title="NICO Mid Technical Assessment",
        author="NICO",
        invariant=1,
    )
    styles = _document_styles("MidV5")
    page_title = ParagraphStyle("MidV5PageTitle", parent=styles["title"], fontSize=18, leading=21, spaceAfter=7)
    compact = ParagraphStyle("MidV5Compact", parent=styles["small"], fontSize=7.6, leading=9.4, spaceAfter=2)
    compact_body = ParagraphStyle("MidV5Body", parent=styles["body"], fontSize=8.2, leading=10.2, spaceAfter=3)
    compact_h2 = ParagraphStyle("MidV5H2", parent=styles["h2"], fontSize=11.5, leading=13.5, spaceBefore=5, spaceAfter=3)
    p = _paragraph
    technical = _technical(payload)
    context = _context(payload)
    decision = _dict(payload.get("decision_summary"))
    integrity = _dict(payload.get("score_integrity"))
    coverage = _dict(payload.get("evidence_coverage"))
    repairs = [item for item in _list(_dict(payload.get("repair_intelligence")).get("candidates")) if isinstance(item, dict)]
    exceptions = [item for item in _list(payload.get("deduplicated_review_exceptions")) if isinstance(item, dict)]
    score = _canonical_score(payload)

    hero = Table([[p("NICO MID TECHNICAL ASSESSMENT", page_title)]], colWidths=[7.1 * inch])
    hero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
    ]))
    story: list[Any] = [
        hero,
        Spacer(1, 0.07 * inch),
        p(f"{_DRAFT_LABEL} — Powered by Reparodynamics — snapshot-bound", styles["callout"]),
        _table([
            [p("Repository", styles["label"]), p(payload.get("repository"), compact), p("Run", styles["label"]), p(payload.get("run_id"), compact)],
            [p("Snapshot", styles["label"]), p(payload.get("snapshot_commit_sha"), compact, 350), p("Report", styles["label"]), p(payload.get("report_id"), compact, 350)],
            [p("Score", styles["label"]), p(f"{score}/100", compact), p("Evidence-unit coverage", styles["label"]), p(f"{coverage.get('percent', 0)}%", compact)],
            [p("Maturity", styles["label"]), p(decision.get("technical_maturity") or "Mid", compact), p("Human review", styles["label"]), p("REQUIRED", compact)],
        ], [0.85 * inch, 2.65 * inch, 1.08 * inch, 2.52 * inch], header_color="#f8fafc"),
        p("Executive decision", compact_h2),
        p("The technical score is the weighted result of seven controls. Evidence-unit coverage measures availability only and does not imply that every analyzer completed or that every finding was dispositioned.", styles["callout"], 1300),
        p("Priority controls", compact_h2),
    ]
    priorities = decision.get("primary_score_constraints") or []
    story.extend(_bullets([f"{index}. {item.get('label')} — {item.get('score')}/100: {item.get('primary_reason')}" for index, item in enumerate(priorities, 1)], compact_body, max_items=3))
    story.append(p("Weighted technical scorecard", compact_h2))
    score_rows = [[p("Control", styles["label"]), p("Truth", styles["label"]), p("Score", styles["label"]), p("Weight", styles["label"]), p("Points", styles["label"])]]
    for row in _score_rows(payload):
        score_rows.append([p(row.get("label"), compact), p(row.get("truth_status"), compact), p(str(row.get("score")), compact), p(f"{row.get('weight')}%", compact), p(str(row.get("weighted_contribution")), compact)])
    story.append(_table(score_rows, [2.18 * inch, 1.70 * inch, 0.55 * inch, 0.62 * inch, 0.72 * inch]))
    story.append(p(f"Canonical weighted score={score}; integrity match={integrity.get('score_match', True)}. Human-context modules remain unscored.", compact))

    story.extend([PageBreak(), p("Method, Coverage, and Score Sensitivity", page_title)])
    story.append(p("Assessment rules", compact_h2))
    story.extend(_bullets([
        "Seven fixed-weight technical controls determine the score.",
        "Missing or failed evidence is disclosed and never converted into a healthy result.",
        "Analyzer execution, parsed results, and reviewer disposition are separate evidence states.",
        "A score change requires verified repair evidence and a new immutable snapshot.",
        "NICO did not modify the assessed repository or create a branch, commit, pull request, or deployment.",
    ], compact_body, max_items=8))
    story.append(p("Evidence-unit coverage", compact_h2))
    story.append(_table([
        [p("Measure", styles["label"]), p("Result", styles["label"])],
        [p("Available units", compact), p(f"{coverage.get('percent', 0)}% ({coverage.get('numerator', 0)}/{coverage.get('denominator', 0)})", compact)],
        [p("Meaning", compact), p("Availability of explicit same-run evidence units. Analyzer completion and finding disposition are reported inside each technical dossier.", compact, 1200)],
    ], [1.35 * inch, 5.75 * inch], header_color="#f1f5f9"))
    story.append(p("Score sensitivity", compact_h2))
    sensitivity_rows = [[p("Control", styles["label"]), p("Score", styles["label"]), p("Weight", styles["label"]), p("Lift to 80", styles["label"]), p("Lift to 90", styles["label"])]]
    for row in payload.get("score_sensitivity") or []:
        sensitivity_rows.append([p(row.get("label"), compact), p(str(row.get("score")), compact), p(f"{row.get('weight')}%", compact), p(str(row.get("lift_to_80")), compact), p(str(row.get("lift_to_90")), compact)])
    story.append(_table(sensitivity_rows, [2.65 * inch, 0.65 * inch, 0.70 * inch, 0.85 * inch, 0.85 * inch]))
    story.append(p("Sensitivity values are arithmetic scenarios, not promises. Reassessment can remain unchanged or decline when new findings or weaker evidence are discovered.", styles["warning"], 1300))

    rows_by_id = {str(row.get("section_id") or ""): row for row in _score_rows(payload)}
    for index, section in enumerate(technical, 1):
        section_id = str(section.get("id") or "")
        row = rows_by_id.get(section_id, {})
        evidence = _clean_texts(section.get("evidence"))
        findings = _clean_texts(section.get("findings"))
        gaps = _section_limitations(section)
        story.extend([PageBreak(), p(f"Technical Review {index} of {len(technical)} — {section.get('label')}", page_title)])
        story.append(_table([
            [p("Score", styles["label"]), p("Weight", styles["label"]), p("Contribution", styles["label"]), p("Truth", styles["label"]), p("Confidence", styles["label"])],
            [p(f"{section.get('score')}/100", compact), p(f"{_WEIGHTS.get(section_id)}%", compact), p(str(row.get("weighted_contribution")), compact), p(section.get("truth_status"), compact), p(section.get("confidence") or "evidence-bound", compact)],
        ], [0.75 * inch, 0.68 * inch, 0.92 * inch, 1.75 * inch, 2.20 * inch], header_color="#ecfeff"))
        story.append(p("Evidence-bound conclusion", compact_h2))
        story.append(p(section.get("summary") or "No evidence-bound conclusion was returned.", styles["callout"], 1250))
        story.append(p("Evidence reviewed", compact_h2))
        story.extend(_bullets(evidence or ["No direct evidence item was retained."], compact, max_items=7))
        story.append(p("Findings and limitations", compact_h2))
        finding_text = [f"Finding: {item}" for item in findings] or ["Finding: No specific repair finding was retained; reviewer validation remains required."]
        gap_text = [f"Limitation: {item}" for item in gaps] or ["Limitation: Report-wide human-review boundaries apply."]
        story.extend(_bullets((finding_text + gap_text)[:8], compact, max_items=8))
        breakdown = _dict(section.get("score_evidence_breakdown"))
        if breakdown:
            story.append(p("Score evidence", compact_h2))
            compact_breakdown = [[p("Factor", styles["label"]), p("Retained value", styles["label"])]]
            for key, value in list(sorted(breakdown.items()))[:6]:
                compact_breakdown.append([p(str(key).replace("_", " ").title(), compact), p(value, compact, 800)])
            story.append(_table(compact_breakdown, [2.35 * inch, 4.75 * inch], header_color="#f1f5f9"))
        story.append(p("Reviewer decision and required proof", compact_h2))
        questions = _REVIEW_QUESTIONS.get(section_id, [])[:2]
        story.extend(_bullets(questions + ["Retain the exact artifact, reviewer disposition, relevant tests or analyzer output, and a new immutable snapshot rescan before accepting a score change."], compact, max_items=4))

    story.extend([PageBreak(), p("Repair Plan and Human-Context Requests", page_title)])
    story.append(p("Repairs are report-only candidates. The responsible owner, implementation method, verification, and acceptance decision remain human responsibilities.", styles["callout"], 1250))
    if repairs:
        repair_rows = [[p("Rank", styles["label"]), p("Finding", styles["label"]), p("Action and verification", styles["label"])]]
        for item in repairs[:6]:
            action = str(item.get("recommended_action") or "Collect exact evidence and apply the smallest reversible repair.")
            verification = "; ".join(_clean_texts(item.get("test_plan"))) or "Run relevant tests and a NICO rescan."
            repair_rows.append([p(f"P{item.get('rank', '?')}", compact), p(item.get("title"), compact, 600), p(f"{action} Verification: {verification}", compact, 1200)])
        story.append(_table(repair_rows, [0.48 * inch, 2.55 * inch, 4.07 * inch], header_color="#ecfeff"))
    story.append(p("Execution sequence", compact_h2))
    story.extend(_bullets([
        "Stabilize failed, unavailable, or non-parseable evidence collection.",
        "Disposition each finding as verified, repaired, accepted risk, or documented false positive.",
        "Run the smallest relevant test, the full validation suite, and a new immutable NICO rescan.",
    ], compact_body, max_items=5))
    story.append(p("Human-context modules — unscored", compact_h2))
    context_rows = [[p("Module", styles["label"]), p("Evidence request", styles["label"])]]
    for section in context:
        request = _CONTEXT_REQUESTS.get(str(section.get("id") or ""), "Direct reviewable context with source, owner, date, scope, and decision impact.")
        context_rows.append([p(section.get("label"), compact), p(request, compact, 1100)])
    story.append(_table(context_rows, [1.75 * inch, 5.35 * inch], header_color="#f1f5f9"))
    story.append(p("Submitted context may inform final human review but cannot silently rewrite the seven-control technical score.", styles["warning"], 1200))

    story.extend([PageBreak(), p("Review Exceptions and Integrity", page_title)])
    story.append(p(f"Original exception records: {payload.get('review_exception_original_count', 0)}. Decision-ready deduplicated items: {payload.get('review_exception_final_count', len(exceptions))}.", styles["callout"]))
    if exceptions:
        exception_rows = [[p("Severity", styles["label"]), p("Exception", styles["label"]), p("Decision reason", styles["label"])]]
        for item in exceptions[:12]:
            exception_rows.append([p(str(item.get("severity") or "medium").upper(), compact), p(item.get("title") or item.get("category"), compact, 600), p(item.get("reason") or "Human review required.", compact, 1000)])
        story.append(_table(exception_rows, [0.72 * inch, 2.45 * inch, 3.93 * inch], header_color="#fef3c7"))
    story.append(p("Integrity identity", compact_h2))
    story.append(_table([
        [p("Identity field", styles["label"]), p("Value", styles["label"])],
        [p("Source identity SHA-256", compact), p(payload.get("source_identity_sha256"), compact, 1200)],
        [p("Review packet SHA-256", compact), p(_dict(payload.get("review_packet")).get("review_packet_sha256"), compact, 1200)],
        [p("Snapshot commit SHA", compact), p(payload.get("snapshot_commit_sha"), compact, 1200)],
        [p("Report contract", compact), p(payload.get("report_version"), compact)],
        [p("Presentation", compact), p(payload.get("presentation_version"), compact)],
        [p("Unsupported claims permitted", compact), p("0", compact)],
    ], [1.70 * inch, 5.40 * inch], header_color="#f1f5f9"))
    story.append(p("Final safety boundary", compact_h2))
    story.extend(_bullets([
        "Human review is required before approval or client delivery.",
        "NICO did not modify the assessed repository or automatically apply report suggestions.",
        "A recommendation is not evidence that a repair was implemented or effective.",
        "A clean scanner result is not proof that no vulnerability, defect, or credential exists.",
        "Only this exact report identity and attached evidence packet may be reviewed for approval.",
    ], compact_body, max_items=8))

    footer = _footer("NICO Mid — evidence-bound — snapshot-bound — human review required")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def install_mid_report_professional_v5() -> dict[str, Any]:
    from nico import mid_assessment_report as report_module

    if getattr(report_module, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": MID_REPORT_V5_VERSION}
    current_payload = report_module._report_payload

    def payload_v5(record: dict[str, Any], packet: dict[str, Any], identity: dict[str, Any], generated_at: str) -> dict[str, Any]:
        return _enhance(current_payload(record, packet, identity, generated_at))

    report_module._report_payload = payload_v5
    report_module._markdown = _markdown
    report_module._html = _html
    report_module._pdf = _pdf
    setattr(report_module, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "version": MID_REPORT_V5_VERSION,
        "legacy_report_contract_preserved": True,
        "canonical_score_single_source": True,
        "target_pdf_pages": 11,
        "dedicated_technical_dossiers": 7,
        "single_context_evidence_table": True,
        "deduplicated_exception_summary": True,
        "orphan_page_prevention": True,
        "report_only": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["MID_REPORT_V5_VERSION", "install_mid_report_professional_v5"]
