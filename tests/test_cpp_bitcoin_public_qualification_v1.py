"""Public Bitcoin discovery completes without ChatGPT or Bitcoin execution."""
from copy import deepcopy

import pytest

from nico.cpp_bitcoin_public_qualification_v1 import (
    CHATGPT_FLAGS,
    LICENSE_BLOB,
    live_tree_matches_frozen,
    public_discovery_receipt,
)
from nico.cpp_large_repository_contract_v1 import (
    QUALIFICATION_TARGET,
    UPSTREAM_DOCUMENT_BLOBS,
    frozen_contract,
)


def test_public_discovery_is_complete_and_stable():
    first = public_discovery_receipt()
    second = public_discovery_receipt()
    assert first["schema"].endswith(".v1")
    assert first["discovery_status"] == "complete"
    assert first["receipt_sha256"] == second["receipt_sha256"]
    assert len(first["receipt_sha256"]) == 64
    assert first["contract_sha256"] == frozen_contract()["contract_sha256"]
    assert first["overall_c0_status"] == "UNPROVEN"


def test_chatgpt_flags_are_historical_and_do_not_block_merge():
    receipt = public_discovery_receipt()
    flags = receipt["chatgpt_platform_restriction"]
    assert flags == CHATGPT_FLAGS
    assert flags["openai_support_required"] is False
    assert flags["current_nico_gate"] is False
    assert receipt["merge_blocked_by_chatgpt"] is False
    assert flags["bitcoin_build_test_discovery"] == "historical_chatgpt_only"
    assert flags["cloud_browser_reaccess"] == "historical_chatgpt_only"


def test_pinned_public_identity_and_official_docs():
    receipt = public_discovery_receipt()
    assert receipt["commit_sha"] == QUALIFICATION_TARGET["commit_sha"]
    assert receipt["tree_sha"] == QUALIFICATION_TARGET["tree_sha"]
    assert receipt["tree_entries"] == 3248
    assert receipt["tree_blobs"] == 3031
    assert receipt["cpp_source_header_files"] == 1546
    assert receipt["summed_blob_bytes"] == 49_729_651
    assert receipt["document_blobs"] == dict(UPSTREAM_DOCUMENT_BLOBS)
    assert receipt["license"] == LICENSE_BLOB
    assert receipt["license"]["spdx"] == "MIT"
    assert receipt["discovered_build"]["configure"] == "cmake -B build"
    assert receipt["discovered_build"]["fuzz_configure"] == "cmake --preset=libfuzzer"
    assert receipt["discovered_toolchain"]["gcc_minimum"] == "12.1"
    assert receipt["discovered_toolchain"]["cmake_minimum"] == "3.22"


def test_discovery_does_not_compile_or_fuzz_bitcoin():
    receipt = public_discovery_receipt()
    assert receipt["cloned"] is False
    assert receipt["compiled"] is False
    assert receipt["fuzzed"] is False
    assert receipt["sanitizer_executed_on_bitcoin"] is False
    assert receipt["qa_assets_downloaded"] is False
    assert receipt["compile_fits_worker"] is False
    assert receipt["fuzz_fits_worker"] is False
    assert receipt["worker_memory_bytes"] == 268_435_456
    assert receipt["recommended_compile_memory_bytes"] == 1_610_612_736
    assert receipt["source_execution_status"] == "not_executed_envelope_insufficient"
    assert receipt["discovered_toolchain"]["executed_by_nico"] is False


def test_live_tree_observation_matches_frozen_identity():
    matched = live_tree_matches_frozen({
        "sha": QUALIFICATION_TARGET["tree_sha"],
        "truncated": False,
        "tree_entries": 3248,
        "tree_blobs": 3031,
        "cpp_source_header_files": 1546,
        "summed_blob_bytes": 49_729_651,
    })
    assert matched["matched"] is True
    assert matched["compiled"] is False
    assert matched["chatgpt_platform_restriction"]["openai_support_required"] is False


def test_live_tree_rejects_identity_drift():
    with pytest.raises(ValueError, match="live_tree_does_not_match_frozen"):
        live_tree_matches_frozen({
            "sha": QUALIFICATION_TARGET["tree_sha"],
            "truncated": True,
            "tree_entries": 3248,
            "tree_blobs": 3031,
            "cpp_source_header_files": 1546,
            "summed_blob_bytes": 49_729_651,
        })


def test_receipt_rejects_compile_claim_and_openai_gate():
    receipt = public_discovery_receipt()
    bad = deepcopy(receipt)
    del bad["receipt_sha256"]
    bad["compiled"] = True
    with pytest.raises(ValueError, match="discovery_must_not_execute_bitcoin"):
        from nico.cpp_bitcoin_public_qualification_v1 import _validate
        _validate(bad)
    bad = deepcopy(receipt)
    del bad["receipt_sha256"]
    bad["chatgpt_platform_restriction"]["openai_support_required"] = True
    with pytest.raises(ValueError, match="openai_support_must_not_block_discovery"):
        from nico.cpp_bitcoin_public_qualification_v1 import _validate
        _validate(bad)
    bad = deepcopy(receipt)
    del bad["receipt_sha256"]
    bad["merge_blocked_by_chatgpt"] = True
    with pytest.raises(ValueError, match="chatgpt_must_not_block_merge"):
        from nico.cpp_bitcoin_public_qualification_v1 import _validate
        _validate(bad)
