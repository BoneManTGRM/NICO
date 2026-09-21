"""C1 acquisition receipts: owned synthetic control plus frozen public inventory.

Does not clone, compile, fuzz, or sanitizer-instrument Bitcoin Core. Qualification
inventory is retained preparation context, not completed C0 qualification. Blob
contents are not fetched. Overall C1 remains UNPROVEN until those blobs exist
under the same population contract.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from nico.cpp_large_repository_contract_v1 import (
    HISTORICAL_REGRESSION_TARGET,
    QUALIFICATION_TARGET,
    authorize_large_repository_static_analysis,
    frozen_contract,
    source_fits_budget,
)
from nico.full_assessment_complexity_evidence import collect_complexity_evidence
from nico.scanner_worker import MAX_GIT_HISTORY_BYTES, MAX_REPO_BYTES, repository_size_observation

VERSION = "nico.cpp_large_repository_acquisition.v2"

OWNED_SYNTHETIC_FILES = {
    "src/value.cpp": "int value(int x) { if (x > 1) return x; return 0; }\n",
    "include/value.hpp": "int value(int x);\n",
}

OVERALL_C1_STATUS = "unproven_blobs_not_fetched"
ACCEPTED_SUBPROOF = "synthetic_control_and_frozen_public_tree_inventory"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def write_owned_synthetic_control(root: Path) -> dict[str, str]:
    """Materialize the owned C/C++ fixture. Never writes third-party source."""
    written: dict[str, str] = {}
    for relative, text in OWNED_SYNTHETIC_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written[relative] = text
    return written


def acquire_owned_synthetic_control(root: Path) -> dict[str, Any]:
    """Inventory and statically measure the owned fixture. No compile, no Bitcoin."""
    files = write_owned_synthetic_control(root)
    size = repository_size_observation(root, source_limit=MAX_REPO_BYTES, history_limit=MAX_GIT_HISTORY_BYTES)
    measured = collect_complexity_evidence(files)
    if measured.get("cpp_files_analyzed", 0) < 1:
        raise ValueError("small_cpp_control_unproven")
    if measured.get("cpp_build_verified") is not False:
        raise ValueError("small_control_must_not_claim_build_verification")
    if measured.get("cpp_analysis_method") != "lizard_token_function_analysis":
        raise ValueError("small_control_requires_lizard_token_analysis")
    if not size.get("inventory_complete"):
        raise ValueError("synthetic_control_inventory_incomplete")
    if size.get("external_symlink_targets_read") is not False:
        raise ValueError("synthetic_control_must_not_follow_external_symlinks")
    receipt = {
        "schema": VERSION,
        "predicate": "C1",
        "role": "synthetic_control",
        "control_id": "owned_synthetic_cpp_fixture",
        "repository": "nico/owned-synthetic-cpp-fixture",
        "cloned": False,
        "blobs_fetched": True,
        "compiled": False,
        "fuzzed": False,
        "source_bytes": size["source_bytes"],
        "git_history_bytes": size["git_history_bytes"],
        "source_byte_limit": size["source_byte_limit"],
        "git_history_byte_limit": size["git_history_byte_limit"],
        "exceeded_limits": list(size["exceeded_limits"]),
        "inventory_complete": True,
        "symlink_count": size["symlink_count"],
        "external_symlink_targets_read": False,
        "byte_count_scope": size["byte_count_scope"],
        "cpp_files_analyzed": measured["cpp_files_analyzed"],
        "cpp_analysis_method": measured["cpp_analysis_method"],
        "cpp_build_verified": False,
        "functions_measured": measured["functions_measured"],
        "analyzed_source_paths": list(measured["analyzed_source_paths"]),
        "source_fits_budget": source_fits_budget(size["source_bytes"]),
        "contract_sha256": frozen_contract()["contract_sha256"],
    }
    receipt["receipt_sha256"] = _sha256(receipt)
    return receipt


def frozen_qualification_inventory() -> dict[str, Any]:
    """Public Git tree identity from C0. Does not clone or fetch blob contents."""
    target = deepcopy(QUALIFICATION_TARGET)
    contract = frozen_contract()
    receipt = {
        "schema": VERSION,
        "predicate": "C1",
        "role": "qualification_inventory",
        "status": "frozen_public_tree_inventory_blobs_not_fetched",
        "repository": target["repository"],
        "commit_sha": target["commit_sha"],
        "tree_sha": target["tree_sha"],
        "tree_entries": target["tree_entries"],
        "tree_blobs": target["tree_blobs"],
        "cpp_source_header_files": target["cpp_source_header_files"],
        "summed_blob_bytes": target["summed_blob_bytes"],
        "tree_truncated": target["tree_truncated"],
        "access_mode": target["access_mode"],
        "inventory_method": "github_git_trees_api_at_frozen_revision",
        "cloned": False,
        "blobs_fetched": False,
        "compiled": False,
        "fuzzed": False,
        "source_bytes": target["summed_blob_bytes"],
        "source_byte_limit": contract["numeric_budget"]["source_bytes"],
        "git_history_byte_limit": contract["numeric_budget"]["git_history_bytes"],
        "source_fits_budget": source_fits_budget(target["summed_blob_bytes"]),
        "inventory_complete": False,
        "complete_reason": "public_tree_identity_frozen_blob_contents_not_fetched",
        "external_symlink_targets_read": False,
        "contract_sha256": contract["contract_sha256"],
    }
    receipt["receipt_sha256"] = _sha256(receipt)
    return receipt


def historical_regression_block() -> dict[str, Any]:
    """Immutable oversize observation. Not re-acquired and not authorized."""
    historical = deepcopy(HISTORICAL_REGRESSION_TARGET)
    receipt = {
        "schema": VERSION,
        "predicate": "C1",
        "role": "historical_regression",
        "status": "blocked_over_source_budget",
        "repository": historical["repository"],
        "commit_sha": historical["commit_sha"],
        "run_id": historical["run_id"],
        "source_bytes": historical["source_bytes"],
        "source_fits_budget": False,
        "cloned": False,
        "blobs_fetched": False,
        "compiled": False,
        "authorized": False,
        "contract_sha256": frozen_contract()["contract_sha256"],
    }
    receipt["receipt_sha256"] = _sha256(receipt)
    return receipt


def validate_c1_population_contract(
    small_control: Mapping[str, Any],
    inventory: Mapping[str, Any] | None = None,
    historical: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Accept the synthetic-control subproof. Do not claim Bitcoin acquisition."""
    inventory = frozen_qualification_inventory() if inventory is None else dict(inventory)
    historical = historical_regression_block() if historical is None else dict(historical)
    if small_control.get("role") != "synthetic_control":
        raise ValueError("c1_requires_synthetic_control_receipt")
    if small_control.get("cpp_files_analyzed", 0) < 1:
        raise ValueError("small_cpp_control_unproven")
    if small_control.get("cpp_build_verified") is not False:
        raise ValueError("small_control_must_not_claim_build_verification")
    if small_control.get("compiled") is not False:
        raise ValueError("c1_must_not_compile_control")
    if small_control.get("inventory_complete") is not True:
        raise ValueError("synthetic_control_inventory_incomplete")
    if inventory.get("cloned") is not False or inventory.get("blobs_fetched") is not False:
        raise ValueError("qualification_inventory_must_not_clone_or_fetch_blobs")
    if inventory.get("compiled") is not False:
        raise ValueError("c1_must_not_compile_qualification_target")
    if inventory.get("commit_sha") != QUALIFICATION_TARGET["commit_sha"]:
        raise ValueError("qualification_inventory_identity_drift")
    if inventory.get("commit_sha") == historical.get("commit_sha"):
        raise ValueError("qualification_target_must_remain_distinct_from_historical_regression")
    if historical.get("source_fits_budget") is not False:
        raise ValueError("historical_oversize_observation_must_remain_over_budget")
    if historical.get("authorized") is not False:
        raise ValueError("historical_regression_must_remain_unauthorized")
    eligibility = authorize_large_repository_static_analysis(
        {
            "cpp_files_analyzed": small_control["cpp_files_analyzed"],
            "cpp_build_verified": False,
            "cpp_analysis_method": small_control["cpp_analysis_method"],
        },
        source_bytes=inventory["source_bytes"],
    )
    summary = {
        "schema": VERSION,
        "predicate": "C1",
        "overall_status": OVERALL_C1_STATUS,
        "accepted_subproof": ACCEPTED_SUBPROOF,
        "synthetic_control_receipt_sha256": small_control.get("receipt_sha256"),
        "qualification_inventory_receipt_sha256": inventory.get("receipt_sha256"),
        "historical_block_receipt_sha256": historical.get("receipt_sha256"),
        "preparation_mode": eligibility["mode"],
        "assessment_authorized": eligibility["authorized"],
        "authorization_status": eligibility["authorization_status"],
        "cpp_build_verified": False,
        "client_delivery_allowed": False,
        "cloned_qualification_target": False,
        "remaining_predicates_unproven": list(frozen_contract()["remaining_predicates_unproven"]),
        "contract_sha256": frozen_contract()["contract_sha256"],
    }
    if "C0" not in summary["remaining_predicates_unproven"]:
        raise ValueError("preparation_must_not_qualify_c0")
    if "C1" not in summary["remaining_predicates_unproven"]:
        raise ValueError("c1_must_remain_unproven_until_blobs_are_fetched")
    summary["summary_sha256"] = _sha256(summary)
    return summary
