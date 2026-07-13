from __future__ import annotations

import json
import re
from pathlib import Path


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "golden"
    / "synthetic_mixed_risk_repair_assessment.json"
)


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_mixed_risk_fixture_is_explicitly_synthetic_and_snapshot_bound() -> None:
    fixture = _load()

    assert fixture["evidence_kind"] == "synthetic"
    assert fixture["live_claim"] is False
    assert fixture["authorization"] == {
        "status": "fixture_only",
        "scope": "synthetic_repository",
    }
    assert fixture["identity"]["repository"].startswith("example.invalid/")
    assert fixture["identity"]["commit_sha"] == "2" * 40
    for item in fixture["evidence"]:
        assert item["synthetic"] is True
        assert item["snapshot_commit_sha"] == fixture["identity"]["commit_sha"]
        if item["status"] == "complete":
            assert re.fullmatch(r"[0-9a-f]{64}", item["artifact_sha256"])


def test_complete_evidence_binds_findings_while_failed_evidence_gets_no_credit() -> None:
    fixture = _load()
    evidence = {item["source"]: item for item in fixture["evidence"]}
    findings = {item["finding_id"]: item for item in fixture["findings"]}

    assert evidence["gitleaks"]["status"] == "complete"
    assert evidence["pip-audit"]["status"] == "complete"
    assert evidence["semgrep"]["status"] == "failed"
    assert "no passing credit" in evidence["semgrep"]["reason"]
    assert evidence["gitleaks"]["finding_ids"] == ["synthetic-finding-secret-0001"]
    assert evidence["pip-audit"]["finding_ids"] == ["synthetic-finding-dependency-0001"]
    assert set(findings) == {
        "synthetic-finding-secret-0001",
        "synthetic-finding-dependency-0001",
    }
    assert all(item["status"] == "evidence_bound" for item in findings.values())


def test_findings_do_not_claim_real_credentials_exposure_or_exploitability() -> None:
    fixture = _load()
    findings = {item["finding_id"]: item for item in fixture["findings"]}

    secret = findings["synthetic-finding-secret-0001"]
    dependency = findings["synthetic-finding-dependency-0001"]
    assert secret["production_secret_confirmed"] is False
    assert secret["exploitability_confirmed"] is False
    assert dependency["production_exposure_confirmed"] is False
    assert dependency["exploitability_confirmed"] is False
    assert "without claiming a real credential or exploit" in secret["reason"]
    assert "without claiming production exposure" in dependency["reason"]


def test_score_discloses_failed_evidence_and_never_becomes_certification() -> None:
    fixture = _load()
    score = fixture["score"]

    assert score["value"] == 61
    assert score["status"] == "synthetic_evidence_limited_score"
    assert score["source"] == "fixture_only"
    assert score["certification"] is False
    assert any("Semgrep evidence failed" in item for item in score["limitations"])
    assert any("do not prove production exposure" in item for item in score["limitations"])


def test_repairs_are_draft_only_and_require_verification_and_rollback() -> None:
    fixture = _load()
    plan = fixture["repair_plan"]

    assert plan["status"] == "draft_requires_review"
    assert plan["automatic_production_change_allowed"] is False
    assert len(plan["candidates"]) == 2
    assert {item["finding_id"] for item in plan["candidates"]} == {
        "synthetic-finding-secret-0001",
        "synthetic-finding-dependency-0001",
    }
    assert all(item["verification"] for item in plan["candidates"])
    assert all(item["rollback"] for item in plan["candidates"])


def test_risk_findings_and_failed_evidence_keep_review_and_delivery_closed() -> None:
    fixture = _load()

    assert fixture["review"]["status"] == "required"
    assert fixture["review"]["approved"] is False
    assert fixture["review"]["client_ready"] is False
    assert any("failed Semgrep evidence" in item for item in fixture["review"]["required_decisions"])
    assert fixture["delivery"]["status"] == "blocked"
    assert "failed evidence" in fixture["delivery"]["reason"]
    assert "unapproved repair candidates" in fixture["delivery"]["reason"]
