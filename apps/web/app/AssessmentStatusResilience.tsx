"use client";

import {useEffect} from "react";

const STATUS_MAX_CONSECUTIVE_FAILURES = 8;
const STATUS_RETRY_BASE_MS = 1500;
const STATUS_RETRY_MAX_MS = 12000;
const RETRYABLE_HTTP_STATUSES = new Set([408, 425, 429, 500, 502, 503, 504]);
const TERMINAL_STATUSES = new Set(["blocked", "failed", "error", "interrupted", "rejected"]);
const START_PATH = /^\/(?:api\/nico\/)?assessment\/(?:express-run|mid-run|full-run)$/;
const MID_START_PATH = /^\/(?:api\/nico\/)?assessment\/mid-run$/;
const STATUS_PATH = /^\/(?:api\/nico\/)?assessment\/(?:express-run|mid-run|full-run)\/([^/]+)\/status$/;
const MID_ACTIVE_RUN_KEY = "nico.mid.active_run";

const STAGE_PROGRESS: Record<string, number> = {
  request_accepted: 4,
  repo_evidence: 18,
  repository_evidence: 18,
  scanner_worker: 18,
  scanner_reconciliation: 62,
  evidence_attachment: 62,
  accuracy_review: 66,
  scoring: 74,
  score_reconciliation: 76,
  reports: 86,
  report_generation: 86,
  approval_request: 94,
  truth_and_review_gates: 96,
  complete: 100,
};

type JsonRecord = Record<string, unknown>;
type ProgressRecord = {step?: unknown; status?: unknown; message?: unknown; evidence?: unknown};

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function retryDelay(attempt: number) {
  return Math.min(STATUS_RETRY_BASE_MS * (2 ** Math.max(0, attempt - 1)), STATUS_RETRY_MAX_MS);
}

function requestUrl(input: RequestInfo | URL): URL | null {
  try {
    const value = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    return new URL(value, window.location.origin);
  } catch {
    return null;
  }
}

function requestBody(input: RequestInfo | URL, init?: RequestInit): JsonRecord {
  const raw = init?.body;
  if (typeof raw !== "string") return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed as JsonRecord : {};
  } catch {
    return {};
  }
}

function boundedNumber(value: unknown): number | null {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : null;
}

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function progressItems(payload: JsonRecord): ProgressRecord[] {
  return Array.isArray(payload.progress)
    ? payload.progress.filter((item): item is ProgressRecord => Boolean(item) && typeof item === "object")
    : [];
}

function activeProgress(payload: JsonRecord): ProgressRecord | null {
  const active = new Set(["queued", "running", "pending", "planned", "starting"]);
  const items = progressItems(payload);
  return items.find((item) => active.has(String(item.status || "").toLowerCase())) || items[items.length - 1] || null;
}

function scannerProgress(payload: JsonRecord): number | null {
  const scanner = record(payload.scanner);
  const scannerEvidence = record(payload.scanner_evidence);
  const active = activeProgress(payload);
  const activeEvidence = record(active?.evidence);
  const explicit = boundedNumber(
    scanner.progress_percent
    ?? scannerEvidence.scanner_progress_percent
    ?? activeEvidence.scanner_progress_percent
    ?? activeEvidence.progress_percent,
  );
  if (explicit !== null) return explicit;

  const requested = Array.isArray(scanner.tools_requested)
    ? scanner.tools_requested.map(String)
    : Array.isArray(activeEvidence.tools_requested)
      ? activeEvidence.tools_requested.map(String)
      : [];
  const completed = Array.isArray(scanner.tools_run)
    ? scanner.tools_run.map(String)
    : Array.isArray(activeEvidence.tools_run)
      ? activeEvidence.tools_run.map(String)
      : [];
  const activeTool = String(scanner.active_tool || activeEvidence.active_tool || "");
  if (!requested.length) return null;
  const activeIndex = activeTool ? requested.indexOf(activeTool) : -1;
  const fractional = activeIndex >= 0
    ? (activeIndex + 0.35) / requested.length
    : completed.length / requested.length;
  return Math.max(0, Math.min(100, Math.round(fractional * 100)));
}

function normalizedProgress(payload: JsonRecord): JsonRecord {
  const output: JsonRecord = structuredClone(payload);
  const status = String(output.status || "").toLowerCase();
  const active = activeProgress(output);
  const step = String(active?.step || output.current_stage || "");
  const scanStatus = String(record(output.scanner).status || record(output.scanner_evidence).scanner_status || "").toLowerCase();
  const scanPercent = scannerProgress(output);

  const reportComplete = String(output.report_generation_status || "").toLowerCase() === "complete";
  const approval = record(output.approval_request);
  const fullApproval = record(output.approval);
  const finalReady = status === "complete" && (
    Boolean(approval.approval_id) && reportComplete
    || Boolean(fullApproval.approval_id)
    || String(output.assessment_type || output.service_tier || "").toLowerCase() === "express"
  );
  if (finalReady) {
    output.current_stage = "complete";
    output.progress_percent = 100;
    return output;
  }

  if (step === "scanner_worker" || ["queued", "running"].includes(scanStatus)) {
    output.current_stage = "scanner_worker";
    if (scanPercent !== null) {
      // Repository evidence occupies 0-18%; scanner execution advances through
      // the remaining scanner window to evidence attachment at 62%.
      output.progress_percent = Math.max(18, Math.min(61, Math.round(18 + (scanPercent * 0.43))));
      output.scanner_progress_percent = Math.round(scanPercent);
    } else {
      output.progress_percent = 18;
    }
    return output;
  }

  const explicit = boundedNumber(output.progress_percent);
  const fallback = STAGE_PROGRESS[step];
  if (fallback !== undefined && (explicit === null || explicit < fallback)) output.progress_percent = fallback;
  if (step) output.current_stage = step;
  return output;
}

async function jsonPayload(response: Response): Promise<JsonRecord | null> {
  try {
    const payload = await response.clone().json();
    return payload && typeof payload === "object" ? payload as JsonRecord : null;
  } catch {
    return null;
  }
}

function responseFromPayload(response: Response, payload: JsonRecord): Response {
  const headers = new Headers(response.headers);
  headers.set("Content-Type", "application/json");
  headers.set("Cache-Control", "no-store");
  return new Response(JSON.stringify(payload), {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function matchingTerminalEvidence(payload: JsonRecord | null, runId: string) {
  if (!payload) return false;
  const detail = record(payload.detail);
  const status = String(detail.status || payload.status || "").toLowerCase();
  const responseRunId = String(detail.run_id || payload.run_id || "");
  return responseRunId === runId && TERMINAL_STATUSES.has(status);
}

function rememberMidRun(payload: JsonRecord) {
  const runId = String(payload.run_id || "");
  if (!runId.startsWith("midrun_")) return;
  const status = String(payload.status || "").toLowerCase();
  const final = status === "complete"
    && String(payload.report_generation_status || "").toLowerCase() === "complete"
    && Boolean(record(payload.approval_request).approval_id);
  try {
    if (final || TERMINAL_STATUSES.has(status)) {
      if (window.sessionStorage.getItem(MID_ACTIVE_RUN_KEY) === runId) window.sessionStorage.removeItem(MID_ACTIVE_RUN_KEY);
    } else {
      window.sessionStorage.setItem(MID_ACTIVE_RUN_KEY, runId);
    }
  } catch {
    // Exact-run state remains in the response even if browser storage is unavailable.
  }
}

function temporarilyUnreachable(lastGood: JsonRecord, runId: string): Response {
  const output = normalizedProgress(lastGood);
  const items = progressItems(output);
  const active = activeProgress(output);
  const replacement: ProgressRecord = {
    ...(active || {}),
    status: String(active?.status || "running"),
    message: `Status is temporarily unreachable. Exact run ${runId} remains preserved and NICO will continue read-only status checks without starting a duplicate assessment.`,
  };
  if (active) {
    const index = items.indexOf(active);
    items[index] = replacement;
  } else {
    items.push({step: String(output.current_stage || "status_recovery"), status: "running", message: replacement.message});
  }
  output.status = "running";
  output.run_id = String(output.run_id || runId);
  output.progress = items;
  output.status_transport = {
    status: "temporarily_unreachable",
    consecutive_failures: STATUS_MAX_CONSECUTIVE_FAILURES,
    recovery_required_if_stale: true,
    duplicate_start_allowed: false,
  };
  rememberMidRun(output);
  return new Response(JSON.stringify(output), {
    status: 200,
    headers: {"Content-Type": "application/json", "Cache-Control": "no-store"},
  });
}

function savedRunUnavailable(runId: string, body: JsonRecord): Response {
  const payload: JsonRecord = {
    status: "running",
    run_id: runId,
    repository: body.repository || "",
    customer_id: body.customer_id || "default_customer",
    project_id: body.project_id || "default_project",
    assessment_type: "mid",
    service_tier: "mid",
    current_stage: "status_recovery",
    progress_percent: 4,
    progress: [{
      step: "status_recovery",
      status: "running",
      message: `A saved Mid run (${runId}) exists, but its status is temporarily unreachable. NICO did not start a duplicate assessment. Review Recovery if the run becomes stale.`,
    }],
    status_transport: {
      status: "temporarily_unreachable",
      recovery_required_if_stale: true,
      duplicate_start_allowed: false,
    },
    human_review_required: true,
    client_ready: false,
  };
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: {"Content-Type": "application/json", "Cache-Control": "no-store"},
  });
}

export default function AssessmentStatusResilience() {
  useEffect(() => {
    const originalFetch = window.fetch.bind(window);
    const lastGoodByRun = new Map<string, JsonRecord>();

    const resilientFetch: typeof window.fetch = async (input, init) => {
      const url = requestUrl(input);
      if (!url) return originalFetch(input, init);
      const startMatch = START_PATH.exec(url.pathname);
      const statusMatch = STATUS_PATH.exec(url.pathname);

      if (startMatch) {
        const body = requestBody(input, init);
        if (MID_START_PATH.test(url.pathname)) {
          let savedRunId = "";
          try {
            savedRunId = window.sessionStorage.getItem(MID_ACTIVE_RUN_KEY) || "";
          } catch {
            savedRunId = "";
          }
          if (savedRunId.startsWith("midrun_")) {
            const savedStatusUrl = new URL(`${url.pathname}/${encodeURIComponent(savedRunId)}/status`, url.origin);
            try {
              const savedResponse = await resilientFetch(savedStatusUrl, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({...body, auto_continue: true}),
                cache: "no-store",
                credentials: "same-origin",
                keepalive: true,
              });
              const savedPayload = await jsonPayload(savedResponse);
              if (savedResponse.ok && savedPayload) {
                const normalized = normalizedProgress(savedPayload);
                lastGoodByRun.set(savedRunId, normalized);
                rememberMidRun(normalized);
                return responseFromPayload(savedResponse, normalized);
              }
              if (savedResponse.status !== 404) return savedRunUnavailable(savedRunId, body);
              try {
                window.sessionStorage.removeItem(MID_ACTIVE_RUN_KEY);
              } catch {
                // A missing saved run may still proceed through normal start validation.
              }
            } catch {
              return savedRunUnavailable(savedRunId, body);
            }
          }
        }

        // Assessment starts remain single-shot. Only exact-run status reads retry.
        const response = await originalFetch(input, init);
        const payload = await jsonPayload(response);
        if (response.ok && payload) {
          const normalized = normalizedProgress(payload);
          const runId = String(normalized.run_id || "");
          if (runId) lastGoodByRun.set(runId, normalized);
          rememberMidRun(normalized);
          return responseFromPayload(response, normalized);
        }
        return response;
      }

      if (!statusMatch || String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase() !== "POST") {
        return originalFetch(input, init);
      }

      const runId = decodeURIComponent(statusMatch[1]);
      let lastResponse: Response | null = null;
      let lastError: unknown = null;
      for (let failure = 0; failure < STATUS_MAX_CONSECUTIVE_FAILURES; failure += 1) {
        try {
          const nextInput = input instanceof Request ? input.clone() : input;
          const response = await originalFetch(nextInput, {
            ...init,
            credentials: "same-origin",
            keepalive: true,
          });
          lastResponse = response;
          const payload = await jsonPayload(response);

          if (matchingTerminalEvidence(payload, runId)) return response;
          if (!response.ok && RETRYABLE_HTTP_STATUSES.has(response.status)) {
            if (failure + 1 < STATUS_MAX_CONSECUTIVE_FAILURES) await sleep(retryDelay(failure + 1));
            continue;
          }
          if (response.ok && !payload) {
            if (failure + 1 < STATUS_MAX_CONSECUTIVE_FAILURES) await sleep(retryDelay(failure + 1));
            continue;
          }
          if (payload) {
            const normalized = normalizedProgress(payload);
            lastGoodByRun.set(runId, normalized);
            rememberMidRun(normalized);
            return responseFromPayload(response, normalized);
          }
          return response;
        } catch (error) {
          lastError = error;
          if (failure + 1 < STATUS_MAX_CONSECUTIVE_FAILURES) await sleep(retryDelay(failure + 1));
        }
      }

      const lastGood = lastGoodByRun.get(runId);
      if (lastGood) return temporarilyUnreachable(lastGood, runId);
      if (lastResponse) return lastResponse;
      throw lastError instanceof Error ? lastError : new Error("Assessment status is temporarily unreachable.");
    };

    window.fetch = resilientFetch;
    return () => {
      if (window.fetch === resilientFetch) window.fetch = originalFetch;
    };
  }, []);

  return null;
}

export {
  RETRYABLE_HTTP_STATUSES,
  STATUS_MAX_CONSECUTIVE_FAILURES,
  STATUS_RETRY_BASE_MS,
  STATUS_RETRY_MAX_MS,
  normalizedProgress,
};
