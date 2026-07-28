from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from nico.provider_platform_contract_v1 import ProviderContractViolation, ProviderKind, RepositoryIdentity

VERSION = "nico.provider_authenticated_conformance.v1"


class AuthenticatedProviderClient(Protocol):
    def resolve_repository_identity(self) -> RepositoryIdentity: ...
    def fetch_pipeline_evidence(self, immutable_revision: str) -> Sequence[Mapping]: ...
    def fetch_branch_policy_evidence(self) -> Mapping: ...


@dataclass(frozen=True)
class ConformanceResult:
    provider: ProviderKind
    immutable_revision: str
    repository_id: str
    pipeline_evidence_count: int
    branch_policy_observed: bool
    authenticated: bool
    evidence_reference: str


def run_authenticated_conformance(
    client: AuthenticatedProviderClient,
    *,
    provider: ProviderKind,
    evidence_reference: str,
) -> ConformanceResult:
    if not evidence_reference.strip():
        raise ProviderContractViolation("Authenticated conformance requires a retained evidence reference")

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
    )


def conformance_support_record(result: ConformanceResult) -> dict:
    return {
        "version": VERSION,
        "provider": result.provider.value,
        "support_level": "production_validated",
        "authenticated_conformance_run": result.evidence_reference,
        "immutable_revision": result.immutable_revision,
        "repository_id": result.repository_id,
        "pipeline_evidence_count": result.pipeline_evidence_count,
        "branch_policy_observed": result.branch_policy_observed,
        "client_claim_allowed": True,
    }


__all__ = [
    "AuthenticatedProviderClient",
    "ConformanceResult",
    "conformance_support_record",
    "run_authenticated_conformance",
]
