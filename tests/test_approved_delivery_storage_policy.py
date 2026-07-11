from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico import approved_delivery_access as access_store
from nico import approved_delivery_acknowledgments as acknowledgment_store
from nico import approved_delivery_receipts as receipt_store
from nico.api import hosted
from nico.approved_delivery_storage_policy import (
    delivery_storage_readiness,
    durable_delivery_storage_required,
    validate_delivery_persistence,
)


def test_storage_policy_is_optional_outside_hosted_deployment(monkeypatch):
    monkeypatch.delenv("NICO_REQUIRE_DURABLE_DELIVERY_STORAGE", raising=False)

    result = validate_delivery_persistence({"durable": False, "adapter": "memory"}, "access-grant")

    assert durable_delivery_storage_required() is False
    assert result["status"] == "ready"
    assert result["ready"] is True
    assert result["required"] is False
    assert result["adapter"] == "memory"


def test_storage_policy_blocks_memory_when_durability_is_required(monkeypatch):
    monkeypatch.setenv("NICO_REQUIRE_DURABLE_DELIVERY_STORAGE", "true")

    result = validate_delivery_persistence({"durable": False, "adapter": "memory"}, "delivery-receipt")

    assert durable_delivery_storage_required() is True
    assert result["status"] == "blocked"
    assert result["ready"] is False
    assert "DATABASE_URL" in result["message"]


def test_storage_readiness_requires_all_delivery_record_types(monkeypatch):
    monkeypatch.setenv("NICO_REQUIRE_DURABLE_DELIVERY_STORAGE", "true")
    monkeypatch.setattr(access_store, "_persistence_status", lambda: {"durable": True, "adapter": "postgres"})
    monkeypatch.setattr(receipt_store, "_persistence_status", lambda: {"durable": False, "adapter": "memory"})
    monkeypatch.setattr(acknowledgment_store, "_persistence_status", lambda: {"durable": True, "adapter": "postgres"})

    readiness = delivery_storage_readiness()

    assert readiness["status"] == "blocked"
    assert readiness["ready"] is False
    assert readiness["components"]["access_grants"]["ready"] is True
    assert readiness["components"]["delivery_receipts"]["ready"] is False
    assert readiness["components"]["client_acknowledgments"]["ready"] is True


def test_storage_readiness_passes_when_all_delivery_stores_are_durable(monkeypatch):
    monkeypatch.setenv("NICO_REQUIRE_DURABLE_DELIVERY_STORAGE", "true")
    durable = lambda: {"durable": True, "adapter": "postgres"}
    monkeypatch.setattr(access_store, "_persistence_status", durable)
    monkeypatch.setattr(receipt_store, "_persistence_status", durable)
    monkeypatch.setattr(acknowledgment_store, "_persistence_status", durable)

    readiness = delivery_storage_readiness()

    assert readiness["status"] == "ready"
    assert readiness["ready"] is True
    assert all(item["durable"] for item in readiness["components"].values())


def test_hosted_middleware_blocks_external_delivery_writes_when_storage_is_not_ready(monkeypatch):
    blocked = {
        "status": "blocked",
        "ready": False,
        "durable_storage_required": True,
        "components": {"access_grants": {"ready": False, "adapter": "memory"}},
        "rule": "test rule",
    }
    monkeypatch.setattr(hosted, "delivery_storage_readiness", lambda: blocked)
    target = FastAPI()
    hosted.register_hosted_extension_routes(target)
    client = TestClient(target)

    create_link = client.post(
        "/assessment/full-run/example/approved-delivery/access",
        json={"customer_id": "default_customer", "project_id": "default_project"},
    )
    redeem = client.post("/delivery/approved/redeem", json={"token": "example"})
    acknowledge = client.post(
        "/delivery/approved/acknowledge",
        json={"token": "example", "receipt_id": "receipt", "acknowledged_by": "Client", "acknowledged": True},
    )

    for response in (create_link, redeem, acknowledge):
        assert response.status_code == 503
        assert response.json()["code"] == "durable_delivery_storage_unavailable"
        assert response.headers["cache-control"] == "no-store, private, max-age=0"


def test_hosted_readiness_endpoint_is_public_and_sanitized(monkeypatch):
    readiness = {
        "status": "ready",
        "ready": True,
        "durable_storage_required": True,
        "components": {
            "access_grants": {"status": "ready", "ready": True, "durable": True, "adapter": "postgres"},
            "delivery_receipts": {"status": "ready", "ready": True, "durable": True, "adapter": "postgres"},
            "client_acknowledgments": {"status": "ready", "ready": True, "durable": True, "adapter": "postgres"},
        },
        "rule": "durable delivery required",
    }
    monkeypatch.setattr(hosted, "delivery_storage_readiness", lambda: readiness)
    target = FastAPI()
    hosted.register_hosted_extension_routes(target)
    client = TestClient(target)

    response = client.get("/delivery/storage-readiness")

    assert response.status_code == 200
    assert response.json() == readiness
    assert "DATABASE_URL" not in response.text


def test_docker_requires_durable_delivery_storage():
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")

    assert "ENV NICO_REQUIRE_DURABLE_DELIVERY_STORAGE=true" in dockerfile
    assert "uvicorn nico.api.hosted:app" in dockerfile
