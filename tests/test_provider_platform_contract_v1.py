from __future__ import annotations

from dataclasses import dataclass

import pytest

from nico.provider_platform_contract_v1 import (
    ProviderCapabilitySet,
    ProviderContractViolation,
    ProviderKind,
    RepositoryIdentity,
    TIER1_REQUIRED_CAPABILITIES,
    assert_tier1_conformance,
    capability_limitations,
    validate_provider,
)


@dataclass
class FakeProvider:
    kind: ProviderKind = ProviderKind.GITLAB
    capabilities: ProviderCapabilitySet = TIER1_REQUIRED_CAPABILITIES
    resolved_revision: str = "a" * 40

    def authenticate(self):
        return {"authenticated": True}

    def get_repository_identity(self) -> RepositoryIdentity:
        return RepositoryIdentity(
            provider=self.kind,
            provider_instance="gitlab.example.com",
            organization_or_workspace="engineering",
            project="platform",
            repository="service",
            repository_id="42",
            branch="main",
            immutable_revision="a" * 40,
            provider_evidence_artifact="provider-snapshot.json",
            provider_evidence_sha256="b" * 64,
        )

    def resolve_immutable_revision(self, revision=None):
        return self.resolved_revision

    def snapshot_repository(self, revision):
        return {"revision": revision}

    def list_branches(self):
        return ("main",)

    def list_commits(self, *, limit=100):
        return ()

    def list_change_requests(self, *, limit=100):
        return ()

    def list_pipeline_runs(self, *, revision=None, limit=100):
        return ()

    def list_branch_policies(self):
        return ()

    def list_deployments(self, *, limit=100):
        return ()

    def download_artifact(self, artifact_reference):
        return b"{}"


def test_tier1_provider_requires_exact_immutable_revision() -> None:
    provider = FakeProvider(resolved_revision="c" * 40)
    with pytest.raises(ProviderContractViolation, match="revision mismatch"):
        validate_provider(provider)


def test_snapshot_capability_requires_hashed_provider_artifact() -> None:
    provider = FakeProvider()
    identity = provider.get_repository_identity()
    provider.get_repository_identity = lambda: RepositoryIdentity(
        provider=identity.provider,
        provider_instance=identity.provider_instance,
        organization_or_workspace=identity.organization_or_workspace,
        project=identity.project,
        repository=identity.repository,
        repository_id=identity.repository_id,
        branch=identity.branch,
        immutable_revision=identity.immutable_revision,
    )
    with pytest.raises(ProviderContractViolation, match="hashed provider evidence artifact"):
        validate_provider(provider)


def test_tier1_conformance_passes_for_complete_provider() -> None:
    assert_tier1_conformance(FakeProvider())


def test_missing_provider_capability_creates_limitation_not_fake_defect() -> None:
    provider = FakeProvider(
        capabilities=ProviderCapabilitySet(
            repository_snapshot=True,
            immutable_revision_resolution=True,
            change_requests=True,
            pipeline_history=False,
            job_history=False,
            artifacts=False,
            branch_policies=False,
            deployments=False,
        )
    )
    limitations = capability_limitations(provider)
    assert any(item["affected_controls"] == ["pipeline_history"] for item in limitations)
    assert all(item["category"] == "provider_capability" for item in limitations)
    assert all("technical maturity is not penalized as zero" in item["confidence_effect"] for item in limitations)


def _identity(*, provider: ProviderKind, instance: str, repository: str = "service") -> RepositoryIdentity:
    return RepositoryIdentity(
        provider=provider,
        provider_instance=instance,
        organization_or_workspace="engineering",
        project="platform",
        repository=repository,
        repository_id="immutable-repository-42",
        branch="main",
        immutable_revision="a" * 40,
    )


def test_canonical_repository_key_separates_provider_instances() -> None:
    hosted = _identity(provider=ProviderKind.GITLAB, instance="https://gitlab.com")
    self_managed = _identity(provider=ProviderKind.GITLAB, instance="https://gitlab.example.com")
    assert hosted.canonical_repository_key != self_managed.canonical_repository_key
    assert hosted.resolved_provider_deployment.value == "hosted"
    assert self_managed.resolved_provider_deployment.value == "self_managed"


def test_repository_rename_does_not_change_immutable_lineage_key() -> None:
    before = _identity(provider=ProviderKind.GITHUB, instance="https://github.com", repository="old-name")
    after = _identity(provider=ProviderKind.GITHUB, instance="github.com/", repository="new-name")
    assert before.canonical_repository_key == after.canonical_repository_key


def test_provider_instance_identity_rejects_embedded_credentials() -> None:
    identity = _identity(provider=ProviderKind.GITLAB, instance="https://token@gitlab.example.com")
    with pytest.raises(ProviderContractViolation, match="must not contain credentials"):
        identity.validate()
