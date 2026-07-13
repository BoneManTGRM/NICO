import json
from pathlib import Path


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "golden"
    / "synthetic_unavailable_assessment.json"
)


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_golden_fixture_is_explicitly_synthetic_and_not_live() -> None:
    fixture = _load_fixture()

    assert fixture["evidence_kind"] == "synthetic"
    assert fixture["live_claim"] is False
    assert fixture["authorization"] == {
        "status": "fixture_only",
        "scope": "synthetic_repository",
    }
    assert fixture["identity"]["run_id"].startswith("synthetic-")
    assert fixture["identity"]["scan_id"].startswith("synthetic-")
    assert fixture["identity"]["report_id"].startswith("synthetic-")
    assert fixture["identity"]["repository"].startswith("example.invalid/")


def test_unavailable_evidence_never_receives_completion_or_score_credit() -> None:
    fixture = _load_fixture()
    unavailable = [
        item for item in fixture["evidence"] if item["status"] == "unavailable"
    ]

    assert unavailable
    assert all(item["synthetic"] is True for item in fixture["evidence"])
    assert all(item.get("reason") for item in unavailable)
    assert fixture["score"]["value"] is None
    assert fixture["score"]["status"] == "insufficient_evidence"


def test_fixture_remains_fail_closed_for_review_and_delivery() -> None:
    fixture = _load_fixture()

    assert fixture["review"] == {
        "status": "required",
        "approved": False,
        "client_ready": False,
    }
    assert fixture["delivery"]["status"] == "blocked"
    assert "synthetic" in fixture["delivery"]["reason"]
    assert "unapproved" in fixture["delivery"]["reason"]
