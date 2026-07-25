from __future__ import annotations

import hashlib
import json
import re

from pydantic import Field

from nico.decision_grade_findings_v1 import Finding, RoadmapWorkPackage, rank_executive_findings, value
from nico.decision_grade_types_v1 import (
    AssessmentIdentity,
    Assumption,
    DecisionPostures,
    DeliveryStatus,
    EvidenceRecord,
    EvidenceStatus,
    HumanApproval,
    RenderValidation,
    ScannerExecutionRecord,
    ScoreControl,
    StrictModel,
    ValidationSeverity,
    VERSION,
)


class DecisionGradeAssessment(StrictModel):
    schema_version: str = VERSION
    identity: AssessmentIdentity
    technical_score: float | None = Field(default=None, ge=0, le=100)
    evidence_adjusted_score: float | None = Field(default=None, ge=0, le=100)
    score_controls: list[ScoreControl] = Field(default_factory=list)
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    executive_risk_ids: list[str] = Field(default_factory=list, max_length=7)
    roadmap: list[RoadmapWorkPackage] = Field(default_factory=list)
    scanners: list[ScannerExecutionRecord] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    decision_postures: DecisionPostures | None = None
    scope_boundaries: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    render_validation: RenderValidation = Field(default_factory=RenderValidation)
    human_approval: HumanApproval = Field(default_factory=HumanApproval)
    report_artifact_digest: str | None = None


class ValidationIssue(StrictModel):
    code: str
    severity: ValidationSeverity
    path: str
    message: str


class ReadinessResult(StrictModel):
    schema_version: str = VERSION
    delivery_status: DeliveryStatus
    client_ready: bool
    issues: list[ValidationIssue]
    executive_risk_ids: list[str]
    fingerprint: str


def issue(code: str, path: str, message: str, severity: ValidationSeverity = ValidationSeverity.ERROR) -> ValidationIssue:
    return ValidationIssue(code=code, severity=severity, path=path, message=message)


def unsupported_benchmark(finding: Finding) -> bool:
    text = " ".join(filter(None, (finding.benchmark_claim, finding.business_impact, finding.technical_interpretation)))
    return bool(re.search(r"\b(industry average|quartile|percentile|top\s+\d+%|benchmark(?:ed)?)\b", text, re.I)) and not finding.benchmark_source


def validate_report_readiness(package: DecisionGradeAssessment) -> ReadinessResult:
    issues: list[ValidationIssue] = []
    evidence_ids = {item.evidence_id for item in package.evidence_records}
    finding_ids = {item.finding_id for item in package.findings}
    roadmap_ids = {item.work_package_id for item in package.roadmap}
    assumption_ids = {item.assumption_id for item in package.assumptions}
    ranked_ids = [item.finding_id for item in rank_executive_findings(package.findings)]

    if len(finding_ids) != len(package.findings):
        issues.append(issue("duplicate_finding_id", "findings", "Finding IDs must be unique."))
    if package.executive_risk_ids and package.executive_risk_ids != ranked_ids[: len(package.executive_risk_ids)]:
        issues.append(issue("executive_risk_order", "executive_risk_ids", "Executive risks are not in deterministic priority order."))
    if any(item not in finding_ids for item in package.executive_risk_ids):
        issues.append(issue("unknown_executive_risk", "executive_risk_ids", "Executive risk references an unknown finding."))

    for index, evidence in enumerate(package.evidence_records):
        if evidence.commit_sha.casefold() != package.identity.commit_sha.casefold() and evidence.source_kind != "external":
            issues.append(issue("commit_sha_mismatch", f"evidence_records.{index}.commit_sha", "Direct and derived evidence must match the immutable commit."))

    acceptance_ids: set[str] = set()
    for index, finding in enumerate(package.findings):
        path = f"findings.{index}"
        if set(finding.evidence_ids) - evidence_ids:
            issues.append(issue("unknown_evidence_reference", f"{path}.evidence_ids", "Finding references unknown evidence."))
        for criterion in finding.acceptance_criteria:
            if criterion.criterion_id in acceptance_ids:
                issues.append(issue("duplicate_acceptance_criterion_id", f"{path}.acceptance_criteria", "Acceptance criterion IDs must be unique."))
            acceptance_ids.add(criterion.criterion_id)
        if value(finding.priority) in {"P0", "P1"} and value(finding.status) == "open":
            required = {
                "evidence": finding.evidence_ids,
                "business_impact": finding.business_impact,
                "recommended_action": finding.recommended_action,
                "owner": finding.owner_role,
                "effort": finding.effort,
                "acceptance_criteria": finding.acceptance_criteria,
                "roadmap_mapping": finding.roadmap_work_package_ids,
                "backlog_mapping": finding.backlog_item_ids,
                "residual_risk": finding.residual_risk,
            }
            for label, retained in required.items():
                if not retained:
                    issues.append(issue(f"p1_missing_{label}", path, f"Open {finding.priority} finding is missing {label.replace('_', ' ')}."))
        if set(finding.roadmap_work_package_ids) - roadmap_ids:
            issues.append(issue("unknown_roadmap_reference", f"{path}.roadmap_work_package_ids", "Finding references an unknown roadmap package."))
        if finding.cost_of_inaction and set(finding.cost_of_inaction.assumption_ids) - assumption_ids:
            issues.append(issue("unknown_cost_assumption", f"{path}.cost_of_inaction", "Cost estimate references an unknown assumption."))
        if unsupported_benchmark(finding):
            issues.append(issue("unsupported_benchmark", path, "Benchmark language requires a retained comparison source."))

    for index, work in enumerate(package.roadmap):
        if set(work.related_finding_ids) - finding_ids:
            issues.append(issue("unknown_finding_reference", f"roadmap.{index}", "Work package references an unknown finding."))
        if set(work.acceptance_criteria_ids) - acceptance_ids:
            issues.append(issue("unknown_acceptance_reference", f"roadmap.{index}", "Work package references an unknown acceptance criterion."))

    if package.score_controls:
        contribution = round(sum(item.contribution for item in package.score_controls if not item.excluded), 4)
        if package.technical_score is None or abs(contribution - package.technical_score) > 0.05:
            issues.append(issue("score_arithmetic_mismatch", "technical_score", f"Technical score does not reconcile to {contribution}."))
    if package.technical_score is not None and package.evidence_adjusted_score is not None and package.evidence_adjusted_score > package.technical_score + 0.05:
        issues.append(issue("evidence_adjusted_exceeds_technical", "evidence_adjusted_score", "Evidence-adjusted score cannot exceed technical score without a documented method."))

    failed = [item.scanner_name for item in package.scanners if item.required and value(item.status) in {EvidenceStatus.FAILED.value, EvidenceStatus.TIMED_OUT.value, EvidenceStatus.PERMISSION_BLOCKED.value} and not item.limitation_accepted]
    if failed:
        issues.append(issue("required_scanner_incomplete", "scanners", f"Required scanners are incomplete: {', '.join(sorted(failed))}."))

    if not package.scope_boundaries:
        issues.append(issue("scope_boundaries_missing", "scope_boundaries", "Scope boundaries and unassessed risks must be stated."))
    render = package.render_validation
    for code, path, passed in (
        ("pdf_not_rendered", "pdf_rendered", render.pdf_rendered),
        ("markdown_not_rendered", "markdown_rendered", render.markdown_rendered),
        ("json_not_rendered", "json_rendered", render.json_rendered),
        ("backlog_export_not_rendered", "backlog_export_rendered", render.backlog_export_rendered),
    ):
        if not passed:
            issues.append(issue(code, f"render_validation.{path}", "Required artifact validation has not passed."))
    if render.executive_brief_pages != 1:
        issues.append(issue("executive_brief_page_budget", "render_validation.executive_brief_pages", "Executive Decision Brief must render on exactly one page."))
    if render.empty_pages or render.clipped_content_detected or render.broken_tables_detected:
        issues.append(issue("pdf_layout_failure", "render_validation", "PDF layout regression detected."))

    approval = package.human_approval
    if approval.required and not approval.approved:
        issues.append(issue("human_approval_required", "human_approval.approved", "Named human approval is required."))
    if approval.approved and not approval.reviewer:
        issues.append(issue("human_reviewer_missing", "human_approval.reviewer", "Approved package requires a named reviewer."))
    if approval.approved and package.report_artifact_digest and approval.approved_artifact_digest != package.report_artifact_digest:
        issues.append(issue("approval_digest_mismatch", "human_approval.approved_artifact_digest", "Approval does not match the exact artifact digest."))

    if package.decision_postures:
        release = package.decision_postures.release
        if release.status.casefold() in {"approved", "green", "ready"} and release.blocking_finding_ids:
            issues.append(issue("release_posture_contradiction", "decision_postures.release", "Release is approved while blockers remain."))

    errors = {item.code for item in issues if value(item.severity) == "error"}
    if errors & {"commit_sha_mismatch", "score_arithmetic_mismatch", "release_posture_contradiction", "unsupported_benchmark", "approval_digest_mismatch"}:
        status = DeliveryStatus.DELIVERY_BLOCKED
    elif errors & {"required_scanner_incomplete", "unknown_evidence_reference"}:
        status = DeliveryStatus.EVIDENCE_INCOMPLETE
    elif "human_approval_required" in errors:
        status = DeliveryStatus.HUMAN_REVIEW_REQUIRED
    elif errors:
        status = DeliveryStatus.INTERNAL_DRAFT
    elif issues:
        status = DeliveryStatus.CONDITIONALLY_DELIVERABLE
    else:
        status = DeliveryStatus.CLIENT_READY

    payload = {"assessment_id": package.identity.assessment_id, "commit_sha": package.identity.commit_sha, "status": status.value, "issues": [item.model_dump(mode="json") for item in issues], "executive_risk_ids": ranked_ids}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ReadinessResult(delivery_status=status, client_ready=status == DeliveryStatus.CLIENT_READY, issues=issues, executive_risk_ids=ranked_ids, fingerprint=fingerprint)
