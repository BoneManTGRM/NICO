"use client";

import {useEffect} from "react";

const MID_ACTIVE_RUN_KEY = "nico.mid.active_run";
const MID_START_PATH = /^\/(?:api\/nico\/)?assessment\/mid-run$/;
const TERMINAL_STATUSES = new Set(["blocked", "failed", "error", "interrupted", "rejected"]);

type JsonRecord = Record<string, unknown>;

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

function requestBody(init?: RequestInit): JsonRecord {
  if (typeof init?.body !== "string") return {};
  try {
    const value = JSON.parse(init.body);
    return value && typeof value === "object" ? value as JsonRecord : {};
  } catch {
    return {};
  }
}

async function responsePayload(response: Response): Promise<JsonRecord | null> {
  try {
    const value = await response.clone().json();
    return value && typeof value === "object" ? value as JsonRecord : null;
  } catch {
    return null;
  }
}

function lifecycleIdentity(payload: JsonRecord | null) {
  const detail = record(payload?.detail);
  return {
    runId: String(detail.run_id || payload?.run_id || ""),
    status: String(detail.status || payload?.status || "").toLowerCase(),
  };
}

function clearSavedRun(runId: string) {
  try {
    if (window.sessionStorage.getItem(MID_ACTIVE_RUN_KEY) === runId) {
      window.sessionStorage.removeItem(MID_ACTIVE_RUN_KEY);
    }
  } catch {
    // The backend response remains authoritative when browser storage is unavailable.
  }
}

function safeUnavailableResponse(runId: string, body: JsonRecord): Response {
  return new Response(JSON.stringify({
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
      message: `Saved Mid run ${runId} could not be reached. NICO preserved the exact run and did not create a duplicate assessment. Review Recovery if the run becomes stale.`,
    }],
    status_transport: {
      status: "temporarily_unreachable",
      recovery_required_if_stale: true,
      duplicate_start_allowed: false,
    },
    human_review_required: true,
    client_ready: false,
  }), {
    status: 200,
    headers: {"Content-Type": "application/json", "Cache-Control": "no-store"},
  });
}

export default function AssessmentSavedMidRunGuard() {
  useEffect(() => {
    const originalFetch = window.fetch.bind(window);

    const guardedFetch: typeof window.fetch = async (input, init) => {
      const url = requestUrl(input);
      const method = String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
      if (!url || method !== "POST" || !MID_START_PATH.test(url.pathname)) {
        return originalFetch(input, init);
      }

      let savedRunId = "";
      try {
        savedRunId = window.sessionStorage.getItem(MID_ACTIVE_RUN_KEY) || "";
      } catch {
        savedRunId = "";
      }
      if (!savedRunId.startsWith("midrun_")) return originalFetch(input, init);

      const body = requestBody(init);
      const statusUrl = new URL(`${url.pathname}/${encodeURIComponent(savedRunId)}/status`, url.origin);
      try {
        const statusResponse = await originalFetch(statusUrl, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({...body, auto_continue: true}),
          cache: "no-store",
          credentials: "same-origin",
          keepalive: true,
        });
        const payload = await responsePayload(statusResponse);
        const identity = lifecycleIdentity(payload);

        // Exact-run failed or blocked evidence stays terminal. It is never
        // rewritten as a transport outage or retried into a new assessment.
        if (identity.runId === savedRunId && TERMINAL_STATUSES.has(identity.status)) {
          clearSavedRun(savedRunId);
          return statusResponse;
        }
        if (statusResponse.ok && payload) return statusResponse;
        if (statusResponse.status === 404) {
          clearSavedRun(savedRunId);
          return originalFetch(input, init);
        }
        return safeUnavailableResponse(savedRunId, body);
      } catch {
        return safeUnavailableResponse(savedRunId, body);
      }
    };

    window.fetch = guardedFetch;
    return () => {
      if (window.fetch === guardedFetch) window.fetch = originalFetch;
    };
  }, []);

  return null;
}
