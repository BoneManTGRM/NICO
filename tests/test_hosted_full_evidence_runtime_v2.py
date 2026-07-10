from __future__ import annotations

from nico import hosted_full_evidence_runtime_v2 as runtime


def complete_result() -> dict:
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "sections": [
            {"id": "trust_client_readiness", "evidence": [], "unavailable": []},
            {"id": "dependency_health", "evidence": [], "unavailable": []},
            {"id": "static_analysis", "evidence": [], "unavailable": []},
            {"id": "secrets_review", "evidence": [], "unavailable": []},
        ],
    }


def test_complete_hosted_assessment_auto_requests_full_evidence() -> None:
    result = complete_result()

    assert runtime._explicit_refresh_requested(result) is True
    assert runtime._request_source(result) == "auto_required_for_complete_hosted_assessment"


def test_refresh_can_be_explicitly_disabled() -> None:
    result = complete_result()
    result["refresh_full_evidence_requested"] = False

    assert runtime._explicit_refresh_requested(result) is False
    assert runtime._should_refresh(result) is False
    assert result["report_quality_guards"]["hosted_full_evidence_runtime"]["status"] == "skipped_no_explicit_refresh_request"


def test_authorized_by_marker_still_requests_full_evidence() -> None:
    result = complete_result()
    result["authorized_by"] = "frontend-refresh-full-evidence"

    assert runtime._explicit_refresh_requested(result) is True
    assert runtime._request_source(result) == "authorized_by_marker"


def test_runtime_does_not_repeat_after_attempt(monkeypatch) -> None:
    result = complete_result()
    result["scanner_worker_auto_ran"] = True

    def fail_run_worker(payload):
        raise AssertionError("worker should not run twice")

    monkeypatch.setattr(runtime, "run_hosted_scanner_worker", fail_run_worker)

    output = runtime.ensure_hosted_runtime_evidence(result)

    assert output is result
    guard = result["report_quality_guards"]["hosted_full_evidence_runtime"]
    assert guard["status"] == "skipped_runtime_already_attempted"
    assert guard["refresh_full_evidence_requested"] is True


def test_auto_request_adds_visible_queued_note(monkeypatch) -> None:
    result = complete_result()

    def fail_run_worker(payload):
        return "not-an-artifact"

    monkeypatch.setattr(runtime, "run_hosted_scanner_worker", fail_run_worker)

    output = runtime.ensure_hosted_runtime_evidence(result)

    assert output is result
    guard = result["report_quality_guards"]["hosted_full_evidence_runtime"]
    assert guard["status"] == "failed_no_artifact"
    assert guard["request_source"] == "auto_required_for_complete_hosted_assessment"
    trust = next(item for item in result["sections"] if item["id"] == "trust_client_readiness")
    assert any("Refresh Full Evidence runtime validation" in item for item in trust["evidence"])
    assert not any("skipped_no_explicit_refresh_request" in item for item in trust["evidence"])
