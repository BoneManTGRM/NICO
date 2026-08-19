import type {Phase, Result, Stage} from "./assessmentTypes";

// Keep this order aligned with nico.comprehensive_orchestration_contract.COMPREHENSIVE_STAGES.
// It is used only as a browser display fallback when a response carries a stale/zero
// top-level progress value while the exact run has already advanced to a later stage.
export const COMPREHENSIVE_STAGE_IDS = [
  "authorization_and_scope",
  "immutable_repository_snapshot",
  "repository_and_delivery_evidence",
  "dependency_security_static_analysis",
  "ci_cd_architecture_complexity_velocity",
  "evidence_reconciliation_and_scoring",
  "decision_report_generation",
  "deep_scanner_triage",
  "functional_qa",
  "platform_parity",
  "deployment_and_infrastructure",
  "architecture_and_data_flow",
  "developer_delivery_process",
  "stakeholder_and_business_alignment",
  "requirements_traceability",
  "historical_trends_and_change_failure",
  "six_month_roadmap",
  "staffing_sequencing_and_cost",
  "risk_reduction_and_executive_briefing",
  "final_comprehensive_report_generation",
  "cross_format_truth_verification",
  "human_review_request",
  "client_acceptance_pending",
] as const;

const SUCCESS_STAGE_STATUSES = new Set([
  "complete",
  "completed",
  "success",
  "passed",
  "verified",
  "review_required",
]);

function boundedPercent(value: unknown): number | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  return Math.max(0, Math.min(100, parsed));
}

function stageStatus(value: Stage | undefined): string {
  return String(value?.status || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function completedStageCount(result: Result | null): number {
  if (!result) return 0;
  const top = result as Result & {completed_stages?: unknown};
  const record = result.record as (NonNullable<Result["record"]> & {completed_stages?: unknown}) | undefined;
  const explicitCounts = [top.completed_stages, record?.completed_stages]
    .filter(Array.isArray)
    .map((value) => value.length);

  const projectedResults = record?.stage_results || {};
  let contiguousCompleted = 0;
  for (const stageId of COMPREHENSIVE_STAGE_IDS) {
    if (!SUCCESS_STAGE_STATUSES.has(stageStatus(projectedResults[stageId]))) break;
    contiguousCompleted += 1;
  }

  return Math.max(0, ...explicitCounts, contiguousCompleted);
}

function currentStageIndex(result: Result | null): number {
  const stageId = String(result?.current_stage || result?.record?.current_stage || "").trim();
  return COMPREHENSIVE_STAGE_IDS.indexOf(stageId as (typeof COMPREHENSIVE_STAGE_IDS)[number]);
}

/**
 * Customer-facing progress must never remain at 0% after the durable run has visibly
 * advanced through later canonical stages. The backend remains authoritative; this
 * function takes the highest trustworthy projection available from the same response:
 * top-level display progress, nested canonical progress, explicit completed stages,
 * stage-result completion, or the current canonical stage position.
 *
 * The first active stage receives a 1% liveness floor so a running assessment no longer
 * looks frozen at 0%. This does not mutate canonical evidence or claim a stage complete.
 */
export function progressPercent(
  phase: Phase,
  result: Result | null,
  running: boolean,
): number {
  if (phase === "complete" || phase === "review_required") return 100;

  const top = result as (Result & {
    canonical_progress_percent?: unknown;
    active_stage_progress_percent?: unknown;
  }) | null;
  const serverCandidates = [
    boundedPercent(result?.progress_percent),
    boundedPercent(result?.record?.progress_percent),
    boundedPercent(top?.canonical_progress_percent),
  ].filter((value): value is number => value != null);
  const serverProgress = serverCandidates.length ? Math.max(...serverCandidates) : 0;

  const totalStages = COMPREHENSIVE_STAGE_IDS.length;
  const completed = Math.min(totalStages, completedStageCount(result));
  const completedFloor = (completed / totalStages) * 100;

  const stageIndex = currentStageIndex(result);
  const enteredStageFloor = stageIndex >= 0
    ? (stageIndex / totalStages) * 100
    : 0;
  const activeStageProgress = boundedPercent(top?.active_stage_progress_percent);
  const activeStageInterpolated = stageIndex >= 0 && activeStageProgress != null
    ? ((stageIndex + activeStageProgress / 100) / totalStages) * 100
    : 0;

  let display = Math.max(
    serverProgress,
    completedFloor,
    enteredStageFloor,
    activeStageInterpolated,
  );
  if (running && stageIndex === 0 && display === 0) display = 1;
  if (running && stageIndex < 0 && display === 0) display = 1;

  return Math.round(Math.max(0, Math.min(100, display)) * 100) / 100;
}
