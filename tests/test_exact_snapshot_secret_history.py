from __future__ import annotations

import json
import time
from pathlib import Path

import nico.exact_snapshot_secret_history as history
import nico.full_assessment_scorecard as scorecard
import nico.mid_assessment_handlers as mid_handlers
import nico.scanner_worker as scanner_worker
import nico.snapshot_assessment_handlers as snapshot_handlers


def _repo(secret_hits: int = 0) -> dict:
    return {"code_signal_evidence": {"potential_secret_pattern_hits": secret_hits}}


def _scanner(*results: dict) -> dict:
    return {
        "status": "attached",
        "tools_run": [str(item.get("scanner")) for item in results if item.get("status") in {"passed", "failed", "timeout", "error"}],
        "failed_tools": [str(item.get("scanner")) for item in results if item.get("status") in {"failed", "error"}],
        "timed_out_tools": [str(item.get("scanner")) for item in results if item.get("status") == "timeout"],
        "scanner_results": list(results),
    }


def _current_tree(high: int = 0, medium: int = 0, low: int = 0) -> dict:
    return {
        "scanner": "nico-secrets",
        "status": "failed" if high else "passed",
        "finding_counts": {"high": high, "medium": medium, "low": low},
        "files_scanned": 250,
    }


def _history_result(name: str, findings: int = 0, verified: int = 0, *, full: bool = True) -> dict:
    return {
        "scanner": name,
        "status": "passed",
        "execution_status": "completed_with_findings" if findings else "completed_clean",
        "execution_completed": True,
        "finding_count": findings,
        "verified_finding_count": verified,
        "candidate_finding_count": max(0, findings - verified),
        "full_history_covered": full,
        "history_commit_count": 420,
        "history_depth": "full" if full else "shallow_or_unverified",
    }


def test_gitleaks_parser_excludes_raw_and_encoded_secret_values() -> None:
    raw = "candidate-secret-value-never-retain"
    encoded = "Y2FuZGlkYXRlLXNlY3JldC12YWx1ZQ=="
    payload = [
        {
            "RuleID": "generic-api-key",
            "File": "nico/config.py",
            "StartLine": 12,
            "Commit": "a" * 40,
            "Secret": raw,
            "Match": encoded,
        }
    ]

    findings, error = history.parse_gitleaks_findings(json.dumps(payload))

    assert error is None
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "generic-api-key"
    assert findings[0]["commit_fingerprint"]
    assert raw not in repr(findings)
    assert encoded not in repr(findings)


def test_trufflehog_parser_excludes_raw_secret_material() -> None:
    raw = "raw-secret-never-retain"
    payload = {
        "DetectorName": "PrivateKey",
        "Verified": True,
        "Raw": raw,
        "RawV2": "encoded-secret-never-retain",
        "SourceMetadata": {
            "Data": {
                "Git": {
                    "file": "nico/private.pem",
                    "line": 1,
                    "commit": "b" * 40,
                }
            }
        },
    }

    findings, error = history.parse_trufflehog_findings(json.dumps(payload) + "\n")

    assert error is None
    assert len(findings) == 1
    assert findings[0]["verified"] is True
    assert findings[0]["path"] == "nico/private.pem"
    assert raw not in repr(findings)
    assert "encoded-secret-never-retain" not in repr(findings)


def test_parseable_gitleaks_finding_exit_is_completed_and_redacted(monkeypatch, tmp_path: Path) -> None:
    raw = "candidate-secret-value-never-retain"
    payload = [
        {
            "RuleID": "generic-api-key",
            "File": "nico/config.py",
            "StartLine": 7,
            "Commit": "c" * 40,
            "Secret": raw,
        }
    ]

    class FakeProcess:
        pid = 123
        returncode = 1

        def __init__(self, command):
            report_path = Path(command[command.index("--report-path") + 1])
            report_path.write_text(json.dumps(payload), encoding="utf-8")

        def communicate(self, timeout=None):
            return "", ""

    monkeypatch.setattr(history.shutil, "which", lambda _binary: "/usr/local/bin/gitleaks")
    monkeypatch.setattr(
        history,
        "history_metadata",
        lambda _path: {
            "full_history_covered": True,
            "history_depth": "full",
            "history_commit_count": 420,
            "snapshot_commit_sha": "d" * 40,
        },
    )
    monkeypatch.setattr(history.subprocess, "Popen", lambda command, **kwargs: FakeProcess(command))

    result = history._run_history_tool(
        "gitleaks",
        {"binary": "gitleaks", "intent": "Exact git-history credential review"},
        tmp_path,
        {"PATH": "/usr/local/bin"},
        time.monotonic() + 30,
    )

    assert result["status"] == "passed"
    assert result["execution_completed"] is True
    assert result["execution_status"] == "completed_with_findings"
    assert result["finding_count"] == 1
    assert result["full_history_covered"] is True
    assert raw not in repr(result)


def test_two_clean_full_history_scanners_support_high_evidence_score() -> None:
    section = history.history_secrets_section(
        _repo(),
        _scanner(_current_tree(), _history_result("gitleaks"), _history_result("trufflehog")),
    )

    assert section["score"] >= 90
    assert section["status"] == "green"
    assert section["confidence"] == "history-scanner-and-repository-bound"
    assert section["secret_history_triage"]["history_scanners_completed"] == 2
    assert section["secret_history_triage"]["history_finding_count"] == 0
    assert any("Gitleaks exact git-history scan completed with 0 finding" in item for item in section["evidence"])
    assert any("TruffleHog exact git-history scan completed with 0 finding" in item for item in section["evidence"])
    assert not any("did not both" in item for item in section["unavailable"])


def test_missing_or_shallow_history_remains_capped_and_disclosed() -> None:
    section = history.history_secrets_section(
        _repo(),
        _scanner(_current_tree(), _history_result("gitleaks"), _history_result("trufflehog", full=False)),
    )

    assert section["score"] <= 74
    assert section["status"] == "yellow"
    assert section["secret_history_triage"]["history_scanners_completed"] == 1
    assert any("did not both" in item for item in section["unavailable"])


def test_verified_history_finding_keeps_secrets_red() -> None:
    section = history.history_secrets_section(
        _repo(),
        _scanner(_current_tree(), _history_result("gitleaks"), _history_result("trufflehog", findings=1, verified=1)),
    )

    assert section["score"] <= 35
    assert section["status"] == "red"
    assert section["secret_history_triage"]["verified_finding_count"] == 1
    assert any("Immediately rotate" in item for item in section["findings"])


def test_attachment_handler_preserves_static_and_history_structured_fields(monkeypatch) -> None:
    raw_results = [
        {
            "scanner": "bandit",
            "status": "passed",
            "evidence_summary": "Bandit structured triage",
            "execution_completed": True,
            "execution_status": "completed_with_findings",
            "finding_count": 10,
            "material_finding_count": 1,
            "review_finding_count": 3,
            "excluded_test_finding_count": 6,
            "severity_counts": {"high": 1, "low": 9},
            "triage_version": "static-v1",
            "safe_output_preview": "must not be attached",
        },
        {
            "scanner": "gitleaks",
            "status": "passed",
            "evidence_summary": "Gitleaks clean history",
            "execution_completed": True,
            "execution_status": "completed_clean",
            "finding_count": 0,
            "verified_finding_count": 0,
            "candidate_finding_count": 0,
            "full_history_covered": True,
            "history_commit_count": 420,
            "history_depth": "full",
            "triage_version": history.HISTORY_VERSION,
        },
    ]

    def fake_delegate(context, outputs):
        return {
            "status": "complete",
            "scanner_evidence": {
                "scanner_results": [
                    {"scanner": "bandit", "status": "passed", "evidence_summary": "Bandit structured triage"},
                    {"scanner": "gitleaks", "status": "passed", "evidence_summary": "Gitleaks clean history"},
                ]
            },
        }

    monkeypatch.setattr(history, "_ATTACHMENT_DELEGATE", fake_delegate)
    result = history.history_attachment_handler(
        {"run_id": "midrun_example"},
        {"scanner_worker": {"scan": {"scanner_results": raw_results}}},
    )

    evidence = result["scanner_evidence"]
    by_name = {item["scanner"]: item for item in evidence["scanner_results"]}
    assert evidence["structured_triage_fields_attached"] is True
    assert by_name["bandit"]["material_finding_count"] == 1
    assert by_name["bandit"]["excluded_test_finding_count"] == 6
    assert "safe_output_preview" not in by_name["bandit"]
    assert by_name["gitleaks"]["full_history_covered"] is True
    assert by_name["gitleaks"]["history_commit_count"] == 420


def test_installer_adds_history_tools_and_preserves_wrapper_chain() -> None:
    first = history.install_exact_snapshot_secret_history()
    delegate = history._DELEGATE_RUN_TOOL
    attachment_delegate = history._ATTACHMENT_DELEGATE
    second = history.install_exact_snapshot_secret_history()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
    assert delegate is history._DELEGATE_RUN_TOOL
    assert attachment_delegate is history._ATTACHMENT_DELEGATE
    assert "gitleaks" in scanner_worker.TOOL_CATALOG
    assert "trufflehog" in scanner_worker.TOOL_CATALOG
    assert scanner_worker.run_tool is history.history_run_tool
    assert scorecard._secrets_section is history.history_secrets_section
    assert snapshot_handlers._snapshot_evidence_attachment_handler is history.history_attachment_handler
    assert mid_handlers._snapshot_evidence_attachment_handler is history.history_attachment_handler
