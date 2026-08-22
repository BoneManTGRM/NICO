from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from nico.provider_platform_contract_v1 import ProviderContractViolation, ProviderKind

VERSION = "nico.provider_support_policy.v1"


class SupportLevel(str, Enum):
    # Retained as a compatibility presentation level.
    PRODUCTION_VALIDATED = "production_validated"
    AUTHENTICATED_BETA = "authenticated_beta"
    FIXTURE_ONLY = "fixture_only"
    UNSUPPORTED = "unsupported"


class ProviderSupportMaturity(str, Enum):
    IMPLEMENTED = "IMPLEMENTED"
    ENGINEERING_PARITY_PROVEN = "ENGINEERING_PARITY_PROVEN"
    REAL_PROVIDER_INTEGRATION_PROVEN = "REAL_PROVIDER_INTEGRATION_PROVEN"
    CONTROLLED_PILOT_PROVEN = "CONTROLLED_PILOT_PROVEN"
    PRODUCTION_CLIENT_PROVEN = "PRODUCTION_CLIENT_PROVEN"
    IMPLEMENTED_BUT_UNPROVEN = "IMPLEMENTED_BUT_UNPROVEN"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class ProviderSupport:
    provider: ProviderKind
    level: SupportLevel
    # Existing positional field order is preserved for compatibility.
    authenticated_conformance_run: str = ""
    immutable_revision_fixture: str = ""
    limitations: tuple[str, ...] = ()
    maturity: ProviderSupportMaturity = ProviderSupportMaturity.IMPLEMENTED_BUT_UNPROVEN
    engineering_parity_evidence_reference: str = ""
    real_provider_integration_evidence_reference: str = ""
    controlled_pilot_evidence_reference: str = ""
    production_client_evidence_reference: str = ""

    @property
    def client_claim_allowed(self) -> bool:
        return (
            self.level is SupportLevel.PRODUCTION_VALIDATED
            and self.maturity is ProviderSupportMaturity.PRODUCTION_CLIENT_PROVEN
            and bool(self.authenticated_conformance_run)
            and bool(self.real_provider_integration_evidence_reference)
            and bool(self.controlled_pilot_evidence_reference)
            and bool(self.production_client_evidence_reference)
        )


def validate_support_evidence(support: ProviderSupport) -> None:
    maturity = support.maturity
    if maturity is ProviderSupportMaturity.UNSUPPORTED:
        if support.level is not SupportLevel.UNSUPPORTED:
            raise ProviderContractViolation("Unsupported maturity must use unsupported presentation level")
        return
    if maturity is ProviderSupportMaturity.ENGINEERING_PARITY_PROVEN:
        if not support.engineering_parity_evidence_reference:
            raise ProviderContractViolation("Engineering parity requires retained engineering evidence")
    elif maturity is ProviderSupportMaturity.REAL_PROVIDER_INTEGRATION_PROVEN:
        if not support.authenticated_conformance_run or not support.real_provider_integration_evidence_reference:
            raise ProviderContractViolation("Real-provider integration requires authenticated retained evidence")
    elif maturity is ProviderSupportMaturity.CONTROLLED_PILOT_PROVEN:
        if (
            not support.authenticated_conformance_run
            or not support.real_provider_integration_evidence_reference
            or not support.controlled_pilot_evidence_reference
        ):
            raise ProviderContractViolation(
                "Controlled-pilot maturity requires authenticated provider and retained pilot evidence"
            )
    elif maturity is ProviderSupportMaturity.PRODUCTION_CLIENT_PROVEN:
        if (
            not support.authenticated_conformance_run
            or not support.real_provider_integration_evidence_reference
            or not support.controlled_pilot_evidence_reference
            or not support.production_client_evidence_reference
        ):
            raise ProviderContractViolation(
                "Production-client maturity requires authenticated integration, controlled-pilot, "
                "and exact retained production evidence"
            )
    if support.level is SupportLevel.PRODUCTION_VALIDATED and maturity is not ProviderSupportMaturity.PRODUCTION_CLIENT_PROVEN:
        raise ProviderContractViolation("Production-validated presentation requires production-client-proven maturity")


# Every declared provider must have an explicit support state. New enum members
# therefore fail safe as unsupported rather than disappearing from disclosures.
_DEFAULT_UNSUPPORTED = {
    provider: ProviderSupport(
        provider=provider,
        level=SupportLevel.UNSUPPORTED,
        limitations=("No production-validated adapter or authenticated conformance evidence retained.",),
        maturity=ProviderSupportMaturity.UNSUPPORTED,
    )
    for provider in ProviderKind
}

DEFAULT_SUPPORT: Mapping[ProviderKind, ProviderSupport] = {
    **_DEFAULT_UNSUPPORTED,
    ProviderKind.GITHUB: ProviderSupport(
        provider=ProviderKind.GITHUB,
        level=SupportLevel.AUTHENTICATED_BETA,
        limitations=(
            "GitHub is the commercial v1 boundary, but exact external-pilot and "
            "production-client evidence is not retained in this support registry.",
        ),
        maturity=ProviderSupportMaturity.IMPLEMENTED_BUT_UNPROVEN,
    ),
    ProviderKind.GITLAB: ProviderSupport(
        ProviderKind.GITLAB,
        SupportLevel.FIXTURE_ONLY,
        limitations=("No authenticated conformance evidence retained.",),
        maturity=ProviderSupportMaturity.IMPLEMENTED_BUT_UNPROVEN,
    ),
    ProviderKind.BITBUCKET_CLOUD: ProviderSupport(
        ProviderKind.BITBUCKET_CLOUD,
        SupportLevel.FIXTURE_ONLY,
        limitations=("No authenticated conformance evidence retained.",),
        maturity=ProviderSupportMaturity.IMPLEMENTED_BUT_UNPROVEN,
    ),
    ProviderKind.AZURE_DEVOPS: ProviderSupport(
        ProviderKind.AZURE_DEVOPS,
        SupportLevel.FIXTURE_ONLY,
        limitations=("No authenticated conformance evidence retained.",),
        maturity=ProviderSupportMaturity.IMPLEMENTED_BUT_UNPROVEN,
    ),
    ProviderKind.GITEA: ProviderSupport(
        ProviderKind.GITEA,
        SupportLevel.FIXTURE_ONLY,
        limitations=("No authenticated conformance evidence retained.",),
        maturity=ProviderSupportMaturity.IMPLEMENTED_BUT_UNPROVEN,
    ),
    ProviderKind.FORGEJO: ProviderSupport(
        ProviderKind.FORGEJO,
        SupportLevel.FIXTURE_ONLY,
        limitations=("No authenticated conformance evidence retained.",),
        maturity=ProviderSupportMaturity.IMPLEMENTED_BUT_UNPROVEN,
    ),
}


def require_client_claim(
    provider: ProviderKind,
    registry: Mapping[ProviderKind, ProviderSupport] = DEFAULT_SUPPORT,
) -> ProviderSupport:
    support = registry.get(provider)
    if support is None:
        raise ProviderContractViolation(
            f"{provider.value} cannot be presented as production-supported; support_level=unsupported"
        )
    validate_support_evidence(support)
    if not support.client_claim_allowed:
        raise ProviderContractViolation(
            f"{provider.value} cannot be presented as production-supported; "
            f"support_level={support.level.value}; maturity={support.maturity.value}"
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
        maturity=ProviderSupportMaturity.UNSUPPORTED,
    )
    validate_support_evidence(support)
    return {
        "version": VERSION,
        "provider": provider.value,
        "support_level": support.level.value,
        "maturity": support.maturity.value,
        "client_claim_allowed": support.client_claim_allowed,
        "authenticated_conformance_run": support.authenticated_conformance_run or None,
        "engineering_parity_evidence_reference": support.engineering_parity_evidence_reference or None,
        "real_provider_integration_evidence_reference": support.real_provider_integration_evidence_reference or None,
        "controlled_pilot_evidence_reference": support.controlled_pilot_evidence_reference or None,
        "production_client_evidence_reference": support.production_client_evidence_reference or None,
        "limitations": list(support.limitations),
    }


__all__ = [
    "DEFAULT_SUPPORT",
    "ProviderSupport",
    "ProviderSupportMaturity",
    "SupportLevel",
    "provider_disclosure",
    "require_client_claim",
    "validate_support_evidence",
]
