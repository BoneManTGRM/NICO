from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.comprehensive_production_bootstrap as bootstrap
from nico.comprehensive_capability_registry import execution_plan


def _executors() -> dict:
    output = {}
    for item in execution_plan():
        capability = str(item["capability"])

        def execute(context, *, _capability=capability):
            return {
                "status": "complete",
                "capability": _capability,
                "run_id": context["run_id"],
                "repository": context["repository"],
                "commit_sha": context["commit_sha"],
                "evidence_ledger_id": context["evidence_ledger_id"],
            }

        output[capability] = execute
    return output


def _payload(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "e" * 40,
        "evidence_ledger_id": f"ledger_{run_id}",
        "customer_id": "customer_hosted",
        "project_id": "project_hosted",
        "authorized": True,
        "authorization_confirmed": True,
    }


def _clear_postgres_aliases(monkeypatch) -> None:
    for key in (
        "DATABASE_URL",
        "DATABASE_PRIVATE_URL",
        "POSTGRES_URL",
        "POSTGRES_PRIVATE_URL",
        "RAILWAY_DATABASE_URL",
        "RAILWAY_POSTGRES_URL",
        "PGHOST",
        "PGUSER",
        "PGPASSWORD",
        "PGDATABASE",
        "PGPORT",
    ):
        monkeypatch.delenv(key, raising=False)


def test_required_sqlite_without_persistent_volume_fails_before_creating_doomed_run(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _clear_postgres_aliases(monkeypatch)
    monkeypatch.setenv("NICO_ENABLE_SQLITE_DURABLE_STORAGE", "true")
    monkeypatch.setenv("NICO_REQUIRE_DURABLE_ASSESSMENT_STORAGE", "true")
    monkeypatch.setenv("NICO_SQLITE_PATH", str(tmp_path / "ephemeral.sqlite3"))
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    monkeypatch.delenv("NICO_DURABLE_VOLUME_PATH", raising=False)
    monkeypatch.delenv("NICO_SQLITE_PERSISTENCE_CONFIRMED", raising=False)

    app = FastAPI()
    controller = bootstrap.install_comprehensive_production_bootstrap(
        app,
        capability_executors=_executors(),
    )

    assert controller is None
    assert app.state.comprehensive_runtime["reason"] == "comprehensive_sqlite_persistent_volume_required"
    response = TestClient(app).post("/assessment/comprehensive-run", json=_payload("comprun_doomed"))
    assert response.status_code == 503
    assert "persistent volume" in response.json()["detail"]["message"].lower()


def test_railway_volume_path_preserves_same_run_after_backend_replacement(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _clear_postgres_aliases(monkeypatch)
    volume = tmp_path / "railway-volume"
    monkeypatch.setenv("NICO_ENABLE_SQLITE_DURABLE_STORAGE", "true")
    monkeypatch.setenv("NICO_REQUIRE_DURABLE_ASSESSMENT_STORAGE", "true")
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(volume))
    monkeypatch.delenv("NICO_SQLITE_PATH", raising=False)
    monkeypatch.delenv("NICO_COMPREHENSIVE_SQLITE_PATH", raising=False)

    first = FastAPI()
    bootstrap.install_comprehensive_production_bootstrap(first, capability_executors=_executors())
    first_runtime = first.state.comprehensive_runtime
    assert first_runtime["persistence_adapter"] == "sqlite"
    assert first_runtime["storage_source"] == "mounted_durable_sqlite"
    assert first_runtime["survives_container_replacement_verified"] is True

    first_client = TestClient(first)
    assert first_client.post(
        "/assessment/comprehensive-run",
        json=_payload("comprun_volume_restart"),
    ).status_code == 200
    advanced = first_client.post(
        "/assessment/comprehensive-run/comprun_volume_restart/continue",
        json={"max_stages": 1},
    ).json()

    replacement = FastAPI()
    bootstrap.install_comprehensive_production_bootstrap(replacement, capability_executors=_executors())
    restored = TestClient(replacement).get(
        "/assessment/comprehensive-run/comprun_volume_restart"
    )

    assert restored.status_code == 200
    assert restored.json()["revision"] == advanced["revision"]
    assert restored.json()["integrity_sha256"] == advanced["integrity_sha256"]
    assert restored.json()["persistence"]["survives_container_replacement_verified"] is True


def test_comprehensive_bootstrap_uses_private_postgres_alias_resolution(
    monkeypatch,
) -> None:
    captured: dict = {}
    sentinel = object()
    monkeypatch.setattr(
        bootstrap,
        "_resolved_postgres_url",
        lambda: ("postgresql://user:secret@private-db/nico", "RAILWAY_DATABASE_URL"),
    )

    def fake_configure(app, **kwargs):
        captured.update(kwargs)
        app.state.comprehensive_runtime = {
            "configured": True,
            "persistence_adapter": "postgres",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        return sentinel

    monkeypatch.setattr(bootstrap, "configure_comprehensive_runtime", fake_configure)
    app = FastAPI()

    controller = bootstrap.install_comprehensive_production_bootstrap(
        app,
        capability_executors=_executors(),
    )

    assert controller is sentinel
    assert captured["database_url"] == "postgresql://user:secret@private-db/nico"
    runtime = app.state.comprehensive_runtime
    assert runtime["database_url_source"] == "RAILWAY_DATABASE_URL"
    assert runtime["storage_source"] == "postgres:RAILWAY_DATABASE_URL"
    assert runtime["survives_container_replacement_verified"] is True
    assert "secret" not in str(runtime)
