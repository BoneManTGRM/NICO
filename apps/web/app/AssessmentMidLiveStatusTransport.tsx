"use client";

import {useEffect} from "react";

const MID_START_PATH = /^\/(?:api\/nico\/)?assessment\/mid-run$/;
const MID_STATUS_PATH = /^\/(?:api\/nico\/)?assessment\/mid-run\/([^/]+)\/status$/;
const LIVE_RETRY_COUNT = 2;
const LIVE_TIMEOUT_MS = 12_000;
const LIVE_RETRY_DELAY_MS = 1_000;

type JsonRecord = Record<string, unknown>;

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

function responseFromPayload(payload: JsonRecord, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {"Content-Type": "application/json", "Cache-Control": "no-store"},
  });
}

function preservedResponse(lastGood: JsonRecord | undefined, runId: string): Response {
  const output: JsonRecord = lastGood ? structuredClone(lastGood) : {
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
  const message = `Live status is temporarily unavailable. Exact run ${runId} remains preserved; NICO will retry without starting a duplicate assessment.`;
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
    status: "live_status_temporarily_unreachable",
    retry_count: LIVE_RETRY_COUNT,
    duplicate_start_allowed: false,
    recovery_required_if_stale: true,
  };
  return responseFromPayload(output);
}

export default function AssessmentMidLiveStatusTransport() {
  useEffect(() => {
    const previousFetch = window.fetch.bind(window);
    const lastGoodByRun = new Map<string, JsonRecord>();

    const transportFetch: typeof window.fetch = async (input, init) => {
      const url = requestUrl(input);
      if (!url) return previousFetch(input, init);
      const method = String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();

      if (MID_START_PATH.test(url.pathname) && method === "POST") {
        const response = await previousFetch(input, init);
        const payload = await jsonPayload(response);
        const runId = String(payload?.run_id || "");
        if (response.ok && payload && runId.startsWith("midrun_")) lastGoodByRun.set(runId, payload);
        return response;
      }

      const match = MID_STATUS_PATH.exec(url.pathname);
      if (!match || method !== "POST") return previousFetch(input, init);

      const runId = decodeURIComponent(match[1]);
      const body = bodyPayload(init);
      const prefix = url.pathname.startsWith("/api/nico/") ? "/api/nico" : "";
      const liveUrl = new URL(`${prefix}/assessment/mid-run/${encodeURIComponent(runId)}/live-status`, url.origin);
      const customerId = String(body.customer_id || "");
      const projectId = String(body.project_id || "");
      if (customerId) liveUrl.searchParams.set("customer_id", customerId);
      if (projectId) liveUrl.searchParams.set("project_id", projectId);

      let lastLiveResponse: Response | null = null;
      for (let attempt = 1; attempt <= LIVE_RETRY_COUNT; attempt += 1) {
        try {
          const liveResponse = await previousFetch(liveUrl, {
            method: "GET",
            cache: "no-store",
            credentials: "same-origin",
            signal: AbortSignal.timeout(LIVE_TIMEOUT_MS),
          });
          lastLiveResponse = liveResponse;
          const livePayload = await jsonPayload(liveResponse);
          if (liveResponse.ok && livePayload) {
            lastGoodByRun.set(runId, livePayload);
            if (livePayload.continuation_required === true) {
              const continuation = await previousFetch(input, init);
              const continuationPayload = await jsonPayload(continuation);
              if (continuation.ok && continuationPayload) lastGoodByRun.set(runId, continuationPayload);
              return continuation;
            }
            return liveResponse;
          }
          if (liveResponse.status === 404) return previousFetch(input, init);
        } catch {
          // Bounded live-status retry below.
        }
        if (attempt < LIVE_RETRY_COUNT) await sleep(LIVE_RETRY_DELAY_MS);
      }

      if (lastLiveResponse?.status === 404) return previousFetch(input, init);
      return preservedResponse(lastGoodByRun.get(runId), runId);
    };

    window.fetch = transportFetch;
    return () => {
      if (window.fetch === transportFetch) window.fetch = previousFetch;
    };
  }, []);

  return null;
}
