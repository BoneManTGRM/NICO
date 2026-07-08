from __future__ import annotations

from nico.hosted_metadata_auth import (
    MetadataAuthGitHubAssessmentClient,
    github_metadata_auth_summary,
    run_github_assessment_with_metadata_auth,
)


class FakeResponse:
    status_code = 201
    text = ""

    def json(self):
        return {"token": "installation-token-123"}


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        return FakeResponse()


def test_metadata_client_prefers_github_app_installation_auth(monkeypatch):
    monkeypatch.setenv("NICO_GITHUB_APP_ID", "123")
    monkeypatch.setenv("NICO_GITHUB_APP_PRIVATE_KEY", "private")
    monkeypatch.setenv("NICO_GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("NICO_GITHUB_TOKEN", "fallback-token")
    monkeypatch.setattr("nico.github_app_auth.build_github_app_jwt", lambda: ("app-jwt", None))
    session = FakeSession()

    client = MetadataAuthGitHubAssessmentClient(session=session)

    assert client.auth_mode == "github_app_installation"
    assert client.headers["Authorization"] == "Bearer installation-token-123"
    assert session.calls[0]["url"].endswith("/app/installations/456/access_tokens")
    assert any("GitHub App installation token" in item for item in client.auth_evidence)


def test_metadata_client_falls_back_to_server_token(monkeypatch):
    monkeypatch.delenv("NICO_GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("NICO_GITHUB_APP_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("NICO_GITHUB_APP_INSTALLATION_ID", raising=False)
    monkeypatch.setenv("NICO_GITHUB_TOKEN", "fallback-token")

    client = MetadataAuthGitHubAssessmentClient()

    assert client.auth_mode == "server_token"
    assert client.headers["Authorization"] == "Bearer fallback-token"
    assert any("not configured" in item for item in client.auth_unavailable)


def test_github_metadata_auth_summary_masks_auth_details():
    client = type(
        "Client",
        (),
        {
            "auth_mode": "server_token",
            "auth_evidence": ["Server-side token configured."],
            "auth_unavailable": [],
        },
    )()

    summary = github_metadata_auth_summary(client)

    assert summary == {
        "mode": "server_token",
        "evidence": ["Server-side token configured."],
        "unavailable": [],
    }


def test_assessment_wrapper_uses_auth_aware_client(monkeypatch):
    import nico.hosted_assessment as hosted_assessment

    class FakeClient:
        headers = {"Authorization": "Bearer fake"}
        auth_mode = "github_app_installation"
        auth_evidence = ["GitHub App installation token was created server-side for authorized repository assessment."]
        auth_unavailable = []

    def fake_run_assessment(payload):
        client = hosted_assessment.GitHubAssessmentClient()
        return {
            "status": "complete",
            "repository": payload["repository"],
            "authorization_header_seen": client.headers.get("Authorization"),
        }

    original_client = hosted_assessment.GitHubAssessmentClient
    monkeypatch.setattr(hosted_assessment, "run_github_assessment", fake_run_assessment)

    result = run_github_assessment_with_metadata_auth(
        {"repository": "owner/repo", "authorized": True},
        client_factory=FakeClient,
    )

    assert result["authorization_header_seen"] == "Bearer fake"
    assert result["github_metadata_auth"]["mode"] == "github_app_installation"
    assert hosted_assessment.GitHubAssessmentClient is original_client
