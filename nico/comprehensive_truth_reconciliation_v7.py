from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-truth-reconciliation.v7"
DISPOSITION_MODEL = "mutually-exclusive-candidate-dispositions.v1"
WORKFLOW_MODEL = "complete-workflow-outcome-taxonomy.v1"
SCORING_MODEL = "technical-minus-named-assurance-deductions.v1"

_SUMMARY_MARKER = "__nico_truth_reconciled_summary_v7__"
_REGISTER_MARKER = "__nico_truth_reconciled_register_v7__"
_OPERATIONAL_MARKER = "__nico_truth_reconciled_operational_v7__"
_PROVIDER_MARKER = "__nico_truth_reconciled_provider_v7__"


def _text(value: Any, limit: int = 4000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _text(value).casefold().replace("_", "-")).strip("-")


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _reconcile_tool_counts(raw: Mapping[str, Any]) -> tuple[dict[str, int], dict[str, Any]]:
    source = {
        "raw": _integer(raw.get("raw")),
        "material": _integer(raw.get("material")),
        "review_required": _integer(raw.get("review_required")),
        "approved_or_nonblocking": _integer(raw.get("approved_or_nonblocking")),
        "excluded_test_only": _integer(raw.get("excluded_test_only")),
    }
    raw_total = source["raw"]
    fixed = (
        source["material"]
        + source["approved_or_nonblocking"]
        + source["excluded_test_only"]
    )
    impossible = fixed > raw_total
    review_required = max(0, raw_total - fixed)
    reconciled = {
        "raw": raw_total,
        "material": source["material"],
        "review_required": review_required,
        "approved_or_nonblocking": source["approved_or_nonblocking"],
        "excluded_test_only": source["excluded_test_only"],
    }
    adjustment = {
        "source": source,
        "reconciled": reconciled,
        "source_review_required": source["review_required"],
        "reconciled_review_required": review_required,
        "review_required_adjusted": source["review_required"] != review_required,
        "fixed_dispositions_exceed_raw": impossible,
        "disposition_sum": (
            reconciled["material"]
            + reconciled["review_required"]
            + reconciled["approved_or_nonblocking"]
            + reconciled["excluded_test_only"]
        ),
    }
    return reconciled, adjustment


def reconciled_summary_by_tool(scan: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    summary = scan.get("finding_summary") if isinstance(scan.get("finding_summary"), Mapping) else {}
    by_tool = summary.get("by_tool") if isinstance(summary.get("by_tool"), Mapping) else {}
    output: dict[str, dict[str, int]] = {}
    for tool, raw in by_tool.items():
        if not isinstance(raw, Mapping):
            continue
        reconciled, _adjustment = _reconcile_tool_counts(raw)
        output[_text(tool, 120).casefold()] = reconciled
    return output


def _rule_family(record: Mapping[str, Any]) -> str:
    rule = _token(record.get("rule_id")) or "unclassified"
    category = _token(record.get("category")) or "unknown"
    if rule.startswith("ghsa-") or rule.startswith("cve-"):
        return f"dependency-vulnerability:{rule}"
    if category == "secret":
        return f"secret-candidate:{rule}"
    if category == "static":
        return f"static-analysis:{rule}"
    return f"{category}:{rule}"


def _production_classification(record: Mapping[str, Any]) -> str:
    disposition = _token(record.get("disposition"))
    path = _text(record.get("source_path"), 1200).casefold()
    if disposition == "excluded-test-only":
        return "non_production"
    if any(part in path.split("/") for part in ("test", "tests", "fixture", "fixtures", "example", "examples")):
        return "non_production"
    return "production_or_unknown"


def _enrich_candidate(record: Mapping[str, Any]) -> dict[str, Any]:
    item = deepcopy(dict(record))
    evidence_digest = _digest(
        {
            "scanner": item.get("scanner"),
            "rule_id": item.get("rule_id"),
            "source_path": item.get("source_path"),
            "line": item.get("line"),
            "evidence": item.get("evidence"),
        }
    )
    family = _rule_family(item)
    duplicate_group = _digest(
        {
            "commit": item.get("exact_commit_sha"),
            "source_path": item.get("source_path"),
            "line": item.get("line"),
            "rule_family": family,
            "evidence_digest": evidence_digest,
        }
    )
    batch_key = _digest(
        {
            "scanner": item.get("scanner"),
            "rule_family": family,
            "production_classification": _production_classification(item),
            "evidence_quality": item.get("evidence_quality"),
        }
    )
    proposed = _text(item.get("disposition"), 120) or "review_required"
    item.update(
        {
            "candidate_id": item.get("finding_id"),
            "normalized_rule_family": family,
            "duplicate_group_id": f"NICO-DUPE-{duplicate_group[:16].upper()}",
            "evidence_digest_sha256": evidence_digest,
            "supporting_evidence_digest_sha256": evidence_digest,
            "scanner_severity": item.get("severity") or "unknown",
            "reachability": item.get("reachability") or "not_assessed",
            "production_classification": _production_classification(item),
            "proposed_disposition": proposed,
            "human_disposition": item.get("human_disposition"),
            "disposition_rationale": item.get("disposition_rationale")
            or "Automated proposed disposition; human review has not been recorded.",
            "reviewer_identity": item.get("reviewer_identity"),
            "review_timestamp": item.get("review_timestamp"),
            "batch_disposition_key": f"NICO-BATCH-{batch_key[:16].upper()}",
            "raw_payload_retention_state": (
                "count_only"
                if item.get("evidence_quality") == "count_only"
                else "retained"
            ),
            "triage_state": (
                "pending_human_review"
                if proposed == "review_required"
                else "automated_provisional_disposition"
            ),
        }
    )
    return item


def reconciled_build_register(
    scan: Mapping[str, Any],
    commit_sha: str,
) -> dict[str, Any]:
    from nico import comprehensive_native_providers_v5 as providers

    previous = getattr(reconciled_build_register, "_nico_previous")
    source_summary = (
        (scan.get("finding_summary") or {}).get("by_tool")
        if isinstance(scan.get("finding_summary"), Mapping)
        else {}
    )
    source_summary = source_summary if isinstance(source_summary, Mapping) else {}
    adjustments: dict[str, dict[str, Any]] = {}
    impossible_tools: list[str] = []
    for tool, raw in source_summary.items():
        if not isinstance(raw, Mapping):
            continue
        _reconciled, adjustment = _reconcile_tool_counts(raw)
        tool_name = _text(tool, 120).casefold()
        adjustments[tool_name] = adjustment
        if adjustment["fixed_dispositions_exceed_raw"]:
            impossible_tools.append(tool_name)

    result = deepcopy(previous(scan, commit_sha))
    findings = [
        _enrich_candidate(item)
        for item in result.get("findings") or []
        if isinstance(item, Mapping)
    ]
    result["findings"] = findings
    result["candidate_disposition_model"] = DISPOSITION_MODEL
    result["source_summary_reconciliation"] = adjustments
    result["source_summary_adjustment_count"] = sum(
        1 for value in adjustments.values() if value.get("review_required_adjusted")
    )
    result["mutually_exclusive_dispositions_verified"] = not impossible_tools
    result["impossible_disposition_tools"] = impossible_tools
    totals = result.get("totals") if isinstance(result.get("totals"), Mapping) else {}
    disposition_sum = sum(
        _integer(totals.get(key))
        for key in (
            "material",
            "review_required",
            "approved_or_nonblocking",
            "excluded_test_only",
        )
    )
    total_raw = _integer(totals.get("raw"))
    result["disposition_sum"] = disposition_sum
    result["disposition_sum_matches_raw"] = disposition_sum == total_raw
    if impossible_tools or disposition_sum != total_raw:
        result["status"] = "blocked"
        result["count_parity_verified"] = False
        discrepancies = list(result.get("discrepancies") or [])
        discrepancies.append(
            {
                "reason": "mutually_exclusive_disposition_invariant_failed",
                "raw": total_raw,
                "disposition_sum": disposition_sum,
                "tools": impossible_tools,
            }
        )
        result["discrepancies"] = discrepancies
    result["canonical_digest_sha256"] = _digest(findings)
    return result


def complete_ci_operational_health(repo: Mapping[str, Any]) -> dict[str, Any]:
    workflow = repo.get("workflow_evidence") if isinstance(repo.get("workflow_evidence"), Mapping) else {}
    success = _integer(workflow.get("successful_runs"))
    explicit_non_success = _integer(workflow.get("non_success_runs"))
    categories = {
        "success": success,
        "failure": _integer(workflow.get("failed_runs") or workflow.get("failure_runs")),
        "cancelled": _integer(workflow.get("cancelled_runs")),
        "skipped": _integer(workflow.get("skipped_runs")),
        "neutral": _integer(workflow.get("neutral_runs")),
        "timed_out": _integer(workflow.get("timed_out_runs")),
        "action_required": _integer(workflow.get("action_required_runs")),
        "queued_or_in_progress": _integer(
            workflow.get("queued_runs")
        )
        + _integer(workflow.get("in_progress_runs")),
        "unknown": _integer(workflow.get("unknown_runs")),
    }
    granular_non_success = sum(
        value for key, value in categories.items() if key not in {"success", "unknown"}
    )
    if granular_non_success == 0 and explicit_non_success:
        categories["failure"] = explicit_non_success
    elif explicit_non_success > granular_non_success:
        categories["unknown"] += explicit_non_success - granular_non_success

    explicit_total = max(
        _integer(workflow.get("workflow_run_count")),
        _integer(workflow.get("total_runs")),
        _integer(repo.get("workflow_run_count")),
    )
    accounted = sum(categories.values())
    total = max(explicit_total, accounted)
    if total > accounted:
        categories["unknown"] += total - accounted
    accounted = sum(categories.values())
    success_rate = round(categories["success"] * 100 / total) if total else None
    if success_rate is None:
        status = "unavailable"
    elif success_rate >= 95:
        status = "strong"
    elif success_rate >= 80:
        status = "moderate"
    else:
        status = "weak"
    return {
        "status": status,
        "score": success_rate,
        "successful_runs": categories["success"],
        "non_success_runs": total - categories["success"],
        "observed_run_count": total,
        "workflow_run_count": total,
        "outcome_taxonomy": categories,
        "outcome_taxonomy_model": WORKFLOW_MODEL,
        "outcome_count_parity_verified": accounted == total,
        "unclassified_outcome_count": categories["unknown"],
        "score_effect": "operational_context_only",
        "technical_configuration_score_affected": False,
    }


def _augment_provider_result(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    assessment = (
        deepcopy(dict(output.get("assessment") or {}))
        if isinstance(output.get("assessment"), Mapping)
        else {}
    )
    if not assessment:
        return output
    contract = (
        deepcopy(dict(assessment.get("score_contract") or {}))
        if isinstance(assessment.get("score_contract"), Mapping)
        else {}
    )
    technical = _integer(
        contract.get("technical_score")
        or assessment.get("technical_score")
        or assessment.get("canonical_technical_score")
    )
    candidate_penalty = _integer(contract.get("candidate_volume_penalty"))
    payload_penalty = _integer(contract.get("missing_raw_payload_penalty"))
    analyzer_penalty = _integer(contract.get("incomplete_analyzer_penalty"))
    named_other = contract.get("other_assurance_penalties")
    named_other = named_other if isinstance(named_other, Mapping) else {}
    other_penalty = sum(_integer(value) for value in named_other.values())
    assurance_penalty = candidate_penalty + payload_penalty + analyzer_penalty + other_penalty
    evidence_adjusted = max(0, technical - assurance_penalty)
    formula = (
        f"{technical} - {candidate_penalty} - {payload_penalty} - "
        f"{analyzer_penalty} - {other_penalty} = {evidence_adjusted}"
    )
    unavailable_notes = assessment.get("unavailable_data_notes")
    if not isinstance(unavailable_notes, list):
        unavailable_notes = output.get("unavailable_data_notes")
    unavailable_notes = unavailable_notes if isinstance(unavailable_notes, list) else []
    stages = assessment.get("stage_summaries")
    stages = stages if isinstance(stages, list) else output.get("stage_summaries")
    stages = stages if isinstance(stages, list) else []
    limited_stage_count = sum(
        1
        for item in stages
        if isinstance(item, Mapping)
        and _token(item.get("status")) in {"unavailable", "limited", "review-required"}
    )
    unavailable_count = max(len(unavailable_notes), limited_stage_count)
    contract.update(
        {
            "scoring_model_version": SCORING_MODEL,
            "score_formula": formula,
            "technical_score": technical,
            "candidate_volume_penalty": candidate_penalty,
            "missing_raw_payload_penalty": payload_penalty,
            "incomplete_analyzer_penalty": analyzer_penalty,
            "other_assurance_penalties": dict(named_other),
            "other_assurance_penalty_total": other_penalty,
            "assurance_penalty": assurance_penalty,
            "evidence_adjusted_score": evidence_adjusted,
            "all_numeric_score_inputs_renderable": True,
        }
    )
    assessment["score_contract"] = contract
    assessment["technical_score"] = technical
    assessment["canonical_technical_score"] = technical
    assessment["evidence_adjusted_score"] = evidence_adjusted
    assessment["canonical_evidence_adjusted_score"] = evidence_adjusted
    assessment["unavailable_note_count"] = unavailable_count
    assessment["source_loc"] = assessment.get("source_loc") or "not_available"
    operational = assessment.get("ci_cd_operational_health")
    operational = operational if isinstance(operational, Mapping) else {}
    if operational:
        assessment["ci_cd_operational_health"] = deepcopy(dict(operational))
    register = assessment.get("canonical_scanner_finding_register")
    register = register if isinstance(register, Mapping) else {}
    totals = register.get("totals") if isinstance(register.get("totals"), Mapping) else {}
    assessment["candidate_disposition"] = {
        "total_raw": _integer(totals.get("raw")),
        "confirmed_material": _integer(totals.get("material")),
        "review_required": _integer(totals.get("review_required")),
        "approved_nonblocking": _integer(totals.get("approved_or_nonblocking")),
        "excluded_nonproduction": _integer(totals.get("excluded_test_only")),
        "count_only": _integer(totals.get("count_only")),
        "mutually_exclusive": register.get("disposition_sum_matches_raw") is True,
        "model_version": DISPOSITION_MODEL,
    }
    output["assessment"] = assessment
    evidence = (
        deepcopy(dict(output.get("evidence") or {}))
        if isinstance(output.get("evidence"), Mapping)
        else {}
    )
    evidence.update(
        {
            "score_formula": formula,
            "scoring_model_version": SCORING_MODEL,
            "technical_score": technical,
            "evidence_adjusted_score": evidence_adjusted,
            "candidate_volume_penalty": candidate_penalty,
            "missing_raw_payload_penalty": payload_penalty,
            "incomplete_analyzer_penalty": analyzer_penalty,
            "other_assurance_penalty_total": other_penalty,
            "unavailable_note_count": unavailable_count,
            "candidate_disposition": deepcopy(assessment["candidate_disposition"]),
        }
    )
    output["evidence"] = evidence
    return output


def install_comprehensive_truth_reconciliation_v7() -> dict[str, Any]:
    from nico import comprehensive_native_providers_v5 as providers

    if not getattr(providers._summary_by_tool, _SUMMARY_MARKER, False):
        setattr(reconciled_summary_by_tool, _SUMMARY_MARKER, True)
        setattr(reconciled_summary_by_tool, "_nico_previous", providers._summary_by_tool)
        providers._summary_by_tool = reconciled_summary_by_tool

    if not getattr(providers.build_canonical_scanner_finding_register, _REGISTER_MARKER, False):
        previous_builder = providers.build_canonical_scanner_finding_register
        setattr(reconciled_build_register, _REGISTER_MARKER, True)
        setattr(reconciled_build_register, "_nico_previous", previous_builder)
        providers.build_canonical_scanner_finding_register = reconciled_build_register

    if not getattr(providers._ci_operational_health, _OPERATIONAL_MARKER, False):
        setattr(complete_ci_operational_health, _OPERATIONAL_MARKER, True)
        setattr(complete_ci_operational_health, "_nico_previous", providers._ci_operational_health)
        providers._ci_operational_health = complete_ci_operational_health

    current_provider = providers.canonical_scoring_provider
    if not getattr(current_provider, _PROVIDER_MARKER, False):

        @wraps(current_provider)
        def canonical_scoring_provider(context: dict[str, Any]) -> dict[str, Any]:
            return _augment_provider_result(current_provider(context))

        setattr(canonical_scoring_provider, _PROVIDER_MARKER, True)
        setattr(canonical_scoring_provider, "_nico_previous", current_provider)
        providers.canonical_scoring_provider = canonical_scoring_provider

    return {
        "status": "installed",
        "version": VERSION,
        "candidate_disposition_model": DISPOSITION_MODEL,
        "workflow_outcome_model": WORKFLOW_MODEL,
        "scoring_model": SCORING_MODEL,
        "mutually_exclusive_dispositions_required": True,
        "workflow_outcome_parity_required": True,
        "blank_numeric_score_inputs_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "DISPOSITION_MODEL",
    "SCORING_MODEL",
    "VERSION",
    "WORKFLOW_MODEL",
    "complete_ci_operational_health",
    "install_comprehensive_truth_reconciliation_v7",
    "reconciled_build_register",
    "reconciled_summary_by_tool",
]
