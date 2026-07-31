from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from fastapi import FastAPI

from nico import client_assessment_truth_v3 as client_truth
from nico import comprehensive_assessment_hardening_v1 as hardening
from nico import comprehensive_native_providers as legacy
from nico import comprehensive_native_providers_v2 as v2
from nico import snapshot_repository_evidence as snapshot_repository
from nico.comprehensive_assessment_hardening_v1 import (
    install_final_publisher_gate,
    install_import_time_hardening,
)
from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY

VERSION = "nico.comprehensive-native-providers.v3"

_PRE_HARDENING_SCAN_FILES = getattr(snapshot_repository, "scan_files", None)
_PRE_HARDENING_SCORE_REPAIR = client_truth._repair_stale_report_contracts


def _strict_review_candidate(item: Mapping[str, Any]) -> bool:
    """Group only explicit dependency or secret review candidates.

    Existing report polish remains authoritative for scanner runtime diagnostics,
    confirmed P2 records, code candidates, and static-analysis candidates. This
    prevents a generic candidate-volume layer from replacing more precise client
    language or hiding a confirmed finding.
    """

    category = str(item.get("category") or "").strip().casefold()
    if category not in {"dependency", "secret"}:
        return False
    if item.get("material") is True:
        return False
    status = str(item.get("status") or "").strip().casefold()
    disposition = str(
        item.get("disposition") or item.get("candidate_classification") or ""
    ).strip().casefold()
    explicit = bool(
        item.get("review_required") is True
        or status in {"review_required", "candidate", "unverified"}
        or "review_required" in disposition
        or disposition.endswith("_candidate")
    )
    if not explicit:
        return False
    title = str(item.get("title") or "").casefold()
    fact = str(item.get("fact") or "").casefold()
    evidence = str(item.get("evidence") or "").casefold()
    runtime_diagnostic = any(
        token in f"{title} {fact} {evidence}"
        for token in (
            "resource limit",
            "failed to create new os thread",
            "did not produce a complete result",
            "configuration failed",
            "configuration_failed",
            "scanner execution boundary",
        )
    )
    return not runtime_diagnostic


def _has_numeric_score_truth(canonical: Mapping[str, Any]) -> bool:
    assessment = canonical.get("assessment")
    if not isinstance(assessment, Mapping):
        return False
    maturity = assessment.get("maturity_signal")
    score_contract = assessment.get("score_contract")
    candidates = [
        assessment.get("technical_score"),
        assessment.get("canonical_evidence_adjusted_score"),
        assessment.get("evidence_adjusted_score"),
    ]
    if isinstance(maturity, Mapping):
        candidates.extend(
            maturity.get(key)
            for key in (
                "score",
                "source_score",
                "presented_score",
                "technical_score",
                "canonical_evidence_adjusted_score",
                "evidence_adjusted_score",
            )
        )
    if isinstance(score_contract, Mapping):
        candidates.extend(
            score_contract.get(key)
            for key in ("technical_score", "evidence_adjusted_score")
        )
    return any(isinstance(value, (int, float)) and not isinstance(value, bool) for value in candidates)


def _hybrid_score_truth_repair(canonical: dict[str, Any]) -> int:
    """Use equality verification when score aliases exist, legacy repair otherwise."""

    if _has_numeric_score_truth(canonical):
        return hardening._repair_stale_report_contracts_hardened(canonical)
    return _PRE_HARDENING_SCORE_REPAIR(canonical)


hardening._is_review_candidate = _strict_review_candidate
HARDENING_STATUS = install_import_time_hardening()
client_truth._repair_stale_report_contracts = _hybrid_score_truth_repair
if callable(_PRE_HARDENING_SCAN_FILES):
    snapshot_repository.scan_files = _PRE_HARDENING_SCAN_FILES
elif not callable(getattr(snapshot_repository, "scan_files", None)):
    snapshot_repository.scan_files = snapshot_repository.analyze_source_signals

_IMMUTABLE_CONTROL_FIELDS = (
    "cache",
    "concurrency",
    "timeout",
    "matrix",
    "artifact_upload",
    "environment_gate",
    "test_command",
    "lint_command",
    "build_command",
    "security_command",
    "deployment_command",
)


def _bounded(value: float | int) -> int:
    return max(0, min(100, int(round(value))))


def _section_map(assessment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or ""): item
        for item in assessment.get("sections") or []
        if isinstance(item, dict) and item.get("id")
    }


def _immutable_ci_score(
    workflow: dict[str, Any],
    commit_sha: str,
) -> tuple[int, list[str], list[str], dict[str, Any]]:
    """Score only workflow configuration bound to the immutable repository commit."""

    workflow_files = int(workflow.get("workflow_file_count") or 0)
    configuration_sha = str(
        workflow.get("workflow_configuration_snapshot_sha") or ""
    ).casefold()
    expected_sha = str(commit_sha or "").casefold()
    exact_configuration = bool(expected_sha and configuration_sha == expected_sha)
    explicit_permissions = workflow.get("explicit_permissions_present") is True
    controls = (
        workflow.get("configuration_controls")
        if isinstance(workflow.get("configuration_controls"), dict)
        else {}
    )
    retained_controls = {
        name: controls.get(name) is True for name in _IMMUTABLE_CONTROL_FIELDS
    }
    control_count = sum(retained_controls.values())

    score = 45
    findings: list[str] = []
    if workflow_files:
        score += 10
    else:
        findings.append("No workflow configuration was retained at the assessed commit.")
    if exact_configuration:
        score += 10
    else:
        findings.append(
            "Workflow configuration was not proven against the exact assessed commit."
        )
    if explicit_permissions:
        score += 10
    else:
        findings.append(
            "Explicit workflow permission boundaries were not proven at the assessed commit."
        )
    score += min(25, control_count * 3)

    historical = {
        "successful_runs": int(workflow.get("successful_runs") or 0),
        "non_success_runs": int(workflow.get("non_success_runs") or 0),
        "jobs_observed": int(workflow.get("jobs_observed") or 0),
        "job_success_rate": workflow.get("job_success_rate"),
        "deployments_observed": int(workflow.get("deployments_observed") or 0),
        "successful_deployments": int(workflow.get("successful_deployments") or 0),
        "runtime_proof_workflows": list(workflow.get("runtime_proof_workflows") or []),
        "score_effect": "none",
        "classification": "mutable_operational_trend",
    }
    evidence = [
        f"Workflow files at assessed commit: {workflow_files}.",
        f"Workflow configuration exact-SHA match: {exact_configuration}.",
        f"Explicit permissions present: {explicit_permissions}.",
        (
            "Immutable workflow controls present: "
            f"{control_count}/{len(_IMMUTABLE_CONTROL_FIELDS)}."
        ),
        (
            "Historical workflow, job, and deployment outcomes are retained "
            "as an unscored operational trend."
        ),
    ]
    contract = {
        "version": "nico.immutable-ci-score.v1",
        "configuration_snapshot_sha": configuration_sha,
        "expected_commit_sha": expected_sha,
        "exact_configuration_match": exact_configuration,
        "immutable_control_count": control_count,
        "immutable_control_population": len(_IMMUTABLE_CONTROL_FIELDS),
        "mutable_operational_history_affects_technical_score": False,
        "score_inputs": {
            "workflow_files_present": bool(workflow_files),
            "exact_configuration_match": exact_configuration,
            "explicit_permissions_present": explicit_permissions,
            "configuration_controls": retained_controls,
        },
        "operational_trend": historical,
    }
    return _bounded(score), evidence, findings, contract


def _immutable_delivery_score(
    architecture_score: int,
    ci_score: int,
    activity: dict[str, Any],
    workflow: dict[str, Any],
) -> tuple[int, list[str], list[str], dict[str, Any]]:
    """Measure sustainable delivery capacity without scoring mutable activity volume."""

    score = _bounded(architecture_score * 0.60 + ci_score * 0.40)
    evidence = [
        f"Architecture and technical-debt score: {architecture_score}/100.",
        f"Immutable CI configuration score: {ci_score}/100.",
        (
            "The delivery-capacity score is 60% architecture maintainability "
            "and 40% immutable workflow automation."
        ),
        (
            "Commit, pull-request, merge, job, and deployment counts are "
            "retained as trend context and have no score effect."
        ),
    ]
    findings: list[str] = []
    if architecture_score < 75:
        findings.append(
            "Concentrated architecture or complexity risk constrains sustainable delivery capacity."
        )
    contract = {
        "version": "nico.immutable-delivery-capacity.v1",
        "architecture_weight": 0.60,
        "immutable_ci_weight": 0.40,
        "mutable_activity_affects_technical_score": False,
        "operational_trend": {
            "commits_returned": int(activity.get("commits_returned") or 0),
            "pull_requests_returned": int(activity.get("pull_requests_returned") or 0),
            "merged_pull_requests": int(activity.get("merged_pull_requests") or 0),
            "jobs_observed": int(workflow.get("jobs_observed") or 0),
            "job_success_rate": workflow.get("job_success_rate"),
            "score_effect": "none",
        },
    }
    return score, evidence, findings, contract


def canonical_scoring_provider(context: dict[str, Any]) -> dict[str, Any]:
    baseline = v2.canonical_scoring_provider(context)
    if baseline.get("status") != "complete":
        return baseline
    assessment = deepcopy(baseline.get("assessment") or {})
    sections = _section_map(assessment)
    repo = legacy._repo(context)
    workflow = (
        repo.get("workflow_evidence")
        if isinstance(repo.get("workflow_evidence"), dict)
        else {}
    )
    activity = (
        repo.get("activity_evidence")
        if isinstance(repo.get("activity_evidence"), dict)
        else {}
    )

    architecture = sections.get("architecture_debt") or {}
    architecture_score = int(
        architecture.get("presented_score") or architecture.get("score") or 0
    )
    ci_score, ci_evidence, ci_findings, ci_contract = _immutable_ci_score(
        workflow,
        str(context.get("commit_sha") or ""),
    )
    (
        velocity_score,
        velocity_evidence,
        velocity_findings,
        velocity_contract,
    ) = _immutable_delivery_score(
        architecture_score,
        ci_score,
        activity,
        workflow,
    )

    ci_section = legacy._section(
        "ci_cd",
        "CI/CD Analysis",
        ci_score,
        (
            "CI/CD technical maturity is scored only from workflow configuration "
            "bound to the exact immutable commit; later operational outcomes are "
            "reported separately."
        ),
        ci_evidence,
        ci_findings,
    )
    ci_section["score_contract"] = ci_contract
    velocity_section = legacy._section(
        "velocity_complexity",
        "Velocity / Complexity",
        velocity_score,
        (
            "Sustainable delivery capacity is derived from immutable architecture "
            "maintainability and workflow automation; mutable activity volume is "
            "unscored context."
        ),
        velocity_evidence,
        velocity_findings,
    )
    velocity_section["score_contract"] = velocity_contract

    updated_sections: list[dict[str, Any]] = []
    for section in assessment.get("sections") or []:
        if not isinstance(section, dict):
            continue
        if section.get("id") == "ci_cd":
            updated_sections.append(ci_section)
        elif section.get("id") == "velocity_complexity":
            updated_sections.append(velocity_section)
        else:
            updated_sections.append(section)
    assessment["sections"] = updated_sections

    scored = [
        int(item.get("presented_score"))
        for item in updated_sections
        if isinstance(item.get("presented_score"), int)
    ]
    technical_score = round(sum(scored) / len(scored)) if scored else 0
    coverage = (
        assessment.get("evidence_coverage")
        if isinstance(assessment.get("evidence_coverage"), dict)
        else {}
    )
    analyzer_coverage = int(coverage.get("percent") or 0)
    evidence_adjusted = min(
        technical_score,
        round(technical_score * 0.85 + analyzer_coverage * 0.15),
    )
    level = (
        "Senior"
        if technical_score >= 82
        else "Mid"
        if technical_score >= 58
        else "Junior"
    )

    assessment["technical_score"] = technical_score
    assessment["canonical_evidence_adjusted_score"] = evidence_adjusted
    assessment["evidence_adjusted_score"] = evidence_adjusted
    assessment["maturity_signal"] = {
        **dict(assessment.get("maturity_signal") or {}),
        "level": level,
        "score": technical_score,
        "source_score": technical_score,
        "presented_score": technical_score,
        "technical_score": technical_score,
        "canonical_evidence_adjusted_score": evidence_adjusted,
        "evidence_adjusted_score": evidence_adjusted,
    }
    score_contract = deepcopy(dict(assessment.get("score_contract") or {}))
    score_contract.update(
        {
            "version": VERSION,
            "same_sha_score_deterministic": True,
            "mutable_operational_history_affects_technical_score": False,
            "mutable_operational_history_affects_evidence_adjusted_score": False,
            "immutable_ci_contract": ci_contract,
            "immutable_delivery_capacity_contract": velocity_contract,
            "target_score_not_used_as_input": True,
            "score_override_allowed": False,
            "technical_score": technical_score,
            "evidence_adjusted_score": evidence_adjusted,
        }
    )
    assessment["score_contract"] = score_contract
    assessment["executive_summary"] = (
        f"Exact-SHA technical evidence for {context['repository']} produced an "
        f"evidence-bound {level} maturity signal ({technical_score}/100) and "
        f"evidence-adjusted score of {evidence_adjusted}/100. Mutable operational "
        "history is disclosed separately and cannot change the score for this "
        "immutable commit."
    )

    result = deepcopy(baseline)
    result["assessment"] = assessment
    evidence = deepcopy(dict(result.get("evidence") or {}))
    evidence.update(
        {
            "maturity_level": level,
            "technical_score": technical_score,
            "evidence_adjusted_score": evidence_adjusted,
            "same_sha_score_deterministic": True,
            "mutable_operational_history_score_effect": "none",
        }
    )
    result["evidence"] = evidence
    result["summary"] = (
        "Canonical scoring completed from immutable code, workflow configuration, "
        "and exact-SHA scanner evidence; mutable operational trends were retained "
        "without affecting technical scores."
    )
    return result


def native_comprehensive_providers() -> dict[str, legacy.Provider]:
    providers = v2.native_comprehensive_providers()
    providers["canonical_scoring"] = canonical_scoring_provider
    return providers


def install_native_comprehensive_providers(
    app: FastAPI,
) -> dict[str, legacy.Provider]:
    existing = getattr(app.state, PROVIDER_STATE_KEY, None)
    providers = dict(existing) if isinstance(existing, dict) else {}
    providers.update(native_comprehensive_providers())
    setattr(app.state, PROVIDER_STATE_KEY, providers)

    final_gate = install_final_publisher_gate()
    hardening_status = {**HARDENING_STATUS, **final_gate}
    app.state.nico_native_comprehensive_provider_status = {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "provider_count": len(providers),
        "providers": sorted(providers),
        "category_specific_scoring_bound": (
            providers.get("canonical_scoring") is canonical_scoring_provider
        ),
        "same_sha_score_deterministic": True,
        "mutable_operational_history_affects_score": False,
        "score_override_allowed": False,
        "source_signal_binding_compatible": (
            hardening_status.get("source_signal_binding_compatible") is True
        ),
        "frozen_operational_evidence_bound": (
            hardening_status.get("frozen_operational_evidence_bound") is True
        ),
        "production_manifest_scope_filter_bound": (
            hardening_status.get("production_manifest_scope_filter_bound") is True
        ),
        "review_candidate_summary_bound": (
            hardening_status.get("review_candidate_summary_bound") is True
        ),
        "report_contract_publication_gate_bound": (
            hardening_status.get("final_report_contract_publication_gate_bound") is True
        ),
        "hardening_status": hardening_status,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return providers


__all__ = [
    "VERSION",
    "HARDENING_STATUS",
    "canonical_scoring_provider",
    "install_native_comprehensive_providers",
    "native_comprehensive_providers",
]
