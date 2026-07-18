import hashlib

from nico.cross_tier_artifact_identity_v1 import qualify_cross_tier_artifact_identity


def package(tier: str) -> dict:
    assessment_id = tier + "-assessment"
    run_id = tier + "-run"
    snapshot_sha = "b" * 40
    artifacts = {}
    for format_name in ("markdown", "html", "pdf"):
        artifacts[format_name] = {
            "available": True,
            "sha256": hashlib.sha256(f"{tier}:{format_name}".encode()).hexdigest(),
            "assessment_id": assessment_id,
            "run_id": run_id,
            "snapshot_sha": snapshot_sha,
            "manual_inspection_passed": True,
        }
    return {
        "assessment_id": assessment_id,
        "run_id": run_id,
        "snapshot_sha": snapshot_sha,
        "artifacts": artifacts,
        "human_review_required": True,
        "client_ready": False,
    }


def packages() -> dict:
    return {tier: package(tier) for tier in ("express", "mid", "full")}


def test_valid_packages_qualify() -> None:
    result = qualify_cross_tier_artifact_identity(packages())
    assert result["status"] == "qualified"
    assert result["delivery_allowed"] is True


def test_identity_mismatch_blocks() -> None:
    values = packages()
    values["mid"]["artifacts"]["pdf"]["run_id"] = "different-run"
    result = qualify_cross_tier_artifact_identity(values)
    assert "mid:pdf:run_identity_mismatch" in result["failures"]
    assert "mid:cross_format_identity_mismatch" in result["failures"]


def test_bad_digest_and_missing_inspection_block() -> None:
    values = packages()
    values["full"]["artifacts"]["pdf"]["sha256"] = "invalid"
    values["full"]["artifacts"]["html"]["manual_inspection_passed"] = False
    result = qualify_cross_tier_artifact_identity(values)
    assert "full:pdf:invalid_sha256" in result["failures"]
    assert "full:html:manual_inspection_missing" in result["failures"]


def test_missing_tier_and_early_client_ready_block() -> None:
    values = packages()
    del values["express"]
    values["mid"]["client_ready"] = True
    result = qualify_cross_tier_artifact_identity(values)
    assert "express:missing_package" in result["failures"]
    assert "mid:client_ready_before_approval" in result["failures"]


def test_prior_block_is_preserved() -> None:
    result = qualify_cross_tier_artifact_identity(packages(), prior_release_allowed=False)
    assert result["delivery_allowed"] is False
    assert "prior_release_block" in result["failures"]


def test_cross_tier_assessment_and_run_reuse_block() -> None:
    values = packages()
    values["mid"]["assessment_id"] = values["express"]["assessment_id"]
    values["mid"]["run_id"] = values["express"]["run_id"]
    for artifact in values["mid"]["artifacts"].values():
        artifact["assessment_id"] = values["mid"]["assessment_id"]
        artifact["run_id"] = values["mid"]["run_id"]
    result = qualify_cross_tier_artifact_identity(values)
    assert "mid:assessment_id_reused_from_express" in result["failures"]
    assert "mid:run_id_reused_from_express" in result["failures"]


def test_cross_tier_artifact_digest_reuse_blocks() -> None:
    values = packages()
    values["full"]["artifacts"]["pdf"]["sha256"] = values["express"]["artifacts"]["pdf"]["sha256"]
    result = qualify_cross_tier_artifact_identity(values)
    assert "full:pdf:sha256_reused_from_express_pdf" in result["failures"]


def test_cross_format_digest_reuse_blocks() -> None:
    values = packages()
    values["mid"]["artifacts"]["html"]["sha256"] = values["mid"]["artifacts"]["markdown"]["sha256"]
    result = qualify_cross_tier_artifact_identity(values)
    assert "mid:html:duplicate_cross_format_sha256" in result["failures"]
