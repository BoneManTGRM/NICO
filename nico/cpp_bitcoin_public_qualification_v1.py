"""Public Bitcoin Core discovery. Completes the ChatGPT-blocked C0 task.

Grok reads the pinned public GitHub revision and official docs. This does not
compile, fuzz, sanitizer-instrument, or execute Bitcoin Core. ChatGPT's
cybersecurity flag is historical and is not a NICO or GitHub gate. The isolated
worker still cannot host upstream compile (256 MiB vs ~1.5 GiB).
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

from nico.cpp_large_repository_contract_v1 import (
    QUALIFICATION_TARGET,
    UPSTREAM_DOCUMENT_BLOBS,
    UPSTREAM_TOOLCHAIN_CONTEXT,
    frozen_contract,
)

VERSION = "nico.cpp_bitcoin_public_qualification.v1"

LICENSE_BLOB = {
    "path": "COPYING",
    "blob_sha": "89960cbf2f221a29852ed162b25bda2afc0b2dd6",
    "spdx": "MIT",
    "title": "The MIT License (MIT)",
}

DISCOVERED_BUILD = {
    "configure": "cmake -B build",
    "build": "cmake --build build",
    "wallet_flag": "ENABLE_WALLET",
    "fuzz_configure": "cmake --preset=libfuzzer",
    "fuzz_harness_dir": "src/test/fuzz",
    "qa_assets_repository": "bitcoin-core/qa-assets",
}

CHATGPT_FLAGS = {
    "bitcoin_build_test_discovery": "historical_chatgpt_only",
    "cloud_browser_reaccess": "historical_chatgpt_only",
    "openai_support_required": False,
    "current_nico_gate": False,
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def public_discovery_receipt() -> dict[str, Any]:
    """Return the frozen public discovery receipt. Does not clone Bitcoin Core."""
    contract = frozen_contract()
    envelope = contract["isolation_probe_envelope"]
    toolchain = deepcopy(UPSTREAM_TOOLCHAIN_CONTEXT)
    receipt = {
        "schema": VERSION,
        "predicate": "C0",
        "role": "public_toolchain_license_discovery",
        "discovery_status": "complete",
        "source_execution_status": "not_executed_envelope_insufficient",
        "chatgpt_platform_restriction": deepcopy(CHATGPT_FLAGS),
        "access_mode": "anonymous_public",
        "repository": QUALIFICATION_TARGET["repository"],
        "commit_sha": QUALIFICATION_TARGET["commit_sha"],
        "tree_sha": QUALIFICATION_TARGET["tree_sha"],
        "tree_entries": QUALIFICATION_TARGET["tree_entries"],
        "tree_blobs": QUALIFICATION_TARGET["tree_blobs"],
        "cpp_source_header_files": QUALIFICATION_TARGET["cpp_source_header_files"],
        "summed_blob_bytes": QUALIFICATION_TARGET["summed_blob_bytes"],
        "tree_truncated": QUALIFICATION_TARGET["tree_truncated"],
        "source_fits_budget": True,
        "document_blobs": dict(UPSTREAM_DOCUMENT_BLOBS),
        "license": deepcopy(LICENSE_BLOB),
        "discovered_build": deepcopy(DISCOVERED_BUILD),
        "discovered_toolchain": toolchain,
        "worker_memory_bytes": envelope["memory_max_bytes"],
        "recommended_compile_memory_bytes": toolchain["recommended_compile_memory_bytes"],
        "compile_fits_worker": False,
        "fuzz_fits_worker": False,
        "cloned": False,
        "compiled": False,
        "fuzzed": False,
        "sanitizer_executed_on_bitcoin": False,
        "qa_assets_downloaded": False,
        "overall_c0_status": contract["status"],
        "merge_blocked_by_chatgpt": False,
        "contract_sha256": contract["contract_sha256"],
    }
    _validate(receipt)
    receipt["receipt_sha256"] = _sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    return receipt


def _validate(receipt: Mapping[str, Any]) -> None:
    if receipt["discovery_status"] != "complete":
        raise ValueError("public_discovery_must_be_complete")
    if receipt["chatgpt_platform_restriction"]["openai_support_required"] is not False:
        raise ValueError("openai_support_must_not_block_discovery")
    if receipt["chatgpt_platform_restriction"]["current_nico_gate"] is not False:
        raise ValueError("chatgpt_flag_must_not_be_current_nico_gate")
    if receipt["merge_blocked_by_chatgpt"] is not False:
        raise ValueError("chatgpt_must_not_block_merge")
    if receipt["commit_sha"] != QUALIFICATION_TARGET["commit_sha"]:
        raise ValueError("qualification_identity_drift")
    if receipt["tree_sha"] != QUALIFICATION_TARGET["tree_sha"]:
        raise ValueError("qualification_identity_drift")
    if receipt["document_blobs"] != dict(UPSTREAM_DOCUMENT_BLOBS):
        raise ValueError("toolchain_document_identity_drift")
    if receipt["license"]["blob_sha"] != LICENSE_BLOB["blob_sha"]:
        raise ValueError("license_identity_drift")
    if receipt["license"]["spdx"] != "MIT":
        raise ValueError("license_must_remain_mit")
    if receipt["compiled"] is not False or receipt["fuzzed"] is not False:
        raise ValueError("discovery_must_not_execute_bitcoin")
    if receipt["qa_assets_downloaded"] is not False:
        raise ValueError("discovery_must_not_download_qa_assets")
    if receipt["compile_fits_worker"] is not False:
        raise ValueError("isolation_must_not_claim_compile_capacity")
    if receipt["worker_memory_bytes"] >= receipt["recommended_compile_memory_bytes"]:
        raise ValueError("isolation_envelope_must_remain_below_compile_requirement")
    if receipt["discovered_toolchain"]["executed_by_nico"] is not False:
        raise ValueError("upstream_toolchain_must_not_be_executed")
    if receipt["overall_c0_status"] != "UNPROVEN":
        raise ValueError("discovery_must_not_promote_c0")
    if receipt["source_execution_status"] != "not_executed_envelope_insufficient":
        raise ValueError("bitcoin_execution_must_remain_envelope_blocked")


def live_tree_matches_frozen(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Accept a live GitHub Trees API observation. Does not fetch source blobs."""
    expected = public_discovery_receipt()
    required = {
        "sha": expected["tree_sha"],
        "truncated": False,
        "tree_entries": expected["tree_entries"],
        "tree_blobs": expected["tree_blobs"],
        "cpp_source_header_files": expected["cpp_source_header_files"],
        "summed_blob_bytes": expected["summed_blob_bytes"],
    }
    mismatches = {
        key: {"expected": value, "observed": observation.get(key)}
        for key, value in required.items()
        if observation.get(key) != value
    }
    if mismatches:
        raise ValueError(f"live_tree_does_not_match_frozen:{sorted(mismatches)}")
    return {
        "schema": VERSION,
        "role": "live_public_tree_match",
        "matched": True,
        "tree_sha": expected["tree_sha"],
        "commit_sha": expected["commit_sha"],
        "chatgpt_platform_restriction": deepcopy(CHATGPT_FLAGS),
        "compiled": False,
        "receipt_sha256": expected["receipt_sha256"],
    }
