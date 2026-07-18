"use client";

import {useEffect} from "react";

export const EXPRESS_RECOVERY_STATE_EVENT = "nico:express-recovery-state";
export const EXPRESS_RECOVERY_STORAGE_KEY = "nico.express.recovery_state";

const EXPRESS_STATUS_PATH = /^\/(?:api\/nico\/)?assessment\/express-run\/([^/?#]+)\/status$/;
const FAILURE_LIMIT = 3;
const FAILURE_WINDOW_MS = 30_000;
const ACTIVE_STATUSES = new Set(["queued", "running", "pending", "planned", "starting"]);

type JsonRecord = Record<string, unknown>;
type FailureState = {count: number; firstSeenAt: number};

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function requestUrl(input: RequestInfo | URL): URL | null {
  try {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    return new URL(raw, window.location.origin);
  } catch {
    return null;
  }
}

async function payloadFrom(response: Response): Promise<JsonRecord | null> {
  try {
    const value = await response.clone().json();
    return value && typeof value === "object" ? value as JsonRecord : null;
  } catch {
    return null;
  }
}

function responseFrom(payload: JsonRecord): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: {"Content-Type": "application/json", "Cache-Control": "no-store"},
  });
}

function isMissingExactRun(payload: JsonRecord | null): boolean {
  if (!payload) return false;
  const transport = record(payload.status_transport);
  const detail = record(payload.detail);
  const status = Number(transport.http_status || detail.http_status || 0);
  const code = String(transport.code || detail.code || payload.code || "").toLowerCase();
  return status === 404 || code === "http_404" || code === "run_not_found" || code === "assessment_run_not_found";
}

function persistenceTruth(payload: JsonRecord): {recorded: boolean; durable: boolean; adapter: string} {
  const persistence = record(payload.persistence);
  return {
    recorded: persistence.recorded === true,
    durable: persistence.durable === true,
    adapter: String(persistence.adapter || "unknown"),
  };
}

function publish(detail: JsonRecord) {
  try {
    window.sessionStorage.setItem(EXPRESS_RECOVERY_STORAGE_KEY, JSON.stringify(detail));
  } catch {
    // The visible event remains authoritative when storage is unavailable.
  }
  window.dispatchEvent(new CustomEvent(EXPRESS_RECOVERY_STATE_EVENT, {detail}));
}

function clear(runId: string) {
  try {
    const current = JSON.parse(window.sessionStorage.getItem(EXPRESS_RECOVERY_STORAGE_KEY) || "{}") as JsonRecord;
    if (!runId || String(current.run_id || "") === runId) window.sessionStorage.removeItem(EXPRESS_RECOVERY_STORAGE_KEY);
  } catch {
    // A healthy event still clears the mounted control.
  }
  window.dispatchEvent(new CustomEvent(EXPRESS_RECOVERY_STATE_EVENT, {detail: {status: "healthy", run_id: runId}}));
}

function recoveryProjection(payload: JsonRecord, runId: string, state: FailureState): JsonRecord {
  const output = structuredClone(payload);
  const persistence = persistenceTruth(output);
  const currentStage = String(output.current_stage || "status_recovery");
  const message = persistence.durable
    ? `Exact run ${runId} is missing from the live status route after bounded checks. NICO stopped automatic continuation and requires exact-run reconciliation before any replacement can be considered.`
    : `Exact run ${runId} returned HTTP 404 and its record is not durable. NICO stopped automatic continuation instead of displaying an indefinite running state. Recover or explicitly close this run before starting another assessment.`;
  const items = Array.isArray(output.progress)
    ? output.progress.filter((item) => item && typeof item === "object") as JsonRecord[]
    : [];
  const activeIndex = items.findIndex((item) => ACTIVE_STATUSES.has(String(item.status || "").toLowerCase()));
  const blockedStep = {
    ...(activeIndex >= 0 ? items[activeIndex] : {}),
    step: activeIndex >= 0 ? String(items[activeIndex].step || currentStage) : currentStage,
    status: "blocked",
    message,
    evidence: {
      ...record(activeIndex >= 0 ? items[activeIndex].evidence : {}),
      code: "express_exact_run_recovery_required",
      original_http_status: 404,
      exact_run_terminal_evidence: false,
      terminal_state_written: false,
      durable_record: persistence.durable,
    },
  };
  if (activeIndex >= 0) items[activeIndex] = blockedStep;
  else items.push(blockedStep);

  output.status = "blocked";
  output.run_id = runId;
  output.failure_stage = currentStage;
  output.current_stage = "recovery_required";
  output.progress = items;
  output.recovery_required = true;
  output.recovery_path = "/operations/recovery";
  output.status_read_only = true;
  output.terminal_state_written = false;
  output.duplicate_start_allowed = false;
  output.human_review_required = true;
  output.client_ready = false;
  output.status_transport = {
    ...record(output.status_transport),
    status: "recovery_required",
    http_status: 404,
    code: "express_exact_run_recovery_required",
    consecutive_failures: state.count,
    bounded_failure_limit: FAILURE_LIMIT,
    exact_run_terminal_evidence: false,
    terminal_state_written: false,
    duplicate_start_allowed: false,
    recovery_required: true,
  };

  publish({
    status: "recovery_required",
    tier: "express",
    run_id: runId,
    scan_id: String(record(output.scanner).scan_id || record(output.scanner_evidence).scan_id || ""),
    current_stage: currentStage,
    progress_percent: Number(output.progress_percent || 0),
    consecutive_failures: state.count,
    http_status: 404,
    code: "express_exact_run_recovery_required",
    message,
    recovery_required: true,
    recovery_path: "/operations/recovery",
    persistence_recorded: persistence.recorded,
    persistence_durable: persistence.durable,
    persistence_adapter: persistence.adapter,
  });
  return output;
}

export default function AssessmentExpressRecoveryGuard() {
  useEffect(() => {
    const previousFetch = window.fetch.bind(window);
    const failures = new Map<string, FailureState>();

    const guardedFetch: typeof window.fetch = async (input, init) => {
      const response = await previousFetch(input, init);
      const url = requestUrl(input);
      const match = url ? EXPRESS_STATUS_PATH.exec(url.pathname) : null;
      if (!match) return response;

      const runId = decodeURIComponent(match[1]);
      const payload = await payloadFrom(response);
      if (!isMissingExactRun(payload)) {
        failures.delete(runId);
        if (response.ok && payload) clear(runId);
        return response;
      }

      const now = Date.now();
      const existing = failures.get(runId) || {count: 0, firstSeenAt: now};
      const next = {count: existing.count + 1, firstSeenAt: existing.firstSeenAt};
      failures.set(runId, next);
      const persistence = persistenceTruth(payload || {});
      const exhausted = next.count >= FAILURE_LIMIT || now - next.firstSeenAt >= FAILURE_WINDOW_MS;

      // A 404 combined with an explicitly non-durable record cannot recover through
      // additional browser polling. Escalate immediately; otherwise allow a small
      // bounded window for deployment propagation or transient route inconsistency.
      if (!persistence.durable || exhausted) {
        return responseFrom(recoveryProjection(payload || {}, runId, next));
      }
      return response;
    };

    window.fetch = guardedFetch;
    return () => {
      if (window.fetch === guardedFetch) window.fetch = previousFetch;
    };
  }, []);

  return null;
}

export {FAILURE_LIMIT, FAILURE_WINDOW_MS, isMissingExactRun, persistenceTruth, recoveryProjection};
