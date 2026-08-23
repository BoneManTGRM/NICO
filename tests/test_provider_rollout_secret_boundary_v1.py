from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.provider_platform_contract_v1 import ProviderKind
from nico.provider_rollout_control_v1 import (
    ProviderRolloutConfig,
    ProviderRolloutRegistry,
    ProviderRolloutState,
    install_provider_rollout_routes,
)


def _registry() -> ProviderRolloutRegistry:
    return ProviderRolloutRegistry(
        configs={
            provider: ProviderRolloutConfig(
                provider,
                ProviderRolloutState.INTERNAL_TEST,
                True,
                credential_reference_id=f"{provider.value}-server-reference",
                capability_evidence_reference=f"artifact://{provider.value}/engineering",
                native_ci_evidence_supported=True,
            )
            for provider in (
                ProviderKind.GITHUB,
                ProviderKind.GITLAB,
                ProviderKind.BITBUCKET_CLOUD,
                ProviderKind.AZURE_DEVOPS,
            )
        }
    )


def _payload() -> dict[str, object]:
    return {
        "provider": "github",
        "client_id": "client-1",
        "project_id": "project-1",
        "session_id": "session-1",
        "run_id": "comprun-1",
        "locale": "en-US",
        "execution_mode": "internal_test",
    }


@pytest.mark.parametrize(
    "payload_fragment",
    (
        {"metadata": {"connection": {"token": "nested-provider-secret"}}},
        {"metadata": [{"access-token": "nested-provider-secret"}]},
        {"metadata": {"providerCredential": "nested-provider-secret"}},
        {"metadata": {"api key": "nested-provider-secret"}},
    ),
)
def test_nested_raw_credentials_are_rejected_without_echoing_secret(
    monkeypatch: pytest.MonkeyPatch,
    payload_fragment: dict[str, object],
) -> None:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-token")
    app = FastAPI()
    install_provider_rollout_routes(app, registry=_registry())
    client = TestClient(app)
    secret = "nested-provider-secret"

    response = client.post(
        "/providers/operator/preflight",
        headers={"X-NICO-Admin-Token": "operator-token"},
        json={**_payload(), **payload_fragment},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "raw_provider_credentials_prohibited"
    assert response.json()["detail"]["credential_detail_exposed"] is False
    assert response.json()["detail"]["operator_run_only"] is True
    assert response.json()["detail"]["customer_self_service"] is False
    assert secret not in response.text


def test_successful_preflight_exposes_no_credential_reference_derivative() -> None:
    result = _registry().preflight(_payload(), operator_authorized=True)

    assert result["credential_reference_bound"] is True
    assert result["credential_reference_exposed"] is False
    assert "credential_reference_fingerprint" not in result
    assert "github-server-reference" not in str(result)


def test_rollout_admin_route_rejects_nested_credentials_without_echo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-token")
    app = FastAPI()
    install_provider_rollout_routes(app, registry=_registry())
    client = TestClient(app)
    secret = "nested-rollout-secret"

    response = client.post(
        "/providers/github/rollout",
        headers={"X-NICO-Admin-Token": "operator-token"},
        json={
            "actor": "provider-operator",
            "operational_enabled": False,
            "metadata": {"authorization": secret},
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == (
        "provider_evidence_and_credentials_not_mutable_by_api"
    )
    assert response.json()["detail"]["credential_detail_exposed"] is False
    assert secret not in response.text


def test_no_public_provider_control_route_is_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-token")
    app = FastAPI()
    install_provider_rollout_routes(app, registry=_registry())
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/providers/operator/preflight" in paths
    assert "/providers/operator/capabilities" in paths
    assert "/providers/onboarding/preflight" not in paths
