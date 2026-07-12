from __future__ import annotations

import json
import time
from pathlib import Path

import nico.exact_snapshot_static_triage as triage
import nico.full_assessment_scorecard as scorecard
import nico.scanner_worker as scanner_worker


def _repo(risk_hits: int = 0) -> dict:
    return {"code_signal_evidence": {"risk_pattern_hits": risk_hits}}


def _scanner(*results: dict) -> dict:
    return {
        "status": "attached",
        "tools_run": [str(item.get("scanner")) for item in results if item.get("status") in {"passed", "failed", "timeout", "error"}],
        "failed_tools": [str(item.get("scanner")) for item in results if item.get("status") in {"failed", "error"}],
        "timed_out_tools": [str(item.get("scanner")) for item in results if item.get("status") == "timeout"],
        "scanner_results": list(results),
    }


def _repo_evidence(risk_hits: int = 0) -> dict:
    return {"code_signal_evidence": {"risk_pattern_hits": risk_hits}}


def test_bandit_parser_separates_material_review_and_test_only_findings() -> None:
    payload = {
        "results": [
            {
                "test_id": "B602",
                "filename": "nico/runtime.py",
                "line_number": 41,
                "issue_severity": "HIGH",
                "issue_confidence": "HIGH",
                "issue_text": "subprocess shell execution",
                "code": "must never be retained",
            },
            {
                "test_id": "B101",
                "filename": "tests/test_runtime.py",
                "line_number": 9,
                "issue_severity": "LOW",
                "issue_confidence": "HIGH",
                "issue_text": "assert used",
            },
            {
                "test_id": "B404",
                "filename": "nico/worker.py",
                "line_number": 12,
                "issue_severity": "LOW",
                "issue_confidence": "HIGH",
                "issue_text": "subprocess import",
            },
        ]
    }

    findings, error = triage.parse_static_findings("bandit", json.dumps(payload))

    assert error is None
    assert len(findings) == 3
    assert sum(bool(item["material"]) for item in findings) == 1
    assert sum(bool(item["review_required"]) for item in findings) == 1
    assert sum(bool(item["test_only"]) for item in findings) == 1
    assert "must never be retained" not in repr(findings)


def test_semgrep_parser_uses_rule_severity_without_source_snippets() -> None:
    payload = {
        "results": [
            {
                "check_id": "python.lang.security.audit.subprocess-shell-true",
                "path": "nico/runner.py",
                "start": {"line": 18},
                "extra": {
                    "severity": "ERROR",
                    "message": "Shell execution requires review",
                    "lines": "secret source snippet must not be retained",
                    "metadata": {"confidence": "HIGH"},
                },
            },
            {
                "check_id": "typescript.react.security.audit.react-dangerouslysetinnerhtml",
                "path": "apps/web/page.test.tsx",
                "start": {"line": 25},
                "extra": {"severity": "WARNING", "message": "test fixture", "metadata": {}},
            },
        ]
    }

    findings, error = triage.parse_static_findings("semgrep", json.dumps(payload))

    assert error is None
    assert len(findings) == 2
    assert findings[0]["material"] is True
    assert findings[1]["test_only"] is True
    assert "secret source snippet" not in repr(findings)


def test_parseable_nonzero_bandit_exit_is_completed_evidence(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "results": [
            {
                "test_id": "B101",
                "filename": "tests/test_example.py",
                "line_number": 3,
                "issue_severity": "LOW",
                "issue_confidence": "HIGH",
                "issue_text": "assert used",
            }
        ]
    }
    (tmp_path / "sample.py").write_text("value = 1\n", encoding="utf-8")

    class FakeProcess:
        pid = 123
        returncode = 1

        def communicate(self, timeout=None):
            return json.dumps(payload), ""

    monkeypatch.setattr(triage.shutil, "which", lambda _binary: "/usr/bin/bandit")
    monkeypatch.setattr(triage.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    result = triage._run_structured_static_tool(
        "bandit",
        {"binary": "bandit", "intent": "Python static review", "tier": "static"},
        tmp_path,
        {"PATH": "/usr/bin"},
        time.monotonic() + 30,
    )

    assert result["status"] == "passed"
    assert result["execution_completed"] is True
    assert result["execution_status"] == "completed_with_findings"
    assert result["finding_count"] == 1
    assert result["material_finding_count"] == 0
    assert result["excluded_test_finding_count"] == 1
    assert "assert used" not in result["safe_output_preview"]


def test_static_score_uses_material_findings_not_raw_nonzero_exit_counts() -> None:
    clean_built_in = {
        "scanner": "nico-static",
        "status": "passed",
        "finding_count": 0,
        "files_scanned": 240,
    }
    bandit = {
        "scanner": "bandit",
        "status": "passed",
        "execution_completed": True,
        "finding_count": 85,
        "material_finding_count": 0,
        "review_finding_count": 15,
        "excluded_test_finding_count": 70,
        "evidence_summary": "Bandit completed with classified findings.",
    }
    semgrep = {
        "scanner": "semgrep",
        "status": "passed",
        "execution_completed": True,
        "finding_count": 38,
        "material_finding_count": 0,
        "review_finding_count": 8,
        "excluded_test_finding_count": 30,
        "evidence_summary": "Semgrep completed with classified findings.",
    }

    section = triage.triaged_static_section(_repo_evidence(), _scanner(clean_built_in, bandit, semgrep))

    assert section["score"] >= 80
    assert section["status"] == "green"
    assert section["static_triage"]["material_finding_count"] == 0
    assert section["static_triage"]["review_finding_count"] == 23
    assert section["static_triage"]["excluded_test_finding_count"] == 100
    assert any("Human-review 23" in finding for finding in section["findings"])


def test_material_production_findings_keep_static_score_review_limited() -> None:
    clean_built_in = {
        "scanner": "nico-static",
        "status": "passed",
        "finding_count": 0,
        "files_scanned": 240,
    }
    bandit = {
        "scanner": "bandit",
        "status": "passed",
        "execution_completed": True,
        "finding_count": 4,
        "material_finding_count": 2,
        "review_finding_count": 2,
        "excluded_test_finding_count": 0,
        "evidence_summary": "Bandit completed with material findings.",
    }
    semgrep = {
        "scanner": "semgrep",
        "status": "passed",
        "execution_completed": True,
        "finding_count": 1,
        "material_finding_count": 1,
        "review_finding_count": 0,
        "excluded_test_finding_count": 0,
        "evidence_summary": "Semgrep completed with a material finding.",
    }

    section = triage.triaged_static_section(_repo_evidence(), _scanner(clean_built_in, bandit, semgrep))

    assert section["score"] <= 74
    assert section["status"] == "yellow"
    assert section["static_triage"]["material_finding_count"] == 3
    assert any("Prioritize 3 material" in finding for finding in section["findings"])


def test_execution_failure_remains_a_coverage_failure() -> None:
    clean_built_in = {"scanner": "nico-static", "status": "passed", "finding_count": 0, "files_scanned": 20}
    bandit = {
        "scanner": "bandit",
        "status": "failed",
        "execution_completed": False,
        "execution_status": "execution_failed",
    }

    section = triage.triaged_static_section(_repo_evidence(), _scanner(clean_built_in, bandit))

    assert section["static_triage"]["execution_failures"] == 1
    assert any("did not both produce parseable" in note for note in section["unavailable"])


def test_installer_wraps_scanner_once_and_rebinds_static_scoring() -> None:
    first = triage.install_exact_snapshot_static_triage()
    delegate = triage._DELEGATE_RUN_TOOL
    second = triage.install_exact_snapshot_static_triage()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
    assert delegate is triage._DELEGATE_RUN_TOOL
    assert scanner_worker.run_tool is triage.triaged_run_tool
    assert scorecard._static_section is triage.triaged_static_section
