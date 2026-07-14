from __future__ import annotations

import os

from nico.frontend_cors_policy import (
    REQUIRED_FRONTEND_ORIGINS,
    install_required_frontend_cors_origins,
    required_frontend_cors_origins,
)


def test_required_frontend_origins_survive_configured_overrides(monkeypatch) -> None:
    partner_origin = "https://partner.example"
    app_origin = "https://app.nicoaudit.com"
    monkeypatch.setenv(
        "NICO_CORS_ORIGINS",
        f"{partner_origin},{app_origin}/",
    )

    result = install_required_frontend_cors_origins()
    origins = os.environ["NICO_CORS_ORIGINS"].split(",")

    for required in REQUIRED_FRONTEND_ORIGINS:
        assert any(origin == required for origin in origins)
    assert any(origin == partner_origin for origin in origins)
    assert sum(origin == app_origin for origin in origins) == 1
    assert result["wildcard_allowed"] is False
    assert result["credentials_in_origin_allowed"] is False


def test_cors_policy_rejects_wildcards_credentials_paths_and_non_http_origins() -> None:
    credential_origin = "https://user:secret@example.com"
    path_origin = "https://example.com/path"
    file_origin = "file:///tmp/socket"
    valid_origin = "https://valid.example"
    origins = required_frontend_cors_origins(
        f"*,{credential_origin},{path_origin},{file_origin},{valid_origin}"
    )

    assert all(origin != "*" for origin in origins)
    assert all(origin != credential_origin for origin in origins)
    assert all(origin != path_origin for origin in origins)
    assert all(origin != file_origin for origin in origins)
    assert any(origin == valid_origin for origin in origins)


def test_cors_policy_is_deterministic_and_deduplicated() -> None:
    app_origin = "https://app.nicoaudit.com"
    localhost_origin = "http://localhost:3000"
    origins = required_frontend_cors_origins(
        f"{app_origin},{app_origin}/,{localhost_origin}"
    )

    assert origins[: len(REQUIRED_FRONTEND_ORIGINS)] == list(REQUIRED_FRONTEND_ORIGINS)
    assert len(origins) == len(set(origins))
