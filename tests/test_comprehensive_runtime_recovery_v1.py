from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.api import comprehensive_production_bootstrap as bootstrap


class _ProbeStore:
    def __init__(self, *, available: bool) -> None:
        self.available = available

    def live_persistence_probe(self) -> dict:
        return {
            "status": "ready" if self.available else "unavailable",
            "available": self.available,
            "adapter": "postgres",
            "error_detail_exposed": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }


def _controller(store: _ProbeStore) -> SimpleNamespace:
    return SimpleNamespace(_service=SimpleNamespace(_store=store))


def _base_status(*, status: str, reason: str = "") -> dict:
    return {
        "artifact_schema": bootstrap.VERSION,
        "service_id": "comprehensive",
        "status": status,
        "configured": status == "ready",
        "reason": reason,
        "non_storage_readiness_verified": True,
        "persistence_adapter": "postgres" if status == "ready" else "unavailable",
        "storage_source": "postgres:database_url" if status == "ready" else "unavailable",
        "durability_verified": status == "ready",
        "survives_container_replacement_verified": status == "ready",
        "run_store_shared_across_workers": status == "ready",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _runtime(*, status: str, reason: str = "") -> dict:
    ready = status == "ready"
    return {
        "status": status,
        "configured": ready,
        "reason": reason,
        "persistence_adapter": "postgres" if ready else "unavailable",
        "storage_source": "postgres:database_url" if ready else "unavailable",
        "database_url_source": "database_url" if ready else "",
        "durability_verified": ready,
        "survives_container_replacement_verified": ready,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_diagnostics_recovers_same_canonical_runtime_after_transient_startup_outage(monkeypatch) -> None:
    app = FastAPI()
    app.state.nico_comprehensive_production_runtime = _base_status(
        status="blocked",
        reason="comprehensive_database_unavailable",
    )
    app.state.comprehensive_runtime = _runtime(
        status="blocked",
        reason="comprehensive_database_unavailable",
    )
    store = _ProbeStore(available=True)
    controller = _controller(store)
    calls = {"install": 0}

    monkeypatch.setattr(
        bootstrap,
        "build_production_capability_executors",
        lambda _target: {"same_store_executor": lambda _context: {}},
    )

    def recover(target: FastAPI, *, capability_executors: dict):
        calls["install"] += 1
        assert capability_executors
        target.state.comprehensive_runtime = _runtime(status="ready")
        target.state.comprehensive_api_controller = controller
        return controller

    monkeypatch.setattr(bootstrap, "install_comprehensive_production_bootstrap", recover)
    bootstrap._register_runtime_diagnostics(app)

    response = TestClient(app).get(bootstrap.COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["reason"] == ""
    assert payload["runtime_recovery_supported"] is True
    assert payload["runtime_recovery_attempted"] is True
    assert payload["runtime_recovered"] is True
    assert payload["live_persistence_probe"]["available"] is True
    assert payload["same_canonical_store_recovery_only"] is True
    assert payload["automatic_cross_store_fallback"] is False
    assert payload["human_review_required"] is True
    assert payload["client_delivery_allowed"] is False
    assert calls["install"] == 1


def test_live_database_probe_blocks_and_recovers_without_switching_store(monkeypatch) -> None:
    app = FastAPI()
    app.state.nico_comprehensive_production_runtime = _base_status(status="ready")
    app.state.comprehensive_runtime = _runtime(status="ready")
    store = _ProbeStore(available=False)
    app.state.comprehensive_api_controller = _controller(store)

    def unexpected_rebootstrap(*_args, **_kwargs):
        raise AssertionError("configured runtime must not switch or rebuild stores")

    monkeypatch.setattr(
        bootstrap,
        "install_comprehensive_production_bootstrap",
        unexpected_rebootstrap,
    )
    bootstrap._register_runtime_diagnostics(app)
    client = TestClient(app)

    blocked = client.get(bootstrap.COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE)
    assert blocked.status_code == 200
    blocked_payload = blocked.json()
    assert blocked_payload["status"] == "blocked"
    assert blocked_payload["reason"] == "comprehensive_database_unavailable"
    assert blocked_payload["live_persistence_probe"]["available"] is False
    assert blocked_payload["runtime_recovery_attempted"] is False
    assert blocked_payload["automatic_cross_store_fallback"] is False

    store.available = True
    ready = client.get(bootstrap.COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE)
    assert ready.status_code == 200
    ready_payload = ready.json()
    assert ready_payload["status"] == "ready"
    assert ready_payload["reason"] == ""
    assert ready_payload["live_persistence_probe"]["available"] is True
    assert ready_payload["runtime_recovery_attempted"] is False
    assert ready_payload["same_canonical_store_recovery_only"] is True


def test_failed_recovery_remains_fail_closed(monkeypatch) -> None:
    app = FastAPI()
    app.state.nico_comprehensive_production_runtime = _base_status(
        status="blocked",
        reason="comprehensive_database_unavailable",
    )
    app.state.comprehensive_runtime = _runtime(
        status="blocked",
        reason="comprehensive_database_unavailable",
    )

    monkeypatch.setattr(
        bootstrap,
        "build_production_capability_executors",
        lambda _target: {"same_store_executor": lambda _context: {}},
    )
    monkeypatch.setattr(
        bootstrap,
        "install_comprehensive_production_bootstrap",
        lambda *_args, **_kwargs: None,
    )
    bootstrap._register_runtime_diagnostics(app)

    response = TestClient(app).get(bootstrap.COMPREHENSIVE_RUNTIME_DIAGNOSTICS_ROUTE)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["reason"] == "comprehensive_database_unavailable"
    assert payload["runtime_recovery_attempted"] is True
    assert payload["runtime_recovered"] is False
    assert payload["automatic_cross_store_fallback"] is False
    assert payload["human_review_required"] is True
    assert payload["client_delivery_allowed"] is False
