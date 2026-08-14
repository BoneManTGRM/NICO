import type {
  Assessment,
  Report,
  Result,
  RunRecord,
  Stage,
} from "./assessmentTypes";

export type RunIdentityFallback = {
  runId: string;
  repository?: string;
  customerId?: string;
  projectId?: string;
  commitSha?: string;
  evidenceLedgerId?: string;
};

const RUN_SNAPSHOT_CACHE_LIMIT = 4;
const runSnapshots = new Map<string, Result>();

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function runIdFor(value: Result | null): string {
  const record = objectRecord(value?.record);
  const identity = objectRecord(record.identity);
  return String(value?.run_id || identity.run_id || "").trim();
}

function sameRunIdentity(incoming: Result, previous: Result): boolean {
  const incomingRunId = runIdFor(incoming);
  const previousRunId = runIdFor(previous);
  return Boolean(incomingRunId && previousRunId && incomingRunId === previousRunId);
}

function finiteProgress(value: unknown): number | null {
  const numeric = Number(value);
  return Number.isFinite(numeric)
    ? Math.max(0, Math.min(100, numeric))
    : null;
}

function progressFor(value: Result | null): number | null {
  return (
    finiteProgress(value?.progress_percent) ??
    finiteProgress(value?.record?.progress_percent)
  );
}

function meaningfulStage(value: unknown): string {
  const stage = String(value || "").trim();
  const normalized = stage.toLowerCase().replace(/[\s-]+/g, "_");
  return stage && !["unknown", "unknown_stage", "unavailable", "none", "null"].includes(normalized)
    ? stage
    : "";
}

function currentStageFor(value: Result | null): string {
  return (
    meaningfulStage(value?.current_stage) ||
    meaningfulStage(value?.record?.current_stage)
  );
}

function reportContinuity(value: Report | undefined): Report | undefined {
  if (!value) {
    return undefined;
  }
  const continuity: Report = {};
  for (const key of [
    "pdf_filename",
    "pdf_error",
    "report_id",
    "pdf_sha256",
    "canonical_truth_sha256",
    "assessment_state",
    "markdown_available",
    "html_available",
    "json_available",
    "pdf_available",
    "artifact_delivery",
    "response_bounded",
  ] as const) {
    if (value[key] !== undefined) {
      continuity[key] = value[key] as never;
    }
  }
  return Object.keys(continuity).length ? continuity : undefined;
}

function assessmentContinuity(
  value: Assessment | undefined,
): Assessment | undefined {
  if (!value) {
    return undefined;
  }
  const source = value as Record<string, unknown>;
  const continuity: Assessment = {};
  for (const key of [
    "technical_score",
    "canonical_evidence_adjusted_score",
    "evidence_adjusted_score",
    "maturity_signal",
    "evidence_coverage",
    "evidence_completion_contract",
  ]) {
    if (source[key] !== undefined) {
      continuity[key] = source[key];
    }
  }
  return Object.keys(continuity).length ? continuity : undefined;
}

function stageContinuity(value: Stage): Stage {
  return {
    ...(value.status !== undefined ? {status: value.status} : {}),
    ...(value.message !== undefined ? {message: value.message} : {}),
    ...(value.summary !== undefined ? {summary: value.summary} : {}),
    ...(assessmentContinuity(value.assessment)
      ? {assessment: assessmentContinuity(value.assessment)}
      : {}),
    ...(reportContinuity(value.report_package)
      ? {report_package: reportContinuity(value.report_package)}
      : {}),
    ...(reportContinuity(value.reports)
      ? {reports: reportContinuity(value.reports)}
      : {}),
  };
}

function mergeStageResults(
  previous: Record<string, Stage> | undefined,
  incoming: Record<string, Stage> | undefined,
): Record<string, Stage> {
  const merged: Record<string, Stage> = {...(previous || {})};
  for (const [stageId, stage] of Object.entries(incoming || {})) {
    merged[stageId] = {
      ...(previous?.[stageId] || {}),
      ...stage,
    };
  }
  return merged;
}

function normalizeRunIdentity(
  value: Result,
  fallback: RunIdentityFallback,
): Result {
  const record = objectRecord(value.record);
  const identity = objectRecord(record.identity);
  const runId = String(
    value.run_id || identity.run_id || fallback.runId || "",
  ).trim();
  const repository = String(
    value.repository || identity.repository || fallback.repository || "",
  ).trim();
  const customerId = String(
    value.customer_id ||
      identity.customer_id ||
      fallback.customerId ||
      "default_customer",
  ).trim();
  const projectId = String(
    value.project_id ||
      identity.project_id ||
      fallback.projectId ||
      "default_project",
  ).trim();
  const commitSha = String(
    value.commit_sha ||
      identity.commit_sha ||
      value.repository_snapshot?.commit_sha ||
      fallback.commitSha ||
      "",
  ).trim();
  const evidenceLedgerId = String(
    value.evidence_ledger_id ||
      identity.evidence_ledger_id ||
      fallback.evidenceLedgerId ||
      "",
  ).trim();

  return {
    ...value,
    ...(runId ? {run_id: runId} : {}),
    ...(repository ? {repository} : {}),
    ...(customerId ? {customer_id: customerId} : {}),
    ...(projectId ? {project_id: projectId} : {}),
    ...(commitSha ? {commit_sha: commitSha} : {}),
    ...(evidenceLedgerId ? {evidence_ledger_id: evidenceLedgerId} : {}),
    record: {
      ...record,
      identity: {
        ...identity,
        ...(runId ? {run_id: runId} : {}),
        ...(repository ? {repository} : {}),
        ...(customerId ? {customer_id: customerId} : {}),
        ...(projectId ? {project_id: projectId} : {}),
        ...(commitSha ? {commit_sha: commitSha} : {}),
        ...(evidenceLedgerId ? {evidence_ledger_id: evidenceLedgerId} : {}),
      },
    },
  };
}

function reconcileSameRunSnapshot(
  incoming: Result,
  previous: Result | null,
): Result {
  if (!previous || !sameRunIdentity(incoming, previous)) {
    return incoming;
  }

  const previousRecord = previous.record || {};
  const incomingRecord = incoming.record || {};
  const previousProgress = progressFor(previous);
  const incomingProgress = progressFor(incoming);
  const progressPercent = previousProgress == null
    ? incomingProgress
    : incomingProgress == null
      ? previousProgress
      : Math.max(previousProgress, incomingProgress);
  const currentStage = currentStageFor(incoming) || currentStageFor(previous);
  const stageResults = mergeStageResults(
    previousRecord.stage_results,
    incomingRecord.stage_results,
  );

  const safePrevious: Partial<Result> = {
    assessment_state: previous.assessment_state,
    canonical_truth_sha256: previous.canonical_truth_sha256,
    service_id: previous.service_id,
    status: previous.status,
    current_stage: previous.current_stage,
    progress_percent: previous.progress_percent,
    progress: previous.progress,
    assessment: previous.assessment,
    reports: previous.reports,
    repository_snapshot: previous.repository_snapshot,
    scanner: previous.scanner,
    scanner_evidence: previous.scanner_evidence,
    persistence: previous.persistence,
    survives_container_replacement_verified:
      previous.survives_container_replacement_verified,
    human_review_required: previous.human_review_required,
  };
  const safePreviousRecord: Partial<RunRecord> = {
    assessment_state: previousRecord.assessment_state,
    canonical_truth_sha256: previousRecord.canonical_truth_sha256,
    assessment_package_complete: previousRecord.assessment_package_complete,
    status: previousRecord.status,
    current_stage: previousRecord.current_stage,
    progress_percent: previousRecord.progress_percent,
    stage_results: previousRecord.stage_results,
    human_review_required: previousRecord.human_review_required,
  };

  return {
    ...safePrevious,
    ...incoming,
    ...(currentStage ? {current_stage: currentStage} : {}),
    ...(progressPercent != null ? {progress_percent: progressPercent} : {}),
    record: {
      ...safePreviousRecord,
      ...incomingRecord,
      ...(currentStage ? {current_stage: currentStage} : {}),
      ...(progressPercent != null ? {progress_percent: progressPercent} : {}),
      ...(Object.keys(stageResults).length ? {stage_results: stageResults} : {}),
      identity: incomingRecord.identity,
    },
  };
}

function continuitySnapshot(value: Result): Result {
  const record = value.record || {};
  const stageResults = Object.fromEntries(
    Object.entries(record.stage_results || {}).map(([stageId, stage]) => [
      stageId,
      stageContinuity(stage),
    ]),
  );
  const activeExecution = objectRecord(value.active_stage_execution);

  return {
    run_id: value.run_id,
    repository: value.repository,
    commit_sha: value.commit_sha,
    evidence_ledger_id: value.evidence_ledger_id,
    customer_id: value.customer_id,
    project_id: value.project_id,
    assessment_state: value.assessment_state,
    canonical_truth_sha256: value.canonical_truth_sha256,
    service_id: value.service_id,
    status: value.status,
    current_stage: value.current_stage,
    progress_percent: value.progress_percent,
    progress: value.progress?.map((item) => ({
      step: item.step,
      status: item.status,
      message: item.message,
    })),
    assessment: assessmentContinuity(value.assessment),
    reports: reportContinuity(value.reports),
    repository_snapshot: value.repository_snapshot,
    scanner: value.scanner,
    scanner_evidence: value.scanner_evidence,
    persistence: value.persistence,
    survives_container_replacement_verified:
      value.survives_container_replacement_verified,
    human_review_required: value.human_review_required,
    ...(Object.keys(activeExecution).length
      ? {active_stage_execution: {...activeExecution}}
      : {}),
    record: {
      assessment_state: record.assessment_state,
      canonical_truth_sha256: record.canonical_truth_sha256,
      assessment_package_complete: record.assessment_package_complete,
      status: record.status,
      current_stage: record.current_stage,
      progress_percent: record.progress_percent,
      ...(Object.keys(stageResults).length ? {stage_results: stageResults} : {}),
      identity: record.identity,
      human_review_required: record.human_review_required,
    },
  };
}

function cacheRunSnapshot(value: Result): void {
  const runId = runIdFor(value);
  if (!runId) {
    return;
  }
  runSnapshots.delete(runId);
  runSnapshots.set(runId, continuitySnapshot(value));
  while (runSnapshots.size > RUN_SNAPSHOT_CACHE_LIMIT) {
    const oldest = runSnapshots.keys().next().value;
    if (!oldest) {
      break;
    }
    runSnapshots.delete(oldest);
  }
}

/**
 * Preserve exact identity and monotonic presentation state for bounded responses
 * belonging to the same run. The cache retains only small status/report metadata;
 * scanner evidence, report bodies, PDF bytes, human decisions, approval state,
 * and client-delivery authorization are never cached or carried forward.
 */
export function preserveRunIdentity(
  value: Result,
  fallback: RunIdentityFallback,
): Result {
  const incoming = normalizeRunIdentity(value, fallback);
  const previous = runSnapshots.get(runIdFor(incoming)) || null;
  const reconciled = normalizeRunIdentity(
    reconcileSameRunSnapshot(incoming, previous),
    fallback,
  );
  cacheRunSnapshot(reconciled);
  return reconciled;
}

export function preserveRunSnapshot(
  value: Result,
  previous: Result | null,
  fallback: RunIdentityFallback,
): Result {
  const incoming = normalizeRunIdentity(value, fallback);
  const reconciled = normalizeRunIdentity(
    reconcileSameRunSnapshot(incoming, previous),
    fallback,
  );
  cacheRunSnapshot(reconciled);
  return reconciled;
}
