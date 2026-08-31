from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from nico.provider_credentials import EnvironmentCredentialResolver, build_reference
from nico.provider_live_clients import ProviderCollection
from nico.provider_neutral_contract import ProviderKind
from scripts import provider_live_acceptance


@dataclass
class FakeCollector:
    revisions: list[str]
    provider: ProviderKind = ProviderKind.GITLAB
    page_counts: list[int] | None = None
    access_mode: str = "authenticated_read_only"
    credential_used: bool = True
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
        self.credential = (
            EnvironmentCredentialResolver({"TOKEN": "never-export-me"}).resolve(reference)
            if self.credential_used
            else None
        )

    def collect(self, repository_id: str, *, revision: str = "") -> ProviderCollection:
        observed = self.revisions[min(self.index, len(self.revisions) - 1)]
        pages_fetched = (
            self.page_counts[min(self.index, len(self.page_counts) - 1)]
            if self.page_counts
            else 1
        )
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
                    "web_url": "https://gitlab.example.com/group/repo",
                },
                "revision": exact,
                "source_tree": [
                    {
                        "id": "f" * 40,
                        "path": "src/app.py",
                        "type": "blob",
                        "mode": "100644",
                    }
                ],
                "merge_requests": [],
                "pipelines": [{"id": 1, "sha": exact, "ref": "main", "status": "success"}],
                "capability_status": [
                    {"capability": "repository", "state": "supported", "reason": ""},
                    {"capability": "commits", "state": "supported", "reason": ""},
                    {"capability": "branches", "state": "supported", "reason": ""},
                    {"capability": "tree", "state": "supported", "reason": ""},
                    {"capability": "blobs", "state": "supported", "reason": ""},
                    {"capability": "source_links", "state": "supported", "reason": ""},
                ],
                "pagination_complete": True,
                "collection_limitations": [],
                "snapshot_manifest_sha256": "sha256:" + "1" * 64,
                "scopes": ["read_api", "read_repository"],
                "access_mode": self.access_mode,
                "credential_used": self.credential_used,
                "collected_at": f"2026-07-21T00:00:0{self.index}Z",
            },
            pages_fetched=pages_fetched,
            requests_made=2,
            collected_at=f"2026-07-21T00:00:0{self.index}Z",
            access_mode=self.access_mode,
            credential_used=self.credential_used,
        )

    def close(self) -> None:
        self.closed = True


class FakeRequestAudit:
    def __init__(self, authorization_header_observed: bool = True) -> None:
        self.authorization_header_observed = authorization_header_observed

    def safe_metadata(self) -> dict[str, object]:
        return {
            "request_count": 1,
            "authorization_header_observed": self.authorization_header_observed,
            "cookie_header_observed": False,
            "secret_query_observed": False,
        }


class FakeHandle:
    def __init__(self, collector: FakeCollector) -> None:
        self.collector = collector
        self.credential = collector.credential
        self.request_audit = FakeRequestAudit(collector.credential_used)

    def close(self) -> None:
        self.collector.close()


@pytest.mark.parametrize(
    "provider,host",
    (
        ("github", "api.github.com"),
        ("gitlab", "gitlab.com"),
        ("bitbucket_cloud", "api.bitbucket.org"),
        ("azure_devops", "dev.azure.com"),
    ),
)
def test_live_acceptance_builds_a_non_secret_host_policy(provider, host) -> None:
    reference = provider_live_acceptance._credential_reference(provider)

    assert reference.allowed_hosts == (host,)
    assert reference.env_var
    assert not hasattr(reference, "secret")


def test_required_source_evidence_failure_is_an_authentication_required_outcome() -> None:
    error = provider_live_acceptance.ProviderClientError(
        "provider_required_source_evidence_unavailable"
    )

    assert provider_live_acceptance._error_code(error) == (
        "provider_required_source_evidence_unavailable"
    )


def test_two_pass_acceptance_preserves_identity_without_exporting_secret(monkeypatch) -> None:
    collector = FakeCollector(["a" * 40, "a" * 40])
    monkeypatch.setattr(
        provider_live_acceptance,
        "build_collector",
        lambda provider, access_mode: FakeHandle(collector),
    )

    result = provider_live_acceptance.run_acceptance(
        provider="gitlab",
        repository="group/repo",
        revision="a" * 40,
        access_mode="authenticated_read_only",
        passes=2,
    )

    assert result["status"] == "passed"
    assert result["artifact_schema"] == "nico.provider_live_acceptance.v3"
    assert result["provider_support_maturity"] == "REAL_PROVIDER_INTEGRATION_PROVEN"
    assert result["public_anonymous_support_proven"] is False
    assert result["private_provider_support_proven"] is False
    assert result["passes_completed"] == 2
    assert all(result["proof"].values())
    assert len({item["repository_id"] for item in result["runs"]}) == 1
    assert len({item["revision"] for item in result["runs"]}) == 1
    assert all(item["source_object_count"] == 1 for item in result["runs"])
    assert all(item["exact_source_locator_count"] == 1 for item in result["runs"])
    assert "never-export-me" not in str(result)
    assert result["credential_metadata"]["secret_present"] is True
    assert result["credential_metadata"]["credential_used"] is True
    assert result["human_review_required"] is True
    assert result["human_approval_proven"] is False
    assert result["client_delivery_allowed"] is False
    assert collector.closed is True


def test_first_pass_pins_revision_for_second_pass(monkeypatch) -> None:
    collector = FakeCollector(["a" * 40, "b" * 40])
    monkeypatch.setattr(
        provider_live_acceptance,
        "build_collector",
        lambda provider, access_mode: FakeHandle(collector),
    )

    result = provider_live_acceptance.run_acceptance(
        provider="gitlab",
        repository="group/repo",
        revision="",
        access_mode="authenticated_read_only",
        passes=2,
    )
    assert result["expected_revision"] == "a" * 40
    assert {item["revision"] for item in result["runs"]} == {"a" * 40}


def test_complete_optional_pagination_count_may_vary_between_stable_source_passes(
    monkeypatch,
) -> None:
    collector = FakeCollector(["a" * 40, "a" * 40], page_counts=[8, 7])
    monkeypatch.setattr(
        provider_live_acceptance,
        "build_collector",
        lambda provider, access_mode: FakeHandle(collector),
    )

    result = provider_live_acceptance.run_acceptance(
        provider="gitlab",
        repository="group/repo",
        revision="a" * 40,
        access_mode="authenticated_read_only",
        passes=2,
    )

    assert result["proof"]["pagination_complete"] is True
    assert [item["pages_fetched"] for item in result["runs"]] == [8, 7]


def test_flexible_public_outcome_accepts_real_anonymous_success(monkeypatch) -> None:
    collector = FakeCollector(
        ["a" * 40, "a" * 40],
        access_mode="anonymous_public",
        credential_used=False,
    )
    monkeypatch.setattr(
        provider_live_acceptance,
        "_build_azure_collector",
        lambda repository, access_mode: (FakeHandle(collector), repository),
    )

    result = provider_live_acceptance.run_acceptance(
        provider="azure_devops",
        repository="Org/Project/Repo",
        revision="a" * 40,
        access_mode="anonymous_public",
        expected_outcome="success_or_authentication_required",
        passes=2,
    )

    assert result["observed_outcome"] == "success"
    assert result["public_anonymous_support_proven"] is True
    assert result["provider_support_maturity"] == "REAL_PROVIDER_INTEGRATION_PROVEN"


def test_flexible_public_outcome_accepts_stable_authentication_required(monkeypatch) -> None:
    class AuthenticationRequiredCollector:
        credential = None

        def collect(self, repository_id: str, *, revision: str = ""):
            raise provider_live_acceptance.ProviderClientError(
                "provider_read_only_authentication_required"
            )

        def close(self) -> None:
            return None

    collector = AuthenticationRequiredCollector()

    class AuthenticationRequiredHandle:
        credential = None
        request_audit = FakeRequestAudit(False)

        def __init__(self):
            self.collector = collector

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        provider_live_acceptance,
        "_build_azure_collector",
        lambda repository, access_mode: (AuthenticationRequiredHandle(), repository),
    )

    result = provider_live_acceptance.run_acceptance(
        provider="azure_devops",
        repository="Org/Project/Repo",
        revision="",
        access_mode="anonymous_public",
        expected_outcome="success_or_authentication_required",
        passes=2,
    )

    assert result["observed_outcome"] == "authentication_required"
    assert result["public_anonymous_support_proven"] is False
    assert result["provider_support_maturity"] == "IMPLEMENTED_BUT_UNPROVEN"
    assert result["proof"]["no_misleading_empty_report"] is True


def test_flexible_public_outcome_rejects_success_authentication_drift(monkeypatch) -> None:
    class DriftingCollector(FakeCollector):
        def collect(self, repository_id: str, *, revision: str = "") -> ProviderCollection:
            if self.index:
                raise provider_live_acceptance.ProviderClientError(
                    "provider_read_only_authentication_required"
                )
            return super().collect(repository_id, revision=revision)

    collector = DriftingCollector(
        ["a" * 40],
        access_mode="anonymous_public",
        credential_used=False,
    )
    monkeypatch.setattr(
        provider_live_acceptance,
        "_build_azure_collector",
        lambda repository, access_mode: (FakeHandle(collector), repository),
    )

    with pytest.raises(
        provider_live_acceptance.LiveAcceptanceError,
        match="provider_acceptance_outcome_drift",
    ):
        provider_live_acceptance.run_acceptance(
            provider="azure_devops",
            repository="Org/Project/Repo",
            revision="a" * 40,
            access_mode="anonymous_public",
            expected_outcome="success_or_authentication_required",
            passes=2,
        )


def test_acceptance_rejects_one_pass(monkeypatch) -> None:
    collector = FakeCollector(["a" * 40])
    monkeypatch.setattr(
        provider_live_acceptance,
        "build_collector",
        lambda provider, access_mode: FakeHandle(collector),
    )
    with pytest.raises(provider_live_acceptance.LiveAcceptanceError, match="requires_two_passes"):
        provider_live_acceptance.run_acceptance(
            provider="gitlab",
                repository="group/repo",
                revision="a" * 40,
                access_mode="authenticated_read_only",
                passes=1,
        )


def test_unsupported_provider_fails_before_credentials() -> None:
    with pytest.raises(provider_live_acceptance.LiveAcceptanceError, match="unsupported"):
        provider_live_acceptance.build_collector("unknown", "anonymous_public")


def test_provider_changes_trigger_four_isolated_anonymous_public_proofs() -> None:
    workflow = Path(".github/workflows/provider-live-acceptance.yml").read_text(
        encoding="utf-8"
    )

    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "anonymous-public-release:" in workflow
    for fixture in (
        "octocat/Hello-World",
        "gitlab-org/gitlab-test",
        "atlassian_tutorial/helloworld",
        "clearmeasurelabs/Onion-DevOps-Architecture/Onion-DevOps-Architecture-vnext-security",
    ):
        assert fixture in workflow
    assert workflow.count("--passes 2") >= 3
    assert "github.event.pull_request.head.sha" in workflow
    assert workflow.count("expected_outcome: success\n") == 3
    assert "expected_outcome: success_or_authentication_required" in workflow
    assert "--workflow-sha \"${ACCEPTANCE_SHA}\"" in workflow
    assert "unset NICO_GITHUB_TOKEN GITHUB_TOKEN GH_TOKEN" in workflow
    assert "unset NICO_GITLAB_TOKEN GITLAB_TOKEN" in workflow
    assert "unset NICO_BITBUCKET_CLOUD_TOKEN BITBUCKET_TOKEN" in workflow
    assert "unset NICO_AZURE_DEVOPS_TOKEN" in workflow
