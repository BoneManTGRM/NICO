from __future__ import annotations

import json
from pathlib import Path


GOLDEN_DIR = Path(__file__).parent / "fixtures" / "golden"
MANIFEST_PATH = GOLDEN_DIR / "manifest.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fixture_entries() -> tuple[dict, list[tuple[dict, dict]]]:
    manifest = _load(MANIFEST_PATH)
    fixtures = []
    for entry in manifest["fixtures"]:
        path = GOLDEN_DIR / entry["path"]
        fixtures.append((entry, _load(path)))
    return manifest, fixtures


def test_manifest_is_synthetic_and_does_not_claim_live_coverage() -> None:
    manifest, _fixtures = _fixture_entries()

    assert manifest["manifest_version"] == 1
    assert manifest["evidence_kind"] == "synthetic_fixture_manifest"
    assert manifest["live_claim"] is False
    assert "does not replace recorded authorized deployment demonstrations" in manifest["remaining_boundary"]


def test_manifest_paths_exist_and_declared_names_match_payloads() -> None:
    manifest, fixtures = _fixture_entries()

    assert len(fixtures) == 3
    assert len({entry["id"] for entry, _fixture in fixtures}) == len(fixtures)
    assert len({entry["path"] for entry, _fixture in fixtures}) == len(fixtures)
    assert len({entry["fixture_name"] for entry, _fixture in fixtures}) == len(fixtures)

    for entry, fixture in fixtures:
        assert "/" not in entry["path"]
        assert "\\" not in entry["path"]
        assert entry["path"].endswith(".json")
        assert fixture["fixture_name"] == entry["fixture_name"]
        assert fixture["evidence_kind"] == "synthetic"
        assert fixture["live_claim"] is False


def test_fixture_identities_are_unique_and_non_production() -> None:
    _manifest, fixtures = _fixture_entries()
    identities = [fixture["identity"] for _entry, fixture in fixtures]

    assert len({item["run_id"] for item in identities}) == len(identities)
    assert len({item["scan_id"] for item in identities}) == len(identities)
    assert len({item["report_id"] for item in identities}) == len(identities)
    assert len({item["repository"] for item in identities}) == len(identities)
    assert all(item["run_id"].startswith("synthetic-") for item in identities)
    assert all(item["scan_id"].startswith("synthetic-") for item in identities)
    assert all(item["report_id"].startswith("synthetic-") for item in identities)
    assert all(item["repository"].startswith("example.invalid/") for item in identities)


def test_every_fixture_preserves_review_approval_and_delivery_boundaries() -> None:
    manifest, fixtures = _fixture_entries()
    required = manifest["required_boundaries"]

    assert required == {
        "synthetic_only": True,
        "live_claim": False,
        "human_review_required": True,
        "approved": False,
        "client_ready": False,
        "delivery_blocked": True,
        "certification_forbidden": True,
        "automatic_production_change_forbidden": True,
    }

    for _entry, fixture in fixtures:
        review = fixture["review"]
        assert review["status"] == "required"
        assert review["approved"] is False
        assert review["client_ready"] is False
        assert fixture["delivery"]["status"] == "blocked"

        score = fixture.get("score")
        if isinstance(score, dict):
            assert score.get("certification") is not True

        repair = fixture.get("repair") or fixture.get("repair_plan") or {}
        assert repair.get("automatic_production_change_allowed") is not True


def test_manifest_coverage_union_matches_declared_requirements() -> None:
    manifest, fixtures = _fixture_entries()
    declared = set(manifest["coverage_requirements"])
    observed = {
        item
        for entry, _fixture in fixtures
        for item in entry.get("coverage", [])
    }

    assert observed == declared
    assert {
        "unavailable_evidence",
        "complete_review_boundary",
        "mixed_risk_repair_boundary",
    } == {entry["id"] for entry, _fixture in fixtures}


def test_manifest_never_labels_fixture_score_as_live_or_certifying() -> None:
    _manifest, fixtures = _fixture_entries()

    numeric_scores = []
    for _entry, fixture in fixtures:
        score = fixture.get("score") or {}
        if isinstance(score.get("value"), (int, float)):
            numeric_scores.append(score)
            assert score.get("source") == "fixture_only"
            assert score.get("certification") is False
            assert "synthetic" in str(score.get("status") or "")

    assert len(numeric_scores) == 2
