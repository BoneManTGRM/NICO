from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import nico.express_async_api as express
import nico.express_backend_diagnostics as diagnostics
from nico.storage import MemoryAdapter


class RequestModel:
    def __init__(self, **payload):
        self.payload = payload

    def model_dump(self):
        return deepcopy(self.payload)


def _request() -> dict:
    return {
        "repository": "BoneManTGRM/NICO",
        "authorized": True,
        "authorization_confirmed": True,
        "customer_id": "customer_stage_progress",
        "project_id": "project_stage_progress",
        "client_name": "Stage Test",
        "project_name": "Express Lifecycle",
        "refresh_full_evidence": True,
    }


def test_express_worker_publishes_truthful_stage_sequence_and_scanner_state(monkeypatch) -> None:
    store = MemoryAdapter()
    run_id = "express_run_truthful_stage_progress"
    request = _request()
    observed: list[dict] = []

    monkeypatch.setattr(express, "STORE", store)
    monkeypatch.setattr(diagnostics.express, "STORE", store)
    original_record = express._record

    def capturing_record(record_run_id: str, payload: dict, response: dict):
        observed.append(deepcopy(response))
        return original_record(record_run_id, payload, response)

    monkeypatch.setattr(express, "_record", capturing_record)
    monkeypatch.setattr(diagnostics.express, "_record", capturing_record)
    monkeypatch.setattr(diagnostics, "_clear_request_local_payload", lambda: None)

    base_result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "scanner": {
            "status": "complete",
            "current_stage": "scanner_suite_complete",
            "progress_percent": 100,
            "tools_run": ["pip_audit", "trufflehog", "semgrep"],
        },
        "sections": [{"id": "summary", "label": "Summary"}],
        "reports": {
            "report_id": "express_report_truthful_stage_progress",
            "markdown": "# Express report",
            "html": "<html><body>Express report</body></html>",
            "pdf_base64": "JVBERi0xLjQK",
        },
    }

    def attach_review(result, _payload):
        output = deepcopy(result)
        output["report_id"] = "express_report_truthful_stage_progress"
        return output

    fake_main = SimpleNamespace(
        GithubAssessmentRequest=RequestModel,
        extract_scanner_worker_artifact=lambda _payload: {},
        run_github_assessment=lambda _payload: deepcopy(base_result),
        run_github_assessment_with_scanner_artifacts=lambda _payload: deepcopy(base_result),
        attach_existing_worker_evidence=lambda result, _payload: deepcopy(result),
        enrich_payload_with_scanner_evidence=lambda result: deepcopy(result),
        apply_report_accuracy=lambda result: deepcopy(result),
        attach_express_review_target=attach_review,
        polish_express_result=lambda result: deepcopy(result),
        finalize_express_result_consistency=lambda result: deepcopy(result),
        attach_evidence_artifact_bundle=lambda result: {
            **deepcopy(result),
            "evidence_artifact_bundle": {"bundle_hash": "bundle_truthful_stage"},
        },
        attach_client_acceptance_gate=lambda result: {
            **deepcopy(result),
            "human_review_required": True,
            "client_ready": False,
        },
        safe_assessment_response_payload=lambda result: deepcopy(result),
        _LAST_HOSTED_ASSESSMENT={},
    )
    monkeypatch.setattr(express, "import_module", lambda _name: fake_main)

    express._ACTIVE_RUNS.add(run_id)
    express._ACTIVE_SCOPE_RUNS[express._scope_key(request)] = run_id
    diagnostics.execute_with_diagnostics(run_id, request)

    latest_by_stage = {str(item.get("current_stage")): item for item in observed}
    expected = {
        "repository_evidence": 14,
        "scanner_reconciliation": 48,
        "accuracy_review": 62,
        "score_reconciliation": 72,
        "report_generation": 82,
        "truth_and_review_gates": 94,
        "complete": 100,
    }
    assert {stage: latest_by_stage[stage]["progress_percent"] for stage in expected} == expected

    repository = latest_by_stage["repository_evidence"]
    assert repository["worker_started"] is True
    assert repository["worker_started_at"]
    assert repository["worker_process_id"] > 0
    assert repository["worker_thread"]
    assert repository["status_truth"] == "durable_worker_stage"
    assert repository["scanner"]["status"] == "pending"
    assert repository["scanner"]["current_stage"] == "awaiting_repository_evidence"

    scanner = latest_by_stage["scanner_reconciliation"]
    assert scanner["scanner"]["status"] == "complete"
    assert scanner["backend_stage"] == "attach_existing_worker_evidence"

    final = latest_by_stage["complete"]
    assert final["status"] == "complete"
    assert final["scanner"]["status"] == "complete"
    assert final["reports"]["report_id"] == "express_report_truthful_stage_progress"
    assert final["human_review_required"] is True
    assert final["client_ready"] is False
    assert run_id not in express._ACTIVE_RUNS


def test_backend_diagnostic_failure_is_terminal_not_request_accepted(monkeypatch) -> None:
    store = MemoryAdapter()
    run_id = "express_run_terminal_diagnostic_progress"
    request = _request()
    monkeypatch.setattr(express, "STORE", store)
    monkeypatch.setattr(diagnostics.express, "STORE", store)
    monkeypatch.setattr(diagnostics, "_clear_request_local_payload", lambda: None)

    class BackendFailure(RuntimeError):
        pass

    fake_main = SimpleNamespace(
        GithubAssessmentRequest=RequestModel,
        extract_scanner_worker_artifact=lambda _payload: {},
        run_github_assessment=lambda _payload: (_ for _ in ()).throw(BackendFailure("private failure")),
        run_github_assessment_with_scanner_artifacts=lambda _payload: {},
    )
    monkeypatch.setattr(express, "import_module", lambda _name: fake_main)

    express._ACTIVE_RUNS.add(run_id)
    express._ACTIVE_SCOPE_RUNS[express._scope_key(request)] = run_id
    diagnostics.execute_with_diagnostics(run_id, request)

    response = store.get("assessment_runs", run_id)["response"]
    assert response["status"] == "failed"
    assert response["progress_percent"] == 100
    assert response["current_stage"] == "failed"
    assert response["failure_stage"] == "collect_assessment"
    assert response["code"] == "express_backend_execution_failed"
    assert "private failure" not in repr(response)
