from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = REPO_ROOT / "docs" / "PROJECT_STATUS.md"


def _status_text() -> str:
    return STATUS_PATH.read_text(encoding="utf-8")


def test_project_status_records_eleven_completed_workstreams() -> None:
    text = _status_text()
    assert "Completed major workstreams: **11 of 12**." in text

    roadmap = text.split("## Completion roadmap", 1)[1].split("## Remaining execution order", 1)[0]
    assert len(re.findall(r"^- \[x\] ", roadmap, flags=re.MULTILINE)) == 11
    assert len(re.findall(r"^- \[ \] ", roadmap, flags=re.MULTILINE)) == 1
    assert "- [x] CLI/service modularization across configuration, scanning, scoring, repair, drift, reporting, verification, and persistence." in roadmap
    assert "- [ ] Deployed browser/API E2E proof for unified Express, Mid, and Full with exact-run identity and no duplicate starts." in roadmap


def test_only_deployed_assessment_proof_remains_in_execution_order() -> None:
    text = _status_text()
    remaining = text.split("## Remaining execution order", 1)[1].split("## CLI/service modularization completion evidence", 1)[0]
    assert "1. Deployed Express, Mid, and Full browser/API E2E proof." in remaining
    assert "CLI and service modularization" not in remaining
    assert "1–2 small, reviewable pull requests" in remaining


def test_modularization_evidence_preserves_truth_boundaries() -> None:
    text = _status_text()
    evidence = text.split("## CLI/service modularization completion evidence", 1)[1].split("## Resilience completion evidence", 1)[0]

    for module_path in (
        "nico/local_runtime_config.py",
        "nico/local_scan_engine.py",
        "nico/local_scan_service.py",
        "nico/local_governance_service.py",
        "nico/local_store.py",
        "nico/local_scoring_repair_service.py",
        "nico/local_reporting_service.py",
        "nico/local_verification_service.py",
        "nico/local_memory_service.py",
        "nico/cli_entrypoint.py",
        "nico/cli.py",
    ):
        assert (REPO_ROOT / module_path).exists(), f"missing modularization evidence path: {module_path}"

    assert "does not claim deployed Express/Mid/Full assessment proof" in evidence
    assert "approved reports" in evidence
    assert "client readiness" in evidence
    assert "autonomous repairs" in evidence
    assert "elimination of all defects" in evidence


def test_release_truth_binds_to_verified_modularization_commit() -> None:
    text = _status_text()
    assert "3ca12001cea9ce3e17e5c5d23c904edd624d932b" in text
    assert "Convert nico.cli into a compatibility facade (#386)" in text
    assert "configured Vercel and Railway deployment checks passed" in text
    assert "deployed Express, Mid, and Full browser/API E2E proof remains incomplete" in text
