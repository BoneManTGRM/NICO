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
    _score_rows,
    _technical,
)
from nico.mid_report_professional_v5 import (
    _canonical_score,
    _clean_texts,
    _section_limitations,
)


MID_REPORT_V6_VERSION = "mid-assessment-draft-v6-executive-actionable"
_PATCH_MARKER = "_nico_mid_report_professional_v6"

_CONTROL_PLAYBOOK: dict[str, dict[str, str]] = {
    "code_audit": {
        "owner": "Engineering lead + security reviewer",
        "effort": "1–4 hours per confirmed item",
        "action": "Attach the exact file, line, rule identifier, severity, and confidence for every sampled risk pattern. Disposition each item as repaired, accepted risk, or documented false positive.",
        "verification": "Run the smallest affected test, the full validation suite, and a new immutable NICO rescan; retain the reviewer disposition and post-repair SHA.",
        "impact": "Untriaged sampled patterns prevent a client-safe statement about code risk even when broad repository structure is strong.",
    },
    "dependency_health": {
        "owner": "Platform or application engineering",
        "effort": "2–6 hours",
        "action": "Resolve the gap between scanner execution and accepted scoring evidence. Retain parseable npm-audit, pip-audit, and OSV output bound to the exact snapshot, then map each result to direct or transitive dependencies.",
        "verification": "Confirm manifest/lockfile alignment, deduplicate advisories, document materiality, rerun dependency tests, and rescan the immutable snapshot.",
        "impact": "Executed scanners that are not parsed and accepted cannot support a defensible vulnerability conclusion.",
    },
    "secrets_review": {
        "owner": "Security reviewer + repository owner",
        "effort": "1–4 hours when clean; longer if rotation is required",
        "action": "Complete both current-tree and authorized full-history credential checks. Retain only masked fingerprints, classify candidates, and rotate any confirmed credential outside NICO.",
        "verification": "Attach accepted Gitleaks and TruffleHog evidence, rotation references for confirmed items, and a clean exact-snapshot rescan.",
        "impact": "One clean history tool does not establish full current-tree and history coverage across the authorized repository scope.",
    },
    "static_analysis": {
        "owner": "Engineering lead + application security",
        "effort": "2–8 hours",
        "action": "Run Bandit, Semgrep, ESLint, and TypeScript against the exact snapshot and retain parseable structured output. Separate production findings from tests, generated files, review-only items, and accepted risk.",
        "verification": "Resolve or disposition material findings, rerun each analyzer, run relevant tests, and retain the exact analyzer artifacts and post-repair SHA.",
        "impact": "TypeScript or CI validation alone cannot substitute for accepted exact-snapshot rule coverage from the requested static analyzers.",
    },
    "ci_cd": {
        "owner": "DevOps or platform engineering",
        "effort": "2–6 hours for classification; repair effort varies",
        "action": "Classify every non-success run as product regression, test assertion, build/configuration failure, cancelled or superseded, transient infrastructure, expected development failure, or unresolved.",
        "verification": "Attach failing job logs, identify recurrence by workflow and branch, rerun affected checks, and confirm the latest default-branch required checks are green.",
        "impact": "A high aggregate CI score is not sufficient when non-success runs have not been root-cause classified.",
    },
    "architecture_debt": {
        "owner": "Technical lead or architect",
        "effort": "4–12 hours",
        "action": "Add language-aware coupling, circular-dependency, duplication, dependency-direction, module-size, and complexity-hotspot evidence. Link each hotspot to an ownership and remediation decision.",
        "verification": "Retain analyzer output, architecture decision records, targeted tests, and a rescan demonstrating the changed hotspot measurements.",
        "impact": "Repository layout, tests, and documentation prove structure, but they do not fully measure architecture quality or debt concentration.",
    },
    "velocity_complexity": {
        "owner": "Engineering manager + technical lead",
        "effort": "4–8 hours",
        "action": "Correlate churn with complexity, ownership concentration, review latency, pull-request age, and change-failure recurrence. Report hotspots without attributing individual performance from activity counts alone.",
        "verification": "Retain the bounded measurement window, source queries, hotspot list, reviewer interpretation, and a new assessment snapshot.",
        "impact": "Commit and pull-request counts show traceability but do not establish delivery quality, review effectiveness, or maintainability.",
    },
}


def _display(value: Any, *, empty: str = "Not provided") -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    if value is None:
        return empty
    if isinstance(value, str):
        return " ".join(value.split()) or empty
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        text = "; ".join(_clean_texts(value))
        return text or empty
    if isinstance(value, dict):
        return "; ".join(f"{key}={_display(item)}" for key, item in sorted(value.items())) or empty
    return str(value)


def _decision_status(score: int | None) -> tuple[str, str]:
    if score is None:
        return "Insufficient evidence for a technical decision", "Complete the missing evidence chain before approval review."
    if score >= 85:
        return "Proceed to human review", "Technical controls are broadly strong; remaining limitations still require explicit reviewer disposition."
    if score >= 70:
        return "Proceed to human review with remediation conditions", "The assessment is usable for planning, but the primary constraints should be resolved or formally accepted before client delivery."
    return "Remediation required before approval review", "The current evidence-supported score contains material control weakness or insufficient accepted evidence."


def _section_state(section: dict[str, Any]) -> dict[str, str]:
    evidence = " ".join(_clean_texts(section.get("evidence"))).lower()
    limitations = " ".join(_section_limitations(section)).lower()
    findings = _clean_texts(section.get("findings"))
    truth = _display(section.get("truth_status") or section.get("status"), empty="Unknown")

    execution = "Completed"
    if any(token in evidence + " " + limitations for token in ("not run", "did not provide", "unavailable", "failed", "timed out")):
        execution = "Partial or unavailable"
    if "scanner" not in evidence and "workflow" not in evidence and "analyzer" not in evidence:
        execution = "Repository evidence only"

    parsed = "Parsed"
    if any(token in evidence + " " + limitations for token in ("non-parseable", "parseable exact-snapshot evidence", "structured scanners completed=0", "analyzers completed=0")):
        parsed = "Incomplete"
    elif execution == "Repository evidence only":
        parsed = "Not applicable"

    accepted = "Accepted"
    if "limitation" in truth.lower():
        accepted = "Accepted with limitations"
    elif truth.lower() in {"unavailable", "failed", "gray", "not scored"}:
        accepted = truth

    if findings:
        disposition = "Open finding(s)"
    elif _section_limitations(section):
        disposition = "Reviewer validation required"
    else:
        disposition = "No material finding confirmed"

    return {
        "execution": execution,
        "parsed": parsed,
        "accepted": accepted,
        "disposition": disposition,
    }


def _section_action(section: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    section_id = str(section.get("id") or "")
    playbook = _CONTROL_PLAYBOOK.get(section_id, {})
    score = section.get("score")
    weight = int(row.get("weight") or _WEIGHTS.get(section_id) or 0)
    try:
        numeric_score = max(0, min(100, int(float(score))))
    except (TypeError, ValueError):
        numeric_score = 0
    lift_to_80 = round(max(0, 80 - numeric_score) * weight / 100, 2)
    lift_to_90 = round(max(0, 90 - numeric_score) * weight / 100, 2)
    return {
        "section_id": section_id,
        "label": section.get("label") or section_id.replace("_", " ").title(),
        "owner": playbook.get("owner", "Authorized technical owner"),
        "effort": playbook.get("effort", "Estimate after evidence review"),
        "action": playbook.get("action", "Collect exact evidence, disposition the finding, and apply the smallest reversible repair."),
        "verification": playbook.get("verification", "Run relevant tests and a new immutable NICO rescan."),
        "impact": playbook.get("impact", "The current evidence limits a stronger technical conclusion."),
        "conditional_lift_to_80": lift_to_80,
        "conditional_lift_to_90": lift_to_90,
    }


def _action_plan(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = {str(row.get("section_id") or ""): row for row in _score_rows(payload)}
    sections = {str(section.get("id") or ""): section for section in _technical(payload)}
    constraints = _dict(payload.get("decision_summary")).get("primary_score_constraints") or []
    ordered_ids = [str(item.get("section_id") or "") for item in constraints if isinstance(item, dict)]
    for row in sorted(rows.values(), key=lambda item: int(item.get("score") or 101)):
        section_id = str(row.get("section_id") or "")
        section = sections.get(section_id, {})
        if section_id not in ordered_ids and (int(row.get("score") or 0) < 85 or _clean_texts(section.get("findings"))):
            ordered_ids.append(section_id)
    return [_section_action(sections[section_id], rows.get(section_id, {})) for section_id in ordered_ids if section_id in sections][:7]


def _group_exceptions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in _list(payload.get("deduplicated_review_exceptions")):
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "review_required")
        group = grouped.setdefault(category, {"category": category, "count": 0, "examples": [], "review_priority": "Review required"})
        group["count"] += 1
        title = _display(item.get("title") or category)
        if title not in group["examples"] and len(group["examples"]) < 3:
            group["examples"].append(title)
        if "score" in category:
            group["review_priority"] = "High review priority"
        elif "missing" in category or "unavailable" in category:
            group["review_priority"] = "Context request"
    return sorted(grouped.values(), key=lambda item: (item["review_priority"] != "High review priority", -int(item["count"]), item["category"]))


def _enhance(payload: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(payload)
    score = _canonical_score(output)
    status, status_reason = _decision_status(score)
    decision = _dict(output.get("decision_summary"))
    decision.update({
        "review_decision": status,
        "review_decision_reason": status_reason,
        "action_plan": _action_plan(output),
    })
    output["decision_summary"] = decision
    output["presentation_version"] = MID_REPORT_V6_VERSION
    output["presentation_detail_level"] = 6
    output["evidence_assurance_matrix"] = [
        {"section_id": section.get("id"), "label": section.get("label"), **_section_state(section)}
        for section in _technical(output)
    ]
    output["grouped_review_exceptions"] = _group_exceptions(output)
    output["report_depth_contract"] = {
        **_dict(output.get("report_depth_contract")),
        "minimum_pdf_pages": 7,
        "target_pdf_pages": 8,
        "maximum_pdf_pages": 10,
        "paired_technical_dossiers": True,
        "evidence_assurance_matrix": True,
        "finding_specific_action_plan": True,
        "blank_values_normalized": True,
        "full_integrity_values_retained_in_markdown_and_json": True,
        "legacy_payload_contract_preserved": True,
    }
    return output


def _markdown(payload: dict[str, Any]) -> str:
    decision = _dict(payload.get("decision_summary"))
    coverage = _dict(payload.get("evidence_coverage"))
    score = _canonical_score(payload)
    rows = {str(row.get("section_id") or ""): row for row in _score_rows(payload)}
    lines = [
        "# NICO MID TECHNICAL ASSESSMENT",
        "",
        f"**{_DRAFT_LABEL} — Powered by Reparodynamics — immutable snapshot**",
        "",
        f"- Repository: `{payload.get('repository')}`",
        f"- Run: `{payload.get('run_id')}`",
        f"- Snapshot: `{payload.get('snapshot_commit_sha')}`",
        f"- Technical score: **{score}/100**",
        f"- Evidence-unit coverage: **{coverage.get('percent', 0)}%** ({coverage.get('numerator', 0)}/{coverage.get('denominator', 0)})",
        "- Human review: **REQUIRED**",
        "",
        "## Executive technical decision",
        "",
        f"**{decision.get('review_decision')}** — {decision.get('review_decision_reason')}",
        "",
        "Evidence-unit coverage measures availability. It does not mean every analyzer executed, every output parsed, or every finding was dispositioned.",
        "",
        "### Primary constraints and required decisions",
    ]
    for index, item in enumerate(decision.get("primary_score_constraints") or [], 1):
        section_id = str(item.get("section_id") or "")
        action = next((entry for entry in decision.get("action_plan") or [] if entry.get("section_id") == section_id), {})
        lines.extend([
            f"{index}. **{item.get('label')} — {item.get('score')}/100**",
            f"   - Constraint: {item.get('primary_reason')}",
            f"   - Decision impact: {action.get('impact')}",
            f"   - Required action: {action.get('action')}",
            f"   - Owner / effort: {action.get('owner')} / {action.get('effort')}",
            f"   - Verification: {action.get('verification')}",
        ])

    lines.extend(["", "## Evidence assurance matrix", "", "| Control | Execution | Parsing | Accepted for scoring | Disposition |", "|---|---|---|---|---|"])
    for item in payload.get("evidence_assurance_matrix") or []:
        lines.append(f"| {item.get('label')} | {item.get('execution')} | {item.get('parsed')} | {item.get('accepted')} | {item.get('disposition')} |")

    lines.extend(["", "## Weighted score and sensitivity", ""])
    for row in _score_rows(payload):
        lines.append(f"- **{row.get('label')}**: {row.get('score')}/100 × {row.get('weight')}% = {row.get('weighted_contribution')} points; conditional lift to 80={round(max(0, 80-int(row.get('score') or 0))*int(row.get('weight') or 0)/100, 2)}.")

    for index, section in enumerate(_technical(payload), 1):
        section_id = str(section.get("id") or "")
        row = rows.get(section_id, {})
        state = _section_state(section)
        action = _section_action(section, row)
        evidence = _clean_texts(section.get("evidence"))
        findings = _clean_texts(section.get("findings"))
        limitations = _section_limitations(section)
        lines.extend([
            "",
            f"## Technical review {index} of 7 — {section.get('label')} ({section.get('score')}/100)",
            "",
            f"**Decision impact:** {action['impact']}",
            "",
            f"- Evidence state: execution={state['execution']}; parsing={state['parsed']}; scoring={state['accepted']}; disposition={state['disposition']}.",
            f"- Required action: {action['action']}",
            f"- Accountable owner: {action['owner']}",
            f"- Estimated effort: {action['effort']}",
            f"- Verification: {action['verification']}",
            f"- Conditional weighted lift: to 80={action['conditional_lift_to_80']}; to 90={action['conditional_lift_to_90']}.",
            "",
            "### Evidence reviewed",
        ])
        lines.extend(f"- {item}" for item in evidence or ["No direct evidence item was retained."])
        lines.extend(["", "### Open findings and evidence limits"])
        lines.extend(f"- Finding: {item}" for item in findings or ["No material defect was confirmed in this control."])
        lines.extend(f"- Evidence limit: {item}" for item in limitations or ["No section-specific evidence limitation was retained; report-wide human review still applies."])
        breakdown = _dict(section.get("score_evidence_breakdown"))
        if breakdown:
            lines.extend(["", "### Score evidence"])
            for key, value in sorted(breakdown.items()):
                lines.append(f"- {key.replace('_', ' ').title()}: {_display(value)}")
        questions = _REVIEW_QUESTIONS.get(section_id, [])[:2]
        if questions:
            lines.extend(["", "### Reviewer questions"])
            lines.extend(f"- {item}" for item in questions)

    lines.extend(["", "## Prioritized remediation roadmap", ""])
    for index, item in enumerate(decision.get("action_plan") or [], 1):
        lines.extend([
            f"### P{index} — {item.get('label')}",
            f"- Why now: {item.get('impact')}",
            f"- Action: {item.get('action')}",
            f"- Owner: {item.get('owner')}",
            f"- Effort: {item.get('effort')}",
            f"- Verification: {item.get('verification')}",
        ])

    lines.extend(["", "## Human-context evidence requests", ""])
    for section in _context(payload):
        request = _CONTEXT_REQUESTS.get(str(section.get("id") or ""), "Direct reviewable context with source, owner, date, scope, and decision impact.")
        lines.append(f"- **{section.get('label')}**: {request}")

    lines.extend(["", "## Review exceptions and integrity", ""])
    for group in payload.get("grouped_review_exceptions") or []:
        lines.append(f"- **{group.get('review_priority')}** — {group.get('category').replace('_', ' ').title()}: {group.get('count')} item(s); examples: {'; '.join(group.get('examples') or [])}.")
    lines.extend([
        "",
        f"- Source identity SHA-256: `{payload.get('source_identity_sha256')}`",
        f"- Review packet SHA-256: `{_dict(payload.get('review_packet')).get('review_packet_sha256')}`",
        f"- Snapshot commit SHA: `{payload.get('snapshot_commit_sha')}`",
        "- Unsupported claims permitted: 0.",
        "- Human review is required before approval or client delivery.",
        "- NICO did not modify the assessed repository or create a branch, commit, pull request, or deployment.",
    ])
    return "\n".join(lines).strip() + "\n"


def _html(payload: dict[str, Any]) -> str:
    escaped = html.escape(_markdown(payload))
    return f"<!doctype html><html><head><meta charset='utf-8'><title>NICO Mid Technical Assessment</title></head><body><pre>{escaped}</pre></body></html>"


def _short_hash(value: Any) -> str:
    text = _display(value)
    if len(text) <= 34:
        return text
    return f"{text[:18]}…{text[-12:]}"


def _pdf(payload: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether, PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle
    from nico.report_flowable_safety import _bullets, _document_styles, _footer, _paragraph, _table

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.46 * inch,
        leftMargin=0.46 * inch,
        topMargin=0.40 * inch,
        bottomMargin=0.58 * inch,
        title="NICO Mid Technical Assessment",
        author="NICO",
        invariant=1,
    )
    styles = _document_styles("MidV6")
    title = ParagraphStyle("MidV6Title", parent=styles["title"], fontSize=17, leading=19.5, spaceAfter=4)
    subtitle = ParagraphStyle("MidV6Subtitle", parent=styles["small"], fontSize=8.1, leading=9.5, textColor=colors.HexColor("#cbd5e1"), spaceAfter=0)
    page_title = ParagraphStyle("MidV6PageTitle", parent=styles["title"], fontSize=17, leading=20, spaceAfter=7)
    h2 = ParagraphStyle("MidV6H2", parent=styles["h2"], fontSize=10.8, leading=12.5, spaceBefore=4, spaceAfter=2)
    body = ParagraphStyle("MidV6Body", parent=styles["body"], fontSize=7.7, leading=9.2, spaceAfter=2)
    small = ParagraphStyle("MidV6Small", parent=styles["small"], fontSize=7.0, leading=8.3, spaceAfter=1)
    p = _paragraph
    technical = _technical(payload)
    context = _context(payload)
    decision = _dict(payload.get("decision_summary"))
    integrity = _dict(payload.get("score_integrity"))
    coverage = _dict(payload.get("evidence_coverage"))
    score = _canonical_score(payload)
    rows = {str(row.get("section_id") or ""): row for row in _score_rows(payload)}

    hero = Table([
        [p("NICO MID TECHNICAL ASSESSMENT", title)],
        [p(f"{_DRAFT_LABEL} · Powered by Reparodynamics · immutable snapshot · human review required", subtitle)],
    ], colWidths=[7.08 * inch])
    hero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 9),
    ]))
    story: list[Any] = [
        hero,
        Spacer(1, 0.06 * inch),
        _table([
            [p("Repository", styles["label"]), p(payload.get("repository"), small), p("Run", styles["label"]), p(payload.get("run_id"), small)],
            [p("Snapshot", styles["label"]), p(_short_hash(payload.get("snapshot_commit_sha")), small), p("Report", styles["label"]), p(payload.get("report_id"), small)],
            [p("Score", styles["label"]), p(f"{score}/100", small), p("Evidence units", styles["label"]), p(f"{coverage.get('percent', 0)}% ({coverage.get('numerator', 0)}/{coverage.get('denominator', 0)})", small)],
            [p("Maturity", styles["label"]), p(decision.get("technical_maturity") or "Not provided", small), p("Review decision", styles["label"]), p(decision.get("review_decision"), small, 500)],
        ], [0.78 * inch, 2.72 * inch, 1.02 * inch, 2.56 * inch], header_color="#f8fafc"),
        p("Executive technical decision", h2),
        p(f"<b>{decision.get('review_decision')}</b> — {decision.get('review_decision_reason')}", styles["callout"], 1300),
        p("Primary constraints and accountable actions", h2),
    ]
    priority_rows = [[p("Control", styles["label"]), p("Constraint", styles["label"]), p("Required action", styles["label"]), p("Owner / effort", styles["label"])]]
    actions = {str(item.get("section_id") or ""): item for item in decision.get("action_plan") or []}
    for item in (decision.get("primary_score_constraints") or [])[:3]:
        action = actions.get(str(item.get("section_id") or ""), {})
        priority_rows.append([
            p(f"{item.get('label')}\n{item.get('score')}/100", small, 350),
            p(item.get("primary_reason"), small, 650),
            p(action.get("action"), small, 900),
            p(f"{action.get('owner')}\n{action.get('effort')}", small, 450),
        ])
    story.append(_table(priority_rows, [1.12 * inch, 1.72 * inch, 2.85 * inch, 1.39 * inch], header_color="#ecfeff"))
    story.append(p("Weighted technical scorecard", h2))
    score_rows = [[p("Control", styles["label"]), p("Truth", styles["label"]), p("Score", styles["label"]), p("Weight", styles["label"]), p("Points", styles["label"])]]
    for row in _score_rows(payload):
        score_rows.append([p(row.get("label"), small), p(row.get("truth_status"), small), p(str(row.get("score")), small), p(f"{row.get('weight')}%", small), p(str(row.get("weighted_contribution")), small)])
    story.append(_table(score_rows, [2.15 * inch, 1.72 * inch, 0.54 * inch, 0.62 * inch, 0.68 * inch]))
    strengths = _clean_texts(decision.get("verified_strengths"))[:3]
    if strengths:
        story.append(p("Verified strengths", h2))
        story.extend(_bullets(strengths, small, max_items=3))
    story.append(p(f"Canonical weighted score={score}; integrity match={_display(integrity.get('score_match'))}. Evidence-unit coverage is not analyzer-completion coverage.", small))

    story.extend([PageBreak(), p("Evidence Assurance and Score Sensitivity", page_title)])
    story.append(p("Evidence-state model", h2))
    story.append(_table([
        [p("State", styles["label"]), p("Meaning", styles["label"])],
        [p("Execution", small), p("The analyzer, workflow query, or repository collector ran for the authorized scope.", small)],
        [p("Parsing", small), p("NICO converted the output into structured evidence rather than retaining only a command conclusion.", small)],
        [p("Accepted for scoring", small), p("Evidence identity, snapshot binding, and truth rules allowed the result to influence the control score.", small)],
        [p("Disposition", small), p("A reviewer or verified automation classified each retained item as material, review-only, accepted risk, false positive, or repaired.", small)],
    ], [1.42 * inch, 5.66 * inch], header_color="#f1f5f9"))
    story.append(p("Evidence assurance matrix", h2))
    matrix_rows = [[p("Control", styles["label"]), p("Execution", styles["label"]), p("Parsing", styles["label"]), p("Scoring", styles["label"]), p("Disposition", styles["label"])]]
    for item in payload.get("evidence_assurance_matrix") or []:
        matrix_rows.append([p(item.get("label"), small), p(item.get("execution"), small), p(item.get("parsed"), small), p(item.get("accepted"), small), p(item.get("disposition"), small)])
    story.append(_table(matrix_rows, [1.68 * inch, 1.25 * inch, 1.05 * inch, 1.45 * inch, 1.65 * inch], header_color="#ecfeff"))
    story.append(p("Score sensitivity", h2))
    sensitivity_rows = [[p("Control", styles["label"]), p("Score", styles["label"]), p("Weight", styles["label"]), p("Conditional lift to 80", styles["label"]), p("Conditional lift to 90", styles["label"])]]
    for row in payload.get("score_sensitivity") or []:
        sensitivity_rows.append([p(row.get("label"), small), p(str(row.get("score")), small), p(f"{row.get('weight')}%", small), p(str(row.get("lift_to_80")), small), p(str(row.get("lift_to_90")), small)])
    story.append(_table(sensitivity_rows, [2.55 * inch, 0.58 * inch, 0.62 * inch, 1.05 * inch, 1.05 * inch]))
    story.append(p("Sensitivity is arithmetic, not a promise. A reassessment may remain unchanged or decline when stronger evidence reveals new findings.", styles["warning"], 1200))

    for index, section in enumerate(technical):
        if index % 2 == 0:
            story.extend([PageBreak(), p(f"Technical Control Review — {index + 1}–{min(index + 2, len(technical))} of {len(technical)}", page_title)])
        section_id = str(section.get("id") or "")
        row = rows.get(section_id, {})
        state = _section_state(section)
        action = _section_action(section, row)
        evidence = _clean_texts(section.get("evidence"))[:4]
        findings = _clean_texts(section.get("findings"))[:3]
        gaps = _section_limitations(section)[:3]
        block: list[Any] = []
        heading = Table([[p(f"{index + 1}. {section.get('label')}", h2), p(f"{section.get('score')}/100 · {_WEIGHTS.get(section_id)}% weight", h2)]], colWidths=[4.7 * inch, 2.38 * inch])
        heading.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e0f2fe")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        block.append(heading)
        block.append(_table([
            [p("Execution", styles["label"]), p("Parsing", styles["label"]), p("Accepted for scoring", styles["label"]), p("Disposition", styles["label"])],
            [p(state["execution"], small), p(state["parsed"], small), p(state["accepted"], small), p(state["disposition"], small)],
        ], [1.55 * inch, 1.25 * inch, 1.85 * inch, 2.43 * inch], header_color="#f8fafc"))
        block.append(p(f"<b>Decision impact:</b> {action['impact']}", body, 1000))
        block.append(p(f"<b>Required action:</b> {action['action']}", body, 1200))
        block.append(p(f"<b>Owner / effort:</b> {action['owner']} / {action['effort']} · <b>Conditional lift:</b> to 80={action['conditional_lift_to_80']}, to 90={action['conditional_lift_to_90']}", small, 1000))
        evidence_items = [f"Evidence: {item}" for item in evidence] or ["Evidence: No direct evidence item was retained."]
        issue_items = [f"Open finding: {item}" for item in findings] or ["Open finding: No material defect was confirmed in this control."]
        issue_items += [f"Evidence limit: {item}" for item in gaps]
        block.extend(_bullets((evidence_items + issue_items)[:7], small, max_items=7))
        breakdown = _dict(section.get("score_evidence_breakdown"))
        if breakdown:
            compact_rows = [[p("Score factor", styles["label"]), p("Retained value", styles["label"])]]
            for key, value in list(sorted(breakdown.items()))[:5]:
                compact_rows.append([p(str(key).replace("_", " ").title(), small), p(_display(value), small, 450)])
            block.append(_table(compact_rows, [2.45 * inch, 4.63 * inch], header_color="#f8fafc"))
        block.append(p(f"<b>Verification proof:</b> {action['verification']}", body, 1100))
        block.append(Spacer(1, 0.10 * inch))
        story.append(KeepTogether(block))

    story.extend([PageBreak(), p("Prioritized Remediation Roadmap", page_title)])
    story.append(p("The roadmap below is report-only. Implementation ownership, approval, and deployment remain human responsibilities.", styles["callout"], 1200))
    roadmap_rows = [[p("Priority", styles["label"]), p("Control and decision impact", styles["label"]), p("Action", styles["label"]), p("Owner / effort", styles["label"]), p("Verification", styles["label"])]]
    for index, item in enumerate((decision.get("action_plan") or [])[:5], 1):
        roadmap_rows.append([
            p(f"P{index}", small),
            p(f"{item.get('label')}\n{item.get('impact')}", small, 650),
            p(item.get("action"), small, 850),
            p(f"{item.get('owner')}\n{item.get('effort')}", small, 450),
            p(item.get("verification"), small, 700),
        ])
    story.append(_table(roadmap_rows, [0.42 * inch, 1.63 * inch, 2.12 * inch, 1.22 * inch, 1.69 * inch], header_color="#ecfeff"))
    story.append(p("CI/CD non-success classification required", h2))
    story.append(_table([
        [p("Classification", styles["label"]), p("Required evidence", styles["label"])],
        [p("Product regression", small), p("Failing job, first bad commit, affected behavior, repair, and passing rerun.", small)],
        [p("Test assertion", small), p("Assertion, expected behavior, whether test or product was wrong, and disposition.", small)],
        [p("Build/configuration", small), p("Toolchain or configuration error, affected branch, correction, and stable rerun.", small)],
        [p("Cancelled / superseded", small), p("Replacement run or superseding commit proving the cancellation is non-defective.", small)],
        [p("Transient infrastructure", small), p("Provider or network evidence, retry outcome, and recurrence assessment.", small)],
        [p("Unresolved", small), p("Assigned owner, target date, blocking impact, and required next diagnostic.", small)],
    ], [1.55 * inch, 5.53 * inch], header_color="#f1f5f9"))
    story.append(p("Human-context modules — unscored", h2))
    context_rows = [[p("Module", styles["label"]), p("Evidence request", styles["label"])]]
    for section in context:
        request = _CONTEXT_REQUESTS.get(str(section.get("id") or ""), "Direct reviewable context with source, owner, date, scope, and decision impact.")
        context_rows.append([p(section.get("label"), small), p(request, small, 900)])
    story.append(_table(context_rows, [1.70 * inch, 5.38 * inch], header_color="#f8fafc"))

    story.extend([PageBreak(), p("Review Exceptions, Integrity, and Approval Boundary", page_title)])
    story.append(p(f"Original exception records: {payload.get('review_exception_original_count', 0)}. Decision-ready deduplicated items: {payload.get('review_exception_final_count', 0)}.", styles["callout"]))
    grouped = payload.get("grouped_review_exceptions") or []
    if grouped:
        grouped_rows = [[p("Review priority", styles["label"]), p("Exception group", styles["label"]), p("Count", styles["label"]), p("Examples", styles["label"])]]
        for item in grouped:
            grouped_rows.append([p(item.get("review_priority"), small), p(str(item.get("category") or "").replace("_", " ").title(), small), p(str(item.get("count")), small), p("; ".join(item.get("examples") or []), small, 650)])
        story.append(_table(grouped_rows, [1.28 * inch, 2.15 * inch, 0.48 * inch, 3.17 * inch], header_color="#fef3c7"))
    story.append(p("Integrity identity", h2))
    story.append(_table([
        [p("Identity field", styles["label"]), p("PDF display value", styles["label"]), p("Use", styles["label"])],
        [p("Source identity SHA-256", small), p(_short_hash(payload.get("source_identity_sha256")), small), p("Binds the report source truth.", small)],
        [p("Review packet SHA-256", small), p(_short_hash(_dict(payload.get("review_packet")).get("review_packet_sha256")), small), p("Binds the reviewable evidence packet.", small)],
        [p("Snapshot commit SHA", small), p(_short_hash(payload.get("snapshot_commit_sha")), small), p("Binds findings and scores to one immutable repository state.", small)],
        [p("Report contract", small), p(payload.get("report_version"), small), p("Preserves the underlying report data contract.", small)],
        [p("Presentation", small), p(payload.get("presentation_version"), small), p("Identifies this decision-ready rendering.", small)],
    ], [1.55 * inch, 3.05 * inch, 2.48 * inch], header_color="#f1f5f9"))
    story.append(p("Full hashes remain in Markdown and JSON exports; the PDF uses shortened values for readability.", small))
    story.append(p("Final approval boundary", h2))
    story.extend(_bullets([
        "Human review is required before approval or client delivery.",
        "NICO did not modify the assessed repository or automatically apply report suggestions.",
        "A recommendation is not evidence that a repair was implemented or effective.",
        "A clean scanner result is not proof that no vulnerability, defect, or credential exists.",
        "Only this exact report identity and attached evidence packet may be reviewed for approval.",
    ], body, max_items=8))

    footer = _footer("NICO Mid · evidence-bound · immutable snapshot · human review required")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def install_mid_report_professional_v6() -> dict[str, Any]:
    from nico import mid_assessment_report as report_module

    if getattr(report_module, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": MID_REPORT_V6_VERSION}
    current_payload = report_module._report_payload

    def payload_v6(record: dict[str, Any], packet: dict[str, Any], identity: dict[str, Any], generated_at: str) -> dict[str, Any]:
        return _enhance(current_payload(record, packet, identity, generated_at))

    report_module._report_payload = payload_v6
    report_module._markdown = _markdown
    report_module._html = _html
    report_module._pdf = _pdf
    setattr(report_module, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "version": MID_REPORT_V6_VERSION,
        "target_pdf_pages": 8,
        "paired_technical_dossiers": True,
        "evidence_assurance_matrix": True,
        "finding_specific_action_plan": True,
        "blank_values_normalized": True,
        "full_hashes_retained_in_markdown_and_json": True,
        "report_only": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["MID_REPORT_V6_VERSION", "install_mid_report_professional_v6"]
