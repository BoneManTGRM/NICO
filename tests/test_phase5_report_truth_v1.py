from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from nico.phase5_report_truth_v1 import (
    BASELINE,
    install_phase5_report_truth_v1,
    reconcile_phase5_report_truth,
    scan_files_executable_only,
)


TARGET = "1" * 40


def _tool(tool: str, *, status: str = "completed", findings: list[dict] | None = None) -> dict:
    complete = status == "completed"
    return {
        "tool": tool,
        "status": status,
        "category": "static",
        "target_commit_sha": TARGET,
        "verified_for_this_report": complete,
        "output_capture_complete": complete,
        "raw_artifact_capture_complete": complete,
        "returncode_valid": complete,
        "timed_out": False,
        "scans_git_history": tool in {"gitleaks", "trufflehog"},
        "full_history_verified": complete if tool in {"gitleaks", "trufflehog"} else False,
        "findings": findings or [],
        "findings_count": len(findings or []),
        "artifact_hash": f"hash-{tool}",
        "raw_artifact_sha256": f"raw-{tool}",
        "deterministic_fingerprint": f"fingerprint-{tool}",
        "failure_or_unavailable_reason": "" if complete else "deterministic test failure",
    }


def _assessment() -> dict:
    return {
        "maturity_signal": {"score": 85, "presented_score": 85},
        "canonical_evidence_adjusted_score": 83,
        "sections": [
            {"id": "dependency_health", "label": "Dependency", "score": 92, "evidence": [], "findings": [], "unavailable": []},
            {"id": "secrets_review", "label": "Secrets", "score": 93, "evidence": [], "findings": [], "unavailable": []},
            {"id": "static_analysis", "label": "Static", "score": 79, "evidence": [], "findings": ["Failed static tools: bandit"], "unavailable": ["bandit unavailable"]},
            {"id": "ci_cd", "label": "CI/CD", "score": 78, "evidence": [], "findings": ["14 historical workflow runs were non-successful"], "unavailable": []},
            {"id": "architecture_debt", "label": "Architecture", "score": 78, "evidence": [], "findings": [], "unavailable": []},
        ],
        "findings_register": [
            {"finding_id": "bandit-old", "category": "evidence", "title": "bandit evidence unavailable"},
            {
                "finding_id": "complexity",
                "category": "architecture",
                "title": "Complexity hotspot: _build_markdown",
                "evidence": "cyclomatic_complexity=108; loc=230",
            },
        ],
        "human_review_required": True,
        "client_ready": False,
    }


def test_code_risk_scan_ignores_configuration_literals_but_keeps_executable_tls_disable() -> None:
    result = scan_files_executable_only(
        {
            "nico/config_builder.py": 'RULE = "requests.get(url, verify=False)"\n',
            "nico/runtime.py": "response = requests.get(url, verify=False)\n",
            "config/rules.yml": "pattern: requests.$METHOD(..., verify=False, ...)\n",
        }
    )

    assert result["risk_scan_method"] == "executable_source_token_aware_v1"
    assert result["configuration_literals_treated_as_executable"] is False
    assert len(result["risks"]) == 1
    assert result["risks"][0].startswith("nico/runtime.py:1: tls_verify_disabled")


def test_report_scanner_status_comes_from_exact_sha_retained_artifact() -> None:
    tools = {
        "bandit": _tool("bandit"),
        "eslint": _tool("eslint"),
        "gitleaks": _tool("gitleaks"),
        "osv-scanner": _tool("osv-scanner"),
    }
    stage_results = {
        "dependency_security_static_analysis": {
            "commit_sha": TARGET,
            "scanner_artifact": {"target_commit_sha": TARGET, "tools": tools},
        }
    }

    result = reconcile_phase5_report_truth(_assessment(), stage_results)
    health = result["evidence_health_summary"]

    assert set(tools).issubset(set(health["completed_scanners"]))
    assert health["report_status_derived_from_retained_artifact"] is True
    assert not any(item.get("finding_id") == "bandit-old" for item in result["findings_register"])
    assert result["phase5_verified_outcomes"]["scanner_status_changes"]["bandit"] == {
        "before": "failed",
        "after": "completed",
    }
    phase5 = next(item for item in result["sections"] if item["id"] == "phase5_verified_outcomes")
    assert phase5["exclude_from_maturity"] is True
    assert "scanner-status change" in phase5["summary"]


def test_mismatched_or_incomplete_scanner_evidence_stays_incomplete() -> None:
    bandit = _tool("bandit")
    bandit["target_commit_sha"] = "2" * 40
    eslint = _tool("eslint", status="failed")
    stage_results = {
        "dependency_security_static_analysis": {
            "commit_sha": TARGET,
            "scanner_artifact": {"target_commit_sha": TARGET, "tools": {"bandit": bandit, "eslint": eslint}},
        }
    }

    result = reconcile_phase5_report_truth(_assessment(), stage_results)
    health = result["evidence_health_summary"]
    incomplete = {item["scanner"]: item for item in health["incomplete_scanners"]}

    assert "bandit" not in health["completed_scanners"]
    assert incomplete["bandit"]["exact_commit_match"] is False
    assert incomplete["eslint"]["status"] == "failed"
    assert any(item.get("finding_id") == "bandit-old" for item in result["findings_register"])


def test_classified_ci_history_is_visible_and_cancellations_are_not_failures() -> None:
    install_phase5_report_truth_v1()
    from nico import snapshot_repository_evidence as snapshot

    runs = [
        {"id": 1, "name": "CI", "status": "completed", "conclusion": "success", "event": "push", "head_sha": TARGET},
        {"id": 2, "name": "CI newer run superseded", "status": "completed", "conclusion": "cancelled", "event": "push", "head_sha": TARGET},
        {"id": 3, "name": "CI", "status": "completed", "conclusion": "failure", "event": "push", "head_sha": TARGET},
    ]
    summary = snapshot._workflow_summary({}, runs, {}, TARGET)
    classified = summary["classified_history"]

    assert summary["non_success_runs_are_cause_classified"] is True
    assert summary["genuine_failure_runs"] == 1
    assert summary["cancelled_or_superseded_runs"] == 1
    assert classified["cancellations_counted_as_failures"] is False

    assessment = _assessment()
    result = reconcile_phase5_report_truth(
        assessment,
        {"ci_cd_architecture_complexity_velocity": {"commit_sha": TARGET, "workflow_evidence": summary}},
    )
    ci = next(item for item in result["sections"] if item["id"] == "ci_cd")
    assert ci["historical_reliability_classified"] is True
    assert any("genuine_failure=1" in line for line in ci["evidence"])
    assert not any("non-successful" in line for line in ci["findings"])


def test_semgrep_profile_is_externalized_and_preserves_tls_rule(tmp_path: Path) -> None:
    install_phase5_report_truth_v1()
    from nico import scanner_evidence_pipeline_v1 as scanner

    workspace = SimpleNamespace(root=tmp_path)
    generated = scanner._semgrep_config(workspace)
    text = generated.read_text(encoding="utf-8")

    assert generated == tmp_path / "nico-semgrep-standard.yml"
    assert "nico.python.requests-no-verify" in text
    assert "verify=False" in text
    assert (Path(__file__).resolve().parents[1] / "config" / "nico-semgrep-standard.yml").is_file()


def test_phase5_delta_does_not_invent_complexity_improvement() -> None:
    result = reconcile_phase5_report_truth(
        _assessment(),
        {"evidence_reconciliation_and_scoring": {"commit_sha": TARGET}},
    )
    outcomes = result["phase5_verified_outcomes"]

    assert outcomes["complexity_changes"] == {}
    assert "_build_markdown" in outcomes["unchanged_complexity_hotspots"]
    assert outcomes["truth_rule"].startswith("Only exact-SHA retained evidence")
    assert BASELINE["technical_maturity"] == 85
