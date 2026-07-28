from __future__ import annotations

import pytest

from nico.provider_platform_contract_v1 import ProviderContractViolation, ProviderKind
from nico.provider_support_policy_v1 import (
    DEFAULT_SUPPORT,
    ProviderSupport,
    SupportLevel,
    provider_disclosure,
    require_client_claim,
)


def test_fixture_only_and_authenticated_beta_cannot_be_claimed_as_production() -> None:
    for provider in ProviderKind:
        with pytest.raises(ProviderContractViolation):
            require_client_claim(provider)


def test_production_claim_requires_authenticated_conformance_reference() -> None:
    provider = ProviderKind.GITHUB
    registry = {
        provider: ProviderSupport(provider, SupportLevel.PRODUCTION_VALIDATED)
    }
    with pytest.raises(ProviderContractViolation):
        require_client_claim(provider, registry)

    registry[provider] = ProviderSupport(
        provider,
        SupportLevel.PRODUCTION_VALIDATED,
        authenticated_conformance_run="gha://run/123",
        immutable_revision_fixture="abc123",
    )
    support = require_client_claim(provider, registry)
    assert support.client_claim_allowed is True


def test_disclosure_is_explicit_and_never_upgrades_fixture_evidence() -> None:
    disclosure = provider_disclosure(ProviderKind.GITLAB)
    assert disclosure["support_level"] == "fixture_only"
    assert disclosure["client_claim_allowed"] is False
    assert disclosure["authenticated_conformance_run"] is None
    assert disclosure["limitations"]


def test_default_registry_covers_every_provider_kind() -> None:
    assert set(DEFAULT_SUPPORT) == set(ProviderKind)
