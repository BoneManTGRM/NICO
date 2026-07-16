from __future__ import annotations

import html
import io
from copy import deepcopy
from typing import Any

MID_REPORT_V4_VERSION = "mid-assessment-draft-v4-full-depth"
_PATCH_MARKER = "_nico_mid_report_professional_v4"
_WEIGHTS = {
    "code_audit": 20,
    "dependency_health": 15,
    "secrets_review": 10,
    "static_analysis": 15,
    "ci_cd": 15,
    "architecture_debt": 15,
    "velocity_complexity": 10,
}
_REVIEW_QUESTIONS = {
    "code_audit": [
        "Are every sampled risk-pattern hit and affected path identified and dispositioned?",
        "Do retained tests exercise the changed or high-risk code paths?",
        "Would line-by-line semantic review materially change this bounded conclusion?",
    ],
    "dependency_health": [
        "Are manifests and lockfiles aligned with the deployed application?",
        "Were vulnerability results parsed, deduplicated, and mapped to direct dependencies?",
        "Is a second structured dependency source required for corroboration?",
    ],
    "secrets_review": [
        "Were current-tree and history-oriented credential checks both completed where authorized?",
        "Were candidate secrets verified, rotated, and removed where necessary?",
        "Does deployment-provider evidence reveal secrets outside this snapshot?",
    ],
    "static_analysis": [
        "Did each requested analyzer produce parseable exact-snapshot output?",
        "Were production findings separated from tests, generated files, and accepted risk?",
        "Are TypeScript compilation and lint-rule coverage represented as distinct controls?",
    ],
    "ci_cd": [
        "Do failing and cancelled runs have known, reviewed causes?",
        "Are required checks, permissions, branch protections, and artifact retention configured?",
        "Are flaky jobs separated from reproducible product or infrastructure failures?",
    ],
    "architecture_debt": [
        "Do repository boundaries match the intended runtime and ownership model?",
        "Are complexity, duplication, coupling, and dependency-direction hotspots identified?",
        "Which debt items could constrain reliability or delivery in the next release cycle?",
    ],
    "velocity_complexity": [
        "Does commit and pull-request activity provide adequate review traceability?",
        "Are complexity and churn concentrated in a small set of files or contributors?",
        "What stakeholder context is required to connect activity to delivered business value?",
    ],
}
_CONTEXT_REQUESTS = {
    "functional_qa": "Runnable build or test environment, acceptance criteria, expected workflows, and recent defect evidence.",
    "platform_parity": "Relevant platform builds, supported versions, expected parity, and platform-specific test results.",
    "architecture_context": "Architecture diagrams, service boundaries, data flows, operational dependencies, and deployment topology.",
    "stakeholder_alignment": "Stakeholder notes, objectives, constraints, decision ownership, and unresolved disagreements.",
    "business_roadmap": "Prioritized outcomes, milestones, constraints, dependencies, target dates, and success measures.",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _texts(value: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in _list(value):
        text = " ".join(str(item or "").split())
        if text and text.lower() not in seen:
            seen.add(text.lower())
            output.append(text)
    return output


def _score(value: Any) -> int | None:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return None


def _technical(payload: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {str(item.get("id") or ""): item for item in _list(payload.get("sections")) if isinstance(item, dict)}
    return [by_id[key] for key in _WEIGHTS if key in by_id]


def _context(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _list(payload.get("sections")) if isinstance(item, dict) and str(item.get("id") or "") not in _WEIGHTS]


def _score_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [dict(item) for item in _list(_dict(payload.get("score_integrity")).get("weighted_rows")) if isinstance(item, dict)]
    if rows:
        return rows
    output = []
    for section in _technical(payload):
        score = _score(section.get("score"))
        weight = _WEIGHTS.get(str(section.get("id") or ""))
        if score is None or weight is None:
            continue
        output.append({
            "section_id": section.get("id"),
            "label": section.get("label"),
            "score": score,
            "weight": weight,
            "weighted_contribution": round(score * weight / 100, 2),
            "truth_status": section.get("truth_status"),
        })
    return output


def _enhance(payload: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(payload)
    rows = _score_rows(output)
    sensitivity = []
    for row in rows:
        score = _score(row.get("score"))
        weight = int(row.get("weight") or 0)
        if score is None or not weight:
            continue
        sensitivity.append({
            **row,
            "lift_to_80": round(max(0, 80 - score) * weight / 100, 2),
            "lift_to_90": round(max(0, 90 - score) * weight / 100, 2),
            "weighted_gap": round((100 - score) * weight / 100, 2),
        })
    output.update({
        "report_version": MID_REPORT_V4_VERSION,
        "detail_level": 4,
        "score_sensitivity": sorted(sensitivity, key=lambda item: item["weighted_gap"], reverse=True),
        "report_depth_contract": {
            "minimum_pdf_pages": 11,
            "dedicated_technical_dossiers": len(_technical(output)),
            "methodology_section": True,
            "repair_roadmap": True,
            "context_evidence_requests": True,
            "review_exception_appendix": True,
            "page_count_is_not_a_quality_substitute": True,
        },
    })
    return output


def _markdown(payload: dict[str, Any]) -> str:
    decision = _dict(payload.get("decision_summary"))
    lines = [
        "# NICO MID TECHNICAL ASSESSMENT",
        "",
        "**DRAFT - SNAPSHOT-BOUND - EVIDENCE-BOUND - HUMAN REVIEW REQUIRED**",
        "",
        f"- Repository: `{payload.get('repository')}`",
        f"- Run: `{payload.get('run_id')}`",
        f"- Snapshot: `{payload.get('snapshot_commit_sha')}`",
        f"- Technical score: **{decision.get('technical_score')}/100**",
        "",
        "## Assessment scope and methodology",
        "",
        "- Seven fixed-weight technical sections determine the score.",
        "- Missing or failed evidence is disclosed and never converted into a pass.",
        "- Analyzer execution is not equivalent to a clean finding result.",
        "- Human-context modules remain unscored until validated by a human reviewer.",
        "- Score changes require verified remediation and a new immutable snapshot.",
        "",
        "## Score sensitivity",
        "",
    ]
    for row in payload.get("score_sensitivity") or []:
        lines.append(f"- {row.get('label')}: lift to 80={row.get('lift_to_80')}; lift to 90={row.get('lift_to_90')}; maximum weighted gap={row.get('weighted_gap')}.")
    for index, section in enumerate(_technical(payload), 1):
        limits = _texts(section.get("unavailable")) + _texts(section.get("missing_evidence_sources")) + _texts(section.get("failed_evidence_tools"))
        lines.extend([
            "",
            f"## Technical dossier {index}: {section.get('label')} - {section.get('score')}/100",
            "",
            f"- Truth status: {section.get('truth_status')}",
            f"- Confidence: {section.get('confidence') or 'evidence-bound'}",
            "",
            str(section.get("summary") or ""),
            "",
            "### Evidence reviewed",
        ])
        lines.extend(f"- {item}" for item in _texts(section.get("evidence")) or ["No direct evidence item was retained."])
        lines.extend(["", "### Findings"])
        lines.extend(f"- {item}" for item in _texts(section.get("findings")) or ["No specific repair finding was retained; reviewer validation remains required."])
        lines.extend(["", "### Limitations and scope boundaries"])
        lines.extend(f"- {item}" for item in limits + _texts(section.get("scope_disclosures")) or ["The report-wide evidence and human-review boundaries apply."])
        lines.extend(["", "### Reviewer questions"])
        lines.extend(f"- {item}" for item in _REVIEW_QUESTIONS.get(str(section.get("id") or ""), []))
    lines.extend(["", "## Prioritized repair roadmap", ""])
    for item in _list(_dict(payload.get("repair_intelligence")).get("candidates"))[:12]:
        if isinstance(item, dict):
            lines.extend([
                f"### P{item.get('rank', '?')} - {item.get('title')}",
                f"- Severity: {item.get('severity')} | Priority: {item.get('priority_score')} | Effort: {item.get('effort')}",
                f"- Action: {item.get('recommended_action')}",
                f"- Verification: {'; '.join(_texts(item.get('test_plan')))}",
                "",
            ])
    lines.extend(["## Human-context evidence requests", ""])
    for section in _context(payload):
        request = _CONTEXT_REQUESTS.get(str(section.get("id") or ""), "Direct reviewable context with source, date, owner, scope, and decision impact.")
        lines.append(f"- {section.get('label')} ({section.get('truth_status')}): {request}")
    lines.extend(["", "## Review by exception", ""])
    for item in payload.get("deduplicated_review_exceptions") or []:
        lines.append(f"- {str(item.get('severity') or 'medium').upper()} - {item.get('title') or item.get('category')}: {item.get('reason')}")
    lines.extend([
        "",
        "## Integrity boundary",
        "",
        f"- Source identity SHA-256: `{payload.get('source_identity_sha256')}`",
        f"- Review packet SHA-256: `{_dict(payload.get('review_packet')).get('review_packet_sha256')}`",
        f"- Snapshot commit SHA: `{payload.get('snapshot_commit_sha')}`",
        "- Unsupported claims permitted: 0.",
        "- Human review is required before approval or client delivery.",
    ])
    return "\n".join(lines).strip() + "\n"


def _html(payload: dict[str, Any]) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><title>NICO Mid Assessment</title></head><body><pre>{html.escape(_markdown(payload))}</pre></body></html>"


def _pdf(payload: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle
    from nico.report_flowable_safety import _bullets, _document_styles, _footer, _paragraph, _table

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.56 * inch, leftMargin=0.56 * inch, topMargin=0.52 * inch, bottomMargin=0.68 * inch, title="NICO Mid Technical Assessment", author="NICO", invariant=1)
    styles = _document_styles("MidV4")
    page_title = ParagraphStyle("MidV4PageTitle", parent=styles["title"], fontSize=19, leading=23, spaceAfter=10)
    p = _paragraph
    technical = _technical(payload)
    context = _context(payload)
    decision = _dict(payload.get("decision_summary"))
    integrity = _dict(payload.get("score_integrity"))
    coverage = _dict(payload.get("evidence_coverage"))
    repairs = [item for item in _list(_dict(payload.get("repair_intelligence")).get("candidates")) if isinstance(item, dict)]
    exceptions = [item for item in _list(payload.get("deduplicated_review_exceptions")) if isinstance(item, dict)]

    hero = Table([[p("NICO MID TECHNICAL ASSESSMENT", page_title)]], colWidths=[7.0 * inch])
    hero.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")), ("TEXTCOLOR", (0, 0), (-1, -1), colors.white), ("TOPPADDING", (0, 0), (-1, -1), 16), ("BOTTOMPADDING", (0, 0), (-1, -1), 16)]))
    story: list[Any] = [
        hero,
        Spacer(1, 0.10 * inch),
        p("Powered by Reparodynamics - full-depth - snapshot-bound - human review required", styles["callout"]),
        _table([
            [p("Repository", styles["label"]), p(payload.get("repository"), styles["small"]), p("Run", styles["label"]), p(payload.get("run_id"), styles["small"])],
            [p("Snapshot", styles["label"]), p(payload.get("snapshot_commit_sha"), styles["small"], 350), p("Report", styles["label"]), p(payload.get("report_id"), styles["small"], 350)],
            [p("Maturity", styles["label"]), p(decision.get("technical_maturity"), styles["small"]), p("Score", styles["label"]), p(f"{decision.get('technical_score')}/100", styles["small"])],
            [p("Coverage", styles["label"]), p(f"{coverage.get('percent', 0)}%", styles["small"]), p("Delivery", styles["label"]), p("HUMAN REVIEW REQUIRED", styles["small"])],
        ], [0.82 * inch, 2.70 * inch, 0.72 * inch, 2.76 * inch], header_color="#f8fafc"),
        p("Executive Decision", styles["h2"]),
        p("This Mid report is a full technical review packet, not a compressed score sheet. It separates verified controls, score constraints, evidence limitations, reviewer questions, remediation candidates, and the proof required before any score change.", styles["callout"], 1500),
    ]
    decision_rows = [[p("Decision area", styles["label"]), p("Current result", styles["label"])]]
    decision_rows.extend([
        [p("Primary constraints", styles["small"]), p("; ".join(f"{item.get('label')} {item.get('score')}/100" for item in (decision.get("primary_score_constraints") or [])[:5]) or "No constraint summary returned.", styles["small"], 1000)],
        [p("Verified strengths", styles["small"]), p("; ".join(decision.get("verified_strengths") or []) or "No verified strength summary returned.", styles["small"], 1000)],
        [p("Immediate actions", styles["small"]), p("; ".join(decision.get("recommended_actions") or []) or "Human review of the report.", styles["small"], 1000)],
        [p("Delivery gate", styles["small"]), p("Client delivery remains disabled until an authorized reviewer approves this exact report identity.", styles["small"], 1000)],
    ])
    story.append(_table(decision_rows, [1.42 * inch, 5.58 * inch], header_color="#ecfeff"))
    story.append(p("Weighted Technical Scorecard", styles["h2"]))
    score_rows = [[p("Area", styles["label"]), p("Truth", styles["label"]), p("Score", styles["label"]), p("Weight", styles["label"]), p("Contribution", styles["label"])]]
    for row in _score_rows(payload):
        score_rows.append([p(row.get("label"), styles["small"]), p(row.get("truth_status"), styles["small"]), p(str(row.get("score")), styles["small"]), p(f"{row.get('weight')}%", styles["small"]), p(str(row.get("weighted_contribution")), styles["small"])])
    story.append(_table(score_rows, [2.12 * inch, 1.72 * inch, 0.55 * inch, 0.62 * inch, 0.86 * inch]))
    story.append(p(f"Calculated score={integrity.get('calculated_score')}; final report score={integrity.get('final_report_score', integrity.get('reported_score'))}; match={integrity.get('score_match')}. Coverage and human-context modules do not directly change this score.", styles["small"]))

    story.extend([PageBreak(), p("Assessment Scope and Methodology", page_title)])
    story.append(p("What is assessed", styles["h2"]))
    story.extend(_bullets([
        "Seven fixed-weight technical sections using repository, analyzer, workflow, and bounded activity evidence.",
        "Exact-snapshot code conclusions bound to the captured commit SHA.",
        "Time-window operational evidence for commits, pull requests, workflows, and delivery signals.",
        "Five human-context modules retained as unscored evidence requests until reviewer validation.",
    ], styles["small"], max_items=8))
    story.append(p("Truth and scoring rules", styles["h2"]))
    story.extend(_bullets([
        "Missing or failed evidence is disclosed and is never converted into a pass or healthy result.",
        "Analyzer execution coverage is separate from parsed finding severity and disposition.",
        "A clean bounded result does not prove that no vulnerability, defect, or credential exists.",
        "Score changes require completed repair evidence and a new immutable snapshot assessment.",
        "NICO did not modify the repository, create a branch, commit, pull request, or deployment.",
    ], styles["small"], max_items=10))
    story.append(p("Evidence coverage", styles["h2"]))
    story.append(_table([
        [p("Measure", styles["label"]), p("Result", styles["label"])],
        [p("Coverage", styles["small"]), p(f"{coverage.get('percent', 0)}% ({coverage.get('numerator', 0)}/{coverage.get('denominator', 0)})", styles["small"])],
        [p("Method", styles["small"]), p(coverage.get("method") or "Coverage is calculated from explicit evidence units.", styles["small"], 1200)],
        [p("Interpretation", styles["small"]), p("Coverage measures evidence availability, not technical maturity, and does not directly alter the score.", styles["small"], 1200)],
    ], [1.55 * inch, 5.45 * inch], header_color="#f1f5f9"))
    story.append(p("Report architecture", styles["h2"]))
    story.extend(_bullets([
        "Executive decision and weighted scorecard.",
        "Methodology and evidence interpretation.",
        "Score sensitivity and bounded improvement scenarios.",
        "Seven dedicated technical review dossiers.",
        "Prioritized repair roadmap and verification requirements.",
        "Human-context evidence requests, review exceptions, and integrity identity.",
    ], styles["small"], max_items=10))

    story.extend([PageBreak(), p("Score Intelligence and Sensitivity", page_title)])
    story.append(p("The score is the sum of each section score multiplied by its fixed weight. Sensitivity values are arithmetic scenarios, not promises.", styles["callout"], 1400))
    sensitivity_rows = [[p("Area", styles["label"]), p("Current", styles["label"]), p("Weight", styles["label"]), p("Lift to 80", styles["label"]), p("Lift to 90", styles["label"]), p("Max gap", styles["label"])]]
    for row in payload.get("score_sensitivity") or []:
        sensitivity_rows.append([p(row.get("label"), styles["small"]), p(str(row.get("score")), styles["small"]), p(f"{row.get('weight')}%", styles["small"]), p(str(row.get("lift_to_80")), styles["small"]), p(str(row.get("lift_to_90")), styles["small"]), p(str(row.get("weighted_gap")), styles["small"])])
    story.append(_table(sensitivity_rows, [2.05 * inch, 0.62 * inch, 0.62 * inch, 0.78 * inch, 0.78 * inch, 0.78 * inch]))
    story.append(p("Primary score constraints", styles["h2"]))
    constraint_rows = [[p("Rank", styles["label"]), p("Area", styles["label"]), p("Score", styles["label"]), p("Reason", styles["label"])]]
    for index, item in enumerate(decision.get("primary_score_constraints") or [], 1):
        constraint_rows.append([p(str(index), styles["small"]), p(item.get("label"), styles["small"]), p(str(item.get("score")), styles["small"]), p(item.get("primary_reason"), styles["small"], 900)])
    story.append(_table(constraint_rows, [0.42 * inch, 1.75 * inch, 0.60 * inch, 4.23 * inch], header_color="#fef3c7"))
    story.append(p("A future score can remain unchanged or decline if reassessment discovers new findings or weaker evidence. Recommendations alone never raise a score.", styles["warning"], 1400))

    for index, section in enumerate(technical, 1):
        section_id = str(section.get("id") or "")
        score = _score(section.get("score"))
        weight = _WEIGHTS.get(section_id)
        contribution = next((row.get("weighted_contribution") for row in _score_rows(payload) if str(row.get("section_id") or "") == section_id), None)
        limitations = _texts(section.get("unavailable")) + _texts(section.get("missing_evidence_sources")) + _texts(section.get("failed_evidence_tools"))
        story.extend([PageBreak(), p(f"Technical Review Dossier {index} of {len(technical)}", page_title)])
        story.append(_table([
            [p("Domain", styles["label"]), p("Score", styles["label"]), p("Weight", styles["label"]), p("Contribution", styles["label"]), p("Truth", styles["label"]), p("Confidence", styles["label"])],
            [p(section.get("label"), styles["small"]), p(f"{score}/100" if score is not None else "Not scored", styles["small"]), p(f"{weight}%", styles["small"]), p(str(contribution), styles["small"]), p(section.get("truth_status"), styles["small"]), p(section.get("confidence") or "evidence-bound", styles["small"])],
        ], [1.75 * inch, 0.68 * inch, 0.58 * inch, 0.84 * inch, 1.42 * inch, 1.73 * inch], header_color="#ecfeff"))
        story.append(p("Evidence-bound conclusion", styles["h2"]))
        story.append(p(section.get("summary"), styles["callout"], 1500))
        story.append(p("Evidence reviewed", styles["h2"]))
        story.extend(_bullets(_texts(section.get("evidence")) or ["No direct evidence item was retained."], styles["small"], max_items=10))
        story.append(p("Actionable findings", styles["h2"]))
        story.extend(_bullets(_texts(section.get("findings")) or ["No specific repair finding was retained; reviewer validation remains required."], styles["small"], max_items=8))
        story.append(p("Material limitations and scope boundaries", styles["h2"]))
        story.extend(_bullets(limitations + _texts(section.get("scope_disclosures")) or ["The report-wide evidence and human-review boundaries apply."], styles["small"], max_items=10))
        breakdown = _dict(section.get("score_evidence_breakdown"))
        if breakdown:
            story.append(p("Score evidence breakdown", styles["h2"]))
            breakdown_rows = [[p("Evidence factor", styles["label"]), p("Retained value", styles["label"])]]
            for key, value in sorted(breakdown.items()):
                breakdown_rows.append([p(str(key).replace("_", " ").title(), styles["small"]), p(value, styles["small"], 1000)])
            story.append(_table(breakdown_rows, [2.35 * inch, 4.65 * inch], header_color="#f1f5f9"))
        story.append(p("Reviewer decision questions", styles["h2"]))
        story.extend(_bullets(_REVIEW_QUESTIONS.get(section_id, []), styles["small"], max_items=8))
        story.append(p("Evidence required before score improvement", styles["h2"]))
        story.extend(_bullets(limitations[:4] or ["Retain the exact source artifact, analyzer output, reviewer disposition, relevant tests, and a new immutable snapshot rescan."], styles["small"], max_items=8))
        story.append(p("A recommendation is not evidence of completion. The reviewer must verify implementation, relevant tests, analyzer output where applicable, and the post-repair snapshot before accepting a score change.", styles["warning"], 1400))

    story.extend([PageBreak(), p("Prioritized Repair Roadmap", page_title)])
    story.append(p("Repairs are report-only candidates. The responsible owner, implementation method, and acceptance decision remain human responsibilities.", styles["callout"], 1400))
    if repairs:
        repair_rows = [[p("Rank", styles["label"]), p("Finding", styles["label"]), p("Severity", styles["label"]), p("Priority", styles["label"]), p("Effort", styles["label"])]]
        for item in repairs[:12]:
            repair_rows.append([p(f"P{item.get('rank', '?')}", styles["small"]), p(item.get("title"), styles["small"], 500), p(str(item.get("severity") or "unknown").upper(), styles["small"]), p(str(item.get("priority_score") or "N/A"), styles["small"]), p(str(item.get("effort") or "unknown").upper(), styles["small"])])
        story.append(_table(repair_rows, [0.42 * inch, 3.85 * inch, 0.78 * inch, 0.72 * inch, 0.72 * inch], header_color="#ecfeff"))
        for item in repairs[:8]:
            story.append(p(f"P{item.get('rank', '?')} - {item.get('title')}", styles["h2"]))
            story.append(p(f"Recommended action: {item.get('recommended_action')}", styles["body"], 1300))
            story.append(p(f"Verification plan: {'; '.join(_texts(item.get('test_plan'))) or 'Run the smallest relevant test, the full validation suite, and a NICO rescan.'}", styles["small"], 1100))
            story.append(p("Completion evidence: implementation reference, reviewer disposition, test output, relevant analyzer output, and immutable post-repair commit SHA.", styles["small"], 1000))
    else:
        story.append(p("No ranked repair candidate was retained. Human review of each section remains required.", styles["warning"]))
    story.append(p("Execution sequence", styles["h2"]))
    story.extend(_bullets([
        "Stabilize evidence collection: resolve failed, unavailable, or non-parseable analyzer output.",
        "Disposition findings: verify, fix, accept risk, or document false positives with reviewer identity and date.",
        "Improve structural controls: tests, lockfiles, workflow permissions, branch protections, documentation, and architecture boundaries.",
        "Reassess only after the resulting state is captured as a new immutable snapshot.",
    ], styles["small"], max_items=8))

    story.extend([PageBreak(), p("Human-Context Evidence Requests", page_title)])
    story.append(p("These modules require evidence a repository scan cannot prove. They remain unscored until an authorized reviewer validates the submitted material.", styles["callout"], 1400))
    context_rows = [[p("Module", styles["label"]), p("Status", styles["label"]), p("Evidence request", styles["label"])]]
    for section in context:
        request = _CONTEXT_REQUESTS.get(str(section.get("id") or ""), "Direct reviewable context with source, date, owner, scope, and decision impact.")
        context_rows.append([p(section.get("label"), styles["small"]), p(section.get("truth_status"), styles["small"]), p(request, styles["small"], 900)])
    story.append(_table(context_rows, [1.65 * inch, 1.10 * inch, 4.25 * inch], header_color="#f1f5f9"))
    for section in context:
        request = _CONTEXT_REQUESTS.get(str(section.get("id") or ""), "Direct reviewable context with source, date, owner, scope, and decision impact.")
        story.append(p(section.get("label"), styles["h2"]))
        story.append(p(f"Requested evidence: {request}", styles["body"], 1200))
        story.append(p(f"Currently attached: {'; '.join(_texts(section.get('evidence'))) or 'No validated external context attached.'}", styles["small"], 1000))
    story.append(p("Submitted context may inform final human review but cannot silently rewrite the seven-section technical score.", styles["warning"], 1300))

    story.extend([PageBreak(), p("Review by Exception and Integrity", page_title)])
    story.append(p(f"Original exception records: {payload.get('review_exception_original_count', 0)}. Decision-ready deduplicated items: {payload.get('review_exception_final_count', 0)}.", styles["callout"]))
    if exceptions:
        exception_rows = [[p("Severity", styles["label"]), p("Title", styles["label"]), p("Section", styles["label"]), p("Reason", styles["label"])]]
        for item in exceptions:
            exception_rows.append([p(str(item.get("severity") or "medium").upper(), styles["small"]), p(item.get("title") or item.get("category"), styles["small"], 400), p(item.get("section_id") or "general", styles["small"]), p(item.get("reason") or "Human review required.", styles["small"], 800)])
        story.append(_table(exception_rows, [0.72 * inch, 1.85 * inch, 1.12 * inch, 3.31 * inch], header_color="#fef3c7"))
        for item in exceptions:
            story.append(p(f"{str(item.get('severity') or 'medium').upper()} - {item.get('title') or item.get('category')}", styles["h3"]))
            story.append(p(item.get("reason") or "Human review required.", styles["body"], 1000))
            story.extend(_bullets(item.get("blockers"), styles["small"], max_items=8))
    else:
        story.append(p("No review exception was generated. Human approval is still required.", styles["warning"]))
    story.append(p("Integrity identity", styles["h2"]))
    story.append(_table([
        [p("Identity field", styles["label"]), p("Value", styles["label"])],
        [p("Source identity SHA-256", styles["small"]), p(payload.get("source_identity_sha256"), styles["small"], 1200)],
        [p("Review packet SHA-256", styles["small"]), p(_dict(payload.get("review_packet")).get("review_packet_sha256"), styles["small"], 1200)],
        [p("Snapshot commit SHA", styles["small"]), p(payload.get("snapshot_commit_sha"), styles["small"], 1200)],
        [p("Report version", styles["small"]), p(payload.get("report_version"), styles["small"])],
        [p("Unsupported claims permitted", styles["small"]), p("0", styles["small"])],
    ], [1.85 * inch, 5.15 * inch], header_color="#f1f5f9"))
    story.append(p("Final safety boundary", styles["h2"]))
    story.extend(_bullets([
        "Human review is required before approval or client delivery.",
        "NICO did not modify the assessed repository or automatically apply report suggestions.",
        "A recommendation is not evidence that a repair was implemented or effective.",
        "A clean scanner result is not proof that no vulnerability, defect, or credential exists.",
        "Only this exact report identity and attached evidence packet may be reviewed for approval.",
    ], styles["small"], max_items=8))

    footer = _footer("NICO Mid - full-depth - snapshot-bound - human review required")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def install_mid_report_professional_v4() -> dict[str, Any]:
    from nico import mid_assessment_report as report_module

    if getattr(report_module, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": MID_REPORT_V4_VERSION}
    current_payload = report_module._report_payload

    def payload_v4(record: dict[str, Any], packet: dict[str, Any], identity: dict[str, Any], generated_at: str) -> dict[str, Any]:
        return _enhance(current_payload(record, packet, identity, generated_at))

    report_module._report_payload = payload_v4
    report_module._markdown = _markdown
    report_module._html = _html
    report_module._pdf = _pdf
    report_module.MID_REPORT_VERSION = MID_REPORT_V4_VERSION
    setattr(report_module, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "version": MID_REPORT_V4_VERSION,
        "minimum_pdf_pages": 11,
        "dedicated_technical_dossiers": 7,
        "full_evidence_display": True,
        "score_sensitivity": True,
        "repair_roadmap": True,
        "context_evidence_requests": True,
        "review_exception_appendix": True,
        "report_only": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["MID_REPORT_V4_VERSION", "install_mid_report_professional_v4"]
