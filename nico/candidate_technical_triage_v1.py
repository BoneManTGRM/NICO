from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.candidate-technical-triage.v1"
SOURCE_COMMIT_SHA = "9c876ba4e3e9bb152de52567232038e52a6bbb3e"
SOURCE_REGISTER_SHA256 = "93f35cf18dd808e8c5a2c1a4fbe5fa430971550a08b419b6cc2445ca08c8d8be"
SOURCE_CANDIDATE_COUNT = 662
SOURCE_VERDICT_COUNTS = {"not_actionable": 624, "needs_review": 38}
SOURCE_CATEGORY_VERDICT_COUNTS = {
    "static": {"not_actionable": 586},
    "secret": {"not_actionable": 17},
    "dependency": {"not_actionable": 21, "needs_review": 38},
}

_STATIC_RULES = {'B101': ('medium', 'assert_internal_or_acceptance_harness_no_boundary_bypass'), 'B104': ('high', 'intentional_service_bind_deployment_boundary'), 'B105': ('high', 'noncredential_constant_or_status_marker'), 'B107': ('high', 'empty_default_triggers_auth_block'), 'B108': ('high', 'temp_path_detection_guard_not_temp_file_creation'), 'B110': ('medium', 'best_effort_or_compatibility_exception_no_material_bypass'), 'B112': ('high', 'best_effort_iteration_skip_authoritative_gate_preserved'), 'B310': ('medium', 'fixed_https_or_operator_configured_endpoint'), 'B404': ('high', 'subprocess_import_only'), 'B603': ('medium', 'argv_execution_shell_false_inputs_constrained'), 'B607': ('medium', 'trusted_worker_tool_resolution'), 'B608': ('high', 'parameterized_sql_or_validated_identifier')}
_DEPENDENCY_NEEDS_REVIEW = {
    "GHSA-3F63-HFP8-52JQ",
    "GHSA-44WM-F244-XHP3",
    "GHSA-45HQ-CXWH-F6VC",
    "GHSA-4X4J-2G7C-83W6",
    "GHSA-5X94-69RX-G8H2",
    "GHSA-62P4-GMF7-7G93",
    "GHSA-65PC-FJ4G-8RJX",
    "GHSA-6R8X-57C9-28J4",
    "GHSA-8GHJ-P4VJ-MR35",
    "GHSA-8V84-F9PQ-WR9X",
    "GHSA-9HW9-CH79-4VH6",
    "GHSA-FJ7V-R99M-22GQ",
    "GHSA-JJJ6-MW9F-P565",
    "GHSA-PHJ9-MV4W-65PM",
    "GHSA-R73J-PQJ5-W3X7",
    "GHSA-VJC4-5QP5-M44J",
    "GHSA-WJX4-4JCJ-G98J",
    "GHSA-XJ96-63GP-2GMR",
    "PYSEC-2023-175",
    "PYSEC-2023-227",
    "PYSEC-2026-165",
    "PYSEC-2026-1793",
    "PYSEC-2026-1794",
    "PYSEC-2026-215",
    "PYSEC-2026-2253",
    "PYSEC-2026-2254",
    "PYSEC-2026-2255",
    "PYSEC-2026-2256",
    "PYSEC-2026-2257",
    "PYSEC-2026-2874",
    "PYSEC-2026-3451",
    "PYSEC-2026-3453",
    "PYSEC-2026-3454",
    "PYSEC-2026-3493",
    "PYSEC-2026-3494",
    "PYSEC-2026-3495",
    "PYSEC-2026-3496",
    "PYSEC-2026-457",
}
_DEPENDENCY_BUILD_TOOL = {
    "GHSA-4XH5-X5GV-QWPH",
    "GHSA-58QW-9MGM-455V",
    "GHSA-5XP3-JFQ3-5Q8X",
    "GHSA-6VGW-5PG2-W6JP",
    "GHSA-GPVV-69J7-GWJ8",
    "GHSA-JP4C-XJXW-MGF9",
    "GHSA-MQ26-G339-26XF",
    "GHSA-WF93-45JW-7689",
    "PYSEC-2020-173",
    "PYSEC-2021-437",
    "PYSEC-2023-228",
    "PYSEC-2026-1795",
    "PYSEC-2026-1796",
    "PYSEC-2026-196",
    "PYSEC-2026-2875",
    "PYSEC-2026-2876",
}
_DEPENDENCY_TOOLING_TRANSITIVE = {
    "GHSA-QMGC-5H2G-MVRW",
    "GHSA-W853-JP5J-5J7F",
    "PYSEC-2026-1374",
    "PYSEC-2026-1375",
}
_DEPENDENCY_MISATTRIBUTED = {
    "GHSA-J7HP-H8JX-5PPR",
}

_RATIONALES = {
    "assert_internal_or_acceptance_harness_no_boundary_bypass": (
        "Retained exact-SHA source review found assert usage in internal invariants, acceptance proofs, "
        "or test harnesses without an established supported attacker-controlled bypass."
    ),
    "intentional_service_bind_deployment_boundary": (
        "The bind address is an intentional deployment boundary; the retained finding did not establish "
        "a protected-boundary bypass."
    ),
    "noncredential_constant_or_status_marker": (
        "The flagged constant is a status, label, marker, or other noncredential value in the retained source context."
    ),
    "empty_default_triggers_auth_block": (
        "The empty default flows into an authorization check that blocks missing or invalid credentials."
    ),
    "temp_path_detection_guard_not_temp_file_creation": (
        "The literal temporary path is used for detection or rejection logic rather than insecure temporary-file creation."
    ),
    "best_effort_or_compatibility_exception_no_material_bypass": (
        "The broad exception is in best-effort diagnostics or compatibility handling; the authoritative security gate remains intact."
    ),
    "best_effort_iteration_skip_authoritative_gate_preserved": (
        "The skipped iteration is best-effort handling and does not replace or bypass the authoritative gate."
    ),
    "fixed_https_or_operator_configured_endpoint": (
        "The URL path is fixed HTTPS or operator-configured rather than a supported lower-trust arbitrary URL sink."
    ),
    "subprocess_import_only": (
        "The finding is the subprocess module import itself and does not establish command execution."
    ),
    "argv_execution_shell_false_inputs_constrained": (
        "The retained execution uses argv form with shell disabled and constrained command inputs."
    ),
    "trusted_worker_tool_resolution": (
        "The command is resolved from the trusted worker/tool catalog rather than lower-trust arbitrary executable input."
    ),
    "parameterized_sql_or_validated_identifier": (
        "The retained SQL path uses parameters, fixed mappings, or validated/quoted identifiers rather than raw lower-trust SQL text."
    ),
    "unverified_synthetic_test_fixture": (
        "The retained secret-scanner observation is an unverified synthetic test fixture; no verified production secret was established."
    ),
    "build_tool_version_not_product_runtime_dependency": (
        "The advisory applies to build/scanner tooling rather than a shipped NICO runtime dependency."
    ),
    "tooling_transitive_no_supported_reachable_lock_path": (
        "The transitive tooling dependency had no established supported product-runtime reachability in the retained evidence."
    ),
    "nested_affected_package_misattributed_as_scanned_dependency": (
        "The package name came from nested advisory metadata rather than a package actually scanned as an installed NICO dependency."
    ),
    "transitive_image_dependency_version_and_parser_reachability_unresolved": (
        "The retained dependency evidence required an exact current version/SBOM and supported input-reachability check before disposition."
    ),
}


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _classification(record: Mapping[str, Any]) -> dict[str, Any] | None:
    if not record.get("prior_candidate_id"):
        return None
    if str(record.get("prior_target_commit_sha") or "") != SOURCE_COMMIT_SHA:
        return None

    category = str(record.get("category") or "").casefold()
    rule = str(record.get("rule_id") or "").upper()

    if category == "static":
        mapped = _STATIC_RULES.get(rule)
        if not mapped:
            return None
        confidence, rationale_code = mapped
        return {
            "verdict": "not_actionable",
            "confidence": confidence,
            "rationale_code": rationale_code,
            "proposed_system_disposition": "approved_or_nonblocking",
            "exploitability_stack_rank": None,
            "recommended_next_step": (
                "Keep as hardening/maintainability work only if the owner wants the flagged pattern removed; "
                "do not count it as a confirmed material security finding."
            ),
        }

    if category == "secret":
        return {
            "verdict": "not_actionable",
            "confidence": "high",
            "rationale_code": "unverified_synthetic_test_fixture",
            "proposed_system_disposition": "excluded_test_only",
            "exploitability_stack_rank": None,
            "recommended_next_step": (
                "Continue secret scanning and keep real credential material out of fixtures; no production-secret remediation is supported by this retained finding."
            ),
        }

    if category == "dependency":
        if rule in _DEPENDENCY_NEEDS_REVIEW:
            return {
                "verdict": "needs_review",
                "confidence": "medium",
                "rationale_code": "transitive_image_dependency_version_and_parser_reachability_unresolved",
                "proposed_system_disposition": "review_required",
                "exploitability_stack_rank": 35,
                "recommended_next_step": (
                    "Verify the exact current dependency graph and scanner result after the explicit Pillow/idna remediation pins."
                ),
            }
        if rule in _DEPENDENCY_BUILD_TOOL:
            return {
                "verdict": "not_actionable",
                "confidence": "high",
                "rationale_code": "build_tool_version_not_product_runtime_dependency",
                "proposed_system_disposition": "approved_or_nonblocking",
                "exploitability_stack_rank": None,
                "recommended_next_step": "Retain build-image/SBOM evidence separately from product-runtime dependency findings.",
            }
        if rule in _DEPENDENCY_TOOLING_TRANSITIVE:
            return {
                "verdict": "not_actionable",
                "confidence": "medium",
                "rationale_code": "tooling_transitive_no_supported_reachable_lock_path",
                "proposed_system_disposition": "approved_or_nonblocking",
                "exploitability_stack_rank": None,
                "recommended_next_step": "Retain dependency reachability evidence if the tooling dependency later enters a shipped runtime path.",
            }
        if rule in _DEPENDENCY_MISATTRIBUTED:
            return {
                "verdict": "not_actionable",
                "confidence": "high",
                "rationale_code": "nested_affected_package_misattributed_as_scanned_dependency",
                "proposed_system_disposition": "approved_or_nonblocking",
                "exploitability_stack_rank": None,
                "recommended_next_step": "Preserve the raw advisory package identity so nested affected-package metadata is not counted as a scanned dependency.",
            }
    return None


def _overlay(record: dict[str, Any], classification: Mapping[str, Any]) -> None:
    rationale_code = str(classification.get("rationale_code") or "")
    record.update(
        {
            "technical_triage_status": "imported_proposal",
            "technical_triage_verdict": str(classification.get("verdict") or ""),
            "technical_triage_confidence": str(classification.get("confidence") or "unknown"),
            "technical_triage_rationale_code": rationale_code,
            "technical_triage_rationale": _RATIONALES.get(rationale_code, ""),
            "technical_triage_recommended_next_step": str(
                classification.get("recommended_next_step") or ""
            ),
            "technical_triage_exploitability_rank": classification.get("exploitability_stack_rank"),
            "technical_triage_source_commit_sha": SOURCE_COMMIT_SHA,
            "technical_triage_source_register_sha256": SOURCE_REGISTER_SHA256,
            "technical_triage_source_candidate_id": str(record.get("prior_candidate_id") or ""),
            "technical_triage_proposed_system_disposition": str(
                classification.get("proposed_system_disposition") or ""
            ),
            "technical_triage_human_approval_status": "pending",
            "technical_triage_human_approval_carried_forward": False,
            "technical_triage_client_delivery_allowed": False,
        }
    )


def apply_candidate_technical_triage(register: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(register))
    findings = [
        deepcopy(dict(item))
        for item in output.get("findings") or []
        if isinstance(item, Mapping)
    ]

    imported_records = 0
    imported_occurrences = 0
    not_actionable_records = 0
    not_actionable_occurrences = 0
    needs_review_records = 0
    needs_review_occurrences = 0
    current_only_records = 0
    current_only_occurrences = 0
    unmapped_prior_records = 0
    unmapped_prior_occurrences = 0

    for record in findings:
        occurrence_count = max(1, _count(record.get("occurrence_count")))
        classification = _classification(record)
        if classification is not None:
            _overlay(record, classification)
            imported_records += 1
            imported_occurrences += occurrence_count
            if classification["verdict"] == "not_actionable":
                not_actionable_records += 1
                not_actionable_occurrences += occurrence_count
            else:
                needs_review_records += 1
                needs_review_occurrences += occurrence_count
            continue

        if record.get("prior_candidate_id"):
            record["technical_triage_status"] = "pending_unmapped_prior"
            unmapped_prior_records += 1
            unmapped_prior_occurrences += occurrence_count
        else:
            record["technical_triage_status"] = "pending_current_only"
            current_only_records += 1
            current_only_occurrences += occurrence_count
        record["technical_triage_human_approval_status"] = "pending"
        record["technical_triage_human_approval_carried_forward"] = False
        record["technical_triage_client_delivery_allowed"] = False

    output["findings"] = findings
    output["technical_candidate_triage"] = {
        "artifact_schema": VERSION,
        "status": "complete",
        "source_register_available": True,
        "source_target_commit_sha": SOURCE_COMMIT_SHA,
        "source_register_sha256": SOURCE_REGISTER_SHA256,
        "source_candidate_count": SOURCE_CANDIDATE_COUNT,
        "source_verdict_counts": deepcopy(SOURCE_VERDICT_COUNTS),
        "source_category_verdict_counts": deepcopy(SOURCE_CATEGORY_VERDICT_COUNTS),
        "matched_current_candidate_records": imported_records,
        "matched_current_candidate_occurrences": imported_occurrences,
        "imported_not_actionable_records": not_actionable_records,
        "imported_not_actionable_occurrences": not_actionable_occurrences,
        "imported_needs_review_records": needs_review_records,
        "imported_needs_review_occurrences": needs_review_occurrences,
        "current_only_candidate_records": current_only_records,
        "current_only_candidate_occurrences": current_only_occurrences,
        "unmapped_prior_candidate_records": unmapped_prior_records,
        "unmapped_prior_candidate_occurrences": unmapped_prior_occurrences,
        "technical_triage_authority": "proposal_only_pending_authorized_human_review",
        "canonical_dispositions_mutated": False,
        "score_effect": "none_from_import_alone",
        "human_approval_carried_forward": False,
        "human_approval_status": "pending",
        "client_delivery_allowed": False,
    }
    output["canonical_digest_sha256"] = hashlib.sha256(
        json.dumps(findings, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return output


__all__ = [
    "VERSION",
    "SOURCE_COMMIT_SHA",
    "SOURCE_REGISTER_SHA256",
    "SOURCE_CANDIDATE_COUNT",
    "SOURCE_VERDICT_COUNTS",
    "SOURCE_CATEGORY_VERDICT_COUNTS",
    "apply_candidate_technical_triage",
]
