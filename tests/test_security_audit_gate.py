from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_gitleaks_accepts_only_the_exact_public_sara_verifier_digest(tmp_path: Path) -> None:
    _clean_evidence(tmp_path)
    finding = {
        "RuleID": "generic-api-key",
        "Secret": "REDACTED",
        "File": "nico/admin_security.py",
        "StartLine": 14,
        "Match": 'DEPLOYED_SARA_OPERATOR_PASSWORD_SHA256 = "REDACTED"',
        "Fingerprint": "public-verifier-fingerprint",
    }
    _write(tmp_path, "gitleaks.json", [finding])
    _write(tmp_path, "gitleaks-summary.json", {"status": "completed", "finding_count": 1})

    manifest = build_manifest(tmp_path)

    gitleaks = manifest["tools"]["gitleaks"]
    assert gitleaks["blocking"] == 0
    assert gitleaks["approved_public_verifiers"] == 1
    assert gitleaks["triage"][0]["disposition"] == "approved_public_verifier_digest"
    assert manifest["security_gate"]["status"] == "passed"


def test_gitleaks_rejects_public_verifier_lookalikes(tmp_path: Path) -> None:
    _clean_evidence(tmp_path)
    finding = {
        "RuleID": "generic-api-key",
        "Secret": "REDACTED",
        "File": "nico/another_module.py",
        "StartLine": 1,
        "Match": 'DEPLOYED_SARA_OPERATOR_PASSWORD_SHA256 = "REDACTED"',
        "Fingerprint": "lookalike-fingerprint",
    }
    _write(tmp_path, "gitleaks.json", [finding])
    _write(tmp_path, "gitleaks-summary.json", {"status": "completed", "finding_count": 1})

    manifest = build_manifest(tmp_path)

    assert manifest["tools"]["gitleaks"]["blocking"] == 1
    assert manifest["security_gate"]["status"] == "blocked"


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


@pytest.mark.parametrize("path,deployment_id", [
    ("NICO-Ship-Checkpoint.md", "97d2fb09-0716-4cd7-b1ae-51509755dc50"),
    ("NICO-Ship-Checkpoint.md", "132496a3-be53-42f2-aab2-3f812583528a"),
    ("NICO-Ship-Checkpoint.md", "5ef9587d-d432-4246-8ea3-e382c5275860"),
    ("NICO-Ship-Checkpoint.md", "b486f62e-607e-40be-ab5d-219d1cd01f89"),
    ("NICO-Ship-Checkpoint.md", "7e14894a-4d8a-4fc3-8885-08bf7b0c6bb6"),
    ("NICO-Ship-Checkpoint.md", "be548d2c-58f0-401b-ba8c-8f17fe3688ef"),
    ("NICO-Ship-Checkpoint.md", "65874b41-82dc-4b7e-b842-fbd656a00594"),
    ("NICO-Ship-Checkpoint.md", "6b0447a3-1da7-476d-a758-af0ec6c2123b"),
    ("NICO-Ship-Checkpoint.md", "d9d51992-d34a-4348-a83d-1f760faaa6a8"),
    ("docs/operator-report-approval.md", "82eb5f88-2e22-4fe1-a482-44700f464557"),
    ("docs/operator-report-approval.md", "4b198570-42a7-48e7-be91-4d93bd808923"),
    ("docs/human-report-repair-acceptance.md", "57588a18-cd2e-43bf-a46d-4324a60d237a"),
    ("NICO-Ship-Checkpoint.md", "e2897040-1f8c-4559-95fd-44b961ef6c26"),
    ("NICO-Ship-Checkpoint.md", "4b5ff41e-ec40-486c-8461-83475ffa90a9"),
    ("NICO-Ship-Checkpoint.md", "9c1d37e7-7233-41fa-b2a4-41d2cf89302b"),
    ("NICO-Ship-Checkpoint.md", "b60e6737-9ed8-4ad0-b85d-2e771a02710d"),
    ("NICO-Ship-Checkpoint.md", "9097aa8a-f30c-4585-8de6-f5bdf2ffa209"),
])
def test_documented_railway_deployment_id_is_retained_but_other_credentials_block(
    tmp_path: Path, path: str, deployment_id: str,
) -> None:
    _clean_evidence(tmp_path)
    known = {
        "SourceMetadata": {"Data": {"Git": {"file": path}}},
        "DetectorName": "RailwayApp",
        "Verified": False,
        "Raw": deployment_id,
    }
    _write_json_lines(tmp_path, "trufflehog.json", [known])
    manifest = build_manifest(tmp_path)
    evidence = manifest["tools"]["trufflehog"]
    assert manifest["security_gate"]["status"] == "passed"
    assert evidence["finding_count"] == 1
    assert evidence["approved_nonsecret_identifiers"] == 1
    expected = ("approved_nonsecret_project_identifier" if deployment_id == "4b5ff41e-ec40-486c-8461-83475ffa90a9"
                else "approved_nonsecret_service_identifier" if deployment_id == "d9d51992-d34a-4348-a83d-1f760faaa6a8"
                else "approved_nonsecret_thread_identifier" if deployment_id == "9c1d37e7-7233-41fa-b2a4-41d2cf89302b"
                else "approved_nonsecret_deployment_identifier")
    assert evidence["triage"][0]["disposition"] == expected
    assert known["Raw"] not in json.dumps(evidence)
    for changed in (
        {"Verified": True},
        {"Raw": "unknown-credential"},
        {"DetectorName": "Other"},
        {"SourceMetadata": {"Data": {"Git": {"file": "nico/settings.py"}}}},
        {"SourceMetadata": {"Data": {"Git": {"file": (
            "docs/operator-report-approval.md" if "human-report" in path
            else "docs/human-report-repair-acceptance.md"
        )}}}},
    ):
        _write_json_lines(tmp_path, "trufflehog.json", [{**known, **changed}])
        manifest = build_manifest(tmp_path)
        assert manifest["security_gate"]["status"] == "blocked"
        assert manifest["tools"]["trufflehog"]["blocking"] == 1
