from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import (
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
)
from nico.comprehensive_run_store import ComprehensiveRunStore
from nico.comprehensive_stage_adapter import CapabilityExecutor, bind_capability_executors

VERSION = "nico.comprehensive_run_service.v1"


class ComprehensiveRunService:
    """Restart-safe orchestration over the canonical Comprehensive run record.

    Each completed stage is persisted separately. A process interruption can resume
    from the exact next required stage without creating a second run or changing the
    repository snapshot. Human review and client delivery boundaries remain encoded
    in the persisted record rather than inferred by callers.
    """

    def __init__(self, store: ComprehensiveRunStore, capability_executors: Mapping[str, CapabilityExecutor]) -> None:
        self._store = store
        self._stage_executors = bind_capability_executors(capability_executors)

    def start(
        self,
        *,
        run_id: str,
        repository: str,
        commit_sha: str,
        evidence_ledger_id: str,
        customer_id: str,
        project_id: str,
        authorized: bool,
    ) -> dict[str, Any]:
        record = create_comprehensive_run_record(
            run_id=run_id,
            repository=repository,
            commit_sha=commit_sha,
            evidence_ledger_id=evidence_ledger_id,
            customer_id=customer_id,
            project_id=project_id,
            authorized=authorized,
        )
        return self._store.create(record)

    def load(self, run_id: str) -> dict[str, Any]:
        return self._store.load(run_id)

    def resume(self, run_id: str, *, max_stages: int | None = None) -> dict[str, Any]:
        record = self._store.load(run_id)
        if record.get("terminal"):
            return record

        remaining = len(COMPREHENSIVE_STAGES) - len(record.get("completed_stages") or [])
        budget = remaining if max_stages is None else max(0, min(remaining, int(max_stages)))
        for _ in range(budget):
            record = self._run_next_stage(record)
            if record.get("terminal"):
                break
        return record

    def run_to_review(self, run_id: str) -> dict[str, Any]:
        return self.resume(run_id, max_stages=None)

    def _run_next_stage(self, record: dict[str, Any]) -> dict[str, Any]:
        completed = list(record.get("completed_stages") or [])
        if len(completed) >= len(COMPREHENSIVE_STAGES):
            return record

        stage_id = COMPREHENSIVE_STAGES[len(completed)]
        executor = self._stage_executors.get(stage_id)
        identity = record["identity"]
        if executor is None:
            result: dict[str, Any] = {
                "status": "blocked",
                "reason": f"missing_executor:{stage_id}",
            }
        else:
            context = {
                "artifact_schema": VERSION,
                "service_id": "comprehensive",
                "stage_id": stage_id,
                "run_id": identity["run_id"],
                "repository": identity["repository"],
                "commit_sha": identity["commit_sha"],
                "evidence_ledger_id": identity["evidence_ledger_id"],
                "customer_id": identity["customer_id"],
                "project_id": identity["project_id"],
                "prior_stage_results": deepcopy(record.get("stage_results") or {}),
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
            raw = executor(context)
            if not isinstance(raw, dict):
                raise TypeError(f"stage_executor_must_return_dict:{stage_id}")
            result = raw

        previous_revision = int(record["revision"])
        updated = apply_comprehensive_stage_result(
            record,
            stage_id=stage_id,
            result=result,
        )
        return self._store.save(updated, expected_revision=previous_revision)


__all__ = ["ComprehensiveRunService", "VERSION"]
