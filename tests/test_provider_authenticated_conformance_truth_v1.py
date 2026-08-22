from __future__ import annotations

import pytest

from nico.provider_authenticated_conformance_v1 import (
    ConformanceProofScope,
    conformance_support_record,
    run_authenticated_conformance,
)
from nico.provider_platform_contract_v1 import ProviderContractViolation, ProviderKind, RepositoryIdentity


class FakeClient:
    def resolve_repository_identity(self) -> RepositoryIdentity:
        return RepositoryIdentity(
            provider=ProviderKind.GITLAB,
            provider_instance="https://gitlab.com",
            organization_or_workspace="engineering",
            project="platform",
            repository="service",
            repository_id="project-42",
            branch="main",
            immutable_revision="a" * 40,
        )

    def fetch_pipeline_evidence(self, immutable_revision: str):
        return ({"pipeline_id": "9", "commit_sha": immutable_revision},)

    def fetch_branch_policy_evidence(self):
        return {"protected": True}


def test_authenticated_engineering_conformance_cannot_claim_production() -> None:
    result = run_authenticated_conformance(
        FakeClient(),
        provider=ProviderKind.GITLAB,
        evidence_reference="artifact://engineering/9",
    )
    record = conformance_support_record(result)
    assert record["support_level"] == "authenticated_beta"
    assert record["maturity"] == "ENGINEERING_PARITY_PROVEN"
    assert record["engineering_parity_evidence_reference"] == "artifact://engineering/9"
    assert record["real_provider_integration_evidence_reference"] is None
    assert record["controlled_pilot_evidence_reference"] is None
    assert record["production_client_evidence_reference"] is None
    assert record["client_claim_allowed"] is False
    assert record["canonical_repository_key"].startswith("nico-repository-v2:")


def test_real_provider_scope_requires_retained_authorization() -> None:
    with pytest.raises(ProviderContractViolation, match="authorization reference"):
        run_authenticated_conformance(
            FakeClient(),
            provider=ProviderKind.GITLAB,
            evidence_reference="artifact://provider/9",
            proof_scope=ConformanceProofScope.REAL_PROVIDER_INTEGRATION,
        )

    result = run_authenticated_conformance(
        FakeClient(),
        provider=ProviderKind.GITLAB,
        evidence_reference="artifact://provider/9",
        proof_scope=ConformanceProofScope.REAL_PROVIDER_INTEGRATION,
        authorization_reference="authorization://test-tenant/7",
    )
    record = conformance_support_record(result)
    assert record["maturity"] == "REAL_PROVIDER_INTEGRATION_PROVEN"
    assert record["engineering_parity_evidence_reference"] is None
    assert record["real_provider_integration_evidence_reference"] == "artifact://provider/9"
    assert record["authorization_reference"] == "authorization://test-tenant/7"
    assert record["client_claim_allowed"] is False


def test_pipeline_evidence_for_another_commit_fails_closed() -> None:
    client = FakeClient()
    client.fetch_pipeline_evidence = lambda immutable_revision: ({"commit_sha": "b" * 40},)
    with pytest.raises(ProviderContractViolation, match="not bound"):
        run_authenticated_conformance(
            client,
            provider=ProviderKind.GITLAB,
            evidence_reference="artifact://engineering/10",
        )
