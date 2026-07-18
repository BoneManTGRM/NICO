from nico.report_artifact_binding_gate_v1 import qualify_report_artifacts


def _artifact(name):
    return {
        "uri": f"s3://reports/{name}",
        "sha256": (name.replace("/", "-") + "0" * 64)[:64],
        "content_fingerprint": f"fingerprint-{name}",
        "download_verified": True,
        "manual_inspection_complete": True,
        "mobile_verified": True,
    }


def _manifest(tier):
    return {
        "assessment_id": f"assessment-{tier}",
        "snapshot_sha": "a" * 40,
        "generated_at": "2026-07-18T02:00:00Z",
        "generator_version": "v1",
        "artifacts": {
            language: {
                output_format: _artifact(f"{tier}/{language}/{output_format}")
                for output_format in ("pdf", "html", "markdown")
            }
            for language in ("en", "es")
        },
        "cross_format_equivalent": True,
        "cross_language_equivalent": True,
        "tier_isolation_verified": True,
    }


def _manifests():
    return {tier: _manifest(tier) for tier in ("express", "mid", "full")}


def test_complete_artifact_manifests_qualify():
    result = qualify_report_artifacts(_manifests())
    assert result["delivery_allowed"] is True
    assert result["status"] == "qualified"


def test_missing_language_and_format_block():
    manifests = _manifests()
    del manifests["mid"]["artifacts"]["es"]
    del manifests["full"]["artifacts"]["en"]["pdf"]
    result = qualify_report_artifacts(manifests)
    assert "mid:missing_language:es" in result["failures"]
    assert "full:en:missing_format:pdf" in result["failures"]


def test_unverified_download_inspection_and_mobile_block():
    manifests = _manifests()
    artifact = manifests["express"]["artifacts"]["en"]["pdf"]
    artifact["download_verified"] = False
    artifact["manual_inspection_complete"] = False
    artifact["mobile_verified"] = False
    result = qualify_report_artifacts(manifests)
    assert "express:en:pdf:download_unverified" in result["failures"]
    assert "express:en:pdf:inspection_incomplete" in result["failures"]
    assert "express:en:pdf:mobile_unverified" in result["failures"]


def test_equivalence_isolation_and_duplicate_assessment_block():
    manifests = _manifests()
    manifests["mid"]["assessment_id"] = manifests["express"]["assessment_id"]
    manifests["full"]["cross_format_equivalent"] = False
    manifests["full"]["cross_language_equivalent"] = False
    manifests["full"]["tier_isolation_verified"] = False
    result = qualify_report_artifacts(manifests)
    assert "mid:duplicate_assessment_id" in result["failures"]
    assert "full:cross_format_mismatch" in result["failures"]
    assert "full:cross_language_mismatch" in result["failures"]
    assert "full:tier_isolation_failed" in result["failures"]


def test_prior_release_block_is_preserved():
    result = qualify_report_artifacts(_manifests(), prior_release_allowed=False)
    assert result["delivery_allowed"] is False
    assert "prior_release_block" in result["failures"]
