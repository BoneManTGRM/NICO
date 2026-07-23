from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "branch_governance_issue.py"
SPEC = importlib.util.spec_from_file_location("nico_branch_governance_issue", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_dry_run_command_is_exact_and_bounded() -> None:
    assert MODULE.parse_cleanup_command("/branch-cleanup dry-run batch=99") == {
        "mode": "dry-run",
        "batch_size": 99,
        "manifest_sha256": "",
        "confirmation": "",
    }
    for body in (
        "/branch-cleanup dry-run batch=0",
        "/branch-cleanup dry-run batch=100",
        "/branch-cleanup dry-run batch=99 please",
    ):
        with pytest.raises(ValueError):
            MODULE.parse_cleanup_command(body)


def test_execute_requires_exact_hash_and_confirmation_token() -> None:
    digest = "a" * 64
    assert MODULE.parse_cleanup_command(
        f"/branch-cleanup execute batch=50 manifest={digest} confirm=DELETE_REVIEWED_MERGED_BRANCHES"
    ) == {
        "mode": "execute",
        "batch_size": 50,
        "manifest_sha256": digest,
        "confirmation": "DELETE REVIEWED MERGED BRANCHES",
    }
    for body in (
        f"/branch-cleanup execute batch=50 manifest={digest} confirm=DELETE_ALL",
        "/branch-cleanup execute batch=50 manifest=abc confirm=DELETE_REVIEWED_MERGED_BRANCHES",
        f"/branch-cleanup execute batch=100 manifest={digest} confirm=DELETE_REVIEWED_MERGED_BRANCHES",
    ):
        with pytest.raises(ValueError):
            MODULE.parse_cleanup_command(body)


def test_inventory_comment_preserves_truth_and_manifest_identity(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.json"
    manifest = tmp_path / "safe.txt"
    inventory.write_text(
        json.dumps(
            {
                "branch_count": 839,
                "classification_counts": {
                    "ACTIVE_DEFAULT": 1,
                    "MERGED_SAFE_TO_DELETE": 700,
                    "MANUAL_REVIEW": 138,
                },
                "records": [
                    {"branch": "agent/merged", "deletion_candidate": True},
                    {"branch": "agent/unique", "deletion_candidate": False},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest.write_text("agent/merged\n", encoding="utf-8")
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    body = MODULE.inventory_comment(inventory, manifest, "https://example.test/run")
    assert MODULE.INVENTORY_MARKER in body
    assert "Total remote branches: **839**" in body
    assert "Proven merged deletion candidates: **1**" in body
    assert digest in body
    assert "agent/merged" in body
    assert "agent/unique" not in body
    assert "/branch-cleanup dry-run batch=99" in body


def test_cleanup_comment_never_claims_deletion_without_result(tmp_path: Path) -> None:
    body = MODULE.cleanup_comment(tmp_path / "missing.json", "https://example.test/run", False)
    assert "failed before a result artifact" in body
    assert "No successful deletion result is claimed" in body


def test_dry_run_comment_emits_hash_bound_execution_command(tmp_path: Path) -> None:
    result = tmp_path / "result.json"
    digest = "b" * 64
    result.write_text(
        json.dumps(
            {
                "mode": "dry-run",
                "manifest_sha256": digest,
                "candidate_count": 99,
                "deleted": [],
            }
        ),
        encoding="utf-8",
    )
    body = MODULE.cleanup_comment(result, "https://example.test/run", True)
    assert "Branches deleted: **0**" in body
    assert f"manifest={digest}" in body
    assert "confirm=DELETE_REVIEWED_MERGED_BRANCHES" in body
