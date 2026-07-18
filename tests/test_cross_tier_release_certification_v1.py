from nico.cross_tier_release_certification_v1 import certify_release


SHA = "a" * 40


def _artifacts():
    return {
        "en": {"pdf": "en.pdf", "html": "en.html", "markdown": "en.md"},
        "es": {"pdf": "es.pdf", "html": "es.html", "markdown": "es.md"},
    }


def _evidence():
    tier = {
        "commit_sha": SHA,
        "smoke_test_passed": True,
        "mobile_download_passed": True,
        "manual_inspection_passed": True,
        "artifacts": _artifacts(),
    }
    return {
        "verification_passes": [
            {"status": "clean", "commit_sha": SHA},
            {"status": "clean", "commit_sha": SHA},
        ],
        "deployments": {
            "staging": {"healthy": True, "commit_sha": SHA, "deployment_id": "staging-1"},
            "production": {"healthy": True, "commit_sha": SHA, "deployment_id": "production-1"},
        },
        "tiers": {"express": dict(tier), "mid": dict(tier), "full": dict(tier)},
        "critical_defects": 0,
        "high_defects": 0,
    }


def test_complete_release_is_certified():
    result = certify_release(_evidence(), expected_sha=SHA)
    assert result["release_allowed"] is True
    assert result["status"] == "certified"


def test_two_clean_same_sha_passes_are_required():
    evidence = _evidence()
    evidence["verification_passes"][1]["commit_sha"] = "b" * 40
    result = certify_release(evidence, expected_sha=SHA)
    assert result["release_allowed"] is False
    assert "verification_pass_1:sha_mismatch" in result["failures"]


def test_staging_and_production_must_be_healthy_and_aligned():
    evidence = _evidence()
    evidence["deployments"]["production"]["healthy"] = False
    evidence["deployments"]["production"]["commit_sha"] = "b" * 40
    result = certify_release(evidence, expected_sha=SHA)
    assert "production:unhealthy" in result["failures"]
    assert "production:sha_mismatch" in result["failures"]


def test_every_tier_requires_mobile_smoke_manual_and_artifacts():
    evidence = _evidence()
    evidence["tiers"]["mid"]["mobile_download_passed"] = False
    del evidence["tiers"]["full"]["artifacts"]["es"]["pdf"]
    result = certify_release(evidence, expected_sha=SHA)
    assert "mid:mobile_download_failed" in result["failures"]
    assert "full:es:pdf:missing" in result["failures"]


def test_remaining_critical_or_high_defects_block_release():
    evidence = _evidence()
    evidence["critical_defects"] = 1
    evidence["high_defects"] = 2
    result = certify_release(evidence, expected_sha=SHA)
    assert "critical_defects_remaining" in result["failures"]
    assert "high_defects_remaining" in result["failures"]


def test_prior_delivery_block_is_preserved():
    result = certify_release(_evidence(), expected_sha=SHA, prior_delivery_allowed=False)
    assert result["release_allowed"] is False
    assert "prior_delivery_block" in result["failures"]
