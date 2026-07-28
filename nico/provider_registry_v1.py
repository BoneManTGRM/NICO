from __future__ import annotations

from typing import Any, Callable, Mapping

from nico.provider_adapters_v1 import AzureDevOpsAdapter, BitbucketCloudAdapter, GiteaAdapter, ForgejoAdapter, GitHubAdapter, GitLabAdapter
from nico.provider_platform_contract_v1 import ProviderContractViolation, ProviderKind, SourceControlProvider, validate_provider

AdapterFactory = Callable[[Mapping[str, Any]], SourceControlProvider]


_FACTORIES: dict[ProviderKind, type] = {
    ProviderKind.GITHUB: GitHubAdapter,
    ProviderKind.GITLAB: GitLabAdapter,
    ProviderKind.BITBUCKET_CLOUD: BitbucketCloudAdapter,
    ProviderKind.AZURE_DEVOPS: AzureDevOpsAdapter,
    ProviderKind.GITEA: GiteaAdapter,
    ProviderKind.FORGEJO: ForgejoAdapter,
}


def supported_providers() -> tuple[str, ...]:
    return tuple(kind.value for kind in _FACTORIES)


def build_provider(kind: str | ProviderKind, config: Mapping[str, Any]) -> SourceControlProvider:
    try:
        provider_kind = kind if isinstance(kind, ProviderKind) else ProviderKind(str(kind))
    except ValueError as exc:
        raise ProviderContractViolation(f"Unsupported provider: {kind}") from exc
    factory = _FACTORIES.get(provider_kind)
    if factory is None:
        raise ProviderContractViolation(f"No production adapter registered for {provider_kind.value}")
    adapter = factory(config)
    validate_provider(adapter)
    return adapter


def provider_evidence_snapshot(adapter: SourceControlProvider) -> dict[str, Any]:
    identity = validate_provider(adapter)
    return {
        "provider": identity.provider.value,
        "provider_instance": identity.provider_instance,
        "organization_or_workspace": identity.organization_or_workspace,
        "project": identity.project,
        "repository": identity.repository,
        "repository_id": identity.repository_id,
        "branch": identity.branch,
        "immutable_revision": identity.immutable_revision,
        "revision_algorithm": identity.revision_algorithm,
        "provider_evidence_artifact": identity.provider_evidence_artifact,
        "provider_evidence_sha256": identity.provider_evidence_sha256,
        "capabilities": adapter.capabilities.as_dict(),
    }


__all__ = ["build_provider", "provider_evidence_snapshot", "supported_providers"]
