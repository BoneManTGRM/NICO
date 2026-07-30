"use client";

import {useEffect} from "react";
import {ASSESSMENT_FAILURE_EVENT, type AssessmentFailureEvidence} from "./AssessmentApiTransportBridge";

const EXPRESS_ROUTE = /^\/api\/nico\/assessment\/express-run(?:\/[^/?#]+\/status)?$/;
const COMPREHENSIVE_ROUTE = /^\/api\/nico\/assessment\/(?:comprehensive-intake|comprehensive-run\/[^/?#]+(?:\/continue)?)$/;
const LEGACY_RUN_ROUTE = /^\/api\/nico\/assessment\/(?:mid-run|full-run)(?:\/[^/?#]+\/status)?$/;
const TERMINAL_FAILURES = new Set(["blocked", "failed", "error", "interrupted", "rejected"]);
const NORMAL_REVIEW_REASONS = new Set(["pending_human_approval", "internal_approval_required", "pending_internal_approval"]);

type JsonRecord = Record<string, unknown>;
type ProgressRecord = {step?: unknown; status?: unknown; message?: unknown; evidence?: unknown};

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
      message: text(stage.message, stage.reason, stage.summary),
      evidence: stage.evidence,
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
  const progress = progressItems(source.progress || payload.progress || runRecord.progress);
  const failedProgress = terminalProgress(progress)
    || stageResultFailure(runRecord.stage_results)
    || stageResultFailure(source.stage_results)
    || stageResultFailure(payload.stage_results);

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
  const code = bounded(text(
    source.error_code,
    payload.error_code,
    source.failure_code,
    payload.failure_code,
    source.code,
    payload.code,
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
    message: failureReason,
    run_id: runId,
    assessment_type: assessmentTypeForRoute(route, source, payload),
    progress: progressRows(normalizedProgress),
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
