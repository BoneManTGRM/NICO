"use client";

import {useEffect} from "react";

const ASSESSMENT_PATH = /^\/(?:api\/nico\/)?assessment\/(?:express-run|mid-run|full-run)(?:\/[^/?#]+\/status)?$/;
const STATUS_PATH = /^\/(?:api\/nico\/)?assessment\/(?:express-run|mid-run|full-run)\/([^/?#]+)\/status$/;
const TERMINAL_STATUSES = new Set(["blocked", "failed", "error", "interrupted", "rejected"]);

type JsonRecord = Record<string, unknown>;
type ProgressRecord = {step?: unknown; status?: unknown; message?: unknown; evidence?: unknown};

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

async function responsePayload(response: Response): Promise<JsonRecord | null> {
  try {
    const parsed = await response.clone().json();
    return parsed && typeof parsed === "object" ? parsed as JsonRecord : null;
  } catch {
    return null;
  }
}

function lifecycleIdentity(payload: JsonRecord | null) {
  const detail = record(payload?.detail);
  return {
    runId: String(detail.run_id || payload?.run_id || ""),
    status: String(detail.status || payload?.status || "").toLowerCase(),
    code: String(detail.code || payload?.code || ""),
  };
}

function progressItems(payload: JsonRecord): ProgressRecord[] {
  return Array.isArray(payload.progress)
    ? payload.progress.filter((item): item is ProgressRecord => Boolean(item) && typeof item === "object")
    : [];
}

function recoveryResponse(
  runId: string,
  response: Response,
  payload: JsonRecord | null,
  lastGood: JsonRecord | undefined,
): Response {
  const output: JsonRecord = lastGood ? structuredClone(lastGood) : {
    status: "running",
    run_id: runId,
    current_stage: "status_recovery",
    progress_percent: 4,
    progress: [],
    human_review_required: true,
    client_ready: false,
  };
  const identity = lifecycleIdentity(payload);
  const code = identity.code || `http_${response.status}`;
  const message = `Status check returned HTTP ${response.status} (${code}) without exact-run terminal evidence. Exact run ${runId} remains preserved; review Recovery if status remains unavailable.`;
  const items = progressItems(output);
  const activeIndex = items.findIndex((item) => ["queued", "running", "pending", "planned", "starting"].includes(String(item.status || "").toLowerCase()));
  const replacement: ProgressRecord = {
    ...(activeIndex >= 0 ? items[activeIndex] : {}),
    step: activeIndex >= 0 ? items[activeIndex].step : String(output.current_stage || "status_recovery"),
    status: "running",
    message,
  };
  if (activeIndex >= 0) items[activeIndex] = replacement;
  else items.push(replacement);

  output.status = "running";
  output.run_id = String(output.run_id || runId);
  output.progress = items;
  output.status_transport = {
    status: "request_rejected",
    http_status: response.status,
    code,
    exact_run_terminal_evidence: false,
    duplicate_start_allowed: false,
    recovery_required_if_stale: true,
  };
  return new Response(JSON.stringify(output), {
    status: 200,
    headers: {"Content-Type": "application/json", "Cache-Control": "no-store"},
  });
}

export default function AssessmentStatusOutcomeGuard() {
  useEffect(() => {
    const originalFetch = window.fetch.bind(window);
    const lastGoodByRun = new Map<string, JsonRecord>();

    const guardedFetch: typeof window.fetch = async (input, init) => {
      const url = requestUrl(input);
      if (!url || !ASSESSMENT_PATH.test(url.pathname)) return originalFetch(input, init);

      const response = await originalFetch(input, init);
      const payload = await responsePayload(response);
      const statusMatch = STATUS_PATH.exec(url.pathname);
      if (!statusMatch) {
        if (response.ok && payload) {
          const runId = String(payload.run_id || "");
          if (runId) lastGoodByRun.set(runId, payload);
        }
        return response;
      }

      const runId = decodeURIComponent(statusMatch[1]);
      if (response.ok && payload) {
        lastGoodByRun.set(runId, payload);
        return response;
      }

      const identity = lifecycleIdentity(payload);
      if (identity.runId === runId && TERMINAL_STATUSES.has(identity.status)) return response;

      // An HTTP/proxy/request-validation failure is evidence about the status
      // request, not evidence that the assessment failed. Preserve the last
      // accepted exact-run state and keep the operator on the Recovery path.
      return recoveryResponse(runId, response, payload, lastGoodByRun.get(runId));
    };

    window.fetch = guardedFetch;
    return () => {
      if (window.fetch === guardedFetch) window.fetch = originalFetch;
    };
  }, []);

  return null;
}
