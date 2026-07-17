from __future__ import annotations

from copy import deepcopy

from nico.mid_static_score_accuracy import apply_verified_control_reconciliation


def _assessment() -> dict:
    return {
        "sections": [
            {"id": "code_audit", "score": 60, "status": "yellow", "evidence": ["original code evidence"], "findings": ["review four sampled patterns"]},
            {"id": "dependency_health", "score": 72, "status": "yellow", "evidence": ["original dependency evidence"], "findings": []},
            {"id": "secrets_review", "score": 80, "status": "green", "evidence": [], "findings": []},
            {"id": "static_analysis", "score": 49, "status": "red", "evidence": ["original static evidence"], "findings": ["review scanner items"]},
            {"id": "ci_cd", "score": 83, "status": "green", "evidence": [], "findings": []},
            {"id": "architecture_debt", "score": 82, "status": "green", "evidence": [], "findings": []},
            {"id": "velocity_complexity", "score": 84, "status": "green", "evidence": [], "findings": []},
        ],
        "maturity_signal": {"score": 70, "level": "Mid"},
        "scorecard": {"technical_score": 70},
    }


def _repository() -> dict:
    return {
        "status": "attached",
        "file_evidence": {"files_profiled": 40},
        "architecture_evidence": {
            "source_file_count": 120,
            "test_path_count": 45,
            "documentation_path_count": 20,
        },
        "activity_evidence": {"commits_returned": 50, "pull_requests_returned": 25},
        "dependency_evidence": {
            "manifest_paths": ["requirements.txt", "apps/web/package.json"],
            "lockfile_paths": ["apps/web/package-lock.json"],
            "dependency_entries": 200,
        },
        "code_signal_evidence": {"risk_pattern_hits": 4, "todo_fixme_security_notes": 0},
    }


def _scanner(*, static_material: int = 0) -> dict:
    tools = ["pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint", "typescript"]
    return {
        "status": "attached",
        "snapshot_match": True,
        "tools_requested": tools,
        "tools_run": tools,
        "failed_tools": [],
        "timed_out_tools": [],
        "unavailable_tools": [],
        "scanner_results": [
            {
                "tool": tool,
                "status": "completed",
                "verified_for_this_report": True,
                "current_run": True,
            }
            for tool in tools
        ],
        "finding_summary": {
            "by_category": {
                "dependency": {
                    "raw": 2,
                    "material": 0,
                    "review_required": 2,
                    "approved_or_nonblocking": 0,
                    "excluded_test_only": 0,
                },
                "static": {
                    "raw": 6,
                    "material": static_material,
                    "review_required": 4,
                    "approved_or_nonblocking": 0,
                    "excluded_test_only": 2,
                },
            }
        },
    }


def _sections(payload: dict) -> dict[str, dict]:
    return {item["id"]: item for item in payload["sections"]}


def test_verified_snapshot_evidence_recovers_undercredited_controls() -> None:
    original = _assessment()
    reconciled = apply_verified_control_reconciliation(original, _repository(), _scanner())
    sections = _sections(reconciled)

    assert sections["code_audit"]["score"] >= 80
    assert sections["dependency_health"]["score"] >= 80
    assert sections["static_analysis"]["score"] >= 80
    assert sections["code_audit"]["findings"] == original["sections"][0]["findings"]
    assert sections["static_analysis"]["findings"] == original["sections"][3]["findings"]
    assert reconciled["scorecard"]["technical_score"] > original["scorecard"]["technical_score"]
    assert reconciled["mid_verified_control_reconciliation"]["findings_removed"] is False
    assert reconciled["mid_verified_control_reconciliation"]["missing_evidence_treated_as_clean"] is False


def test_material_static_finding_blocks_static_and_code_upward_reconciliation() -> None:
    original = _assessment()
    reconciled = apply_verified_control_reconciliation(original, _repository(), _scanner(static_material=1))
    sections = _sections(reconciled)

    assert sections["code_audit"]["score"] == 60
    assert sections["static_analysis"]["score"] == 49
    assert sections["dependency_health"]["score"] >= 80
    assert reconciled["mid_verified_control_reconciliation"]["static_material_findings"] == 1


def test_missing_snapshot_identity_cannot_raise_scores() -> None:
    original = _assessment()
    scanner = _scanner()
    scanner["snapshot_match"] = False

    reconciled = apply_verified_control_reconciliation(original, _repository(), scanner)

    assert reconciled == original
    assert reconciled is not original


def test_reconciliation_is_idempotent_for_same_evidence() -> None:
    first = apply_verified_control_reconciliation(_assessment(), _repository(), _scanner())
    second = apply_verified_control_reconciliation(deepcopy(first), _repository(), _scanner())

    assert _sections(first)["code_audit"]["score"] == _sections(second)["code_audit"]["score"]
    assert _sections(first)["dependency_health"]["score"] == _sections(second)["dependency_health"]["score"]
    assert _sections(first)["static_analysis"]["score"] == _sections(second)["static_analysis"]["score"]
    assert len(_sections(first)["static_analysis"]["evidence"]) == len(_sections(second)["static_analysis"]["evidence"])
