from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Protocol, Sequence

from nico.provider_platform_contract_v1 import ProviderContractViolation, ProviderKind, RepositoryIdentity
from nico.provider_support_policy_v1 import ProviderSupportMaturity, SupportLevel

VERSION = "nico.provider_authenticated_conformance.v1"


class AuthenticatedProviderClient(Protocol):
    def resolve_repository_identity(self) -> RepositoryIdentity: ...
    def fetch_pipeline_evidence(self, immutable_revision: str) -> Sequence[Mapping]: ...
    def fetch_branch_policy_evidence(self) -> Mapping: ...


class ConformanceProofScope(str, Enum):
    ENGINEERING = "engineering"
    REAL_PROVIDER_INTEGRATION = "real_provider_integration"


@dataclass(frozen=True)
class ConformanceResult:
    provider: ProviderKind
    immutable_revision: str
    repository_id: str
    pipeline_evidence_count: int
    branch_policy_observed: bool
    authenticated: bool
    evidence_reference: str
    proof_scope: ConformanceProofScope = ConformanceProofScope.ENGINEERING
    authorization_reference: str = ""
    canonical_repository_key: str = ""


def run_authenticated_conformance(
    client: AuthenticatedProviderClient,
    *,
    provider: ProviderKind,
    evidence_reference: str,
    proof_scope: ConformanceProofScope = ConformanceProofScope.ENGINEERING,
    authorization_reference: str = "",
) -> ConformanceResult:
    if not evidence_reference.strip():
        raise ProviderContractViolation("Authenticated conformance requires a retained evidence reference")
    if proof_scope is ConformanceProofScope.REAL_PROVIDER_INTEGRATION and not authorization_reference.strip():
        raise ProviderContractViolation(
            "Real-provider integration proof requires a retained authorization reference"
        )

    identity = client.resolve_repository_identity()
    identity.validate()
    if identity.provider is not provider:
        raise ProviderContractViolation(
            f"Provider mismatch: expected={provider.value}; actual={identity.provider.value}"
        )

    pipelines = list(client.fetch_pipeline_evidence(identity.immutable_revision))
    for item in pipelines:
        revision = str(item.get("commit_sha") or item.get("immutable_revision") or "")
        if revision != identity.immutable_revision:
            raise ProviderContractViolation("Pipeline evidence is not bound to the assessed immutable revision")

    branch_policy = dict(client.fetch_branch_policy_evidence() or {})
    if not pipelines:
        raise ProviderContractViolation("No authenticated exact-revision pipeline evidence was returned")

    return ConformanceResult(
        provider=provider,
        immutable_revision=identity.immutable_revision,
        repository_id=identity.repository_id,
        pipeline_evidence_count=len(pipelines),
        branch_policy_observed=bool(branch_policy),
        authenticated=True,
        evidence_reference=evidence_reference,
        proof_scope=proof_scope,
        authorization_reference=authorization_reference,
        canonical_repository_key=identity.canonical_repository_key,
    )


def conformance_support_record(result: ConformanceResult) -> dict:
    maturity = (
        ProviderSupportMaturity.REAL_PROVIDER_INTEGRATION_PROVEN
        if result.proof_scope is ConformanceProofScope.REAL_PROVIDER_INTEGRATION
        else ProviderSupportMaturity.ENGINEERING_PARITY_PROVEN
    )
    return {
        "version": VERSION,
        "provider": result.provider.value,
        "support_level": SupportLevel.AUTHENTICATED_BETA.value,
        "maturity": maturity.value,
        "authenticated_conformance_run": result.evidence_reference,
        "engineering_parity_evidence_reference": (
            result.evidence_reference
            if maturity is ProviderSupportMaturity.ENGINEERING_PARITY_PROVEN
            else None
        ),
        "real_provider_integration_evidence_reference": (
            result.evidence_reference
            if maturity is ProviderSupportMaturity.REAL_PROVIDER_INTEGRATION_PROVEN
            else None
        ),
        "controlled_pilot_evidence_reference": None,
        "production_client_evidence_reference": None,
        "authorization_reference": result.authorization_reference or None,
        "immutable_revision": result.immutable_revision,
        "repository_id": result.repository_id,
        "canonical_repository_key": result.canonical_repository_key,
        "pipeline_evidence_count": result.pipeline_evidence_count,
        "branch_policy_observed": result.branch_policy_observed,
        # Authenticated engineering or provider-integration evidence is not a
        # real controlled pilot, production client, or exact-artifact approval.
        "client_claim_allowed": False,
    }


__all__ = [
    "AuthenticatedProviderClient",
    "ConformanceProofScope",
    "ConformanceResult",
    "conformance_support_record",
    "run_authenticated_conformance",
]
