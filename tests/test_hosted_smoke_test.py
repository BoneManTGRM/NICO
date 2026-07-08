from __future__ import annotations

from nico.hosted_smoke_test import SMOKE_TESTS, build_hosted_smoke_test


def test_hosted_smoke_test_passes_with_all_evidence():
    evidence = {case["evidence_key"]: {"status": case.get("required_status") or "ok"} for case in SMOKE_TESTS}

    result = build_hosted_smoke_test({"evidence": evidence})

    assert result["artifact_schema"] == "nico.hosted_smoke_test.v1"
    assert result["status"] == "passed_smoke_test"
    assert result["readiness_score"] == 100
    assert result["missing_evidence"] == []
    assert result["failed_evidence"] == []


def test_hosted_smoke_test_tracks_missing_evidence():
    result = build_hosted_smoke_test({"evidence": {"health": {"status": "ok"}}})

    assert result["status"] == "incomplete_smoke_test"
    assert result["readiness_score"] < 100
    assert "targets" in result["missing_evidence"]
    assert result["human_review_required"] is True


def test_hosted_smoke_test_fails_on_bad_required_status():
    evidence = {case["evidence_key"]: {"status": case.get("required_status") or "ok"} for case in SMOKE_TESTS}
    evidence["health"] = {"status": "error"}

    result = build_hosted_smoke_test({"evidence": evidence})

    assert result["status"] == "failed_smoke_test"
    assert "health" in result["failed_evidence"]
    assert result["cases"][0]["result"] == "failed"
