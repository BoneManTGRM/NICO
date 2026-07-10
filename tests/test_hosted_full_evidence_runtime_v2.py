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


def requested_result() -> dict:
    result = complete_result()
    result["refresh_full_evidence_requested"] = True
    return result


def clean_scanner_artifact() -> dict:
    return {
        "worker_execution_state": "completed",
        "tools": {
            "pip-audit": {"status": "completed", "finding_count": 0},
            "npm-audit": {"status": "completed", "finding_count": 0},
            "osv-scanner": {"status": "completed", "finding_count": 0},
            "bandit": {"status": "completed", "finding_count": 0},
            "semgrep": {"status": "completed", "finding_count": 0},
            "eslint": {"status": "completed", "finding_count": 0},
            "typescript": {"status": "completed", "finding_count": 0},
            "gitleaks": {"status": "completed", "finding_count": 0},
            "trufflehog": {"status": "completed", "finding_count": 0},
        },
    }


def test_standard_complete_result_still_skips_without_request() -> None:
    result = complete_result()

    assert runtime._explicit_refresh_requested(result) is False
    assert runtime._request_source(result) == "not_requested"
    assert runtime._should_refresh(result) is False
    assert result["report_quality_guards"]["hosted_full_evidence_runtime"]["status"] == "skipped_no_explicit_refresh_request"


def test_explicit_payload_flag_requests_full_evidence() -> None:
    result = requested_result()

    assert runtime._explicit_refresh_requested(result) is True
    assert runtime._request_source(result) == "explicit_payload_flag"


def test_refresh_can_be_explicitly_disabled() -> None:
    result = requested_result()
    result["refresh_full_evidence_requested"] = False

    assert runtime._explicit_refresh_requested(result) is False
    assert runtime._should_refresh(result) is False
    assert result["report_quality_guards"]["hosted_full_evidence_runtime"]["status"] == "skipped_no_explicit_refresh_request"


def test_authorized_by_marker_still_requests_full_evidence() -> None:
    result = complete_result()
    result["authorized_by"] = "frontend-refresh-full-evidence"

    assert runtime._explicit_refresh_requested(result) is True
    assert runtime._request_source(result) == "authorized_by_marker"


def test_runtime_does_not_repeat_after_attached_artifact(monkeypatch) -> None:
    result = requested_result()
    result["scanner_worker_auto_ran"] = True
    result["scanner_worker_artifact"] = clean_scanner_artifact()

    def fail_run_worker(payload):
        raise AssertionError("worker should not run twice")

    monkeypatch.setattr(runtime, "run_hosted_scanner_worker", fail_run_worker)

    output = runtime.ensure_hosted_runtime_evidence(result)

    assert output is result
    guard = result["report_quality_guards"]["hosted_full_evidence_runtime"]
    assert guard["status"] == "skipped_all_required_tools_already_present"
    assert guard["refresh_full_evidence_requested"] is True


def test_previous_attempt_without_artifact_can_retry(monkeypatch) -> None:
    result = requested_result()
    result["report_quality_guards"] = {"hosted_full_evidence_runtime": {"status": "attempted"}}

    monkeypatch.setattr(runtime, "run_hosted_scanner_worker", lambda payload: clean_scanner_artifact())

    output = runtime.ensure_hosted_runtime_evidence(result)

    assert output is result
    guard = result["report_quality_guards"]["hosted_full_evidence_runtime"]
    assert guard["status"] == "completed"
    assert guard["missing_dependency_tools"] == []
    assert guard["missing_static_tools"] == []
    assert guard["missing_secret_tools"] == []


def test_zero_finding_status_only_artifact_is_recognized() -> None:
    result = requested_result()
    result["scanner_worker_artifact"] = clean_scanner_artifact()

    assert runtime._missing_required_tools(result) == []


def test_explicit_request_adds_visible_runtime_note(monkeypatch) -> None:
    result = requested_result()

    def fail_run_worker(payload):
        return "not-an-artifact"

    monkeypatch.setattr(runtime, "run_hosted_scanner_worker", fail_run_worker)

    output = runtime.ensure_hosted_runtime_evidence(result)

    assert output is result
    guard = result["report_quality_guards"]["hosted_full_evidence_runtime"]
    assert guard["status"] == "failed_no_artifact"
    assert guard["request_source"] == "explicit_payload_flag"
    trust = next(item for item in result["sections"] if item["id"] == "trust_client_readiness")
    assert any("Refresh Full Evidence runtime validation" in item for item in trust["evidence"])
    assert not any("skipped_no_explicit_refresh_request" in item for item in trust["evidence"])
