"""C0 static-analysis contract: no compile, fuzz, or sanitizer execution."""
from copy import deepcopy

import pytest

from nico.cpp_large_repository_contract_v1 import (
    HISTORICAL_REGRESSION_TARGET,
    NICO_FORBIDDEN_OPERATIONS,
    QUALIFICATION_TARGET,
    authorize_large_repository_static_analysis,
    frozen_contract,
    source_fits_budget,
)
from nico.full_assessment_complexity_evidence import collect_complexity_evidence
from nico.scanner_worker import MAX_REPO_BYTES


def _small_control():
    measured = collect_complexity_evidence({
        "src/value.cpp": "int value(int x) { if (x > 1) return x; return 0; }\n",
        "include/value.hpp": "int value(int x);\n",
    })
    assert measured["cpp_files_analyzed"] == 2
    assert measured["cpp_build_verified"] is False
    return measured


def test_c0_contract_is_complete_and_stable():
    first = frozen_contract()
    second = frozen_contract()
    assert first["predicate"] == "C0"
    assert first["status"] == "frozen_static_analysis_only"
    assert first["contract_sha256"] == second["contract_sha256"]
    assert len(first["contract_sha256"]) == 64
    required = {
        "qualification_target", "historical_regression_target",
        "nico_executed_configuration", "nico_forbidden_operations",
        "upstream_informational_toolchain", "numeric_budget",
        "isolation_probe_envelope", "small_control",
        "remaining_predicates_unproven", "authorization",
    }
    assert required <= first.keys()
    assert first["remaining_predicates_unproven"] == [f"C{index}" for index in range(1, 20)]
    assert "C0" not in first["remaining_predicates_unproven"]


def test_qualification_target_stays_distinct_from_immutable_history():
    contract = frozen_contract()
    assert contract["qualification_target"]["commit_sha"] == QUALIFICATION_TARGET["commit_sha"]
    assert contract["historical_regression_target"]["commit_sha"] == HISTORICAL_REGRESSION_TARGET["commit_sha"]
    assert contract["qualification_target"]["commit_sha"] != contract["historical_regression_target"]["commit_sha"]
    assert contract["historical_regression_target"]["run_id"] == "comprun_7cc47a5a81695fa452354479ea23b422"


def test_nico_does_not_claim_build_fuzz_or_sanitizer_execution():
    contract = frozen_contract()
    config = contract["nico_executed_configuration"]
    assert config["cpp_build_verified"] is False
    assert config["preprocessing_complete"] is False
    assert config["configurations_evaluated"] == "none"
    assert config["analyzers"] == ["lizard_token_function_analysis", "cppcheck_standalone"]
    assert set(NICO_FORBIDDEN_OPERATIONS) <= set(contract["nico_forbidden_operations"])
    toolchain = contract["upstream_informational_toolchain"]
    assert toolchain["executed_by_nico"] is False
    assert toolchain["cmake_minimum"] == "3.22"
    assert toolchain["clang_minimum"] == "17.0"
    assert toolchain["gcc_minimum"] == "12.1"
    assert toolchain["cxx_standard"] == "c++20"


def test_pinned_source_fits_budget_and_historical_oversize_does_not():
    contract = frozen_contract()
    limit = contract["numeric_budget"]["source_bytes"]
    assert limit == MAX_REPO_BYTES == 150_000_000
    assert source_fits_budget(QUALIFICATION_TARGET["summed_blob_bytes"])
    assert not source_fits_budget(HISTORICAL_REGRESSION_TARGET["source_bytes"])
    assert QUALIFICATION_TARGET["summed_blob_bytes"] < limit
    assert HISTORICAL_REGRESSION_TARGET["source_bytes"] > limit


def test_isolation_envelope_cannot_host_upstream_compile():
    contract = frozen_contract()
    envelope = contract["isolation_probe_envelope"]
    compile_need = contract["upstream_informational_toolchain"]["recommended_compile_memory_bytes"]
    assert envelope["memory_max_bytes"] == 268_435_456
    assert envelope["memory_max_bytes"] < compile_need
    assert envelope["sufficient_for_upstream_compile"] is False
    assert envelope["external_network"] is False


def test_small_control_authorizes_static_analysis_only():
    receipt = authorize_large_repository_static_analysis(
        _small_control(),
        source_bytes=QUALIFICATION_TARGET["summed_blob_bytes"],
    )
    assert receipt["authorized"] is True
    assert receipt["mode"] == "static_analysis_only"
    assert receipt["cpp_build_verified"] is False
    assert receipt["client_delivery_allowed"] is False
    assert receipt["qualification_commit_sha"] == QUALIFICATION_TARGET["commit_sha"]
    assert receipt["contract_sha256"] == frozen_contract()["contract_sha256"]


def test_missing_small_control_blocks_large_repository():
    with pytest.raises(ValueError, match="small_cpp_control_unproven"):
        authorize_large_repository_static_analysis(
            {"cpp_files_analyzed": 0, "cpp_build_verified": False,
             "cpp_analysis_method": "lizard_token_function_analysis"},
            source_bytes=100,
        )


def test_build_claim_on_small_control_is_rejected():
    measured = deepcopy(_small_control())
    measured["cpp_build_verified"] = True
    with pytest.raises(ValueError, match="must_not_claim_build_verification"):
        authorize_large_repository_static_analysis(measured, source_bytes=100)


@pytest.mark.parametrize("operation", [
    "cmake_build",
    "run_libfuzzer_or_afl_or_honggfuzz",
    "enable_address_undefined_memory_sanitizers",
    "execute_assessed_binaries",
])
def test_forbidden_operations_cannot_be_authorized(operation):
    with pytest.raises(ValueError, match="forbidden_c_cpp_operation_requested"):
        authorize_large_repository_static_analysis(
            _small_control(),
            source_bytes=QUALIFICATION_TARGET["summed_blob_bytes"],
            claimed_operations=[operation],
        )


def test_historical_oversize_population_is_not_authorized():
    with pytest.raises(ValueError, match="repository_size_limit_exceeded"):
        authorize_large_repository_static_analysis(
            _small_control(),
            source_bytes=HISTORICAL_REGRESSION_TARGET["source_bytes"],
        )


def test_authorization_does_not_imply_delivery_or_credential_use():
    contract = frozen_contract()
    assert contract["authorization"]["provider_credential_used"] is False
    assert contract["authorization"]["independent_authorization_verification"] == "not_established"
    assert contract["authorization"]["client_delivery_allowed"] is False
    assert contract["authorization"]["access_mode"] == "anonymous_public"
