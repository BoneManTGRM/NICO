from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from nico.provider_platform_contract_v1 import ProviderKind
from nico.provider_rollout_control_v1 import (
    ProviderRolloutConfig,
    ProviderRolloutError,
    ProviderRolloutRegistry,
    ProviderRolloutState,
    install_provider_rollout_routes,
)
from nico.provider_support_policy_v1 import (
    DEFAULT_SUPPORT,
    ProviderSupport,
    ProviderSupportMaturity,
    SupportLevel,
)


def _configs() -> dict[ProviderKind, ProviderRolloutConfig]:
    return {
        ProviderKind.GITHUB: ProviderRolloutConfig(
            ProviderKind.GITHUB,
            ProviderRolloutState.INTERNAL_TEST,
            True,
            credential_reference_id="github-server-reference",
            capability_evidence_reference="artifact://github/engineering",
            native_ci_evidence_supported=True,
        ),
        ProviderKind.GITLAB: ProviderRolloutConfig(
            ProviderKind.GITLAB,
            ProviderRolloutState.INTERNAL_TEST,
            True,
            credential_reference_id="gitlab-server-reference",
            capability_evidence_reference="artifact://gitlab/engineering",
            native_ci_evidence_supported=True,
        ),
        ProviderKind.BITBUCKET_CLOUD: ProviderRolloutConfig(
            ProviderKind.BITBUCKET_CLOUD,
            ProviderRolloutState.INTERNAL_TEST,
            True,
            credential_reference_id="bitbucket-server-reference",
            capability_evidence_reference="artifact://bitbucket/engineering",
        ),
        ProviderKind.AZURE_DEVOPS: ProviderRolloutConfig(
            ProviderKind.AZURE_DEVOPS,
            ProviderRolloutState.INTERNAL_TEST,
            True,
            credential_reference_id="azure-server-reference",
            capability_evidence_reference="artifact://azure/engineering",
            native_ci_evidence_supported=True,
        ),
    }


def _payload(provider: str = "github", *, locale: str = "en-US") -> dict[str, object]:
    return {
        "provider": provider,
        "client_id": "client-1",
        "project_id": "project-1",
        "session_id": "session-1",
        "run_id": "comprun-1",
        "locale": locale,
        "onboarding_mode": "internal_test",
    }


def _registry(
    *,
    configs: dict[ProviderKind, ProviderRolloutConfig] | None = None,
    support_registry: dict[ProviderKind, ProviderSupport] | None = None,
) -> ProviderRolloutRegistry:
    return ProviderRolloutRegistry(
        configs=configs or _configs(),
        support_registry=support_registry or DEFAULT_SUPPORT,
    )


def test_capability_truth_is_localized_without_translating_machine_fields() -> None:
    registry = _registry()

    english = registry.capability(ProviderKind.GITHUB, locale="en-US")
    spanish = registry.capability(ProviderKind.GITHUB, locale="es-MX")

    assert english["provider"] == spanish["provider"] == "github"
    assert english["rollout_state"] == spanish["rollout_state"] == "internal_test"
    assert english["support_maturity"] == spanish["support_maturity"]
    assert english["availability_state"] == spanish["availability_state"] == "preview_limited"
    assert english["availability_label"] == "Preview / limited"
    assert spanish["availability_label"] == "Vista previa / limitada"
    assert english["client_delivery_allowed"] is False
    assert spanish["client_delivery_allowed"] is False


def test_unauthorized_rollout_change_is_rejected_and_state_is_unchanged() -> None:
    registry = _registry()
    app = FastAPI()
    install_provider_rollout_routes(app, registry=registry)
    client = TestClient(app)

    response = client.post(
        "/providers/github/rollout",
        json={"rollout_state": "production", "operational_enabled": True},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == (
        "provider_rollout_admin_authentication_required"
    )
    assert registry.capability(ProviderKind.GITHUB)["rollout_state"] == "internal_test"
    assert registry.audit_events() == []


def test_authorized_operator_can_disable_one_provider_without_disabling_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-token")
    registry = _registry()
    app = FastAPI()
    install_provider_rollout_routes(app, registry=registry)
    client = TestClient(app)

    response = client.post(
        "/providers/gitlab/rollout",
        headers={"X-NICO-Admin-Token": "operator-token"},
        json={"rollout_state": "disabled", "operational_enabled": False, "actor": "ops"},
    )

    assert response.status_code == 200
    assert response.json()["availability_state"] == "not_available"
    assert registry.capability(ProviderKind.GITLAB)["operational_enabled"] is False
    assert registry.capability(ProviderKind.GITHUB)["operational_enabled"] is True
    assert registry.audit_events()[0]["evidence_mutated"] is False
    assert registry.audit_events()[0]["credential_mutated"] is False


def test_disabled_provider_connection_attempt_fails_closed() -> None:
    configs = _configs()
    configs[ProviderKind.GITLAB] = ProviderRolloutConfig(
        ProviderKind.GITLAB,
        ProviderRolloutState.DISABLED,
        False,
        credential_reference_id="gitlab-server-reference",
        capability_evidence_reference="artifact://gitlab/engineering",
    )
    registry = _registry(configs=configs)

    with pytest.raises(ProviderRolloutError, match="provider_operationally_disabled"):
        registry.preflight(_payload("gitlab"), operator_authorized=True)


def test_client_side_authority_tampering_is_rejected() -> None:
    registry = _registry()
    payload = _payload()
    payload.update(
        {
            "rollout_state": "production",
            "support_maturity": "PRODUCTION_CLIENT_PROVEN",
            "client_onboarding_allowed": True,
        }
    )

    with pytest.raises(
        ProviderRolloutError,
        match="provider_authority_state_is_server_controlled",
    ):
        registry.preflight(payload, operator_authorized=True)


def test_unsupported_provider_selection_is_rejected() -> None:
    registry = _registry()

    with pytest.raises(ProviderRolloutError, match="provider_not_supported"):
        registry.preflight(_payload("gitea"), operator_authorized=True)


def test_connection_binding_prevents_cross_client_project_and_provider_reuse() -> None:
    registry = _registry()
    first = registry.preflight(_payload(), operator_authorized=True)

    for changed in (
        {"client_id": "other-client"},
        {"project_id": "other-project"},
        {"provider": "gitlab"},
    ):
        payload = _payload()
        payload.update(changed)
        payload["existing_connection_binding_id"] = first["connection_binding_id"]
        with pytest.raises(
            ProviderRolloutError,
            match="provider_connection_binding_mismatch",
        ):
            registry.preflight(payload, operator_authorized=True)


def test_locale_switch_preserves_same_connection_binding() -> None:
    registry = _registry()

    english = registry.preflight(_payload(locale="en-US"), operator_authorized=True)
    spanish = registry.preflight(_payload(locale="es-MX"), operator_authorized=True)

    assert english["connection_binding_id"] == spanish["connection_binding_id"]
    assert english["client_id"] == spanish["client_id"]
    assert english["project_id"] == spanish["project_id"]
    assert english["session_id"] == spanish["session_id"]
    assert english["run_id"] == spanish["run_id"]
    assert english["locale"] == "en-US"
    assert spanish["locale"] == "es-MX"


def test_engineering_parity_does_not_enable_production_client_claim() -> None:
    configs = _configs()
    configs[ProviderKind.GITLAB] = ProviderRolloutConfig(
        ProviderKind.GITLAB,
        ProviderRolloutState.PRODUCTION,
        True,
        credential_reference_id="gitlab-server-reference",
        capability_evidence_reference="artifact://gitlab/engineering",
    )
    support = dict(DEFAULT_SUPPORT)
    support[ProviderKind.GITLAB] = ProviderSupport(
        ProviderKind.GITLAB,
        SupportLevel.FIXTURE_ONLY,
        maturity=ProviderSupportMaturity.ENGINEERING_PARITY_PROVEN,
        engineering_parity_evidence_reference="artifact://gitlab/parity",
    )
    registry = _registry(configs=configs, support_registry=support)

    capability = registry.capability(ProviderKind.GITLAB)
    assert capability["availability_state"] == "preview_limited"
    assert capability["ordinary_client_onboarding_allowed"] is False
    with pytest.raises(ProviderRolloutError, match="provider_not_production_onboardable"):
        registry.preflight(
            {**_payload("gitlab"), "onboarding_mode": "ordinary_client"},
            operator_authorized=False,
        )


def test_stale_capability_revision_fails_closed() -> None:
    registry = _registry()
    payload = _payload()
    payload["expected_capability_revision"] = registry.revision + 1

    with pytest.raises(ProviderRolloutError, match="stale_provider_capability_evidence"):
        registry.preflight(payload, operator_authorized=True)


def test_missing_capability_evidence_blocks_controlled_pilot() -> None:
    configs = _configs()
    configs[ProviderKind.GITLAB] = ProviderRolloutConfig(
        ProviderKind.GITLAB,
        ProviderRolloutState.CONTROLLED_PILOT,
        True,
        credential_reference_id="gitlab-server-reference",
        capability_evidence_reference="",
    )
    support = dict(DEFAULT_SUPPORT)
    support[ProviderKind.GITLAB] = ProviderSupport(
        ProviderKind.GITLAB,
        SupportLevel.AUTHENTICATED_BETA,
        authenticated_conformance_run="gha://gitlab/123",
        maturity=ProviderSupportMaturity.REAL_PROVIDER_INTEGRATION_PROVEN,
        real_provider_integration_evidence_reference="artifact://gitlab/live/123",
    )
    registry = _registry(configs=configs, support_registry=support)

    capability = registry.capability(ProviderKind.GITLAB)
    assert capability["capability_evidence_state"] == "missing"
    assert capability["controlled_pilot_onboarding_allowed"] is False
    with pytest.raises(ProviderRolloutError, match="provider_controlled_pilot_not_proven"):
        registry.preflight(
            {**_payload("gitlab"), "onboarding_mode": "controlled_pilot"},
            operator_authorized=True,
        )


def test_repository_provider_and_ci_provider_remain_separate() -> None:
    registry = _registry()
    payload = _payload("gitlab")
    payload["ci_provider"] = "jenkins"

    result = registry.preflight(payload, operator_authorized=True)

    assert result["repository_provider"] == "gitlab"
    assert result["ci_provider"] == "jenkins"
    assert result["repository_and_ci_provider_separate"] is True
    capability = registry.capability(ProviderKind.GITLAB)
    assert capability["ci_provider"]["external_ci_is_separate"] is True


def test_raw_credentials_are_rejected_without_echoing_secret() -> None:
    registry = _registry()
    app = FastAPI()
    install_provider_rollout_routes(app, registry=registry)
    client = TestClient(app)
    secret = "never-return-this-provider-secret"

    response = client.post(
        "/providers/onboarding/preflight",
        json={**_payload(), "token": secret},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["detail"]["code"] == "raw_provider_credentials_prohibited"
    assert body["detail"]["credential_detail_exposed"] is False
    assert secret not in response.text


def test_controlled_pilot_requires_operator_and_real_provider_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-token")
    configs = _configs()
    configs[ProviderKind.GITLAB] = ProviderRolloutConfig(
        ProviderKind.GITLAB,
        ProviderRolloutState.CONTROLLED_PILOT,
        True,
        credential_reference_id="gitlab-server-reference",
        capability_evidence_reference="artifact://gitlab/capability/123",
    )
    support = dict(DEFAULT_SUPPORT)
    support[ProviderKind.GITLAB] = ProviderSupport(
        ProviderKind.GITLAB,
        SupportLevel.AUTHENTICATED_BETA,
        authenticated_conformance_run="gha://gitlab/123",
        maturity=ProviderSupportMaturity.REAL_PROVIDER_INTEGRATION_PROVEN,
        real_provider_integration_evidence_reference="artifact://gitlab/live/123",
    )
    registry = _registry(configs=configs, support_registry=support)
    app = FastAPI()
    install_provider_rollout_routes(app, registry=registry)
    client = TestClient(app)
    payload = {**_payload("gitlab"), "onboarding_mode": "controlled_pilot"}

    denied = client.post("/providers/onboarding/preflight", json=payload)
    accepted = client.post(
        "/providers/onboarding/preflight",
        headers={"X-NICO-Admin-Token": "operator-token"},
        json=payload,
    )

    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "authorized_controlled_pilot_required"
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "authorized"
    assert accepted.json()["availability_state"] == "controlled_pilot"
    assert accepted.json()["client_delivery_allowed"] is False


def test_production_onboarding_requires_cumulative_production_client_evidence() -> None:
    configs = _configs()
    configs[ProviderKind.GITHUB] = ProviderRolloutConfig(
        ProviderKind.GITHUB,
        ProviderRolloutState.PRODUCTION,
        True,
        credential_reference_id="github-server-reference",
        capability_evidence_reference="artifact://github/capability/456",
        native_ci_evidence_supported=True,
    )
    support = dict(DEFAULT_SUPPORT)
    support[ProviderKind.GITHUB] = ProviderSupport(
        ProviderKind.GITHUB,
        SupportLevel.PRODUCTION_VALIDATED,
        authenticated_conformance_run="gha://github/123",
        maturity=ProviderSupportMaturity.PRODUCTION_CLIENT_PROVEN,
        real_provider_integration_evidence_reference="artifact://github/live/123",
        controlled_pilot_evidence_reference="pilot://github/456",
        production_client_evidence_reference="delivery://github/789",
    )
    registry = _registry(configs=configs, support_registry=support)

    capability = registry.capability(ProviderKind.GITHUB)
    result = registry.preflight(
        {**_payload(), "onboarding_mode": "ordinary_client"},
        operator_authorized=False,
    )

    assert capability["availability_state"] == "production_supported"
    assert capability["ordinary_client_onboarding_allowed"] is True
    assert result["status"] == "authorized"
    assert result["credential_reference_exposed"] is False
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
