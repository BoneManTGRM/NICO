from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, replace
from enum import Enum
from threading import RLock
from typing import Any, Mapping

from fastapi import FastAPI, Header, HTTPException, Request

from nico.admin_security import require_admin_write
from nico.provider_platform_contract_v1 import ProviderContractViolation, ProviderKind
from nico.provider_support_policy_v1 import (
    DEFAULT_SUPPORT,
    ProviderSupport,
    ProviderSupportMaturity,
    provider_disclosure,
)

VERSION = "nico.provider_rollout_control.v1"
STATE_KEY = "nico_provider_rollout_registry_v1"
CAPABILITIES_ROUTE = "/providers/capabilities"
PREFLIGHT_ROUTE = "/providers/onboarding/preflight"
ROLLOUT_ROUTE = "/providers/{provider}/rollout"


class ProviderRolloutError(ValueError):
    def __init__(self, code: str, *, status_code: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class ProviderRolloutState(str, Enum):
    DISABLED = "disabled"
    INTERNAL_TEST = "internal_test"
    CONTROLLED_PILOT = "controlled_pilot"
    PRODUCTION = "production"


class ClientFacingProviderState(str, Enum):
    PRODUCTION_SUPPORTED = "production_supported"
    CONTROLLED_PILOT = "controlled_pilot"
    PREVIEW_LIMITED = "preview_limited"
    NOT_AVAILABLE = "not_available"


HOSTED_PROVIDER_ORDER = (
    ProviderKind.GITHUB,
    ProviderKind.GITLAB,
    ProviderKind.BITBUCKET_CLOUD,
    ProviderKind.AZURE_DEVOPS,
)

_HOSTED_INSTANCES = {
    ProviderKind.GITHUB: "https://github.com",
    ProviderKind.GITLAB: "https://gitlab.com",
    ProviderKind.BITBUCKET_CLOUD: "https://bitbucket.org",
    ProviderKind.AZURE_DEVOPS: "https://dev.azure.com",
}

_PROVIDER_LABELS = {
    ProviderKind.GITHUB: "GitHub.com",
    ProviderKind.GITLAB: "GitLab.com",
    ProviderKind.BITBUCKET_CLOUD: "Bitbucket Cloud",
    ProviderKind.AZURE_DEVOPS: "Azure DevOps Services / Azure Repos",
}

_AVAILABILITY_LABELS = {
    "en-US": {
        ClientFacingProviderState.PRODUCTION_SUPPORTED: "Production supported",
        ClientFacingProviderState.CONTROLLED_PILOT: "Controlled pilot",
        ClientFacingProviderState.PREVIEW_LIMITED: "Preview / limited",
        ClientFacingProviderState.NOT_AVAILABLE: "Not available",
    },
    "es-MX": {
        ClientFacingProviderState.PRODUCTION_SUPPORTED: "Compatible con producción",
        ClientFacingProviderState.CONTROLLED_PILOT: "Piloto controlado",
        ClientFacingProviderState.PREVIEW_LIMITED: "Vista previa / limitada",
        ClientFacingProviderState.NOT_AVAILABLE: "No disponible",
    },
}

_TAMPERED_AUTHORITY_FIELDS = frozenset(
    {
        "rollout_state",
        "support_level",
        "support_maturity",
        "availability_state",
        "client_onboarding_allowed",
        "controlled_pilot_allowed",
        "credential_configured",
        "capability_evidence_reference",
        "production_supported",
    }
)

_SECRET_FIELDS = frozenset(
    {
        "token",
        "access_token",
        "private_token",
        "password",
        "secret",
        "credential",
        "credentials",
        "authorization",
        "api_key",
    }
)

_MATURITY_ORDER = {
    ProviderSupportMaturity.UNSUPPORTED: 0,
    ProviderSupportMaturity.PARTIAL: 1,
    ProviderSupportMaturity.IMPLEMENTED_BUT_UNPROVEN: 2,
    ProviderSupportMaturity.IMPLEMENTED: 2,
    ProviderSupportMaturity.ENGINEERING_PARITY_PROVEN: 3,
    ProviderSupportMaturity.REAL_PROVIDER_INTEGRATION_PROVEN: 4,
    ProviderSupportMaturity.CONTROLLED_PILOT_PROVEN: 5,
    ProviderSupportMaturity.PRODUCTION_CLIENT_PROVEN: 6,
    ProviderSupportMaturity.BLOCKED_EXTERNAL: 2,
}


@dataclass(frozen=True)
class ProviderRolloutConfig:
    provider: ProviderKind
    rollout_state: ProviderRolloutState
    operational_enabled: bool
    credential_reference_id: str = ""
    capability_evidence_reference: str = ""
    repository_source_supported: bool = True
    native_ci_evidence_supported: bool = False

    @property
    def credential_configured(self) -> bool:
        return bool(self.credential_reference_id.strip())

    @property
    def capability_evidence_present(self) -> bool:
        return bool(self.capability_evidence_reference.strip())


@dataclass(frozen=True)
class ProviderOnboardingBinding:
    connection_binding_id: str
    provider: ProviderKind
    provider_instance: str
    client_id: str
    project_id: str
    session_id: str
    run_id: str
    credential_reference_fingerprint: str



def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _required(value: Any, field: str) -> str:
    normalized = _text(value)
    if not normalized:
        raise ProviderRolloutError(f"{field}_required")
    return normalized


def _locale(value: Any) -> str:
    normalized = _text(value).replace("_", "-").casefold()
    if normalized.startswith("es"):
        return "es-MX"
    return "en-US"


def _provider(value: Any) -> ProviderKind:
    token = _text(value).casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "github.com": ProviderKind.GITHUB,
        "github": ProviderKind.GITHUB,
        "gitlab.com": ProviderKind.GITLAB,
        "gitlab": ProviderKind.GITLAB,
        "bitbucket": ProviderKind.BITBUCKET_CLOUD,
        "bitbucket_cloud": ProviderKind.BITBUCKET_CLOUD,
        "bitbucket.org": ProviderKind.BITBUCKET_CLOUD,
        "azure": ProviderKind.AZURE_DEVOPS,
        "azure_repos": ProviderKind.AZURE_DEVOPS,
        "azure_devops": ProviderKind.AZURE_DEVOPS,
        "dev.azure.com": ProviderKind.AZURE_DEVOPS,
    }
    provider = aliases.get(token)
    if provider not in HOSTED_PROVIDER_ORDER:
        raise ProviderRolloutError("provider_not_supported")
    return provider


def _bool_from_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _env_prefix(provider: ProviderKind) -> str:
    return "NICO_PROVIDER_" + provider.value.upper()


def default_rollout_configs() -> dict[ProviderKind, ProviderRolloutConfig]:
    defaults = {
        ProviderKind.GITHUB: ProviderRolloutState.CONTROLLED_PILOT,
        ProviderKind.GITLAB: ProviderRolloutState.INTERNAL_TEST,
        ProviderKind.BITBUCKET_CLOUD: ProviderRolloutState.INTERNAL_TEST,
        ProviderKind.AZURE_DEVOPS: ProviderRolloutState.INTERNAL_TEST,
    }
    output: dict[ProviderKind, ProviderRolloutConfig] = {}
    for provider in HOSTED_PROVIDER_ORDER:
        prefix = _env_prefix(provider)
        raw_state = os.getenv(f"{prefix}_ROLLOUT", defaults[provider].value)
        try:
            state = ProviderRolloutState(raw_state.strip().casefold())
        except ValueError as exc:
            raise ProviderRolloutError(
                f"provider_rollout_state_invalid:{provider.value}"
            ) from exc
        output[provider] = ProviderRolloutConfig(
            provider=provider,
            rollout_state=state,
            operational_enabled=_bool_from_env(f"{prefix}_ENABLED", True),
            credential_reference_id=_text(
                os.getenv(f"{prefix}_CREDENTIAL_REFERENCE", "")
            ),
            capability_evidence_reference=_text(
                os.getenv(f"{prefix}_CAPABILITY_EVIDENCE", "")
            ),
            repository_source_supported=True,
            native_ci_evidence_supported=provider
            in {ProviderKind.GITHUB, ProviderKind.GITLAB, ProviderKind.AZURE_DEVOPS},
        )
    return output


def _maturity_at_least(
    maturity: ProviderSupportMaturity,
    threshold: ProviderSupportMaturity,
) -> bool:
    return _MATURITY_ORDER.get(maturity, 0) >= _MATURITY_ORDER.get(threshold, 0)


class ProviderRolloutRegistry:
    """Server-authoritative hosted-provider rollout and onboarding policy.

    Browser-supplied rollout, maturity, evidence, and credential state is never
    authoritative. Raw credentials are not accepted. The registry binds a server-side
    credential reference to the same client, project, session, provider instance, and
    optional run without exposing that reference after submission.
    """

    def __init__(
        self,
        configs: Mapping[ProviderKind, ProviderRolloutConfig] | None = None,
        support_registry: Mapping[ProviderKind, ProviderSupport] = DEFAULT_SUPPORT,
    ) -> None:
        source = dict(configs or default_rollout_configs())
        missing = set(HOSTED_PROVIDER_ORDER) - set(source)
        if missing:
            raise ProviderRolloutError(
                "provider_rollout_config_missing:" + ",".join(sorted(item.value for item in missing))
            )
        self._configs = {provider: source[provider] for provider in HOSTED_PROVIDER_ORDER}
        self._support_registry = dict(support_registry)
        self._revision = 1
        self._lock = RLock()
        self._audit: list[dict[str, Any]] = []

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def _support(self, provider: ProviderKind) -> tuple[ProviderSupport, dict[str, Any]]:
        support = self._support_registry.get(provider)
        if support is None:
            raise ProviderRolloutError("provider_support_record_missing", status_code=409)
        try:
            disclosure = provider_disclosure(provider, self._support_registry)
        except ProviderContractViolation as exc:
            raise ProviderRolloutError(
                "provider_support_evidence_invalid", status_code=409
            ) from exc
        return support, disclosure

    def _availability(
        self,
        config: ProviderRolloutConfig,
        support: ProviderSupport,
    ) -> ClientFacingProviderState:
        if not config.operational_enabled or config.rollout_state is ProviderRolloutState.DISABLED:
            return ClientFacingProviderState.NOT_AVAILABLE
        if config.rollout_state is ProviderRolloutState.PRODUCTION:
            if (
                support.client_claim_allowed
                and config.credential_configured
                and config.capability_evidence_present
            ):
                return ClientFacingProviderState.PRODUCTION_SUPPORTED
            return ClientFacingProviderState.PREVIEW_LIMITED
        if config.rollout_state is ProviderRolloutState.CONTROLLED_PILOT:
            if (
                _maturity_at_least(
                    support.maturity,
                    ProviderSupportMaturity.REAL_PROVIDER_INTEGRATION_PROVEN,
                )
                and config.credential_configured
                and config.capability_evidence_present
            ):
                return ClientFacingProviderState.CONTROLLED_PILOT
            return ClientFacingProviderState.PREVIEW_LIMITED
        return ClientFacingProviderState.PREVIEW_LIMITED

    def capability(self, provider: ProviderKind, *, locale: str = "en-US") -> dict[str, Any]:
        with self._lock:
            config = self._configs[provider]
            revision = self._revision
        support, disclosure = self._support(provider)
        availability = self._availability(config, support)
        normalized_locale = _locale(locale)
        return {
            "artifact_schema": VERSION,
            "capability_revision": revision,
            "provider": provider.value,
            "provider_label": _PROVIDER_LABELS[provider],
            "provider_instance": _HOSTED_INSTANCES[provider],
            "locale": normalized_locale,
            "rollout_state": config.rollout_state.value,
            "operational_enabled": config.operational_enabled,
            "availability_state": availability.value,
            "availability_label": _AVAILABILITY_LABELS[normalized_locale][availability],
            "support_level": disclosure["support_level"],
            "support_maturity": disclosure["maturity"],
            "client_claim_allowed": disclosure["client_claim_allowed"],
            "ordinary_client_onboarding_allowed": (
                availability is ClientFacingProviderState.PRODUCTION_SUPPORTED
            ),
            "controlled_pilot_onboarding_allowed": (
                availability is ClientFacingProviderState.CONTROLLED_PILOT
            ),
            "internal_test_onboarding_allowed": (
                config.operational_enabled
                and config.rollout_state is not ProviderRolloutState.DISABLED
                and config.credential_configured
            ),
            "credential_configured": config.credential_configured,
            "credential_reference_exposed": False,
            "capability_evidence_state": (
                "present" if config.capability_evidence_present else "missing"
            ),
            "repository_source": {
                "provider": provider.value,
                "supported": config.repository_source_supported,
                "state": (
                    "available" if config.repository_source_supported else "unsupported"
                ),
            },
            "ci_provider": {
                "provider": provider.value,
                "native_evidence_supported": config.native_ci_evidence_supported,
                "external_ci_is_separate": True,
                "external_ci_state": "not_configured",
            },
            "limitations": list(disclosure["limitations"]),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    def snapshot(self, *, locale: str = "en-US") -> dict[str, Any]:
        normalized_locale = _locale(locale)
        return {
            "artifact_schema": VERSION,
            "capability_revision": self.revision,
            "locale": normalized_locale,
            "one_product": "NICO COMPREHENSIVE",
            "repository_provider_parity_separate_from_platform_parity": True,
            "providers": [
                self.capability(provider, locale=normalized_locale)
                for provider in HOSTED_PROVIDER_ORDER
            ],
            "credentials_server_side_only": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @staticmethod
    def _credential_fingerprint(config: ProviderRolloutConfig) -> str:
        if not config.credential_configured:
            return ""
        return "sha256:" + hashlib.sha256(
            f"{config.provider.value}\x1f{config.credential_reference_id}".encode("utf-8")
        ).hexdigest()

    def _binding(
        self,
        config: ProviderRolloutConfig,
        *,
        client_id: str,
        project_id: str,
        session_id: str,
        run_id: str,
    ) -> ProviderOnboardingBinding:
        credential_fingerprint = self._credential_fingerprint(config)
        components = (
            VERSION,
            config.provider.value,
            _HOSTED_INSTANCES[config.provider],
            client_id,
            project_id,
            session_id,
            run_id,
            credential_fingerprint,
        )
        digest = hashlib.sha256("\x1f".join(components).encode("utf-8")).hexdigest()
        return ProviderOnboardingBinding(
            connection_binding_id=f"nico-provider-connection-v1:{digest}",
            provider=config.provider,
            provider_instance=_HOSTED_INSTANCES[config.provider],
            client_id=client_id,
            project_id=project_id,
            session_id=session_id,
            run_id=run_id,
            credential_reference_fingerprint=credential_fingerprint,
        )

    def preflight(
        self,
        payload: Mapping[str, Any],
        *,
        operator_authorized: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ProviderRolloutError("request_body_must_be_object")
        keys = {str(key).casefold() for key in payload}
        if keys & _SECRET_FIELDS:
            raise ProviderRolloutError("raw_provider_credentials_prohibited")
        if keys & _TAMPERED_AUTHORITY_FIELDS:
            raise ProviderRolloutError("provider_authority_state_is_server_controlled")

        provider = _provider(payload.get("provider"))
        locale = _locale(payload.get("locale"))
        client_id = _required(payload.get("client_id"), "client_id")
        project_id = _required(payload.get("project_id"), "project_id")
        session_id = _required(payload.get("session_id"), "session_id")
        run_id = _text(payload.get("run_id"))
        mode = _text(payload.get("onboarding_mode") or "ordinary_client").casefold()
        if mode not in {"ordinary_client", "controlled_pilot", "internal_test"}:
            raise ProviderRolloutError("provider_onboarding_mode_invalid")

        expected_revision = payload.get("expected_capability_revision")
        if expected_revision not in (None, ""):
            try:
                expected = int(expected_revision)
            except (TypeError, ValueError) as exc:
                raise ProviderRolloutError("capability_revision_invalid") from exc
            if expected != self.revision:
                raise ProviderRolloutError("stale_provider_capability_evidence", status_code=409)

        with self._lock:
            config = self._configs[provider]
        capability = self.capability(provider, locale=locale)
        if not config.operational_enabled or config.rollout_state is ProviderRolloutState.DISABLED:
            raise ProviderRolloutError("provider_operationally_disabled", status_code=409)
        if not config.credential_configured:
            raise ProviderRolloutError("provider_credential_reference_missing", status_code=409)
        if mode == "ordinary_client":
            if capability["ordinary_client_onboarding_allowed"] is not True:
                raise ProviderRolloutError("provider_not_production_onboardable", status_code=409)
        elif mode == "controlled_pilot":
            if not operator_authorized:
                raise ProviderRolloutError("authorized_controlled_pilot_required", status_code=403)
            if capability["controlled_pilot_onboarding_allowed"] is not True:
                raise ProviderRolloutError("provider_controlled_pilot_not_proven", status_code=409)
        else:
            if not operator_authorized:
                raise ProviderRolloutError("authorized_internal_test_required", status_code=403)
            if capability["internal_test_onboarding_allowed"] is not True:
                raise ProviderRolloutError("provider_internal_test_unavailable", status_code=409)

        binding = self._binding(
            config,
            client_id=client_id,
            project_id=project_id,
            session_id=session_id,
            run_id=run_id,
        )
        existing = _text(payload.get("existing_connection_binding_id"))
        if existing and existing != binding.connection_binding_id:
            raise ProviderRolloutError("provider_connection_binding_mismatch", status_code=409)

        ci_provider = _text(payload.get("ci_provider") or provider.value)
        if not ci_provider:
            ci_provider = provider.value
        return {
            "artifact_schema": VERSION,
            "status": "authorized",
            "onboarding_mode": mode,
            "locale": locale,
            "capability_revision": self.revision,
            "connection_binding_id": binding.connection_binding_id,
            "client_id": client_id,
            "project_id": project_id,
            "session_id": session_id,
            "run_id": run_id,
            "repository_provider": provider.value,
            "repository_provider_instance": binding.provider_instance,
            "ci_provider": ci_provider,
            "repository_and_ci_provider_separate": ci_provider != provider.value,
            "credential_reference_bound": True,
            "credential_reference_fingerprint": binding.credential_reference_fingerprint,
            "credential_reference_exposed": False,
            "rollout_state": capability["rollout_state"],
            "availability_state": capability["availability_state"],
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    def update_operational_state(
        self,
        provider: ProviderKind,
        *,
        rollout_state: ProviderRolloutState | None = None,
        operational_enabled: bool | None = None,
        actor: str,
    ) -> dict[str, Any]:
        normalized_actor = _required(actor, "actor")
        with self._lock:
            current = self._configs[provider]
            updated = replace(
                current,
                rollout_state=rollout_state or current.rollout_state,
                operational_enabled=(
                    current.operational_enabled
                    if operational_enabled is None
                    else bool(operational_enabled)
                ),
            )
            self._configs[provider] = updated
            self._revision += 1
            self._audit.append(
                {
                    "revision": self._revision,
                    "provider": provider.value,
                    "rollout_state": updated.rollout_state.value,
                    "operational_enabled": updated.operational_enabled,
                    "actor": normalized_actor,
                    "evidence_mutated": False,
                    "credential_mutated": False,
                }
            )
        return self.capability(provider)

    def audit_events(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._audit]


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    return {
        (str(method).upper(), str(getattr(route, "path", "")))
        for route in target.routes
        for method in (getattr(route, "methods", set()) or set())
    }


def _http_error(exc: ProviderRolloutError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": "Provider onboarding was blocked by server-authoritative rollout policy.",
            "credential_detail_exposed": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    )


def install_provider_rollout_routes(
    target: FastAPI,
    *,
    registry: ProviderRolloutRegistry | None = None,
) -> dict[str, Any]:
    current = getattr(target.state, STATE_KEY, None)
    if current is None:
        current = registry or ProviderRolloutRegistry()
        setattr(target.state, STATE_KEY, current)
    elif registry is not None and current is not registry:
        raise RuntimeError("provider_rollout_registry_already_installed")
    if not isinstance(current, ProviderRolloutRegistry):
        raise RuntimeError("provider_rollout_registry_invalid")

    existing = _route_pairs(target)
    required = {
        ("GET", CAPABILITIES_ROUTE),
        ("POST", PREFLIGHT_ROUTE),
        ("POST", ROLLOUT_ROUTE),
    }
    present = existing & required
    if present and present != required:
        raise RuntimeError(
            "partial_provider_rollout_route_registration:" + str(sorted(required - present))
        )

    if not present:

        @target.get(CAPABILITIES_ROUTE)
        async def provider_capabilities(locale: str = "en-US") -> dict[str, Any]:
            return current.snapshot(locale=locale)

        @target.post(PREFLIGHT_ROUTE)
        async def provider_onboarding_preflight(
            request: Request,
            x_nico_admin_token: str = Header(default=""),
        ) -> dict[str, Any]:
            try:
                payload = await request.json()
                allowed, _ = require_admin_write(x_nico_admin_token)
                return current.preflight(payload, operator_authorized=allowed)
            except ProviderRolloutError as exc:
                raise _http_error(exc) from exc

        @target.post(ROLLOUT_ROUTE)
        async def update_provider_rollout(
            provider: str,
            request: Request,
            x_nico_admin_token: str = Header(default=""),
        ) -> dict[str, Any]:
            allowed, status = require_admin_write(x_nico_admin_token)
            if not allowed:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "provider_rollout_admin_authentication_required",
                        "admin_write": status,
                        "credential_detail_exposed": False,
                        "human_review_required": True,
                        "client_delivery_allowed": False,
                    },
                )
            try:
                payload = await request.json()
                if not isinstance(payload, Mapping):
                    raise ProviderRolloutError("request_body_must_be_object")
                forbidden = {str(key).casefold() for key in payload} & (
                    _SECRET_FIELDS
                    | {
                        "capability_evidence_reference",
                        "credential_reference_id",
                        "support_maturity",
                        "support_level",
                    }
                )
                if forbidden:
                    raise ProviderRolloutError(
                        "provider_evidence_and_credentials_not_mutable_by_api"
                    )
                raw_state = payload.get("rollout_state")
                state = (
                    None
                    if raw_state in (None, "")
                    else ProviderRolloutState(_text(raw_state).casefold())
                )
                enabled = payload.get("operational_enabled")
                if enabled is not None and not isinstance(enabled, bool):
                    raise ProviderRolloutError("operational_enabled_must_be_boolean")
                return current.update_operational_state(
                    _provider(provider),
                    rollout_state=state,
                    operational_enabled=enabled,
                    actor=_text(payload.get("actor") or "provider_operator"),
                )
            except ValueError as exc:
                if isinstance(exc, ProviderRolloutError):
                    raise _http_error(exc) from exc
                raise _http_error(
                    ProviderRolloutError("provider_rollout_state_invalid")
                ) from exc

        target.openapi_schema = None

    route_counts = {
        f"{method} {path}": sum(
            1
            for route in target.routes
            if str(getattr(route, "path", "")) == path
            and method
            in {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
        )
        for method, path in sorted(required)
    }
    if any(count != 1 for count in route_counts.values()):
        raise RuntimeError(f"provider_rollout_routes_missing_or_duplicated:{route_counts}")
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "route_counts": route_counts,
        "capability_revision": current.revision,
        "provider_count": len(HOSTED_PROVIDER_ORDER),
        "credentials_server_side_only": True,
        "support_maturity_separate_from_rollout": True,
        "repository_provider_separate_from_ci_provider": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "CAPABILITIES_ROUTE",
    "ClientFacingProviderState",
    "HOSTED_PROVIDER_ORDER",
    "PREFLIGHT_ROUTE",
    "ProviderOnboardingBinding",
    "ProviderRolloutConfig",
    "ProviderRolloutError",
    "ProviderRolloutRegistry",
    "ProviderRolloutState",
    "ROLLOUT_ROUTE",
    "STATE_KEY",
    "VERSION",
    "default_rollout_configs",
    "install_provider_rollout_routes",
]
