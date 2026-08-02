from __future__ import annotations

from nico.comprehensive_requested_scanner_projection_v62 import (
    install_comprehensive_requested_scanner_projection_v62,
    requested_scanner_population,
)


def _record(name: str, *, completed: bool, status: str = "completed") -> dict[str, object]:
    return {
        "scanner_name": name,
        "tool": name,
        "status": status,
        "completed": completed,
        "exact_commit_match": True,
        "artifact_hash": (name[0] or "a") * 64 if completed else "",
        "findings": [],
    }


def test_requested_manifest_excludes_stale_unrequested_scanner_from_coverage() -> None:
    canonical = {
        "scanner_execution_records": [
            _record("bandit", completed=True),
            _record("eslint", completed=True),
            _record("gitleaks", completed=False, status="unavailable"),
        ],
        "live_scanner_evidence": {
            "tools_requested": ["bandit", "eslint"],
            "tools_run": ["bandit", "eslint"],
            "failed_tools": [],
            "unavailable_tools": [],
            "timed_out_tools": [],
        },
    }

    records, completed, incomplete, coverage = requested_scanner_population(canonical)

    assert [item["scanner_name"] for item in records] == ["bandit", "eslint"]
    assert [item["scanner_name"] for item in completed] == ["bandit", "eslint"]
    assert incomplete == []
    assert coverage == 100
    assert all(item["requested_for_exact_run"] is True for item in records)


def test_missing_requested_scanner_is_created_as_incomplete_fail_closed() -> None:
    canonical = {
        "scanner_execution_records": [_record("bandit", completed=True)],
        "live_scanner_evidence": {
            "tools_requested": ["bandit", "eslint"],
            "tools_run": ["bandit"],
            "failed_tools": [],
            "unavailable_tools": [],
            "timed_out_tools": [],
        },
    }

    records, completed, incomplete, coverage = requested_scanner_population(canonical)

    assert [item["scanner_name"] for item in records] == ["bandit", "eslint"]
    assert [item["scanner_name"] for item in completed] == ["bandit"]
    assert [item["scanner_name"] for item in incomplete] == ["eslint"]
    assert incomplete[0]["status"] == "missing"
    assert incomplete[0]["verified_for_this_report"] is False
    assert coverage == 50


def test_requested_projection_installer_binds_v55_population_boundary() -> None:
    from nico import comprehensive_canonical_projection_truth_v55 as projection

    result = install_comprehensive_requested_scanner_projection_v62()

    assert result["status"] in {"installed", "already_installed"}
    assert result["bound"] is True
    assert projection._scanner_population is requested_scanner_population
