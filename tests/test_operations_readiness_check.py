from __future__ import annotations

import json

from nico.operations_readiness import OPERATIONS_READINESS_SCHEMA
from nico.operations_readiness_check import evaluate_operations_readiness, fetch_operations_readiness, main


class FakeResponse:
    def __init__(self, body: dict, status: int = 200):
        self.status = status
        self._body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


def test_fetch_operations_readiness_uses_semantic_endpoint() -> None:
    calls = []

    def opener(request, timeout=20):
        calls.append((request.full_url, timeout))
        return FakeResponse({"artifact_schema": OPERATIONS_READINESS_SCHEMA, "status": "ready", "operational_ready": True})

    payload = fetch_operations_readiness("https://api.example.test/", opener=opener)

    assert payload["status"] == "ready"
    assert payload["status_code"] == 200
    assert calls == [("https://api.example.test/operations/readiness", 20)]


def test_evaluate_operations_readiness_fails_closed() -> None:
    passed, message = evaluate_operations_readiness({"status": "ready", "operational_ready": True})
    assert passed is False
    assert "schema" in message.lower()

    passed, message = evaluate_operations_readiness(
        {
            "artifact_schema": OPERATIONS_READINESS_SCHEMA,
            "status": "blocked",
            "operational_ready": False,
            "blockers": ["durable_storage"],
        }
    )
    assert passed is False
    assert "durable_storage" in message


def test_evaluate_operations_readiness_requires_explicit_degraded_override() -> None:
    payload = {
        "artifact_schema": OPERATIONS_READINESS_SCHEMA,
        "status": "degraded",
        "operational_ready": False,
        "warnings": ["operator_admin_configured"],
    }

    assert evaluate_operations_readiness(payload)[0] is False
    assert evaluate_operations_readiness(payload, allow_degraded=True)[0] is True


def test_main_returns_two_when_base_url_is_missing(capsys) -> None:
    code = main([])
    captured = capsys.readouterr()

    assert code == 2
    assert "Hosted NICO API URL is required" in captured.out
