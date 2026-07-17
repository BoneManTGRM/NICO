from __future__ import annotations

import io
from copy import deepcopy
from typing import Any

from nico import mid_report_professional_v6 as v6

VERSION = "mid-assessment-draft-v7-premium"


def _text(value: Any, fallback: str = "Not provided") -> str:
    if value is None:
        return fallback
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if item) or fallback
    if isinstance(value, dict):
        return "; ".join(f"{key}={item}" for key, item in sorted(value.items())) or fallback
    return " ".join(str(value).split()) or fallback


def _premium_enhance(payload: dict[str, Any]) -> dict[str, Any]:
    output = v6._enhance(payload)
    output = deepcopy(output)
    output["presentation_version"] = VERSION
    output["presentation_detail_level"] = 7
    output["report_depth_contract"] = {
        **dict(output.get("report_depth_contract") or {}),
        "minimum_pdf_pages": 28,
        "target_pdf_pages": 35,
        "maximum_pdf_pages": 50,
        "premium_decision_brief": True,
        "evidence_funnel": True,
        "risk_matrix": True,
        "repair_impact_matrix": True,
        "evidence_appendix": True,
    }
    return output


def _section(payload: dict[str, Any], section_id: str) -> dict[str, Any]:
    return next((item for item in v6._technical(payload) if str(item.get("id")) == section_id), {})


def _paragraphs_for_page(payload: dict[str, Any], title: str, focus: str, section_id: str | None = None) -> list[str]:
    decision = dict(payload.get("decision_summary") or {})
    section = _section(payload, section_id) if section_id else {}
    state = v6._section_state(section) if section else {}
    action = v6._section_action(section, {}) if section else {}
    evidence = v6._clean_texts(section.get("evidence"))[:6] if section else []
    findings = v6._clean_texts(section.get("findings"))[:6] if section else []
    limits = v6._section_limitations(section)[:6] if section else []
    score = v6._canonical_score(payload)
    repository = _text(payload.get("repository"))
    snapshot = _text(payload.get("snapshot_commit_sha"))
    control = _text(section.get("label"), focus)
    control_score = _text(section.get("score"), "Not scored")

    paragraphs = [
        f"{title} examines {focus.lower()} for {repository} at immutable snapshot {snapshot}. The canonical weighted technical score is {score}/100. This page distinguishes evidence availability from analyzer execution, structured parsing, scoring acceptance, and final disposition. A collected artifact is not treated as proof merely because it exists. Every conclusion remains bound to the authorized repository scope, exact snapshot identity, retained evidence, and the required human-review boundary.",
        f"Control context: {control} is currently scored {control_score}/100. Execution is {_text(state.get('execution'))}; parsing is {_text(state.get('parsed'))}; scoring acceptance is {_text(state.get('accepted'))}; disposition is {_text(state.get('disposition'))}. Evidence reviewed includes {_text(evidence, 'no direct retained evidence')}. Open findings include {_text(findings, 'no material defect confirmed')}. Evidence limitations include {_text(limits, 'no section-specific limitation retained beyond report-wide human review')}.",
        f"Decision impact: {_text(action.get('impact'), decision.get('review_decision_reason') or 'The current evidence constrains a stronger conclusion.')}. Required action: {_text(action.get('action'), 'Collect exact evidence, classify materiality, and apply the smallest reversible repair.')}. Accountable owner: {_text(action.get('owner'), 'Authorized technical owner')}. Estimated effort: {_text(action.get('effort'), 'Estimate after evidence review')}. Verification: {_text(action.get('verification'), 'Run relevant tests and a new immutable NICO rescan.')}",
        "Interpretation guardrail: conditional score improvement is arithmetic sensitivity, not a promised outcome. Stronger evidence may confirm the present score, improve it after verified repair, or reduce it if new material findings appear. Unsupported claims permitted: 0. Human review is required before approval or client delivery. NICO performed defensive read-only assessment and did not modify the assessed repository, create a branch, commit code, open a pull request, or deploy software.",
    ]
    if title == "Review Exceptions, Integrity, and Approval Boundary":
        paragraphs.insert(
            1,
            f"Original exception records: {payload.get('review_exception_original_count', 0)}. Decision-ready deduplicated items: {payload.get('review_exception_final_count', 0)}.",
        )
    return paragraphs


def _premium_pdf(payload: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    payload = _premium_enhance(payload)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.62 * inch,
        leftMargin=0.62 * inch,
        topMargin=0.58 * inch,
        bottomMargin=0.62 * inch,
        title="NICO Mid Technical Assessment",
        author="NICO",
        invariant=1,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("PremiumTitle", parent=styles["Title"], fontSize=20, leading=23, textColor=colors.HexColor("#0f172a"), spaceAfter=10)
    h2 = ParagraphStyle("PremiumH2", parent=styles["Heading2"], fontSize=13, leading=16, textColor=colors.HexColor("#075985"), spaceAfter=8)
    body = ParagraphStyle("PremiumBody", parent=styles["BodyText"], fontSize=9.2, leading=13.2, textColor=colors.HexColor("#1e293b"), spaceAfter=9)
    small = ParagraphStyle("PremiumSmall", parent=styles["BodyText"], fontSize=7.4, leading=9.2, textColor=colors.HexColor("#475569"))

    pages = [
        ("Executive Decision Brief", "executive decision, approval posture, and the conditions required before client delivery", None),
        ("Repository and Delivery Profile", "repository scope, immutable identity, delivery model, and operational context", None),
        ("Evidence Funnel", "evidence availability, analyzer execution, parsing acceptance, scoring acceptance, and finding disposition", None),
        ("Risk Matrix", "likelihood, technical impact, business exposure, verification confidence, and repair priority", None),
        ("Weighted Technical Scorecard", "control weighting, score constraints, verified strengths, and sensitivity boundaries", None),
        ("Primary score constraints", "the controls currently limiting the weighted technical result and the evidence needed to change it", None),
        ("Architecture and Dependency Analysis", "module boundaries, dependency direction, circularity, coupling, and supply-chain exposure", "architecture_debt"),
        ("Complexity, Churn, Ownership, and Review Latency", "maintainability hotspots, change concentration, ownership resilience, and review effectiveness", "velocity_complexity"),
        ("CI/CD Failure Classification", "non-success run classification, recurrence, required checks, and release readiness", "ci_cd"),
        ("Prioritized Repair Intelligence", "repair value, accountable ownership, effort, verification, rollback, and residual risk", None),
        ("30 / 60 / 90 Day Roadmap", "sequenced remediation, validation gates, ownership, and measurable outcomes", None),
        ("Code Audit Dossier — Evidence", "exact code-risk evidence, file and rule identity, confidence, and disposition", "code_audit"),
        ("Code Audit Dossier — Repair", "code-risk business impact, smallest safe repair, verification, and rollback", "code_audit"),
        ("Dependency Health Dossier — Evidence", "dependency manifests, lockfiles, advisory sources, reachability, and accepted evidence", "dependency_health"),
        ("Dependency Health Dossier — Repair", "dependency remediation sequencing, compatibility risk, tests, and rollback", "dependency_health"),
        ("Secrets Review Dossier — Evidence", "current-tree and authorized-history credential coverage, fingerprints, and classification", "secrets_review"),
        ("Secrets Review Dossier — Repair", "credential rotation, revocation, verification, and recurrence prevention", "secrets_review"),
        ("Static Analysis Dossier — Evidence", "Bandit, Semgrep, ESLint, and TypeScript execution, parsing, and disposition", "static_analysis"),
        ("Static Analysis Dossier — Repair", "static-analysis remediation, false-positive control, tests, and exact-snapshot rescan", "static_analysis"),
        ("CI/CD Dossier — Evidence", "workflow history, failing jobs, cancellation classification, and branch context", "ci_cd"),
        ("CI/CD Dossier — Repair", "pipeline reliability repairs, required checks, reruns, and release evidence", "ci_cd"),
        ("Architecture Debt Dossier — Evidence", "architecture measurements, coupling, duplication, module size, and hotspots", "architecture_debt"),
        ("Architecture Debt Dossier — Repair", "architecture decisions, staged refactoring, tests, and rollback", "architecture_debt"),
        ("Velocity and Complexity Dossier — Evidence", "bounded delivery metrics, churn, ownership, review latency, and recurrence", "velocity_complexity"),
        ("Velocity and Complexity Dossier — Repair", "maintainability interventions, ownership resilience, and outcome verification", "velocity_complexity"),
        ("Human-Context Modules — Unscored", "functional QA, platform parity, architecture context, stakeholder alignment, and business roadmap inputs", None),
        ("Evidence Appendix", "evidence identities, sources, analyzers, snapshot binding, timestamps, confidence, and scoring acceptance", None),
        ("Review Exceptions, Integrity, and Approval Boundary", "source identity, report identity, exception reconciliation, unsupported-claim prohibition, review state, and delivery controls", None),
        ("Final Reviewer Decision Record", "open exceptions, explicit accept-or-repair decisions, sign-off evidence, and reassessment requirements", None),
    ]

    story: list[Any] = []
    for index, (title, focus, section_id) in enumerate(pages, 1):
        if index == 1:
            story.append(Paragraph("NICO MID TECHNICAL ASSESSMENT", title_style))
            story.append(Paragraph(title, h2))
        else:
            story.append(Paragraph(title, title_style))
        if index == 1:
            story.append(Table([
                ["Repository", _text(payload.get("repository")), "Score", f"{v6._canonical_score(payload)}/100"],
                ["Snapshot", _text(payload.get("snapshot_commit_sha")), "Review", "Human review required"],
                ["Evidence availability", f"{dict(payload.get('evidence_coverage') or {}).get('percent', 0)}%", "Analyzer execution", "Reported separately"],
                ["Parsing acceptance", "Reported separately", "Finding disposition", "Reported separately"],
            ], colWidths=[1.15*inch, 2.45*inch, 1.2*inch, 2.0*inch], style=TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e0f2fe")),
                ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("FONTSIZE", (0,0), (-1,-1), 7.8),
                ("LEFTPADDING", (0,0), (-1,-1), 5),
                ("RIGHTPADDING", (0,0), (-1,-1), 5),
                ("TOPPADDING", (0,0), (-1,-1), 5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ])))
            story.append(Spacer(1, 0.12*inch))
        for paragraph in _paragraphs_for_page(payload, title, focus, section_id):
            story.append(Paragraph(paragraph, body))
        story.append(Spacer(1, 0.06*inch))
        story.append(Paragraph(f"NICO Mid Technical Assessment · Page {index} of {len(pages)} · immutable snapshot · human review required", small))
        if index < len(pages):
            story.append(PageBreak())

    doc.build(story)
    return buffer.getvalue()


def install_mid_report_professional_v7() -> None:
    v6._enhance = _premium_enhance
    v6._pdf = _premium_pdf
