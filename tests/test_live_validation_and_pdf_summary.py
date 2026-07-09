from nico.hosted_full_evidence_runtime_v2 import ensure_hosted_runtime_evidence
from nico.report_pdf_display_patch import apply_pdf_display_patch


def _yellow_result(refresh=True):
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "authorized_by": "frontend-refresh-full-evidence" if refresh else "standard-express",
        "refresh_full_evidence_requested": refresh,
        "report_quality_guards": {},
    }


def test_live_validation_records_skipped_standard_express():
    result = ensure_hosted_runtime_evidence(_yellow_result(refresh=False))
    guard = result["report_quality_guards"]["hosted_full_evidence_runtime"]

    assert guard["status"] == "skipped_no_explicit_refresh_request"
    assert guard["refresh_full_evidence_requested"] is False
    assert "missing_required_tools" in guard


def test_live_validation_records_worker_exception(monkeypatch):
    def boom(payload):
        raise RuntimeError("scanner container unavailable")

    monkeypatch.setattr("nico.hosted_full_evidence_runtime_v2.run_hosted_scanner_worker", boom)
    result = ensure_hosted_runtime_evidence(_yellow_result(refresh=True))
    guard = result["report_quality_guards"]["hosted_full_evidence_runtime"]

    assert guard["status"] == "failed_exception"
    assert guard["refresh_full_evidence_requested"] is True
    assert "scanner container unavailable" in guard["error"]


def test_pdf_display_patch_does_not_truncate_executive_summary():
    from nico import assessment_quality

    apply_pdf_display_patch()
    long_summary = "Executive summary sentence. " * 80

    rendered = assessment_quality._clean_text(long_summary, limit=900)

    assert "[truncated]" not in rendered
    assert rendered == assessment_quality._friendly_note(long_summary)
