from __future__ import annotations

from copy import deepcopy

from nico.cross_tier_two_pass_verification_v1 import verify_two_consecutive_release_passes

SHA = "a" * 40


def _tier() -> dict:
    return {
        "tests_passed": True,
        "security_passed": True,
        "build_passed": True,
        "render_qa_passed": True,
        "identity_invariants_passed": True,
        "deployment_sha_aligned": True,
        "client_delivery_allowed": True,
    }


def _pass() -> dict:
    return {
        "commit_sha": SHA,
        "tiers": {tier: _tier() for tier in ("express", "mid", "full")},
    }


def test_two_clean_same_commit_passes_release_all_tiers() -> None:
    result = verify_two_consecutive_release_passes([_pass(), _pass()], expected_commit_sha=SHA)
    assert result["release_verified"] is True
    assert result["client_delivery_allowed"] is True
    assert result["issues"] == []


def test_one_pass_is_insufficient() -> None:
    result = verify_two_consecutive_release_passes([_pass()], expected_commit_sha=SHA)
    assert "exactly_two_passes_required" in result["issues"]
    assert result["release_verified"] is False


def test_different_commit_sha_fails_closed() -> None:
    second = _pass()
    second["commit_sha"] = "b" * 40
    result = verify_two_consecutive_release_passes([_pass(), second], expected_commit_sha=SHA)
    assert "pass_2:commit_sha_mismatch" in result["issues"]
    assert "verification_pass_sha_mismatch" in result["issues"]
    assert result["client_delivery_allowed"] is False


def test_any_tier_failure_blocks_release() -> None:
    second = deepcopy(_pass())
    second["tiers"]["mid"]["render_qa_passed"] = False
    result = verify_two_consecutive_release_passes([_pass(), second], expected_commit_sha=SHA)
    assert "pass_2:mid_render_qa_passed_failed" in result["issues"]
    assert result["release_verified"] is False


def test_missing_tier_record_blocks_release() -> None:
    second = _pass()
    del second["tiers"]["full"]
    result = verify_two_consecutive_release_passes([_pass(), second], expected_commit_sha=SHA)
    assert "pass_2:missing_full_record" in result["issues"]
    assert result["release_verified"] is False


def test_prior_delivery_block_cannot_be_overridden() -> None:
    second = _pass()
    second["tiers"]["express"]["client_delivery_allowed"] = False
    result = verify_two_consecutive_release_passes([_pass(), second], expected_commit_sha=SHA)
    assert "pass_2:express_delivery_not_allowed" in result["issues"]
    assert result["client_delivery_allowed"] is False
