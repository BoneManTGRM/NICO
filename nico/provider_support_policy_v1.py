from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from nico.provider_platform_contract_v1 import ProviderContractViolation, ProviderKind

VERSION = "nico.provider_support_policy.v1"


class SupportLevel(str, Enum):
    PRODUCTION_VALIDATED = "production_validated"
    AUTHENTICATED_BETA = "authenticated_beta"
    FIXTURE_ONLY = "fixture_only"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ProviderSupport:
    provider: ProviderKind
    level: SupportLevel
    authenticated_conformance_run: str = ""
    immutable_revision_fixture: str = ""
    limitations: tuple[str, ...] = ()

    @property
    def client_claim_allowed(self) -> bool:
        return self.level is SupportLevel.PRODUCTION_VALIDATED and bool(self.authenticated_conformance_run)


# Every declared provider must have an explicit support state. New enum members
# therefore fail safe as unsupported rather than disappearing from disclosures.
_DEFAULT_UNSUPPORTED = {
    provider: ProviderSupport(
        provider=provider,
        level=SupportLevel.UNSUPPORTED,
        limitations=("No production-validated adapter or authenticated conformance evidence retained.",),
    )
    for provider in ProviderKind
}

DEFAULT_SUPPORT: Mapping[ProviderKind, ProviderSupport] = {
    **_DEFAULT_UNSUPPORTED,
    ProviderKind.GITHUB: ProviderSupport(
        provider=ProviderKind.GITHUB,
        level=SupportLevel.AUTHENTICATED_BETA,
        limitations=("Production conformance must be rerun after Phase 7 integration.",),
    ),
    ProviderKind.GITLAB: ProviderSupport(
        ProviderKind.GITLAB,
        SupportLevel.FIXTURE_ONLY,
        limitations=("No authenticated conformance evidence retained.",),
    ),
    ProviderKind.BITBUCKET_CLOUD: ProviderSupport(
        ProviderKind.BITBUCKET_CLOUD,
        SupportLevel.FIXTURE_ONLY,
        limitations=("No authenticated conformance evidence retained.",),
    ),
    ProviderKind.AZURE_DEVOPS: ProviderSupport(
        ProviderKind.AZURE_DEVOPS,
        SupportLevel.FIXTURE_ONLY,
        limitations=("No authenticated conformance evidence retained.",),
    ),
    ProviderKind.GITEA: ProviderSupport(
        ProviderKind.GITEA,
        SupportLevel.FIXTURE_ONLY,
        limitations=("No authenticated conformance evidence retained.",),
    ),
    ProviderKind.FORGEJO: ProviderSupport(
        ProviderKind.FORGEJO,
        SupportLevel.FIXTURE_ONLY,
        limitations=("No authenticated conformance evidence retained.",),
    ),
}


def require_client_claim(
    provider: ProviderKind,
    registry: Mapping[ProviderKind, ProviderSupport] = DEFAULT_SUPPORT,
) -> ProviderSupport:
    support = registry.get(provider)
    if support is None or not support.client_claim_allowed:
        level = support.level.value if support else SupportLevel.UNSUPPORTED.value
        raise ProviderContractViolation(
            f"{provider.value} cannot be presented as production-supported; support_level={level}"
        )
    return support


def provider_disclosure(
    provider: ProviderKind,
    registry: Mapping[ProviderKind, ProviderSupport] = DEFAULT_SUPPORT,
) -> dict:
    support = registry.get(provider) or ProviderSupport(
        provider,
        SupportLevel.UNSUPPORTED,
        limitations=("No adapter registered.",),
    )
    return {
        "version": VERSION,
        "provider": provider.value,
        "support_level": support.level.value,
        "client_claim_allowed": support.client_claim_allowed,
        "authenticated_conformance_run": support.authenticated_conformance_run or None,
        "limitations": list(support.limitations),
    }


__all__ = [
    "DEFAULT_SUPPORT",
    "ProviderSupport",
    "SupportLevel",
    "provider_disclosure",
    "require_client_claim",
]
