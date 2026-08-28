from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from functools import wraps
from typing import Any

from fastapi import FastAPI

from nico import comprehensive_api_routes as api_routes

VERSION = "nico.phase3_engagement_intake.v6"
INTAKE_PATCH = "_nico_phase3_engagement_intake_v1"
REVIEW_PATCH = "_nico_phase3_review_identity_v1"
RECOVERY_PATCH = "_nico_phase3_recovery_identity_v1"
ENGAGEMENT_MODULE = "stakeholder_context"
ENGAGEMENT_FIELDS = ("access_method", "primary_technical_contact", "authorized_scope")
_ENGAGEMENT_LITERAL_LIMITS = {
    "client_identity": 180,
    "project_identity": 180,
    "primary_technical_contact": 600,
    "access_method": 1200,
    "authorized_scope": 4000,
}
# These scopes are explicitly non-client. The reserved production-proof pair exists only
# for isolated release verification and is protected independently by the proof lifecycle.
PLACEHOLDER_CUSTOMERS = {
    "",
    "default_customer",
    "internal",
    "internal_customer",
    "nico_production_proof",
}
PLACEHOLDER_PROJECTS = {
    "",
    "default_project",
    "internal",
    "internal_project",
    "spanish_comprehensive_production",
}


def _text(value: Any, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit]


def _values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [] if value in (None, "") else [_text(value)]


def _literal_values(value: Any, *, limit: int) -> list[str]:
    """Return bounded engagement values without rewriting human-entered text."""

    from nico.comprehensive_engagement_metadata_v1 import _literal

    values = list(value) if isinstance(value, (list, tuple)) else [value]
    output: list[str] = []
    for item in values:
        literal = _literal(item, limit)
        if literal:
            output.append(literal)
    return output


def _module(payload: Mapping[str, Any]) -> dict[str, Any]:
    human = payload.get("human_evidence") if isinstance(payload.get("human_evidence"), Mapping) else {}
    raw = human.get(ENGAGEMENT_MODULE)
    return deepcopy(dict(raw)) if isinstance(raw, Mapping) else {}


def _client_mode(payload: Mapping[str, Any], client: str, project: str) -> bool:
    """Resolve client mode from authoritative scope when the caller supplied it.

    Public Comprehensive intake now keeps optional client/project labels as display
    metadata while sending the canonical default scope explicitly. Those labels must
    therefore never escalate the request into a client-final engagement or make the
    three lightweight context fields mandatory. Explicit non-placeholder scope remains
    the authority for real client mode. The reserved synthetic production-proof scope
    is also explicitly non-client. Legacy callers that omit scope keys retain the
    original label-driven behavior for compatibility.
    """

    scope_supplied = "customer_id" in payload or "project_id" in payload
    if not scope_supplied:
        return bool(client or project)

    customer = _text(payload.get("customer_id"), 240).casefold()
    project_id = _text(payload.get("project_id"), 240).casefold()
    customer_is_client = customer not in PLACEHOLDER_CUSTOMERS
    project_is_client = project_id not in PLACEHOLDER_PROJECTS
    if customer_is_client != project_is_client:
        raise ValueError("client_project_scope_identity_required")
    return customer_is_client and project_is_client


def validate_and_enrich_intake(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Bind client identity and scope without changing the ten-module evidence schema."""

    body = deepcopy(dict(payload))
    client = (_literal_values(body.get("client_name"), limit=180) or [""])[0]
    project = (_literal_values(body.get("project_name"), limit=180) or [""])[0]
    client_mode = _client_mode(body, client, project)
    human = (
        deepcopy(dict(body.get("human_evidence") or {}))
        if isinstance(body.get("human_evidence"), Mapping)
        else {}
    )
    engagement = _module(body)
    evidence = (
        deepcopy(dict(engagement.get("evidence") or {}))
        if isinstance(engagement.get("evidence"), Mapping)
        else {}
    )
    if client_mode:
        if not client:
            raise ValueError("client_identity_required_for_client_engagement")
        if not project:
            raise ValueError("project_identity_required_for_client_engagement")
        missing = [
            field
            for field in ENGAGEMENT_FIELDS
            if not _literal_values(
                evidence.get(field),
                limit=_ENGAGEMENT_LITERAL_LIMITS[field],
            )
        ]
        if missing:
            raise ValueError("client_engagement_context_required:" + ",".join(missing))
        evidence.update(
            {
                "engagement_mode": ["client"],
                "client_identity": [client],
                "project_identity": [project],
                "repository_identity": [_text(body.get("repository"), 500)],
                "authorization_confirmation": [
                    "confirmed" if body.get("authorization_confirmed") is True else "not_confirmed"
                ],
            }
        )
    else:
        evidence.update(
            {
                "engagement_mode": ["internal"],
                "repository_identity": [_text(body.get("repository"), 500)],
                "authorization_confirmation": [
                    "confirmed" if body.get("authorization_confirmed") is True else "not_confirmed"
                ],
            }
        )
    engagement["evidence"] = evidence
    engagement.setdefault("reviewer", "")
    engagement.setdefault("observed_at", "")
    engagement.setdefault("source_reference", "")
    human[ENGAGEMENT_MODULE] = engagement
    body["human_evidence"] = human
    body["phase3_engagement_mode"] = "client" if client_mode else "internal"
    return body


def engagement_truth(record: Mapping[str, Any]) -> dict[str, Any]:
    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    human = record.get("human_evidence") if isinstance(record.get("human_evidence"), Mapping) else {}
    modules = human.get("modules") if isinstance(human.get("modules"), Mapping) else {}
    module = modules.get(ENGAGEMENT_MODULE) if isinstance(modules.get(ENGAGEMENT_MODULE), Mapping) else {}
    evidence = module.get("evidence") if isinstance(module.get("evidence"), Mapping) else {}
    declared = (_values(evidence.get("engagement_mode")) or [""])[0].casefold()
    customer = _text(identity.get("customer_id"), 240).casefold()
    project_id = _text(identity.get("project_id"), 240).casefold()
    inferred = "internal" if customer in PLACEHOLDER_CUSTOMERS or project_id in PLACEHOLDER_PROJECTS else "client"
    mode = declared if declared in {"internal", "client"} else inferred
    truth = {
        "mode": mode,
        "client_identity": (
            _literal_values(
                evidence.get("client_identity"),
                limit=_ENGAGEMENT_LITERAL_LIMITS["client_identity"],
            )
            or [""]
        )[0],
        "project_identity": (
            _literal_values(
                evidence.get("project_identity"),
                limit=_ENGAGEMENT_LITERAL_LIMITS["project_identity"],
            )
            or [""]
        )[0],
        "primary_technical_contact": (
            _literal_values(
                evidence.get("primary_technical_contact"),
                limit=_ENGAGEMENT_LITERAL_LIMITS["primary_technical_contact"],
            )
            or [""]
        )[0],
        "access_method": (
            _literal_values(
                evidence.get("access_method"),
                limit=_ENGAGEMENT_LITERAL_LIMITS["access_method"],
            )
            or [""]
        )[0],
        "authorized_scope": (
            _literal_values(
                evidence.get("authorized_scope"),
                limit=_ENGAGEMENT_LITERAL_LIMITS["authorized_scope"],
            )
            or [""]
        )[0],
    }
    truth["client_delivery_identity_valid"] = bool(
        mode == "client"
        and all(
            truth[key]
            for key in (
                "client_identity",
                "project_identity",
                "primary_technical_contact",
                "access_method",
                "authorized_scope",
            )
        )
        and customer not in PLACEHOLDER_CUSTOMERS
        and project_id not in PLACEHOLDER_PROJECTS
    )
    return truth


def client_delivery_identity_valid(record: Mapping[str, Any]) -> bool:
    return engagement_truth(record)["client_delivery_identity_valid"] is True


def _guard_service(service: Any) -> bool:
    """Guard one concrete Comprehensive service without global class monkeypatching."""

    if service is None:
        return False
    if getattr(service, REVIEW_PATCH, False):
        return True
    current_review = getattr(service, "review", None)
    load = getattr(service, "load", None)
    if not callable(current_review) or not callable(load):
        return False

    @wraps(current_review)
    def guarded_review(
        run_id: str,
        *,
        reviewer: str,
        reviewer_role: str,
        decision: str,
        decision_reason: str,
        decided_at: str | None = None,
        expected_artifact_identity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if str(decision or "").casefold() == "approved" and not client_delivery_identity_valid(load(run_id)):
            raise ValueError("client_delivery_identity_required_for_final_approval")
        return current_review(
            run_id,
            reviewer=reviewer,
            reviewer_role=reviewer_role,
            decision=decision,
            decision_reason=decision_reason,
            decided_at=decided_at,
            expected_artifact_identity=expected_artifact_identity,
        )

    service.review = guarded_review
    setattr(service, REVIEW_PATCH, True)
    return True


def _install_current_service_guard(app: FastAPI) -> bool:
    controller = getattr(app.state, "comprehensive_api_controller", None)
    return _guard_service(getattr(controller, "_service", None))


def _install_recovery_guard() -> bool:
    """Ensure a controller created after transient database recovery gets the same guard."""

    try:
        from nico.api import comprehensive_production_bootstrap as api_bootstrap
    except Exception:
        return False
    current = getattr(api_bootstrap, "install_comprehensive_production_bootstrap", None)
    if not callable(current):
        return False
    if getattr(current, RECOVERY_PATCH, False):
        return True

    @wraps(current)
    def guarded_bootstrap(*args: Any, **kwargs: Any) -> Any:
        controller = current(*args, **kwargs)
        _guard_service(getattr(controller, "_service", None))
        return controller

    setattr(guarded_bootstrap, RECOVERY_PATCH, True)
    api_bootstrap.install_comprehensive_production_bootstrap = guarded_bootstrap
    return True


def install_phase3_engagement_intake_v1(app: FastAPI | None = None) -> dict[str, Any]:
    if not getattr(api_routes._intake, INTAKE_PATCH, False):
        current = api_routes._intake

        @wraps(current)
        def guarded_intake(request: Any, payload: dict[str, Any]) -> dict[str, Any]:
            return current(request, validate_and_enrich_intake(payload))

        setattr(guarded_intake, INTAKE_PATCH, True)
        api_routes._intake = guarded_intake

    review_guard_installed = _install_current_service_guard(app) if app is not None else False
    recovery_guard_installed = _install_recovery_guard()
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "client_and_project_required_for_client_mode": True,
        "primary_contact_access_scope_required": True,
        "client_mode_requires_authoritative_non_placeholder_scope": True,
        "optional_display_labels_do_not_enable_client_mode": True,
        "reserved_production_proof_scope_is_non_client": True,
        "internal_assessment_allowed": True,
        "internal_placeholder_client_delivery_blocked": True,
        "existing_human_evidence_modules_reused": True,
        "historical_module_definition_contract_mutated": False,
        "approval_identity_guard_scoped_to_installed_service": True,
        "approval_identity_guard_installed": review_guard_installed,
        "runtime_recovery_guard_installed": recovery_guard_installed,
        "runtime_recovery_reapplies_approval_identity_guard": recovery_guard_installed,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_guard_service",
    "client_delivery_identity_valid",
    "engagement_truth",
    "install_phase3_engagement_intake_v1",
    "validate_and_enrich_intake",
]
