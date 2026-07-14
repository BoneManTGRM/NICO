from __future__ import annotations

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


class FailedSession(FakeSession):
    def post(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        return FakeResponse(403, {"message": "forbidden"})


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
    assert result.unavailable == []


def test_build_github_auth_headers_falls_back_without_false_unavailable_warning(monkeypatch):
    monkeypatch.delenv("NICO_GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("NICO_GITHUB_APP_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("NICO_GITHUB_APP_INSTALLATION_ID", raising=False)
    monkeypatch.setenv("NICO_GITHUB_TOKEN", "fallback-token")

    result = build_github_auth_headers()

    assert result.mode == "server_token"
    assert result.headers["Authorization"] == "Bearer fallback-token"
    assert result.unavailable == []
    assert any("server-side GitHub token fallback was used" in item for item in result.evidence)
    assert not any("not configured" in item for item in result.unavailable)


def test_failed_preferred_auth_is_reclassified_when_server_fallback_works(monkeypatch):
    monkeypatch.setenv("NICO_GITHUB_APP_ID", "123")
    monkeypatch.setenv("NICO_GITHUB_APP_PRIVATE_KEY", "private")
    monkeypatch.setenv("NICO_GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("NICO_GITHUB_TOKEN", "fallback-token")
    monkeypatch.setattr("nico.github_app_auth.build_github_app_jwt", lambda: ("app-jwt", None))

    result = build_github_auth_headers(session=FailedSession())

    assert result.mode == "server_token"
    assert result.headers["Authorization"] == "Bearer fallback-token"
    assert result.unavailable == []
    assert any("server-side GitHub token fallback was used" in item for item in result.evidence)


def test_clone_auth_uses_git_extraheader_not_token_url(monkeypatch):
    monkeypatch.setenv("NICO_GITHUB_APP_ID", "123")
    monkeypatch.setenv("NICO_GITHUB_APP_PRIVATE_KEY", "private")
    monkeypatch.setenv("NICO_GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setattr("nico.github_app_auth.build_github_app_jwt", lambda: ("app-jwt", None))

    result = build_github_clone_auth_env(session=FakeSession())

    assert result.mode == "github_app_installation"
    assert result.extra_env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert result.extra_env["GIT_CONFIG_VALUE_0"] == "AUTHORIZATION: bearer installation-token-123"
    assert result.unavailable == []


def test_clone_auth_server_fallback_is_available_checkout_evidence(monkeypatch):
    monkeypatch.delenv("NICO_GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("NICO_GITHUB_APP_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("NICO_GITHUB_APP_INSTALLATION_ID", raising=False)
    monkeypatch.setenv("NICO_GITHUB_TOKEN", "fallback-token")

    result = build_github_clone_auth_env()

    assert result.mode == "server_token"
    assert result.extra_env["GIT_CONFIG_VALUE_0"] == "AUTHORIZATION: bearer fallback-token"
    assert result.unavailable == []
    assert any("authorized repository checkout" in item for item in result.evidence)


def test_anonymous_auth_preserves_real_credential_unavailability(monkeypatch):
    for key in (
        "NICO_GITHUB_APP_ID",
        "NICO_GITHUB_APP_PRIVATE_KEY",
        "NICO_GITHUB_APP_INSTALLATION_ID",
        "NICO_GITHUB_TOKEN",
        "GITHUB_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)

    api = build_github_auth_headers()
    clone = build_github_clone_auth_env()

    assert api.mode == "anonymous"
    assert clone.mode == "anonymous"
    assert any("GitHub App installation auth not configured" in item for item in api.unavailable)
    assert any("No server-side GitHub credential" in item for item in api.unavailable)
    assert any("No server-side GitHub credential" in item for item in clone.unavailable)


def test_checkout_uses_authenticated_extraheader_without_token_in_clone_url(monkeypatch, tmp_path):
    captured = {}

    def fake_auth_env():
        return type(
            "CloneAuth",
            (),
            {
                "extra_env": {
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                    "GIT_CONFIG_VALUE_0": "AUTHORIZATION: bearer secret-token",
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
    assert captured["extra_env"]["GIT_CONFIG_VALUE_0"] == "AUTHORIZATION: bearer secret-token"
