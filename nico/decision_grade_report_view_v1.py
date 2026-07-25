from __future__ import annotations

from collections import Counter
from typing import Any

from nico.decision_grade_contract_v1 import (
    CostOfInaction,
    DecisionGradeContract,
    EvidenceStatus,
    Finding,
    Priority,
    RoadmapWorkPackage,
)

VERSION = "nico.decision_grade_report_view.v1"


_SCANNER_ALIASES: tuple[tuple[str, str], ...] = (
    ("osv-scanner", "osv-scanner"),
    ("osv scanner", "osv-scanner"),
    ("osv dependency", "osv-scanner"),
    ("dependency_audit", "dependency_audit"),
    ("dependency audit", "dependency_audit"),
    ("pip-audit", "pip-audit"),
    ("pip audit", "pip-audit"),
    ("npm-audit", "npm-audit"),
    ("npm audit", "npm-audit"),
    ("trufflehog", "trufflehog"),
    ("gitleaks", "gitleaks"),
    ("semgrep", "semgrep"),
    ("bandit", "bandit"),
    ("eslint", "eslint"),
    ("typescript", "typescript"),
)


def _contract(value: DecisionGradeContract | dict[str, Any]) -> DecisionGradeContract:
    return value if isinstance(value, DecisionGradeContract) else DecisionGradeContract.model_validate(value)


def _cost_text(value: CostOfInaction) -> str:
    if value.mode == "qualitative":
        return (
            f"{value.qualitative_exposure or 'Unrated'} qualitative exposure over {value.timeframe_days} days. "
            f"{value.rationale}"
        )
    amount_parts: list[str] = []
    for label, amount in (("low", value.amount_low), ("base", value.amount_base), ("high", value.amount_high)):
        if amount is not None:
            amount_parts.append(f"{label} {value.currency} {amount:,.2f}")
    hours = ""
    if value.engineering_hours_low is not None or value.engineering_hours_high is not None:
        hours = (
            f" Engineering exposure: {value.engineering_hours_low if value.engineering_hours_low is not None else '?'}"
            f"–{value.engineering_hours_high if value.engineering_hours_high is not None else '?'} hours."
        )
    amount_text = ", ".join(amount_parts) or "No monetary total calculated"
    return f"{amount_text} over {value.timeframe_days} days.{hours} {value.rationale}"


def _residual_text(finding: Finding) -> str:
    residual = finding.residual_risk
    return (
        f"Remaining likelihood: {residual.remaining_likelihood}; remaining impact: {residual.remaining_impact} "
        f"The fix does not eliminate: {residual.does_not_eliminate}"
    )


def _criterion_text(finding: Finding) -> list[str]:
    return [
        f"{item.description} [method: {item.validation_method}; target commit: {item.target_commit_sha}]"
        for item in finding.acceptance_criteria
    ]


def _finding_view(finding: Finding) -> dict[str, Any]:
    return {
        "id": finding.finding_id,
        "finding_id": finding.finding_id,
        "source_finding_id": finding.source_finding_id,
        "fingerprint": finding.fingerprint,
        "priority": finding.priority.value,
        "category": finding.category,
        "title": finding.title,
        "status": finding.current_status,
        "severity": finding.severity,
        "likelihood": finding.likelihood,
        "business_criticality": finding.business_criticality,
        "confidence": finding.confidence,
        "location": "; ".join(finding.evidence_locations) or "No durable source location retained",
        "evidence_ids": finding.evidence_ids,
        "evidence": finding.factual_statement,
        "fact": finding.factual_statement,
        "interpretation": finding.technical_interpretation,
        "impact": finding.business_impact,
        "business_impact": finding.business_impact,
        "affected_decision_areas": finding.affected_decision_areas,
        "recommendation": finding.recommended_action,
        "owner_role": finding.owner_role,
        "effort": finding.effort,
        "expected_impact": finding.expected_impact,
        "acceptance_criteria": _criterion_text(finding),
        "cost_of_inaction": _cost_text(finding.cost_of_inaction),
        "cost_of_inaction_mode": finding.cost_of_inaction.mode,
        "cost_of_inaction_assumptions": finding.cost_of_inaction.assumptions,
        "residual_risk": _residual_text(finding),
        "residual_risk_monitoring": finding.residual_risk.required_monitoring,
        "roadmap_mappings": finding.roadmap_mappings,
        "backlog_issue_mapping": finding.backlog_issue_mapping,
        "release_blocker": finding.release_blocker,
    }


def _roadmap_view(package: RoadmapWorkPackage) -> dict[str, Any]:
    return {
        "work_package_id": package.work_package_id,
        "title": package.title,
        "window": package.time_window,
        "time_window": package.time_window,
        "related_finding_ids": package.related_finding_ids,
        "objective": package.objective,
        "ordered_implementation_steps": package.ordered_implementation_steps,
        "dependencies": package.dependencies,
        "owner_role": package.owner_role,
        "supporting_roles": package.supporting_roles,
        "effort": package.effort_range,
        "effort_range": package.effort_range,
        "classification": package.classification,
        "expected_technical_impact": package.expected_technical_impact,
        "expected_business_impact": package.expected_business_impact,
        "expected_impact": f"{package.expected_technical_impact} {package.expected_business_impact}",
        "acceptance_criteria": [item.description for item in package.acceptance_criteria],
        "residual_risk": package.residual_risk.does_not_eliminate,
        "sequencing_rationale": package.sequencing_rationale,
    }


def _roadmap_windows(contract: DecisionGradeContract) -> list[dict[str, Any]]:
    order = ("0-30 days", "31-90 days", "91-180 days")
    packages = [_roadmap_view(item) for item in contract.roadmap_work_packages]
    windows: list[dict[str, Any]] = []
    for window in order:
        selected = [item for item in packages if item["time_window"] == window]
        if not selected:
            continue
        windows.append(
            {
                "window": window,
                "objective": selected[0]["sequencing_rationale"],
                "work_packages": selected,
            }
        )
    return windows


def _scanner_name_from_finding(finding: Finding) -> str:
    text = " ".join(
        (
            finding.title,
            finding.factual_statement,
            finding.technical_interpretation,
            finding.recommended_action,
        )
    ).casefold()
    for token, canonical in _SCANNER_ALIASES:
        if token in text:
            return canonical
    return "unidentified-scanner"


def _finding_scanner_status(finding: Finding) -> str | None:
    text = " ".join(
        (
            finding.title,
            finding.factual_statement,
            finding.technical_interpretation,
        )
    ).casefold()
    if "timed out" in text or "timeout" in text:
        return EvidenceStatus.TIMED_OUT.value
    if any(token in text for token in ("unavailable", "failed", "did not execute", "could not run")):
        return EvidenceStatus.FAILED.value
    if any(
        token in text
        for token in (
            "incomplete",
            "did not produce a complete result",
            "did not complete",
            "partial result",
            "review-limited because the analyzer",
        )
    ):
        return EvidenceStatus.PARTIAL.value
    return None


def _finding_derived_scanner_limitations(contract: DecisionGradeContract) -> list[dict[str, Any]]:
    relevant_categories = {"evidence", "dependency", "static", "secret", "code"}
    limitations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for finding in contract.findings:
        if finding.category.casefold() not in relevant_categories:
            continue
        status = _finding_scanner_status(finding)
        if status is None:
            continue
        scanner = _scanner_name_from_finding(finding)
        key = (scanner, status, finding.finding_id)
        if key in seen:
            continue
        seen.add(key)
        limitations.append(
            {
                "scanner": scanner,
                "status": status,
                "required": finding.priority in {Priority.P0, Priority.P1} or finding.release_blocker,
                "affected_categories": [finding.category],
                "affected_controls": list(finding.affected_decision_areas),
                "confidence_impact": finding.business_impact,
                "remediation": finding.recommended_action,
                "source": "retained_finding",
                "finding_id": finding.finding_id,
            }
        )
    return limitations


def _evidence_health(contract: DecisionGradeContract) -> dict[str, Any]:
    scanner_counts = Counter(item.status.value for item in contract.scanner_executions)
    evidence_counts = Counter(item.collection_status.value for item in contract.evidence_records)
    incomplete = {
        EvidenceStatus.PARTIAL.value,
        EvidenceStatus.FAILED.value,
        EvidenceStatus.TIMED_OUT.value,
        EvidenceStatus.STALE.value,
        EvidenceStatus.CONFLICTED.value,
        EvidenceStatus.PERMISSION_UNAVAILABLE.value,
    }
    structured_limitations = [
        {
            "scanner": item.scanner_name,
            "status": item.status.value,
            "required": item.required,
            "affected_categories": item.evidence_categories_affected,
            "affected_controls": item.score_controls_affected,
            "confidence_impact": item.confidence_impact,
            "remediation": item.remediation_guidance,
            "source": "scanner_execution_record",
        }
        for item in contract.scanner_executions
        if item.status.value in incomplete
    ]
    finding_limitations = _finding_derived_scanner_limitations(contract)
    structured_keys = {(item["scanner"], item["status"]) for item in structured_limitations}
    finding_only = [
        item
        for item in finding_limitations
        if (item["scanner"], item["status"]) not in structured_keys
    ]
    affected_scanners = [*structured_limitations, *finding_only]
    required_failures = sorted(
        {
            item["scanner"]
            for item in affected_scanners
            if item.get("required") is True
        }
    )
    if required_failures:
        confidence_effect = (
            "Required scanner limitations are retained; the Evidence-Adjusted score and delivery posture must remain constrained."
        )
    elif affected_scanners:
        confidence_effect = (
            "Scanner limitations are retained in canonical findings, although none is classified as a required scanner failure."
        )
    else:
        confidence_effect = "No scanner failure or limitation was retained in structured execution records or canonical findings."
    return {
        "scanner_status_counts": dict(sorted(scanner_counts.items())),
        "evidence_status_counts": dict(sorted(evidence_counts.items())),
        "structured_execution_records_present": bool(contract.scanner_executions),
        "completed_scanners": [item.scanner_name for item in contract.scanner_executions if item.status == EvidenceStatus.COMPLETE],
        "incomplete_scanners": affected_scanners,
        "finding_derived_scanner_limitations": finding_only,
        "required_scanner_failures": required_failures,
        "confidence_effect": confidence_effect,
    }


def _scope_boundaries(contract: DecisionGradeContract) -> list[dict[str, str]]:
    common = [
        ("Live production behavior", "Not verified unless production telemetry was explicitly supplied and retained."),
        ("Penetration testing", "Repository analysis is not a penetration test and does not prove exploitability or absence of vulnerabilities."),
        ("Cloud account configuration", "External cloud resources and account-level controls are outside scope unless explicitly authorized and collected."),
        ("Privacy and regulatory compliance", "Technical evidence does not constitute legal or regulatory certification."),
        ("Production load and disaster recovery", "Load, failover, backup, and recovery behavior require direct runtime evidence."),
        ("Stakeholder and organizational process", "Human intent, team dynamics, requirements quality, and governance require stakeholder evidence."),
    ]
    if contract.identity.assessment_type.value in {"express", "mid"}:
        common.append(("Unassessed package controls", "Controls excluded by the purchased assessment scope must not be interpreted as healthy."))
    return [{"area": area, "boundary": boundary} for area, boundary in common]


def build_report_view(contract: DecisionGradeContract | dict[str, Any]) -> dict[str, Any]:
    normalized = _contract(contract)
    findings = [_finding_view(item) for item in normalized.findings]
    findings_by_id = {item["finding_id"]: item for item in findings}
    executive = [findings_by_id[item] for item in normalized.executive_risk_register if item in findings_by_id][:7]
    return {
        "schema_version": VERSION,
        "assessment_type": normalized.identity.assessment_type.value,
        "delivery_status": normalized.readiness_status.value,
        "executive_risk_register_limit": 7,
        "executive_risk_register": executive,
        "findings_register": findings,
        "roadmap": _roadmap_windows(normalized),
        "evidence_health": _evidence_health(normalized),
        "assumption_register": [item.model_dump(mode="json") for item in normalized.assumptions],
        "scope_boundaries": _scope_boundaries(normalized),
        "decision_postures": normalized.decision_postures.model_dump(mode="json"),
        "validation_issues": [item.model_dump(mode="json") for item in normalized.validation_issues],
        "how_to_use": [
            "Read the Executive Decision Brief.",
            "Disposition every P1 against its acceptance criteria.",
            "Convert the 0–30 day roadmap into the immediate backlog.",
            "Execute work in the stated dependency order.",
            "Re-run NICO after P1 closure.",
            "Compare score, risk, evidence, and complexity deltas.",
            "DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED until exact-package approval is recorded.",
        ],
    }


def apply_report_view(assessment: dict[str, Any], contract: DecisionGradeContract | dict[str, Any]) -> dict[str, Any]:
    view = build_report_view(contract)
    output = dict(assessment)
    output["decision_grade_report_view"] = view
    output["executive_risk_register"] = view["executive_risk_register"]
    output["decision_grade_findings_register"] = view["findings_register"]
    output["decision_grade_roadmap"] = view["roadmap"]
    output["evidence_health_summary"] = view["evidence_health"]
    output["assumption_register"] = view["assumption_register"]
    output["scope_boundaries"] = view["scope_boundaries"]
    output["decision_postures"] = view["decision_postures"]
    output["how_to_use_report"] = view["how_to_use"]
    output["delivery_status"] = view["delivery_status"]
    return output


__all__ = ["VERSION", "build_report_view", "apply_report_view"]
