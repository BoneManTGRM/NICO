"use client";

import {useEffect} from "react";

export const MID_RECOVERY_STATE_EVENT = "nico:mid-recovery-state";
export const MID_FORCE_LIVE_RETRY_EVENT = "nico:mid-live-status-retry";

const MID_START_PATH = /^\/(?:api\/nico\/)?assessment\/mid-run$/;
const MID_STATUS_PATH = /^\/(?:api\/nico\/)?assessment\/mid-run\/([^/]+)\/status$/;
const LIVE_RETRY_COUNT = 2;
const LIVE_TIMEOUT_MS = 12_000;
const LIVE_RETRY_DELAY_MS = 1_000;
const LIVE_BACKOFF_BASE_MS = 3_000;
const LIVE_BACKOFF_MAX_MS = 30_000;
const PROXY_CONTRACT_CODES = new Set([
  "assessment_proxy_route_not_allowed",
  "assessment_backend_not_configured",
]);

type JsonRecord = Record<string, unknown>;
type FailureEvidence = {
  httpStatus: number;
  code: string;
  message: string;
  contractMismatch: boolean;
};
type RunState = {
  consecutiveFailures: number;
  nextProbeAt: number;
  lastGood?: JsonRecord;
  lastSuccessAt?: string;
  lastFailure?: FailureEvidence;
};

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function requestUrl(input: RequestInfo | URL): URL | null {
  try {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    return new URL(raw, window.location.origin);
  } catch {
    return null;
  }
}

function bodyPayload(init?: RequestInit): JsonRecord {
  if (typeof init?.body !== "string") return {};
  try {
    const parsed = JSON.parse(init.body);
    return parsed && typeof parsed === "object" ? parsed as JsonRecord : {};
  } catch {
    return {};
  }
}

async function jsonPayload(response: Response): Promise<JsonRecord | null> {
  try {
    const parsed = await response.clone().json();
    return parsed && typeof parsed === "object" ? parsed as JsonRecord : null;
  } catch {
    return null;
  }
}

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function responseFromPayload(payload: JsonRecord, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {"Content-Type": "application/json", "Cache-Control": "no-store"},
  });
}

function failureFromResponse(response: Response, payload: JsonRecord | null): FailureEvidence {
  const detail = record(payload?.detail);
  const code = String(detail.code || payload?.code || `http_${response.status}`).slice(0, 100);
  const message = String(
    detail.message
    || payload?.message
    || payload?.error
    || `Live status request failed with HTTP ${response.status}.`,
  ).replace(/\s+/g, " ").trim().slice(0, 360);
  return {
    httpStatus: response.status,
    code,
    message,
    contractMismatch: PROXY_CONTRACT_CODES.has(code)
      || (response.status === 404 && /route|endpoint|not configured/i.test(message)),
  };
}

function scannerIdentity(payload: JsonRecord | undefined) {
  const scanner = record(payload?.scanner);
  const evidence = record(payload?.scanner_evidence);
  return {
    scanId: String(scanner.scan_id || evidence.scan_id || payload?.scan_id || ""),
    scannerStatus: String(scanner.status || evidence.scanner_status || evidence.status || ""),
    activeTool: String(scanner.active_tool || evidence.active_tool || ""),
    heartbeatAt: String(scanner.heartbeat_at || evidence.heartbeat_at || payload?.heartbeat_at || ""),
  };
}

function publishRecoveryState(
  runId: string,
  status: "healthy" | "temporarily_unreachable" | "recovery_required" | "deployment_mismatch",
  payload: JsonRecord | undefined,
  state: RunState,
) {
  const scanner = scannerIdentity(payload);
  const transport = record(payload?.status_transport);
  const detail = {
    status,
    run_id: runId,
    scan_id: scanner.scanId,
    scanner_status: scanner.scannerStatus,
    active_tool: scanner.activeTool,
    heartbeat_at: scanner.heartbeatAt,
    current_stage: String(payload?.current_stage || ""),
    progress_percent: Number(payload?.progress_percent || 0),
    recovery_required: Boolean(payload?.recovery_required) || status === "recovery_required",
    recovery_path: String(payload?.recovery_path || "/operations/recovery"),
    last_success_at: state.lastSuccessAt || "",
    next_retry_at: state.nextProbeAt ? new Date(state.nextProbeAt).toISOString() : "",
    consecutive_failures: state.consecutiveFailures,
    http_status: state.lastFailure?.httpStatus || Number(transport.http_status || 0),
    code: state.lastFailure?.code || String(payload?.code || transport.code || ""),
    message: state.lastFailure?.message || "",
    duplicate_start_allowed: false,
  };
  try {
    window.sessionStorage.setItem("nico.mid.recovery_state", JSON.stringify(detail));
  } catch {
    // The live event remains available when browser storage is unavailable.
  }
  window.dispatchEvent(new CustomEvent(MID_RECOVERY_STATE_EVENT, {detail}));
}

function backoffMs(consecutiveFailures: number) {
  return Math.min(
    LIVE_BACKOFF_BASE_MS * (2 ** Math.max(0, consecutiveFailures - 1)),
    LIVE_BACKOFF_MAX_MS,
  );
}

function preservedResponse(runId: string, state: RunState): Response {
  const output: JsonRecord = state.lastGood ? structuredClone(state.lastGood) : {
    status: "running",
    run_id: runId,
    assessment_type: "mid",
    service_tier: "mid",
    current_stage: "status_recovery",
    progress_percent: 18,
    progress: [],
    human_review_required: true,
    client_ready: false,
  };
  const progress = Array.isArray(output.progress)
    ? output.progress.filter((item) => item && typeof item === "object") as JsonRecord[]
    : [];
  const mismatch = Boolean(state.lastFailure?.contractMismatch);
  const message = mismatch
    ? `The web deployment cannot reach the required Mid live-status contract for exact run ${runId}. The run remains preserved; verify the Railway backend deployment before retrying or opening Recovery.`
    : `Live status is temporarily unavailable. Exact run ${runId} remains preserved; NICO will retry with bounded backoff without starting a duplicate assessment.`;
  const activeIndex = progress.findIndex((item) => ["queued", "running", "pending", "planned"].includes(String(item.status || "").toLowerCase()));
  const replacement = {
    ...(activeIndex >= 0 ? progress[activeIndex] : {}),
    step: activeIndex >= 0 ? progress[activeIndex].step : String(output.current_stage || "status_recovery"),
    status: "running",
    message,
  };
  if (activeIndex >= 0) progress[activeIndex] = replacement;
  else progress.push(replacement);
  output.status = "running";
  output.run_id = String(output.run_id || runId);
  output.progress = progress;
  output.status_transport = {
    status: mismatch ? "backend_contract_mismatch" : "live_status_temporarily_unreachable",
    retry_count: LIVE_RETRY_COUNT,
    consecutive_failures: state.consecutiveFailures,
    next_retry_at: new Date(state.nextProbeAt).toISOString(),
    last_success_at: state.lastSuccessAt || "",
    http_status: state.lastFailure?.httpStatus || 0,
    code: state.lastFailure?.code || "browser_transport_interrupted",
    duplicate_start_allowed: false,
    recovery_required_if_stale: true,
  };
  publishRecoveryState(
    runId,
    mismatch ? "deployment_mismatch" : "temporarily_unreachable",
    output,
    state,
  );
  return responseFromPayload(output);
}

export default function AssessmentMidLiveStatusTransport() {
  useEffect(() => {
    const previousFetch = window.fetch.bind(window);
    const stateByRun = new Map<string, RunState>();

    const stateFor = (runId: string) => {
      const existing = stateByRun.get(runId);
      if (existing) return existing;
      const created: RunState = {consecutiveFailures: 0, nextProbeAt: 0};
      stateByRun.set(runId, created);
      return created;
    };

    const forceRetry = (event: Event) => {
      const detail = (event as CustomEvent<{run_id?: string}>).detail || {};
      const runId = String(detail.run_id || "");
      if (!runId) return;
      const state = stateFor(runId);
      state.nextProbeAt = 0;
    };
    window.addEventListener(MID_FORCE_LIVE_RETRY_EVENT, forceRetry);

    const transportFetch: typeof window.fetch = async (input, init) => {
      const url = requestUrl(input);
      if (!url) return previousFetch(input, init);
      const method = String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();

      if (MID_START_PATH.test(url.pathname) && method === "POST") {
        const response = await previousFetch(input, init);
        const payload = await jsonPayload(response);
        const runId = String(payload?.run_id || "");
        if (response.ok && payload && runId.startsWith("midrun_")) {
          const state = stateFor(runId);
          state.lastGood = payload;
          state.lastSuccessAt = new Date().toISOString();
          state.consecutiveFailures = 0;
          state.nextProbeAt = 0;
          publishRecoveryState(runId, "healthy", payload, state);
        }
        return response;
      }

      const match = MID_STATUS_PATH.exec(url.pathname);
      if (!match || method !== "POST") return previousFetch(input, init);

      const runId = decodeURIComponent(match[1]);
      const state = stateFor(runId);
      if (Date.now() < state.nextProbeAt) return preservedResponse(runId, state);

      const body = bodyPayload(init);
      const prefix = url.pathname.startsWith("/api/nico/") ? "/api/nico" : "";
      const liveUrl = new URL(`${prefix}/assessment/mid-run/${encodeURIComponent(runId)}/live-status`, url.origin);
      const customerId = String(body.customer_id || "");
      const projectId = String(body.project_id || "");
      if (customerId) liveUrl.searchParams.set("customer_id", customerId);
      if (projectId) liveUrl.searchParams.set("project_id", projectId);

      let exactRunNotFound = false;
      for (let attempt = 1; attempt <= LIVE_RETRY_COUNT; attempt += 1) {
        try {
          const liveResponse = await previousFetch(liveUrl, {
            method: "GET",
            cache: "no-store",
            credentials: "same-origin",
            signal: AbortSignal.timeout(LIVE_TIMEOUT_MS),
          });
          const livePayload = await jsonPayload(liveResponse);
          if (liveResponse.ok && livePayload) {
            state.lastGood = livePayload;
            state.lastSuccessAt = new Date().toISOString();
            state.consecutiveFailures = 0;
            state.nextProbeAt = 0;
            if (livePayload.recovery_required === true) {
              state.lastFailure = undefined;
              publishRecoveryState(runId, "recovery_required", livePayload, state);
              return liveResponse;
            }
            if (livePayload.live_status_degraded === true) {
              state.consecutiveFailures = 1;
              state.nextProbeAt = Date.now() + backoffMs(state.consecutiveFailures);
              state.lastFailure = {
                httpStatus: 0,
                code: String(livePayload.code || "mid_live_status_projection_degraded"),
                message: "NICO returned a bounded read-only lifecycle projection while the full live-status projection was unavailable.",
                contractMismatch: false,
              };
              publishRecoveryState(runId, "temporarily_unreachable", livePayload, state);
              return liveResponse;
            }
            state.lastFailure = undefined;
            publishRecoveryState(runId, "healthy", livePayload, state);
            if (livePayload.continuation_required === true) {
              const continuation = await previousFetch(input, init);
              const continuationPayload = await jsonPayload(continuation);
              if (continuation.ok && continuationPayload) {
                state.lastGood = continuationPayload;
                state.lastSuccessAt = new Date().toISOString();
              }
              return continuation;
            }
            return liveResponse;
          }

          const failure = failureFromResponse(liveResponse, livePayload);
          state.lastFailure = failure;
          if (liveResponse.status === 404 && !failure.contractMismatch) {
            exactRunNotFound = true;
            break;
          }
          if (failure.contractMismatch) break;
        } catch {
          state.lastFailure = {
            httpStatus: 0,
            code: "browser_transport_interrupted",
            message: "The browser could not complete the Mid live-status request.",
            contractMismatch: false,
          };
        }
        if (attempt < LIVE_RETRY_COUNT) await sleep(LIVE_RETRY_DELAY_MS);
      }

      if (exactRunNotFound) return previousFetch(input, init);
      state.consecutiveFailures += 1;
      state.nextProbeAt = Date.now() + backoffMs(state.consecutiveFailures);
      return preservedResponse(runId, state);
    };

    window.fetch = transportFetch;
    return () => {
      window.removeEventListener(MID_FORCE_LIVE_RETRY_EVENT, forceRetry);
      if (window.fetch === transportFetch) window.fetch = previousFetch;
    };
  }, []);

  return null;
}
