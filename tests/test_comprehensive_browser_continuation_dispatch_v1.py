from __future__ import annotations

import threading
import time
from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import register_comprehensive_api_routes
from nico.comprehensive_browser_continuation_dispatch_v1 import (
    active_browser_continuations_for_tests,
    dispatch_browser_continuation,
    reset_browser_continuation_dispatch_for_tests,
)


class _BlockingController:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def continue_run(self, run_id: str, payload: dict, *, browser_projection: bool):
        assert run_id == "comprun_dispatch_unit"
        assert payload == {"max_stages": 1}
        assert browser_projection is True
        self.calls += 1
        self.entered.set()
        assert self.release.wait(2)
        return {"status": "running"}


def _wait_until_idle(run_id: str) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if run_id not in active_browser_continuations_for_tests():
            return
        time.sleep(0.01)
    raise AssertionError("browser continuation dispatcher did not become idle")


def test_dispatch_returns_without_owning_publication_and_deduplicates() -> None:
    reset_browser_continuation_dispatch_for_tests()
    controller = _BlockingController()

    started = time.monotonic()
    first = dispatch_browser_continuation(
        controller,
        run_id="comprun_dispatch_unit",
        payload={"max_stages": 1},
    )
    elapsed = time.monotonic() - started
    assert controller.entered.wait(1)

    second = dispatch_browser_continuation(
        controller,
        run_id="comprun_dispatch_unit",
        payload={"max_stages": 1},
    )

    assert elapsed < 0.2
    assert first["status"] == "dispatched"
    assert first["request_thread_owns_publication"] is False
    assert second["status"] == "already_active"
    assert controller.calls == 1
    controller.release.set()
    _wait_until_idle("comprun_dispatch_unit")
    reset_browser_continuation_dispatch_for_tests()


class _AdvisoryCursor:
    def __init__(self, acquired: bool) -> None:
        self.acquired = acquired
        self.statements: list[tuple[str, tuple[int, ...]]] = []

    def execute(self, statement: str, params: tuple[int, ...]) -> None:
        self.statements.append((statement, params))

    def fetchone(self) -> tuple[bool]:
        return (self.acquired,)


class _AdvisoryConnection:
    def __init__(self, acquired: bool) -> None:
        self.cursor_value = _AdvisoryCursor(acquired)
        self.closed = False

    def cursor(self) -> _AdvisoryCursor:
        return self.cursor_value

    def close(self) -> None:
        self.closed = True


class _PostgresStore:
    _dialect = "postgres"

    def __init__(self, acquired: bool) -> None:
        self.connection = _AdvisoryConnection(acquired)

    def _connection_factory(self) -> _AdvisoryConnection:
        return self.connection


class _PostgresService:
    def __init__(self, acquired: bool) -> None:
        self._store = _PostgresStore(acquired)


class _PostgresController:
    def __init__(self, acquired: bool) -> None:
        self._service = _PostgresService(acquired)
        self.called = threading.Event()

    def continue_run(self, *_args, **_kwargs) -> dict:
        self.called.set()
        return {"status": "running"}


def test_postgres_advisory_lock_guards_cross_worker_publication() -> None:
    reset_browser_continuation_dispatch_for_tests()
    controller = _PostgresController(acquired=True)

    result = dispatch_browser_continuation(
        controller,
        run_id="comprun_dispatch_postgres",
        payload={"max_stages": 1},
    )
    assert controller.called.wait(1)
    _wait_until_idle("comprun_dispatch_postgres")

    cursor = controller._service._store.connection.cursor_value
    assert result["distributed_lock_required"] is True
    assert [statement for statement, _params in cursor.statements] == [
        "SELECT pg_try_advisory_lock(%s)",
        "SELECT pg_advisory_unlock(%s)",
    ]
    assert cursor.statements[0][1] == cursor.statements[1][1]
    assert controller._service._store.connection.closed is True
    reset_browser_continuation_dispatch_for_tests()


def test_postgres_lock_contention_does_not_run_duplicate_publication() -> None:
    reset_browser_continuation_dispatch_for_tests()
    controller = _PostgresController(acquired=False)

    dispatch_browser_continuation(
        controller,
        run_id="comprun_dispatch_postgres_contended",
        payload={"max_stages": 1},
    )
    _wait_until_idle("comprun_dispatch_postgres_contended")

    assert controller.called.is_set() is False
    cursor = controller._service._store.connection.cursor_value
    assert [statement for statement, _params in cursor.statements] == [
        "SELECT pg_try_advisory_lock(%s)"
    ]
    assert controller._service._store.connection.closed is True
    reset_browser_continuation_dispatch_for_tests()


class _ProductionProjectionService:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.resume_calls = 0
        self.record = {
            "artifact_schema": "nico.comprehensive_run_record.v1",
            "identity": {
                "run_id": "comprun_dispatch_route",
                "repository": "BoneManTGRM/NICO",
                "commit_sha": "a" * 40,
                "evidence_ledger_id": "ledger_dispatch_route",
                "customer_id": "customer_dispatch_route",
                "project_id": "project_dispatch_route",
                "assessment_depth": "strategic",
                "report_language": "en",
            },
            "status": "running",
            "current_stage": "functional_qa",
            "completed_stages": [],
            "stage_results": {},
            "blockers": [],
            "progress_percent": 34.78,
            "revision": 30,
            "terminal": False,
            "human_review_required": True,
            "human_review_completed": False,
            "client_delivery_allowed": False,
            "integrity_sha256": "dispatch-route-integrity",
        }

    def load_browser_projection(self, run_id: str) -> dict:
        assert run_id == "comprun_dispatch_route"
        return ComprehensiveApiController._response(
            deepcopy(self.record),
            operation="status",
            browser_projection=True,
        )

    def resume(self, run_id: str, *, max_stages: int | None = None) -> dict:
        assert run_id == "comprun_dispatch_route"
        assert max_stages == 1
        self.resume_calls += 1
        self.entered.set()
        assert self.release.wait(2)
        return deepcopy(self.record)


def test_production_browser_route_returns_durable_projection_before_resume_finishes() -> None:
    reset_browser_continuation_dispatch_for_tests()
    service = _ProductionProjectionService()
    controller = ComprehensiveApiController(service)  # type: ignore[arg-type]
    app = FastAPI()
    app.state.comprehensive_runtime = {
        "configured": True,
        "persistence_adapter": "postgres",
        "detached_stage_execution": True,
        "continuation_transport_owns_provider_lifetime": False,
    }
    register_comprehensive_api_routes(app, controller=controller)

    started = time.monotonic()
    response = TestClient(app).post(
        "/assessment/comprehensive-run/comprun_dispatch_route/continue",
        headers={"x-nico-browser-projection": "terminal-manifest-v1"},
        json={"max_stages": 1},
    )
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert elapsed < 0.5
    assert service.entered.wait(1)
    body = response.json()
    assert body["operation"] == "continuation_dispatched"
    assert body["revision"] == 30
    assert body["current_stage"] == "functional_qa"
    assert body["continuation_dispatch"]["status"] == "dispatched"
    assert body["continuation_dispatch"]["request_thread_owns_publication"] is False
    assert body["client_delivery_allowed"] is False
    service.release.set()
    _wait_until_idle("comprun_dispatch_route")
    assert service.resume_calls == 1
    reset_browser_continuation_dispatch_for_tests()
