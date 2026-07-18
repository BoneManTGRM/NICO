from nico.production_release_evidence_v1 import verify_production_release


SHA = "a" * 40


def _artifact():
    return {"commit_sha": SHA, "artifact_id": "artifact-1", "sha256": "b" * 64}


def _tier():
    return {
        "smoke_test_passed": True,
        "mobile_download_passed": True,
        "manual_inspection_passed": True,
        "outputs": {
            "en": {"pdf": _artifact(), "html": _artifact(), "markdown": _artifact()},
            "es": {"pdf": _artifact(), "html": _artifact(), "markdown": _artifact()},
        },
    }


def _evidence():
    return {
        "deployments": {
            "staging": {
                "commit_sha": SHA,
                "healthy": True,
                "deployment_id": "staging-1",
                "frontend_url": "https://staging.example.test",
                "backend_url": "https://staging-api.example.test",
            },
            "production": {
                "commit_sha": SHA,
                "healthy": True,
                "deployment_id": "production-1",
                "frontend_url": "https://example.test",
                "backend_url": "https://api.example.test",
            },
        },
        "verification_passes": [
            {"commit_sha": SHA, "clean": True},
            {"commit_sha": SHA, "clean": True},
        ],
        "tiers": {"express": _tier(), "mid": _tier(), "full": _tier()},
        "open_defects": {"critical": 0, "high": 0},
    }


def test_complete_release_evidence_allows_release():
    result = verify_production_release(_evidence(), expected_commit_sha=SHA)
    assert result["release_allowed"] is True
    assert result["status"] == "release_ready"


def test_deployment_sha_drift_blocks_release():
    evidence = _evidence()
    evidence["deployments"]["production"]["commit_sha"] = "c" * 40
    result = verify_production_release(evidence, expected_commit_sha=SHA)
    assert "production:commit_sha_mismatch" in result["failures"]


def test_requires_two_clean_same_sha_passes():
    evidence = _evidence()
    evidence["verification_passes"] = [{"commit_sha": SHA, "clean": True}]
    result = verify_production_release(evidence, expected_commit_sha=SHA)
    assert "two_verification_passes_required" in result["failures"]


def test_missing_cross_tier_language_format_blocks_release():
    evidence = _evidence()
    del evidence["tiers"]["mid"]["outputs"]["es"]["pdf"]
    result = verify_production_release(evidence, expected_commit_sha=SHA)
    assert "mid:es:pdf:missing" in result["failures"]


def test_mobile_or_manual_failure_blocks_release():
    evidence = _evidence()
    evidence["tiers"]["full"]["mobile_download_passed"] = False
    evidence["tiers"]["express"]["manual_inspection_passed"] = False
    result = verify_production_release(evidence, expected_commit_sha=SHA)
    assert "full:mobile_download_failed" in result["failures"]
    assert "express:manual_inspection_failed" in result["failures"]


def test_open_critical_or_high_defects_block_release():
    evidence = _evidence()
    evidence["open_defects"] = {"critical": 1, "high": 2}
    result = verify_production_release(evidence, expected_commit_sha=SHA)
    assert "critical_defects_open" in result["failures"]
    assert "high_defects_open" in result["failures"]


def test_invalid_checksum_and_missing_artifact_identity_block():
    evidence = _evidence()
    evidence["tiers"]["express"]["outputs"]["en"]["html"]["sha256"] = "bad"
    evidence["tiers"]["full"]["outputs"]["es"]["markdown"]["artifact_id"] = ""
    result = verify_production_release(evidence, expected_commit_sha=SHA)
    assert "express:en:html:checksum_invalid" in result["failures"]
    assert "full:es:markdown:artifact_id_missing" in result["failures"]
