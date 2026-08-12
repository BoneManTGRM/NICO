from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from nico import comprehensive_native_providers as legacy
from nico.phase3_engagement_intake_v1 import engagement_truth

VERSION = "nico.phase3_evidence_core.v2"


def _text(value: Any, limit: int = 1200) -> str:
    return " ".join(str(value or "").split())[:limit]


def _values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [] if value in (None, "") else [_text(value)]


def _module(context: Mapping[str, Any], module_id: str) -> dict[str, Any]:
    package = context.get("human_evidence") if isinstance(context.get("human_evidence"), Mapping) else {}
    modules = package.get("modules") if isinstance(package.get("modules"), Mapping) else {}
    raw = modules.get(module_id)
    return dict(raw) if isinstance(raw, Mapping) else {}


def _field(context: Mapping[str, Any], module_id: str, field: str) -> list[str]:
    module = _module(context, module_id)
    evidence = module.get("evidence") if isinstance(module.get("evidence"), Mapping) else {}
    return _values(evidence.get(field))


def _state(context: Mapping[str, Any], module_id: str) -> str:
    module = _module(context, module_id)
    status = _text(module.get("status"), 80).casefold()
    if status == "excluded":
        return "not_applicable"
    if status in {"complete", "partial"}:
        verification = " ".join(_field(context, module_id, "verification_status")).casefold()
        return "retained_verified" if verification in {"verified", "retained_verified", "verified_by_authorized_source"} else "supplied_unverified"
    return "not_supplied"


def _prior(context: Mapping[str, Any], stage_id: str) -> dict[str, Any]:
    return legacy._prior(dict(context), stage_id)


def _repo(context: Mapping[str, Any]) -> dict[str, Any]:
    return legacy._repo(dict(context))


def _complexity(context: Mapping[str, Any]) -> dict[str, Any]:
    return legacy._complexity(dict(context))


def _result(context: Mapping[str, Any], status: str = "complete", **payload: Any) -> dict[str, Any]:
    return legacy._result(dict(context), status, **payload)


def _missing(kind: str, why: str, cannot: str, resolve: str, effect: str = "scope_limitation") -> dict[str, str]:
    return {
        "evidence_type": kind,
        "state": "not_supplied",
        "why_it_matters": why,
        "cannot_conclude": cannot,
        "evidence_to_resolve": resolve,
        "approval_effect": effect,
    }


def _outcome(value: str) -> str:
    lowered = value.casefold()
    if re.search(r"\b(pass|passed|success|successful|ok)\b", lowered):
        return "passed"
    if re.search(r"\b(fail|failed|failure|error|broken|regression)\b", lowered):
        return "failed"
    if re.search(r"\b(skip|skipped|not run|blocked|pending|unknown|inconclusive)\b", lowered):
        return "unresolved"
    return "unclassified"


def _qa_result_synthesis(cases: list[str], observed: list[str]) -> dict[str, Any]:
    classified = [{"result": item, "outcome": _outcome(item)} for item in observed]
    counts = {name: sum(row["outcome"] == name for row in classified) for name in ("passed", "failed", "unresolved", "unclassified")}
    return {
        "result_count": len(classified),
        "outcome_counts": counts,
        "classified_results": classified[:100],
        "test_case_count": len(cases),
        "result_gap_count": max(0, len(cases) - len(observed)),
        "result_gap_detected": len(cases) > len(observed),
        "draft_conclusion": (
            "Supplied observed results include one or more failed outcomes; professional review and remediation evidence are required."
            if counts["failed"]
            else "Supplied observed results contain no parsed failure token, but this synthesis is not stakeholder acceptance or production certification."
            if classified
            else "No observed runtime result was supplied."
        ),
    }


def _parity_matrix_synthesis(matrix: list[str]) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    by_feature: dict[str, set[str]] = {}
    for item in matrix:
        parts = [_text(part, 400) for part in re.split(r"\s*(?:\||;|,)\s*", item) if _text(part, 400)]
        feature = parts[0] if parts else item
        platform = parts[1] if len(parts) > 1 else "unspecified"
        outcome = _outcome(parts[2] if len(parts) > 2 else item)
        rows.append({"raw": item, "feature": feature, "platform": platform, "outcome": outcome})
        by_feature.setdefault(feature.casefold(), set()).add(outcome)
    divergence = sorted(feature for feature, values in by_feature.items() if len({value for value in values if value != "unclassified"}) > 1)
    return {
        "parsed_row_count": len(rows),
        "parsed_rows": rows[:100],
        "observed_divergence_candidates": divergence[:50],
        "observed_divergence_candidate_count": len(divergence),
        "matrix_is_approved_parity_authority": False,
    }


def technical_analysis_provider(context: dict[str, Any]) -> dict[str, Any]:
    baseline = legacy.technical_analysis_provider(context)
    if baseline.get("status") != "complete":
        return baseline
    repo, complexity = _repo(context), _complexity(context)
    activity = repo.get("activity_evidence") if isinstance(repo.get("activity_evidence"), Mapping) else {}
    workflow = repo.get("workflow_evidence") if isinstance(repo.get("workflow_evidence"), Mapping) else {}
    hotspots = [dict(item) for item in complexity.get("hotspots") or [] if isinstance(item, Mapping)][:25]
    duplicate = complexity.get("duplicate_evidence") if isinstance(complexity.get("duplicate_evidence"), Mapping) else {}
    evidence = deepcopy(dict(baseline.get("evidence") or {}))
    evidence.update(
        {
            "top_hotspots": hotspots[:10],
            "hotspot_count": len(hotspots),
            "top_coupled_files": list(complexity.get("top_coupled_files") or [])[:10],
            "duplicate_line_ratio": duplicate.get("duplicate_line_ratio"),
            "duplicate_block_groups": duplicate.get("duplicate_block_groups"),
            "change_pattern_context": {
                "commits_observed": activity.get("commits_returned", 0),
                "pull_requests_observed": activity.get("pull_requests_returned", 0),
                "merged_pull_requests_observed": activity.get("merged_pull_requests", 0),
                "workflow_runs_observed": workflow.get("workflow_run_count", 0),
                "activity_volume_quality_score_effect": "none",
            },
            "maintainability_scope_note": "Hotspots, coupling, and duplication are evidence-bound to the retained exact-SHA sampled source set.",
        }
    )
    baseline["evidence"] = evidence
    baseline["summary"] = "Exact-source maintainability, complexity hotspots, coupling, duplication, workflow automation, and bounded change history were synthesized; activity volume remains unscored context."
    return baseline


def functional_qa_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context)
    architecture = repo.get("architecture_evidence") if isinstance(repo.get("architecture_evidence"), Mapping) else {}
    workflows = repo.get("workflow_evidence") if isinstance(repo.get("workflow_evidence"), Mapping) else {}
    cases = _field(context, "functional_qa", "test_cases")
    observed = _field(context, "functional_qa", "observed_results")
    supplied = bool(cases or observed)
    synthesis = _qa_result_synthesis(cases, observed)
    missing = [] if supplied else [
        _missing(
            "runtime_functional_qa",
            "Repository tests do not establish production user journeys.",
            "Production journey, integration, browser/device, and stakeholder acceptance.",
            "Approved journey matrix, runtime environment, observed results, and acceptance criteria.",
        )
    ]
    if supplied and synthesis["result_gap_detected"]:
        missing.append(
            _missing(
                "functional_qa_result_gaps",
                "Every supplied critical journey needs a retained observed result before the evidence set is complete.",
                "Complete runtime coverage for the supplied journey matrix.",
                "Observed result records for the remaining supplied test cases.",
            )
        )
    evidence = {
        "repository_test_inventory_state": "retained_verified",
        "test_path_count": int(architecture.get("test_path_count") or 0),
        "test_commands_detected": [item for item in workflows.get("commands_detected") or [] if "test" in str(item).casefold()],
        "runtime_evidence_state": _state(context, "functional_qa") if supplied else "not_assessed",
        "supplied_test_cases": cases,
        "supplied_observed_results": observed,
        "automated_result_synthesis": synthesis,
        "repository_tests_are_runtime_acceptance": False,
        "runtime_acceptance_established": False,
        "stakeholder_acceptance_established": False,
    }
    return _result(
        context,
        summary="Repository test inventory, supplied journey evidence, parsed results, coverage gaps, and draft QA conclusions were reconciled without treating repository tests or model synthesis as runtime acceptance.",
        functional_qa=evidence,
        missing_evidence=missing,
        evidence=evidence,
        unavailable_data_notes=[item["cannot_conclude"] for item in missing],
    )


def platform_parity_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context)
    files = repo.get("file_evidence") if isinstance(repo.get("file_evidence"), Mapping) else {}
    sampled = [str(item) for item in files.get("sampled_paths") or []]
    matrix = _field(context, "platform_parity", "matrix")
    supplied = bool(matrix)
    synthesis = _parity_matrix_synthesis(matrix)
    missing = [] if supplied else [
        _missing(
            "device_runtime_parity",
            "Source/config indicators cannot prove runtime or device parity.",
            "Actual feature, device, permission, or localization parity.",
            "Supported device/platform matrix with observed runtime results and approved parity criteria.",
        )
    ]
    evidence = {
        "source_indicator_state": "retained_verified",
        "ios_paths": [path for path in sampled if any(token in path.casefold() for token in ("ios", ".swift", "xcode"))][:30],
        "android_paths": [path for path in sampled if any(token in path.casefold() for token in ("android", ".kt", ".gradle"))][:30],
        "runtime_matrix_state": _state(context, "platform_parity") if supplied else "not_assessed",
        "supplied_matrix": matrix,
        "matrix_synthesis": synthesis,
        "source_indicators_are_device_parity": False,
        "device_runtime_parity_established": False,
        "permission_runtime_parity_established": False,
    }
    return _result(
        context,
        summary="Repository platform indicators and supplied feature/device observations were reconciled and divergence candidates surfaced without promoting source indicators or an unapproved matrix to runtime/device parity.",
        platform_parity=evidence,
        missing_evidence=missing,
        evidence=evidence,
        unavailable_data_notes=[item["cannot_conclude"] for item in missing],
    )


def stakeholder_alignment_provider(context: dict[str, Any]) -> dict[str, Any]:
    objectives = _field(context, "stakeholder_context", "objectives") + _field(context, "product_objectives", "objectives")
    constraints = _field(context, "stakeholder_context", "constraints") + _field(context, "release_constraints", "constraints")
    success = _field(context, "product_objectives", "success_measures")
    supplied = bool(objectives or constraints or success)
    missing = [] if supplied else [
        _missing(
            "stakeholder_business_authority",
            "Technical evidence cannot establish stakeholder intent or business authority.",
            "Approved priorities, budget/deadline authority, residual-risk ownership, or client acceptance.",
            "Authorized objectives, constraints, success measures, decision owners, and authority records.",
        )
    ]
    seen: dict[str, str] = {}
    contradictions: list[dict[str, Any]] = []
    for kind, values in (("objective", objectives), ("constraint", constraints)):
        for value in values:
            key = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
            if key in seen and seen[key] != kind:
                contradictions.append({"statement": value, "types": [seen[key], kind]})
            seen[key] = kind
    evidence = {
        "engagement": engagement_truth(
            {
                "identity": {"customer_id": context.get("customer_id"), "project_id": context.get("project_id")},
                "human_evidence": context.get("human_evidence") or {},
            }
        ),
        "evidence_state": _state(context, "stakeholder_context") if supplied else "not_supplied",
        "objectives": objectives,
        "constraints": constraints,
        "success_measures": success,
        "contradictions": contradictions,
        "stakeholder_authority_established": False,
        "model_inference_is_stakeholder_authority": False,
        "disputed_interpretation_requires_human_decision": True,
    }
    return _result(
        context,
        summary="Supplied stakeholder/business evidence was organized, linked to the engagement, and checked for conflicts while authority and disputed meaning remain human decisions.",
        stakeholder_alignment=evidence,
        missing_evidence=missing,
        evidence=evidence,
        unavailable_data_notes=[item["cannot_conclude"] for item in missing],
    )


def _req_id(text: str, index: int) -> str:
    match = re.match(r"\s*([A-Za-z][A-Za-z0-9_.-]{1,48})\s*[:|\-]", text)
    return match.group(1) if match else f"REQ-{index:03d}"


def _authority_for(requirement_index: int, values: list[str]) -> str:
    value = values[requirement_index] if requirement_index < len(values) else values[0] if len(values) == 1 else ""
    lowered = value.casefold()
    if lowered in {"authoritative", "approved", "contractual"}:
        return "authoritative"
    if lowered in {"draft", "inferred", "unverified", "supplied_unverified"}:
        return "supplied_unverified"
    return "missing"


def requirements_traceability_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context)
    files = repo.get("file_evidence") if isinstance(repo.get("file_evidence"), Mapping) else {}
    sampled = [str(item) for item in files.get("sampled_paths") or []]
    requirements = _field(context, "compliance_requirements", "requirements")
    authority = _field(context, "compliance_requirements", "authority_status")
    mappings: list[dict[str, Any]] = []
    for index, requirement in enumerate(requirements):
        tokens = [
            token
            for token in re.findall(r"[a-z0-9_./-]{4,}", requirement.casefold())
            if token not in {"shall", "must", "should", "requirement"}
        ]
        matches = [path for path in sampled if any(token in path.casefold() for token in tokens[:8])][:10]
        mappings.append(
            {
                "requirement_id": _req_id(requirement, index + 1),
                "requirement": requirement,
                "authority_classification": _authority_for(index, authority),
                "implementation_evidence": matches,
                "implementation_mapping_classification": "inferred" if matches else "missing",
                "finding_link": "not_automatically_inferred",
                "status_or_owner": "not_supplied",
                "verification_artifact": "not_supplied",
            }
        )
    missing: list[dict[str, str]] = []
    if not requirements:
        missing.append(
            _missing(
                "authoritative_requirements",
                "Conformance cannot be assessed without an authoritative source.",
                "Requirement breach, contractual nonconformance, or approved-roadmap deviation.",
                "Approved requirements/specifications/ADRs/acceptance criteria with owner and source reference.",
            )
        )
    elif any(item["authority_classification"] == "missing" for item in mappings):
        missing.append(
            _missing(
                "requirements_authority_status",
                "Supplied requirements need an authority classification before contractual or approved conformance can be asserted.",
                "Whether the affected statements are approved obligations, drafts, or informal notes.",
                "Authority status and source provenance for each supplied requirement set.",
            )
        )
    evidence = {
        "evidence_state": _state(context, "compliance_requirements"),
        "authority_status_supplied": authority,
        "supplied_requirement_count": len(mappings),
        "authoritative_requirement_count": sum(item["authority_classification"] == "authoritative" for item in mappings),
        "mappings": mappings,
        "repository_paths_are_contractual_authority": False,
        "contractual_obligations_invented": False,
        "inferred_mapping_is_authoritative": False,
    }
    return _result(
        context,
        summary="Supplied requirements were mapped to retained implementation paths where supportable, with authoritative, supplied-unverified, inferred, missing, and verification states explicit.",
        requirements_traceability=evidence,
        missing_evidence=missing,
        evidence=evidence,
        unavailable_data_notes=[item["cannot_conclude"] for item in missing],
    )


CORE_PROVIDER_REPLACEMENTS = {
    "technical_analysis": technical_analysis_provider,
    "functional_qa": functional_qa_provider,
    "platform_parity": platform_parity_provider,
    "stakeholder_alignment": stakeholder_alignment_provider,
    "requirements_traceability": requirements_traceability_provider,
}

__all__ = [
    "VERSION",
    "CORE_PROVIDER_REPLACEMENTS",
    "_field",
    "_missing",
    "_prior",
    "_repo",
    "_result",
    "_state",
    "_text",
    "functional_qa_provider",
    "platform_parity_provider",
    "requirements_traceability_provider",
    "stakeholder_alignment_provider",
    "technical_analysis_provider",
]
