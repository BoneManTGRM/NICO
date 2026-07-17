from __future__ import annotations

import io
from copy import deepcopy
from typing import Any

from nico import mid_report_professional_v6 as v6
from nico.mid_report_premium_contract_v8 import mid_report_contract, reconcile_mid_scores


VERSION = "mid-assessment-draft-v8-premium"


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
    output["presentation_detail_level"] = 8
    output["report_depth_contract"] = {
        **dict(output.get("report_depth_contract") or {}),
        "minimum_pdf_pages": 35,
        "target_pdf_pages": 42,
        "maximum_pdf_pages": 50,
        "premium_decision_brief": True,
        "transparent_scoring": True,
        "evidence_funnel": True,
        "risk_matrix": True,
        "repair_impact_matrix": True,
        "architecture_map": True,
        "dependency_topology": True,
        "ownership_analysis": True,
        "ci_reliability": True,
        "test_maturity": True,
        "evidence_appendix": True,
    }
    locale = str(output.get("report_language") or output.get("language") or output.get("locale") or "en")
    mid_report_contract(output, locale)
    reconcile_mid_scores(output)
    return output


def _section(payload: dict[str, Any], section_id: str) -> dict[str, Any]:
    return next((item for item in v6._technical(payload) if str(item.get("id")) == section_id), {})


def _score_context(payload: dict[str, Any], section_id: str | None) -> str:
    if not section_id:
        return "No single control owns this page; the page synthesizes cross-control evidence."
    records = dict(payload.get("mid_score_transparency") or {}).get("records", [])
    record = next((item for item in records if str(item.get("section_id")) == section_id), {})
    if not record:
        return "No transparent score record was retained for this control."
    deductions = "; ".join(f"-{item.get('points')} {item.get('reason')}" for item in record.get("deductions", [])) or "no deductions"
    return (
        f"Transparent score: source {record.get('source_score', 0)}/100; presented {record.get('presented_score', 0)}/100; "
        f"status {str(record.get('status') or 'unknown').upper()}; confidence {record.get('confidence') or 'unknown'}; deductions {deductions}."
    )


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

    return [
        f"{title} examines {focus.lower()} for {repository} at immutable snapshot {snapshot}. The canonical weighted technical score is {score}/100. This page distinguishes evidence availability from analyzer execution, structured parsing, scoring acceptance, and final disposition. A collected artifact is not treated as proof merely because it exists. Every conclusion remains bound to the authorized repository scope, exact snapshot identity, retained evidence, and the required human-review boundary.",
        f"Control context: {control} is currently scored {control_score}/100. Execution is {_text(state.get('execution'))}; parsing is {_text(state.get('parsed'))}; scoring acceptance is {_text(state.get('accepted'))}; disposition is {_text(state.get('disposition'))}. Evidence reviewed includes {_text(evidence, 'no direct retained evidence')}. Open findings include {_text(findings, 'no material defect confirmed')}. Evidence limitations include {_text(limits, 'no section-specific limitation retained beyond report-wide human review')}.",
        _score_context(payload, section_id),
        f"Decision impact: {_text(action.get('impact'), decision.get('review_decision_reason') or 'The current evidence constrains a stronger conclusion.')}. Required action: {_text(action.get('action'), 'Collect exact evidence, classify materiality, and apply the smallest reversible repair.')}. Accountable owner: {_text(action.get('owner'), 'Authorized technical owner')}. Estimated effort: {_text(action.get('effort'), 'Estimate after evidence review')}. Verification: {_text(action.get('verification'), 'Run relevant tests and a new immutable NICO rescan.')}",
        "Interpretation guardrail: conditional score improvement is arithmetic sensitivity, not a promised outcome. Stronger evidence may confirm the present score, improve it after verified repair, or reduce it if new material findings appear. Unsupported claims permitted: 0. Human review is required before approval or client delivery. NICO performed defensive read-only assessment and did not modify the assessed repository, create a branch, commit code, open a pull request, or deploy software.",
    ]


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
        title="NICO Mid Technical Diligence Assessment",
        author="NICO",
        invariant=1,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("PremiumTitle", parent=styles["Title"], fontSize=20, leading=23, textColor=colors.HexColor("#0f172a"), spaceAfter=10)
    h2 = ParagraphStyle("PremiumH2", parent=styles["Heading2"], fontSize=13, leading=16, textColor=colors.HexColor("#075985"), spaceAfter=8)
    body = ParagraphStyle("PremiumBody", parent=styles["BodyText"], fontSize=8.8, leading=12.4, textColor=colors.HexColor("#1e293b"), spaceAfter=7)
    small = ParagraphStyle("PremiumSmall", parent=styles["BodyText"], fontSize=7.2, leading=9.0, textColor=colors.HexColor("#475569"))

    pages = [
        ("Executive Decision Brief", "executive decision, approval posture, and the conditions required before client delivery", None, None),
        ("Repository and Delivery Profile", "repository scope, immutable identity, delivery model, and operational context", None, None),
        ("Evidence Funnel", "evidence availability, analyzer execution, parsing acceptance, scoring acceptance, and finding disposition", None, None),
        ("Risk Matrix", "likelihood, technical impact, business exposure, verification confidence, and repair priority", None, None),
        ("Transparent Weighted Technical Scorecard", "control weighting, explicit deductions, score constraints, verified strengths, and sensitivity boundaries", None, None),
        ("Primary Score Constraints", "the controls currently limiting the weighted technical result and the evidence needed to change it", None, None),
        ("Architecture and System Design", "module boundaries, dependency direction, circularity, coupling, service boundaries, and design resilience", "architecture_debt", None),
        ("Architecture Boundary and Trust Map", "runtime boundaries, trust transitions, external systems, privileged paths, and evidence limitations", "architecture_debt", None),
        ("Dependency and Supply-Chain Topology", "dependency manifests, lockfiles, transitive exposure, update constraints, and advisory reachability", "dependency_health", None),
        ("Complexity and Churn Hotspots", "maintainability hotspots, change concentration, high-risk modules, and verification priority", "velocity_complexity", None),
        ("Ownership and Delivery Concentration", "bus factor, review concentration, critical-path ownership, and delivery resilience", "velocity_complexity", None),
        ("CI/CD Reliability and Release Controls", "non-success run classification, recurrence, required checks, release gates, and rollback readiness", "ci_cd", None),
        ("Test Maturity and Quality Gates", "test depth, determinism, integration coverage, regression protection, and quality-gate enforcement", "static_analysis", None),
        ("Repair Impact Matrix", "repair value, accountable ownership, effort, verification, rollback, and residual risk", None, "Prioritized Repair Intelligence"),
        ("30 / 60 / 90 Day Roadmap", "sequenced remediation, validation gates, ownership, dependencies, and measurable outcomes", None, None),
        ("Immediate 0–30 Day Work Plan", "release blockers, exact owners, effort estimates, evidence requirements, and completion definitions", None, None),
        ("Code Audit Dossier — Evidence", "exact code-risk evidence, file and rule identity, confidence, and disposition", "code_audit", None),
        ("Code Audit Dossier — Repair", "code-risk business impact, smallest safe repair, verification, and rollback", "code_audit", None),
        ("Dependency Health Dossier — Evidence", "dependency manifests, lockfiles, advisory sources, reachability, and accepted evidence", "dependency_health", None),
        ("Dependency Health Dossier — Repair", "dependency remediation sequencing, compatibility risk, tests, and rollback", "dependency_health", None),
        ("Secrets Review Dossier — Evidence", "current-tree and authorized-history credential coverage, fingerprints, and classification", "secrets_review", None),
        ("Secrets Review Dossier — Repair", "credential rotation, revocation, verification, and recurrence prevention", "secrets_review", None),
        ("Static Analysis Dossier — Evidence", "Bandit, Semgrep, ESLint, and TypeScript execution, parsing, and disposition", "static_analysis", None),
        ("Static Analysis Dossier — Repair", "static-analysis remediation, false-positive control, tests, and exact-snapshot rescan", "static_analysis", None),
        ("CI/CD Dossier — Evidence", "workflow history, failing jobs, cancellation classification, and branch context", "ci_cd", None),
        ("CI/CD Dossier — Repair", "pipeline reliability repairs, required checks, reruns, and release evidence", "ci_cd", None),
        ("Architecture Debt Dossier — Evidence", "architecture measurements, coupling, duplication, module size, and hotspots", "architecture_debt", None),
        ("Architecture Debt Dossier — Repair", "architecture decisions, staged refactoring, tests, and rollback", "architecture_debt", None),
        ("Velocity and Complexity Dossier — Evidence", "bounded delivery metrics, churn, ownership, review latency, and recurrence", "velocity_complexity", None),
        ("Velocity and Complexity Dossier — Repair", "maintainability interventions, ownership resilience, and outcome verification", "velocity_complexity", None),
        ("Human-Context Modules — Unscored", "functional QA, platform parity, architecture context, stakeholder alignment, and business roadmap inputs", None, None),
        ("Evidence Provenance and Snapshot Integrity", "source identity, immutable commit binding, timestamps, analyzer versions, confidence, and acceptance", None, None),
        ("Evidence Appendix", "evidence identities, sources, analyzers, snapshot binding, timestamps, confidence, and scoring acceptance", None, None),
        ("Review Exceptions", "source identity, report identity, exception reconciliation, unsupported-claim prohibition, review state, and delivery controls", None, "Integrity and Approval Boundary"),
        ("Final Reviewer Decision Record", "open exceptions, explicit accept-or-repair decisions, sign-off evidence, residual risk, and reassessment requirements", None, None),
    ]

    story: list[Any] = []
    for index, (title, focus, section_id, subtitle) in enumerate(pages, 1):
        if index == 1:
            story.append(Paragraph("NICO MID TECHNICAL DILIGENCE ASSESSMENT", title_style))
            story.append(Paragraph(title, h2))
        else:
            story.append(Paragraph(title, title_style))
        if subtitle:
            story.append(Paragraph(subtitle, h2))
        if index == 1:
            score_records = dict(payload.get("mid_score_transparency") or {}).get("records", [])
            presented = [int(item.get("presented_score") or 0) for item in score_records if isinstance(item, dict)]
            adjusted = round(sum(presented) / len(presented)) if presented else 0
            story.append(Table([
                ["Repository", _text(payload.get("repository")), "Canonical score", f"{v6._canonical_score(payload)}/100"],
                ["Snapshot", _text(payload.get("snapshot_commit_sha")), "Evidence-adjusted", f"{adjusted}/100"],
                ["Evidence availability", f"{dict(payload.get('evidence_coverage') or {}).get('percent', 0)}%", "Review", "Human review required"],
                ["Page contract", "35–50 substantive pages", "Delivery", "Blocked pending approval"],
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
        if title == "Review Exceptions":
            story.append(Paragraph(f"Original exception records: {payload.get('review_exception_original_count', 0)}", body))
            story.append(Paragraph(f"Decision-ready deduplicated items: {payload.get('review_exception_final_count', 0)}", body))
        story.append(Spacer(1, 0.06*inch))
        story.append(Paragraph(f"NICO Mid Technical Diligence Assessment · Page {index} of {len(pages)} · immutable snapshot · human review required", small))
        if index < len(pages):
            story.append(PageBreak())

    doc.build(story)
    return buffer.getvalue()


def install_mid_report_professional_v7() -> None:
    v6._enhance = _premium_enhance
    v6._pdf = _premium_pdf
