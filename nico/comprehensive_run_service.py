from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from nico.comprehensive_approved_delivery_v1 import attach_approved_delivery_package
from nico.comprehensive_background_stage_execution_v1 import (
    BACKGROUND_STAGE_IDS,
    execute_background_stage,
    is_background_stage_in_progress,
)
from nico.comprehensive_background_terminal_order_v2 import (
    install_background_terminal_ordering,
)
from nico.comprehensive_blocked_run_recovery_v1 import (
    rewind_blocked_run_for_final_artifact_recovery,
)
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_pre_render_scanner_truth_v64 import (
    install_pre_render_authoritative_scanner_truth,
)
from nico.comprehensive_review_decision_v1 import build_reviewed_edition
from nico.comprehensive_run_record import (
    apply_comprehensive_review_decision,
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
)
from nico.comprehensive_run_store import ComprehensiveRunStore
from nico.comprehensive_stage_adapter import CapabilityExecutor, bind_capability_executors
from nico.comprehensive_stage_execution_timeout_v1 import execute_stage_with_timeout
from nico.comprehensive_stage_watchdog_v1 import (
    apply_stage_watchdog,
    rewind_stalled_stage_for_retry,
)

install_background_terminal_ordering()
install_pre_render_authoritative_scanner_truth()

VERSION = "nico.comprehensive_run_service.v10"


class ComprehensiveRunService:
    """Restart-safe orchestration over the canonical Comprehensive run record.

    Each completed stage and each explicit human review decision is persisted through
    the same optimistic-concurrency store. Approval binds the exact existing artifacts;
    it never reruns report generation or changes the assessed commit. An approved
    delivery archive is generated only after the accepted-edition manifest validates.

    Long scanner, triage, executive-briefing, and final-report providers execute behind
    a durable background polling boundary. Their HTTP continuation requests return
    promptly while exact-run work continues. Short stages keep the direct bounded
    execution path. Neither path can claim completion without a returned provider result,
    and both retain the existing one-retry, evidence-preserving stall contract.

    Background task persistence is monotonic: once a provider records a terminal task
    result, a delayed heartbeat cannot revert the durable task to ``running``. Before
    report rendering, exact-run scanner completion also replaces stale recursive
    incomplete-analyzer aliases so generated Markdown, HTML, JSON, and PDF cannot list a
    completed tool as incomplete.
    """

    def __init__(
        self,
        store: ComprehensiveRunStore,
        capability_executors: Mapping[str, CapabilityExecutor],
    ) -> None:
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
        assessment_depth: str = "strategic",
        report_language: str = "en",
        human_evidence: Any = None,
    ) -> dict[str, Any]:
        record = create_comprehensive_run_record(
            run_id=run_id,
            repository=repository,
            commit_sha=commit_sha,
            evidence_ledger_id=evidence_ledger_id,
            customer_id=customer_id,
            project_id=project_id,
            authorized=authorized,
            assessment_depth=assessment_depth,
            report_language=report_language,
            human_evidence=human_evidence,
        )
        return self._store.create(record)

    def load(self, run_id: str) -> dict[str, Any]:
        return self._store.load(run_id)

    def resume(
        self,
        run_id: str,
        *,
        max_stages: int | None = None,
    ) -> dict[str, Any]:
        record = self._store.load(run_id)
        if record.get("terminal"):
            recovered = rewind_blocked_run_for_final_artifact_recovery(record)
            if recovered == record:
                recovered = rewind_stalled_stage_for_retry(record)
            if recovered == record:
                return record
            record = self._store.save(
                recovered,
                expected_revision=int(record["revision"]),
            )

        remaining = len(COMPREHENSIVE_STAGES) - len(
            record.get("completed_stages") or []
        )
        budget = (
            remaining
            if max_stages is None
            else max(0, min(remaining, int(max_stages)))
        )
        for _ in range(budget):
            record = self._run_next_stage(record)
            if record.get("terminal"):
                break
        return record

    def run_to_review(self, run_id: str) -> dict[str, Any]:
        return self.resume(run_id, max_stages=None)

    def review(
        self,
        run_id: str,
        *,
        reviewer: str,
        reviewer_role: str,
        decision: str,
        decision_reason: str,
        decided_at: str | None = None,
    ) -> dict[str, Any]:
        record = self._store.load(run_id)
        previous_revision = int(record["revision"])
        manifest = build_reviewed_edition(
            record,
            reviewer=reviewer,
            reviewer_role=reviewer_role,
            decision=decision,
            decision_reason=decision_reason,
            decided_at=decided_at,
        )
        updated = apply_comprehensive_review_decision(
            record,
            manifest=manifest,
        )
        if str(decision or "").strip().casefold() == "approved":
            updated = attach_approved_delivery_package(updated, manifest)
        return self._store.save(updated, expected_revision=previous_revision)

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
                "error_code": "comprehensive_stage_executor_missing",
                "error_message": f"No executor is bound for stage {stage_id}.",
                "retryable": False,
                "cancelable": True,
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
                "assessment_depth": identity["assessment_depth"],
                "report_language": identity["report_language"],
                "human_evidence": deepcopy(record.get("human_evidence") or {}),
                "prior_stage_results": deepcopy(record.get("stage_results") or {}),
                "recovery_history": deepcopy(record.get("recovery_history") or []),
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
            if stage_id in BACKGROUND_STAGE_IDS:
                raw = execute_background_stage(
                    executor,
                    context,
                    stage_id=stage_id,
                )
                result = (
                    raw
                    if is_background_stage_in_progress(raw)
                    else apply_stage_watchdog(
                        record,
                        stage_id=stage_id,
                        result=raw,
                    )
                )
            else:
                raw = execute_stage_with_timeout(
                    executor,
                    context,
                    stage_id=stage_id,
                )
                result = apply_stage_watchdog(
                    record,
                    stage_id=stage_id,
                    result=raw,
                )

        previous_revision = int(record["revision"])
        updated = apply_comprehensive_stage_result(
            record,
            stage_id=stage_id,
            result=result,
        )
        return self._store.save(updated, expected_revision=previous_revision)


__all__ = ["ComprehensiveRunService", "VERSION"]
