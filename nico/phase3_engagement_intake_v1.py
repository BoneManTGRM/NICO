from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from functools import wraps
from typing import Any

from nico import comprehensive_api_routes as api_routes
from nico import comprehensive_run_service as run_service_module
from nico import decision_grade_human_evidence_v1 as human_model
from nico import strategic_human_evidence_v1 as persisted_human
from nico.comprehensive_run_service import ComprehensiveRunService

VERSION = "nico.phase3_engagement_intake.v1"
PATCH = "_nico_phase3_engagement_intake_v1"
ENGAGEMENT_MODULE = "stakeholder_context"
REQUIREMENTS_MODULE = "compliance_requirements"
ENGAGEMENT_FIELDS = ("access_method", "primary_technical_contact", "authorized_scope")
PLACEHOLDER_CUSTOMERS = {"", "default_customer", "internal", "internal_customer"}
PLACEHOLDER_PROJECTS = {"", "default_project", "internal", "internal_project"}


def _text(value: Any, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit]


def _values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [] if value in (None, "") else [_text(value)]


def _module(payload: Mapping[str, Any]) -> dict[str, Any]:
    human = payload.get("human_evidence") if isinstance(payload.get("human_evidence"), Mapping) else {}
    raw = human.get(ENGAGEMENT_MODULE)
    return deepcopy(dict(raw)) if isinstance(raw, Mapping) else {}


def validate_and_enrich_intake(payload: Mapping[str, Any]) -> dict[str, Any]:
    body = deepcopy(dict(payload))
    client = _text(body.get("client_name"), 300)
    project = _text(body.get("project_name"), 300)
    client_mode = bool(client or project)
    human = deepcopy(dict(body.get("human_evidence") or {})) if isinstance(body.get("human_evidence"), Mapping) else {}
    engagement = _module(body)
    evidence = deepcopy(dict(engagement.get("evidence") or {})) if isinstance(engagement.get("evidence"), Mapping) else {}
    if client_mode:
        if not client:
            raise ValueError("client_identity_required_for_client_engagement")
        if not project:
            raise ValueError("project_identity_required_for_client_engagement")
        missing = [field for field in ENGAGEMENT_FIELDS if not _values(evidence.get(field))]
        if missing:
            raise ValueError("client_engagement_context_required:" + ",".join(missing))
        evidence.update({
            "engagement_mode": ["client"], "client_identity": [client], "project_identity": [project],
            "repository_identity": [_text(body.get("repository"), 500)],
            "authorization_confirmation": ["confirmed" if body.get("authorization_confirmed") is True else "not_confirmed"],
        })
    else:
        evidence.update({
            "engagement_mode": ["internal"], "repository_identity": [_text(body.get("repository"), 500)],
            "authorization_confirmation": ["confirmed" if body.get("authorization_confirmed") is True else "not_confirmed"],
        })
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
        "client_identity": (_values(evidence.get("client_identity")) or [""])[0],
        "project_identity": (_values(evidence.get("project_identity")) or [""])[0],
        "primary_technical_contact": (_values(evidence.get("primary_technical_contact")) or [""])[0],
        "access_method": (_values(evidence.get("access_method")) or [""])[0],
        "authorized_scope": (_values(evidence.get("authorized_scope")) or [""])[0],
    }
    truth["client_delivery_identity_valid"] = bool(
        mode == "client" and all(truth[key] for key in ("client_identity", "project_identity", "primary_technical_contact", "access_method", "authorized_scope"))
        and customer not in PLACEHOLDER_CUSTOMERS and project_id not in PLACEHOLDER_PROJECTS
    )
    return truth


def client_delivery_identity_valid(record: Mapping[str, Any]) -> bool:
    return engagement_truth(record)["client_delivery_identity_valid"] is True


def _register_fields() -> None:
    updated = []
    for raw in human_model.MODULE_DEFINITIONS:
        item = dict(raw); fields = list(item.get("required_fields") or ()); module_id = str(item.get("module_id") or "")
        if module_id == ENGAGEMENT_MODULE:
            for field in ENGAGEMENT_FIELDS:
                if field not in fields: fields.append(field)
            item["description"] = "Stakeholder objectives/constraints plus client access method, primary technical contact, and authorized scope when this is client work."
        if module_id == REQUIREMENTS_MODULE:
            if "authority_status" not in fields: fields.append("authority_status")
            item["description"] = "Requirements, specifications, ADRs, acceptance criteria, or roadmap commitments with explicit authority status."
        item["required_fields"] = tuple(fields); updated.append(item)
    human_model.MODULE_DEFINITIONS = tuple(updated)
    for module_id in (ENGAGEMENT_MODULE, REQUIREMENTS_MODULE):
        definition = next(item for item in updated if item["module_id"] == module_id)
        retained = dict(persisted_human.MODULES[module_id]); retained["description"] = definition["description"]; retained["required_fields"] = definition["required_fields"]
        persisted_human.MODULES[module_id] = retained


def install_phase3_engagement_intake_v1() -> dict[str, Any]:
    _register_fields()
    if not getattr(api_routes._intake, PATCH, False):
        current = api_routes._intake
        @wraps(current)
        def guarded_intake(request: Any, payload: dict[str, Any]) -> dict[str, Any]:
            return current(request, validate_and_enrich_intake(payload))
        setattr(guarded_intake, PATCH, True); api_routes._intake = guarded_intake
    if not getattr(ComprehensiveRunService.review, PATCH, False):
        current_review = ComprehensiveRunService.review
        @wraps(current_review)
        def guarded_review(self: ComprehensiveRunService, run_id: str, *, reviewer: str, reviewer_role: str, decision: str, decision_reason: str, decided_at: str | None = None) -> dict[str, Any]:
            if str(decision or "").casefold() == "approved" and not client_delivery_identity_valid(self._store.load(run_id)):
                raise ValueError("client_delivery_identity_required_for_final_approval")
            return current_review(self, run_id, reviewer=reviewer, reviewer_role=reviewer_role, decision=decision, decision_reason=decision_reason, decided_at=decided_at)
        setattr(guarded_review, PATCH, True); ComprehensiveRunService.review = guarded_review; run_service_module.ComprehensiveRunService.review = guarded_review
    return {
        "artifact_schema": VERSION, "status": "installed", "client_and_project_required_for_client_mode": True,
        "primary_contact_access_scope_required": True, "internal_assessment_allowed": True,
        "internal_placeholder_client_delivery_blocked": True, "existing_human_evidence_modules_reused": True,
        "human_review_required": True, "client_delivery_allowed": False,
    }

__all__ = ["VERSION", "client_delivery_identity_valid", "engagement_truth", "install_phase3_engagement_intake_v1", "validate_and_enrich_intake"]
