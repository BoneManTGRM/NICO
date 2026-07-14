from __future__ import annotations

import base64

from nico.github_app_auth import build_github_auth_headers, build_github_clone_auth_env, github_app_configured
from nico.hosted_scanner_worker import checkout_for_hosted_scan
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        return FakeResponse(201, {"token": "installation-token-123"})


def _decode_basic_extraheader(value: str) -> str:
    prefix = "AUTHORIZATION: basic "
    assert value.startswith(prefix)
    return base64.b64decode(value[len(prefix):]).decode("utf-8")


def test_github_app_config_requires_all_secret_parts(monkeypatch):
    monkeypatch.setenv("NICO_GITHUB_APP_ID", "123")
    monkeypatch.setenv("NICO_GITHUB_APP_PRIVATE_KEY", "private")
    monkeypatch.delenv("NICO_GITHUB_APP_INSTALLATION_ID", raising=False)

    assert github_app_configured() is False

    monkeypatch.setenv("NICO_GITHUB_APP_INSTALLATION_ID", "456")

    assert github_app_configured() is True


def test_build_github_auth_headers_prefers_installation_token(monkeypatch):
    monkeypatch.setenv("NICO_GITHUB_APP_ID", "123")
    monkeypatch.setenv("NICO_GITHUB_APP_PRIVATE_KEY", "private")
    monkeypatch.setenv("NICO_GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("NICO_GITHUB_TOKEN", "fallback-token")
    monkeypatch.setattr("nico.github_app_auth.build_github_app_jwt", lambda: ("app-jwt", None))
    session = FakeSession()

    result = build_github_auth_headers(session=session)

    assert result.mode == "github_app_installation"
    assert result.headers["Authorization"] == "Bearer installation-token-123"
    assert session.calls[0]["url"].endswith("/app/installations/456/access_tokens")
    assert any("GitHub App installation token" in item for item in result.evidence)


def test_build_github_auth_headers_falls_back_to_server_token(monkeypatch):
    monkeypatch.delenv("NICO_GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("NICO_GITHUB_APP_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("NICO_GITHUB_APP_INSTALLATION_ID", raising=False)
    monkeypatch.setenv("NICO_GITHUB_TOKEN", "fallback-token")

    result = build_github_auth_headers()

    assert result.mode == "server_token"
    assert result.headers["Authorization"] == "Bearer fallback-token"
    assert any("not configured" in item for item in result.unavailable)


def test_clone_auth_uses_git_basic_extraheader_not_token_url(monkeypatch):
    monkeypatch.setenv("NICO_GITHUB_APP_ID", "123")
    monkeypatch.setenv("NICO_GITHUB_APP_PRIVATE_KEY", "private")
    monkeypatch.setenv("NICO_GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setattr("nico.github_app_auth.build_github_app_jwt", lambda: ("app-jwt", None))

    result = build_github_clone_auth_env(session=FakeSession())

    assert result.mode == "github_app_installation"
    assert result.extra_env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert _decode_basic_extraheader(result.extra_env["GIT_CONFIG_VALUE_0"]) == "x-access-token:installation-token-123"
    assert "installation-token-123" not in result.extra_env["GIT_CONFIG_VALUE_0"]


def test_server_token_clone_fallback_uses_git_basic_extraheader(monkeypatch):
    monkeypatch.delenv("NICO_GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("NICO_GITHUB_APP_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("NICO_GITHUB_APP_INSTALLATION_ID", raising=False)
    monkeypatch.setenv("NICO_GITHUB_TOKEN", "fallback-token")

    result = build_github_clone_auth_env()

    assert result.mode == "server_token"
    assert _decode_basic_extraheader(result.extra_env["GIT_CONFIG_VALUE_0"]) == "x-access-token:fallback-token"
    assert "fallback-token" not in result.extra_env["GIT_CONFIG_VALUE_0"]
    assert any("GitHub App installation auth not configured" in item for item in result.unavailable)
    assert not any("No server-side GitHub credential" in item for item in result.unavailable)


def test_checkout_uses_authenticated_extraheader_without_token_in_clone_url(monkeypatch, tmp_path):
    captured = {}
    encoded = base64.b64encode(b"x-access-token:secret-token").decode("ascii")

    def fake_auth_env():
        return type(
            "CloneAuth",
            (),
            {
                "extra_env": {
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                    "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {encoded}",
                }
            },
        )()

    def fake_run_command(args, *, cwd, limits, extra_env=None):
        captured["args"] = tuple(args)
        captured["extra_env"] = dict(extra_env or {})
        return WorkerCommandResult(args=tuple(args), returncode=0, stdout="", stderr="")

    monkeypatch.setattr("nico.hosted_scanner_worker.build_github_clone_auth_env", fake_auth_env)
    monkeypatch.setattr("nico.hosted_scanner_worker.run_command", fake_run_command)

    checkout_for_hosted_scan({"repository": "owner/private", "authorized": True}, WorkerWorkspace(root=tmp_path))

    assert captured["args"][-2] == "https://github.com/owner/private.git"
    assert "secret-token" not in captured["args"][-2]
    assert _decode_basic_extraheader(captured["extra_env"]["GIT_CONFIG_VALUE_0"]) == "x-access-token:secret-token"
