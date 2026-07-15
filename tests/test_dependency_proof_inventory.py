from __future__ import annotations

import json
from pathlib import Path

from nico.dependency_proof_inventory import _json_hash, build_dependency_proof_inventory
from nico.hosted_scanner_worker import _blocked_artifact


def test_dependency_proof_inventory_tracks_root_and_web_dependency_files(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("pytest==8.0.0\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "echo ok"}}), encoding="utf-8")
    web = tmp_path / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text(json.dumps({"scripts": {"lint": "next lint"}}), encoding="utf-8")
    (web / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3}), encoding="utf-8")

    tools = {
        "pip-audit": {"status": "completed", "returncode": 0, "timed_out": False, "findings": []},
        "npm-audit": {"status": "completed", "returncode": 0, "timed_out": False, "findings": []},
        "osv-scanner": {"status": "unavailable", "reason": "not installed", "findings": []},
    }

    inventory = build_dependency_proof_inventory(tmp_path, tools)

    assert inventory["artifact_schema"] == "nico.dependency_proof_inventory.v1"
    assert "requirements.txt" in inventory["existing_files"]
    assert "package.json" in inventory["existing_files"]
    assert "apps/web/package.json" in inventory["existing_files"]
    assert "apps/web/package-lock.json" in inventory["existing_files"]
    assert "package-lock.json" in inventory["missing_files"]
    assert inventory["completed_scanners"] == ["pip-audit", "npm-audit"]
    assert inventory["unavailable_scanners"] == ["osv-scanner"]
    assert inventory["current_run_evidence_complete"] is False
    assert inventory["inventory_hash"]
    for row in inventory["files"]:
        if row["exists"]:
            assert row["sha256"]
            assert row["bytes"] >= 0


def test_dependency_proof_inventory_marks_findings_and_completed_evidence(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("pytest==8.0.0\n", encoding="utf-8")
    tools = {
        "pip-audit": {"status": "completed", "returncode": 1, "timed_out": False, "findings": [{"id": "PYSEC-1"}]},
        "npm-audit": {"status": "completed", "returncode": 0, "timed_out": False, "findings": []},
        "osv-scanner": {"status": "completed", "returncode": 0, "timed_out": False, "findings": []},
    }

    inventory = build_dependency_proof_inventory(tmp_path, tools)

    assert inventory["current_run_evidence_complete"] is True
    assert inventory["finding_scanners"] == ["pip-audit"]
    pip = next(item for item in inventory["scanner_tools"] if item["tool"] == "pip-audit")
    assert pip["finding_count"] == 1
    assert pip["artifact_hash"]


def test_dependency_proof_hash_is_deterministic_for_self_referential_scanner_payload(tmp_path: Path) -> None:
    tool: dict[str, object] = {
        "status": "completed",
        "returncode": 0,
        "timed_out": False,
        "findings": [],
    }
    tool["self"] = tool
    tools = {
        "pip-audit": tool,
        "npm-audit": {"status": "completed", "returncode": 0, "timed_out": False, "findings": []},
        "osv-scanner": {"status": "completed", "returncode": 0, "timed_out": False, "findings": []},
    }

    first = build_dependency_proof_inventory(tmp_path, tools)
    second = build_dependency_proof_inventory(tmp_path, tools)
    pip_first = next(item for item in first["scanner_tools"] if item["tool"] == "pip-audit")
    pip_second = next(item for item in second["scanner_tools"] if item["tool"] == "pip-audit")

    assert len(pip_first["artifact_hash"]) == 64
    assert pip_first["artifact_hash"] == pip_second["artifact_hash"]
    assert first["inventory_hash"] == second["inventory_hash"]
    assert first["current_run_evidence_complete"] is True


def test_dependency_proof_hash_handles_self_referential_lists_and_non_finite_floats() -> None:
    values: list[object] = [float("nan"), float("inf"), float("-inf")]
    values.append(values)

    first = _json_hash(values)
    second = _json_hash(values)

    assert len(first) == 64
    assert first == second


def test_blocked_hosted_worker_artifact_keeps_dependency_proof_unavailable() -> None:
    artifact = _blocked_artifact({"repository": "BoneManTGRM/NICO"}, "not authorized")

    proof = artifact["dependency_proof"]
    assert proof["artifact_schema"] == "nico.dependency_proof_inventory.v1"
    assert proof["existing_files"] == []
    assert set(proof["unavailable_scanners"]) == {"pip-audit", "npm-audit", "osv-scanner"}
    assert proof["current_run_evidence_complete"] is False
