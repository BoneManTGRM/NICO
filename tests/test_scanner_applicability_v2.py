from __future__ import annotations

from nico.scanner_applicability_v1 import normalize_scanner_applicability_canonical


SHA = "a" * 40


def _record(name: str, status: str, reason: str = "") -> dict:
    return {
        "scanner_name": name,
        "commit_sha": SHA,
        "state": status,
        "status": status,
        "completed": status.startswith("completed"),
        "verified": status.startswith("completed"),
        "exact_commit_match": True,
        "artifact_hash": (name[0] * 64) if status.startswith("completed") else "",
        "failure_reason": reason,
        "findings": [],
    }


def test_python_only_repository_marks_node_analyzers_not_applicable() -> None:
    canonical = {
        "identity": {"commit_sha": SHA},
        "repository_evidence": {
            "file_evidence": {"sampled_paths": ["requirements.txt", "src/main.py"]},
            "dependency_evidence": {"manifest_paths": ["requirements.txt"]},
        },
        "scanner_execution_records": [
            _record("pip-audit", "completed"),
            _record("bandit", "completed"),
            _record("semgrep", "completed"),
            _record("gitleaks", "completed"),
            _record("trufflehog", "completed"),
            _record("osv-scanner", "completed"),
            _record("npm-audit", "unavailable", "package-lock.json not found for npm audit."),
            _record("eslint", "unavailable", "apps/web/package.json not found."),
            _record("typescript", "unavailable", "apps/web/package.json not found."),
        ],
        "assessment": {},
    }

    result = normalize_scanner_applicability_canonical(canonical)
    applicable = result["scanner_execution_records"]
    not_applicable = result["not_applicable_scanner_records"]
    summary = result["assessment"]["scanner_applicability_summary"]

    assert [item["scanner_name"] for item in applicable] == [
        "pip-audit",
        "bandit",
        "semgrep",
        "gitleaks",
        "trufflehog",
        "osv-scanner",
    ]
    assert {item["scanner_name"] for item in not_applicable} == {
        "npm-audit",
        "eslint",
        "typescript",
    }
    assert all(item["completed"] is False for item in not_applicable)
    assert all(item["verified"] is False for item in not_applicable)
    assert all(item["applicable"] is False for item in not_applicable)
    assert summary["requested_scanners"] == 9
    assert summary["applicable_scanners"] == 6
    assert summary["completed_applicable_scanners"] == 6
    assert summary["incomplete_applicable_scanners"] == 0
    assert summary["not_applicable_scanners"] == 3
    assert summary["not_applicable_receives_completion_credit"] is False


def test_python_only_repository_accepts_exact_pipeline_unavailability_messages() -> None:
    canonical = {
        "identity": {"commit_sha": SHA},
        "repository_evidence": {
            "file_evidence": {"sampled_paths": ["requirements.txt", "src/main.py"]},
            "dependency_evidence": {"manifest_paths": ["requirements.txt"]},
        },
        "scanner_execution_records": [
            _record(
                "npm-audit",
                "unavailable",
                "No package-lock.json with an adjacent package.json was found.",
            ),
            _record(
                "eslint",
                "unavailable",
                "No supported JavaScript or TypeScript source files were found in apps/web/app.",
            ),
            _record(
                "typescript",
                "unavailable",
                "Project dependencies were not prepared.",
            ),
        ],
        "assessment": {},
    }

    result = normalize_scanner_applicability_canonical(canonical)

    assert result["scanner_execution_records"] == []
    assert {
        item["scanner_name"] for item in result["not_applicable_scanner_records"]
    } == {"npm-audit", "eslint", "typescript"}
    assert all(
        item["completed"] is False
        for item in result["not_applicable_scanner_records"]
    )


def test_python_only_frozen_report_recovers_legacy_failed_mismatch_states() -> None:
    canonical = {
        "identity": {"commit_sha": SHA},
        "repository_evidence": {
            "file_evidence": {"sampled_paths": ["requirements.txt", "src/main.py"]},
        },
        "requested_scanner_records": [
            _record(
                "npm-audit",
                "failed",
                "No package-lock.json with an adjacent package.json was found.",
            ),
            _record(
                "eslint",
                "failed",
                "No supported JavaScript or TypeScript source files were found in apps/web/app.",
            ),
        ],
        "assessment": {},
    }

    result = normalize_scanner_applicability_canonical(canonical)

    assert result["scanner_execution_records"] == []
    assert {
        item["scanner_name"] for item in result["not_applicable_scanner_records"]
    } == {"npm-audit", "eslint"}
    assert all(
        item["raw_state"] == "failed"
        for item in result["not_applicable_scanner_records"]
    )


def test_node_repository_does_not_hide_missing_applicable_analyzers() -> None:
    canonical = {
        "identity": {"commit_sha": SHA},
        "repository_evidence": {
            "file_evidence": {
                "sampled_paths": ["package.json", "package-lock.json", "src/index.ts"]
            },
            "dependency_evidence": {
                "manifest_paths": ["package.json"],
                "lockfile_paths": ["package-lock.json"],
            },
        },
        "scanner_execution_records": [
            _record("npm-audit", "unavailable", "npm binary is not installed in the worker image"),
            _record("eslint", "unavailable", "project dependencies were not prepared"),
            _record("typescript", "unavailable", "tsc was not installed by the exact package-lock"),
        ],
        "assessment": {},
    }

    result = normalize_scanner_applicability_canonical(canonical)
    assert result["not_applicable_scanner_records"] == []
    assert len(result["scanner_execution_records"]) == 3
    assert result["assessment"]["scanner_applicability_summary"]["incomplete_applicable_scanners"] == 3
    assert all(item["applicable"] is True for item in result["scanner_execution_records"])


def test_node_only_repository_marks_pip_audit_not_applicable() -> None:
    canonical = {
        "identity": {"commit_sha": SHA},
        "repository_evidence": {
            "file_evidence": {"sampled_paths": ["package.json", "src/index.ts"]},
            "dependency_evidence": {"manifest_paths": ["package.json"]},
        },
        "scanner_execution_records": [
            _record("pip-audit", "unavailable", "requirements.txt not found for pip-audit."),
        ],
        "assessment": {},
    }

    result = normalize_scanner_applicability_canonical(canonical)

    assert result["scanner_execution_records"] == []
    assert result["not_applicable_scanner_records"][0]["scanner_name"] == "pip-audit"
    assert result["assessment"]["scanner_applicability_summary"]["incomplete_applicable_scanners"] == 0


def test_node_only_repository_accepts_exact_pipeline_pip_audit_wording() -> None:
    canonical = {
        "identity": {"commit_sha": SHA},
        "repository_evidence": {
            "file_evidence": {"sampled_paths": ["package.json", "src/index.ts"]},
            "dependency_evidence": {"manifest_paths": ["package.json"]},
        },
        "scanner_execution_records": [
            _record("pip-audit", "unavailable", "requirements.txt was not found."),
        ],
        "assessment": {},
    }

    result = normalize_scanner_applicability_canonical(canonical)

    assert result["scanner_execution_records"] == []
    assert result["not_applicable_scanner_records"][0]["scanner_name"] == "pip-audit"
    assert result["assessment"]["scanner_applicability_summary"] == {
        "version": "nico.scanner-applicability.v2",
        "repository_signals": {
            "node_manifest": True,
            "node_source": True,
            "python_manifest": False,
            "python_source": False,
        },
        "requested_scanners": 1,
        "applicable_scanners": 0,
        "completed_applicable_scanners": 0,
        "incomplete_applicable_scanners": 0,
        "not_applicable_scanners": 1,
        "not_applicable_tools": ["pip-audit"],
        "not_applicable_receives_completion_credit": False,
        "unavailable_reserved_for_applicable_missing_evidence": True,
    }


def test_scanner_error_wording_does_not_create_false_repository_signal() -> None:
    canonical = {
        "identity": {"commit_sha": SHA},
        "repository_evidence": {
            "file_evidence": {"sampled_paths": ["requirements.txt", "app.py"]}
        },
        "scanner_execution_records": [
            _record("eslint", "unavailable", "apps/web/package.json not found."),
        ],
        "assessment": {},
    }

    result = normalize_scanner_applicability_canonical(canonical)
    summary = result["assessment"]["scanner_applicability_summary"]
    assert summary["repository_signals"]["node_manifest"] is False
    assert summary["repository_signals"]["node_source"] is False
    assert summary["not_applicable_scanners"] == 1


def test_missing_applicable_python_binary_remains_unavailable() -> None:
    canonical = {
        "identity": {"commit_sha": SHA},
        "repository_evidence": {
            "file_evidence": {"sampled_paths": ["requirements.txt", "app.py"]}
        },
        "scanner_execution_records": [
            _record("bandit", "unavailable", "bandit is not installed in the worker image"),
        ],
        "assessment": {},
    }

    result = normalize_scanner_applicability_canonical(canonical)
    assert result["not_applicable_scanner_records"] == []
    assert result["scanner_execution_records"][0]["state"] == "unavailable"
    assert result["assessment"]["scanner_applicability_summary"]["incomplete_applicable_scanners"] == 1
