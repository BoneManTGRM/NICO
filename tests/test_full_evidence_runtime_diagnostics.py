from nico.hosted_full_evidence_runtime_v2 import ensure_hosted_runtime_evidence


def test_full_evidence_runtime_records_skipped_standard_express():
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "authorized_by": "standard-express",
    }

    updated = ensure_hosted_runtime_evidence(result)

    guard = updated["report_quality_guards"]["hosted_full_evidence_runtime"]
    assert guard["status"] == "skipped_no_explicit_refresh_request"
    assert guard["refresh_full_evidence_requested"] is False
    assert "pip-audit" in guard["missing_required_tools"]
    assert "scanner_worker_artifact" not in updated
