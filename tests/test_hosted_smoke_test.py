from __future__ import annotations

from copy import deepcopy

from nico.hosted_smoke_test import SMOKE_TESTS, build_hosted_smoke_test


def production_smoke_artifact() -> dict:
    return {
        "schema_version": 1,
        "evidence_kind": "authorized_live_production_smoke",
        "live_claim": True,
        "authorization_confirmed": True,
        "status": "passed",
        "proof": {
            "one_start_per_tier": True,
            "exact_run_continuation": True,
            "human_review_boundary_preserved": True,
            "no_client_ready_claim": True,
        },
        "tiers": [
            {
                "tier": "express",
                "status": "passed",
                "start_count": 1,
                "run_id": "",
                "polled_single_exact_status_url": True,
                "human_review_required": True,
                "client_ready": False,
            },
            {
                "tier": "mid",
                "status": "passed",
                "start_count": 1,
                "run_id": "midrun_exact_1",
                "polled_single_exact_status_url": True,
                "human_review_required": True,
                "client_ready": False,
            },
            {
                "tier": "full",
                "status": "passed",
                "start_count": 1,
                "run_id": "fullrun_exact_1",
                "polled_single_exact_status_url": True,
                "human_review_required": True,
                "client_ready": False,
            },
        ],
    }


def complete_evidence() -> dict:
    evidence = {}
    for case in SMOKE_TESTS:
        if case["evidence_key"] == "production_assessment_smoke":
            evidence[case["evidence_key"]] = production_smoke_artifact()
        else:
            evidence[case["evidence_key"]] = {"status": case.get("required_status") or "ok"}
    return evidence


def test_hosted_smoke_test_passes_with_all_evidence():
    result = build_hosted_smoke_test({"evidence": complete_evidence()})

    assert result["artifact_schema"] == "nico.hosted_smoke_test.v1"
    assert result["contract_version"] == 2
    assert result["status"] == "passed_smoke_test"
    assert result["readiness_score"] == 100
    assert result["missing_evidence"] == []
    assert result["failed_evidence"] == []
    tier_case = next(case for case in result["cases"] if case["id"] == "production_assessment_tiers")
    assert tier_case["passed"] is True
    assert "one start per tier" in tier_case["note"]


def test_hosted_smoke_test_tracks_missing_evidence():
    result = build_hosted_smoke_test({"evidence": {"health": {"status": "ok"}}})

    assert result["status"] == "incomplete_smoke_test"
    assert result["readiness_score"] < 100
    assert "targets" in result["missing_evidence"]
    assert "production_assessment_smoke" in result["missing_evidence"]
    assert result["human_review_required"] is True


def test_hosted_smoke_test_fails_on_bad_required_status():
    evidence = complete_evidence()
    evidence["health"] = {"status": "error"}

    result = build_hosted_smoke_test({"evidence": evidence})

    assert result["status"] == "failed_smoke_test"
    assert "health" in result["failed_evidence"]
    assert result["cases"][0]["result"] == "failed"


def test_synthetic_tier_fixture_cannot_satisfy_live_production_proof():
    evidence = complete_evidence()
    evidence["production_assessment_smoke"]["live_claim"] = False
    evidence["production_assessment_smoke"]["evidence_kind"] = "synthetic_production_smoke_fixture"

    result = build_hosted_smoke_test({"evidence": evidence})

    assert result["status"] == "failed_smoke_test"
    assert result["failed_evidence"] == ["production_assessment_smoke"]
    tier_case = next(case for case in result["cases"] if case["id"] == "production_assessment_tiers")
    assert "not authorized live proof" in tier_case["note"]


def test_missing_full_tier_fails_closed():
    evidence = complete_evidence()
    evidence["production_assessment_smoke"]["tiers"] = [
        item for item in evidence["production_assessment_smoke"]["tiers"] if item["tier"] != "full"
    ]

    result = build_hosted_smoke_test({"evidence": evidence})

    assert result["status"] == "failed_smoke_test"
    tier_case = next(case for case in result["cases"] if case["id"] == "production_assessment_tiers")
    assert "missing tier proof: full" in tier_case["note"]


def test_duplicate_start_or_changed_continuation_proof_fails_closed():
    evidence = complete_evidence()
    artifact = evidence["production_assessment_smoke"]
    mid = next(item for item in artifact["tiers"] if item["tier"] == "mid")
    mid["start_count"] = 2

    result = build_hosted_smoke_test({"evidence": evidence})

    assert result["status"] == "failed_smoke_test"
    tier_case = next(case for case in result["cases"] if case["id"] == "production_assessment_tiers")
    assert "exactly one start request" in tier_case["note"]

    evidence = complete_evidence()
    artifact = evidence["production_assessment_smoke"]
    full = next(item for item in artifact["tiers"] if item["tier"] == "full")
    full["polled_single_exact_status_url"] = False

    result = build_hosted_smoke_test({"evidence": evidence})

    assert result["status"] == "failed_smoke_test"
    tier_case = next(case for case in result["cases"] if case["id"] == "production_assessment_tiers")
    assert "exact-run status continuation" in tier_case["note"]


def test_missing_review_boundary_or_client_ready_claim_fails_closed():
    evidence = complete_evidence()
    express = next(item for item in evidence["production_assessment_smoke"]["tiers"] if item["tier"] == "express")
    express["human_review_required"] = False

    result = build_hosted_smoke_test({"evidence": evidence})

    assert result["status"] == "failed_smoke_test"
    tier_case = next(case for case in result["cases"] if case["id"] == "production_assessment_tiers")
    assert "human-review boundary" in tier_case["note"]

    evidence = deepcopy(complete_evidence())
    full = next(item for item in evidence["production_assessment_smoke"]["tiers"] if item["tier"] == "full")
    full["client_ready"] = True

    result = build_hosted_smoke_test({"evidence": evidence})

    assert result["status"] == "failed_smoke_test"
    tier_case = next(case for case in result["cases"] if case["id"] == "production_assessment_tiers")
    assert "non-client-ready boundary" in tier_case["note"]
