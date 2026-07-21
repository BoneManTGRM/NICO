from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_service import ComprehensiveRunService

VERSION = "nico.comprehensive_api_controller.v3"


def _ordered_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a response copy with stage results in canonical execution order.

    PostgreSQL JSONB does not preserve object insertion order. Without this response
    normalization, a persisted run can render a later running stage above already
    completed prerequisite stages even though the canonical completed-stage prefix is
    correct. Key ordering does not change the run's hashed semantic content.
    """

    ordered_record = deepcopy(record)
    raw_results = ordered_record.get("stage_results")
    if not isinstance(raw_results, dict):
        ordered_record["stage_results"] = {}
        return ordered_record

    ordered_results: dict[str, Any] = {}
    for stage_id in COMPREHENSIVE_STAGES:
        if stage_id in raw_results:
            ordered_results[stage_id] = deepcopy(raw_results[stage_id])
    for stage_id, result in raw_results.items():
        if stage_id not in ordered_results:
            ordered_results[str(stage_id)] = deepcopy(result)
    ordered_record["stage_results"] = ordered_results
    return ordered_record


def _bounded_percent(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return max(0.0, min(100.0, parsed))


def _active_stage_percent(record: dict[str, Any]) -> float | None:
    current_stage = str(record.get("current_stage") or "")
    stage_results = record.get("stage_results")
    if not current_stage or not isinstance(stage_results, dict):
        return None
    result = stage_results.get(current_stage)
    if not isinstance(result, dict):
        return None

    scanner = result.get("scanner")
    if isinstance(scanner, dict):
        nested = _bounded_percent(scanner.get("progress_percent"))
        if nested is not None:
            return nested
    evidence = result.get("evidence")
    if isinstance(evidence, dict):
        nested = _bounded_percent(evidence.get("progress_percent"))
        if nested is not None:
            return nested
    return _bounded_percent(result.get("stage_progress_percent"))


def _display_progress(record: dict[str, Any]) -> tuple[float, float | None]:
    """Interpolate active-stage progress for UI display only.

    The persisted record keeps its completed-stage percentage and integrity hash. The
    response-level percentage may advance within the current stage using bounded
    provider progress, which prevents a long scanner stage from looking frozen.
    """

    canonical = _bounded_percent(record.get("progress_percent")) or 0.0
    if record.get("terminal"):
        return canonical, None
    active = _active_stage_percent(record)
    if active is None:
        return canonical, None
    stage_width = 100.0 / len(COMPREHENSIVE_STAGES)
    interpolated = min(99.99, canonical + (stage_width * active / 100.0))
    return round(max(canonical, interpolated), 2), round(active, 2)


class ComprehensiveApiController:
    """Framework-neutral controller for the customer-facing Comprehensive API.

    HTTP adapters may expose these methods at native Comprehensive routes without
    leaking Mid, Full, or Deep product names. The controller always returns the
    canonical persisted run view and never grants approval or client delivery.
    """

    def __init__(self, service: ComprehensiveRunService) -> None:
        self._service = service

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = self._object(payload)
        repository = self._required(body.get("repository"), "repository")
        commit_sha = self._required(body.get("commit_sha"), "commit_sha")
        run_id = self._required(body.get("run_id"), "run_id")
        evidence_ledger_id = self._required(body.get("evidence_ledger_id"), "evidence_ledger_id")
        customer_id = self._required(body.get("customer_id"), "customer_id")
        project_id = self._required(body.get("project_id"), "project_id")
        if body.get("authorization_confirmed") is not True or body.get("authorized") is not True:
            raise ValueError("explicit_authorization_required")

        record = self._service.start(
            run_id=run_id,
            repository=repository,
            commit_sha=commit_sha,
            evidence_ledger_id=evidence_ledger_id,
            customer_id=customer_id,
            project_id=project_id,
            authorized=True,
        )
        return self._response(record, operation="started")

    def status(self, run_id: str) -> dict[str, Any]:
        record = self._service.load(self._required(run_id, "run_id"))
        return self._response(record, operation="status")

    def continue_run(self, run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = self._object(payload or {})
        bounded = body.get("max_stages")
        max_stages = None if bounded is None else int(bounded)
        if max_stages is not None and max_stages < 0:
            raise ValueError("max_stages_must_be_non_negative")
        record = self._service.resume(self._required(run_id, "run_id"), max_stages=max_stages)
        return self._response(record, operation="continued")

    @staticmethod
    def _object(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise TypeError("request_body_must_be_object")
        return deepcopy(payload)

    @staticmethod
    def _required(value: Any, field: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"{field}_required")
        return normalized

    @staticmethod
    def _response(record: dict[str, Any], *, operation: str) -> dict[str, Any]:
        canonical_record = _ordered_record(record)
        identity = deepcopy(canonical_record["identity"])
        display_progress, active_stage_progress = _display_progress(canonical_record)
        return {
            "artifact_schema": VERSION,
            "service_id": "comprehensive",
            "operation": operation,
            "run_id": identity["run_id"],
            "repository": identity["repository"],
            "commit_sha": identity["commit_sha"],
            "evidence_ledger_id": identity["evidence_ledger_id"],
            "customer_id": identity["customer_id"],
            "project_id": identity["project_id"],
            "status": canonical_record["status"],
            "current_stage": canonical_record["current_stage"],
            "completed_stages": deepcopy(canonical_record["completed_stages"]),
            "progress_percent": display_progress,
            "canonical_progress_percent": canonical_record["progress_percent"],
            "active_stage_progress_percent": active_stage_progress,
            "revision": canonical_record["revision"],
            "terminal": canonical_record["terminal"],
            "human_review_required": True,
            "client_delivery_allowed": False,
            "integrity_sha256": canonical_record["integrity_sha256"],
            "record": canonical_record,
        }


__all__ = ["ComprehensiveApiController", "VERSION"]
