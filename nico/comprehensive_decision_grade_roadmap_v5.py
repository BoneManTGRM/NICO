from __future__ import annotations

from typing import Any

from nico import comprehensive_native_providers as providers
from nico.comprehensive_decision_grade_model_v5 import _score_band

def _work_package(
    title: str,
    *,
    objective: str,
    owner: str,
    effort: str,
    dependencies: list[str],
    acceptance: list[str],
    expected_impact: str,
) -> dict[str, Any]:
    return {
        "title": title,
        "objective": objective,
        "owner_role": owner,
        "effort": effort,
        "dependencies": dependencies,
        "acceptance_criteria": acceptance,
        "expected_impact": expected_impact,
    }


def build_roadmap(assessment: dict[str, Any]) -> list[dict[str, Any]]:
    sections = {str(item.get("id")): item for item in assessment.get("sections") or [] if isinstance(item, dict)}
    findings = assessment.get("findings_register") if isinstance(assessment.get("findings_register"), list) else []
    high_findings = sum(1 for item in findings if isinstance(item, dict) and item.get("priority") in {"P0", "P1"})
    scanner_packages = _work_package(
        "Restore complete scanner and evidence reliability",
        objective="Eliminate worker resource failures, complete required analyzers, and retain exact finding locations without secret leakage.",
        owner="Product Quality Engineer",
        effort="2-4 weeks",
        dependencies=["Stable worker process/thread capacity", "Exact-SHA scanner environment", "Protected secret redaction"],
        acceptance=["Bandit, Semgrep, Gitleaks, and TruffleHog complete twice against one exact SHA", "Every candidate has category, tool, severity, and safe location", "No raw secret appears in logs or artifacts"],
        expected_impact="Raises evidence assurance for security and static-analysis controls; removes category ambiguity.",
    )
    ci_package = _work_package(
        "Classify and reduce CI/CD non-success history",
        objective="Separate defects, cancellations, superseded runs, and infrastructure failures; remove recurring failure classes.",
        owner="Platform Engineer",
        effort="1-3 weeks",
        dependencies=["Workflow run metadata", "Deployment incident context", "Approved reliability threshold"],
        acceptance=["All retained non-success runs are cause-classified", "Recurring failure classes have owners and fixes", "Two consecutive acceptance windows meet the approved success threshold"],
        expected_impact=f"Improves CI/CD assurance from {sections.get('ci_cd', {}).get('presented_score', 'current')} and makes change-failure evidence decision-usable.",
    )
    architecture_package = _work_package(
        "Decompose the highest-complexity hotspots",
        objective="Reduce concentrated complexity and duplicate logic while preserving behavior through characterization tests.",
        owner="Product Engineering Architect",
        effort="4-8 weeks",
        dependencies=["Named hotspot register", "Characterization tests", "Approved complexity threshold"],
        acceptance=["Top hotspots are split into bounded modules", "Target complexity and nesting thresholds pass", "No regression in production acceptance"],
        expected_impact="Reduces defect probability, review cost, and maintenance risk in the most concentrated code regions.",
    )
    traceability_package = _work_package(
        "Create requirements and acceptance traceability",
        objective="Connect business requirements, technical controls, test evidence, findings, and release acceptance records.",
        owner="Product Engineering Architect",
        effort="3-6 weeks",
        dependencies=["Stakeholder-approved objectives", "Requirements register", "Acceptance owners"],
        acceptance=["Every committed requirement has an owner and acceptance test", "Findings and roadmap work link to requirements", "Human review records the approval decision"],
        expected_impact="Converts technical evidence into auditable business decisions and reduces report caveats.",
    )
    runtime_package = _work_package(
        "Add production telemetry and external pilot evidence",
        objective="Validate user journeys, incident recovery, performance, and report usefulness on an authorized external repository.",
        owner="Product Quality Engineer",
        effort="3-6 weeks",
        dependencies=["Authorized pilot repository", "Production telemetry", "Human reviewer"],
        acceptance=["Express and Comprehensive complete on the pilot repository", "Runtime user journeys pass", "Backup/restore and restart recovery evidence is retained", "Reviewer approves or rejects the immutable package"],
        expected_impact="Moves the product from self-assessment proof to externally demonstrated commercial readiness.",
    )
    return [
        {
            "window": "0-30 days",
            "objective": "Close evidence-integrity and release-reliability gaps before expanding client use.",
            "work_packages": [scanner_packages, ci_package],
            "priority_finding_count": high_findings,
        },
        {
            "window": "31-90 days",
            "objective": "Reduce concentrated technical debt and make requirements traceable to acceptance evidence.",
            "work_packages": [architecture_package, traceability_package],
            "priority_finding_count": high_findings,
        },
        {
            "window": "91-180 days",
            "objective": "Prove the complete operating model through telemetry, recovery evidence, and authorized external pilots.",
            "work_packages": [runtime_package],
            "priority_finding_count": high_findings,
        },
    ]


def roadmap_provider(context: dict[str, Any]) -> dict[str, Any]:
    scoring = providers._prior(context, "evidence_reconciliation_and_scoring")
    assessment = scoring.get("assessment") if isinstance(scoring.get("assessment"), dict) else {}
    roadmap = build_roadmap(assessment)
    return providers._result(
        context,
        summary="A decision-grade six-month roadmap was sequenced into owned work packages with effort ranges, dependencies, acceptance criteria, and expected impact.",
        roadmap=roadmap,
        evidence={
            "roadmap_window_count": len(roadmap),
            "work_package_count": sum(len(item["work_packages"]) for item in roadmap),
            "priority_controls": [item.get("label") for item in sorted(assessment.get("sections") or [], key=lambda section: int(section.get("presented_score") or 0))[:5] if isinstance(item, dict)],
        },
        unavailable_data_notes=["Calendar dates, named individuals, labor rates, and budget remain subject to stakeholder approval."],
    )


def resourcing_provider(context: dict[str, Any]) -> dict[str, Any]:
    roadmap = providers._prior(context, "six_month_roadmap").get("roadmap") or []
    plan = [
        {
            "role": "Product Engineering Architect",
            "sequence": 1,
            "focus": "Architecture hotspot reduction, scoring governance, requirements traceability, and final technical disposition.",
            "estimated_load": "0.5-1.0 FTE during architecture and governance windows",
        },
        {
            "role": "Senior Product Engineer",
            "sequence": 2,
            "focus": "Dependency, static-analysis, backend, frontend, and remediation implementation.",
            "estimated_load": "1.0 FTE during remediation windows",
        },
        {
            "role": "Platform Engineer",
            "sequence": 3,
            "focus": "CI/CD reliability, worker resources, deployment telemetry, backup/restore, and operational controls.",
            "estimated_load": "0.5-1.0 FTE during reliability and activation windows",
        },
        {
            "role": "Product Quality Engineer",
            "sequence": 4,
            "focus": "Scanner evidence, functional QA, accessibility, external pilot acceptance, and report truth verification.",
            "estimated_load": "0.5-1.0 FTE across all acceptance windows",
        },
    ]
    return providers._result(
        context,
        summary="A role-based delivery plan was generated with responsibilities and indicative capacity, without presenting unverified market rates as committed cost.",
        staffing_plan=plan,
        evidence={
            "roadmap_windows_available": len(roadmap),
            "recommended_role_count": len(plan),
            "commercial_cost_status": "requires stakeholder-approved rates and budget",
        },
        unavailable_data_notes=["Named people, contract structure, geographic mix, labor rates, and budget ceilings require client approval before cost finalization."],
    )


def executive_briefing_provider(context: dict[str, Any]) -> dict[str, Any]:
    scoring = providers._prior(context, "evidence_reconciliation_and_scoring")
    assessment = scoring.get("assessment") if isinstance(scoring.get("assessment"), dict) else {}
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    roadmap = providers._prior(context, "six_month_roadmap").get("roadmap") or []
    staffing = providers._prior(context, "staffing_sequencing_and_cost").get("staffing_plan") or []
    findings = assessment.get("findings_register") if isinstance(assessment.get("findings_register"), list) else []
    top = [item for item in findings if isinstance(item, dict)][:5]
    briefing = {
        "maturity_level": maturity.get("level") or "Pending",
        "technical_score": maturity.get("presented_score", maturity.get("score")),
        "technical_band": maturity.get("score_band_label") or _score_band(maturity.get("presented_score", maturity.get("score")))["score_band_label"],
        "roadmap_windows": len(roadmap),
        "recommended_roles": len(staffing),
        "top_risks": [item.get("title") for item in top],
        "decision": "Proceed with controlled use and human review; prioritize evidence reliability, CI cause classification, and named architecture hotspots before broad client delivery.",
    }
    return providers._result(
        context,
        summary="Technical score, assurance limits, top risks, roadmap work packages, staffing, and decision boundaries were condensed into an executive briefing.",
        executive_briefing=briefing,
        evidence=briefing,
    )

__all__ = ["build_roadmap", "roadmap_provider", "resourcing_provider", "executive_briefing_provider"]
