from __future__ import annotations

import io
from urllib.error import HTTPError, URLError

import pytest

from nico.hosted_readiness_smoke_check import check_endpoint, main, normalize_base_url, run_smoke_check


class FakeResponse:
    def __init__(self, status: int, body: str):
        self.status = status
        self._body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


def opener_with_payloads(payloads):
    calls = []

    def opener(request, timeout=15):
        calls.append(request.full_url)
        payload = payloads[len(calls) - 1]
        if isinstance(payload, Exception):
            raise payload
        return FakeResponse(payload[0], payload[1])

    opener.calls = calls
    return opener


def test_normalize_base_url_requires_http_scheme():
    assert normalize_base_url("https://api.example.com/") == "https://api.example.com"
    with pytest.raises(ValueError):
        normalize_base_url("api.example.com")


def test_check_endpoint_marks_successful_json_response_ok():
    opener = opener_with_payloads([(200, '{"status":"ok"}')])

    check = check_endpoint("https://api.example.com", "health", opener=opener)

    assert check.ok is True
    assert check.path == "/health"
    assert check.status_code == 200
    assert check.payload["status"] == "ok"
    assert opener.calls == ["https://api.example.com/health"]


def test_run_smoke_check_summarizes_failed_endpoint():
    opener = opener_with_payloads([
        (200, '{"status":"ok"}'),
        HTTPError("https://api.example.com/diagnostics/hosted-scanner-runtime", 404, "missing", {}, io.BytesIO(b'{"detail":"missing"}')),
        URLError("offline"),
    ])

    result = run_smoke_check("https://api.example.com", opener=opener)

    assert result["status"] == "failed"
    assert result["endpoint_count"] == 3
    assert result["passed_count"] == 1
    assert result["failed_count"] == 2
    assert result["checks"][1]["status_code"] == 404
    assert result["checks"][2]["ok"] is False
    assert "does not approve client delivery" in result["guardrail"]


def test_main_returns_two_when_base_url_missing(capsys):
    code = main([])

    captured = capsys.readouterr()
    assert code == 2
    assert "Hosted NICO API URL is required" in captured.out
