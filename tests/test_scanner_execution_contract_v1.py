from __future__ import annotations

"""Regression coverage for exact scanner contracts and candidate stability."""

import json
from pathlib import Path
from types import SimpleNamespace

from nico.client_readiness_candidate_triage import (
    build_candidate_triage_register,
    canonical_candidate,
    cluster_candidates,
)
from nico.scanner_execution_contract_v1 import (
    PINNED_EXECUTORS,
    attach_scanner_execution_contract,
    persist_redacted_scanner_artifact,
    scanner_execution_contract,
    scanner_suite_contract,
    validate_scanner_execution_record,
)


def _spec(name: str, category: str = "static") -> SimpleNamespace:
    command = (name, "--json")
    if name == "semgrep":
        command = ("semgrep", "scan", "--config", "auto", "--json", ".")
    return SimpleNamespace(
        name=name,
        command=command,
        category=category,
        timeout_seconds=240,
        max_output_chars=1000,
        requires_project_commands=name in {"eslint", "typescript"},
        scans_git_history=name in {"gitleaks", "trufflehog"},
        valid_returncodes=frozenset({0, 1}),
    )


def _completed(name: str = "bandit") -> dict:
    return {
        "tool": name,
        "status": "completed",
        "category": "static",
        "returncode": 0,
        "timed_out": False,
        "output_capture_complete": True,
        "verified_for_this_report": True,
        "findings": [],
    }


def test_all_nine_scanner_executors_have_explicit_version_contracts() -> None:
    assert set(PINNED_EXECUTORS) == {
        "pip-audit",
        "npm-audit",
        "osv-scanner",
        "bandit",
        "semgrep",
        "eslint",
        "typescript",
        "gitleaks",
        "trufflehog",
    }
    assert all(item["version"] for item in PINNED_EXECUTORS.values())


def test_scanner_contract_is_deterministic_and_command_bound() -> None:
    first = scanner_execution_contract(_spec("bandit"))
    second = scanner_execution_contract(_spec("bandit"))

    assert first == second
    assert first["executor_version"] == "1.9.4"
    assert first["configuration"]["command"] == ["bandit", "--json"]
    assert first["ruleset"]["configuration_sha256"]
    assert first["ruleset"]["command_sha256"]
    assert first["contract_sha256"]


def test_semgrep_auto_is_disclosed_as_reproducibility_limitation() -> None:
    contract = scanner_execution_contract(_spec("semgrep"))

    assert contract["ruleset"]["immutable"] is False
    assert contract["ruleset"]["mode"] == "dynamic_registry_auto"
    assert "retained resolved-rules digest" in contract["ruleset"]["limitation"]


def test_suite_contract_requires_all_nine_tools_and_reports_ruleset_state() -> None:
    categories = {
        "pip-audit": "dependency",
        "npm-audit": "dependency",
        "osv-scanner": "dependency",
        "bandit": "static",
        "semgrep": "static",
        "eslint": "static",
        "typescript": "static",
        "gitleaks": "secret",
        "trufflehog": "secret",
    }
    suite = scanner_suite_contract(
        [_spec(name, categories[name]) for name in PINNED_EXECUTORS]
    )

    assert suite["missing_required_tools"] == []
    assert suite["duplicate_tool_contracts"] == 0
    assert suite["all_executor_versions_bound"] is True
    assert suite["all_rulesets_immutable"] is False
    assert set(suite["contracts"]) == set(PINNED_EXECUTORS)


def test_redacted_result_is_retained_atomically_with_hash(tmp_path: Path) -> None:
    contracted = attach_scanner_execution_contract(
        _completed(),
        _spec("bandit"),
    )
    contracted.update(
        {
            "snapshot_commit_sha": "a" * 40,
            "actual_commit_sha": "a" * 40,
            "exact_commit_match": True,
        }
    )
    retained = persist_redacted_scanner_artifact(
        contracted,
        scan_id="scan_fixture",
        root=tmp_path,
    )

    metadata = retained["retained_redacted_artifact"]
    assert metadata["status"] == "retained"
    assert metadata["redacted"] is True
    assert metadata["atomic_write"] is True
    path = Path(metadata["path"])
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["tool"] == "bandit"
    assert "stderr" not in payload
    assert not list(path.parent.glob("*.tmp"))
    assert validate_scanner_execution_record(
        retained,
        expected_commit_sha="a" * 40,
    )["status"] == "valid"


def test_completed_result_cannot_claim_verification_without_complete_capture() -> None:
    contracted = attach_scanner_execution_contract(
        {
            **_completed(),
            "output_capture_complete": False,
        },
        _spec("bandit"),
    )
    contracted = persist_redacted_scanner_artifact(
        contracted,
        scan_id="scan_fixture",
        root="",
    )

    validation = validate_scanner_execution_record(contracted)

    assert validation["status"] == "invalid"
    assert "completed.output_capture_complete:required" in validation[
        "validation_errors"
    ]


def test_candidate_identity_and_clusters_are_order_independent() -> None:
    candidates = [
        {
            "category": "static",
            "analyzer": "bandit",
            "rule_id": "B101",
            "path": "nico/a.py",
            "line": 10,
            "message": "assert used",
        },
        {
            "category": "secret",
            "analyzer": "gitleaks",
            "rule_id": "generic-api-key",
            "path": "config/example.env",
            "line": 2,
            "message": "candidate",
        },
    ]
    forward = cluster_candidates(candidates)
    reverse = cluster_candidates(reversed(candidates))

    assert sorted(
        candidate["candidate_id"]
        for cluster in forward
        for candidate in cluster["candidates"]
    ) == sorted(
        candidate["candidate_id"]
        for cluster in reverse
        for candidate in cluster["candidates"]
    )
    assert sorted(item["cluster_digest"] for item in forward) == sorted(
        item["cluster_digest"] for item in reverse
    )


def test_missing_human_candidate_decisions_are_pending_not_internal_failure() -> None:
    candidate = {
        "category": "dependency",
        "analyzer": "pip-audit",
        "advisory_id": "GHSA-fixture",
        "package": "example",
        "installed_version": "1.0",
    }
    register = build_candidate_triage_register(
        [candidate],
        repository="owner/repo",
        commit_sha="a" * 40,
        run_id="run_fixture",
    )

    assert register["status"] == "blocked"
    assert register["candidate_count"] == 1
    assert register["disposition_counts"] == {"pending_human_review": 1}
    assert register["invalid_decisions"] == []
    assert canonical_candidate(candidate)["candidate_id"] == canonical_candidate(candidate)[
        "candidate_id"
    ]
