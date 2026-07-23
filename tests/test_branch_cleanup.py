from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "branch_cleanup.py"
SPEC = importlib.util.spec_from_file_location("nico_branch_cleanup", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    inventory = tmp_path / "branch-inventory.json"
    manifest = tmp_path / "safe-delete-branches.txt"
    inventory.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "branch": "agent/merged",
                        "head_sha": "a" * 40,
                        "classification": "MERGED_SAFE_TO_DELETE",
                        "deletion_candidate": True,
                    },
                    {
                        "branch": "agent/unique",
                        "head_sha": "b" * 40,
                        "classification": "STALE_WITH_UNMERGED_COMMITS",
                        "deletion_candidate": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest.write_text("agent/merged\n", encoding="utf-8")
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    return inventory, manifest, digest


def test_dry_run_never_calls_live_validation_or_deletion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inventory, manifest, digest = write_fixture(tmp_path)
    monkeypatch.setattr(MODULE, "validate_live_candidate", lambda *args, **kwargs: pytest.fail("live validation"))
    monkeypatch.setattr(MODULE, "delete_branch", lambda *args, **kwargs: pytest.fail("delete"))
    result = MODULE.execute(
        repository="owner/repo",
        token="",
        inventory_path=inventory,
        manifest_path=manifest,
        expected_manifest_sha256=digest,
        mode="dry-run",
        confirmation="",
        batch_size=100,
        output_path=tmp_path / "result.json",
    )
    assert result["deleted"] == []
    assert result["validated"] == [{"branch": "agent/merged", "head_sha": "a" * 40}]


def test_execute_requires_exact_confirmation(tmp_path: Path) -> None:
    inventory, manifest, digest = write_fixture(tmp_path)
    with pytest.raises(ValueError, match="confirmation"):
        MODULE.execute(
            repository="owner/repo",
            token="token",
            inventory_path=inventory,
            manifest_path=manifest,
            expected_manifest_sha256=digest,
            mode="execute",
            confirmation="DELETE EVERYTHING",
            batch_size=100,
            output_path=tmp_path / "result.json",
        )


def test_execute_requires_reviewed_manifest_hash(tmp_path: Path) -> None:
    inventory, manifest, _ = write_fixture(tmp_path)
    with pytest.raises(ValueError, match="hash mismatch"):
        MODULE.execute(
            repository="owner/repo",
            token="token",
            inventory_path=inventory,
            manifest_path=manifest,
            expected_manifest_sha256="0" * 64,
            mode="execute",
            confirmation=MODULE.CONFIRMATION_PHRASE,
            batch_size=100,
            output_path=tmp_path / "result.json",
        )


def test_manifest_cannot_promote_unmerged_branch(tmp_path: Path) -> None:
    inventory, manifest, _ = write_fixture(tmp_path)
    manifest.write_text("agent/unique\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not proven safe"):
        MODULE.load_candidates(inventory, manifest)


def test_execute_revalidates_before_each_delete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inventory, manifest, digest = write_fixture(tmp_path)
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        MODULE,
        "validate_live_candidate",
        lambda repository, token, candidate: calls.append(("validate", candidate.branch)),
    )
    monkeypatch.setattr(
        MODULE,
        "delete_branch",
        lambda repository, token, branch: calls.append(("delete", branch)),
    )
    result = MODULE.execute(
        repository="owner/repo",
        token="token",
        inventory_path=inventory,
        manifest_path=manifest,
        expected_manifest_sha256=digest,
        mode="execute",
        confirmation=MODULE.CONFIRMATION_PHRASE,
        batch_size=100,
        output_path=tmp_path / "result.json",
    )
    assert calls == [("validate", "agent/merged"), ("delete", "agent/merged")]
    assert result["deleted"] == ["agent/merged"]
