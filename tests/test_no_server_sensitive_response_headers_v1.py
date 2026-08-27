from __future__ import annotations

import json

import requests

import nico.no_server_assessment as no_server


class _Response:
    status_code = 200
    url = "http://example.test/redirected?session=should-not-be-retained"
    headers = {
        "Content-Security-Policy": "default-src 'self'",
        "Strict-Transport-Security": "max-age=31536000",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "geolocation=()",
        "Set-Cookie": "session=supersecretcookievalue; Secure; HttpOnly; SameSite=Lax",
        "Authorization": "Bearer supersecretauthorizationvalue",
        "Access-Control-Allow-Origin": "https://example.test",
    }


def test_passive_url_check_never_retains_sensitive_response_header_values(monkeypatch) -> None:
    monkeypatch.setattr(no_server.requests, "get", lambda *_args, **_kwargs: _Response())

    result = no_server.passive_url_check("http://example.test", authorized=True, passive_only=True)
    serialized = json.dumps(result, sort_keys=True)

    assert "supersecretcookievalue" not in serialized
    assert "supersecretauthorizationvalue" not in serialized
    assert "should-not-be-retained" not in serialized
    assert "Set-Cookie header present; cookie values are intentionally not collected or retained." in serialized


def test_passive_url_check_never_retains_request_exception_details(monkeypatch) -> None:
    fixture_value = "supersecretexceptionvalue"

    def _raise(*_args, **_kwargs):
        raise requests.RequestException(f"request failed with token={fixture_value}")

    monkeypatch.setattr(no_server.requests, "get", _raise)

    result = no_server.passive_url_check("http://example.test", authorized=True, passive_only=True)
    serialized = json.dumps(result, sort_keys=True)

    assert fixture_value not in serialized
    assert "HTTP reachability check failed; exception details are intentionally not retained." in serialized
