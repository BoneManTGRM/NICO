from __future__ import annotations

import json
from pathlib import Path

from scripts.security_audit_gate import build_manifest


def _write(root: Path, name: str, value: object) -> None:
    (root / name).write_text(json.dumps(value), encoding="utf-8")


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
    _write(root, "gitleaks-summary.json", {"status": "completed", "finding_count": 0})
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
    assert any("potential secrets" in item for item in blockers)
    assert any("Bandit reported 1" in item for item in blockers)
