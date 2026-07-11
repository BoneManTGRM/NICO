from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from nico import public_delivery_boundary as boundary
from nico.api.hosted import register_hosted_extension_routes
from nico.public_delivery_boundary import (
    PublicDeliveryBoundaryMiddleware,
    client_fingerprint,
    client_network_identifier,
    consume_public_delivery_limit,
    install_public_delivery_boundary,
    public_delivery_boundary_status,
)


@pytest.fixture(autouse=True)
def isolated_boundary(monkeypatch):
    monkeypatch.setattr(boundary, "_database_url", lambda: "")
    monkeypatch.setenv("NICO_DELIVERY_RATE_LIMIT_SECRET", "test-rate-secret")
    monkeypatch.setenv("NICO_DELIVERY_RATE_LIMIT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("NICO_DELIVERY_INSPECT_RATE_LIMIT", "30")
    monkeypatch.setenv("NICO_DELIVERY_REDEEM_RATE_LIMIT", "20")
    monkeypatch.setenv("NICO_DELIVERY_ACKNOWLEDGE_RATE_LIMIT", "20")
    monkeypatch.setenv("NICO_DELIVERY_MAX_BODY_BYTES", "16384")
    monkeypatch.delenv("NICO_TRUST_PROXY_HEADERS", raising=False)
    with boundary._MEMORY_LOCK:
        boundary._MEMORY_BUCKETS.clear()
        boundary._LAST_CLEANUP = 0
    with boundary._SCHEMA_LOCK:
        boundary._SCHEMA_READY_URL = ""
        boundary._SCHEMA_RETRY_AT = 0.0
    yield
    with boundary._MEMORY_LOCK:
        boundary._MEMORY_BUCKETS.clear()
        boundary._LAST_CLEANUP = 0


def _scope(client: str = "10.0.0.8", forwarded: str = "") -> dict:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return {"type": "http", "method": "POST", "path": "/delivery/approved/inspect", "headers": headers, "client": (client, 12345)}


def _app(cors: bool = False) -> FastAPI:
    app = FastAPI()
    if cors:
        app.add_middleware(CORSMiddleware, allow_origins=["https://app.nicoaudit.com"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.post("/delivery/approved/inspect")
    async def inspect():
        return {"status": "ok", "available": False}

    @app.post("/delivery/approved/redeem")
    async def redeem():
        return {"status": "ok", "available": False}

    @app.post("/delivery/approved/acknowledge")
    async def acknowledge():
        return {"status": "ok", "available": False}

    @app.post("/unrelated")
    async def unrelated():
        return {"status": "ok"}

    install_public_delivery_boundary(app)
    return app


def test_fixed_window_limit_blocks_only_after_configured_count(monkeypatch):
    monkeypatch.setenv("NICO_DELIVERY_INSPECT_RATE_LIMIT", "2")
    first = consume_public_delivery_limit("/delivery/approved/inspect", "client-a", now_epoch=120)
    second = consume_public_delivery_limit("/delivery/approved/inspect", "client-a", now_epoch=120)
    blocked = consume_public_delivery_limit("/delivery/approved/inspect", "client-a", now_epoch=120)
    reset = consume_public_delivery_limit("/delivery/approved/inspect", "client-a", now_epoch=180)
    assert first["allowed"] and first["remaining"] == 1
    assert second["allowed"] and second["remaining"] == 0
    assert not blocked["allowed"] and blocked["retry_after"] == 60
    assert reset["allowed"] and reset["remaining"] == 1


def test_client_identifier_uses_proxy_headers_only_when_trusted(monkeypatch):
    scope = _scope(forwarded="203.0.113.25, 10.0.0.2")
    assert client_network_identifier(scope) == "10.0.0.8"
    monkeypatch.setenv("NICO_TRUST_PROXY_HEADERS", "true")
    assert client_network_identifier(scope) == "203.0.113.25"


def test_raw_network_identifier_is_never_stored(monkeypatch):
    monkeypatch.setenv("NICO_TRUST_PROXY_HEADERS", "true")
    raw = "203.0.113.77"
    fingerprint = client_fingerprint(_scope(forwarded=raw))
    consume_public_delivery_limit("/delivery/approved/inspect", fingerprint, now_epoch=120)
    assert raw not in repr(boundary._MEMORY_BUCKETS)
    assert fingerprint not in repr(boundary._MEMORY_BUCKETS)
    assert all(len(key) == 64 for key in boundary._MEMORY_BUCKETS)


def test_public_endpoint_rate_limit_has_generic_secure_cors_response(monkeypatch):
    monkeypatch.setenv("NICO_TRUST_PROXY_HEADERS", "true")
    monkeypatch.setenv("NICO_DELIVERY_INSPECT_RATE_LIMIT", "1")
    client = TestClient(_app(cors=True))
    headers = {"Origin": "https://app.nicoaudit.com", "X-Forwarded-For": "203.0.113.9"}
    assert client.post("/delivery/approved/inspect", json={"token": "one"}, headers=headers).status_code == 200
    blocked = client.post("/delivery/approved/inspect", json={"token": "two"}, headers=headers)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "public_delivery_rate_limited"
    assert blocked.headers["cache-control"] == "no-store, private, max-age=0"
    assert blocked.headers["referrer-policy"] == "no-referrer"
    assert blocked.headers["x-ratelimit-limit"] == "1"
    assert blocked.headers["access-control-allow-origin"] == "https://app.nicoaudit.com"


def test_rate_limits_are_separate_by_client_and_route(monkeypatch):
    monkeypatch.setenv("NICO_TRUST_PROXY_HEADERS", "true")
    monkeypatch.setenv("NICO_DELIVERY_INSPECT_RATE_LIMIT", "1")
    monkeypatch.setenv("NICO_DELIVERY_REDEEM_RATE_LIMIT", "1")
    client = TestClient(_app())
    assert client.post("/delivery/approved/inspect", json={"token": "a"}, headers={"X-Forwarded-For": "203.0.113.1"}).status_code == 200
    assert client.post("/delivery/approved/inspect", json={"token": "b"}, headers={"X-Forwarded-For": "203.0.113.1"}).status_code == 429
    assert client.post("/delivery/approved/redeem", json={"token": "c"}, headers={"X-Forwarded-For": "203.0.113.1"}).status_code == 200
    assert client.post("/delivery/approved/inspect", json={"token": "d"}, headers={"X-Forwarded-For": "203.0.113.2"}).status_code == 200


def test_success_response_gets_security_and_limit_headers(monkeypatch):
    monkeypatch.setenv("NICO_DELIVERY_INSPECT_RATE_LIMIT", "3")
    response = TestClient(_app()).post("/delivery/approved/inspect", json={"token": "example"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private, max-age=0"
    assert response.headers["cross-origin-resource-policy"] == "same-site"
    assert response.headers["x-ratelimit-limit"] == "3"
    assert response.headers["x-ratelimit-remaining"] == "2"


def test_oversized_request_and_fields_are_blocked(monkeypatch):
    monkeypatch.setenv("NICO_DELIVERY_MAX_BODY_BYTES", "1024")
    client = TestClient(_app())
    large = client.post("/delivery/approved/inspect", content=b"x" * 2048, headers={"Content-Type": "application/json"})
    assert large.status_code == 413
    assert large.json()["code"] == "public_delivery_request_too_large"
    monkeypatch.setenv("NICO_DELIVERY_MAX_BODY_BYTES", "8192")
    field = client.post("/delivery/approved/inspect", json={"token": "x" * 4097})
    assert field.status_code == 413
    assert field.json()["code"] == "public_delivery_field_too_large"


def test_unrelated_routes_are_not_limited():
    client = TestClient(_app())
    assert client.post("/unrelated").status_code == 200
    second = client.post("/unrelated")
    assert second.status_code == 200
    assert "x-ratelimit-limit" not in second.headers


def test_installation_and_hosted_registration_are_idempotent():
    target = FastAPI()
    install_public_delivery_boundary(target)
    install_public_delivery_boundary(target)
    assert sum(1 for item in target.user_middleware if item.cls is PublicDeliveryBoundaryMiddleware) == 1
    hosted_target = FastAPI()
    register_hosted_extension_routes(hosted_target)
    register_hosted_extension_routes(hosted_target)
    assert sum(1 for item in hosted_target.user_middleware if item.cls is PublicDeliveryBoundaryMiddleware) == 1


def test_boundary_status_is_sanitized(monkeypatch):
    monkeypatch.setenv("NICO_DELIVERY_RATE_LIMIT_SECRET", "do-not-return-this")
    status = public_delivery_boundary_status()
    assert status["status"] == "ready"
    assert status["field_limits"]["token"] == 4096
    assert "do-not-return-this" not in repr(status)
    assert "NICO_ADMIN_TOKEN" not in repr(status)


def test_docker_enables_proxy_headers_on_production_entrypoint():
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")
    assert "ENV NICO_TRUST_PROXY_HEADERS=true" in dockerfile
    assert "uvicorn nico.api.production:app" in dockerfile
