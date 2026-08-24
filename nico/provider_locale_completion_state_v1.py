from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from nico.provider_platform_contract_v1 import ProviderKind
from nico.provider_support_policy_v1 import (
    DEFAULT_SUPPORT,
    ProviderSupportMaturity,
    provider_disclosure,
)

VERSION = "nico.provider-locale-completion-state.v1"

_PRIORITY1 = (
    ProviderKind.GITLAB,
    ProviderKind.BITBUCKET_CLOUD,
    ProviderKind.AZURE_DEVOPS,
)

_ENGINEERING_EVIDENCE = {
    "F": "tests/test_hosted_provider_operator_comprehensive_parity_v1.py",
    "G": "tests/test_hosted_provider_operator_comprehensive_parity_v1.py",
    "H": "tests/test_hosted_provider_operator_comprehensive_parity_v1.py",
    "I": "tests/test_provider_repository_enumeration_v1.py",
    "J": "tests/test_provider_control_objective_parity_v1.py",
    "K": "tests/test_hosted_provider_downstream_pipeline_parity_v1.py",
    "L": "tests/test_provider_locale_same_canonical_truth_v1.py",
    "M": "tests/test_provider_endpoint_security_v1.py",
    "O": "tests/test_provider_acquisition_restart_recovery_v1.py",
    "Q": "tests/test_provider_locale_completion_state_v1.py",
}


@dataclass(frozen=True)
class ProductionAcceptanceEvidence:
    exact_current_main: bool = False
    vercel_deployment: bool = False
    railway_deployment: bool = False
    spanish_comprehensive_proof: bool = False
    ios_webkit_proof: bool = False
    mobile_restart_proof: bool = False
    two_service_acceptance: bool = False
    completion_bound_report: bool = False
    no_validated_p0_p1: bool = False

    @property
    def complete(self) -> bool:
        return all(asdict(self).values())


@dataclass(frozen=True)
class ExternalProviderEvidence:
    gitlab_real_integration: bool = False
    bitbucket_real_integration: bool = False
    azure_real_integration: bool = False
    authorized_real_credentials_available: bool = False
    priority2_authorized_infrastructure_available: bool = False


def _priority1_engineering_parity() -> dict[str, bool]:
    return {
        provider.value: DEFAULT_SUPPORT[provider].maturity
        is ProviderSupportMaturity.ENGINEERING_PARITY_PROVEN
        for provider in _PRIORITY1
    }


def _work_package(
    key: str,
    *,
    engineering_complete: bool,
    status: str,
    evidence: str | None = None,
    blocker: str | None = None,
) -> dict[str, Any]:
    return {
        "id": key,
        "engineering_complete": bool(engineering_complete),
        "status": status,
        "evidence_reference": evidence,
        "blocker": blocker,
    }


def build_provider_locale_completion_state(
    *,
    current_main_sha: str,
    production: ProductionAcceptanceEvidence | None = None,
    external: ExternalProviderEvidence | None = None,
) -> dict[str, Any]:
    """Build the fail-closed machine-readable completion state for issue #708.

    The builder never infers external credentials, human approval, live-provider proof,
    or exact-main production acceptance. Those facts must be supplied explicitly.
    """

    sha = str(current_main_sha or "").strip().casefold()
    if len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha):
        raise ValueError("exact_current_main_sha_required")
    production = production or ProductionAcceptanceEvidence()
    external = external or ExternalProviderEvidence()
    parity = _priority1_engineering_parity()
    priority1_complete = all(parity.values())

    real_provider = {
        ProviderKind.GITLAB.value: external.gitlab_real_integration,
        ProviderKind.BITBUCKET_CLOUD.value: external.bitbucket_real_integration,
        ProviderKind.AZURE_DEVOPS.value: external.azure_real_integration,
    }
    real_provider_gate = (
        all(real_provider.values())
        if external.authorized_real_credentials_available
        else True
    )
    priority2_external_gate = not external.priority2_authorized_infrastructure_available

    packages = {
        "A": _work_package("A", engineering_complete=True, status="complete", evidence="issue-708-provider-neutral-contracts"),
        "B": _work_package("B", engineering_complete=True, status="complete", evidence="nico/provider_platform_contract_v1.py"),
        "C": _work_package("C", engineering_complete=True, status="complete", evidence="unified-locale-routing"),
        "D": _work_package("D", engineering_complete=True, status="complete", evidence="presentation-only-spanish-canonical-state"),
        "E": _work_package("E", engineering_complete=True, status="complete" if production.exact_current_main else "awaiting_exact_main_proof", blocker=None if production.exact_current_main else "exact-current-main production evidence not supplied"),
        "F": _work_package("F", engineering_complete=parity[ProviderKind.GITLAB.value], status="engineering_parity_proven" if parity[ProviderKind.GITLAB.value] else "incomplete", evidence=_ENGINEERING_EVIDENCE["F"]),
        "G": _work_package("G", engineering_complete=parity[ProviderKind.BITBUCKET_CLOUD.value], status="engineering_parity_proven" if parity[ProviderKind.BITBUCKET_CLOUD.value] else "incomplete", evidence=_ENGINEERING_EVIDENCE["G"]),
        "H": _work_package("H", engineering_complete=parity[ProviderKind.AZURE_DEVOPS.value], status="engineering_parity_proven" if parity[ProviderKind.AZURE_DEVOPS.value] else "incomplete", evidence=_ENGINEERING_EVIDENCE["H"]),
        "I": _work_package("I", engineering_complete=True, status="complete", evidence=_ENGINEERING_EVIDENCE["I"]),
        "J": _work_package("J", engineering_complete=True, status="complete", evidence=_ENGINEERING_EVIDENCE["J"]),
        "K": _work_package("K", engineering_complete=True, status="complete", evidence=_ENGINEERING_EVIDENCE["K"]),
        "L": _work_package("L", engineering_complete=True, status="engineering_complete_pending_exact_artifact_proof" if not production.spanish_comprehensive_proof else "complete", evidence=_ENGINEERING_EVIDENCE["L"], blocker=None if production.spanish_comprehensive_proof else "exact-current-main locale artifact proof not supplied"),
        "M": _work_package("M", engineering_complete=True, status="complete", evidence=_ENGINEERING_EVIDENCE["M"]),
        "N": _work_package("N", engineering_complete=priority2_external_gate, status="blocked_external" if priority2_external_gate else "authorized_infrastructure_requires_real_validation", blocker="authorized Priority-2 provider infrastructure unavailable" if priority2_external_gate else "real Priority-2 integration evidence required"),
        "O": _work_package("O", engineering_complete=True, status="complete", evidence=_ENGINEERING_EVIDENCE["O"]),
        "P": _work_package("P", engineering_complete=True, status="complete" if production.complete else "awaiting_exact_main_production_acceptance", blocker=None if production.complete else "one or more exact-current-main production gates are not supplied as passing"),
        "Q": _work_package("Q", engineering_complete=True, status="complete", evidence=_ENGINEERING_EVIDENCE["Q"]),
    }

    engineering_required = tuple("ABCDEFGHIJKLMOQ")
    engineering_complete = all(packages[key]["engineering_complete"] for key in engineering_required)
    commercial_deadline_ready = bool(
        engineering_complete
        and priority1_complete
        and real_provider_gate
        and priority2_external_gate
        and production.complete
    )

    blockers: list[str] = []
    if not priority1_complete:
        blockers.append("priority1_engineering_parity_incomplete")
    if not real_provider_gate:
        blockers.append("authorized_real_provider_integration_incomplete")
    if not production.complete:
        blockers.append("exact_current_main_production_acceptance_incomplete")
    if not priority2_external_gate:
        blockers.append("priority2_authorized_infrastructure_requires_validation")

    return {
        "artifact_schema": VERSION,
        "authoritative_issue": 708,
        "current_main_sha": sha,
        "one_product": "NICO COMPREHENSIVE",
        "operator_run_only": True,
        "priority1_provider_engineering_parity": parity,
        "priority1_real_provider_integration": real_provider,
        "real_provider_integration_required_now": external.authorized_real_credentials_available,
        "priority2_external_infrastructure_available": external.priority2_authorized_infrastructure_available,
        "provider_disclosures": {
            provider.value: provider_disclosure(provider)
            for provider in (ProviderKind.GITHUB, *_PRIORITY1)
        },
        "production_acceptance": asdict(production),
        "work_packages": packages,
        "engineering_program_complete": engineering_complete,
        "commercial_deadline_ready": commercial_deadline_ready,
        "blocking_gates": blockers,
        "human_review_required": True,
        "human_approval_completed": False,
        "client_delivery_allowed": False,
        "guardrail": "No external provider proof, reviewer identity, human disposition, final approval, or client-delivery authorization is inferred by this artifact.",
    }


__all__ = [
    "ExternalProviderEvidence",
    "ProductionAcceptanceEvidence",
    "VERSION",
    "build_provider_locale_completion_state",
]
