from __future__ import annotations

from fastapi import FastAPI

from nico import scanner_tool_runners, snapshot_scanner_worker
from nico.mid_live_status_api import register_mid_live_status_routes
from nico.mid_runtime_diagnostics import MID_RUNTIME_DIAGNOSTICS_PATH, mid_runtime_status, register_mid_runtime_diagnostics
from nico.snapshot_scanner_heartbeat_patch import install_snapshot_scanner_heartbeat


def test_mid_runtime_diagnostics_are_ok_only_when_live_route_and_both_heartbeat_bindings_exist(monkeypatch) -> None:
    app = FastAPI()
    register_mid_live_status_routes(app)
    installed = install_snapshot_scanner_heartbeat()
    monkeypatch.delenv("DATABASE_URL", raising=False)

    status = mid_runtime_status(app)

    assert installed["source_runner_binding_installed"] is True
    assert installed["snapshot_worker_binding_installed"] is True
    assert status["status"] == "ok"
    assert status["mid_live_status_route_count"] == 1
    assert status["source_runner_heartbeat_binding"] is True
    assert status["snapshot_worker_heartbeat_binding"] is True
    assert status["heartbeat_bindings_identical"] is True
    assert status["same_run_duplicate_prevention"] is True


def test_mid_runtime_diagnostics_fail_closed_when_snapshot_worker_uses_unwrapped_runner(monkeypatch) -> None:
    app = FastAPI()
    register_mid_live_status_routes(app)
    install_snapshot_scanner_heartbeat()
    monkeypatch.delenv("DATABASE_URL", raising=False)

    def unwrapped_runner(*args, **kwargs):
        return {}

    monkeypatch.setattr(snapshot_scanner_worker, "run_scanner_tool", unwrapped_runner)
    status = mid_runtime_status(app)

    assert status["status"] == "blocked"
    assert status["source_runner_heartbeat_binding"] is True
    assert status["snapshot_worker_heartbeat_binding"] is False
    assert status["heartbeat_bindings_identical"] is False


def test_mid_runtime_diagnostics_route_registers_exactly_once() -> None:
    app = FastAPI()
    register_mid_live_status_routes(app)
    install_snapshot_scanner_heartbeat()

    first = register_mid_runtime_diagnostics(app)
    second = register_mid_runtime_diagnostics(app)
    routes = [
        route
        for route in app.routes
        if getattr(route, "path", "") == MID_RUNTIME_DIAGNOSTICS_PATH
        and "GET" in (getattr(route, "methods", set()) or set())
    ]

    assert first["status"] in {"ok", "blocked"}
    assert second["status"] in {"ok", "blocked"}
    assert len(routes) == 1
    assert scanner_tool_runners.run_scanner_tool is snapshot_scanner_worker.run_scanner_tool
