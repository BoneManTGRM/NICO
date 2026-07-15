from __future__ import annotations

from nico.scanner_worker_orchestration import build_scanner_worker_orchestration_manifest, stable_artifact_hash


def test_stable_artifact_hash_is_order_independent() -> None:
    left = {"b": 2, "a": 1}
    right = {"a": 1, "b": 2}

    assert stable_artifact_hash(left) == stable_artifact_hash(right)


def test_stable_artifact_hash_handles_circular_scanner_payloads() -> None:
    payload: dict[str, object] = {"status": "completed", "findings": []}
    payload["self"] = payload

    first = stable_artifact_hash(payload)
    second = stable_artifact_hash(payload)

    assert len(first) == 64
    assert first == second


def test_orchestration_manifest_lists_every_required_tool() -> None:
    artifact = {
        "tools": {
            "pip-audit": {
                "tool": "pip-audit",
                "status": "completed",
                "category": "dependency",
                "returncode": 0,
                "timed_out": False,
                "findings": [],
            },
            "bandit": {
                "tool": "bandit",
                "status": "completed",
                "category": "static",
                "returncode": 1,
                "timed_out": False,
                "findings": [{"issue_text": "example"}],
            },
            "trufflehog": {
                "tool": "trufflehog",
                "status": "unavailable",
                "category": "secret",
                "reason": "trufflehog is not installed in the worker image",
                "findings": [],
                "scans_git_history": True,
            },
        }
    }

    manifest = build_scanner_worker_orchestration_manifest(
        artifact,
        repository="BoneManTGRM/NICO",
        run_id="run-123",
        started_at="2026-07-10T00:00:00Z",
        finished_at="2026-07-10T00:01:00Z",
    )

    assert manifest["artifact_schema"] == "nico.scanner_worker_orchestration.v1"
    assert manifest["run_id"] == "run-123"
    assert manifest["required_tool_count"] == len(manifest["tools"])
    names = {item["tool"] for item in manifest["tools"]}
    assert {"pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint", "typescript", "gitleaks", "trufflehog", "coverage"}.issubset(names)
    pip_audit = next(item for item in manifest["tools"] if item["tool"] == "pip-audit")
    bandit = next(item for item in manifest["tools"] if item["tool"] == "bandit")
    trufflehog = next(item for item in manifest["tools"] if item["tool"] == "trufflehog")
    npm_audit = next(item for item in manifest["tools"] if item["tool"] == "npm-audit")

    assert pip_audit["status"] == "completed"
    assert pip_audit["exit_code"] == 0
    assert pip_audit["artifact_hash"]
    assert bandit["has_findings"] is True
    assert bandit["finding_count"] == 1
    assert trufflehog["status"] == "unavailable"
    assert trufflehog["reason"] == "trufflehog is not installed in the worker image"
    assert npm_audit["status"] == "missing"
    assert "npm-audit" in manifest["unavailable_tools"]
    assert "bandit" in manifest["finding_tools"]
    assert manifest["manifest_hash"]


def test_orchestration_manifest_hashes_self_referential_tool_evidence() -> None:
    tool: dict[str, object] = {
        "tool": "pip-audit",
        "status": "completed",
        "category": "dependency",
        "returncode": 0,
        "timed_out": False,
        "findings": [],
    }
    tool["self"] = tool

    manifest = build_scanner_worker_orchestration_manifest(
        {"tools": {"pip-audit": tool}},
        repository="BoneManTGRM/NICO",
        run_id="cycle-run",
        started_at="2026-07-10T00:00:00Z",
        finished_at="2026-07-10T00:00:01Z",
    )

    pip_audit = next(item for item in manifest["tools"] if item["tool"] == "pip-audit")
    assert len(pip_audit["artifact_hash"]) == 64
    assert len(manifest["manifest_hash"]) == 64


def test_orchestration_manifest_is_evidence_only_guarded() -> None:
    manifest = build_scanner_worker_orchestration_manifest(
        {"tools": {}},
        repository="BoneManTGRM/NICO",
        run_id="empty-run",
        started_at="2026-07-10T00:00:00Z",
        finished_at="2026-07-10T00:00:01Z",
    )

    assert manifest["completed_tools"] == []
    assert len(manifest["unavailable_tools"]) == manifest["required_tool_count"]
    assert "cannot be counted as clean proof" in manifest["guardrail"]
