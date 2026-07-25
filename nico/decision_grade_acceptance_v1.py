from __future__ import annotations

import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Iterable, Literal

from nico.decision_grade_contract_v1 import (
    AcceptanceCriterion,
    DecisionGradeContract,
    EvidenceRecord,
    Finding,
    Priority,
    ValidationIssue,
)

VERSION = "nico.decision_grade_acceptance.v1"
_MARKER = "__nico_decision_grade_acceptance_v1__"
_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,64}$")
_VAGUE_PREFIXES = (
    "improve ",
    "add more ",
    "refactor ",
    "make ci ",
    "make the ",
    "review security",
    "review the ",
    "fix architecture",
    "address technical debt",
)


def _text(value: Any, limit: int = 1200) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _path(value: str | None) -> str | None:
    if not value:
        return None
    result = re.sub(r":\d+(?:-\d+)?$", "", value.strip())
    if not result or result.startswith("/") or "/tmp/" in result.casefold():
        return None
    return result


def _issue_key(issue: ValidationIssue) -> tuple[str, tuple[str, ...], str | None]:
    return issue.code, tuple(sorted(issue.related_ids)), issue.path


def _add_issue(
    contract: DecisionGradeContract,
    *,
    code: str,
    severity: Literal["info", "warning", "error", "critical"],
    message: str,
    related_ids: Iterable[str] = (),
    path: str | None = None,
) -> None:
    issue = ValidationIssue(
        code=code,
        severity=severity,
        message=message,
        related_ids=sorted({str(item) for item in related_ids if str(item)}),
        path=path,
    )
    existing = {_issue_key(item) for item in contract.validation_issues}
    if _issue_key(issue) not in existing:
        contract.validation_issues.append(issue)


def _evidence_anchor(
    finding: Finding,
    evidence_by_id: dict[str, EvidenceRecord],
) -> tuple[str | None, str, str]:
    evidence = next((evidence_by_id[item] for item in finding.evidence_ids if item in evidence_by_id), None)
    file_path = _path(evidence.file_path if evidence else None)
    if file_path is None:
        file_path = next((_path(item) for item in finding.evidence_locations if _path(item)), None)
    symbol = _text(evidence.symbol_or_control if evidence else None, 160) or finding.category or finding.finding_id
    source = evidence.evidence_id if evidence else (finding.evidence_ids[0] if finding.evidence_ids else finding.finding_id)
    return file_path, symbol, source


def _criterion_kind(item: AcceptanceCriterion) -> str:
    method = item.validation_method.casefold()
    if item.workflow_name or "workflow" in method or "ci" in method:
        return "workflow"
    if item.test_name or "test" in method:
        return "test"
    return "implementation"


def _is_vague(description: str) -> bool:
    normalized = _text(description, 900).casefold()
    return len(normalized) < 20 or any(normalized.startswith(prefix) for prefix in _VAGUE_PREFIXES)


def _has_anchor(item: AcceptanceCriterion) -> bool:
    return any(
        (
            item.file_path,
            item.symbol_or_control,
            item.test_name,
            item.workflow_name,
            item.configuration_key,
            item.metric,
            item.repository_query,
            item.dependency_identifier,
            item.control_identifier,
        )
    )


def _has_binary_target(item: AcceptanceCriterion) -> bool:
    if item.comparator in {"present", "absent"}:
        return True
    return item.comparator is not None and item.target_value is not None


def _criterion_errors(item: AcceptanceCriterion) -> list[str]:
    errors: list[str] = []
    if _is_vague(item.description):
        errors.append("vague_description")
    if not item.validation_method:
        errors.append("validation_method_missing")
    if not _has_anchor(item):
        errors.append("durable_anchor_missing")
    if not _has_binary_target(item):
        errors.append("binary_target_missing")
    if not _SHA_PATTERN.fullmatch(item.target_commit_sha or ""):
        errors.append("target_commit_invalid")
    if not item.required_evidence:
        errors.append("required_evidence_missing")
    return errors


def _normalize_existing(
    item: AcceptanceCriterion,
    *,
    target_sha: str,
    workflow_name: str,
) -> AcceptanceCriterion:
    output = item.model_copy(deep=True)
    output.target_commit_sha = target_sha
    kind = _criterion_kind(output)
    if kind == "workflow":
        output.workflow_name = output.workflow_name or workflow_name
        output.comparator = output.comparator or "="
        output.target_value = output.target_value if output.target_value is not None else "success"
        output.validation_method = "workflow_verification"
    elif kind == "test":
        output.test_name = output.test_name or output.symbol_or_control or output.control_identifier or "remediation verification test"
        output.comparator = output.comparator or "="
        output.target_value = output.target_value if output.target_value is not None else "pass"
        output.validation_method = "automated_test"
    elif output.comparator is None:
        output.comparator = "="
        output.target_value = output.target_value if output.target_value is not None else "pass"
    output.required_evidence = output.required_evidence or [
        "Validation result for the exact target commit",
        "Binary pass/fail disposition retained against the criterion ID",
    ]
    return output


def _drafted_candidates(
    assessment: dict[str, Any],
    finding: Finding,
    *,
    target_sha: str,
    file_path: str | None,
    symbol: str,
) -> list[AcceptanceCriterion]:
    mapping = assessment.get("drafted_acceptance_criteria")
    if not isinstance(mapping, dict):
        return []
    raw = mapping.get(finding.finding_id) or (mapping.get(finding.source_finding_id) if finding.source_finding_id else None)
    if raw is None:
        return []
    values = raw if isinstance(raw, list) else [raw]
    output: list[AcceptanceCriterion] = []
    for index, value in enumerate(values, start=1):
        if isinstance(value, str):
            payload: dict[str, Any] = {"description": value}
        elif isinstance(value, dict):
            payload = dict(value)
        else:
            continue
        description = _text(payload.get("description") or payload.get("criterion"), 900)
        if not description:
            continue
        try:
            output.append(
                AcceptanceCriterion(
                    criterion_id=f"AC-{finding.finding_id}-DRAFT-{index:02d}",
                    description=description,
                    validation_method=_text(payload.get("validation_method") or "exact_sha_rerun", 100),
                    target_commit_sha=target_sha,
                    file_path=_path(payload.get("file_path")) or file_path,
                    symbol_or_control=_text(payload.get("symbol_or_control") or symbol, 160),
                    test_name=_text(payload.get("test_name"), 180) or None,
                    workflow_name=_text(payload.get("workflow_name"), 180) or None,
                    configuration_key=_text(payload.get("configuration_key"), 180) or None,
                    command=_text(payload.get("command"), 300) or None,
                    metric=_text(payload.get("metric"), 180) or None,
                    comparator=payload.get("comparator"),
                    target_value=payload.get("target_value"),
                    repository_query=_text(payload.get("repository_query"), 300) or None,
                    dependency_identifier=_text(payload.get("dependency_identifier"), 180) or None,
                    control_identifier=_text(payload.get("control_identifier") or finding.category, 180),
                    required_evidence=[_text(item, 300) for item in payload.get("required_evidence") or ["Exact-target-commit verification result"]],
                )
            )
        except Exception:
            continue
    return output


def _criterion(
    finding: Finding,
    *,
    kind: str,
    target_sha: str,
    file_path: str | None,
    symbol: str,
    evidence_id: str,
    workflow_name: str,
) -> AcceptanceCriterion:
    category = finding.category.casefold()
    base = {
        "criterion_id": f"AC-{finding.finding_id}-{kind.upper()}",
        "target_commit_sha": target_sha,
        "file_path": file_path,
        "symbol_or_control": symbol,
        "control_identifier": category,
        "state": "pending",
    }
    if kind == "workflow":
        return AcceptanceCriterion(
            **base,
            description=f"The {workflow_name} workflow completes successfully on the validation commit for {finding.finding_id}.",
            validation_method="workflow_verification",
            workflow_name=workflow_name,
            comparator="=",
            target_value="success",
            required_evidence=["Workflow run URL", "Workflow conclusion", "Validation commit SHA"],
        )
    if kind == "test":
        test_name = f"{finding.finding_id} remediation verification"
        if category == "evidence":
            test_name = f"{finding.finding_id} scanner repeatability verification"
        return AcceptanceCriterion(
            **base,
            description=f"The named verification test for {finding.finding_id} passes on the validation commit.",
            validation_method="automated_test",
            test_name=test_name,
            comparator="=",
            target_value="pass",
            required_evidence=["Named test result", "Test command or workflow reference", "Validation commit SHA"],
        )
    if category == "architecture":
        return AcceptanceCriterion(
            **base,
            description=f"{file_path or symbol} has cyclomatic complexity less than or equal to 30 at the durable control anchor.",
            validation_method="metric_comparison",
            metric="cyclomatic_complexity",
            comparator="<=",
            target_value=30,
            required_evidence=["Complexity scanner result", evidence_id, "Validation commit SHA"],
        )
    if category == "dependency":
        return AcceptanceCriterion(
            **base,
            description="The release-blocking dependency condition is absent from the locked dependency graph on the validation commit.",
            validation_method="locked_graph_query",
            dependency_identifier=symbol,
            repository_query=f"locked_dependency_graph::{finding.finding_id}",
            comparator="absent",
            target_value="release_blocking_condition",
            required_evidence=["Locked dependency graph", "Dependency scanner result", evidence_id],
        )
    if category == "secret":
        return AcceptanceCriterion(
            **base,
            description="No confirmed live credential matching the retained finding fingerprint is present in the authorized repository history.",
            validation_method="secret_history_query",
            repository_query=f"secret_history::{finding.fingerprint}",
            comparator="absent",
            target_value="confirmed_live_credential",
            required_evidence=["Sanitized secret-scanner result", "Authorized history coverage", evidence_id],
        )
    if category == "ci_cd":
        return AcceptanceCriterion(
            **base,
            description=f"The release validation control for {finding.finding_id} records zero unresolved blocking failures.",
            validation_method="workflow_control_query",
            workflow_name=workflow_name,
            metric="unresolved_blocking_failures",
            comparator="=",
            target_value=0,
            required_evidence=["Classified workflow run set", "Validation commit SHA", evidence_id],
        )
    if category in {"static", "code"}:
        return AcceptanceCriterion(
            **base,
            description="The confirmed analyzer condition is absent at the durable file or control anchor on the validation commit.",
            validation_method="analyzer_fingerprint_query",
            repository_query=f"analyzer_fingerprint::{finding.fingerprint}",
            comparator="absent",
            target_value="confirmed_unresolved_condition",
            required_evidence=["Analyzer result", evidence_id, "Validation commit SHA"],
        )
    if category == "evidence":
        return AcceptanceCriterion(
            **base,
            description="The required scanner completes without timeout, permission failure, conflict, or partial-evidence status on the validation commit.",
            validation_method="scanner_execution_verification",
            metric="scanner_status",
            comparator="=",
            target_value="complete",
            required_evidence=["Scanner execution record", evidence_id, "Validation commit SHA"],
        )
    return AcceptanceCriterion(
        **base,
        description=f"The affected {category or 'technical'} control records a binary pass on the validation commit.",
        validation_method="exact_sha_control_verification",
        comparator="=",
        target_value="pass",
        required_evidence=["Control verification result", evidence_id, "Validation commit SHA"],
    )


def _dedupe(criteria: list[AcceptanceCriterion]) -> list[AcceptanceCriterion]:
    output: list[AcceptanceCriterion] = []
    seen: set[tuple[str, str, str]] = set()
    for item in criteria:
        key = (_criterion_kind(item), _text(item.description, 900).casefold(), _text(item.file_path or item.symbol_or_control, 240).casefold())
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _finding_criteria(
    contract: DecisionGradeContract,
    finding: Finding,
    assessment: dict[str, Any],
    *,
    target_sha: str,
    workflow_name: str,
    evidence_by_id: dict[str, EvidenceRecord],
) -> tuple[list[AcceptanceCriterion], int, int]:
    file_path, symbol, evidence_id = _evidence_anchor(finding, evidence_by_id)
    raw = [*finding.acceptance_criteria, *_drafted_candidates(assessment, finding, target_sha=target_sha, file_path=file_path, symbol=symbol)]
    accepted: list[AcceptanceCriterion] = []
    rejected = 0
    for item in raw:
        normalized = _normalize_existing(item, target_sha=target_sha, workflow_name=workflow_name)
        if _criterion_errors(normalized):
            rejected += 1
            _add_issue(
                contract,
                code="acceptance_criterion_replaced",
                severity="warning",
                message="A vague or unverifiable source/drafted acceptance criterion was replaced by a deterministic criterion.",
                related_ids=[finding.finding_id, item.criterion_id],
            )
            continue
        accepted.append(normalized)
    required_kinds = ["implementation"]
    if finding.priority in {Priority.P0, Priority.P1}:
        required_kinds = ["implementation", "test", "workflow"]
    existing_kinds = {_criterion_kind(item) for item in accepted}
    generated = 0
    for kind in required_kinds:
        if kind in existing_kinds:
            continue
        accepted.append(
            _criterion(
                finding,
                kind=kind,
                target_sha=target_sha,
                file_path=file_path,
                symbol=symbol,
                evidence_id=evidence_id,
                workflow_name=workflow_name,
            )
        )
        existing_kinds.add(kind)
        generated += 1
    accepted = _dedupe(accepted)
    for item in accepted:
        errors = _criterion_errors(item)
        if errors:
            _add_issue(
                contract,
                code="acceptance_criterion_unverifiable",
                severity="critical" if finding.priority in {Priority.P0, Priority.P1} else "error",
                message="Acceptance criterion failed deterministic verification: " + ", ".join(errors),
                related_ids=[finding.finding_id, item.criterion_id],
            )
    if finding.priority in {Priority.P0, Priority.P1} and len(accepted) < 3:
        _add_issue(
            contract,
            code="priority_acceptance_coverage_incomplete",
            severity="critical",
            message="P0/P1 finding lacks implementation, test, and workflow acceptance coverage.",
            related_ids=[finding.finding_id],
        )
    return accepted, generated, rejected


def _roadmap_criteria(
    contract: DecisionGradeContract,
    *,
    target_sha: str,
    workflow_name: str,
) -> int:
    generated = 0
    findings_by_id = {item.finding_id: item for item in contract.findings}
    for package in contract.roadmap_work_packages:
        normalized = [
            _normalize_existing(item, target_sha=target_sha, workflow_name=workflow_name)
            for item in package.acceptance_criteria
        ]
        normalized = [item for item in normalized if not _criterion_errors(item)]
        related_priority = any(
            findings_by_id[item].priority in {Priority.P0, Priority.P1}
            for item in package.related_finding_ids
            if item in findings_by_id
        )
        kinds = {_criterion_kind(item) for item in normalized}
        if related_priority and "workflow" not in kinds:
            normalized.append(
                AcceptanceCriterion(
                    criterion_id=f"AC-{package.work_package_id}-WORKFLOW",
                    description=f"The {workflow_name} workflow passes for work package {package.work_package_id} on the validation commit.",
                    validation_method="workflow_verification",
                    target_commit_sha=target_sha,
                    workflow_name=workflow_name,
                    control_identifier=package.work_package_id,
                    comparator="=",
                    target_value="success",
                    required_evidence=["Workflow run URL", "Workflow conclusion", "Validation commit SHA"],
                )
            )
            generated += 1
        package.acceptance_criteria = _dedupe(normalized)
        if not package.acceptance_criteria:
            _add_issue(
                contract,
                code="roadmap_acceptance_criteria_unverifiable",
                severity="error",
                message="Roadmap work package has no valid binary acceptance criterion.",
                related_ids=[package.work_package_id],
            )
    return generated


def apply_acceptance_criteria_engine(
    contract: DecisionGradeContract,
    assessment: dict[str, Any] | None = None,
) -> tuple[DecisionGradeContract, dict[str, Any]]:
    output = contract.model_copy(deep=True)
    source = assessment or {}
    candidate_sha = _text(source.get("acceptance_validation_commit_sha"), 80)
    target_sha = candidate_sha if _SHA_PATTERN.fullmatch(candidate_sha) else output.identity.assessed_commit_sha
    workflow_name = _text(source.get("acceptance_workflow_name") or "repository-validation", 180)
    evidence_by_id = {item.evidence_id: item for item in output.evidence_records}
    generated = 0
    rejected = 0
    for finding in output.findings:
        criteria, generated_count, rejected_count = _finding_criteria(
            output,
            finding,
            source,
            target_sha=target_sha,
            workflow_name=workflow_name,
            evidence_by_id=evidence_by_id,
        )
        finding.acceptance_criteria = criteria
        generated += generated_count
        rejected += rejected_count
    roadmap_generated = _roadmap_criteria(output, target_sha=target_sha, workflow_name=workflow_name)
    total = sum(len(item.acceptance_criteria) for item in output.findings)
    priority_complete = all(
        len(item.acceptance_criteria) >= 3
        and {"implementation", "test", "workflow"}.issubset({_criterion_kind(value) for value in item.acceptance_criteria})
        for item in output.findings
        if item.priority in {Priority.P0, Priority.P1}
    )
    summary = {
        "schema_version": VERSION,
        "status": "complete" if priority_complete else "blocked",
        "target_commit_sha": target_sha,
        "workflow_name": workflow_name,
        "finding_criterion_count": total,
        "deterministic_criteria_generated": generated,
        "roadmap_criteria_generated": roadmap_generated,
        "source_or_drafted_criteria_rejected": rejected,
        "p0_p1_implementation_test_workflow_coverage": priority_complete,
        "language_model_drafts_accepted_only_after_validation": True,
        "binary_results_required": True,
    }
    return output, summary


def wrap_contract_builder(delegate: Callable[..., DecisionGradeContract]) -> Callable[..., DecisionGradeContract]:
    if getattr(delegate, _MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> DecisionGradeContract:
        contract = delegate(*args, **kwargs)
        assessment = kwargs.get("assessment") if isinstance(kwargs.get("assessment"), dict) else {}
        adjusted, summary = apply_acceptance_criteria_engine(contract, assessment)
        if isinstance(assessment, dict):
            assessment["decision_grade_acceptance"] = deepcopy(summary)
        return adjusted

    setattr(wrapped, _MARKER, True)
    return wrapped


def install_decision_grade_acceptance_engine(report_module: Any) -> dict[str, Any]:
    current = report_module.build_decision_grade_contract
    wrapped = wrap_contract_builder(current)
    report_module.build_decision_grade_contract = wrapped
    return {
        "status": "installed" if wrapped is not current else "already_installed",
        "version": VERSION,
        "bound": report_module.build_decision_grade_contract is wrapped,
        "deterministic_templates_enabled": True,
        "contextual_drafts_validated": True,
        "p0_p1_multi_criterion_coverage_required": True,
        "binary_results_required": True,
    }


__all__ = [
    "VERSION",
    "apply_acceptance_criteria_engine",
    "wrap_contract_builder",
    "install_decision_grade_acceptance_engine",
]
