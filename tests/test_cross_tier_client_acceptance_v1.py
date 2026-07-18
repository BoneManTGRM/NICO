from nico.cross_tier_client_acceptance_v1 import qualify_client_acceptance


def _record(**overrides):
    value = {
        "assessment_completed": True,
        "report_opened": True,
        "pdf_downloaded": True,
        "html_downloaded": True,
        "markdown_downloaded": True,
        "mobile_verified": True,
        "english_verified": True,
        "spanish_verified": True,
        "score_matches_report": True,
        "findings_traceable": True,
        "client_signoff": True,
        "assessment_id": "assessment-1",
        "snapshot_sha": "a" * 40,
        "reviewer": "acceptance-reviewer",
        "critical_defects": 0,
        "high_defects": 0,
    }
    value.update(overrides)
    return value


def _evidence():
    return {tier: _record(assessment_id=f"{tier}-assessment") for tier in ("express", "mid", "full")}


def test_all_tiers_accept_when_complete():
    result = qualify_client_acceptance(_evidence())
    assert result["delivery_allowed"] is True
    assert result["status"] == "accepted"


def test_missing_tier_fails_closed():
    evidence = _evidence()
    del evidence["mid"]
    result = qualify_client_acceptance(evidence)
    assert result["delivery_allowed"] is False
    assert "mid:missing_evidence" in result["failures"]


def test_failed_download_or_localization_blocks():
    evidence = _evidence()
    evidence["express"] = _record(pdf_downloaded=False, spanish_verified=False)
    result = qualify_client_acceptance(evidence)
    assert "express:pdf_downloaded:failed" in result["failures"]
    assert "express:spanish_verified:failed" in result["failures"]


def test_identity_reviewer_and_defects_are_required():
    evidence = _evidence()
    evidence["full"] = _record(
        assessment_id="",
        snapshot_sha="",
        reviewer="",
        critical_defects=1,
        high_defects=2,
    )
    result = qualify_client_acceptance(evidence)
    assert "full:missing_assessment_id" in result["failures"]
    assert "full:missing_snapshot_sha" in result["failures"]
    assert "full:missing_reviewer" in result["failures"]
    assert "full:critical_defects_open" in result["failures"]
    assert "full:high_defects_open" in result["failures"]


def test_prior_release_block_is_preserved():
    result = qualify_client_acceptance(_evidence(), prior_release_allowed=False)
    assert result["delivery_allowed"] is False
    assert "prior_release_block" in result["failures"]
