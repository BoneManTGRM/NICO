from __future__ import annotations

from types import SimpleNamespace
from copy import deepcopy

import pytest

from nico.decision_grade_scanner_executions_v1 import (
    install_structured_scanner_executions,
    normalize_scanner_executions,
)


def _by_tool(result):
    return {item["tool"]: item for item in result["scanner_results"]}


def test_legacy_execution_arrays_become_structured_records() -> None:
    result = normalize_scanner_executions(
        {
            "status": "complete",
            "tools_requested": ["pip-audit", "osv-scanner", "bandit", "eslint"],
            "tools_run": ["pip-audit", "eslint"],
            "failed_tools": ["bandit"],
            "unavailable_tools": ["osv-scanner"],
            "optional_tools": ["eslint"],
        }
    )
    records = _by_tool(result)

    assert records["pip-audit"]["status"] == "complete"
    assert records["bandit"]["status"] == "failed"
    assert records["osv-scanner"]["status"] == "unavailable"
    assert records["eslint"]["required"] is False
    assert result["scanner_execution_summary"]["required_incomplete"] == 2


def test_explicit_failure_overrides_conflicting_completed_array() -> None:
    result = normalize_scanner_executions(
        {
            "tools_requested": ["bandit"],
            "tools_run": ["bandit"],
            "failed_tools": ["bandit"],
        }
    )

    assert _by_tool(result)["bandit"]["status"] == "failed"


def test_existing_structured_record_remains_authoritative() -> None:
    result = normalize_scanner_executions(
        {
            "scanner_results": [
                {
                    "tool": "osv-scanner",
                    "status": "partial",
                    "reason": "structured output could not be verified",
                    "findings": [{"id": "candidate-1"}],
                }
            ],
            "tools_run": ["osv-scanner"],
        }
    )
    record = _by_tool(result)["osv-scanner"]

    assert record["status"] == "partial"
    assert record["reason"] == "structured output could not be verified"
    assert record["findings"] == [{"id": "candidate-1"}]


@pytest.mark.parametrize("status", ["not_applicable", "failed", "timed_out", "partial"])
def test_canonical_scanner_name_preserves_noncompletion_evidence(status: str) -> None:
    source = {
        "scanner_results": [{
            "scanner_name": "typescript", "status": status,
            "completed": False, "verified": False,
            "commit_sha": "a" * 40,
            "applicability_evidence": {"inventory_sha256": "b" * 64},
        }],
        "tools_requested": ["typescript"],
        "tools_run": ["typescript"],
    }
    before = deepcopy(source)
    result = normalize_scanner_executions(source)
    record = _by_tool(result)["typescript"]

    assert record["status"] == ("timeout" if status == "timed_out" else status)
    assert record["completed"] is False
    assert record["verified"] is False
    assert record["commit_sha"] == "a" * 40
    assert record["applicability_evidence"] == before["scanner_results"][0]["applicability_evidence"]
    assert result["scanner_execution_summary"]["complete"] == 0
    assert source == before


def test_requested_without_terminal_record_is_partial_not_clean() -> None:
    result = normalize_scanner_executions({"tools_requested": ["gitleaks"]})
    record = _by_tool(result)["gitleaks"]

    assert record["status"] == "partial"
    assert record["required"] is True
    assert result["scanner_execution_summary"]["required_incomplete"] == 1


@pytest.mark.parametrize("status", ["not_applicable", "failed", "timed_out", "partial"])
def test_canonical_scanner_record_overrides_legacy_completion(status: str) -> None:
    source = {
        "scanner_results": [{
            "scanner_name": "typescript", "status": status,
            "completed": False, "verified": False,
            "repository": "owner/synthetic", "commit_sha": "a" * 40,
            "actual_commit_sha": "b" * 40,
            "applicability_evidence": {"inventory_sha256": "c" * 64},
            "findings": [{"id": "synthetic-1"}],
        }],
        "tools_requested": ["typescript"], "tools_run": ["typescript"],
    }
    before = deepcopy(source)
    result = normalize_scanner_executions(source)
    expected = dict(before["scanner_results"][0], tool="typescript", category="static",
                    required=True, status="timeout" if status == "timed_out" else status)
    assert result["scanner_results"] == [expected]
    assert result["scanner_execution_summary"]["complete"] == 0
    assert result["scanner_execution_summary"]["required_incomplete"] == 1
    assert source == before


def test_installer_is_idempotent_and_wraps_provider_scan_reader() -> None:
    provider = SimpleNamespace(_scan=lambda _context: {"tools_requested": ["bandit"], "failed_tools": ["bandit"]})

    first = install_structured_scanner_executions(provider)
    wrapped = provider._scan
    second = install_structured_scanner_executions(provider)
    result = provider._scan({})

    assert first["status"] == "installed"
    assert second["status"] == "already_installed"
    assert provider._scan is wrapped
    assert _by_tool(result)["bandit"]["status"] == "failed"


@pytest.mark.parametrize("status", [None, "unknown", "unavailable", "timeout", "complete"])
def test_canonical_status_and_identity_survive_installed_reader(status) -> None:
    record = {"scanner_name": " TypeScript ", "status": status,
              "commit_sha": "a" * 40, "verified": False}
    source = {"scanner_results": [record], "tools_run": ["typescript"]}
    provider = SimpleNamespace(_scan=lambda _context: source)
    installation = install_structured_scanner_executions(provider)
    result = provider._scan({})
    normalized = _by_tool(result)["typescript"]
    assert normalized["status"] == (status or "unknown")
    assert normalized["commit_sha"] == record["commit_sha"]
    assert normalized["verified"] is False
    assert result["scanner_execution_summary"]["complete"] == int(status == "complete")
    assert installation["human_review_required"] is True
    assert installation["client_delivery_allowed"] is False


@pytest.mark.parametrize("primary", ["tool", "scanner"])
def test_existing_tool_alias_precedence_is_unchanged(primary: str) -> None:
    result = normalize_scanner_executions({"scanner_results": [{
        primary: "bandit", "scanner_name": "typescript", "status": "failed",
    }]})
    assert list(_by_tool(result)) == ["bandit"]
    assert _by_tool(result)["bandit"]["status"] == "failed"
