from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Mapping

from nico.comprehensive_approved_delivery_v1 import (
    attach_approved_delivery_package,
    require_new_report_after_evidence_request,
)
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
from nico.comprehensive_engagement_metadata_v1 import (
    display_identity_projection,
    normalize_comprehensive_engagement_metadata,
)
from nico.comprehensive_delivery_authorization_v1 import (
    authorize_accepted_edition,
)
from nico.comprehensive_final_report_background_v1 import (
    FinalReportPublicationCoordinator,
)
from nico.comprehensive_final_report_execution_boundary_v4 import FINAL_REPORT_STAGE_ID
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_pending_artifact_metadata_repair_v1 import (
    repair_pending_findings_csv_alias,
)
from nico.comprehensive_pre_render_scanner_truth_v65 import (
    install_pre_render_authoritative_scanner_truth,
)
from nico.comprehensive_report_flatten_bound_v1 import install_bounded_report_flatten
from nico.comprehensive_review_decision_v1 import (
    assert_expected_review_artifact_identity,
    build_reviewed_edition,
)
from nico.comprehensive_run_record import (
    _record_hash,
    apply_comprehensive_review_decision,
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
)
from nico.comprehensive_run_store import (
    BrowserProjectionBuilder,
    ComprehensiveRunStore,
)
from nico.comprehensive_stage_adapter import CapabilityExecutor, bind_capability_executors
from nico.comprehensive_stage_execution_timeout_v1 import execute_stage_with_timeout
from nico.comprehensive_stage_watchdog_v1 import (
    apply_stage_watchdog,
    rewind_stalled_stage_for_retry,
)

install_background_terminal_ordering()
install_bounded_report_flatten()
install_pre_render_authoritative_scanner_truth()

VERSION = "nico.comprehensive_run_service.v17"

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


def _require_exact_final_report_integrity(record: Mapping[str, Any]) -> None:
    """Block every human-authority transition until final artifacts validate."""

    # Imported at the operation boundary to avoid the controller/service import cycle.
    from nico.comprehensive_api_controller import _canonical_final_report_outputs

    report, _assessment = _canonical_final_report_outputs(dict(record))
    if not report:
        raise ValueError("comprehensive_report_artifact_integrity_invalid")


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
        engagement_metadata: Any = None,
        repository_provider: str = "",
        provider_access_mode: str = "",
        provider_credential_used: bool | None = None,
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
            repository_provider=repository_provider,
            provider_access_mode=provider_access_mode,
            provider_credential_used=provider_credential_used,
        )
        normalized_engagement = normalize_comprehensive_engagement_metadata(
            engagement_metadata
        )
        if normalized_engagement:
            record["engagement_metadata"] = normalized_engagement
            record["integrity_sha256"] = _record_hash(record)
        return self._store.create(record)

    def load(self, run_id: str) -> dict[str, Any]:
        record = self._store.load(run_id)
        if _final_report_status_maintenance_required(record):
            return self.resume(run_id, max_stages=1)
        return record

    def load_read_only(self, run_id: str) -> dict[str, Any]:
        """Load and integrity-validate a run without continuation or maintenance."""

        return self._store.load(run_id)

    def bind_browser_projection_builder(
        self,
        builder: BrowserProjectionBuilder,
    ) -> None:
        """Install the durable request projection after the controller is available."""

        self._store.bind_browser_projection_builder(builder)

    def reserve_public_intake(
        self,
        *,
        run_id: str,
        request_sha256: str,
        payload: Mapping[str, Any],
        now_epoch: float | None = None,
        lease_seconds: float = 300.0,
    ) -> dict[str, Any]:
        return self._store.reserve_public_intake(
            run_id=run_id,
            request_sha256=request_sha256,
            payload=payload,
            now_epoch=now_epoch,
            lease_seconds=lease_seconds,
            updated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    def load_public_intake(self, run_id: str) -> dict[str, Any] | None:
        return self._store.load_public_intake(run_id)

    def heartbeat_public_intake(
        self,
        *,
        run_id: str,
        lease_id: str,
        lease_until_epoch: float,
    ) -> bool:
        return self._store.heartbeat_public_intake(
            run_id=run_id,
            lease_id=lease_id,
            lease_until_epoch=lease_until_epoch,
            updated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    def complete_public_intake(
        self,
        *,
        run_id: str,
        lease_id: str,
        commit_sha: str,
    ) -> bool:
        return self._store.complete_public_intake(
            run_id=run_id,
            lease_id=lease_id,
            commit_sha=commit_sha,
            updated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    def reconcile_public_intake_accepted(
        self,
        *,
        run_id: str,
        request_sha256: str,
        commit_sha: str,
    ) -> bool:
        return self._store.reconcile_public_intake_accepted(
            run_id=run_id,
            request_sha256=request_sha256,
            commit_sha=commit_sha,
            updated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    def fail_public_intake(
        self,
        *,
        run_id: str,
        lease_id: str,
        failure_code: str,
        retryable: bool,
    ) -> bool:
        return self._store.fail_public_intake(
            run_id=run_id,
            lease_id=lease_id,
            failure_code=failure_code,
            retryable=retryable,
            updated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    def load_browser_projection(self, run_id: str) -> dict[str, Any] | None:
        """Load transaction-bound browser status without materializing full evidence."""

        return self._store.load_browser_projection(run_id)

    def resume(
        self,
        run_id: str,
        *,
        max_stages: int | None = None,
    ) -> dict[str, Any]:
        record = self._store.load(run_id)
        if record.get("terminal"):
            repaired = repair_pending_findings_csv_alias(record)
            if repaired != record:
                return self._store.save(
                    repaired,
                    expected_revision=int(record["revision"]),
                )
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
        expected_artifact_identity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = self._store.load(run_id)
        previous_revision = int(record["revision"])
        _require_exact_final_report_integrity(record)
        assert_expected_review_artifact_identity(
            record,
            expected_artifact_identity,
        )
        manifest = build_reviewed_edition(
            record,
            reviewer=reviewer,
            reviewer_role=reviewer_role,
            decision=decision,
            decision_reason=decision_reason,
            decided_at=decided_at,
        )
        if str(decision or "").strip().casefold() == "approved":
            require_new_report_after_evidence_request(record, manifest)
        updated = apply_comprehensive_review_decision(
            record,
            manifest=manifest,
        )
        return self._store.save(updated, expected_revision=previous_revision)

    def authorize_delivery(
        self,
        run_id: str,
        *,
        authorizer: str,
        authorizer_role: str,
        authorization_reason: str,
        authorized_at: str | None = None,
        expected_artifact_identity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = self._store.load(run_id)
        previous_revision = int(record["revision"])
        _require_exact_final_report_integrity(record)
        accepted = record.get("accepted_edition")
        if not isinstance(accepted, Mapping):
            raise ValueError("delivery_authorization_requires_accepted_edition")
        timestamp = str(
            authorized_at
            or datetime.now(UTC).replace(microsecond=0).isoformat()
        ).strip()
        delivery_authorization = authorize_accepted_edition(
            record,
            accepted,
            authorizer=authorizer,
            authorizer_role=authorizer_role,
            authorization_reason=authorization_reason,
            authorized_at=timestamp,
            expected_artifact_identity=expected_artifact_identity,
        )
        authorization_record = deepcopy(dict(record))
        authorization_record["delivery_authorization"] = deepcopy(
            delivery_authorization
        )
        updated = attach_approved_delivery_package(
            authorization_record,
            accepted,
        )
        updated["client_delivery_allowed"] = True
        updated["delivery_authorization"] = deepcopy(delivery_authorization)
        updated["updated_at"] = timestamp
        updated["revision"] = previous_revision + 1
        updated["integrity_sha256"] = _record_hash(updated)
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
            engagement_metadata = (
                deepcopy(record.get("engagement_metadata"))
                if isinstance(record.get("engagement_metadata"), Mapping)
                else {}
            )
            display_identity = display_identity_projection(engagement_metadata)
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
                "engagement_metadata": engagement_metadata,
                **display_identity,
                "access_method": str(engagement_metadata.get("access_method") or ""),
                "authorized_scope": str(
                    engagement_metadata.get("authorized_scope") or ""
                ),
                "human_evidence": deepcopy(record.get("human_evidence") or {}),
                "prior_stage_results": prior_stage_results,
                "recovery_history": deepcopy(record.get("recovery_history") or []),
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
            for field in (
                "repository_provider",
                "provider_access_mode",
                "provider_credential_used",
            ):
                if field in record:
                    context[field] = deepcopy(record[field])
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
