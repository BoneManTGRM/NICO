"""Frozen static-analysis preparation profile, not completed C0 qualification.

This preparation does not compile, fuzz, or sanitizer-instrument targets.
The original qualification still requires configuration-aware analysis, a real
build and runtime checks. Retained upstream context is not an execution plan.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

from nico.scanner_worker import (
    DEFAULT_TOOL_TIMEOUT_SECONDS,
    MAX_GIT_HISTORY_BYTES,
    MAX_REPO_BYTES,
    TOTAL_SCAN_TIMEOUT_SECONDS,
)

VERSION = "nico.cpp_large_repository_contract.v2"

HISTORICAL_REGRESSION_TARGET = {
    "repository": "bitcoin/bitcoin",
    "commit_sha": "0e9018e8b65611b0769545e177110e4b7fc51244",
    "run_id": "comprun_7cc47a5a81695fa452354479ea23b422",
    "role": "immutable_historical_regression",
    "source_bytes": 291_563_274,
}

QUALIFICATION_TARGET = {
    "repository": "bitcoin/bitcoin",
    "commit_sha": "bb5296576e8f1a9fc11c19d9a25ba02ed4547e24",
    "tree_sha": "186194c9de7f613d2d323db41cb8ce6bf1e3e549",
    "role": "provisional_qualification_revision",
    "access_mode": "anonymous_public",
    "tree_entries": 3248,
    "tree_blobs": 3031,
    "cpp_source_header_files": 1546,
    "summed_blob_bytes": 49_729_651,
    "tree_truncated": False,
}

UPSTREAM_DOCUMENT_BLOBS = {
    "doc/build-unix.md": "b1dd542291e3cbff7487c17865bef6975f2be794",
    "doc/dependencies.md": "23e307844acae91ddf6ea88cf53dfba5147fe5b3",
    "doc/fuzzing.md": "253f3f12ea23755047070ec94c362055f3389446",
}

PREPARATION_ANALYZERS = ("lizard_token_function_analysis", "cppcheck_standalone")
PREPARATION_FORBIDDEN_OPERATIONS = (
    "cmake_configure",
    "cmake_build",
    "compile_assessed_translation_units",
    "run_unit_or_functional_tests",
    "run_libfuzzer_or_afl_or_honggfuzz",
    "enable_address_undefined_memory_sanitizers",
    "download_qa_assets_corpus",
    "execute_assessed_binaries",
)

ORIGINAL_REQUIRED_EXECUTION = (
    "configuration_aware_static_analysis",
    "baseline_build",
    "unit_tests",
    "integration_tests",
    "sanitizer_checks",
    "bounded_fuzz",
)

# Official Bitcoin Core documentation at QUALIFICATION_TARGET.commit_sha.
# Informational only: NICO does not install or invoke this toolchain.
UPSTREAM_TOOLCHAIN_CONTEXT = {
    "cxx_standard": "c++20",
    "cmake_minimum": "3.22",
    "clang_minimum": "17.0",
    "gcc_minimum": "12.1",
    "recommended_compile_memory_bytes": 1_610_612_736,
    "default_generator": "cmake -B build",
    "wallet_flag": "ENABLE_WALLET",
    "fuzz_preset": "libfuzzer",
    "executed_by_nico": False,
}

ISOLATION_PROBE_ENVELOPE = {
    "cpu_max": "50000 100000",
    "memory_max_bytes": 268_435_456,
    "pids_max": 32,
    "external_network": False,
    "sufficient_for_upstream_compile": False,
}

SMALL_CONTROL = {
    "control_id": "owned_synthetic_cpp_fixture",
    "required_before_large_repository": True,
    "proof_tests": "tests/test_cpp_repository_capability.py",
    "status": "synthetic_regression_only",
    "cpp_build_verified": False,
}

REMAINING_UNPROVEN = tuple(f"C{index}" for index in range(20))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def frozen_contract() -> dict[str, Any]:
    """Return the preparation profile. Does not qualify C0 or execute a target."""
    budget = {
        "source_bytes": MAX_REPO_BYTES,
        "git_history_bytes": MAX_GIT_HISTORY_BYTES,
        "total_scan_timeout_seconds": TOTAL_SCAN_TIMEOUT_SECONDS,
        "tool_timeout_seconds": DEFAULT_TOOL_TIMEOUT_SECONDS,
        "aggregate_cost_usd": None,
        "aggregate_cost_status": "not_measured",
        "retry_limit": 0,
    }
    contract = {
        "contract_version": VERSION,
        "predicate": "C0",
        "status": "UNPROVEN",
        "preparation_status": "frozen_static_analysis_only",
        "original_required_execution": list(ORIGINAL_REQUIRED_EXECUTION),
        "qualification_target": deepcopy(QUALIFICATION_TARGET),
        "historical_regression_target": deepcopy(HISTORICAL_REGRESSION_TARGET),
        "preparation_configuration": {
            "analysis_method": "lizard_token_function_analysis",
            "optional_static_analyzer": "cppcheck_standalone",
            "analyzers": list(PREPARATION_ANALYZERS),
            "execution_proven": False,
            "cpp_build_verified": False,
            "configurations_evaluated": "none",
            "preprocessing_complete": False,
        },
        "preparation_forbidden_operations": list(PREPARATION_FORBIDDEN_OPERATIONS),
        "upstream_informational_toolchain": deepcopy(UPSTREAM_TOOLCHAIN_CONTEXT),
        "upstream_document_blobs": dict(UPSTREAM_DOCUMENT_BLOBS),
        "numeric_budget": budget,
        "isolation_probe_envelope": deepcopy(ISOLATION_PROBE_ENVELOPE),
        "small_control": deepcopy(SMALL_CONTROL),
        "remaining_predicates_unproven": list(REMAINING_UNPROVEN),
        "authorization": {
            "access_mode": "anonymous_public",
            "provider_credential_used": False,
            "independent_authorization_verification": "not_established",
            "client_delivery_allowed": False,
        },
    }
    _validate(contract)
    contract["contract_sha256"] = _sha256({key: value for key, value in contract.items() if key != "contract_sha256"})
    return contract


def _validate(contract: Mapping[str, Any]) -> None:
    if contract["status"] != "UNPROVEN":
        raise ValueError("preparation_must_not_qualify_c0")
    if contract["original_required_execution"] != list(ORIGINAL_REQUIRED_EXECUTION):
        raise ValueError("original_required_execution_must_remain_explicit")
    qualification = contract["qualification_target"]
    historical = contract["historical_regression_target"]
    if qualification["commit_sha"] == historical["commit_sha"]:
        raise ValueError("qualification_target_must_remain_distinct_from_historical_regression")
    if qualification["summed_blob_bytes"] > contract["numeric_budget"]["source_bytes"]:
        raise ValueError("qualification_source_exceeds_frozen_source_budget")
    if historical["source_bytes"] <= contract["numeric_budget"]["source_bytes"]:
        raise ValueError("historical_oversize_observation_must_remain_over_budget")
    if contract["preparation_configuration"]["cpp_build_verified"] is not False:
        raise ValueError("cpp_build_must_remain_unverified")
    if contract["upstream_informational_toolchain"]["executed_by_nico"] is not False:
        raise ValueError("upstream_toolchain_must_not_be_executed")
    if set(contract["preparation_configuration"]["analyzers"]) - set(PREPARATION_ANALYZERS):
        raise ValueError("unknown_nico_analyzer")
    missing = [item for item in PREPARATION_FORBIDDEN_OPERATIONS if item not in contract["preparation_forbidden_operations"]]
    if missing:
        raise ValueError("forbidden_operations_incomplete")
    envelope = contract["isolation_probe_envelope"]
    if envelope["memory_max_bytes"] >= contract["upstream_informational_toolchain"]["recommended_compile_memory_bytes"]:
        raise ValueError("isolation_envelope_must_remain_below_compile_requirement")
    if envelope["sufficient_for_upstream_compile"] is not False:
        raise ValueError("isolation_must_not_claim_compile_capacity")
    if contract["small_control"]["required_before_large_repository"] is not True:
        raise ValueError("small_control_gate_required")
    if contract["remaining_predicates_unproven"] != list(REMAINING_UNPROVEN):
        raise ValueError("c0_through_c19_must_remain_unproven")


def source_fits_budget(source_bytes: int, limit: int | None = None) -> bool:
    ceiling = MAX_REPO_BYTES if limit is None else limit
    return source_bytes <= ceiling


def authorize_large_repository_static_analysis(
    small_control_receipt: Mapping[str, Any],
    *,
    source_bytes: int,
    claimed_operations: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Check preparation eligibility only; this helper grants no run authority."""
    contract = frozen_contract()
    if small_control_receipt.get("cpp_files_analyzed", 0) < 1:
        raise ValueError("small_cpp_control_unproven")
    if small_control_receipt.get("cpp_build_verified") is not False:
        raise ValueError("small_control_must_not_claim_build_verification")
    if small_control_receipt.get("cpp_analysis_method") != "lizard_token_function_analysis":
        raise ValueError("small_control_requires_lizard_token_analysis")
    forbidden = [item for item in claimed_operations if item in contract["preparation_forbidden_operations"]]
    if forbidden:
        raise ValueError("forbidden_c_cpp_operation_requested")
    if not source_fits_budget(source_bytes, contract["numeric_budget"]["source_bytes"]):
        raise ValueError("repository_size_limit_exceeded")
    return {
        "authorized": False,
        "preparation_eligible": True,
        "authorization_status": "not_established_by_preparation",
        "mode": "static_analysis_only",
        "cpp_build_verified": False,
        "contract_sha256": contract["contract_sha256"],
        "qualification_commit_sha": contract["qualification_target"]["commit_sha"],
        "analyzers": list(contract["preparation_configuration"]["analyzers"]),
        "client_delivery_allowed": False,
    }
