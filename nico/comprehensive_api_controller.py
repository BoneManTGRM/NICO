from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.comprehensive_run_service import ComprehensiveRunService

VERSION = "nico.comprehensive_api_controller.v1"


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
        identity = deepcopy(record["identity"])
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
            "status": record["status"],
            "current_stage": record["current_stage"],
            "completed_stages": deepcopy(record["completed_stages"]),
            "progress_percent": record["progress_percent"],
            "revision": record["revision"],
            "terminal": record["terminal"],
            "human_review_required": True,
            "client_delivery_allowed": False,
            "integrity_sha256": record["integrity_sha256"],
            "record": deepcopy(record),
        }


__all__ = ["ComprehensiveApiController", "VERSION"]
