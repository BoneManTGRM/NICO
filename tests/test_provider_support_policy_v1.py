from __future__ import annotations

import pytest

from nico.provider_platform_contract_v1 import ProviderContractViolation, ProviderKind
from nico.provider_support_policy_v1 import (
    DEFAULT_SUPPORT,
    ProviderSupport,
    ProviderSupportMaturity,
    SupportLevel,
    provider_disclosure,
    require_client_claim,
)


def test_fixture_only_and_authenticated_beta_cannot_be_claimed_as_production() -> None:
    for provider in ProviderKind:
        with pytest.raises(ProviderContractViolation):
            require_client_claim(provider)


def test_authenticated_conformance_alone_cannot_authorize_production_claim() -> None:
    provider = ProviderKind.GITHUB
    registry = {
        provider: ProviderSupport(
            provider,
            SupportLevel.AUTHENTICATED_BETA,
            authenticated_conformance_run="gha://run/123",
            maturity=ProviderSupportMaturity.REAL_PROVIDER_INTEGRATION_PROVEN,
            real_provider_integration_evidence_reference="artifact://provider-proof/123",
        )
    }
    with pytest.raises(ProviderContractViolation, match="cannot be presented"):
        require_client_claim(provider, registry)


def test_production_client_maturity_requires_cumulative_pilot_evidence() -> None:
    provider = ProviderKind.GITHUB
    registry = {
        provider: ProviderSupport(
            provider,
            SupportLevel.PRODUCTION_VALIDATED,
            authenticated_conformance_run="gha://run/123",
            maturity=ProviderSupportMaturity.PRODUCTION_CLIENT_PROVEN,
            real_provider_integration_evidence_reference="artifact://provider-proof/123",
            production_client_evidence_reference="delivery://receipt/456",
        )
    }
    with pytest.raises(ProviderContractViolation, match="controlled-pilot"):
        require_client_claim(provider, registry)


def test_production_claim_requires_exact_production_client_evidence() -> None:
    provider = ProviderKind.GITHUB
    registry = {
        provider: ProviderSupport(
            provider,
            SupportLevel.PRODUCTION_VALIDATED,
            authenticated_conformance_run="gha://run/123",
            maturity=ProviderSupportMaturity.PRODUCTION_CLIENT_PROVEN,
        )
    }
    with pytest.raises(ProviderContractViolation, match="exact retained production evidence"):
        require_client_claim(provider, registry)

    registry[provider] = ProviderSupport(
        provider,
        SupportLevel.PRODUCTION_VALIDATED,
        authenticated_conformance_run="gha://run/123",
        immutable_revision_fixture="abc123",
        maturity=ProviderSupportMaturity.PRODUCTION_CLIENT_PROVEN,
        real_provider_integration_evidence_reference="artifact://provider-proof/123",
        controlled_pilot_evidence_reference="pilot://acceptance/321",
        production_client_evidence_reference="delivery://receipt/456",
    )
    support = require_client_claim(provider, registry)
    assert support.client_claim_allowed is True


@pytest.mark.parametrize(
    "provider",
    (
        ProviderKind.GITLAB,
        ProviderKind.BITBUCKET_CLOUD,
        ProviderKind.AZURE_DEVOPS,
    ),
)
def test_hosted_engineering_parity_is_explicit_without_upgrading_client_claim(
    provider: ProviderKind,
) -> None:
    disclosure = provider_disclosure(provider)
    assert disclosure["support_level"] == "fixture_only"
    assert disclosure["maturity"] == "ENGINEERING_PARITY_PROVEN"
    assert disclosure["client_claim_allowed"] is False
    assert disclosure["authenticated_conformance_run"] is None
    assert disclosure["engineering_parity_evidence_reference"]
    assert disclosure["real_provider_integration_evidence_reference"] is None
    assert disclosure["controlled_pilot_evidence_reference"] is None
    assert disclosure["production_client_evidence_reference"] is None
    assert disclosure["limitations"]


def test_default_registry_covers_every_provider_kind() -> None:
    assert set(DEFAULT_SUPPORT) == set(ProviderKind)