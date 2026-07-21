from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI

from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_stage_adapter import CapabilityExecutor

VERSION = "nico.comprehensive_production_capabilities.v2"
PROVIDER_STATE_KEY = "comprehensive_capability_providers"


def _required_capabilities() -> tuple[str, ...]:
    return tuple(str(item["capability"]) for item in execution_plan())


def _identity(context: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        value = str(context.get(field) or "").strip()
        if not value:
            raise ValueError(f"{field}_required")
        result[field] = value
    return result


def _authorization_provider(context: dict[str, Any]) -> dict[str, Any]:
    identity = _identity(context)
    if str(context.get("service_id") or "") != "comprehensive":
        return {
            "status": "blocked",
            "reason": "service_id_must_be_comprehensive",
            **identity,
        }
    return {
        "status": "complete",
        "capability": "authorization",
        "authorization_confirmed": True,
        "scope": "authorized_read_only_assessment",
        "summary": (
            "Ownership or explicit authorization and the defensive read-only scope "
            "were confirmed for this exact Comprehensive run."
        ),
        "evidence": {
            "authorization_confirmed": True,
            "scope": "authorized_read_only_assessment",
            "repository": identity["repository"],
            "commit_sha": identity["commit_sha"],
        },
        **identity,
    }


def _providers(app: FastAPI) -> dict[str, CapabilityExecutor]:
    raw = getattr(app.state, PROVIDER_STATE_KEY, None)
    if not isinstance(raw, Mapping):
        return {}
    return {str(name): provider for name, provider in raw.items() if callable(provider)}


def _normalize_result(
    capability: str,
    context: dict[str, Any],
    raw: Any,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypeError(f"comprehensive_provider_must_return_dict:{capability}")
    identity = _identity(context)
    result = dict(raw)
    result.setdefault("status", "complete")
    result["capability"] = capability
    result.update(identity)
    result["human_review_required"] = True
    result["client_delivery_allowed"] = False
    return result


def build_production_capability_executors(app: FastAPI) -> dict[str, CapabilityExecutor]:
    """Build the complete production capability map without fabricating evidence.

    Authorization is enforced by the native controller and represented by one
    built-in provider. Every other executor resolves its provider dynamically from
    application state. Missing providers return an explicit blocked result, so a
    configured durable runtime can expose exact stage-level readiness without ever
    treating unavailable evidence as complete.
    """

    executors: dict[str, CapabilityExecutor] = {}
    for capability in _required_capabilities():
        if capability == "authorization":
            executors[capability] = _authorization_provider
            continue

        def execute(context: dict[str, Any], *, _capability: str = capability) -> dict[str, Any]:
            provider = _providers(app).get(_capability)
            if provider is None:
                return _normalize_result(
                    _capability,
                    context,
                    {
                        "status": "blocked",
                        "reason": f"comprehensive_provider_missing:{_capability}",
                        "evidence_available": False,
                    },
                )
            return _normalize_result(_capability, context, provider(dict(context)))

        executors[capability] = execute

    available = sorted({"authorization", *_providers(app).keys()})
    required = _required_capabilities()
    app.state.nico_comprehensive_capability_provider_status = {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "required_capability_count": len(required),
        "available_capabilities": [name for name in required if name in available],
        "missing_capabilities": [name for name in required if name not in available],
        "fail_closed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return executors


__all__ = [
    "PROVIDER_STATE_KEY",
    "VERSION",
    "build_production_capability_executors",
]
