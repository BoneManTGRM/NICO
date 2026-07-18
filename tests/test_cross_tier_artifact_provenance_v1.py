from nico.cross_tier_artifact_provenance_v1 import qualify_cross_tier_artifact_provenance


def _package(tier: str) -> dict:
    generated_at = "2026-07-18T11:15:00Z"
    deployment_sha = "a" * 40
    generator_version = "nico-report-v15"
    return {
        "generated_at": generated_at,
        "inspected_at": "2026-07-18T11:20:00Z",
        "reviewer": f"{tier}-reviewer",
        "generator_version": generator_version,
        "deployment_sha": deployment_sha,
        "artifacts": {
            name: {
                "generated_at": generated_at,
                "generator_version": generator_version,
                "deployment_sha": deployment_sha,
            }
            for name in ("markdown", "html", "pdf")
        },
    }


def _packages() -> dict:
    return {tier: _package(tier) for tier in ("express", "mid", "full")}


def test_valid_provenance_qualifies() -> None:
    result = qualify_cross_tier_artifact_provenance(_packages())
    assert result["status"] == "qualified"
    assert result["release_allowed"] is True


def test_inspection_before_generation_blocks() -> None:
    values = _packages()
    values["mid"]["inspected_at"] = "2026-07-18T11:10:00Z"
    result = qualify_cross_tier_artifact_provenance(values)
    assert "mid:inspection_before_generation" in result["failures"]


def test_format_provenance_mismatch_blocks() -> None:
    values = _packages()
    values["full"]["artifacts"]["pdf"]["deployment_sha"] = "b" * 40
    values["full"]["artifacts"]["html"]["generator_version"] = "old-renderer"
    result = qualify_cross_tier_artifact_provenance(values)
    assert "full:pdf:deployment_sha_mismatch" in result["failures"]
    assert "full:html:generator_version_mismatch" in result["failures"]


def test_missing_reviewer_and_bad_timestamp_block() -> None:
    values = _packages()
    values["express"]["reviewer"] = ""
    values["express"]["generated_at"] = "not-a-time"
    result = qualify_cross_tier_artifact_provenance(values)
    assert "express:missing_reviewer" in result["failures"]
    assert "express:invalid_generated_at" in result["failures"]


def test_prior_release_block_is_preserved() -> None:
    result = qualify_cross_tier_artifact_provenance(_packages(), prior_release_allowed=False)
    assert result["release_allowed"] is False
    assert "prior_release_block" in result["failures"]
