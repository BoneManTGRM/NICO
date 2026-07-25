from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Iterable

from nico.decision_grade_contract_v1 import (
    DecisionGradeContract,
    EvidenceOrigin,
    EvidenceStatus,
    Finding,
    Priority,
    ReadinessStatus,
    ValidationIssue,
)

VERSION = "nico.decision_grade_consistency.v1"
_MARKER = "__nico_decision_grade_consistency_v1__"
_RESOLVED_STATES = {"closed", "resolved", "remediated", "accepted", "suppressed", "excluded"}
_POSITIVE_RELEASE_STATES = {"approved", "ready", "permitted", "go", "unblocked", "release_approved"}
_POSITIVE_DELIVERY_STATES = {"approved", "ready", "permitted", "client_ready", "deliverable", "delivery_approved"}
_INCOMPLETE_EVIDENCE = {
    EvidenceStatus.PARTIAL,
    EvidenceStatus.FAILED,
    EvidenceStatus.TIMED_OUT,
    EvidenceStatus.STALE,
    EvidenceStatus.CONFLICTED,
    EvidenceStatus.PERMISSION_UNAVAILABLE,
}
_PRIORITY_ORDER = {Priority.P0: 0, Priority.P1: 1, Priority.P2: 2, Priority.P3: 3}
_LEVEL_ORDER = {
    "critical": 0,
    "severe": 1,
    "high": 2,
    "material": 3,
    "medium": 4,
    "moderate": 5,
    "limited": 6,
    "low": 7,
    "minimal": 8,
    "unknown": 9,
}
_CONFIDENCE_ORDER = {"verified": 0, "high": 1, "moderate": 2, "medium": 2, "low": 3, "unknown": 4}


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold().replace("-", "_").replace(" ", "_")


def _issue_key(issue: ValidationIssue) -> tuple[str, tuple[str, ...], str | None]:
    return issue.code, tuple(sorted(issue.related_ids)), issue.path


def _add_issue(
    contract: DecisionGradeContract,
    *,
    code: str,
    severity: str,
    message: str,
    path: str | None = None,
    related_ids: Iterable[str] = (),
) -> None:
    issue = ValidationIssue(
        code=code,
        severity=severity,  # type: ignore[arg-type]
        message=message,
        path=path,
        related_ids=sorted({str(item) for item in related_ids if str(item)}),
    )
    existing = {_issue_key(item) for item in contract.validation_issues}
    if _issue_key(issue) not in existing:
        contract.validation_issues.append(issue)


def _is_resolved(finding: Finding) -> bool:
    return _normalized(finding.current_status) in _RESOLVED_STATES


def _rank_active_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(
        (item for item in findings if not _is_resolved(item)),
        key=lambda item: (
            0 if item.release_blocker else 1,
            _PRIORITY_ORDER[item.priority],
            _LEVEL_ORDER.get(_normalized(item.business_criticality), 9),
            _LEVEL_ORDER.get(_normalized(item.severity), 9),
            _LEVEL_ORDER.get(_normalized(item.likelihood), 9),
            _CONFIDENCE_ORDER.get(_normalized(item.confidence), 9),
            item.finding_id,
        ),
    )


def _normalize_executive_register(contract: DecisionGradeContract) -> None:
    previous = list(contract.executive_risk_register)
    active = _rank_active_findings(contract.findings)
    contract.executive_risk_register = [item.finding_id for item in active[:7]]
    resolved_presented = [
        item.finding_id
        for item in contract.findings
        if _is_resolved(item) and item.finding_id in previous
    ]
    if resolved_presented:
        _add_issue(
            contract,
            code="resolved_finding_removed_from_executive_register",
            severity="warning",
            message="Resolved findings were removed from the active Executive Risk Register.",
            related_ids=resolved_presented,
        )


def _validate_unique_and_referential_integrity(contract: DecisionGradeContract) -> None:
    finding_ids = [item.finding_id for item in contract.findings]
    duplicate_findings = sorted({item for item in finding_ids if finding_ids.count(item) > 1})
    if duplicate_findings:
        _add_issue(
            contract,
            code="duplicate_finding_ids",
            severity="critical",
            message="Stable finding IDs are not unique.",
            related_ids=duplicate_findings,
        )
    evidence_ids = [item.evidence_id for item in contract.evidence_records]
    duplicate_evidence = sorted({item for item in evidence_ids if evidence_ids.count(item) > 1})
    if duplicate_evidence:
        _add_issue(
            contract,
            code="duplicate_evidence_ids",
            severity="critical",
            message="Stable evidence IDs are not unique.",
            related_ids=duplicate_evidence,
        )
    finding_set = set(finding_ids)
    evidence_set = set(evidence_ids)
    package_ids = {item.work_package_id for item in contract.roadmap_work_packages}
    for executive_id in contract.executive_risk_register:
        if executive_id not in finding_set:
            _add_issue(
                contract,
                code="executive_finding_missing",
                severity="critical",
                message="Executive Risk Register references an unknown finding.",
                related_ids=[executive_id],
            )
    for finding in contract.findings:
        missing_evidence = sorted(set(finding.evidence_ids) - evidence_set)
        if missing_evidence:
            _add_issue(
                contract,
                code="finding_evidence_reference_missing",
                severity="critical" if finding.priority in {Priority.P0, Priority.P1} else "error",
                message="Finding references evidence records that do not exist in the canonical contract.",
                related_ids=[finding.finding_id, *missing_evidence],
            )
        missing_packages = sorted(set(finding.roadmap_mappings) - package_ids)
        if missing_packages:
            _add_issue(
                contract,
                code="invalid_roadmap_mapping",
                severity="error",
                message="Finding references an unknown roadmap work package.",
                related_ids=[finding.finding_id, *missing_packages],
            )
        if finding.priority in {Priority.P0, Priority.P1} and not finding.roadmap_mappings:
            _add_issue(
                contract,
                code="priority_roadmap_mapping_missing",
                severity="critical",
                message="P0/P1 finding has no roadmap work-package mapping.",
                related_ids=[finding.finding_id],
            )
        if finding.priority in {Priority.P0, Priority.P1} and not finding.backlog_issue_mapping:
            _add_issue(
                contract,
                code="priority_backlog_mapping_missing",
                severity="critical",
                message="P0/P1 finding has no backlog mapping.",
                related_ids=[finding.finding_id],
            )
        if not finding.recommended_action:
            _add_issue(
                contract,
                code="recommendation_missing",
                severity="critical" if finding.priority in {Priority.P0, Priority.P1} else "error",
                message="Finding has no recommended action.",
                related_ids=[finding.finding_id],
            )
        if not finding.acceptance_criteria:
            _add_issue(
                contract,
                code="acceptance_criteria_missing",
                severity="critical" if finding.priority in {Priority.P0, Priority.P1} else "error",
                message="Finding has no independently verifiable acceptance criterion.",
                related_ids=[finding.finding_id],
            )
        if finding.cost_of_inaction.mode != "qualitative" and not finding.cost_of_inaction.assumptions:
            _add_issue(
                contract,
                code="cost_estimate_assumptions_missing",
                severity="critical",
                message="Quantitative cost-of-inaction estimate has no disclosed assumptions.",
                related_ids=[finding.finding_id],
            )
    for package in contract.roadmap_work_packages:
        unknown = sorted(set(package.related_finding_ids) - finding_set)
        if unknown:
            _add_issue(
                contract,
                code="roadmap_unknown_finding",
                severity="error",
                message="Roadmap work package references unknown findings.",
                related_ids=[package.work_package_id, *unknown],
            )
        if not package.related_finding_ids:
            _add_issue(
                contract,
                code="roadmap_item_without_finding",
                severity="error",
                message="Roadmap work package is not connected to any finding.",
                related_ids=[package.work_package_id],
            )
        if not package.acceptance_criteria:
            _add_issue(
                contract,
                code="roadmap_acceptance_criteria_missing",
                severity="error",
                message="Roadmap work package has no acceptance criteria.",
                related_ids=[package.work_package_id],
            )


def _validate_commit_and_location_integrity(contract: DecisionGradeContract) -> None:
    assessed_sha = contract.identity.assessed_commit_sha.casefold()
    for evidence in contract.evidence_records:
        if evidence.origin != EvidenceOrigin.EXTERNALLY_SUPPLIED and evidence.assessed_commit_sha.casefold() != assessed_sha:
            _add_issue(
                contract,
                code="evidence_commit_mismatch",
                severity="critical",
                message="Direct or derived evidence was collected against a commit other than the immutable assessed commit.",
                path=evidence.file_path,
                related_ids=[evidence.evidence_id],
            )
        path = str(evidence.file_path or "")
        lowered = path.casefold()
        if path.startswith("/") or any(token in lowered for token in ("/tmp/", "\\temp\\", "not retained", "<unknown>")):
            _add_issue(
                contract,
                code="evidence_location_not_durable",
                severity="error" if evidence.collection_status == EvidenceStatus.COMPLETE else "warning",
                message="Evidence uses a temporary, absolute, or unresolved location rather than a durable repository locator.",
                path=path or None,
                related_ids=[evidence.evidence_id],
            )
    evidence_by_id = {item.evidence_id: item for item in contract.evidence_records}
    for finding in contract.findings:
        complete = [
            evidence_by_id[item]
            for item in finding.evidence_ids
            if item in evidence_by_id and evidence_by_id[item].collection_status == EvidenceStatus.COMPLETE
        ]
        if finding.priority in {Priority.P0, Priority.P1} and not complete:
            _add_issue(
                contract,
                code="priority_complete_evidence_missing",
                severity="critical",
                message="P0/P1 finding has no completed canonical evidence record.",
                related_ids=[finding.finding_id, *finding.evidence_ids],
            )


def _validate_scanner_confidence(contract: DecisionGradeContract) -> None:
    incomplete_categories: dict[str, list[str]] = {}
    required_incomplete: list[str] = []
    for scanner in contract.scanner_executions:
        if scanner.status not in _INCOMPLETE_EVIDENCE:
            continue
        if scanner.required:
            required_incomplete.append(scanner.scanner_name)
        for category in scanner.evidence_categories_affected or ["unknown"]:
            incomplete_categories.setdefault(_normalized(category), []).append(scanner.scanner_name)
    for finding in contract.findings:
        affected = incomplete_categories.get(_normalized(finding.category), [])
        if affected and _normalized(finding.confidence) in {"verified", "high"}:
            _add_issue(
                contract,
                code="high_confidence_based_on_incomplete_scanner",
                severity="error",
                message="Finding uses high-confidence language while required evidence for its category is incomplete.",
                related_ids=[finding.finding_id, *affected],
            )
    release_status = _normalized(contract.decision_postures.release.status)
    client_status = _normalized(contract.decision_postures.client_delivery.status)
    blockers = [item.finding_id for item in contract.findings if item.release_blocker and not _is_resolved(item)]
    if blockers and release_status in _POSITIVE_RELEASE_STATES:
        _add_issue(
            contract,
            code="release_approved_with_open_blocker",
            severity="critical",
            message="Release posture is positive while release-blocking findings remain open.",
            related_ids=blockers,
        )
    if required_incomplete and release_status in _POSITIVE_RELEASE_STATES:
        _add_issue(
            contract,
            code="release_approved_with_required_evidence_incomplete",
            severity="critical",
            message="Release posture is positive despite incomplete required scanner evidence.",
            related_ids=required_incomplete,
        )
    if required_incomplete and client_status in _POSITIVE_DELIVERY_STATES:
        _add_issue(
            contract,
            code="client_delivery_approved_with_required_evidence_incomplete",
            severity="critical",
            message="Client Delivery posture is positive despite incomplete mandatory evidence.",
            related_ids=required_incomplete,
        )
    release_posture_blockers = set(contract.decision_postures.release.blocking_finding_ids)
    missing_from_posture = sorted(set(blockers) - release_posture_blockers)
    if missing_from_posture:
        _add_issue(
            contract,
            code="release_posture_blocker_mapping_incomplete",
            severity="error",
            message="Release posture does not identify every open release blocker.",
            related_ids=missing_from_posture,
        )


def _numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _reported_scores(assessment: dict[str, Any]) -> tuple[float | None, float | None, dict[str, Any]]:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    technical = _numeric(assessment.get("technical_score"))
    if technical is None:
        technical = _numeric(maturity.get("technical_score"))
    if technical is None:
        technical = _numeric(maturity.get("score"))
    adjusted = _numeric(assessment.get("canonical_evidence_adjusted_score"))
    if adjusted is None:
        adjusted = _numeric(assessment.get("evidence_adjusted_score"))
    if adjusted is None:
        adjusted = _numeric(maturity.get("evidence_adjusted_score"))
    return technical, adjusted, maturity


def _validate_score_arithmetic(contract: DecisionGradeContract, assessment: dict[str, Any]) -> dict[str, Any]:
    rows = [item for item in assessment.get("scoring_weights") or [] if isinstance(item, dict)]
    technical, adjusted, maturity = _reported_scores(assessment)
    summary: dict[str, Any] = {
        "scored_control_count": 0,
        "active_weight": 0.0,
        "calculated_technical_score": None,
        "reported_technical_score": technical,
        "reported_evidence_adjusted_score": adjusted,
        "contribution_mismatch_count": 0,
    }
    included: list[tuple[dict[str, Any], float, float]] = []
    for row in rows:
        if row.get("included") is not True:
            continue
        score = _numeric(row.get("technical_score"))
        weight = _numeric(row.get("weight"))
        if weight is None:
            percent = _numeric(row.get("weight_percent"))
            weight = percent / 100 if percent is not None else None
        if score is None or weight is None or weight <= 0:
            _add_issue(
                contract,
                code="scored_control_arithmetic_input_missing",
                severity="error",
                message="Included score control is missing a numeric score or positive weight.",
                related_ids=[str(row.get("section_id") or row.get("control") or "unknown-control")],
            )
            continue
        expected = round(score * weight, 2)
        contribution = _numeric(row.get("weighted_contribution"))
        if contribution is None or abs(contribution - expected) > 0.05:
            summary["contribution_mismatch_count"] += 1
            _add_issue(
                contract,
                code="weighted_contribution_mismatch",
                severity="critical",
                message=f"Weighted score contribution does not reconcile; expected {expected:.2f}.",
                related_ids=[str(row.get("section_id") or row.get("control") or "unknown-control")],
            )
        included.append((row, score, weight))
    if included:
        weighted_sum = sum(score * weight for _, score, weight in included)
        active_weight = sum(weight for _, _, weight in included)
        calculated = round(weighted_sum / active_weight) if active_weight > 0 else None
        summary.update(
            {
                "scored_control_count": len(included),
                "active_weight": round(active_weight, 6),
                "calculated_technical_score": calculated,
            }
        )
        if technical is None or calculated is None or abs(technical - calculated) > 0.5:
            _add_issue(
                contract,
                code="technical_score_arithmetic_mismatch",
                severity="critical",
                message=f"Reported Technical Maturity score does not reconcile to weighted controls; calculated {calculated}.",
            )
    elif technical is not None:
        _add_issue(
            contract,
            code="technical_score_without_scored_controls",
            severity="error",
            message="A Technical Maturity score is reported without any included scored controls.",
        )
    maturity_technical = _numeric(maturity.get("technical_score"))
    maturity_adjusted = _numeric(maturity.get("evidence_adjusted_score"))
    if (
        technical is not None
        and adjusted is not None
        and technical != adjusted
        and maturity_technical is not None
        and maturity_adjusted is not None
        and technical == maturity_adjusted
        and adjusted == maturity_technical
    ):
        _add_issue(
            contract,
            code="technical_and_evidence_scores_swapped",
            severity="critical",
            message="Technical Maturity and Evidence-Adjusted scores appear to be swapped between canonical fields.",
        )
    if technical is not None and adjusted is not None and adjusted > technical:
        _add_issue(
            contract,
            code="evidence_adjusted_exceeds_technical",
            severity="critical",
            message="Evidence-Adjusted score cannot exceed the Technical Maturity score.",
        )
    return summary


def _validate_owner_consistency(contract: DecisionGradeContract) -> None:
    package_by_id = {item.work_package_id: item for item in contract.roadmap_work_packages}
    for finding in contract.findings:
        for package_id in finding.roadmap_mappings:
            package = package_by_id.get(package_id)
            if package is None:
                continue
            finding_owner = _normalized(finding.owner_role)
            package_owner = _normalized(package.owner_role)
            supporting = {_normalized(item) for item in package.supporting_roles}
            if finding_owner and package_owner and finding_owner != package_owner and finding_owner not in supporting:
                _add_issue(
                    contract,
                    code="owner_assignment_conflict",
                    severity="warning",
                    message="Finding owner differs from the mapped work-package owner and is not recorded as a supporting role.",
                    related_ids=[finding.finding_id, package_id],
                )


def _derive_readiness(contract: DecisionGradeContract) -> ReadinessStatus:
    if any(item.severity == "critical" for item in contract.validation_issues):
        return ReadinessStatus.DELIVERY_BLOCKED
    if any(item.code == "required_scanner_evidence_incomplete" for item in contract.validation_issues):
        return ReadinessStatus.EVIDENCE_INCOMPLETE
    if any(item.required and item.status in _INCOMPLETE_EVIDENCE for item in contract.scanner_executions):
        return ReadinessStatus.EVIDENCE_INCOMPLETE
    if any(item.severity == "error" for item in contract.validation_issues):
        return ReadinessStatus.HUMAN_REVIEW_REQUIRED
    return contract.readiness_status


def validate_contract_consistency(
    contract: DecisionGradeContract,
    assessment: dict[str, Any] | None = None,
) -> tuple[DecisionGradeContract, dict[str, Any]]:
    output = contract.model_copy(deep=True)
    source = assessment or {}
    _normalize_executive_register(output)
    _validate_unique_and_referential_integrity(output)
    _validate_commit_and_location_integrity(output)
    _validate_scanner_confidence(output)
    score_summary = _validate_score_arithmetic(output, source)
    _validate_owner_consistency(output)
    output.readiness_status = _derive_readiness(output)
    errors = [item for item in output.validation_issues if item.severity in {"error", "critical"}]
    warnings = [item for item in output.validation_issues if item.severity == "warning"]
    summary = {
        "schema_version": VERSION,
        "status": "blocked" if output.readiness_status == ReadinessStatus.DELIVERY_BLOCKED else "complete",
        "readiness_status": output.readiness_status.value,
        "validation_error_count": len(errors),
        "validation_warning_count": len(warnings),
        "critical_issue_codes": sorted({item.code for item in output.validation_issues if item.severity == "critical"}),
        "error_issue_codes": sorted({item.code for item in errors}),
        "executive_risk_count": len(output.executive_risk_register),
        "executive_risk_limit_met": len(output.executive_risk_register) <= 7,
        "resolved_findings_excluded_from_executive_register": all(
            not _is_resolved(item)
            for item in output.findings
            if item.finding_id in output.executive_risk_register
        ),
        "score_arithmetic": score_summary,
        "client_ready_promoted_automatically": False,
    }
    return output, summary


def wrap_contract_builder(delegate: Callable[..., DecisionGradeContract]) -> Callable[..., DecisionGradeContract]:
    if getattr(delegate, _MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> DecisionGradeContract:
        contract = delegate(*args, **kwargs)
        assessment = kwargs.get("assessment") if isinstance(kwargs.get("assessment"), dict) else {}
        validated, summary = validate_contract_consistency(contract, assessment)
        if isinstance(assessment, dict):
            assessment["decision_grade_consistency"] = deepcopy(summary)
        return validated

    setattr(wrapped, _MARKER, True)
    return wrapped


def install_decision_grade_consistency_engine(report_module: Any) -> dict[str, Any]:
    current = report_module.build_decision_grade_contract
    wrapped = wrap_contract_builder(current)
    report_module.build_decision_grade_contract = wrapped
    return {
        "status": "installed" if wrapped is not current else "already_installed",
        "version": VERSION,
        "bound": report_module.build_decision_grade_contract is wrapped,
        "score_arithmetic_reconciled": True,
        "evidence_commit_consistency_enforced": True,
        "posture_contradictions_detected": True,
        "roadmap_and_owner_consistency_checked": True,
        "resolved_findings_excluded_from_executive_register": True,
        "client_ready_promoted_automatically": False,
    }


__all__ = [
    "VERSION",
    "validate_contract_consistency",
    "wrap_contract_builder",
    "install_decision_grade_consistency_engine",
]
