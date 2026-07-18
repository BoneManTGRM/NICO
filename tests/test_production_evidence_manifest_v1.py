from nico.production_evidence_manifest_v1 import validate_production_evidence_manifest


SHA = "a" * 40
CHECKSUM = "b" * 64


def _artifact():
    return {"sha": SHA, "sha256": CHECKSUM}


def _tier():
    return {
        "smoke_test": True,
        "mobile_download": True,
        "manual_inspection": True,
        "artifacts": {
            language: {format_name: _artifact() for format_name in ("pdf", "html", "markdown")}
            for language in ("en", "es")
        },
    }


def _manifest():
    return {
        "deployments": {
            "staging": {"sha": SHA, "healthy": True},
            "production": {"sha": SHA, "healthy": True},
        },
        "verification_passes": [
            {"sha": SHA, "clean": True},
            {"sha": SHA, "clean": True},
        ],
        "tiers": {tier: _tier() for tier in ("express", "mid", "full")},
        "open_defects": {"critical": 0, "high": 0},
    }


def test_complete_manifest_is_release_ready():
    result = validate_production_evidence_manifest(_manifest(), expected_sha=SHA)
    assert result["release_allowed"] is True
    assert result["status"] == "release_ready"


def test_deployment_sha_mismatch_blocks():
    manifest = _manifest()
    manifest["deployments"]["production"]["sha"] = "c" * 40
    result = validate_production_evidence_manifest(manifest, expected_sha=SHA)
    assert "production:sha_mismatch" in result["failures"]


def test_exactly_two_clean_same_sha_passes_required():
    manifest = _manifest()
    manifest["verification_passes"] = [{"sha": SHA, "clean": True}]
    result = validate_production_evidence_manifest(manifest, expected_sha=SHA)
    assert "verification_passes:must_equal_two" in result["failures"]


def test_missing_cross_tier_artifact_blocks():
    manifest = _manifest()
    del manifest["tiers"]["mid"]["artifacts"]["es"]["pdf"]
    result = validate_production_evidence_manifest(manifest, expected_sha=SHA)
    assert "mid:es:pdf:missing" in result["failures"]


def test_open_severe_defects_block():
    manifest = _manifest()
    manifest["open_defects"] = {"critical": 1, "high": 2}
    result = validate_production_evidence_manifest(manifest, expected_sha=SHA)
    assert "open_critical_defects" in result["failures"]
    assert "open_high_defects" in result["failures"]
