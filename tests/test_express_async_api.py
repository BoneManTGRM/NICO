from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException

import nico.express_async_api as express
from nico.storage import MemoryAdapter


class DeferredExecutor:
    def __init__(self) -> None:
        self.calls = []

    def submit(self, fn, *args):
        self.calls.append((fn, args))
        return SimpleNamespace()


class RequestModel:
    def __init__(self, **payload):
        self.payload = payload

    def model_dump(self):
        return deepcopy(self.payload)


@pytest.fixture(autouse=True)
def clear_active_express_state():
    express._ACTIVE_RUNS.clear()
    express._ACTIVE_SCOPE_RUNS.clear()
    yield
    express._ACTIVE_RUNS.clear()
    express._ACTIVE_SCOPE_RUNS.clear()


def request(**overrides):
    payload = {
        "repository": "BoneManTGRM/NICO",
        "authorized": True,
        "authorization_confirmed": True,
        "customer_id": "customer_test",
        "project_id": "project_test",
        "client_name": "Cody Jenkins",
        "project_name": "NICO Audit",
    }
    payload.update(overrides)
    return express.ExpressAssessmentRunRequest(**payload)


def status_request(**overrides):
    payload = {"customer_id": "customer_test", "project_id": "project_test"}
    payload.update(overrides)
    return express.ExpressAssessmentStatusRequest(**payload)


def test_start_requires_both_authorization_signals(monkeypatch) -> None:
    fake_main = SimpleNamespace(
        safe_blocked_exception=lambda result: HTTPException(
            status_code=400,
            detail={"status": "blocked", "message": str(result.get("error") or "blocked")},
        )
    )
    monkeypatch.setattr(express, "import_module", lambda _name: fake_main)

    with pytest.raises(HTTPException) as exc:
        express.express_assessment_start(request(authorization_confirmed=False))

    assert exc.value.status_code == 400
    assert exc.value.detail["status"] == "blocked"


def test_start_returns_quick_exact_run_and_records_queued_state(monkeypatch) -> None:
    store = MemoryAdapter()
    executor = DeferredExecutor()
    monkeypatch.setattr(express, "STORE", store)
    monkeypatch.setattr(express, "_EXECUTOR", executor)

    started = express.express_assessment_start(request())

    run_id = started["run_id"]
    assert run_id.startswith("express_run_")
    assert started["status"] == "queued"
    assert started["client_ready"] is False
    assert started["human_review_required"] is True
    assert len(executor.calls) == 1
    assert executor.calls[0][1][0] == run_id
    record = store.get("assessment_runs", run_id)
    assert record["status"] == "queued"
    assert record["response"]["run_id"] == run_id
    assert record["request"]["authorization_confirmed"] is True
    assert run_id in express._ACTIVE_RUNS
    assert express._ACTIVE_SCOPE_RUNS[("BoneManTGRM/NICO", "customer_test", "project_test")] == run_id


def test_duplicate_active_scope_start_reuses_exact_run_without_second_submit(monkeypatch) -> None:
    store = MemoryAdapter()
    executor = DeferredExecutor()
    monkeypatch.setattr(express, "STORE", store)
    monkeypatch.setattr(express, "_EXECUTOR", executor)

    first = express.express_assessment_start(request())
    second = express.express_assessment_start(request())

    assert second["run_id"] == first["run_id"]
    assert second["status"] == "queued"
    assert second["duplicate_start_prevented"] is True
    assert len(executor.calls) == 1
    assert len(express._ACTIVE_RUNS) == 1


def test_active_capacity_is_bounded_without_creating_third_run(monkeypatch) -> None:
    store = MemoryAdapter()
    executor = DeferredExecutor()
    monkeypatch.setattr(express, "STORE", store)
    monkeypatch.setattr(express, "_EXECUTOR", executor)

    express.express_assessment_start(request(customer_id="customer_one", project_id="project_one"))
    express.express_assessment_start(request(customer_id="customer_two", project_id="project_two"))

    with pytest.raises(HTTPException) as exc:
        express.express_assessment_start(request(customer_id="customer_three", project_id="project_three"))

    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "express_capacity_reached"
    assert len(executor.calls) == express.MAX_ACTIVE_EXPRESS_RUNS
    assert len(express._ACTIVE_RUNS) == express.MAX_ACTIVE_EXPRESS_RUNS


def test_worker_preserves_start_run_id_through_final_report(monkeypatch) -> None:
    store = MemoryAdapter()
    monkeypatch.setattr(express, "STORE", store)
    run_id = "express_run_exact_identity"
    payload = request().model_dump()

    def attach_review(result, _payload):
        assert result["run_id"] == run_id
        output = deepcopy(result)
        output["report_id"] = "express_report_exact"
        output.setdefault("reports", {})["report_id"] = "express_report_exact"
        return output

    fake_main = SimpleNamespace(
        GithubAssessmentRequest=RequestModel,
        extract_scanner_worker_artifact=lambda _payload: {},
        run_github_assessment=lambda _payload: {
            "status": "complete",
            "repository": "BoneManTGRM/NICO",
            "reports": {"markdown": "# Express draft"},
        },
        run_github_assessment_with_scanner_artifacts=lambda _payload: {},
        attach_existing_worker_evidence=lambda result, _payload: result,
        enrich_payload_with_scanner_evidence=lambda result: result,
        apply_report_accuracy=lambda result: result,
        attach_express_review_target=attach_review,
        polish_express_result=lambda result: result,
        finalize_express_result_consistency=lambda result: result,
        attach_evidence_artifact_bundle=lambda result: result,
        attach_client_acceptance_gate=lambda result: {
            **result,
            "human_review_required": True,
            "client_ready": False,
        },
        safe_assessment_response_payload=lambda result: deepcopy(result),
        hosted_assessment_storage_record=lambda _req: (
            run_id,
            {
                "workflow": "express",
                "run_id": run_id,
                "customer_id": "customer_test",
                "project_id": "project_test",
                "status": "complete",
                "payload": {},
            },
        ),
        _LAST_HOSTED_ASSESSMENT={},
    )
    monkeypatch.setattr(express, "import_module", lambda _name: fake_main)
    express._ACTIVE_RUNS.add(run_id)
    express._ACTIVE_SCOPE_RUNS[express._scope_key(payload)] = run_id

    express._execute(run_id, payload)

    record = store.get("assessment_runs", run_id)
    response = record["response"]
    assert response["status"] == "complete"
    assert response["run_id"] == run_id
    assert response["report_id"] == "express_report_exact"
    assert response["reports"]["report_id"] == "express_report_exact"
    assert response["human_review_required"] is True
    assert response["client_ready"] is False
    assert fake_main._LAST_HOSTED_ASSESSMENT["run_id"] == run_id
    assert run_id not in express._ACTIVE_RUNS
    assert express._scope_key(payload) not in express._ACTIVE_SCOPE_RUNS


def test_status_is_bound_to_exact_tenant_scope(monkeypatch) -> None:
    store = MemoryAdapter()
    monkeypatch.setattr(express, "STORE", store)
    run_id = "express_run_scope_test"
    payload = request().model_dump()
    queued = express._response(run_id, payload, "queued", "Queued")
    express._record(run_id, payload, queued)
    express._ACTIVE_RUNS.add(run_id)

    active = express.express_assessment_status(run_id, status_request())
    assert active["customer_id"] == "customer_test"
    assert active["project_id"] == "project_test"

    with pytest.raises(HTTPException) as exc:
        express.express_assessment_status(run_id, status_request(project_id="other_project"))

    assert exc.value.status_code == 404
    assert exc.value.detail == {"status": "not_found", "message": "Express assessment run not found."}


def test_status_returns_active_state_and_fails_closed_after_restart(monkeypatch) -> None:
    store = MemoryAdapter()
    monkeypatch.setattr(express, "STORE", store)
    run_id = "express_run_restart_test"
    payload = request().model_dump()
    queued = express._response(run_id, payload, "queued", "Queued")
    express._record(run_id, payload, queued)

    express._ACTIVE_RUNS.add(run_id)
    active = express.express_assessment_status(run_id, status_request())
    assert active["status"] == "queued"
    assert active["run_id"] == run_id

    express._ACTIVE_RUNS.clear()
    with pytest.raises(HTTPException) as exc:
        express.express_assessment_status(run_id, status_request())

    assert exc.value.status_code == 503
    assert exc.value.detail["status"] == "interrupted"
    assert exc.value.detail["code"] == "express_worker_interrupted"
    assert exc.value.detail["run_id"] == run_id
    saved = store.get("assessment_runs", run_id)
    assert saved["status"] == "interrupted"


def test_terminal_failure_status_never_returns_http_success(monkeypatch) -> None:
    store = MemoryAdapter()
    monkeypatch.setattr(express, "STORE", store)
    run_id = "express_run_failed_test"
    payload = request().model_dump()
    failed = express._response(
        run_id,
        payload,
        "failed",
        "Backend execution failed.",
        code="express_backend_execution_failed",
    )
    express._record(run_id, payload, failed)

    with pytest.raises(HTTPException) as exc:
        express.express_assessment_status(run_id, status_request())

    assert exc.value.status_code == 503
    assert exc.value.detail["client_ready"] is False
    assert exc.value.detail["run_id"] == run_id


def test_unknown_terminal_state_fails_closed(monkeypatch) -> None:
    store = MemoryAdapter()
    monkeypatch.setattr(express, "STORE", store)
    run_id = "express_run_unknown_test"
    payload = request().model_dump()
    unknown = express._response(run_id, payload, "mystery", "Unknown")
    express._record(run_id, payload, unknown)

    with pytest.raises(HTTPException) as exc:
        express.express_assessment_status(run_id, status_request())

    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "express_unknown_terminal_state"
    assert store.get("assessment_runs", run_id)["status"] == "failed"


def test_route_registration_is_complete_and_idempotent() -> None:
    app = FastAPI()

    first = express.register_express_async_routes(app)
    second = express.register_express_async_routes(app)

    assert first["status"] == "installed"
    assert first["single_long_browser_connection_required"] is False
    assert first["exact_run_polling"] is True
    assert first["duplicate_active_scope_start_prevented"] is True
    assert first["max_active_runs"] == express.MAX_ACTIVE_EXPRESS_RUNS
    assert second["status"] == "already_installed"
    for method, path in express.EXPRESS_ASYNC_ROUTES:
        assert express._route_count(app, method, path) == 1
