"""C1 acquisition subproof: owned fixture only. No Bitcoin clone or compile."""
from pathlib import Path

import pytest

from nico.cpp_large_repository_acquisition_v1 import (
    ACCEPTED_SUBPROOF,
    OVERALL_C1_STATUS,
    OWNED_SYNTHETIC_FILES,
    acquire_owned_synthetic_control,
    frozen_qualification_inventory,
    historical_regression_block,
    validate_c1_population_contract,
    write_owned_synthetic_control,
)
from nico.cpp_large_repository_contract_v1 import (
    HISTORICAL_REGRESSION_TARGET,
    QUALIFICATION_TARGET,
    frozen_contract,
)


def test_owned_synthetic_control_is_inventoried_and_measured(tmp_path: Path):
    receipt = acquire_owned_synthetic_control(tmp_path)
    assert receipt["predicate"] == "C1"
    assert receipt["role"] == "synthetic_control"
    assert receipt["cloned"] is False
    assert receipt["compiled"] is False
    assert receipt["fuzzed"] is False
    assert receipt["blobs_fetched"] is True
    assert receipt["inventory_complete"] is True
    assert receipt["cpp_files_analyzed"] == 2
    assert receipt["functions_measured"] == 1
    assert receipt["cpp_analysis_method"] == "lizard_token_function_analysis"
    assert receipt["cpp_build_verified"] is False
    assert receipt["source_fits_budget"] is True
    assert receipt["source_bytes"] > 0
    assert receipt["source_bytes"] < 1000
    assert receipt["exceeded_limits"] == []
    assert receipt["external_symlink_targets_read"] is False
    assert set(receipt["analyzed_source_paths"]) == set(OWNED_SYNTHETIC_FILES)
    assert receipt["contract_sha256"] == frozen_contract()["contract_sha256"]
    assert len(receipt["receipt_sha256"]) == 64


def test_qualification_inventory_is_frozen_public_identity_without_clone():
    receipt = frozen_qualification_inventory()
    assert receipt["predicate"] == "C1"
    assert receipt["role"] == "qualification_inventory"
    assert receipt["cloned"] is False
    assert receipt["blobs_fetched"] is False
    assert receipt["compiled"] is False
    assert receipt["inventory_complete"] is False
    assert receipt["commit_sha"] == QUALIFICATION_TARGET["commit_sha"]
    assert receipt["tree_sha"] == QUALIFICATION_TARGET["tree_sha"]
    assert receipt["tree_blobs"] == 3031
    assert receipt["cpp_source_header_files"] == 1546
    assert receipt["summed_blob_bytes"] == 49_729_651
    assert receipt["source_fits_budget"] is True
    assert receipt["access_mode"] == "anonymous_public"
    assert receipt["inventory_method"] == "github_git_trees_api_at_frozen_revision"
    assert receipt["contract_sha256"] == frozen_contract()["contract_sha256"]


def test_historical_oversize_population_stays_blocked():
    receipt = historical_regression_block()
    assert receipt["role"] == "historical_regression"
    assert receipt["authorized"] is False
    assert receipt["cloned"] is False
    assert receipt["source_fits_budget"] is False
    assert receipt["commit_sha"] == HISTORICAL_REGRESSION_TARGET["commit_sha"]
    assert receipt["run_id"] == "comprun_7cc47a5a81695fa452354479ea23b422"
    assert receipt["source_bytes"] == 291_563_274
    assert receipt["commit_sha"] != QUALIFICATION_TARGET["commit_sha"]


def test_c1_population_contract_accepts_synthetic_subproof_only(tmp_path: Path):
    summary = validate_c1_population_contract(acquire_owned_synthetic_control(tmp_path))
    assert summary["predicate"] == "C1"
    assert summary["overall_status"] == OVERALL_C1_STATUS == "unproven_blobs_not_fetched"
    assert summary["accepted_subproof"] == ACCEPTED_SUBPROOF
    assert summary["preparation_mode"] == "static_analysis_only"
    assert summary["assessment_authorized"] is False
    assert summary["authorization_status"] == "not_established_by_preparation"
    assert summary["cpp_build_verified"] is False
    assert summary["client_delivery_allowed"] is False
    assert summary["cloned_qualification_target"] is False
    assert summary["remaining_predicates_unproven"][0] == "C0"
    assert summary["remaining_predicates_unproven"] == [f"C{index}" for index in range(20)]
    assert "C1" in summary["remaining_predicates_unproven"]
    assert summary["contract_sha256"] == frozen_contract()["contract_sha256"]


def test_c1_rejects_missing_synthetic_control():
    with pytest.raises(ValueError, match="c1_requires_synthetic_control_receipt"):
        validate_c1_population_contract({"role": "qualification_inventory", "cpp_files_analyzed": 2})


def test_c1_rejects_compile_claim_on_control(tmp_path: Path):
    receipt = acquire_owned_synthetic_control(tmp_path)
    receipt["compiled"] = True
    with pytest.raises(ValueError, match="c1_must_not_compile_control"):
        validate_c1_population_contract(receipt)


def test_c1_rejects_cloned_or_fetched_qualification_inventory(tmp_path: Path):
    control = acquire_owned_synthetic_control(tmp_path)
    inventory = frozen_qualification_inventory()
    inventory["cloned"] = True
    with pytest.raises(ValueError, match="must_not_clone_or_fetch_blobs"):
        validate_c1_population_contract(control, inventory=inventory)
    inventory = frozen_qualification_inventory()
    inventory["blobs_fetched"] = True
    with pytest.raises(ValueError, match="must_not_clone_or_fetch_blobs"):
        validate_c1_population_contract(control, inventory=inventory)


def test_c1_rejects_qualification_identity_drift(tmp_path: Path):
    inventory = frozen_qualification_inventory()
    inventory["commit_sha"] = HISTORICAL_REGRESSION_TARGET["commit_sha"]
    with pytest.raises(ValueError, match="identity_drift"):
        validate_c1_population_contract(acquire_owned_synthetic_control(tmp_path), inventory=inventory)


def test_c1_does_not_write_bitcoin_paths(tmp_path: Path):
    written = write_owned_synthetic_control(tmp_path)
    assert written == OWNED_SYNTHETIC_FILES
    paths = {path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file()}
    assert paths == set(OWNED_SYNTHETIC_FILES)
    assert not any("bitcoin" in path.lower() for path in paths)
