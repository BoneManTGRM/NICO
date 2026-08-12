from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from nico import comprehensive_native_providers as legacy
from nico.phase3_engagement_intake_v1 import engagement_truth

VERSION = "nico.phase3_evidence_core.v1"


def _text(value: Any, limit: int = 1200) -> str:
    return " ".join(str(value or "").split())[:limit]


def _values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [] if value in (None, "") else [_text(value)]


def _module(context: Mapping[str, Any], module_id: str) -> dict[str, Any]:
    package = context.get("human_evidence") if isinstance(context.get("human_evidence"), Mapping) else {}
    modules = package.get("modules") if isinstance(package.get("modules"), Mapping) else {}
    raw = modules.get(module_id); return dict(raw) if isinstance(raw, Mapping) else {}


def _field(context: Mapping[str, Any], module_id: str, field: str) -> list[str]:
    module = _module(context, module_id); evidence = module.get("evidence") if isinstance(module.get("evidence"), Mapping) else {}
    return _values(evidence.get(field))


def _state(context: Mapping[str, Any], module_id: str) -> str:
    module = _module(context, module_id); status = _text(module.get("status"), 80).casefold()
    if status == "excluded": return "not_applicable"
    if status in {"complete", "partial"}:
        verification = " ".join(_field(context, module_id, "verification_status")).casefold()
        return "retained_verified" if verification in {"verified", "retained_verified", "verified_by_authorized_source"} else "supplied_unverified"
    return "not_supplied"


def _prior(context: Mapping[str, Any], stage_id: str) -> dict[str, Any]: return legacy._prior(dict(context), stage_id)
def _repo(context: Mapping[str, Any]) -> dict[str, Any]: return legacy._repo(dict(context))
def _complexity(context: Mapping[str, Any]) -> dict[str, Any]: return legacy._complexity(dict(context))
def _result(context: Mapping[str, Any], status: str = "complete", **payload: Any) -> dict[str, Any]: return legacy._result(dict(context), status, **payload)


def _missing(kind: str, why: str, cannot: str, resolve: str, effect: str = "scope_limitation") -> dict[str, str]:
    return {"evidence_type": kind, "state": "not_supplied", "why_it_matters": why, "cannot_conclude": cannot, "evidence_to_resolve": resolve, "approval_effect": effect}


def technical_analysis_provider(context: dict[str, Any]) -> dict[str, Any]:
    baseline = legacy.technical_analysis_provider(context)
    if baseline.get("status") != "complete": return baseline
    repo, complexity = _repo(context), _complexity(context)
    activity = repo.get("activity_evidence") if isinstance(repo.get("activity_evidence"), Mapping) else {}
    workflow = repo.get("workflow_evidence") if isinstance(repo.get("workflow_evidence"), Mapping) else {}
    hotspots = [dict(x) for x in complexity.get("hotspots") or [] if isinstance(x, Mapping)][:25]
    evidence = deepcopy(dict(baseline.get("evidence") or {})); duplicate = complexity.get("duplicate_evidence") if isinstance(complexity.get("duplicate_evidence"), Mapping) else {}
    evidence.update({
        "top_hotspots": hotspots[:10], "hotspot_count": len(hotspots), "top_coupled_files": list(complexity.get("top_coupled_files") or [])[:10],
        "duplicate_line_ratio": duplicate.get("duplicate_line_ratio"), "duplicate_block_groups": duplicate.get("duplicate_block_groups"),
        "change_pattern_context": {"commits_observed": activity.get("commits_returned", 0), "pull_requests_observed": activity.get("pull_requests_returned", 0), "workflow_runs_observed": workflow.get("workflow_run_count", 0), "activity_volume_quality_score_effect": "none"},
    })
    baseline["evidence"] = evidence; baseline["summary"] = "Exact-source maintainability, complexity hotspots, coupling, duplication, workflow automation, and bounded change history were synthesized; activity volume remains unscored context."
    return baseline


def functional_qa_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context); architecture = repo.get("architecture_evidence") if isinstance(repo.get("architecture_evidence"), Mapping) else {}; workflows = repo.get("workflow_evidence") if isinstance(repo.get("workflow_evidence"), Mapping) else {}
    cases, observed = _field(context, "functional_qa", "test_cases"), _field(context, "functional_qa", "observed_results"); supplied = bool(cases or observed)
    missing = [] if supplied else [_missing("runtime_functional_qa", "Repository tests do not establish production user journeys.", "Production journey, integration, browser/device, and stakeholder acceptance.", "Approved journey matrix, runtime environment, observed results, and acceptance criteria.")]
    evidence = {"repository_test_inventory_state": "retained_verified", "test_path_count": int(architecture.get("test_path_count") or 0), "test_commands_detected": [x for x in workflows.get("commands_detected") or [] if "test" in str(x).casefold()], "runtime_evidence_state": _state(context, "functional_qa") if supplied else "not_assessed", "supplied_test_cases": cases, "supplied_observed_results": observed, "repository_tests_are_runtime_acceptance": False, "runtime_acceptance_established": False}
    return _result(context, summary="Repository test evidence and supplied QA evidence were reconciled without treating repository tests as runtime acceptance.", functional_qa=evidence, missing_evidence=missing, evidence=evidence, unavailable_data_notes=[x["cannot_conclude"] for x in missing])


def platform_parity_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context); files = repo.get("file_evidence") if isinstance(repo.get("file_evidence"), Mapping) else {}; sampled = [str(x) for x in files.get("sampled_paths") or []]
    matrix = _field(context, "platform_parity", "matrix"); supplied = bool(matrix)
    missing = [] if supplied else [_missing("device_runtime_parity", "Source/config indicators cannot prove runtime or device parity.", "Actual feature, device, permission, or localization parity.", "Supported device/platform matrix with observed runtime results and approved parity criteria.")]
    evidence = {"source_indicator_state": "retained_verified", "ios_paths": [p for p in sampled if any(t in p.casefold() for t in ("ios", ".swift", "xcode"))][:30], "android_paths": [p for p in sampled if any(t in p.casefold() for t in ("android", ".kt", ".gradle"))][:30], "runtime_matrix_state": _state(context, "platform_parity") if supplied else "not_assessed", "supplied_matrix": matrix, "source_indicators_are_device_parity": False, "device_runtime_parity_established": False}
    return _result(context, summary="Repository platform indicators and supplied parity evidence were reconciled without promoting source indicators to runtime/device parity.", platform_parity=evidence, missing_evidence=missing, evidence=evidence, unavailable_data_notes=[x["cannot_conclude"] for x in missing])


def stakeholder_alignment_provider(context: dict[str, Any]) -> dict[str, Any]:
    objectives = _field(context, "stakeholder_context", "objectives") + _field(context, "product_objectives", "objectives")
    constraints = _field(context, "stakeholder_context", "constraints") + _field(context, "release_constraints", "constraints")
    success = _field(context, "product_objectives", "success_measures"); supplied = bool(objectives or constraints or success)
    missing = [] if supplied else [_missing("stakeholder_business_authority", "Technical evidence cannot establish stakeholder intent or business authority.", "Approved priorities, budget/deadline authority, residual-risk ownership, or client acceptance.", "Authorized objectives, constraints, success measures, decision owners, and authority records.")]
    seen, contradictions = {}, []
    for kind, values in (("objective", objectives), ("constraint", constraints)):
        for value in values:
            key = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
            if key in seen and seen[key] != kind: contradictions.append({"statement": value, "types": [seen[key], kind]})
            seen[key] = kind
    evidence = {"engagement": engagement_truth({"identity": {"customer_id": context.get("customer_id"), "project_id": context.get("project_id")}, "human_evidence": context.get("human_evidence") or {}}), "objectives": objectives, "constraints": constraints, "success_measures": success, "contradictions": contradictions, "stakeholder_authority_established": False, "model_inference_is_stakeholder_authority": False}
    return _result(context, summary="Supplied stakeholder/business evidence was organized and checked for conflicts while authority and disputed meaning remain human decisions.", stakeholder_alignment=evidence, missing_evidence=missing, evidence=evidence, unavailable_data_notes=[x["cannot_conclude"] for x in missing])


def _req_id(text: str, index: int) -> str:
    match = re.match(r"\s*([A-Za-z][A-Za-z0-9_.-]{1,48})\s*[:|\-]", text); return match.group(1) if match else f"REQ-{index:03d}"


def requirements_traceability_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context); files = repo.get("file_evidence") if isinstance(repo.get("file_evidence"), Mapping) else {}; sampled = [str(x) for x in files.get("sampled_paths") or []]
    requirements = _field(context, "compliance_requirements", "requirements"); authority = _field(context, "compliance_requirements", "authority_status"); authoritative = any(x.casefold() in {"authoritative", "approved", "contractual"} for x in authority)
    mappings = []
    for i, requirement in enumerate(requirements, 1):
        tokens = [t for t in re.findall(r"[a-z0-9_./-]{4,}", requirement.casefold()) if t not in {"shall", "must", "should", "requirement"}]
        matches = [p for p in sampled if any(t in p.casefold() for t in tokens[:8])][:10]
        mappings.append({"requirement_id": _req_id(requirement, i), "requirement": requirement, "authority_classification": "authoritative" if authoritative else "supplied_unverified", "implementation_evidence": matches, "implementation_mapping_classification": "inferred" if matches else "missing", "finding_link": "not_automatically_inferred", "verification_artifact": "not_supplied"})
    missing = [] if requirements else [_missing("authoritative_requirements", "Conformance cannot be assessed without an authoritative source.", "Requirement breach, contractual nonconformance, or approved-roadmap deviation.", "Approved requirements/specifications/ADRs/acceptance criteria with owner and source reference.")]
    evidence = {"evidence_state": _state(context, "compliance_requirements"), "authority_status_supplied": authority, "supplied_requirement_count": len(mappings), "authoritative_requirement_count": sum(x["authority_classification"] == "authoritative" for x in mappings), "mappings": mappings, "repository_paths_are_contractual_authority": False, "contractual_obligations_invented": False}
    return _result(context, summary="Supplied requirements were mapped to implementation evidence where supportable, with authoritative, inferred, missing, and unverified states explicit.", requirements_traceability=evidence, missing_evidence=missing, evidence=evidence, unavailable_data_notes=[x["cannot_conclude"] for x in missing])


CORE_PROVIDER_REPLACEMENTS = {
    "technical_analysis": technical_analysis_provider,
    "functional_qa": functional_qa_provider,
    "platform_parity": platform_parity_provider,
    "stakeholder_alignment": stakeholder_alignment_provider,
    "requirements_traceability": requirements_traceability_provider,
}

__all__ = ["VERSION", "CORE_PROVIDER_REPLACEMENTS", "functional_qa_provider", "platform_parity_provider", "requirements_traceability_provider", "stakeholder_alignment_provider", "technical_analysis_provider"]
