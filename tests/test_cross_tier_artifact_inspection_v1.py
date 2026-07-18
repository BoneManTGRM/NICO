from nico.cross_tier_artifact_inspection_v1 import inspect_cross_tier_artifacts

SHA = "a" * 40


def sample_artifacts():
    checks = {
        "no_blank_pages": True,
        "no_near_blank_pages": True,
        "no_clipped_content": True,
        "no_duplicate_prose": True,
        "no_broken_tables": True,
        "no_raw_markup": True,
        "visual_consistency": True,
    }
    result = {}
    for tier, pages in (("express", 18), ("mid", 35), ("full", 70)):
        result[tier] = {"locales": {}}
        for locale in ("en", "es"):
            fp = f"{tier}-{locale}-truth"
            result[tier]["locales"][locale] = {
                "snapshot_sha": SHA,
                "truth_fingerprint": fp,
                "formats": {
                    "pdf": {"artifact_id": f"{tier}-{locale}-pdf", "truth_fingerprint": fp, "page_count": pages, "inspected_pages": pages, "page_checks": dict(checks)},
                    "html": {"artifact_id": f"{tier}-{locale}-html", "truth_fingerprint": fp},
                    "markdown": {"artifact_id": f"{tier}-{locale}-md", "truth_fingerprint": fp},
                },
            }
    return result


def test_complete_inspection_passes():
    result = inspect_cross_tier_artifacts(sample_artifacts(), expected_snapshot_sha=SHA)
    assert result["status"] == "passed"
    assert result["client_delivery_allowed"] is True


def test_pdf_defect_blocks_delivery():
    artifacts = sample_artifacts()
    artifacts["mid"]["locales"]["en"]["formats"]["pdf"]["page_checks"]["no_clipped_content"] = False
    result = inspect_cross_tier_artifacts(artifacts, expected_snapshot_sha=SHA)
    assert "mid:pdf_check_failed:en:no_clipped_content" in result["issues"]


def test_truth_mismatch_blocks_delivery():
    artifacts = sample_artifacts()
    artifacts["full"]["locales"]["es"]["formats"]["html"]["truth_fingerprint"] = "different"
    result = inspect_cross_tier_artifacts(artifacts, expected_snapshot_sha=SHA)
    assert "full:cross_format_truth_mismatch:es" in result["issues"]


def test_incomplete_inspection_and_snapshot_drift_block():
    artifacts = sample_artifacts()
    artifacts["express"]["locales"]["en"]["formats"]["pdf"]["inspected_pages"] = 17
    artifacts["express"]["locales"]["es"]["snapshot_sha"] = "b" * 40
    result = inspect_cross_tier_artifacts(artifacts, expected_snapshot_sha=SHA)
    assert "express:pdf_page_inspection_incomplete:en" in result["issues"]
    assert "express:snapshot_sha_mismatch:es" in result["issues"]


def test_missing_records_fail_closed():
    artifacts = sample_artifacts()
    del artifacts["express"]
    del artifacts["mid"]["locales"]["es"]
    del artifacts["full"]["locales"]["en"]["formats"]["markdown"]
    result = inspect_cross_tier_artifacts(artifacts, expected_snapshot_sha=SHA)
    assert result["status"] == "blocked"
    assert "express:missing_tier_record" in result["issues"]
    assert "mid:missing_locale:es" in result["issues"]
    assert "full:missing_format:en:markdown" in result["issues"]
