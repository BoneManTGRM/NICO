"""Separately retained and authorized locale editions of one completed run.

The source assessment and its accepted artifacts are never replaced. Existing
review/delivery services operate on an isolated selected-edition context; only
that edition's package and lifecycle are committed alongside the source record.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import copy, deepcopy
from datetime import UTC, datetime
from typing import Any

from fastapi import Header, HTTPException, Request, Response

from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_review_decision_v1 import (
    assert_expected_review_artifact_identity, report_package_from_record,
)
from nico.comprehensive_run_record import (
    FINAL_REPORT_STAGE_ID, _record_hash, validate_comprehensive_run_record,
)
from nico.comprehensive_run_service import _require_exact_final_report_integrity
from nico.decision_grade_accepted_edition_guard_v1 import current_report_artifact_digest

VERSION = "nico.comprehensive_localized_edition.v1"
ROUTE = "/assessment/comprehensive-run/{run_id}/localized-editions/{report_language}"
_STATE_FIELDS = (
    "revision", "status", "terminal", "human_review_required", "human_review_completed",
    "client_delivery_allowed", "updated_at", "review_history", "review_decision",
    "accepted_edition", "review_context", "review_source_artifact_identity",
    "delivery_authorization", "approved_delivery_package", "review_work_status",
)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _valid(record: dict[str, Any]) -> None:
    result = validate_comprehensive_run_record(record)
    if result["status"] != "valid":
        raise ValueError("localized_edition_record_invalid:" + ",".join(result["violations"]))
    _require_exact_final_report_integrity(record)


def _parent_binding(record: dict[str, Any]) -> dict[str, Any]:
    _valid(record)
    if record.get("status") != "approved" or record.get("human_review_completed") is not True:
        raise ValueError("localized_edition_requires_approved_source")
    accepted = record.get("accepted_edition")
    if not isinstance(accepted, Mapping):
        raise ValueError("localized_edition_requires_approved_source")
    return {
        "source_identity": deepcopy(record["identity"]),
        "source_report_artifact_digest": current_report_artifact_digest(report_package_from_record(record)),
        "source_accepted_edition_sha256": canonical_sha256(accepted),
        "review_work_ledger_sha256": canonical_sha256(record.get("review_work_ledger") or {}),
    }


def _language(record: Mapping[str, Any], language: str) -> str:
    from nico.comprehensive_same_run_locale_report_v1 import _normalize_report_language
    language = _normalize_report_language(language)
    if language == record["identity"]["report_language"]:
        raise ValueError("localized_edition_use_source_controls")
    return language


def _entry_hash(entry: Mapping[str, Any]) -> str:
    return canonical_sha256({key: value for key, value in entry.items() if key != "integrity_sha256"})


def _context(root: dict[str, Any], entry: Mapping[str, Any]) -> dict[str, Any]:
    context = deepcopy(root)
    context.pop("localized_editions", None)
    for field in _STATE_FIELDS:
        context.pop(field, None)
    context.update(deepcopy(entry["state"]))
    context["identity"]["report_language"] = entry["report_language"]
    package = deepcopy(entry["report_package"])
    final_stage = context["stage_results"][FINAL_REPORT_STAGE_ID]
    final_stage["report_package"] = package
    final_stage["assessment"] = deepcopy(package["json"].get("assessment") or {})
    context.pop("reports", None)
    context["integrity_sha256"] = _record_hash(context)
    return context


def read_localized_edition(service: Any, run_id: str, language: str) -> tuple[dict, dict, dict]:
    root = service.load_read_only(run_id)
    language = _language(root, language)
    binding = _parent_binding(root)
    entry = (root.get("localized_editions") or {}).get(language)
    if not isinstance(entry, Mapping):
        raise KeyError("localized_edition_not_prepared")
    if entry.get("artifact_schema") != VERSION or entry.get("integrity_sha256") != _entry_hash(entry):
        raise ValueError("localized_edition_integrity_invalid")
    if entry.get("report_language") != language or entry.get("parent_binding") != binding:
        raise ValueError("localized_edition_source_binding_changed")
    context = _context(root, entry)
    _valid(context)
    return root, deepcopy(dict(entry)), context


def _save(service: Any, root: dict, entry: dict, context: dict) -> tuple[dict, dict, dict]:
    _valid(context)
    entry["report_package"] = report_package_from_record(context)
    entry["state"] = {field: deepcopy(context[field]) for field in _STATE_FIELDS if field in context}
    entry["integrity_sha256"] = _entry_hash(entry)
    previous = int(root["revision"])
    updated = deepcopy(root)
    updated.setdefault("localized_editions", {})[entry["report_language"]] = entry
    updated["revision"] = previous + 1
    updated["updated_at"] = _now()
    updated["integrity_sha256"] = _record_hash(updated)
    service._store.save(updated, expected_revision=previous)
    return updated, entry, context


def prepare_localized_edition(service: Any, run_id: str, language: str, payload: Mapping[str, Any]) -> tuple[dict, dict, dict]:
    if payload.get("preparation_authorized") is not True or payload.get("authorization_confirmed") is not True:
        raise ValueError("explicit_localized_preparation_authorization_required")
    root = service.load_read_only(run_id)
    language = _language(root, language)
    binding = _parent_binding(root)
    assert_expected_review_artifact_identity(root, payload.get("expected_artifact_identity"))
    if language in (root.get("localized_editions") or {}):
        # Preparation is idempotent and cannot overwrite an inspected/accepted edition.
        return read_localized_edition(service, run_id, language)
    from nico.comprehensive_same_run_locale_report_v1 import _assemble_target
    package = _assemble_target(report_package_from_record(root)["json"], language)
    entry = {
        "artifact_schema": VERSION, "report_language": language,
        "parent_binding": binding,
        "edition_id": "locale_" + canonical_sha256({"parent": binding, "language": language})[:32],
        "prepared_at": _now(), "report_package": package,
        "state": {"revision": 1, "status": "review_required", "terminal": True,
                  "human_review_required": True, "human_review_completed": False,
                  "client_delivery_allowed": False, "review_history": [], "updated_at": _now()},
    }
    context = _context(root, entry)
    if isinstance(root.get("review_work_ledger"), Mapping):
        from nico.comprehensive_review_report_truth_v1 import synchronize_review_truth
        from nico.comprehensive_review_work_runtime_v1 import _review_action_record
        # Use the existing zero-candidate validator compatibility view without
        # changing the persisted source/edition ledger representation or hash.
        retained_ledger = deepcopy(context["review_work_ledger"])
        context = synchronize_review_truth(_review_action_record(context))
        context["review_work_ledger"] = retained_ledger
        context["integrity_sha256"] = _record_hash(context)
    return _save(service, root, entry, context)


class _SelectedEditionStore:
    """In-memory transaction adapter; the parent store remains the only durable write."""
    def __init__(self, record: dict):
        self.record = deepcopy(record)

    def load(self, run_id: str) -> dict:
        if run_id != self.record["identity"]["run_id"]:
            raise KeyError("localized_edition_run_mismatch")
        return deepcopy(self.record)

    def save(self, record: dict, *, expected_revision: int) -> dict:
        if expected_revision != self.record["revision"] or record["revision"] != expected_revision + 1:
            raise ValueError("localized_edition_revision_conflict")
        _valid(record)
        self.record = deepcopy(record)
        return deepcopy(record)


def mutate_localized_edition(service: Any, run_id: str, language: str, payload: Mapping[str, Any], *, delivery: bool = False) -> tuple[dict, dict, dict]:
    root, entry, context = read_localized_edition(service, run_id, language)
    selected = copy(service)
    selected._store = _SelectedEditionStore(context)
    if delivery:
        if payload.get("delivery_authorized") is not True or payload.get("authorization_confirmed") is not True:
            raise ValueError("explicit_delivery_authorization_required")
        updated = selected.authorize_delivery(
            run_id, authorizer=str(payload.get("authorizer") or ""),
            authorizer_role=str(payload.get("authorizer_role") or ""),
            authorization_reason=str(payload.get("authorization_reason") or ""),
            expected_artifact_identity=payload.get("expected_artifact_identity"),
        )
    else:
        if payload.get("review_authorized") is not True or payload.get("authorization_confirmed") is not True:
            raise ValueError("explicit_review_authorization_required")
        # The installed service.review retains its Phase 2 readiness guard.
        # Also enforce it explicitly when a retained ledger exists in isolated use.
        if str(payload.get("decision") or "").strip().casefold() == "approved" and isinstance(context.get("review_work_ledger"), Mapping):
            from nico.comprehensive_review_work_safe_v1 import assert_ready_for_approval
            from nico.comprehensive_review_work_runtime_v1 import _review_action_record
            assert_ready_for_approval(_review_action_record(context))
        updated = selected.review(
            run_id, reviewer=str(payload.get("reviewer") or ""),
            reviewer_role=str(payload.get("reviewer_role") or ""),
            decision=str(payload.get("decision") or ""),
            decision_reason=str(payload.get("decision_reason") or ""),
            expected_artifact_identity=payload.get("expected_artifact_identity"),
        )
    return _save(service, root, entry, updated)


def register_localized_edition_routes(app: Any) -> None:
    from nico import comprehensive_api_routes as routes
    if any(getattr(route, "path", "") == ROUTE for route in app.routes):
        return

    def response(request: Request, result: tuple[dict, dict, dict], operation: str) -> dict:
        _, entry, context = result
        controller = routes._controller(request)
        projected = routes._review_projection(controller._response(
            context, operation=operation, browser_projection=routes._browser_projection_requested(request),
        ), context)
        projected["localized_edition"] = {key: deepcopy(entry[key]) for key in (
            "edition_id", "report_language", "parent_binding", "prepared_at",
        )}
        return routes._with_runtime_truth(request, projected)

    def failure(exc: Exception) -> Exception:
        if isinstance(exc, HTTPException):
            return exc
        if isinstance(exc, KeyError) and exc.args == ("localized_edition_not_prepared",):
            return HTTPException(404, detail={"code": "localized_edition_not_prepared"})
        return routes._translate_error(exc)

    @app.get(ROUTE)
    def get_edition(run_id: str, report_language: str, request: Request, x_nico_admin_token: str = Header(default="")) -> dict:
        try:
            routes._authorize_review(x_nico_admin_token)
            return response(request, read_localized_edition(routes._service(routes._controller(request)), run_id, report_language), "localized_edition")
        except Exception as exc:
            raise failure(exc) from exc

    @app.post(ROUTE)
    async def prepare_edition(run_id: str, report_language: str, request: Request, x_nico_admin_token: str = Header(default="")) -> dict:
        try:
            routes._authorize_review(x_nico_admin_token)
            payload = await request.json()
            if not isinstance(payload, dict):
                raise TypeError("request_body_must_be_object")
            from starlette.concurrency import run_in_threadpool
            result = await run_in_threadpool(prepare_localized_edition, routes._service(routes._controller(request)), run_id, report_language, payload)
            return response(request, result, "localized_edition_prepared")
        except Exception as exc:
            raise failure(exc) from exc

    async def mutate(run_id: str, report_language: str, request: Request, token: str, delivery: bool) -> dict:
        try:
            routes._authorize_review(token)
            payload = await request.json()
            if not isinstance(payload, dict):
                raise TypeError("request_body_must_be_object")
            from starlette.concurrency import run_in_threadpool
            result = await run_in_threadpool(mutate_localized_edition, routes._service(routes._controller(request)), run_id, report_language, payload, delivery=delivery)
            return response(request, result, "delivery_authorized" if delivery else "reviewed")
        except Exception as exc:
            raise failure(exc) from exc

    @app.post(ROUTE + "/review")
    async def review_edition(run_id: str, report_language: str, request: Request, x_nico_admin_token: str = Header(default="")) -> dict:
        return await mutate(run_id, report_language, request, x_nico_admin_token, False)

    @app.post(ROUTE + "/authorize-delivery")
    async def deliver_edition(run_id: str, report_language: str, request: Request, x_nico_admin_token: str = Header(default="")) -> dict:
        return await mutate(run_id, report_language, request, x_nico_admin_token, True)

    @app.get(ROUTE + "/approved-delivery-package")
    def download_edition(run_id: str, report_language: str, request: Request, x_nico_admin_token: str = Header(default="")) -> Response:
        try:
            routes._authorize_review(x_nico_admin_token)
            _, _, context = read_localized_edition(routes._service(routes._controller(request)), run_id, report_language)
            return routes._approved_delivery_response(context)
        except Exception as exc:
            raise failure(exc) from exc
