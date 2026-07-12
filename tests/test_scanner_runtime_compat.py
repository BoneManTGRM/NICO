from __future__ import annotations

import time
from pathlib import Path

import nico.scanner_runtime_compat as compat


def test_osv_prefers_current_v2_cli_and_keeps_v1_fallback(tmp_path: Path) -> None:
    commands = compat._osv_commands(tmp_path)

    assert commands[0][0] == "v2"
    assert commands[0][1][:3] == ["osv-scanner", "scan", "source"]
    assert "--recursive" in commands[0][1]
    assert commands[1][0] == "v1-fallback"


def test_clean_osv_json_is_completed_evidence(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(compat.scanner_worker, "ENABLE_SCANNER_EXECUTION", True)
    monkeypatch.setattr(compat.shutil, "which", lambda _name: "/usr/local/bin/osv-scanner")
    monkeypatch.setattr(
        compat,
        "_communicate",
        lambda *args, **kwargs: (0, '{"results": []}', "", 0.1, False),
    )

    result = compat._run_osv(
        {"intent": "OSV dependency review"},
        tmp_path,
        {"PATH": "/usr/local/bin"},
        time.monotonic() + 30,
    )

    assert result["status"] == "passed"
    assert result["execution_completed"] is True
    assert result["execution_status"] == "completed_clean"
    assert result["finding_count"] == 0


def test_nonzero_empty_osv_output_is_not_clean_evidence(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(compat.scanner_worker, "ENABLE_SCANNER_EXECUTION", True)
    monkeypatch.setattr(compat.shutil, "which", lambda _name: "/usr/local/bin/osv-scanner")
    monkeypatch.setattr(
        compat,
        "_communicate",
        lambda *args, **kwargs: (1, '{"results": []}', "scanner exited nonzero", 0.1, False),
    )

    result = compat._run_osv(
        {"intent": "OSV dependency review"},
        tmp_path,
        {"PATH": "/usr/local/bin"},
        time.monotonic() + 30,
    )

    assert result["status"] == "failed"
    assert result["execution_completed"] is False
    assert result["execution_status"] == "execution_failed"


def test_history_commands_use_current_gitleaks_and_bounded_trufflehog_cli(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    gitleaks = compat._history_command("gitleaks", tmp_path, report)
    trufflehog = compat._history_command("trufflehog", tmp_path, report)

    assert gitleaks[:2] == ["gitleaks", "git"]
    assert "detect" not in gitleaks
    assert "--report-path" in gitleaks
    assert trufflehog[:2] == ["trufflehog", "git"]
    assert "--no-update" in trufflehog
    assert "--no-verification" in trufflehog


def test_nonzero_empty_gitleaks_output_is_not_clean_evidence(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(compat.scanner_worker, "ENABLE_SCANNER_EXECUTION", True)
    monkeypatch.setattr(compat.shutil, "which", lambda _name: "/usr/local/bin/gitleaks")
    monkeypatch.setattr(
        compat.history,
        "history_metadata",
        lambda _path: {
            "full_history_covered": True,
            "history_depth": "full",
            "history_commit_count": 400,
            "snapshot_commit_sha": "a" * 40,
        },
    )
    monkeypatch.setattr(
        compat,
        "_communicate",
        lambda *args, **kwargs: (1, "", "nonzero without report", 0.1, False),
    )

    result = compat._run_history(
        "gitleaks",
        {"binary": "gitleaks", "intent": "Exact git-history credential review"},
        tmp_path,
        {"PATH": "/usr/local/bin"},
        time.monotonic() + 30,
    )

    assert result["status"] == "failed"
    assert result["execution_completed"] is False
    assert result["execution_status"] == "execution_failed"


def test_osv_findings_cap_dependency_score_and_remain_visible(monkeypatch) -> None:
    monkeypatch.setattr(
        compat,
        "_DEPENDENCY_SECTION_DELEGATE",
        lambda _repo, _scanner: {
            "id": "dependency_health",
            "label": "Dependency / Library Ecosystem",
            "score": 82,
            "status": "green",
            "evidence": ["Manifest evidence attached."],
            "verified_claims": ["Manifest evidence attached."],
            "findings": [],
            "unavailable": [],
        },
    )
    scanner = {
        "scanner_results": [
            {
                "scanner": "osv-scanner",
                "execution_completed": True,
                "execution_status": "completed_with_findings",
                "finding_count": 3,
                "runtime_compat_version": compat.SCANNER_RUNTIME_COMPAT_VERSION,
            }
        ]
    }

    section = compat.dependency_section_with_osv_triage({}, scanner)

    assert section["score"] <= 55
    assert section["status"] in {"yellow", "red"}
    assert section["dependency_scanner_triage"]["osv_vulnerability_record_count"] == 3
    assert any("3 OSV vulnerability record" in item for item in section["findings"])
