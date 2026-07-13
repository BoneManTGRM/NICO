from __future__ import annotations

import json
import re
from pathlib import Path


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "golden"
    / "synthetic_complete_review_required_assessment.json"
)
UNAVAILABLE_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "golden"
    / "synthetic_unavailable_assessment.json"
)


def _load(path: Path = FIXTURE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_complete_fixture_is_explicitly_synthetic_and_never_live() -> None:
    fixture = _load()

    assert fixture["fixture_name"] == "synthetic_complete_review_required_assessment"
    assert fixture["evidence_kind"] == "synthetic"
    assert fixture["live_claim"] is False
    assert fixture["authorization"] == {
        "status": "fixture_only",
        "scope": "synthetic_repository",
    }
    assert fixture["identity"]["repository"].startswith("example.invalid/")
    assert fixture["identity"]["run_id"].startswith("synthetic-")
    assert fixture["identity"]["scan_id"].startswith("synthetic-")
    assert fixture["identity"]["report_id"].startswith("synthetic-")


def test_every_requested_tool_has_complete_hash_bound_exact_snapshot_evidence() -> None:
    fixture = _load()
    requested = fixture["requested_tools"]
    evidence = fixture["evidence"]
    by_source = {item["source"]: item for item in evidence}

    assert requested == ["pip-audit", "bandit", "semgrep", "gitleaks"]
    assert set(by_source) == set(requested)
    assert len(by_source) == len(requested)

    for source in requested:
        item = by_source[source]
        assert item["status"] == "complete"
        assert item["synthetic"] is True
        assert item["run_id"] == fixture["identity"]["run_id"]
        assert item["scan_id"] == fixture["identity"]["scan_id"]
        assert item["snapshot_commit_sha"] == fixture["identity"]["commit_sha"]
        assert item["finding_count"] == 0
        assert re.fullmatch(r"[0-9a-f]{64}", item["artifact_sha256"])


def test_numeric_fixture_score_never_becomes_certification_or_security_claim() -> None:
    fixture = _load()
    score = fixture["score"]
    claims = fixture["claims"]

    assert score["value"] == 92
    assert score["status"] == "synthetic_fixture_score"
    assert score["source"] == "fixture_only"
    assert score["certification"] is False
    assert "not a live score or certification" in score["reason"]
    assert claims == {
        "vulnerability_free": False,
        "security_certified": False,
        "production_ready": False,
        "all_possible_evidence_collected": False,
    }


def test_complete_evidence_still_requires_human_review_and_blocks_delivery() -> None:
    fixture = _load()

    assert fixture["review"] == {
        "status": "required",
        "approved": False,
        "client_ready": False,
        "reviewer": None,
    }
    assert fixture["repair"] == {
        "automatic_production_change_allowed": False,
        "status": "no_production_action",
    }
    assert fixture["delivery"]["status"] == "blocked"
    assert "do not replace explicit human approval" in fixture["delivery"]["reason"]


def test_golden_pair_covers_unavailable_and_complete_without_changing_truth_boundary() -> None:
    complete = _load()
    unavailable = _load(UNAVAILABLE_FIXTURE)

    assert complete["fixture_name"] != unavailable["fixture_name"]
    assert all(item["status"] == "complete" for item in complete["evidence"])
    assert any(item["status"] == "unavailable" for item in unavailable["evidence"])
    assert complete["review"]["approved"] is False
    assert unavailable["review"]["approved"] is False
    assert complete["delivery"]["status"] == "blocked"
    assert unavailable["delivery"]["status"] == "blocked"
    assert complete["live_claim"] is False
    assert unavailable["live_claim"] is False
