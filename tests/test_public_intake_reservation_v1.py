from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.comprehensive_api_routes as routes
from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import register_comprehensive_api_routes
from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import (
    ComprehensiveRunConflict,
    ComprehensiveRunStore,
    _public_intake_payload_sha256,
)


def _controller(path: Path) -> ComprehensiveApiController:
    store = ComprehensiveRunStore(
        lambda: sqlite3.connect(path, timeout=10),
        dialect="sqlite",
    )
    store.ensure_schema()
    executors = {}
    for item in execution_plan():
        capability = item["capability"]

        def execute(context, *, _capability=capability):
            return {
                "status": "complete",
                "capability": _capability,
                "run_id": context["run_id"],
                "repository": context["repository"],
                "commit_sha": context["commit_sha"],
                "evidence_ledger_id": context["evidence_ledger_id"],
            }

        executors[capability] = execute
    return ComprehensiveApiController(ComprehensiveRunService(store, executors))


def _app(path: Path) -> FastAPI:
    app = FastAPI()
    app.state.comprehensive_runtime = {
        "configured": True,
        "persistence_adapter": "sqlite",
        "storage_source": str(path),
    }
    register_comprehensive_api_routes(app, controller=_controller(path))
    return app


def _payload(run_id: str = "comprun_11111111111111111111111111111111") -> dict:
    return {
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "provider": "github",
        "customer_id": "synthetic_customer",
        "project_id": "synthetic_project",
        "client_name": "Compañía Águila, S.A. de C.V.",
        "project_name": "Proyecto Ñandú / Release 2.0",
        "human_evidence": {
            "stakeholder_context": {
                "evidence": {
                    "primary_technical_contact": ["María-José Pérez - CTO / Ingeniería"],
                    "access_method": ["GitHub Enterprise - acceso de solo lectura"],
                    "authorized_scope": [
                        "organizacion/proyecto - rama release/2026.08; código, configuración y CI/CD."
                    ],
                    "objectives": ["Controlled synthetic acceptance"],
                }
            }
        },
        "engagement_field_states": {
            field: {"state": "supplied_unverified"}
            for field in (
                "client_name",
                "project_name",
                "primary_technical_contact",
                "access_method",
                "authorized_scope",
            )
        },
        "authorization_scope": "authorized defensive repository assessment",
        "authorized_by": "synthetic acceptance requester",
        "authorized": True,
        "authorization_confirmed": True,
    }


def _snapshot(context: dict) -> dict:
    return {
        "status": "attached",
        "run_id": context["run_id"],
        "repository": context["repository"],
        "commit_sha": "a" * 40,
        "access_mode": "anonymous_public",
        "credential_used": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_concurrent_same_intake_performs_provider_acquisition_exactly_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    started = threading.Event()
    release = threading.Event()
    calls = 0
    lock = threading.Lock()

    def blocked_snapshot(context: dict) -> dict:
        nonlocal calls
        with lock:
            calls += 1
        heartbeat = context.get("_provider_activity_callback")
        assert callable(heartbeat)
        heartbeat()
        started.set()
        assert release.wait(10)
        return _snapshot(context)

    monkeypatch.setattr(routes, "capture_repository_snapshot", blocked_snapshot)
    app = _app(tmp_path / "concurrent.db")
    first_client = TestClient(app)
    second_client = TestClient(app)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(
            first_client.post,
            "/assessment/comprehensive-intake",
            json=_payload(),
        )
        assert started.wait(10)
        second = second_client.post(
            "/assessment/comprehensive-intake",
            json=_payload(),
        )
        assert second.status_code == 200
        assert second.json()["operation"] == "intake_pending"
        release.set()
        first = first_future.result(timeout=10)
    assert first.status_code == 200
    assert first.json()["operation"] == "intake_started"
    assert calls == 1


@pytest.mark.parametrize("field", ["authorization_scope", "authorized_by"])
def test_completed_replay_binds_full_authorization_request(
    tmp_path: Path,
    monkeypatch,
    field: str,
) -> None:
    calls = 0

    def snapshot(context: dict) -> dict:
        nonlocal calls
        calls += 1
        return _snapshot(context)

    monkeypatch.setattr(routes, "capture_repository_snapshot", snapshot)
    client = TestClient(_app(tmp_path / f"{field}.db"))
    assert client.post("/assessment/comprehensive-intake", json=_payload()).status_code == 200
    changed = _payload()
    changed[field] = "different immutable authorization truth"
    conflict = client.post("/assessment/comprehensive-intake", json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "public_intake_idempotency_conflict"
    assert calls == 1


def test_explicit_sha_shortcut_is_hash_bound_and_never_calls_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("explicit SHA must persist before snapshot acquisition")

    monkeypatch.setattr(routes, "capture_repository_snapshot", forbidden)
    app = _app(tmp_path / "explicit.db")
    client = TestClient(app)
    payload = _payload("comprun_22222222222222222222222222222222")
    payload["expected_commit_sha"] = "b" * 40
    first = client.post("/assessment/comprehensive-intake", json=payload)
    assert first.status_code == 200
    assert first.json()["explicit_commit_sha_bound"] == "b" * 40
    changed = dict(payload)
    changed["authorization_scope"] = "changed after accepted"
    conflict = client.post("/assessment/comprehensive-intake", json=changed)
    assert conflict.status_code == 409


def test_crash_after_canonical_create_reconciles_exact_get_without_rerun(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _app(tmp_path / "post-create.db")
    service = app.state.comprehensive_api_controller._service
    payload = _payload("comprun_33333333333333333333333333333333")
    payload["expected_commit_sha"] = "c" * 40

    def crash_after_create(**_kwargs):
        raise RuntimeError("synthetic_crash_after_canonical_create")

    monkeypatch.setattr(service, "complete_public_intake", crash_after_create)
    failed = TestClient(app).post("/assessment/comprehensive-intake", json=payload)
    assert failed.status_code == 500
    reservation = service.load_public_intake(payload["run_id"])
    assert reservation is not None and reservation["status"] == "acquiring"

    recovered = TestClient(app).get(
        f"/assessment/comprehensive-run/{payload['run_id']}"
    )
    assert recovered.status_code == 200
    assert recovered.json()["run_id"] == payload["run_id"]
    reconciled = service.load_public_intake(payload["run_id"])
    assert reconciled is not None and reconciled["status"] == "accepted"
    assert "human_evidence" not in reconciled["payload"]


def test_store_validates_hash_size_leases_and_scrubs_terminal_payload(
    tmp_path: Path,
) -> None:
    database = tmp_path / "store.db"
    store = ComprehensiveRunStore(lambda: sqlite3.connect(database), dialect="sqlite")
    store.ensure_schema()
    run_id = "comprun_44444444444444444444444444444444"
    payload = {
        "run_id": run_id,
        "repository": "group/repo",
        "provider": "gitlab",
        "human_evidence": {"secret_duplicate": "sensitive human context"},
    }
    digest = _public_intake_payload_sha256(payload)
    with pytest.raises(ValueError, match="payload_hash_mismatch"):
        store.reserve_public_intake(
            run_id=run_id,
            request_sha256="sha256:" + "0" * 64,
            payload=payload,
            now_epoch=100,
            lease_seconds=10,
            updated_at="2026-08-31T00:00:00Z",
        )
    with pytest.raises(ValueError, match="payload_too_large"):
        huge = {"run_id": run_id, "value": "x" * (129 * 1024)}
        store.reserve_public_intake(
            run_id=run_id,
            request_sha256=_public_intake_payload_sha256(huge),
            payload=huge,
            now_epoch=100,
            lease_seconds=10,
            updated_at="2026-08-31T00:00:00Z",
        )
    first = store.reserve_public_intake(
        run_id=run_id,
        request_sha256=digest,
        payload=payload,
        now_epoch=100,
        lease_seconds=10,
        updated_at="2026-08-31T00:00:00Z",
    )
    assert first["lease_owner"] is True
    assert store.heartbeat_public_intake(
        run_id=run_id,
        lease_id=first["lease_id"],
        lease_until_epoch=120,
        updated_at="2026-08-31T00:00:01Z",
    )
    active = store.reserve_public_intake(
        run_id=run_id,
        request_sha256=digest,
        payload=payload,
        now_epoch=115,
        lease_seconds=10,
        updated_at="2026-08-31T00:00:02Z",
    )
    assert active["lease_owner"] is False
    reclaimed = store.reserve_public_intake(
        run_id=run_id,
        request_sha256=digest,
        payload=payload,
        now_epoch=121,
        lease_seconds=10,
        updated_at="2026-08-31T00:00:03Z",
    )
    assert reclaimed["lease_owner"] is True
    assert store.complete_public_intake(
        run_id=run_id,
        lease_id=reclaimed["lease_id"],
        commit_sha="d" * 40,
        updated_at="2026-08-31T00:00:04Z",
    )
    assert not store.complete_public_intake(
        run_id=run_id,
        lease_id=first["lease_id"],
        commit_sha="d" * 40,
        updated_at="2026-08-31T00:00:05Z",
    )
    terminal = store.load_public_intake(run_id)
    assert terminal is not None and terminal["status"] == "accepted"
    assert terminal["payload"] == {
        "run_id": run_id,
        "repository": "group/repo",
        "provider": "gitlab",
    }


def test_concurrent_stale_reclaim_has_exactly_one_owner(tmp_path: Path) -> None:
    database = tmp_path / "stale.db"
    seed = ComprehensiveRunStore(lambda: sqlite3.connect(database, timeout=10), dialect="sqlite")
    seed.ensure_schema()
    payload = {"run_id": "comprun_55555555555555555555555555555555", "repository": "g/r"}
    digest = _public_intake_payload_sha256(payload)
    seed.reserve_public_intake(
        run_id=payload["run_id"],
        request_sha256=digest,
        payload=payload,
        now_epoch=1,
        lease_seconds=1,
        updated_at="2026-08-31T00:00:00Z",
    )

    def reclaim() -> bool:
        store = ComprehensiveRunStore(
            lambda: sqlite3.connect(database, timeout=10), dialect="sqlite"
        )
        return bool(
            store.reserve_public_intake(
                run_id=payload["run_id"],
                request_sha256=digest,
                payload=payload,
                now_epoch=10,
                lease_seconds=10,
                updated_at="2026-08-31T00:00:10Z",
            )["lease_owner"]
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        owners = list(pool.map(lambda _item: reclaim(), range(8)))
    assert owners.count(True) == 1
