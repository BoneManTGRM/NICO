from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import register_comprehensive_api_routes
from nico.comprehensive_engagement_metadata_v1 import (
    VERSION as ENGAGEMENT_VERSION,
    normalize_comprehensive_engagement_metadata,
)
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import ComprehensiveRunStore


RUN_ID = "comprun_durable_browser_projection_v1"


def _store(database: Path) -> ComprehensiveRunStore:
    store = ComprehensiveRunStore(
        lambda: sqlite3.connect(database),
        dialect="sqlite",
    )
    store.ensure_schema()
    return store


def _app(store: ComprehensiveRunStore) -> tuple[FastAPI, ComprehensiveRunService]:
    service = ComprehensiveRunService(store, {})
    controller = ComprehensiveApiController(service)
    app = FastAPI()
    register_comprehensive_api_routes(app, controller=controller)
    return app, service


def _start(service: ComprehensiveRunService) -> None:
    engagement_metadata = normalize_comprehensive_engagement_metadata(
        {
            "artifact_schema": ENGAGEMENT_VERSION,
            "client_name": "Cliente — México",
            "project_name": "Auditoría NICO",
            "primary_technical_contact": "Ana María — líder técnica",
            "access_method": "GitHub HTTPS/API — solo lectura",
            "authorized_scope": "Repositorio completo — rama main",
        }
    )
    service.start(
        run_id=RUN_ID,
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger_durable_browser_projection_v1",
        customer_id="customer_durable_browser_projection_v1",
        project_id="project_durable_browser_projection_v1",
        authorized=True,
        assessment_depth="comprehensive",
        report_language="es-MX",
        engagement_metadata=engagement_metadata,
    )


def test_browser_status_survives_restart_without_loading_full_canonical_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database = tmp_path / "comprehensive.sqlite3"
    initial_store = _store(database)
    _initial_app, initial_service = _app(initial_store)
    _start(initial_service)

    projected = initial_store.load_browser_projection(RUN_ID)
    assert projected is not None
    assert len(json.dumps(projected, ensure_ascii=False).encode("utf-8")) < 200_000

    restarted_store = _store(database)
    restarted_app, _restarted_service = _app(restarted_store)

    def fail_full_load(_run_id: str) -> dict:
        raise AssertionError("browser status must not materialize the full canonical payload")

    monkeypatch.setattr(restarted_store, "load", fail_full_load)
    client = TestClient(restarted_app, raise_server_exceptions=False)
    response = client.get(
        f"/assessment/comprehensive-run/{RUN_ID}",
        headers={"x-nico-browser-projection": "terminal-manifest-v1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == RUN_ID
    assert payload["report_language"] == "es-MX"
    assert payload["engagement_metadata"]["client_name"] == "Cliente — México"
    assert payload["response_projection"]["browser_projection"] is True

    full_response = client.get(f"/assessment/comprehensive-run/{RUN_ID}")
    assert full_response.status_code == 500


def test_browser_projection_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "comprehensive.sqlite3"
    store = _store(database)
    _application, service = _app(store)
    _start(service)

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            UPDATE nico_comprehensive_browser_projections
            SET projection_sha256 = ?
            WHERE run_id = ?
            """,
            ("0" * 64, RUN_ID),
        )
        connection.commit()

    try:
        store.load_browser_projection(RUN_ID)
    except ValueError as exc:
        assert str(exc) == "browser_projection_hash_mismatch"
    else:
        raise AssertionError("a corrupted browser projection must fail closed")

    client = TestClient(_application, raise_server_exceptions=False)
    response = client.get(
        f"/assessment/comprehensive-run/{RUN_ID}",
        headers={"x-nico-browser-projection": "terminal-manifest-v1"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == (
        "comprehensive_browser_projection_integrity_invalid"
    )


def test_browser_projection_advances_in_same_run_transaction(tmp_path: Path) -> None:
    database = tmp_path / "comprehensive.sqlite3"
    store = _store(database)
    _application, service = _app(store)
    _start(service)

    initial = store.load_browser_projection(RUN_ID)
    assert initial is not None
    assert initial["revision"] == 1
    assert initial["canonical_status"] == "ready"

    updated = service.resume(RUN_ID, max_stages=1)
    assert updated["revision"] == 2
    assert updated["status"] == "blocked"

    projected = store.load_browser_projection(RUN_ID)
    assert projected is not None
    assert projected["revision"] == updated["revision"]
    assert projected["integrity_sha256"] == updated["integrity_sha256"]
    assert projected["canonical_status"] == updated["status"]
    assert projected["terminal"] is True
