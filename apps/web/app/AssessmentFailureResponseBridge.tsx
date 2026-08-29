"use client";

import {useEffect} from "react";
import {
  ASSESSMENT_FAILURE_EVENT,
  boundedWorkerFailure,
  type AssessmentFailureEvidence,
  type AssessmentWorkerFailureEvidence,
} from "./AssessmentApiTransportBridge";

const EXPRESS_ROUTE = /^\/api\/nico\/assessment\/express-run(?:\/[^/?#]+\/status)?$/;
const COMPREHENSIVE_ROUTE = /^\/api\/nico\/assessment\/(?:comprehensive-intake|comprehensive-run\/[^/?#]+(?:\/continue)?)$/;
const LEGACY_RUN_ROUTE = /^\/api\/nico\/assessment\/(?:mid-run|full-run)(?:\/[^/?#]+\/status)?$/;
const TERMINAL_FAILURES = new Set(["blocked", "failed", "error", "interrupted", "rejected"]);
const NORMAL_REVIEW_REASONS = new Set(["pending_human_approval", "internal_approval_required", "pending_internal_approval"]);
const ARTIFACT_INTEGRITY_STAGE = "final_report_artifact_integrity";
const ARTIFACT_INTEGRITY_CODE = "comprehensive_report_artifact_integrity_invalid";
const ARTIFACT_INTEGRITY_REASON = "The exact final report package failed artifact-integrity validation. Client delivery remains blocked until the preserved package is repaired and revalidated.";

type JsonRecord = Record<string, unknown>;
type ProgressRecord = {
  step?: unknown;
  status?: unknown;
  message?: unknown;
  evidence?: unknown;
  code?: unknown;
  worker?: AssessmentWorkerFailureEvidence | null;
};

function requestUrl(input: RequestInfo | URL): URL | null {
  try {
    if (typeof input === "string") return new URL(input, window.location.origin);
    if (input instanceof URL) return input;
    return new URL(input.url, window.location.origin);
  } catch {
    return null;
  }
}

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as JsonRecord
    : {};
}

function text(...values: unknown[]): string {
  for (const value of values) {
    const normalized = String(value || "").replace(/\s+/g, " ").trim();
    if (normalized) return normalized;
  }
  return "";
}

function bounded(value: unknown, limit: number): string {
  const normalized = text(value);
  return normalized.length <= limit ? normalized : `${normalized.slice(0, Math.max(0, limit - 3))}...`;
}

function progressItems(value: unknown): ProgressRecord[] {
  return Array.isArray(value)
    ? value.filter((item): item is ProgressRecord => Boolean(item) && typeof item === "object")
    : [];
}

function terminalProgress(value: unknown): ProgressRecord | null {
  const items = progressItems(value);
  return [...items].reverse().find((item) => TERMINAL_FAILURES.has(text(item.status).toLowerCase())) || null;
}

function stageResultFailure(value: unknown): ProgressRecord | null {
  const stages = record(value);
  for (const [step, raw] of Object.entries(stages)) {
    const stage = record(raw);
    const status = text(stage.status).toLowerCase();
    if (!TERMINAL_FAILURES.has(status)) continue;
    return {
      step,
      status,
      code: text(stage.error_code, stage.failure_code, stage.code, stage.reason),
      message: text(stage.message, stage.error_message, stage.reason, stage.summary),
      evidence: stage.evidence,
      worker: boundedWorkerFailure(stage, stage.stage_execution),
    };
  }
  return null;
}

function progressRows(value: unknown): AssessmentFailureEvidence["progress"] {
  return progressItems(value).slice(0, 16).map((item) => ({
    step: bounded(item.step, 80) || "unknown_step",
    status: bounded(item.status, 40) || "unknown",
    message: bounded(item.message, 240) || "No bounded stage message was returned.",
  }));
}

function assessmentRoute(pathname: string): boolean {
  return EXPRESS_ROUTE.test(pathname)
    || COMPREHENSIVE_ROUTE.test(pathname)
    || LEGACY_RUN_ROUTE.test(pathname);
}

function assessmentTypeForRoute(pathname: string, source: JsonRecord, payload: JsonRecord): string {
  if (pathname.includes("comprehensive")) return "comprehensive";
  if (pathname.includes("express")) return "express";
  if (pathname.includes("mid-run")) return "mid";
  if (pathname.includes("full-run")) return "full";
  return bounded(source.assessment_type || payload.assessment_type, 40) || "assessment";
}

function originalHttpStatus(response: Response): number {
  const normalized = Number(response.headers.get("X-NICO-Original-Status"));
  return Number.isInteger(normalized) && normalized > 0 ? normalized : response.status;
}

async function normalizeTerminalFailure(response: Response, route: string): Promise<Response | null> {
  // A Comprehensive HTTP/transport failure is never authoritative durable run truth.
  // The canonical controller already retries transient 408/425/429/5xx responses and,
  // once an exact run exists, recovers through the idempotent exact-run status route.
  // Do not convert a temporary proxy/backend error such as 502 into a synthetic terminal
  // assessment failure. A genuine Comprehensive terminal state is normalized only from
  // a successful exact-run response containing persisted terminal evidence.
  if (COMPREHENSIVE_ROUTE.test(route) && !response.ok) return null;

  let payload: JsonRecord = {};
  try {
    payload = record(await response.clone().json());
  } catch {
    return null;
  }

  const detail = record(payload.detail);
  const source = Object.keys(detail).length ? detail : payload;
  const runRecord = record(payload.record || source.record);
  const reportContract = record(source.report_contract || payload.report_contract || runRecord.report_contract);
  const scanner = record(source.scanner || payload.scanner);
  const responseProjection = record(
    source.response_projection
      || payload.response_projection
      || runRecord.response_projection,
  );
  const artifactIntegrityFailure = responseProjection.review_package_invalidated_by_artifact_mismatch === true
    || text(source.delivery_status, payload.delivery_status, runRecord.delivery_status).toLowerCase() === "blocked_artifact_integrity"
    || text(source.approval_status, payload.approval_status).toLowerCase() === "invalidated_artifact_mismatch";
  const progress = progressItems(source.progress || payload.progress || runRecord.progress);
  const failedStageResult = stageResultFailure(runRecord.stage_results)
    || stageResultFailure(source.stage_results)
    || stageResultFailure(payload.stage_results);
  const failedProgress = terminalProgress(progress) || failedStageResult;
  const worker = boundedWorkerFailure(
    failedStageResult?.worker,
    source,
    payload,
    runRecord,
  );

  const lifecycleStatus = text(
    source.status,
    payload.status,
    source.assessment_state,
    payload.assessment_state,
    runRecord.status,
    runRecord.assessment_state,
    failedProgress?.status,
  ).toLowerCase();
  const contractStatus = text(reportContract.status, reportContract.report_contract_status).toLowerCase();
  const contractReason = text(reportContract.reason, reportContract.report_contract_reason).toLowerCase();
  const contractBlocked = TERMINAL_FAILURES.has(contractStatus)
    && !NORMAL_REVIEW_REASONS.has(contractReason);
  const status = TERMINAL_FAILURES.has(lifecycleStatus)
    ? lifecycleStatus
    : contractBlocked ? "blocked" : "";
  if (!status) return null;

  const failedStage = bounded(text(
    artifactIntegrityFailure ? ARTIFACT_INTEGRITY_STAGE : "",
    source.failed_stage,
    source.blocked_stage,
    source.failure_stage,
    payload.failed_stage,
    payload.blocked_stage,
    payload.failure_stage,
    reportContract.failed_stage,
    reportContract.blocked_stage,
    failedProgress?.step,
    source.current_stage,
    payload.current_stage,
    runRecord.current_stage,
    "unknown_stage",
  ), 80);
  const failureReason = bounded(text(
    artifactIntegrityFailure ? ARTIFACT_INTEGRITY_REASON : "",
    source.attention_summary,
    payload.attention_summary,
    source.failure_reason,
    payload.failure_reason,
    source.blocked_reason,
    payload.blocked_reason,
    reportContract.reason,
    reportContract.report_contract_reason,
    scanner.reason,
    failedProgress?.message,
    source.reason,
    payload.reason,
    source.message,
    payload.message,
    payload.error,
    "A required assessment stage failed or was blocked.",
  ), 320);
  const technicalReason = artifactIntegrityFailure
    ? failureReason
    : bounded(text(
      worker?.error,
      source.technical_reason,
      payload.technical_reason,
      source.error_message,
      payload.error_message,
      failureReason,
    ), 1200);
  const code = bounded(text(
    artifactIntegrityFailure ? ARTIFACT_INTEGRITY_CODE : "",
    source.error_code,
    payload.error_code,
    source.failure_code,
    payload.failure_code,
    source.code,
    payload.code,
    failedStageResult?.code,
    reportContract.reason,
    reportContract.report_contract_reason,
    reportContract.status,
    reportContract.report_contract_status,
    `http_${originalHttpStatus(response)}`,
  ), 80);
  const runId = bounded(text(source.run_id, payload.run_id, record(runRecord.identity).run_id), 120);

  const normalizedProgress = [...progress];
  if (!terminalProgress(normalizedProgress)) {
    normalizedProgress.push({step: failedStage, status, message: failureReason});
  }
  const normalized = {
    ...payload,
    ...source,
    status,
    code,
    error_code: code,
    failure_code: code,
    failed_stage: failedStage,
    failure_stage: failedStage,
    current_stage: failedStage,
    failure_reason: failureReason,
    attention_summary: failureReason,
    technical_reason: technicalReason,
    worker_failure: worker,
    run_id: runId,
    progress: normalizedProgress,
    http_status: originalHttpStatus(response),
    human_review_required: true,
    client_ready: false,
    client_delivery_allowed: false,
  };

  const evidence: AssessmentFailureEvidence = {
    http_status: originalHttpStatus(response),
    route,
    status,
    code,
    message: technicalReason,
    run_id: runId,
    assessment_type: assessmentTypeForRoute(route, source, payload),
    progress: progressRows(normalizedProgress),
    worker,
  };
  window.dispatchEvent(new CustomEvent(ASSESSMENT_FAILURE_EVENT, {detail: evidence}));

  return new Response(JSON.stringify(normalized), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store, private",
      "X-NICO-Original-Status": String(originalHttpStatus(response)),
      "X-NICO-Terminal-Failure": "true",
    },
  });
}

export default function AssessmentFailureResponseBridge() {
  useEffect(() => {
    const previousFetch = window.fetch;
    const bridgedFetch: typeof window.fetch = async (input, init) => {
      const target = requestUrl(input);
      if (!target || target.origin !== window.location.origin || !assessmentRoute(target.pathname)) {
        return previousFetch(input, init);
      }

      window.dispatchEvent(new CustomEvent(ASSESSMENT_FAILURE_EVENT, {detail: null}));
      const response = await previousFetch(input, init);
      return await normalizeTerminalFailure(response, target.pathname) || response;
    };

    window.fetch = bridgedFetch;
    return () => {
      if (window.fetch === bridgedFetch) window.fetch = previousFetch;
    };
  }, []);

  return null;
}
