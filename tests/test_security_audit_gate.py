from __future__ import annotations

import json
from pathlib import Path

from scripts.security_audit_gate import build_manifest


def _write(root: Path, name: str, value: object) -> None:
    (root / name).write_text(json.dumps(value), encoding="utf-8")


def _write_json_lines(root: Path, name: str, values: list[dict[str, object]]) -> None:
    (root / name).write_text(
        "".join(json.dumps(value) + "\n" for value in values),
        encoding="utf-8",
    )


def _clean_evidence(root: Path) -> None:
    _write(root, "pip-audit.json", {"dependencies": [{"name": "nico", "vulns": []}]})
    _write(
        root,
        "npm-audit.json",
        {
            "metadata": {
                "vulnerabilities": {
                    "info": 0,
                    "low": 0,
                    "moderate": 0,
                    "high": 0,
                    "critical": 0,
                    "total": 0,
                }
            }
        },
    )
    _write(root, "bandit.json", {"results": []})
    _write(
        root,
        "bandit-triage.json",
        {"blocking": 0, "needs_review": 0, "candidate_false_positive": 0},
    )
    _write(root, "semgrep.json", {"results": [], "errors": []})
    _write(root, "osv-scanner.json", {"results": []})
    _write(root, "gitleaks.json", [])
    _write(root, "gitleaks-summary.json", {"status": "completed", "finding_count": 0})
    _write_json_lines(root, "trufflehog.json", [])
    _write(root, "trufflehog-summary.json", {"status": "completed", "finding_count": 0})
    _write(root, "typescript-summary.json", {"status": "completed_clean", "finding_count": 0})
    _write(
        root,
        "eslint-summary.json",
        {
            "status": "unavailable_not_configured",
            "finding_count": 0,
            "error_count": 0,
            "warning_count": 0,
            "configured": False,
        },
    )
    _write(root, "credential-scan.json", {"findings": []})


def test_clean_complete_evidence_passes_and_preserves_delivery_guardrails(tmp_path: Path) -> None:
    _clean_evidence(tmp_path)
    manifest = build_manifest(tmp_path, repository="BoneManTGRM/NICO", run_id="123")
    assert manifest["worker_execution_state"] == "completed"
    assert manifest["security_gate"]["status"] == "passed"
    assert manifest["security_gate"]["blockers"] == []
    assert manifest["human_review_required"] is True
    assert manifest["client_delivery_allowed"] is False


def test_missing_required_scanner_fails_closed(tmp_path: Path) -> None:
    _clean_evidence(tmp_path)
    (tmp_path / "semgrep.json").unlink()
    manifest = build_manifest(tmp_path)
    assert manifest["worker_execution_state"] == "failed"
    assert any("required scanner semgrep" in item for item in manifest["security_gate"]["blockers"])


def test_any_known_production_dependency_vulnerability_blocks(tmp_path: Path) -> None:
    _clean_evidence(tmp_path)
    _write(
        tmp_path,
        "npm-audit.json",
        {
            "metadata": {
                "vulnerabilities": {
                    "info": 0,
                    "low": 1,
                    "moderate": 0,
                    "high": 0,
                    "critical": 0,
                    "total": 1,
                }
            }
        },
    )
    manifest = build_manifest(tmp_path)
    assert any("npm audit reported 1" in item for item in manifest["security_gate"]["blockers"])


def test_secret_and_high_bandit_findings_block(tmp_path: Path) -> None:
    _clean_evidence(tmp_path)
    _write(tmp_path, "credential-scan.json", {"findings": [{"type": "private_key"}]})
    _write(
        tmp_path,
        "bandit-triage.json",
        {"blocking": 1, "needs_review": 0, "candidate_false_positive": 0},
    )
    manifest = build_manifest(tmp_path)
    blockers = manifest["security_gate"]["blockers"]
    assert any("high-confidence secrets" in item for item in blockers)
    assert any("Bandit reported 1" in item for item in blockers)


def test_semgrep_workflow_shell_injection_blocks_but_review_rule_is_retained(tmp_path: Path) -> None:
    _clean_evidence(tmp_path)
    _write(
        tmp_path,
        "semgrep.json",
        {
            "results": [
                {
                    "check_id": "yaml.github-actions.security.run-shell-injection.run-shell-injection",
                    "path": ".github/workflows/release.yml",
                },
                {
                    "check_id": "python.lang.security.audit.formatted-sql-query.formatted-sql-query",
                    "path": "nico/store.py",
                },
            ],
            "errors": [],
        },
    )
    manifest = build_manifest(tmp_path)
    semgrep = manifest["tools"]["semgrep"]
    assert semgrep["blocking"] == 1
    assert semgrep["needs_review"] == 1
    assert any("Semgrep reported 1" in item for item in manifest["security_gate"]["blockers"])
    assert any("semgrep retained 1" in item for item in manifest["security_gate"]["review_required"])


def test_gitleaks_redacted_test_fixture_is_retained_without_blocking(tmp_path: Path) -> None:
    _clean_evidence(tmp_path)
    finding = {
        "RuleID": "generic-api-key",
        "Secret": "REDACTED",
        "File": "tests/test_redaction.py",
        "StartLine": 12,
        "Fingerprint": "fixture-fingerprint",
    }
    _write(tmp_path, "gitleaks.json", [finding])
    _write(tmp_path, "gitleaks-summary.json", {"status": "completed", "finding_count": 1})
    manifest = build_manifest(tmp_path)
    gitleaks = manifest["tools"]["gitleaks"]
    assert gitleaks["blocking"] == 0
    assert gitleaks["approved_test_placeholders"] == 1
    assert manifest["security_gate"]["status"] == "passed"
    assert any("gitleaks retained 1" in item for item in manifest["security_gate"]["review_required"])


def test_gitleaks_non_placeholder_finding_blocks_even_in_tests(tmp_path: Path) -> None:
    _clean_evidence(tmp_path)
    _write(
        tmp_path,
        "gitleaks.json",
        [
            {
                "RuleID": "generic-api-key",
                "Secret": "not-a-redacted-placeholder",
                "File": "tests/test_redaction.py",
                "StartLine": 12,
                "Fingerprint": "unsafe-fingerprint",
            }
        ],
    )
    _write(tmp_path, "gitleaks-summary.json", {"status": "completed", "finding_count": 1})
    manifest = build_manifest(tmp_path)
    assert manifest["tools"]["gitleaks"]["blocking"] == 1
    assert any("gitleaks reported 1" in item for item in manifest["security_gate"]["blockers"])


def _trufflehog_finding(*, path: str, verified: bool) -> dict[str, object]:
    return {
        "SourceMetadata": {"Data": {"Git": {"file": path}}},
        "DetectorName": "Postgres",
        "Verified": verified,
        "Raw": "not-retained-in-manifest",
    }


def test_trufflehog_unverified_test_fixture_is_retained_without_exposing_raw_secret(tmp_path: Path) -> None:
    _clean_evidence(tmp_path)
    _write_json_lines(
        tmp_path,
        "trufflehog.json",
        [_trufflehog_finding(path="tests/test_database.py", verified=False)],
    )
    _write(tmp_path, "trufflehog-summary.json", {"status": "completed", "finding_count": 1})
    manifest = build_manifest(tmp_path)
    trufflehog = manifest["tools"]["trufflehog"]
    assert trufflehog["blocking"] == 0
    assert trufflehog["approved_test_placeholders"] == 1
    assert "Raw" not in json.dumps(trufflehog)
    assert manifest["security_gate"]["status"] == "passed"


def test_trufflehog_verified_or_non_fixture_finding_blocks(tmp_path: Path) -> None:
    _clean_evidence(tmp_path)
    _write_json_lines(
        tmp_path,
        "trufflehog.json",
        [
            _trufflehog_finding(path="tests/test_database.py", verified=True),
            _trufflehog_finding(path="nico/settings.py", verified=False),
        ],
    )
    _write(tmp_path, "trufflehog-summary.json", {"status": "completed", "finding_count": 2})
    manifest = build_manifest(tmp_path)
    assert manifest["tools"]["trufflehog"]["blocking"] == 2
    assert any("trufflehog reported 2" in item for item in manifest["security_gate"]["blockers"])
