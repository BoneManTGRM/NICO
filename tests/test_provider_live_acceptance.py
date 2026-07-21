from __future__ import annotations

from dataclasses import dataclass

import pytest

from nico.provider_credentials import EnvironmentCredentialResolver, build_reference
from nico.provider_live_clients import ProviderCollection
from nico.provider_neutral_contract import ProviderKind
from scripts import provider_live_acceptance


@dataclass
class FakeCollector:
    revisions: list[str]
    provider: ProviderKind = ProviderKind.GITLAB
    index: int = 0
    closed: bool = False

    def __post_init__(self) -> None:
        reference = build_reference(
            provider="gitlab",
            env_var="TOKEN",
            scheme="private_token",
            key_id="fake-live",
            allowed_hosts=("gitlab.example.com",),
            scopes=("read_api", "read_repository"),
        )
        self.credential = EnvironmentCredentialResolver({"TOKEN": "never-export-me"}).resolve(reference)

    def collect(self, repository_id: str, *, revision: str = "") -> ProviderCollection:
        observed = self.revisions[min(self.index, len(self.revisions) - 1)]
        self.index += 1
        exact = revision or observed
        return ProviderCollection(
            provider=self.provider,
            repository_id="17",
            revision=exact,
            payload={
                "instance_url": "https://gitlab.example.com",
                "project": {
                    "id": 17,
                    "path": "repo",
                    "path_with_namespace": repository_id,
                    "namespace": "group",
                    "default_branch": "main",
                },
                "revision": exact,
                "merge_requests": [],
                "pipelines": [{"id": 1, "sha": exact, "ref": "main", "status": "success"}],
                "scopes": ["read_api", "read_repository"],
                "collected_at": f"2026-07-21T00:00:0{self.index}Z",
            },
            pages_fetched=self.index,
            requests_made=self.index + 1,
            collected_at=f"2026-07-21T00:00:0{self.index}Z",
        )

    def close(self) -> None:
        self.closed = True


def test_two_pass_acceptance_preserves_identity_without_exporting_secret(monkeypatch) -> None:
    collector = FakeCollector(["a" * 40, "a" * 40])
    monkeypatch.setattr(provider_live_acceptance, "build_collector", lambda provider: collector)

    result = provider_live_acceptance.run_acceptance(
        provider="gitlab",
        repository="group/repo",
        revision="a" * 40,
        passes=2,
    )

    assert result["status"] == "passed"
    assert result["passes_completed"] == 2
    assert all(result["proof"].values())
    assert len({item["repository_id"] for item in result["runs"]}) == 1
    assert len({item["revision"] for item in result["runs"]}) == 1
    assert "never-export-me" not in str(result)
    assert result["credential_metadata"]["secret_present"] is True
    assert result["client_delivery_allowed"] is False
    assert collector.closed is True


def test_first_pass_pins_revision_for_second_pass(monkeypatch) -> None:
    collector = FakeCollector(["a" * 40, "b" * 40])
    monkeypatch.setattr(provider_live_acceptance, "build_collector", lambda provider: collector)

    result = provider_live_acceptance.run_acceptance(
        provider="gitlab",
        repository="group/repo",
        revision="",
        passes=2,
    )
    assert result["expected_revision"] == "a" * 40
    assert {item["revision"] for item in result["runs"]} == {"a" * 40}


def test_acceptance_rejects_one_pass(monkeypatch) -> None:
    collector = FakeCollector(["a" * 40])
    monkeypatch.setattr(provider_live_acceptance, "build_collector", lambda provider: collector)
    with pytest.raises(provider_live_acceptance.LiveAcceptanceError, match="requires_two_passes"):
        provider_live_acceptance.run_acceptance(
            provider="gitlab",
            repository="group/repo",
            revision="a" * 40,
            passes=1,
        )


def test_unsupported_provider_fails_before_credentials() -> None:
    with pytest.raises(provider_live_acceptance.LiveAcceptanceError, match="unsupported"):
        provider_live_acceptance.build_collector("unknown")
