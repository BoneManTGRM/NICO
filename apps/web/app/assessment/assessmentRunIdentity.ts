import type {Result, RunRecord, Stage} from "./assessmentTypes";

export type RunIdentityFallback = {
  runId: string;
  repository?: string;
  customerId?: string;
  projectId?: string;
  commitSha?: string;
  evidenceLedgerId?: string;
};

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

export function preserveRunIdentity(
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

/**
 * Reconcile a bounded status/continuation projection with the last richer
 * projection for the same exact run. This is presentation continuity only:
 * human completion, approval, review decisions, accepted editions, and client
 * delivery authorization are never carried forward from an older projection.
 */
export function preserveRunSnapshot(
  value: Result,
  previous: Result | null,
  fallback: RunIdentityFallback,
): Result {
  const incoming = preserveRunIdentity(value, fallback);
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

  return preserveRunIdentity(
    {
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
    },
    fallback,
  );
}
