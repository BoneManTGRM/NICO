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
    is_recoverable_final_artifact_failure,
    rewind_blocked_run_for_final_artifact_recovery,
)
from nico.comprehensive_final_report_background_v1 import (
    FinalReportPublicationCoordinator,
)
from nico.comprehensive_final_report_execution_boundary_v4 import FINAL_REPORT_STAGE_ID
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_pre_render_scanner_truth_v65 import (
    install_pre_render_authoritative_scanner_truth,
)
from nico.comprehensive_report_flatten_bound_v1 import install_bounded_report_flatten
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
install_bounded_report_flatten()
install_pre_render_authoritative_scanner_truth()

VERSION = "nico.comprehensive_run_service.v16"

_EXECUTIVE_BRIEFING_STAGE_ID = "risk_reduction_and_executive_briefing"
_EXECUTIVE_BRIEFING_PRIOR_STAGE_IDS = (
    "evidence_reconciliation_and_scoring",
    "functional_qa",
    "platform_parity",
    "requirements_traceability",
    "stakeholder_and_business_alignment",
    "historical_trends_and_change_failure",
    "six_month_roadmap",
    "staffing_sequencing_and_cost",
)


def _prior_stage_results_for_stage(
    stage_id: str,
    retained_stage_results: dict[str, Any],
    completed: list[str],
) -> dict[str, Any]:
    """Build the smallest safe prior-stage context for one stage.

    The executive briefing consumes a fixed, bounded set of synthesized/scoring
    predecessors. Copying the full retained stage tree here would clone repository and
    scanner payloads before the hard stage-timeout subprocess is even started. On large
    production runs that can exhaust the request window at the 83% boundary while the
    canonical run itself remains valid. Keep mutation isolation by deep-copying only the
    exact predecessors the briefing provider reads.

    Final report generation keeps its existing copy-on-write reference behavior because
    it intentionally consumes the complete canonical evidence tree. Other stages retain
    the historical full deep-copy contract.
    """

    if stage_id == FINAL_REPORT_STAGE_ID:
        if FINAL_REPORT_STAGE_ID not in retained_stage_results:
            return retained_stage_results
        return {
            completed_stage: retained_stage_results[completed_stage]
            for completed_stage in completed
            if completed_stage in retained_stage_results
        }

    if stage_id == _EXECUTIVE_BRIEFING_STAGE_ID:
        return {
            prior_stage_id: deepcopy(retained_stage_results[prior_stage_id])
            for prior_stage_id in _EXECUTIVE_BRIEFING_PRIOR_STAGE_IDS
            if prior_stage_id in retained_stage_results
        }

    return deepcopy(retained_stage_results)


def _final_report_status_maintenance_required(record: Mapping[str, Any]) -> bool:
    """Keep the durable final-report lease alive/recoverable during status polling.

    The public UI and production acceptance proof poll canonical run status while final
    report generation is detached. After a process/container replacement, the prior
    worker and watchdog disappear but the exact durable run and lease remain. A status
    read at the final-report boundary therefore performs one bounded continuation tick:
    active/fresh leases are a no-op, stale leases are reclaimed by the coordinator, and
    recoverable terminal final-report failures consume only the existing one-attempt
    recovery budget. No earlier scanner stage is rerun.
    """

    completed = list(record.get("completed_stages") or [])
    if FINAL_REPORT_STAGE_ID in completed or len(completed) >= len(COMPREHENSIVE_STAGES):
        return False
    next_stage = COMPREHENSIVE_STAGES[len(completed)]
    if next_stage != FINAL_REPORT_STAGE_ID:
        return False
    if record.get("terminal") is True:
        return is_recoverable_final_artifact_failure(record)
    return True


class ComprehensiveRunService:
    """Restart-safe orchestration over the canonical Comprehensive run record.

    Each completed stage and each explicit human review decision is persisted through
    the same optimistic-concurrency store. Approval binds the exact existing artifacts;
    it never reruns report generation or changes the assessed commit. An approved
    delivery archive is generated only after the accepted-edition manifest validates.

    Long-running scanner stages execute behind a durable polling boundary. Final report
    publication keeps its stricter atomic package validation, but generation now runs
    behind a dedicated durable lease so the browser continuation request never has to
    remain open for the full PDF/HTML/Markdown/JSON render. Only a small running marker
    and lease heartbeat are persisted during generation; the complete report package is
    committed once through the canonical optimistic-concurrency run transaction.

    Scanner truth is canonicalized once with copy-on-write traversal before rendering.
    On first entry to the final stage, the exact already-loaded completed-stage result
    mapping is passed by reference so the large scanner tree is not cloned. During
    recovery from an existing final-report running marker, a shallow mapping excludes
    only that marker while retaining each completed stage result by reference.
    Final-report processing remains copy-on-write, so the persisted run cannot be
    mutated by the renderer. Scores, scanner findings, report design, human review,
    and blocked client delivery remain unchanged.
    """

    def __init__(
        self,
        store: ComprehensiveRunStore,
        capability_executors: Mapping[str, CapabilityExecutor],
    ) -> None:
        self._store = store
        self._stage_executors = bind_capability_executors(capability_executors)
        self._final_report_publication = FinalReportPublicationCoordinator(store)

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
        record = self._store.load(run_id)
        if _final_report_status_maintenance_required(record):
            return self.resume(run_id, max_stages=1)
        return record

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
            before_revision = int(record.get("revision") or 0)
            record = self._run_next_stage(record)
            if record.get("terminal"):
                break
            # An asynchronous final-report marker is progress, but a subsequent loop
            # iteration in the same request must not spin repeatedly on the same lease.
            if int(record.get("revision") or 0) == before_revision:
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
            retained_stage_results = (
                record.get("stage_results")
                if isinstance(record.get("stage_results"), dict)
                else {}
            )
            prior_stage_results = _prior_stage_results_for_stage(
                stage_id,
                retained_stage_results,
                completed,
            )
            customer_name = str(
                identity.get("customer_name") or identity.get("client_name") or ""
            ).strip()
            project_name = str(identity.get("project_name") or "").strip()
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
                # Display metadata is descriptive engagement context, not a scope ID.
                # Carry it through the same authoritative stage context as the canonical
                # identifiers so child/background/final-renderer processes cannot lose
                # values that are already durably persisted in record.identity.
                "customer_name": customer_name,
                "client_name": customer_name,
                "project_name": project_name,
                "assessment_depth": identity["assessment_depth"],
                "report_language": identity["report_language"],
                "human_evidence": deepcopy(record.get("human_evidence") or {}),
                "prior_stage_results": prior_stage_results,
                "recovery_history": deepcopy(record.get("recovery_history") or []),
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
            if stage_id == FINAL_REPORT_STAGE_ID:
                return self._final_report_publication.advance(record, executor, context)
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
